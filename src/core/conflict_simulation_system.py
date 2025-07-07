import logging
from typing import List, Dict, Any, Optional, Tuple, Union # Added Union

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Player, GeneratedNpc, PendingConflict, GuildConfig
from src.models.enums import RelationshipEntityType, ConflictStatus, TurnProcessingStatus # Updated import
from src.models.actions import ParsedAction # Assuming ParsedAction is a Pydantic model
from src.core.crud import player_crud, npc_crud, pending_conflict_crud
from src.core import action_processor # To access helper functions or adapt logic

logger = logging.getLogger(__name__)

# Placeholder for a Pydantic model if ParsedAction is not already one
# from pydantic import BaseModel
# class ParsedAction(BaseModel):
#     intent_name: str
#     entities: Dict[str, Any] = {}
#     confidence: float = 1.0
#     text: str = ""

class SimulatedActionActor:
    """
    A wrapper to simulate an actor (Player or NPC) with a single action
    for conflict detection purposes.
    """
    def __init__(self, guild_id: int, parsed_action: ParsedAction, player: Optional[Player] = None, npc: Optional[GeneratedNpc] = None):
        self.id = player.id if player else npc.id # type: ignore
        self.entity_type = RelationshipEntityType.PLAYER if player else RelationshipEntityType.GENERATED_NPC
        self.guild_id = guild_id
        self.collected_actions_json = [parsed_action.model_dump(mode="json")] # Store as if it came from DB
        self.player = player
        self.npc = npc
        self.name = player.character_name if player else (npc.name_i18n.get("en", "Unknown NPC") if npc else "Unknown")


async def simulate_conflict_detection(
    session: AsyncSession,
    guild_id: int,
    actions_input_data: List[Dict[str, Any]]
) -> List[PendingConflict]:
    """
    Simulates conflict detection for a given list of actions without persisting data.

    Args:
        session: The SQLAlchemy async session.
        guild_id: The ID of the guild.
        actions_input_data: A list of dictionaries, each describing an action:
            {
                "actor_id": int,
                "actor_type": "player" | "generated_npc",
                "parsed_action": { // ParsedAction structure
                    "intent_name": "attack",
                    "entities": { ... },
                    "confidence": 1.0,
                    "text": "Attack goblin!"
                }
            }

    Returns:
        A list of Pydantic PendingConflict models if conflicts are detected,
        otherwise an empty list. These are NOT saved to the database.
    """
    simulated_actors: List[SimulatedActionActor] = []
    for action_data in actions_input_data:
        actor_id = action_data.get("actor_id")
        actor_type_str = action_data.get("actor_type")
        parsed_action_dict = action_data.get("parsed_action")

        if not all([actor_id, actor_type_str, parsed_action_dict]):
            logger.warning(f"Skipping invalid action data in simulation: {action_data}")
            continue

        try:
            parsed_action = ParsedAction(**parsed_action_dict)
        except Exception as e:
            logger.warning(f"Skipping action data due to ParsedAction validation error: {e} - {parsed_action_dict}")
            continue

        actor_player: Optional[Player] = None
        actor_npc: Optional[GeneratedNpc] = None

        if actor_type_str.lower() == RelationshipEntityType.PLAYER.value:
            actor_player = await player_crud.get(session, actor_id)
            if not actor_player or actor_player.guild_id != guild_id:
                logger.warning(f"Player {actor_id} not found or not in guild {guild_id} for simulation.")
                continue
        elif actor_type_str.lower() == RelationshipEntityType.GENERATED_NPC.value:
            actor_npc = await npc_crud.get(session, actor_id)
            if not actor_npc or actor_npc.guild_id != guild_id:
                logger.warning(f"NPC {actor_id} not found or not in guild {guild_id} for simulation.")
                continue
        else:
            logger.warning(f"Unsupported actor_type '{actor_type_str}' for simulation.")
            continue

        sim_actor = SimulatedActionActor(guild_id=guild_id, parsed_action=parsed_action, player=actor_player, npc=actor_npc)
        simulated_actors.append(sim_actor)

    if not simulated_actors:
        return []

    # Adapt logic from action_processor._get_relevant_entities_with_actions
    # This part is simplified as we construct simulated_actors directly with one action each.
    # The original function filters entities that *have* actions. Here, all simulated_actors do.

    # Adapt logic from action_processor._get_conflicting_actions_groups
    # The original function takes a list of actual Player/NPC DB models.
    # We need to make it work with our SimulatedActionActor or extract its core logic.

    # Let's try to call the helper directly if possible, or replicate its logic.
    # _get_conflicting_actions_groups expects entities with 'collected_actions_json' and 'id'
    # and 'guild_id'. Our SimulatedActionActor fits this.

    # However, _get_conflicting_actions_groups also takes a 'turn_status' which is a GuildConfig field.
    # We might need to fetch it or mock it if the logic depends heavily on it for conflict types.
    # For now, let's assume default turn processing status or that it's not critical for pure conflict *detection*.

    # The function action_processor._get_conflicting_actions_groups is complex and has side effects
    # (like clearing actions). We need a "pure" version or careful adaptation.

    # Simplified approach:
    # 1. Extract all ParsedActions from simulated_actors.
    # 2. Identify target conflicts directly (e.g. multiple actors targeting the same entity).
    # This is a simplification of the original logic. A more robust solution would involve
    # deeper refactoring of action_processor's conflict detection.

    # For now, let's placeholder the actual conflict detection logic.
    # This will be the most complex part to adapt for "dry run".

    # --- Placeholder for conflict detection logic ---
    # Example: If two actions target the same NPC ID, consider it a conflict for simulation.
    simulated_pending_conflicts: List[PendingConflict] = []

    # This is a very basic example, actual conflict detection is more nuanced.
    # We'd need to properly use/adapt action_processor's logic.
    # For instance, action_processor._determine_conflict_type_and_targets is key.

# --- Helper function to determine the primary target signature of an action ---
def _extract_primary_target_signature(action: ParsedAction) -> Optional[str]:
    """
    Extracts a standardized signature for the primary target of an action.
    This helps group actions that affect the same logical entity.

    Returns:
        A string like "npc:123", "item_static:some_id", "location_feature:feature_key",
        or None if no clear, shared target is identified.
    """
    intent = action.intent
    entities = action.entities

    if not entities:
        return None # No entities, no specific target signature

    # Prioritized entity types for common intents
    if intent in ["attack", "talk", "trade_view_inventory", "trade_buy_item", "trade_sell_item"]:
        for entity in entities:
            if entity.type == "target_npc_id":
                return f"npc:{entity.value}"
            if entity.type == "target_player_id":
                return f"player:{entity.value}"
            # For trade, the NPC is the primary "target" of the interaction session
            if entity.type == "target_npc_name": # Less precise, but could be used if ID not available
                 return f"npc_name:{entity.value.lower()}"


    if intent in ["examine", "interact", "use", "take", "drop"]: # "use" can be on self or target
        # Check for specific target types first
        for entity in entities:
            if entity.type == "target_item_id": # DB ID of an Item instance
                return f"item_instance:{entity.value}"
            if entity.type == "item_static_id": # Static ID of an Item template
                return f"item_static:{entity.value}"
            if entity.type == "target_object_static_id": # E.g. a door, lever with a static_id
                return f"location_object_static:{entity.value}"
            if entity.type == "target_object_name": # E.g. "the old chest"
                return f"location_object_name:{entity.value.lower()}"
            if entity.type == "target_npc_id": # e.g., "use bandage on NPC 123"
                return f"npc:{entity.value}"
            if entity.type == "target_player_id": # e.g., "use potion on Player 456"
                return f"player:{entity.value}"

        # If no specific target_..._id, maybe a generic name?
        # This part is more heuristic.
        if len(entities) == 1: # If only one entity, it's likely the target
            # Avoid generic directions or common words if not specifically typed as a target
            if entities[0].type not in ["direction", "manner", "general_concept"] and \
               not entities[0].value.lower() in ["it", "them", "self", "myself"]:
                return f"named_entity:{entities[0].type}:{entities[0].value.lower()}"

    if intent == "move":
        for entity in entities:
            if entity.type == "location_static_id":
                return f"location_static:{entity.value}"
            if entity.type == "location_name":
                return f"location_name:{entity.value.lower()}"
            if entity.type == "direction": # Could be a conflict if multiple try to "go north" into a small passage
                return f"direction:{entity.value.lower()}"

    # Add more intent/entity combinations as needed.
    # For example, for spellcasting:
    # if intent.startswith("cast_spell_"):
    #     spell_name = intent.split("cast_spell_")[1]
    #     target_signature = None
    #     for entity in entities: # Find target
    #         if entity.type == "target_npc_id": target_signature = f"npc:{entity.value}"; break
    #         if entity.type == "target_player_id": target_signature = f"player:{entity.value}"; break
    #     if target_signature:
    #         return f"spell_on_target:{spell_name}:{target_signature}"
    #     else: # Self-cast or area effect might not have a "shared" target signature this way
    #         return f"spell_general:{spell_name}"


    return None # No clear single target signature for conflict detection based on current rules


    # Let's assume we have a way to get groups of conflicting actions:
    # conflicting_action_groups = await action_processor._get_conflicting_actions_groups(
    #     session, cast(List[Union[Player, GeneratedNpc]], simulated_actors), guild_config.turn_status  # This cast is unsafe
    # )
    # This direct call is problematic due to type differences and side effects.

    # Instead, we'll need to replicate the core logic of identifying conflicting targets.
    # The main function in action_processor to look at is:
    # async def _process_player_actions_for_conflict_detection(
    #        session: AsyncSession, guild_id: int, guild_config: GuildConfig
    #    ) -> List[PendingConflict]:

    # It calls _get_relevant_entities_with_actions, then _get_conflicting_actions_groups,
    # then _create_pending_conflicts_for_group.

    # We need to simulate _create_pending_conflicts_for_group without DB write.
    # Let's assume we have a hypothetical `_find_conflicting_action_sets` that returns
    # data needed to create PendingConflict models.

    # This part requires significant work to adapt action_processor.py logic for dry-run.
    # For the purpose of this step, we will return an empty list,
    # and the actual implementation of conflict detection will be iterative.

    logger.info(f"Simulating conflict detection for {len(simulated_actors)} actions in guild {guild_id}.")

    simulated_pending_conflicts: List[PendingConflict] = []

    if len(simulated_actors) < 2:
        return [] # Not enough actions to have a conflict among them

    # Helper to extract primary target from a ParsedAction
    def get_primary_target(action: ParsedAction) -> Optional[Tuple[str, str]]:
        """
        Extracts a simplified primary target (type, value) from action entities.
        Example: ('target_npc_id', '123'), ('target_object_static_id', 'door_01')
        This is a simplification; real target resolution can be more complex.
        """
        if not action.entities:
            return None

        # Prioritize specific target types
        for entity in action.entities:
            if entity.type in ["target_npc_id", "target_player_id", "target_item_id", "target_object_static_id", "target_location_static_id"]:
                return (entity.type, entity.value)

        # Fallback for more generic target names if intent implies a target
        if action.intent in ["attack", "interact", "examine", "use"]: # Add other relevant intents
            # Could look for entities of type "npc_name", "item_name" etc.
            # For simulation, let's assume specific IDs are preferred for clarity.
            # This part can be expanded based on how NLU typically forms entities.
            pass
        return None

    # Iterate through all unique pairs of actions to check for conflicts
    # A more advanced system might group by target first, then check intents.
    for i in range(len(simulated_actors)):
        for j in range(i + 1, len(simulated_actors)):
            actor1_sim = simulated_actors[i]
            actor2_sim = simulated_actors[j]

            # We expect collected_actions_json to have one action for simulation
            if not actor1_sim.collected_actions_json or not actor2_sim.collected_actions_json:
                continue

            try:
                action1_dict = actor1_sim.collected_actions_json[0]
                action2_dict = actor2_sim.collected_actions_json[0]
                # Re-parse to ParsedAction to ensure we have the model methods/fields
                # The stored version in SimulatedActionActor is already a dict from model_dump
                parsed_action1 = ParsedAction(**action1_dict)
                parsed_action2 = ParsedAction(**action2_dict)
            except Exception as e:
                logger.error(f"Error re-parsing action for simulation: {e}")
                continue

            # Simple conflict: same intent and same primary target
            if parsed_action1.intent == parsed_action2.intent and parsed_action1.intent in ["attack", "interact"]: # Example intents
                target1 = get_primary_target(parsed_action1)
                target2 = get_primary_target(parsed_action2)

                if target1 is not None and target1 == target2:
                    logger.info(f"Potential conflict detected between actor {actor1_sim.id} ({parsed_action1.intent} on {target1}) and actor {actor2_sim.id} ({parsed_action2.intent} on {target2})")

                    involved_entities_json = [
                        {
                            "entity_id": actor1_sim.id,
                            "entity_type": actor1_sim.entity_type.value,
                            "action_intent": parsed_action1.intent,
                            "action_text": parsed_action1.raw_text,
                            "action_entities": [e.model_dump() for e in parsed_action1.entities]
                        },
                        {
                            "entity_id": actor2_sim.id,
                            "entity_type": actor2_sim.entity_type.value,
                            "action_intent": parsed_action2.intent,
                            "action_text": parsed_action2.raw_text,
                            "action_entities": [e.model_dump() for e in parsed_action2.entities]
                        }
                    ]

                    # Check if this specific conflict (same actors, same intent, same target) is already found
                    # This is a very basic way to avoid duplicate conflicts from pair iteration if we extend to groups.
                    # For pure pairs, this might not be strictly necessary unless targets can be multi-valued.
    # This old conflict detection logic based on pairs is being replaced.

    # New logic: Group actions by target signature
    actions_by_target: Dict[str, List[Tuple[SimulatedActionActor, ParsedAction]]] = {}

    for sim_actor in simulated_actors:
        if not sim_actor.collected_actions_json:
            continue
        try:
            action_dict = sim_actor.collected_actions_json[0]
            parsed_action = ParsedAction(**action_dict)
        except Exception as e:
            logger.error(f"Error re-parsing action for target grouping: {e} for actor {sim_actor.id}")
            continue

        target_sig = _extract_primary_target_signature(parsed_action)
        if target_sig:
            if target_sig not in actions_by_target:
                actions_by_target[target_sig] = []
            actions_by_target[target_sig].append((sim_actor, parsed_action))

    # Define conflicting intent pairs/sets
    # (intent1, intent2) -> "conflict_type_name"
    # Using frozenset for order-agnostic pairs.
    # More advanced: define categories of intents (e.g., "exclusive_manipulation", "observation")
    EXCLUSIVE_INTENTS = {"attack", "interact", "use", "take"} # Add more as needed

    for target_sig, targeted_actions in actions_by_target.items():
        if len(targeted_actions) < 2:
            continue # No conflict if only one action targets this signature

        # Check for conflicts within this group of actions on the same target
        # Simple rule: if multiple EXCLUSIVE_INTENTS target the same signature, it's a conflict.
        exclusive_actions_in_group = [
            (actor, p_action) for actor, p_action in targeted_actions if p_action.intent in EXCLUSIVE_INTENTS
        ]

        if len(exclusive_actions_in_group) > 1:
            logger.info(f"Potential conflict detected for target '{target_sig}' with {len(exclusive_actions_in_group)} exclusive actions.")

            involved_entities_json = []
            for actor_sim, p_action in exclusive_actions_in_group:
                involved_entities_json.append({
                    "entity_id": actor_sim.id,
                    "entity_type": actor_sim.entity_type.value,
                    "action_intent": p_action.intent,
                    "action_text": p_action.raw_text,
                    "action_entities": [e.model_dump() for e in p_action.entities]
                })

            # Create one conflict for this group
            # Determine a generic conflict_type based on the target and involved intents
            conflict_type_detail = "_".join(sorted(list(set(pa.intent for _, pa in exclusive_actions_in_group))))

            sim_conflict = PendingConflict(
                guild_id=guild_id,
                conflict_type=f"simulated_target_{conflict_type_detail}_on_{target_sig.split(':')[0]}",
                status=ConflictStatus.SIMULATED_INTERNAL_CONFLICT,
                involved_entities_json=involved_entities_json,
                resolution_details_json={},
                turn_number=0,
            )
            simulated_pending_conflicts.append(sim_conflict)

    if simulated_pending_conflicts:
        logger.info(f"Detected {len(simulated_pending_conflicts)} simulated conflict(s) in guild {guild_id} using target grouping.")

    return simulated_pending_conflicts


async def setup_conflict_simulation_system():
    # This function could be used if there's any setup needed for the system,
    # e.g., loading some global rules or configurations, though unlikely for this module.
    logger.info("Conflict Simulation System initialized (if any setup was needed).")
