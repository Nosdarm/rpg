import asyncio
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Any, Coroutine, Callable, Dict, List, Tuple, AsyncContextManager

from .database import get_db_session, transactional
from ..models import Player, Party, PendingConflict
from ..models.enums import PlayerStatus, PartyTurnStatus, ConflictStatus
from ..models.actions import ParsedAction
from .rules import get_rule # For conflict_resolution_rules
from .player_utils import get_player # Generic get by PK
from .party_utils import get_party # Generic get by PK

# Placeholder imports for actual game modules - these will be called by dispatch
# from .movement_logic import handle_move_action_internal # Needs to be created/adapted
# from .some_other_module import handle_look_action_internal
# from .inventory_module import handle_inventory_action_internal
# from .quest_module import handle_quest_event_internal
# from .interaction_module import handle_intra_location_interaction_internal
from .interaction_handlers import handle_intra_location_action
from .game_events import log_event
from ..bot.utils import notify_master # Utility to notify master
from .combat_cycle_manager import start_combat, process_combat_turn # Added process_combat_turn
from .combat_engine import process_combat_action as engine_process_combat_action # Alias to avoid confusion
from ..models import GeneratedNpc # For fetching target NPC
from .crud.crud_player import player_crud # Changed import
from .crud.crud_npc import npc_crud # Changed import
from .crud.crud_combat_encounter import combat_encounter_crud # Changed: Removed get_active_combat_for_entity

logger = logging.getLogger(__name__)

# --- Action Handler Placeholders ---
# These would ideally be in their respective modules and imported.
# They need to accept session, guild_id, player_id, and action_data.

async def _handle_placeholder_action(
    session: AsyncSession, guild_id: int, player_id: int, action: ParsedAction
) -> dict:
    logger.info(f"[ACTION_PROCESSOR] Guild {guild_id}, Player {player_id}: Handling placeholder action '{action.intent}' with data: {action.entities}")
    # In a real handler:
    # 1. Load necessary game state (player, target entities, location, etc.) using session and guild_id.
    # 2. Perform game logic based on action.intent and action.entities.
    # 3. Update database state via session.
    # 4. Return results/feedback.
    await log_event(session=session, guild_id=guild_id, event_type=f"ACTION_{action.intent.upper()}_EXECUTED",
                    details_json={"player_id": player_id, "action": action.model_dump(mode='json')}, player_id=player_id)
    return {"status": "success", "message": f"Action '{action.intent}' handled by placeholder."}

async def _handle_move_action_wrapper(
    session: AsyncSession, guild_id: int, player_id: int, action: ParsedAction
) -> dict:
    logger.info(f"[ACTION_PROCESSOR] Guild {guild_id}, Player {player_id}: Handling MOVE action: {action.entities}")
    try:
        from src.core.movement_logic import execute_move_for_player_action # Import here to avoid circular deps at module level if any

        target_location_identifier = None
        # Try to get identifier from entities. NLU might provide it under various keys.
        # Common ones could be 'name', 'destination', 'target_location', 'location_static_id'.
        if action.entities:
            for entity in action.entities:
                # Corrected: use entity.type instead of entity.entity_type
                if entity.type == "location_name" or entity.type == "location_static_id":
                    target_location_identifier = entity.value
                    break
            # Fallback or alternative common keys if not found by specific entity_type
            if not target_location_identifier:
                if len(action.entities) == 1: # If only one entity, assume it's the target
                     target_location_identifier = action.entities[0].value
                else: # Heuristic: look for common keys
                    for entity in action.entities:
                        # Corrected: use entity.type instead of entity.entity_type
                        if entity.type.lower() in ["destination", "target", "location"]:
                             target_location_identifier = entity.value
                             break


        if not target_location_identifier:
            # Fallback: if intent is 'move' and there's a single entity value, use it.
            # This might be fragile and depends on NLU output structure.
            # A more robust NLU would clearly label the target location entity.
            # For now, let's assume NLU provides at least one entity that is the target.
            # If action.entities is a list of {'entity_type': 'some_type', 'value': 'some_value'}
            if action.entities and isinstance(action.entities, list) and len(action.entities) > 0:
                 # Let's assume the NLU is simple and the first entity value is the target if not specifically typed.
                 # This part needs to be robust based on actual NLU output.
                 # For this implementation, we'll be strict: NLU must provide an entity we can identify as the target.
                 # The logic above tries to find a suitable entity. If none, then it's an error.
                 pass # Identifier already sought above

        if not target_location_identifier:
            logger.warning(f"Player {player_id} MOVE action: Target location identifier not found in entities: {action.entities}")
            return {"status": "error", "message": "Where do you want to move? Target location not specified clearly."}

        logger.info(f"Player {player_id} MOVE action: Attempting to move to '{target_location_identifier}'.")
        result = await execute_move_for_player_action(
            session=session,
            guild_id=guild_id,
            player_id=player_id,
            target_location_identifier=target_location_identifier
        )
        return result
    except Exception as e:
        logger.error(f"Error in _handle_move_action_wrapper for player {player_id}: {e}", exc_info=True)
        return {"status": "error", "message": f"Failed to execute move action due to an internal error: {e}"}

async def _handle_intra_location_action_wrapper(
    session: AsyncSession, guild_id: int, player_id: int, action: ParsedAction
) -> dict:
    """
    Wrapper for handle_intra_location_action to match ACTION_DISPATCHER signature.
    It uses action.intent directly and passes action.model_dump() as action_data.
    """
    logger.info(f"[ACTION_PROCESSOR] Guild {guild_id}, Player {player_id}: Handling intra-location action '{action.intent}' with data: {action.entities}")
    try:
        # We pass the full ParsedAction.model_dump() as action_data,
        # handle_intra_location_action will look for 'intent' and 'entities' within it.
        action_data_dict = action.model_dump(mode='json')
        result_dict = await handle_intra_location_action(
            guild_id=guild_id,
            session=session,
            player_id=player_id,
            action_data=action_data_dict # Pass the whole action dict
        )
        return result_dict
    except Exception as e:
        logger.error(f"Error in _handle_intra_location_action_wrapper for intent {action.intent}: {e}", exc_info=True)
        return {"status": "error", "message": f"Failed to execute intra-location action '{action.intent}': {e}"}

async def _handle_attack_action_wrapper(
    session: AsyncSession, guild_id: int, player_id: int, action: ParsedAction
) -> dict:
    logger.info(f"[ACTION_PROCESSOR] Guild {guild_id}, Player {player_id}: Handling ATTACK action: {action.entities}")
    actor_player = await player_crud.get_by_id_and_guild(session, id=player_id, guild_id=guild_id) # Changed call
    if not actor_player:
        return {"status": "error", "message": "Attacking player not found."}

    # 1. Determine Target
    target_entity_data = None # Will store {'id': int, 'type': str, 'name': str, 'model': Player | GeneratedNpc}
    if not action.entities:
        return {"status": "error", "message": "Who do you want to attack? Target not specified."}

    # Assuming NLU provides target name or ID. For MVP, let's assume target is an NPC by name.
    # A more robust system would handle targeting players, use IDs, etc.
    target_identifier = action.entities[0].value # Simplistic: take first entity value as target name
    target_type_hint = action.entities[0].type # e.g., "npc_name", "player_name"

    # Try to find NPC target by name in the same location as the player
    # This requires knowing player's current location.
    if actor_player.current_location_id is None:
        return {"status": "error", "message": "Cannot attack: your location is unknown."}

    # Simplified target finding:
    # For now, assume target is an NPC. A full implementation needs to:
    # - Query NPCs in player's current_location_id by name (target_identifier)
    # - Query Players in current_location_id by name (if target_type_hint suggests player)
    # - Handle ambiguous targets (multiple NPCs/players with same name)

    # MVP: Assume target is NPC, search by name.
    # This is a placeholder for proper target resolution.
    # In a real system, you'd use CRUD operations to find entities by name in a location.
    # For now, we'll assume NLU gives a specific enough target name.
    # Let's imagine we have a way to get the target model.
    # For testing, we might need to mock this or create a dummy target.

    # Placeholder: Find target NPC (this is a very simplified lookup)
    # In a real scenario, this would involve querying NPCs at the player's location.
    # For now, let's assume the target_identifier is a unique NPC name in the location.
    # We'll need a way to fetch NPCs by name for the guild.
    # This part is complex and depends on how NPCs are stored and identified.
    # Let's assume for now target_identifier is an ID and type is known.
    # This is a major simplification for the attack wrapper.
    # A proper implementation would use NLU context (e.g. target from previous interaction) or more specific targeting.

    # Simplified: Assume target is an NPC and target_identifier is its ID for now.
    # This is a temporary simplification to proceed with combat flow.
    # NLU should ideally provide target ID and type.
    # If NLU provides name, a lookup step is needed.
    target_id_from_nlu = None
    target_type_from_nlu = None

    if action.entities:
        # A more robust NLU would provide 'target_id' and 'target_type' entities
        # For now, crude extraction:
        first_entity = action.entities[0]
        if first_entity.type.lower() in ["npc", "target_npc", "enemy_npc"]:
            target_type_from_nlu = "npc"
            # Try to convert value to int if it's an ID, otherwise it's a name
            try: target_id_from_nlu = int(first_entity.value)
            except ValueError:
                 # It's a name, need to look up ID. This is the complex part.
                 # For now, we'll error if ID isn't provided by NLU for NPCs.
                 logger.warning(f"NPC target '{first_entity.value}' provided by name. ID lookup not yet implemented in MVP attack handler. Assuming it's an ID for now if it can be cast to int.")
                 # This part is a placeholder for actual name->ID resolution.
                 # If we can't get an ID, we can't proceed easily.
                 return {"status": "error", "message": f"Targeting NPC by name ('{first_entity.value}') not fully supported yet. Please use NPC ID if known."}

        elif first_entity.type.lower() in ["player", "target_player"]:
            target_type_from_nlu = "player"
            try: target_id_from_nlu = int(first_entity.value)
            except ValueError:
                return {"status": "error", "message": f"Targeting Player by name ('{first_entity.value}') not fully supported yet. Please use Player ID."}
        else: # Fallback: assume it's an NPC name if type is generic like 'target_name' or just 'name'
            target_type_from_nlu = "npc" # Default assumption
            logger.warning(f"Generic target '{first_entity.value}' (type: {first_entity.type}). Assuming NPC. Name lookup needed.")
            # This is where robust target name resolution would go.
            # For now, if it's not an int, we can't proceed without a name lookup system.
            try: target_id_from_nlu = int(first_entity.value)
            except ValueError:
                 return {"status": "error", "message": f"Could not determine target ID for '{first_entity.value}'. Name lookup required."}


    if target_id_from_nlu is None or target_type_from_nlu is None:
        return {"status": "error", "message": "Target ID or type could not be determined from NLU."}

    target_model = None
    if target_type_from_nlu == "npc":
        target_model = await npc_crud.get_by_id_and_guild(session=session, id=target_id_from_nlu, guild_id=guild_id)
        if target_model:
            target_entity_data = {"id": target_model.id, "type": "npc", "name": target_model.name_i18n.get("en", "NPC"), "model": target_model}
    elif target_type_from_nlu == "player":
        target_model = await player_crud.get_by_id_and_guild(session=session, id=target_id_from_nlu, guild_id=guild_id) # Changed call
        if target_model:
            target_entity_data = {"id": target_model.id, "type": "player", "name": target_model.name, "model": target_model}

    if not target_entity_data or not target_model:
        return {"status": "error", "message": f"Target {target_type_from_nlu} with identifier '{target_identifier}' not found."}

    # Check if target is self
    if target_entity_data["id"] == actor_player.id and target_entity_data["type"] == "player":
        return {"status": "error", "message": "You cannot attack yourself."}

    # 2. Check Existing Combat
    # Check for actor
    actor_combat = await combat_encounter_crud.get_active_combat_for_entity( # Changed call
        session=session, guild_id=guild_id, entity_id=actor_player.id, entity_type="player"
    )
    # Check for target
    target_combat = await combat_encounter_crud.get_active_combat_for_entity( # Changed call
        session=session, guild_id=guild_id, entity_id=target_entity_data["id"], entity_type=target_entity_data["type"]
    )

    if actor_combat and target_combat and actor_combat.id != target_combat.id:
        return {"status": "error", "message": "You and your target are in different active combat encounters."}

    current_combat_encounter = actor_combat or target_combat
    initial_action_to_process = {
        "action_type": "attack", # This comes from the player's intent
        # "ability_id": None, # For basic attack
        "target_id": target_entity_data["id"],
        "target_type": target_entity_data["type"]
        # Other details like weapon used could be added if NLU provides them or game rules imply them
    }

    if current_combat_encounter:
        # Already in combat, process the action directly
        logger.info(f"Player {player_id} attacking target {target_entity_data['name']} within existing combat {current_combat_encounter.id}")
        if not (current_combat_encounter.current_turn_entity_id == actor_player.id and \
                current_combat_encounter.current_turn_entity_type == "player"):
            return {"status": "error", "message": "It's not your turn to act in the current combat."}

        # Process player's action
        player_action_result = await engine_process_combat_action(
            guild_id=guild_id,
            session=session,
            combat_instance_id=current_combat_encounter.id,
            actor_id=actor_player.id,
            actor_type="player",
            action_data=initial_action_to_process
        )
        logger.info(f"Player {player_id} action in combat {current_combat_encounter.id} processed. Result: {player_action_result.description_i18n}")

        # After player's action, call process_combat_turn to advance combat state (NPC turns, end check)
        # The session here is the same one used by engine_process_combat_action, so changes are visible.
        updated_combat_encounter = await process_combat_turn(
            session=session,
            guild_id=guild_id,
            combat_id=current_combat_encounter.id
        )
        logger.info(f"Combat {updated_combat_encounter.id} advanced. Current status: {updated_combat_encounter.status}, current turn: {updated_combat_encounter.current_turn_entity_type}:{updated_combat_encounter.current_turn_entity_id}")

        return {
            "status": "success",
            "message": "Attack action processed and combat turn advanced.",
            "initial_action_details": player_action_result.model_dump(),
            "combat_status_after_turn": updated_combat_encounter.status.value,
            "current_combat_turn_entity": f"{updated_combat_encounter.current_turn_entity_type}:{updated_combat_encounter.current_turn_entity_id}"
        }
    else:
        # No existing combat for either actor or target that involves both, start a new one
        logger.info(f"Player {player_id} initiating combat by attacking target {target_entity_data['name']}")
        # Determine participants for the new combat
        # MVP: Just actor and target.
        # Future: Could include other entities in the location based on rules (e.g., allies, nearby hostiles).
        participant_models = [actor_player, target_entity_data["model"]]

        # Add other NPCs from the same location if they are hostile to the player or allied with the target
        # This is a complex part that needs rules for "joining combat"
        # For MVP, keep it simple: only player and their direct target.

        try:
            new_combat_encounter = await start_combat(
                session=session,
                guild_id=guild_id,
                location_id=actor_player.current_location_id,
                participant_entities=participant_models
                # initiator_action_data is not directly used by start_combat to process the first action.
                # The first action is processed immediately after start_combat returns.
            )
            logger.info(f"Combat started: {new_combat_encounter.id}. Now processing initiator's action.")

            # Process the initiator's first action in the new combat
            # Ensure the initiator is indeed the first in turn order (start_combat should handle this)
            if not (new_combat_encounter.current_turn_entity_id == actor_player.id and \
                    new_combat_encounter.current_turn_entity_type == "player"):
                # This would be an issue with start_combat's initiative logic if player isn't first
                logger.error(f"Combat started, but initiator Player {actor_player.id} is not the first in turn order. Combat: {new_combat_encounter.id}")
                # Fallback: try to process anyway if combat is active.
                # Or return error. For now, let's be lenient and try.
                # This implies the player might have to wait for their turn if initiative was lost.
                # However, the plan stated: "первое действие атакующего... должно быть обработано как первое действие в бою"
                # This means start_combat should ensure the initiator can act, or this wrapper should.
                # For now, assume start_combat sets turn correctly or we process regardless of whose turn it is *for the first action*.
                # A stricter approach: if not player's turn, they can't act yet.
                # Let's assume for the very first action of combat, the initiator gets to act.
                # The call to engine_process_combat_action will use actor_id, actor_type from its params.
                pass


            action_result = await engine_process_combat_action(
                guild_id=guild_id,
                session=session,
                combat_instance_id=new_combat_encounter.id,
                actor_id=actor_player.id,
                actor_type="player",
                action_data=initial_action_to_process
            )
            logger.info(f"Player {actor_player.id} initial action in new combat {new_combat_encounter.id} processed. Result: {action_result.description_i18n}")

            # After initiator's action, call process_combat_turn to advance combat state
            updated_combat_encounter = await process_combat_turn(
                session=session,
                guild_id=guild_id,
                combat_id=new_combat_encounter.id
            )
            logger.info(f"New combat {updated_combat_encounter.id} advanced after initiator. Current status: {updated_combat_encounter.status}, current turn: {updated_combat_encounter.current_turn_entity_type}:{updated_combat_encounter.current_turn_entity_id}")

            return {
                "status": "success",
                "message": "Combat started, initial attack processed, and combat turn advanced.",
                "combat_id": new_combat_encounter.id,
                "initial_action_details": action_result.model_dump(),
                "combat_status_after_turn": updated_combat_encounter.status.value,
                "current_combat_turn_entity": f"{updated_combat_encounter.current_turn_entity_type}:{updated_combat_encounter.current_turn_entity_id}"
            }

        except Exception as e:
            logger.error(f"Error starting combat or processing initial attack for player {player_id}: {e}", exc_info=True)
            return {"status": "error", "message": f"Failed to start combat: {e}"}


# Action dispatch table
ACTION_DISPATCHER: dict[str, Callable[[AsyncSession, int, int, ParsedAction], Coroutine[Any, Any, dict]]] = {
    "move": _handle_move_action_wrapper, # This is for inter-location movement
    "look": _handle_placeholder_action, # General look, might be different from examining specific object
    "attack": _handle_attack_action_wrapper, # Placeholder for combat
    "take": _handle_placeholder_action,  # Placeholder for inventory
    "use": _handle_placeholder_action,   # Placeholder for inventory/item use
    "talk": _handle_placeholder_action, # Placeholder for dialogue
    "examine": _handle_intra_location_action_wrapper, # examine specific object/feature in location
    "interact": _handle_intra_location_action_wrapper, # interact with specific object/feature
    "go_to": _handle_intra_location_action_wrapper, # move to sublocation / named point within current location
    # NLU should be updated to produce "examine", "interact", "go_to" (for sublocations)
    # instead of the previous generic "examine" placeholder.
    # Add more intents and their handlers here
}

# @transactional # Wraps the initial loading and clearing of actions in a transaction - REMOVED
async def _load_and_clear_actions_for_entity(session: AsyncSession, guild_id: int, entity_id: int, entity_type: str) -> list[ParsedAction]:
    """Loads actions for a single entity and clears them from the DB."""
    actions_to_process = []
    if entity_type == "player":
        player = await get_player(session, guild_id, entity_id) # Corrected
        if player and player.collected_actions_json:
            logger.debug(f"Player {entity_id} raw collected_actions_json: {player.collected_actions_json}")
            try:
                actions_data = json.loads(player.collected_actions_json) if isinstance(player.collected_actions_json, str) else player.collected_actions_json
                logger.debug(f"Player {entity_id} actions_data after potential json.loads: {actions_data}")
                for i, action_data_item in enumerate(actions_data):
                    try:
                        actions_to_process.append(ParsedAction(**action_data_item))
                    except Exception as e_parse:
                        logger.error(f"Player {entity_id}, action item {i} failed Pydantic parsing: {action_data_item}", exc_info=True)
                player.collected_actions_json = [] # Clear actions
                session.add(player)
                logger.info(f"[ACTION_PROCESSOR] Loaded {len(actions_to_process)} actions for player {player.id} and cleared from DB.")
            except json.JSONDecodeError:
                logger.error(f"[ACTION_PROCESSOR] Failed to decode actions for player {player.id}", exc_info=True)
                player.collected_actions_json = [] # Clear invalid actions on JSONDecodeError too
                session.add(player)
            except Exception as e: # Other errors
                logger.error(f"[ACTION_PROCESSOR] Error processing actions_data for player {player.id}: {e}", exc_info=True)
                player.collected_actions_json = [] # Clear invalid actions
                session.add(player)
        elif player:
            logger.debug(f"Player {entity_id} found, but collected_actions_json is empty or None: {player.collected_actions_json}")
        else:
            logger.debug(f"Player {entity_id} not found by get_player.")


    elif entity_type == "party":
        party = await get_party(session, guild_id, entity_id) # Corrected
        if party:
            # Party actions might be stored differently, e.g., on a party model or aggregated from members.
            # For now, assume party actions are collected similarly or this part needs specific logic.
            # MVP: Assume party actions are implicitly handled via player actions within the party.
            # Or, a party might have its own `collected_actions_json` if a party leader submits them.
            # This part is conceptual for now for party-specific actions.
            logger.info(f"[ACTION_PROCESSOR] Party {party.id}: Party-level action collection not yet implemented. Processing member actions.")
            # If parties had their own action queue:
            # if party.collected_actions_json:
            #     actions_data = json.loads(party.collected_actions_json)
            #     for action_data in actions_data: actions_to_process.append(ParsedAction(**action_data))
            #     party.collected_actions_json = []
            #     session.add(party)
    return actions_to_process


async def _load_and_clear_all_actions(
    session: AsyncSession, guild_id: int, entities_and_types_to_process: list[dict]
) -> list[tuple[int, ParsedAction]]:
    """
    Loads actions for all relevant players and clears them from the DB in a single transaction.
    Optimized to load players and parties in batches.
    Returns a list of (player_id, action) tuples.
    """
    all_player_actions_for_turn: list[tuple[int, ParsedAction]] = []

    player_entity_ids_direct = {info["id"] for info in entities_and_types_to_process if info["type"] == "player"}
    party_entity_ids = {info["id"] for info in entities_and_types_to_process if info["type"] == "party"}

    all_player_ids_to_process_actions_for = set(player_entity_ids_direct)
    parties_map: Dict[int, Party] = {}

    if party_entity_ids:
        # Dynamically import party_crud here if not already available at module level
        # For now, assume party_crud is available similar to how player_crud would be.
        # from .crud.crud_party import party_crud # This might cause circular if party_crud needs this module
        # A better approach would be to pass crud instances or use a registry.
        # For this refactor, let's assume party_crud is accessible.
        # This import might need adjustment based on actual project structure and dependencies.
        from .crud.crud_party import party_crud # Assuming this is safe

        loaded_parties = await party_crud.get_many_by_ids(session=session, ids=list(party_entity_ids), guild_id=guild_id)
        for party in loaded_parties:
            parties_map[party.id] = party
            if party.player_ids_json:
                for p_id in party.player_ids_json:
                    all_player_ids_to_process_actions_for.add(p_id)

    if not all_player_ids_to_process_actions_for:
        logger.info(f"[ACTION_PROCESSOR] Guild {guild_id}: No players found to process actions for.")
        return []

    # Dynamically import player_crud
    from .crud.crud_player import player_crud

    loaded_players_list = await player_crud.get_many_by_ids(session=session, ids=list(all_player_ids_to_process_actions_for), guild_id=guild_id)
    players_map: Dict[int, Player] = {p.id: p for p in loaded_players_list}

    for player_id, player_obj in players_map.items():
        if player_obj.collected_actions_json:
            logger.debug(f"Player {player_id} raw collected_actions_json: {player_obj.collected_actions_json}")
            try:
                actions_data = json.loads(player_obj.collected_actions_json) if isinstance(player_obj.collected_actions_json, str) else player_obj.collected_actions_json
                logger.debug(f"Player {player_id} actions_data after potential json.loads: {actions_data}")
                for i, action_data_item in enumerate(actions_data):
                    try:
                        parsed_action = ParsedAction(**action_data_item)
                        all_player_actions_for_turn.append((player_id, parsed_action))
                    except Exception as e_parse:
                        logger.error(f"Player {player_id}, action item {i} failed Pydantic parsing: {action_data_item}", exc_info=True)
                player_obj.collected_actions_json = [] # Clear actions
                session.add(player_obj) # Add to session to mark for update
            except json.JSONDecodeError:
                logger.error(f"[ACTION_PROCESSOR] Failed to decode actions for player {player_id}", exc_info=True)
                player_obj.collected_actions_json = []
                session.add(player_obj)
            except Exception as e:
                logger.error(f"[ACTION_PROCESSOR] Error processing actions_data for player {player_id}: {e}", exc_info=True)
                player_obj.collected_actions_json = []
                session.add(player_obj)
        elif player_obj:
            logger.debug(f"Player {player_id} found, but collected_actions_json is empty or None: {player_obj.collected_actions_json}")

    if all_player_actions_for_turn:
        logger.info(f"[ACTION_PROCESSOR] Guild {guild_id}: Prepared {len(all_player_actions_for_turn)} actions from {len(players_map)} players for processing.")

    return all_player_actions_for_turn


async def _execute_player_actions(
    session_maker: Callable[[], AsyncContextManager[AsyncSession]],
    guild_id: int,
    all_player_actions_for_turn: list[tuple[int, ParsedAction]]
) -> list[dict]:
    """
    Executes all player actions, each in its own transaction.
    Returns a list of action results.
    """
    processed_actions_results = []
    for player_id, action in all_player_actions_for_turn:
        async with session_maker() as action_session:  # New session for each action's transaction
            try:
                async with action_session.begin():  # Start transaction for this action
                    handler = ACTION_DISPATCHER.get(action.intent, _handle_placeholder_action)
                    logger.info(f"[ACTION_PROCESSOR] Guild {guild_id}, Player {player_id}: Dispatching action '{action.intent}' to {handler.__name__}")
                    action_result = await handler(action_session, guild_id, player_id, action)
                    processed_actions_results.append({"player_id": player_id, "action": action.model_dump(mode='json'), "result": action_result})
                logger.info(f"[ACTION_PROCESSOR] Guild {guild_id}, Player {player_id}: Action '{action.intent}' committed successfully.")
            except Exception as e:
                logger.error(f"[ACTION_PROCESSOR] Guild {guild_id}, Player {player_id}: Error processing action '{action.intent}': {e}", exc_info=True)
                processed_actions_results.append({
                    "player_id": player_id,
                    "action": action.model_dump(mode='json'),
                    "result": {"status": "error", "message": str(e)}
                })
                # Log event within the same session if possible, but outside the failed transaction
                try:
                    async with action_session.begin(): # Attempt a new transaction for logging
                        await log_event(action_session, guild_id=guild_id, event_type="ACTION_PROCESSING_ERROR",
                                        details_json={"player_id": player_id, "action": action.model_dump(mode='json'), "error": str(e)}, player_id=player_id)
                    logger.info(f"[ACTION_PROCESSOR] Guild {guild_id}, Player {player_id}: ACTION_PROCESSING_ERROR event logged.")
                except Exception as log_e:
                    logger.error(f"[ACTION_PROCESSOR] Guild {guild_id}, Player {player_id}: Failed to log ACTION_PROCESSING_ERROR: {log_e}", exc_info=True)
    return processed_actions_results


async def _finalize_turn_processing(
    session_maker: Callable[[], AsyncContextManager[AsyncSession]],
    guild_id: int,
    entities_and_types_to_process: list[dict],
    processed_actions_results_count: int
) -> None:
    """
    Updates entity statuses and logs the completion of the guild turn.
    """
    async with session_maker() as final_session:
        async with final_session.begin():
            for entity_info in entities_and_types_to_process:
                entity_id = entity_info["id"]
                entity_type = entity_info["type"]
                if entity_type == "player":
                    player = await get_player(final_session, guild_id, entity_id)
                    if player and player.current_status == PlayerStatus.PROCESSING_GUILD_TURN:
                        player.current_status = PlayerStatus.EXPLORING
                        final_session.add(player)
                        logger.info(f"[ACTION_PROCESSOR] Player {player.id} status reset to EXPLORING.")
                elif entity_type == "party":
                    party = await get_party(final_session, guild_id, entity_id)
                    if party and party.turn_status == PartyTurnStatus.PROCESSING_GUILD_TURN:
                        party.turn_status = PartyTurnStatus.IDLE
                        final_session.add(party)
                        logger.info(f"[ACTION_PROCESSOR] Party {party.id} status reset to IDLE.")
                        for p_id in (party.player_ids_json or []):
                            member = await get_player(final_session, guild_id, p_id)
                            if member and member.current_status == PlayerStatus.PROCESSING_GUILD_TURN:
                                member.current_status = PlayerStatus.EXPLORING
                                final_session.add(member)
                                logger.info(f"[ACTION_PROCESSOR] Party Member {member.id} status reset to EXPLORING.")
            await log_event(final_session, guild_id=guild_id, event_type="GUILD_TURN_PROCESSED",
                            details_json={"processed_entities": entities_and_types_to_process, "results_summary_count": processed_actions_results_count})
    logger.info(f"[ACTION_PROCESSOR] Guild {guild_id}: Entity statuses updated and GUILD_TURN_PROCESSED event logged.")


async def process_actions_for_guild(guild_id: int, entities_and_types_to_process: list[dict]):
    """
    Main asynchronous worker for processing a guild's turn.
    Orchestrates loading, execution, and finalization of player actions.
    entities_and_types_to_process: list of dicts, e.g. [{'id': 1, 'type': 'player', 'discord_id': 123}, {'id': 2, 'type': 'party', 'name': 'The Group'}]
    """
    session_maker = get_db_session
    all_player_actions_for_turn: list[tuple[int, ParsedAction]] = []
    processed_actions_results: list[dict] = []

    # 1. Load and clear all player actions for the turn in a single transaction
    try:
        async with session_maker() as session:
            all_player_actions_for_turn = await _load_and_clear_all_actions(session, guild_id, entities_and_types_to_process)
            await session.commit() # Commit the clearing of collected_actions_json
        logger.info(f"[ACTION_PROCESSOR] Guild {guild_id}: Loaded and cleared {len(all_player_actions_for_turn)} player actions.")
    except Exception as e:
        logger.error(f"[ACTION_PROCESSOR] Guild {guild_id}: Critical error during action loading/clearing phase: {e}", exc_info=True)
        # Optionally, attempt to log this critical failure to the database if possible
        try:
            async with session_maker() as error_log_session:
                await log_event(error_log_session, guild_id=guild_id, event_type="ACTION_LOAD_ERROR",
                                details_json={"error": str(e), "phase": "load_and_clear_all_actions"})
                await error_log_session.commit()
        except Exception as log_e_critical:
            logger.error(f"[ACTION_PROCESSOR] Guild {guild_id}: Failed to log critical ACTION_LOAD_ERROR: {log_e_critical}", exc_info=True)
        return # Stop processing if actions can't be loaded

    # 2. Conflict Analysis (Conceptual MVP)
    # Placeholder for future conflict resolution logic
    # conflict_rule = await get_rule(session_maker, guild_id, "party_conflict_policy", "leader_decides")
    # if conflict_rule == "manual_moderation_required_for_movement": ...
    # For now, all loaded actions are assumed to be executable.

    # 3. Execute player actions, each in its own transaction
    if all_player_actions_for_turn:
        processed_actions_results = await _execute_player_actions(session_maker, guild_id, all_player_actions_for_turn)
        logger.info(f"[ACTION_PROCESSOR] Guild {guild_id}: Execution phase completed for {len(all_player_actions_for_turn)} actions. Results count: {len(processed_actions_results)}.")
    else:
        logger.info(f"[ACTION_PROCESSOR] Guild {guild_id}: No player actions to execute for this turn.")

    # 4. Finalize turn processing (update statuses, log turn completion)
    try:
        await _finalize_turn_processing(session_maker, guild_id, entities_and_types_to_process, len(processed_actions_results))
    except Exception as e:
        logger.error(f"[ACTION_PROCESSOR] Guild {guild_id}: Error during turn finalization phase: {e}", exc_info=True)
        # Optionally, log this error to the database
        try:
            async with session_maker() as error_log_session:
                await log_event(error_log_session, guild_id=guild_id, event_type="TURN_FINALIZE_ERROR",
                                details_json={"error": str(e), "phase": "finalize_turn_processing"})
                await error_log_session.commit()
        except Exception as log_e_final:
            logger.error(f"[ACTION_PROCESSOR] Guild {guild_id}: Failed to log TURN_FINALIZE_ERROR: {log_e_final}", exc_info=True)


    logger.info(f"[ACTION_PROCESSOR] Guild {guild_id}: Turn processing complete. Processed {len(processed_actions_results)} individual action results.")
    # TODO: Send feedback reports to players/master based on processed_actions_results

logger.info("Action Processor module loaded.")

# This module is intended to be run as a background task, e.g., via asyncio.create_task()
# from turn_controller.py.
# Example of how it might be called from turn_controller:
# from src.core.action_processor import process_actions_for_guild
# ...
# entities_for_action_module = [{"id": player.id, "type": "player", "discord_id": player.discord_id}, ...]
# asyncio.create_task(process_actions_for_guild(guild_id, entities_for_action_module))
