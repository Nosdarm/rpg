import logging
from typing import List, Dict, Any, Optional, Tuple, Union # Added Union

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Player, GeneratedNpc, PendingConflict, GuildConfig
from src.models.enums import RelationshipEntityType, ConflictStatus # Updated import
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
        self.name = player.name if player else (npc.name_i18n.get("en", "Unknown NPC") if npc else "Unknown")


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
    try:
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
        A string like "npc:123", "item_static:some_id", "location_object_static:feature_key",
        "use:item_static:potion@target:player:123", "use_on_self:item_static:potion",
        or None if no clear, shared target is identified.
    """
    intent = action.intent
    entities = action.entities

    if not entities:
        return None  # No entities, no specific target signature

    # Helper to find a specific entity type
    def find_entity_value(etype: str) -> Optional[str]:
        for entity in entities:
            if entity.type == etype:
                return entity.value
        return None

    # 1. Combat and Direct NPC/Player Targeting Intents
    if intent in ["attack", "talk", "trade_view_inventory", "trade_buy_item", "trade_sell_item"]:
        target_npc_id = find_entity_value("target_npc_id")
        if target_npc_id: return f"npc:{target_npc_id}"
        target_player_id = find_entity_value("target_player_id")
        if target_player_id: return f"player:{target_player_id}"
        target_npc_name = find_entity_value("target_npc_name")
        if target_npc_name: return f"npc_name:{target_npc_name.lower()}"
        # If other specific target types for these intents, add here

    # 2. Item Manipulation Intents (take, drop, examine item)
    if intent in ["take", "drop"] or (intent == "examine" and any(e.type in ["target_item_id", "item_static_id", "item_name"] for e in entities)):
        target_item_id = find_entity_value("target_item_id")
        if target_item_id: return f"item_instance:{target_item_id}"
        item_static_id = find_entity_value("item_static_id")
        if item_static_id: return f"item_static:{item_static_id}"
        item_name = find_entity_value("item_name") # Less precise
        if item_name: return f"item_name:{item_name.lower()}"

    # 3. Interaction with World Objects (interact, examine object)
    if intent == "interact" or (intent == "examine" and any(e.type in ["target_object_static_id", "target_object_name"] for e in entities)):
        obj_static_id = find_entity_value("target_object_static_id")
        if obj_static_id: return f"obj_static:{obj_static_id}"
        obj_name = find_entity_value("target_object_name")
        if obj_name: return f"obj_name:{obj_name.lower()}"

    # 4. 'use' Intent (can be complex: use item, use item on target, use skill)
    if intent == "use":
        item_id_val = find_entity_value("target_item_id") or find_entity_value("item_static_id")
        item_name_val = find_entity_value("item_name")

        item_signature_part = None
        if item_id_val:
            item_signature_part = f"item_instance:{item_id_val}" if find_entity_value("target_item_id") else f"item_static:{item_id_val}"
        elif item_name_val:
            item_signature_part = f"item_name:{item_name_val.lower()}"

        if item_signature_part: # Primarily item-focused 'use'
            target_npc_id = find_entity_value("target_npc_id")
            if target_npc_id: return f"use:{item_signature_part}@target:npc:{target_npc_id}"
            target_player_id = find_entity_value("target_player_id")
            if target_player_id: return f"use:{item_signature_part}@target:player:{target_player_id}"
            # Could also target self implicitly or explicitly
            if any(e.type == "target_self" and e.value.lower() == "true" for e in entities) or not (target_npc_id or target_player_id):
                 return f"use_on_self:{item_signature_part}"

        # Could also be 'use skill X [on target Y]' - needs skill entity type from NLU
        skill_id_val = find_entity_value("skill_id") or find_entity_value("skill_name")
        if skill_id_val:
            skill_sig_part = f"skill:{skill_id_val.lower()}" # Assuming skill_name if ID not present
            target_npc_id = find_entity_value("target_npc_id")
            if target_npc_id: return f"use:{skill_sig_part}@target:npc:{target_npc_id}"
            target_player_id = find_entity_value("target_player_id")
            if target_player_id: return f"use:{skill_sig_part}@target:player:{target_player_id}"
            return f"use_on_self:{skill_sig_part}" # Default to self if no other target

    # 5. Movement Intent
    if intent == "move":
        loc_static_id = find_entity_value("location_static_id")
        if loc_static_id: return f"location_static:{loc_static_id}"
        loc_name = find_entity_value("location_name")
        if loc_name: return f"location_name:{loc_name.lower()}"
        direction = find_entity_value("direction")
        if direction: return f"direction:{direction.lower()}" # Can still conflict

    # Fallback for general 'examine' or other intents if a single specific target is mentioned
    if intent == "examine": # General examine, not item or object specific already handled
        target_npc_id = find_entity_value("target_npc_id")
        if target_npc_id: return f"npc:{target_npc_id}"
        target_player_id = find_entity_value("target_player_id")
        if target_player_id: return f"player:{target_player_id}"
        # Potentially other generic examinable things

    # Generic fallback if only one non-trivial entity is present (less reliable)
    if len(entities) == 1:
        entity = entities[0]
        if entity.type not in ["direction", "manner", "general_concept", "conjunction"] and \
           not entity.value.lower() in ["it", "them", "self", "myself", "here", "there"]:
            return f"generic_target:{entity.type}:{entity.value.lower()}"

    return None # No clear single target signature for conflict detection


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
    actions_by_target_sig: Dict[str, List[Tuple[SimulatedActionActor, ParsedAction]]] = {}

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
            if target_sig not in actions_by_target_sig:
                actions_by_target_sig[target_sig] = []
            actions_by_target_sig[target_sig].append((sim_actor, parsed_action))

    # --- Define Intent Categories and Conflict Rules ---
    # These could eventually be moved to RuleConfig for more flexibility.

    # Intents that generally require exclusive access to a common target if performed simultaneously.
    # 'use' is tricky: using a potion on self is not exclusive to someone else attacking a third party.
    # But using a specific lever (target) is exclusive if another person also tries to use that same lever.
    # 'take' is exclusive for a specific item.
    # 'attack' is exclusive on a specific target (multiple attackers are fine, but it's a "combat situation" conflict).
    # 'interact' can be exclusive for specific objects (e.g. single-use lever).

    # Category 1: Actions that inherently conflict if multiple actors target the SAME entity with these.
    # Example: two people trying to 'take' the exact same 'item_instance:101'.
    # Example: two people trying to 'attack' 'npc:55'.
    # Example: two people trying to 'interact' with 'obj_static:lever_main_gate'.
    CONFLICT_IF_SAME_TARGET_AND_INTENT_IN_CATEGORY = {
        "EXCLUSIVE_MANIPULATION": {"take", "interact_exclusive_object", "use_specific_consumable_item_instance"},
        "COMBAT_ENGAGEMENT": {"attack"}, # Multiple attacks on same target mean they are in combat together.
        # "trade_with_npc": {"trade_view_inventory", "trade_buy_item", "trade_sell_item"} # If NPC can only trade with one at a time
    }
    # This is a simplified rule. A more advanced rule would be:
    # IF target_sig is an item_instance AND (intent1 is 'take' AND intent2 is 'take') THEN conflict.
    # IF target_sig is an obj_static:X AND (RuleConfig says X is single_interaction) AND (intent1 is 'interact' AND intent2 is 'interact') THEN conflict.

    # Category 2: Pairs of different intents that conflict on the SAME target.
    # (frozenset({intent1, intent2}), target_category_pattern) -> conflict_type_name
    # Example: ('take', 'use') on an 'item_instance:*' or 'item_static:*'
    CONFLICTING_INTENT_PAIRS_ON_SAME_TARGET: Dict[frozenset[str], List[Tuple[str, str]]] = {
        frozenset({"take", "use"}): [("item_contention", "item_instance:"), ("item_contention", "item_static:"), ("item_contention", "item_name:")],
        frozenset({"take", "drop"}): [("item_state_race", "item_instance:"), ("item_state_race", "item_static:"), ("item_state_race", "item_name:")],
        # Add more, e.g., frozenset({"interact_open", "interact_close"}) on "obj_static:door_*"
    }


    for target_sig, actions_on_this_target in actions_by_target_sig.items():
        if len(actions_on_this_target) < 2:
            continue # Not enough actions on the same target signature to conflict

        # Rule 1: Multiple actors performing an "exclusive category" intent on the same target
        # This is a simplified version of the old EXCLUSIVE_INTENTS check, but more targeted.

        # Let's check for specific patterns first.
        # Example: Two 'attack' intents on the same target signature (e.g., "npc:123")
        attack_actions = [(actor, p_action) for actor, p_action in actions_on_this_target if p_action.intent == "attack"]
        if len(attack_actions) > 1:
            involved_entities_json = []
            for actor_sim, p_action in attack_actions:
                involved_entities_json.append({
                    "entity_id": actor_sim.id, "entity_type": actor_sim.entity_type.value,
                    "action_intent": p_action.intent, "action_text": p_action.raw_text,
                    "action_entities": [e.model_dump() for e in p_action.entities]
                })
            sim_conflict = PendingConflict(
                guild_id=guild_id,
                conflict_type=f"sim_multi_attack_on_{target_sig.replace(':', '_')}",
                status=ConflictStatus.SIMULATED_INTERNAL_CONFLICT,
                involved_entities_json=involved_entities_json,
                resolution_details_json={"target_signature": target_sig},
                turn_number=0, # Simulation context doesn't have a turn number
            )
            simulated_pending_conflicts.append(sim_conflict)
            logger.info(f"Conflict: Multiple attacks on '{target_sig}'. Actors: {[a.id for a, _ in attack_actions]}")
            continue # This group of actions is now part of a conflict


        # Example: Two 'take' intents on the same item signature (e.g., "item_instance:101")
        take_actions = [(actor, p_action) for actor, p_action in actions_on_this_target if p_action.intent == "take"]
        if len(take_actions) > 1 and target_sig.startswith(("item_instance:", "item_static:", "item_name:")) :
            involved_entities_json = []
            for actor_sim, p_action in take_actions:
                involved_entities_json.append({
                    "entity_id": actor_sim.id, "entity_type": actor_sim.entity_type.value,
                    "action_intent": p_action.intent, "action_text": p_action.raw_text,
                    "action_entities": [e.model_dump() for e in p_action.entities]
                })
            sim_conflict = PendingConflict(
                guild_id=guild_id,
                conflict_type=f"sim_item_take_contention_on_{target_sig.replace(':', '_')}",
                status=ConflictStatus.SIMULATED_INTERNAL_CONFLICT,
                involved_entities_json=involved_entities_json,
                resolution_details_json={"target_signature": target_sig},
                turn_number=0,
            )
            simulated_pending_conflicts.append(sim_conflict)
            logger.info(f"Conflict: Multiple takes for item '{target_sig}'. Actors: {[a.id for a, _ in take_actions]}")
            continue


        # Rule 2: Check for conflicting intent pairs on the same target
        # Iterate through all unique pairs of actions within actions_on_this_target
        for i in range(len(actions_on_this_target)):
            for j in range(i + 1, len(actions_on_this_target)):
                actor1_sim, action1 = actions_on_this_target[i]
                actor2_sim, action2 = actions_on_this_target[j]

                intent_pair = frozenset({action1.intent, action2.intent})
                if intent_pair in CONFLICTING_INTENT_PAIRS_ON_SAME_TARGET:
                    rules_for_pair = CONFLICTING_INTENT_PAIRS_ON_SAME_TARGET[intent_pair]
                    for conflict_name_tpl, target_category_pattern in rules_for_pair:
                        if target_sig.startswith(target_category_pattern):
                            # Found a conflict based on intent pair and target category
                            involved_entities_json = [
                                {"entity_id": actor1_sim.id, "entity_type": actor1_sim.entity_type.value, "action_intent": action1.intent, "action_text": action1.raw_text, "action_entities": [e.model_dump() for e in action1.entities]},
                                {"entity_id": actor2_sim.id, "entity_type": actor2_sim.entity_type.value, "action_intent": action2.intent, "action_text": action2.raw_text, "action_entities": [e.model_dump() for e in action2.entities]}
                            ]
                            sim_conflict = PendingConflict(
                                guild_id=guild_id,
                                conflict_type=f"sim_{conflict_name_tpl}_on_{target_sig.replace(':', '_')}",
                                status=ConflictStatus.SIMULATED_INTERNAL_CONFLICT,
                                involved_entities_json=involved_entities_json,
                                resolution_details_json={"target_signature": target_sig, "intents": list(intent_pair)},
                                turn_number=0,
                            )
                            # Avoid adding duplicate conflicts if multiple rules match or due to iteration order
                            # A more robust way: Collect all potential conflicts and then merge/deduplicate.
                            # For now, simple append.
                            is_duplicate = False
                            for existing_conflict in simulated_pending_conflicts:
                                existing_actors_involved = {(e["entity_id"], e["action_intent"]) for e in existing_conflict.involved_entities_json}
                                current_actors_involved = {(actor1_sim.id, action1.intent), (actor2_sim.id, action2.intent)}
                                if existing_actors_involved == current_actors_involved and existing_conflict.resolution_details_json.get("target_signature") == target_sig:
                                    is_duplicate = True
                                    break
                            if not is_duplicate:
                                simulated_pending_conflicts.append(sim_conflict)
                                logger.info(f"Conflict: Intents '{action1.intent}' and '{action2.intent}' on '{target_sig}'. Actors: {actor1_sim.id}, {actor2_sim.id}")
                            break # Found a rule for this pair and target, move to next pair
                    else: # Inner loop finished without break
                        continue
                    break # Outer loop: if a conflict for action1 with any other action in the group is found.
                         # This might prevent action1 from being part of another conflict.
                         # Consider if an action can be part of multiple conflicts.
                         # For simulation, one conflict per group of interacting actions might be enough.


    # TODO: Add logic for "use_on_self" vs "take" for the same item.
    # This requires checking actions that might not have the same _extract_primary_target_signature,
    # because "use_on_self:item_static:potion" and "item_static:potion" (from a "take" action) are different signatures.
    # We'd need to iterate all actions, identify "use_on_self" and "take" intents,
    # then compare their item components.

    # Example for use_on_self vs take:
    use_on_self_actions = []
    take_actions_map = {} # item_signature -> list of (actor, action)

    for sim_actor in simulated_actors: # First pass to collect relevant actions
        if not sim_actor.collected_actions_json: continue
        action_dict = sim_actor.collected_actions_json[0]
        parsed_action = ParsedAction(**action_dict)

        if parsed_action.intent == "use":
            # Check if it's a use_on_self type signature
            sig = _extract_primary_target_signature(parsed_action)
            if sig and sig.startswith("use_on_self:"):
                item_part_of_sig = sig.split("use_on_self:", 1)[1] # e.g., "item_static:potion"
                use_on_self_actions.append({"actor": sim_actor, "action": parsed_action, "item_signature": item_part_of_sig})
        elif parsed_action.intent == "take":
            item_sig_for_take = _extract_primary_target_signature(parsed_action) # Should be like "item_static:potion"
            if item_sig_for_take:
                if item_sig_for_take not in take_actions_map:
                    take_actions_map[item_sig_for_take] = []
                take_actions_map[item_sig_for_take].append((sim_actor, parsed_action))

    for u_action_info in use_on_self_actions:
        item_being_used_sig = u_action_info["item_signature"]
        if item_being_used_sig in take_actions_map:
            for t_actor_sim, t_action in take_actions_map[item_being_used_sig]:
                # Conflict: u_action_info["actor"] is using item_being_used_sig on self,
                # AND t_actor_sim is trying to take the same item_being_used_sig.
                involved_entities_json = [
                    {"entity_id": u_action_info["actor"].id, "entity_type": u_action_info["actor"].entity_type.value, "action_intent": u_action_info["action"].intent, "action_text": u_action_info["action"].raw_text, "action_entities": [e.model_dump() for e in u_action_info["action"].entities]},
                    {"entity_id": t_actor_sim.id, "entity_type": t_actor_sim.entity_type.value, "action_intent": t_action.intent, "action_text": t_action.raw_text, "action_entities": [e.model_dump() for e in t_action.entities]}
                ]
                sim_conflict = PendingConflict(
                    guild_id=guild_id,
                    conflict_type=f"sim_item_use_self_vs_take_{item_being_used_sig.replace(':', '_')}",
                    status=ConflictStatus.SIMULATED_INTERNAL_CONFLICT,
                    involved_entities_json=involved_entities_json,
                    resolution_details_json={"item_signature": item_being_used_sig},
                    turn_number=0,
                )
                # Add deduplication logic similar to above if necessary
                simulated_pending_conflicts.append(sim_conflict)
                logger.info(f"Conflict: Use on self vs Take for item '{item_being_used_sig}'. Actors: {u_action_info['actor'].id} (use), {t_actor_sim.id} (take)")


    if simulated_pending_conflicts:
        logger.info(f"Detected {len(simulated_pending_conflicts)} simulated conflict(s) in guild {guild_id} after all checks.")

    return simulated_pending_conflicts
    except Exception as e_outer:
        logger.error(f"!!! CRITICAL ERROR in simulate_conflict_detection: {e_outer}", exc_info=True)
        return [] # Return empty list on any unexpected error to prevent None


async def setup_conflict_simulation_system():
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
        A string like "npc:123", "item_static:some_id", "location_object_static:feature_key",
        "use:item_static:potion@target:player:123", "use_on_self:item_static:potion",
        or None if no clear, shared target is identified.
    """
    intent = action.intent
    entities = action.entities

    if not entities:
        return None  # No entities, no specific target signature

    # Helper to find a specific entity type
    def find_entity_value(etype: str) -> Optional[str]:
        for entity in entities:
            if entity.type == etype:
                return entity.value
        return None

    # 1. Combat and Direct NPC/Player Targeting Intents
    if intent in ["attack", "talk", "trade_view_inventory", "trade_buy_item", "trade_sell_item"]:
        target_npc_id = find_entity_value("target_npc_id")
        if target_npc_id: return f"npc:{target_npc_id}"
        target_player_id = find_entity_value("target_player_id")
        if target_player_id: return f"player:{target_player_id}"
        target_npc_name = find_entity_value("target_npc_name")
        if target_npc_name: return f"npc_name:{target_npc_name.lower()}"
        # If other specific target types for these intents, add here

    # 2. Item Manipulation Intents (take, drop, examine item)
    if intent in ["take", "drop"] or (intent == "examine" and any(e.type in ["target_item_id", "item_static_id", "item_name"] for e in entities)):
        target_item_id = find_entity_value("target_item_id")
        if target_item_id: return f"item_instance:{target_item_id}"
        item_static_id = find_entity_value("item_static_id")
        if item_static_id: return f"item_static:{item_static_id}"
        item_name = find_entity_value("item_name") # Less precise
        if item_name: return f"item_name:{item_name.lower()}"

    # 3. Interaction with World Objects (interact, examine object)
    if intent == "interact" or (intent == "examine" and any(e.type in ["target_object_static_id", "target_object_name"] for e in entities)):
        obj_static_id = find_entity_value("target_object_static_id")
        if obj_static_id: return f"obj_static:{obj_static_id}"
        obj_name = find_entity_value("target_object_name")
        if obj_name: return f"obj_name:{obj_name.lower()}"

    # 4. 'use' Intent (can be complex: use item, use item on target, use skill)
    if intent == "use":
        item_id_val = find_entity_value("target_item_id") or find_entity_value("item_static_id")
        item_name_val = find_entity_value("item_name")

        item_signature_part = None
        if item_id_val:
            item_signature_part = f"item_instance:{item_id_val}" if find_entity_value("target_item_id") else f"item_static:{item_id_val}"
        elif item_name_val:
            item_signature_part = f"item_name:{item_name_val.lower()}"

        if item_signature_part: # Primarily item-focused 'use'
            target_npc_id = find_entity_value("target_npc_id")
            if target_npc_id: return f"use:{item_signature_part}@target:npc:{target_npc_id}"
            target_player_id = find_entity_value("target_player_id")
            if target_player_id: return f"use:{item_signature_part}@target:player:{target_player_id}"
            # Could also target self implicitly or explicitly
            if any(e.type == "target_self" and e.value.lower() == "true" for e in entities) or not (target_npc_id or target_player_id):
                 return f"use_on_self:{item_signature_part}"

        # Could also be 'use skill X [on target Y]' - needs skill entity type from NLU
        skill_id_val = find_entity_value("skill_id") or find_entity_value("skill_name")
        if skill_id_val:
            skill_sig_part = f"skill:{skill_id_val.lower()}" # Assuming skill_name if ID not present
            target_npc_id = find_entity_value("target_npc_id")
            if target_npc_id: return f"use:{skill_sig_part}@target:npc:{target_npc_id}"
            target_player_id = find_entity_value("target_player_id")
            if target_player_id: return f"use:{skill_sig_part}@target:player:{target_player_id}"
            return f"use_on_self:{skill_sig_part}" # Default to self if no other target

    # 5. Movement Intent
    if intent == "move":
        loc_static_id = find_entity_value("location_static_id")
        if loc_static_id: return f"location_static:{loc_static_id}"
        loc_name = find_entity_value("location_name")
        if loc_name: return f"location_name:{loc_name.lower()}"
        direction = find_entity_value("direction")
        if direction: return f"direction:{direction.lower()}" # Can still conflict

    # Fallback for general 'examine' or other intents if a single specific target is mentioned
    if intent == "examine": # General examine, not item or object specific already handled
        target_npc_id = find_entity_value("target_npc_id")
        if target_npc_id: return f"npc:{target_npc_id}"
        target_player_id = find_entity_value("target_player_id")
        if target_player_id: return f"player:{target_player_id}"
        # Potentially other generic examinable things

    # Generic fallback if only one non-trivial entity is present (less reliable)
    if len(entities) == 1:
        entity = entities[0]
        if entity.type not in ["direction", "manner", "general_concept", "conjunction"] and \
           not entity.value.lower() in ["it", "them", "self", "myself", "here", "there"]:
            return f"generic_target:{entity.type}:{entity.value.lower()}"

    return None # No clear single target signature for conflict detection


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
    actions_by_target_sig: Dict[str, List[Tuple[SimulatedActionActor, ParsedAction]]] = {}

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
            if target_sig not in actions_by_target_sig:
                actions_by_target_sig[target_sig] = []
            actions_by_target_sig[target_sig].append((sim_actor, parsed_action))

    # --- Define Intent Categories and Conflict Rules ---
    # These could eventually be moved to RuleConfig for more flexibility.

    # Intents that generally require exclusive access to a common target if performed simultaneously.
    # 'use' is tricky: using a potion on self is not exclusive to someone else attacking a third party.
    # But using a specific lever (target) is exclusive if another person also tries to use that same lever.
    # 'take' is exclusive for a specific item.
    # 'attack' is exclusive on a specific target (multiple attackers are fine, but it's a "combat situation" conflict).
    # 'interact' can be exclusive for specific objects (e.g. single-use lever).

    # Category 1: Actions that inherently conflict if multiple actors target the SAME entity with these.
    # Example: two people trying to 'take' the exact same 'item_instance:101'.
    # Example: two people trying to 'attack' 'npc:55'.
    # Example: two people trying to 'interact' with 'obj_static:lever_main_gate'.
    CONFLICT_IF_SAME_TARGET_AND_INTENT_IN_CATEGORY = {
        "EXCLUSIVE_MANIPULATION": {"take", "interact_exclusive_object", "use_specific_consumable_item_instance"},
        "COMBAT_ENGAGEMENT": {"attack"}, # Multiple attacks on same target mean they are in combat together.
        # "trade_with_npc": {"trade_view_inventory", "trade_buy_item", "trade_sell_item"} # If NPC can only trade with one at a time
    }
    # This is a simplified rule. A more advanced rule would be:
    # IF target_sig is an item_instance AND (intent1 is 'take' AND intent2 is 'take') THEN conflict.
    # IF target_sig is an obj_static:X AND (RuleConfig says X is single_interaction) AND (intent1 is 'interact' AND intent2 is 'interact') THEN conflict.

    # Category 2: Pairs of different intents that conflict on the SAME target.
    # (frozenset({intent1, intent2}), target_category_pattern) -> conflict_type_name
    # Example: ('take', 'use') on an 'item_instance:*' or 'item_static:*'
    CONFLICTING_INTENT_PAIRS_ON_SAME_TARGET: Dict[frozenset[str], List[Tuple[str, str]]] = {
        frozenset({"take", "use"}): [("item_contention", "item_instance:"), ("item_contention", "item_static:"), ("item_contention", "item_name:")],
        frozenset({"take", "drop"}): [("item_state_race", "item_instance:"), ("item_state_race", "item_static:"), ("item_state_race", "item_name:")],
        # Add more, e.g., frozenset({"interact_open", "interact_close"}) on "obj_static:door_*"
    }


    for target_sig, actions_on_this_target in actions_by_target_sig.items():
        if len(actions_on_this_target) < 2:
            continue # Not enough actions on the same target signature to conflict

        # Rule 1: Multiple actors performing an "exclusive category" intent on the same target
        # This is a simplified version of the old EXCLUSIVE_INTENTS check, but more targeted.

        # Let's check for specific patterns first.
        # Example: Two 'attack' intents on the same target signature (e.g., "npc:123")
        attack_actions = [(actor, p_action) for actor, p_action in actions_on_this_target if p_action.intent == "attack"]
        if len(attack_actions) > 1:
            involved_entities_json = []
            for actor_sim, p_action in attack_actions:
                involved_entities_json.append({
                    "entity_id": actor_sim.id, "entity_type": actor_sim.entity_type.value,
                    "action_intent": p_action.intent, "action_text": p_action.raw_text,
                    "action_entities": [e.model_dump() for e in p_action.entities]
                })
            sim_conflict = PendingConflict(
                guild_id=guild_id,
                conflict_type=f"sim_multi_attack_on_{target_sig.replace(':', '_')}",
                status=ConflictStatus.SIMULATED_INTERNAL_CONFLICT,
                involved_entities_json=involved_entities_json,
                resolution_details_json={"target_signature": target_sig},
                turn_number=0, # Simulation context doesn't have a turn number
            )
            simulated_pending_conflicts.append(sim_conflict)
            logger.info(f"Conflict: Multiple attacks on '{target_sig}'. Actors: {[a.id for a, _ in attack_actions]}")
            continue # This group of actions is now part of a conflict


        # Example: Two 'take' intents on the same item signature (e.g., "item_instance:101")
        take_actions = [(actor, p_action) for actor, p_action in actions_on_this_target if p_action.intent == "take"]
        if len(take_actions) > 1 and target_sig.startswith(("item_instance:", "item_static:", "item_name:")) :
            involved_entities_json = []
            for actor_sim, p_action in take_actions:
                involved_entities_json.append({
                    "entity_id": actor_sim.id, "entity_type": actor_sim.entity_type.value,
                    "action_intent": p_action.intent, "action_text": p_action.raw_text,
                    "action_entities": [e.model_dump() for e in p_action.entities]
                })
            sim_conflict = PendingConflict(
                guild_id=guild_id,
                conflict_type=f"sim_item_take_contention_on_{target_sig.replace(':', '_')}",
                status=ConflictStatus.SIMULATED_INTERNAL_CONFLICT,
                involved_entities_json=involved_entities_json,
                resolution_details_json={"target_signature": target_sig},
                turn_number=0,
            )
            simulated_pending_conflicts.append(sim_conflict)
            logger.info(f"Conflict: Multiple takes for item '{target_sig}'. Actors: {[a.id for a, _ in take_actions]}")
            continue


        # Rule 2: Check for conflicting intent pairs on the same target
        # Iterate through all unique pairs of actions within actions_on_this_target
        for i in range(len(actions_on_this_target)):
            for j in range(i + 1, len(actions_on_this_target)):
                actor1_sim, action1 = actions_on_this_target[i]
                actor2_sim, action2 = actions_on_this_target[j]

                intent_pair = frozenset({action1.intent, action2.intent})
                if intent_pair in CONFLICTING_INTENT_PAIRS_ON_SAME_TARGET:
                    rules_for_pair = CONFLICTING_INTENT_PAIRS_ON_SAME_TARGET[intent_pair]
                    for conflict_name_tpl, target_category_pattern in rules_for_pair:
                        if target_sig.startswith(target_category_pattern):
                            # Found a conflict based on intent pair and target category
                            involved_entities_json = [
                                {"entity_id": actor1_sim.id, "entity_type": actor1_sim.entity_type.value, "action_intent": action1.intent, "action_text": action1.raw_text, "action_entities": [e.model_dump() for e in action1.entities]},
                                {"entity_id": actor2_sim.id, "entity_type": actor2_sim.entity_type.value, "action_intent": action2.intent, "action_text": action2.raw_text, "action_entities": [e.model_dump() for e in action2.entities]}
                            ]
                            sim_conflict = PendingConflict(
                                guild_id=guild_id,
                                conflict_type=f"sim_{conflict_name_tpl}_on_{target_sig.replace(':', '_')}",
                                status=ConflictStatus.SIMULATED_INTERNAL_CONFLICT,
                                involved_entities_json=involved_entities_json,
                                resolution_details_json={"target_signature": target_sig, "intents": list(intent_pair)},
                                turn_number=0,
                            )
                            # Avoid adding duplicate conflicts if multiple rules match or due to iteration order
                            # A more robust way: Collect all potential conflicts and then merge/deduplicate.
                            # For now, simple append.
                            is_duplicate = False
                            for existing_conflict in simulated_pending_conflicts:
                                existing_actors_involved = {(e["entity_id"], e["action_intent"]) for e in existing_conflict.involved_entities_json}
                                current_actors_involved = {(actor1_sim.id, action1.intent), (actor2_sim.id, action2.intent)}
                                if existing_actors_involved == current_actors_involved and existing_conflict.resolution_details_json.get("target_signature") == target_sig:
                                    is_duplicate = True
                                    break
                            if not is_duplicate:
                                simulated_pending_conflicts.append(sim_conflict)
                                logger.info(f"Conflict: Intents '{action1.intent}' and '{action2.intent}' on '{target_sig}'. Actors: {actor1_sim.id}, {actor2_sim.id}")
                            break # Found a rule for this pair and target, move to next pair
                    else: # Inner loop finished without break
                        continue
                    break # Outer loop: if a conflict for action1 with any other action in the group is found.
                         # This might prevent action1 from being part of another conflict.
                         # Consider if an action can be part of multiple conflicts.
                         # For simulation, one conflict per group of interacting actions might be enough.


    # TODO: Add logic for "use_on_self" vs "take" for the same item.
    # This requires checking actions that might not have the same _extract_primary_target_signature,
    # because "use_on_self:item_static:potion" and "item_static:potion" (from a "take" action) are different signatures.
    # We'd need to iterate all actions, identify "use_on_self" and "take" intents,
    # then compare their item components.

    # Example for use_on_self vs take:
    use_on_self_actions = []
    take_actions_map = {} # item_signature -> list of (actor, action)

    for sim_actor in simulated_actors: # First pass to collect relevant actions
        if not sim_actor.collected_actions_json: continue
        action_dict = sim_actor.collected_actions_json[0]
        parsed_action = ParsedAction(**action_dict)

        if parsed_action.intent == "use":
            # Check if it's a use_on_self type signature
            sig = _extract_primary_target_signature(parsed_action)
            if sig and sig.startswith("use_on_self:"):
                item_part_of_sig = sig.split("use_on_self:", 1)[1] # e.g., "item_static:potion"
                use_on_self_actions.append({"actor": sim_actor, "action": parsed_action, "item_signature": item_part_of_sig})
        elif parsed_action.intent == "take":
            item_sig_for_take = _extract_primary_target_signature(parsed_action) # Should be like "item_static:potion"
            if item_sig_for_take:
                if item_sig_for_take not in take_actions_map:
                    take_actions_map[item_sig_for_take] = []
                take_actions_map[item_sig_for_take].append((sim_actor, parsed_action))

    for u_action_info in use_on_self_actions:
        item_being_used_sig = u_action_info["item_signature"]
        if item_being_used_sig in take_actions_map:
            for t_actor_sim, t_action in take_actions_map[item_being_used_sig]:
                # Conflict: u_action_info["actor"] is using item_being_used_sig on self,
                # AND t_actor_sim is trying to take the same item_being_used_sig.
                involved_entities_json = [
                    {"entity_id": u_action_info["actor"].id, "entity_type": u_action_info["actor"].entity_type.value, "action_intent": u_action_info["action"].intent, "action_text": u_action_info["action"].raw_text, "action_entities": [e.model_dump() for e in u_action_info["action"].entities]},
                    {"entity_id": t_actor_sim.id, "entity_type": t_actor_sim.entity_type.value, "action_intent": t_action.intent, "action_text": t_action.raw_text, "action_entities": [e.model_dump() for e in t_action.entities]}
                ]
                sim_conflict = PendingConflict(
                    guild_id=guild_id,
                    conflict_type=f"sim_item_use_self_vs_take_{item_being_used_sig.replace(':', '_')}",
                    status=ConflictStatus.SIMULATED_INTERNAL_CONFLICT,
                    involved_entities_json=involved_entities_json,
                    resolution_details_json={"item_signature": item_being_used_sig},
                    turn_number=0,
                )
                # Add deduplication logic similar to above if necessary
                simulated_pending_conflicts.append(sim_conflict)
                logger.info(f"Conflict: Use on self vs Take for item '{item_being_used_sig}'. Actors: {u_action_info['actor'].id} (use), {t_actor_sim.id} (take)")


    if simulated_pending_conflicts:
        logger.info(f"Detected {len(simulated_pending_conflicts)} simulated conflict(s) in guild {guild_id} after all checks.")

    return simulated_pending_conflicts
    except Exception as e_outer:
        logger.error(f"!!! CRITICAL ERROR in simulate_conflict_detection: {e_outer}", exc_info=True)
        return [] # Return empty list on any unexpected error to prevent None


async def setup_conflict_simulation_system():
    # This function could be used if there's any setup needed for the system,
    # e.g., loading some global rules or configurations, though unlikely for this module.
    logger.info("Conflict Simulation System initialized (if any setup was needed).")
