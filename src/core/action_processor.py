import asyncio
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Any, Coroutine, Callable

from src.core.database import get_db_session, transactional
from src.models import Player, Party, PendingConflict
from src.models.enums import PlayerStatus, PartyTurnStatus, ConflictStatus
from src.models.actions import ParsedAction
from src.core.rules import get_rule # For conflict_resolution_rules
from src.core.player_utils import get_player_by_id # Generic get by PK
from src.core.party_utils import get_party_by_id # Generic get by PK

# Placeholder imports for actual game modules - these will be called by dispatch
# from src.core.movement_logic import handle_move_action_internal # Needs to be created/adapted
# from src.core.some_other_module import handle_look_action_internal
# from src.core.combat_module import handle_combat_action_internal
# from src.core.inventory_module import handle_inventory_action_internal
# from src.core.quest_module import handle_quest_event_internal
# from src.core.interaction_module import handle_intra_location_interaction_internal
from src.core.game_events import log_event # Placeholder
from src.bot.utils import notify_master # Utility to notify master

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
        # Assuming movement_logic.handle_move_action is adapted or a new internal version is created
        # that takes a session and player_id (PK) instead of discord_id.
        # For now, this is a conceptual adaptation.
        # from src.core.movement_logic import execute_move_for_player
        # target_location_static_id = action.get_entity_value("target_location_static_id") # Example
        # if target_location_static_id:
        #     result = await execute_move_for_player(session, guild_id, player_id, target_location_static_id)
        #     return result
        # else:
        #     return {"status": "error", "message": "Target location not specified for move action."}
        await log_event(session=session, guild_id=guild_id, event_type="ACTION_MOVE_EXECUTED",
                        details_json={"player_id": player_id, "action": action.model_dump(mode='json')}, player_id=player_id)
        return {"status": "success", "message": "Move action (placeholder) handled."} # Placeholder
    except Exception as e:
        logger.error(f"Error in _handle_move_action_wrapper: {e}", exc_info=True)
        return {"status": "error", "message": f"Failed to execute move action: {e}"}


# Action dispatch table
ACTION_DISPATCHER: dict[str, Callable[[AsyncSession, int, int, ParsedAction], Coroutine[Any, Any, dict]]] = {
    "move": _handle_move_action_wrapper,
    "look": _handle_placeholder_action,
    "attack": _handle_placeholder_action, # Placeholder for combat
    "take": _handle_placeholder_action,  # Placeholder for inventory
    "use": _handle_placeholder_action,   # Placeholder for inventory/item use
    "talk": _handle_placeholder_action, # Placeholder for dialogue
    "examine": _handle_placeholder_action, # Placeholder for detailed look/interaction
    # Add more intents and their handlers here
}


@transactional # Wraps the initial loading and clearing of actions in a transaction
async def _load_and_clear_actions(session: AsyncSession, guild_id: int, entity_id: int, entity_type: str) -> list[ParsedAction]:
    """Loads actions for a single entity and clears them from the DB."""
    actions_to_process = []
    if entity_type == "player":
        player = await get_player_by_id(session, guild_id, entity_id) # Use get_player_by_id (PK)
        if player and player.collected_actions_json:
            try:
                actions_data = json.loads(player.collected_actions_json) if isinstance(player.collected_actions_json, str) else player.collected_actions_json
                for action_data in actions_data:
                    actions_to_process.append(ParsedAction(**action_data))
                player.collected_actions_json = [] # Clear actions
                session.add(player)
                logger.info(f"[ACTION_PROCESSOR] Loaded {len(actions_to_process)} actions for player {player.id} and cleared from DB.")
            except json.JSONDecodeError:
                logger.error(f"[ACTION_PROCESSOR] Failed to decode actions for player {player.id}")
            except Exception as e: # Pydantic validation error etc.
                logger.error(f"[ACTION_PROCESSOR] Error parsing actions for player {player.id}: {e}", exc_info=True)
                player.collected_actions_json = [] # Clear invalid actions
                session.add(player)


    elif entity_type == "party":
        party = await get_party_by_id(session, guild_id, entity_id) # Use get_party_by_id (PK)
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


async def process_actions_for_guild(guild_id: int, entities_and_types_to_process: list[dict]):
    """
    Main asynchronous worker for processing a guild's turn.
    entities_and_types_to_process: list of dicts, e.g. [{'id': 1, 'type': 'player', 'discord_id': 123}, {'id': 2, 'type': 'party', 'name': 'The Group'}]
    """
    session_maker = get_db_session
    all_player_actions_for_turn: list[tuple[int, ParsedAction]] = [] # Store as (player_id, action)

    async with session_maker() as session:
        # 1. Load actions for all relevant players and clear them from DB
        # This initial load is within one transaction managed by @transactional on _load_and_clear_actions
        player_ids_in_processing_parties = set()

        for entity_info in entities_and_types_to_process:
            entity_id = entity_info["id"]
            entity_type = entity_info["type"]

            if entity_type == "player":
                player_actions = await _load_and_clear_actions(session, guild_id, entity_id, "player")
                for action in player_actions:
                    all_player_actions_for_turn.append((entity_id, action))
            elif entity_type == "party":
                party = await get_party_by_id(session, guild_id, entity_id)
                if party and party.player_ids_json:
                    for player_pk_in_party in party.player_ids_json:
                        player_ids_in_processing_parties.add(player_pk_in_party)
                        # Check if this player was also passed as individual entity_info
                        # to avoid double loading if player is passed AND their party is passed.
                        is_player_individually_processed = any(
                            p_info['type'] == 'player' and p_info['id'] == player_pk_in_party
                            for p_info in entities_and_types_to_process
                        )
                        if not is_player_individually_processed:
                            player_actions = await _load_and_clear_actions(session, guild_id, player_pk_in_party, "player")
                            for action in player_actions:
                                all_player_actions_for_turn.append((player_pk_in_party, action))
        await session.commit() # Commit the clearing of collected_actions_json

    logger.info(f"[ACTION_PROCESSOR] Guild {guild_id}: Processing {len(all_player_actions_for_turn)} actions.")

    # 2. Conflict Analysis (Conceptual MVP for party actions)
    # For now, we'll assume actions are processed individually without complex conflict resolution.
    # A real implementation would group actions by party, check for conflicts, etc.
    # If conflict -> create PendingConflict, notify master, skip action.
    # Example:
    # conflict_rule = await get_rule(session_maker, guild_id, "party_conflict_policy", "leader_decides")
    # if conflict_rule == "manual_moderation_required_for_movement": ...

    processed_actions_results = []

    # 3. Action Execution Phase - Each action in its own transaction
    for player_id, action in all_player_actions_for_turn:
        async with session_maker() as action_session: # New session for each action's transaction
            try:
                async with action_session.begin(): # Start transaction for this action
                    handler = ACTION_DISPATCHER.get(action.intent, _handle_placeholder_action)
                    logger.info(f"[ACTION_PROCESSOR] Guild {guild_id}, Player {player_id}: Dispatching action '{action.intent}' to {handler.__name__}")

                    action_result = await handler(action_session, guild_id, player_id, action)
                    processed_actions_results.append({"player_id": player_id, "action": action.model_dump(mode='json'), "result": action_result})

                    # The transaction is committed here if handler is successful
                logger.info(f"[ACTION_PROCESSOR] Guild {guild_id}, Player {player_id}: Action '{action.intent}' committed successfully.")
            except Exception as e:
                # Transaction automatically rolled back by async with session.begin() context manager
                logger.error(f"[ACTION_PROCESSOR] Guild {guild_id}, Player {player_id}: Error processing action '{action.intent}': {e}", exc_info=True)
                processed_actions_results.append({
                    "player_id": player_id,
                    "action": action.model_dump(mode='json'),
                    "result": {"status": "error", "message": str(e)}
                })
                await log_event(action_session, guild_id=guild_id, event_type="ACTION_PROCESSING_ERROR",
                                details_json={"player_id": player_id, "action": action.model_dump(mode='json'), "error": str(e)}, player_id=player_id)
                # No explicit rollback needed due to context manager, but commit is skipped.

    # 4. Post-Processing (Update statuses, log turn completion, send feedback)
    async with session_maker() as final_session:
        async with final_session.begin():
            for entity_info in entities_and_types_to_process:
                entity_id = entity_info["id"]
                entity_type = entity_info["type"]
                if entity_type == "player":
                    player = await get_player_by_id(final_session, guild_id, entity_id)
                    if player and player.status == PlayerStatus.PROCESSING_GUILD_TURN:
                        player.status = PlayerStatus.EXPLORING # Or PlayerStatus.AWAITING_INPUT
                        final_session.add(player)
                        logger.info(f"[ACTION_PROCESSOR] Player {player.id} status reset to EXPLORING.")
                elif entity_type == "party":
                    party = await get_party_by_id(final_session, guild_id, entity_id)
                    if party and party.turn_status == PartyTurnStatus.PROCESSING_GUILD_TURN:
                        party.turn_status = PartyTurnStatus.IDLE # Or AWAITING_PARTY_ACTION
                        final_session.add(party)
                        logger.info(f"[ACTION_PROCESSOR] Party {party.id} status reset to IDLE.")
                        # Reset party members too if they were part of this party's processing
                        for p_id in party.player_ids_json:
                             member = await get_player_by_id(final_session, guild_id, p_id)
                             if member and member.status == PlayerStatus.PROCESSING_GUILD_TURN:
                                 member.status = PlayerStatus.EXPLORING
                                 final_session.add(member)
                                 logger.info(f"[ACTION_PROCESSOR] Party Member {member.id} status reset to EXPLORING.")

            await log_event(final_session, guild_id=guild_id, event_type="GUILD_TURN_PROCESSED",
                            details_json={"processed_entities": entities_and_types_to_process, "results_summary_count": len(processed_actions_results)})
        # Commit status updates and final log event

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
