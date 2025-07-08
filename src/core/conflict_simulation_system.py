import logging
from typing import List, Dict, Any, Optional, Tuple, Union, Callable # Added Callable

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Player, GeneratedNpc, PendingConflict, GuildConfig
from src.models.enums import RelationshipEntityType, ConflictStatus
from src.models.actions import ParsedAction, ActionEntity
from src.core.crud import player_crud, npc_crud, pending_conflict_crud
from src.core import action_processor

logger = logging.getLogger(__name__)

from pydantic import BaseModel

class PydanticConflictForSim(BaseModel):
    guild_id: int
    conflict_type: str
    status: ConflictStatus
    involved_entities_json: List[Dict[str, Any]]
    resolution_details_json: Dict[str, Any] = {}
    turn_number: int
    conflicting_actions_json: Optional[List[Dict[str, Any]]] = None

class SimulatedActionActor:
    def __init__(self, guild_id: int, parsed_action: ParsedAction, player: Optional[Player] = None, npc: Optional[GeneratedNpc] = None):
        if player:
            self.id: int = player.id
            self.entity_type = RelationshipEntityType.PLAYER
            self.name: str = player.name # Player model has .name, not .name_i18n
        elif npc:
            self.id: int = npc.id
            self.entity_type = RelationshipEntityType.GENERATED_NPC
            self.name: str = npc.name_i18n.get("en", f"NPC {npc.id}") # Default to 'en' or NPC ID
        else:
            # This case should ideally not be reached if called correctly from simulate_conflict_detection
            logger.error("SimulatedActionActor initialized without Player or NPC.")
            self.id = -1 # Placeholder or raise error
            self.entity_type = RelationshipEntityType.UNKNOWN # type: ignore[attr-defined]
            self.name = "Unknown Actor"

        self.guild_id = guild_id
        self.collected_actions_json = [parsed_action.model_dump(mode="json")]
        self.player = player
        self.npc = npc

# --- Helper function to determine the primary target signature of an action (moved to module level) ---
def _extract_primary_target_signature(action: ParsedAction) -> Optional[str]:
    intent = action.intent
    entities = action.entities
    if not entities: return None
    def find_entity_value(etype: str) -> Optional[str]:
        for entity in entities:
            if entity.type == etype: return entity.value
        return None

    if intent in ["attack", "talk", "trade_view_inventory", "trade_buy_item", "trade_sell_item"]:
        target_npc_id = find_entity_value("target_npc_id")
        if target_npc_id: return f"npc:{target_npc_id}"
        target_player_id = find_entity_value("target_player_id")
        if target_player_id: return f"player:{target_player_id}"
        target_npc_name = find_entity_value("target_npc_name")
        if target_npc_name: return f"npc_name:{target_npc_name.lower()}"
    if intent in ["take", "drop"]:
        target_item_id = find_entity_value("target_item_id")
        if target_item_id: return f"item_instance:{target_item_id}"
        item_static_id = find_entity_value("item_static_id")
        if item_static_id: return f"item_static:{item_static_id}"
        item_name = find_entity_value("item_name")
        if item_name: return f"item_name:{item_name.lower()}"
    if intent == "interact":
        obj_static_id = find_entity_value("target_object_static_id")
        if obj_static_id: return f"obj_static:{obj_static_id}"
        obj_name = find_entity_value("target_object_name")
        if obj_name: return f"obj_name:{obj_name.lower()}"
    if intent == "use":
        # Priority: Item, then Skill, then World Object
        target_item_id_for_use = find_entity_value("target_item_id")
        item_static_id_for_use = find_entity_value("item_static_id")
        item_name_val = find_entity_value("item_name")
        item_signature_part = None
        if target_item_id_for_use: item_signature_part = f"item_instance:{target_item_id_for_use}"
        elif item_static_id_for_use: item_signature_part = f"item_static:{item_static_id_for_use}"
        elif item_name_val: item_signature_part = f"item_name:{item_name_val.lower()}"

        if item_signature_part:
            target_npc_id_for_item_use = find_entity_value("target_npc_id")
            if target_npc_id_for_item_use: return f"use:{item_signature_part}@target:npc:{target_npc_id_for_item_use}"
            target_player_id_for_item_use = find_entity_value("target_player_id")
            if target_player_id_for_item_use: return f"use:{item_signature_part}@target:player:{target_player_id_for_item_use}"
            if any(e.type == "target_self" and e.value.lower() == "true" for e in entities) or \
               not (target_npc_id_for_item_use or target_player_id_for_item_use): # Default to self if no other target
                 return f"use_on_self:{item_signature_part}"
            # If item signature part exists but no specific target or self, it might be an invalid use or context-dependent
            # For now, let it fall through or return a generic item use signature if that makes sense.
            # However, typically 'use item' implies a target or self.

        skill_id_val = find_entity_value("skill_id")
        skill_name_val = find_entity_value("skill_name")
        actual_skill_ref = None
        if skill_id_val: actual_skill_ref = skill_id_val
        elif skill_name_val: actual_skill_ref = skill_name_val.lower()

        if actual_skill_ref:
            skill_sig_part = f"skill:{actual_skill_ref}"
            target_npc_id_for_skill_use = find_entity_value("target_npc_id")
            if target_npc_id_for_skill_use: return f"use:{skill_sig_part}@target:npc:{target_npc_id_for_skill_use}"
            target_player_id_for_skill_use = find_entity_value("target_player_id")
            if target_player_id_for_skill_use: return f"use:{skill_sig_part}@target:player:{target_player_id_for_skill_use}"
            # Default to self if no other target for skill
            return f"use_on_self:{skill_sig_part}"

        # New: Check for using a world object directly with 'use' intent
        target_object_static_id_for_use = find_entity_value("target_object_static_id")
        if target_object_static_id_for_use: return f"use_obj_static:{target_object_static_id_for_use}" # Reverted to use_obj_static
        target_object_name_for_use = find_entity_value("target_object_name")
        if target_object_name_for_use: return f"use_obj_name:{target_object_name_for_use.lower()}" # Reverted to use_obj_name

    if intent == "move":
        loc_static_id = find_entity_value("location_static_id")
        if loc_static_id: return f"location_static:{loc_static_id}"
        loc_name = find_entity_value("location_name")
        if loc_name: return f"location_name:{loc_name.lower()}"
        direction = find_entity_value("direction")
        if direction: return f"direction:{direction.lower()}"
    if intent == "go_to":
        subloc_static_id = find_entity_value("target_sublocation_static_id")
        if subloc_static_id: return f"subloc_static:{subloc_static_id}"
        subloc_name = find_entity_value("target_sublocation_name")
        if subloc_name: return f"subloc_name:{subloc_name.lower()}"
        point_name = find_entity_value("target_point_name")
        if point_name: return f"point_name:{point_name.lower()}"
    if intent == "examine":
        target_item_id = find_entity_value("target_item_id")
        if target_item_id: return f"item_instance:{target_item_id}"
        item_static_id = find_entity_value("item_static_id")
        if item_static_id: return f"item_static:{item_static_id}"
        obj_static_id = find_entity_value("target_object_static_id")
        if obj_static_id: return f"obj_static:{obj_static_id}"
        target_npc_id = find_entity_value("target_npc_id")
        if target_npc_id: return f"npc:{target_npc_id}"
        target_player_id = find_entity_value("target_player_id")
        if target_player_id: return f"player:{target_player_id}"
        item_name = find_entity_value("item_name")
        if item_name: return f"item_name:{item_name.lower()}"
        obj_name = find_entity_value("target_object_name")
        if obj_name: return f"obj_name:{obj_name.lower()}"
        target_npc_name = find_entity_value("target_npc_name")
        if target_npc_name: return f"npc_name:{target_npc_name.lower()}"
    if len(entities) == 1:
        entity = entities[0]
        if entity.value.strip() and \
           entity.type not in ["direction", "manner", "general_concept", "conjunction"] and \
           not entity.value.lower() in ["it", "them", "self", "myself", "here", "there"]:
            return f"generic_target:{entity.type}:{entity.value.lower()}"
    return None

from src.core.rules import get_rule # Убедиться, что импорт есть

# --- Default rule definitions (to be used if not found in RuleConfig) ---

DEFAULT_RULES_SAME_INTENT_SAME_TARGET_CFG: Dict[str, Dict[str, Any]] = {
    "EXCLUSIVE_ITEM_MANIPULATION": {
        "intents": ["take"],
        "target_prefixes": ["item_instance:", "item_static:", "item_name:"],
        "description": "Only one actor can 'take' the same item instance/type at a time."
    },
    "EXCLUSIVE_OBJECT_MANIPULATION": { # Renamed and expanded
        "intents": ["interact", "use"], # Added "use"
        "target_prefixes": ["obj_static:", "obj_name:", "use_obj_static:", "use_obj_name:"], # Added new prefixes
        "description": "'interact' or 'use' on the same specific object by multiple actors."
    },
    # Conceptual rule for future expansion if actor state becomes available
    # "EXCLUSIVE_TARGET_USAGE_WITH_STATE": {
    #     "intents": ["use_object_exclusive"], # Hypothetical intent for objects like alchemy tables
    #     "target_prefixes": ["obj_static:", "obj_name:"],
    #     "description": "Only one actor can 'use' an exclusive-use object at a time, considering state."
    #     # "requires_actor_state": {"field": "is_using_exclusive_object", "value": false} # Hypothetical
    # },
    "COMBAT_ENGAGEMENT_SHARED_TARGET": {
        "intents": ["attack"],
        "target_prefixes": ["npc:", "player:", "npc_name:"],
        "description": "Multiple actors attacking the same target."
    },
    "TRADE_SESSION_EXCLUSIVE": {
        "intents": ["trade_view_inventory", "trade_buy_item", "trade_sell_item"],
        "target_prefixes": ["npc:", "npc_name:"],
        "description": "Trade actions with the same NPC by multiple actors."
    },
    "EXCLUSIVE_POINT_OCCUPATION": {
        "intents": ["go_to"],
        "target_prefixes": ["subloc_static:", "subloc_name:", "point_name:"],
        "description": "Multiple actors trying to 'go_to' the same specific exclusive point."
    },
}

DEFAULT_RULES_CONFLICTING_INTENT_PAIRS_CFG: List[Dict[str, Any]] = [
    {
        "intent_pair": ["take", "use"],
        "applies_to": [{"conflict_name_template": "item_contention", "target_prefixes": ["item_instance:", "item_static:", "item_name:"]}],
        "description": "'take' and 'use' on the same item by different actors."
    },
    {
        "intent_pair": ["take", "drop"],
        "applies_to": [{"conflict_name_template": "item_state_race", "target_prefixes": ["item_instance:", "item_static:", "item_name:"]}],
        "description": "'take' and 'drop' on the same item."
    },
    {
        "intent_pair": ["attack", "talk"],
        "applies_to": [{"conflict_name_template": "disrupted_interaction_npc", "target_prefixes": ["npc:", "npc_name:"]}],
        "description": "Attacking an NPC while another tries to talk to them."
    },
    {
        "intent_pair": ["attack", "trade_view_inventory"],
        "applies_to": [{"conflict_name_template": "disrupted_trade_npc", "target_prefixes": ["npc:", "npc_name:"]}],
        "description": "Attacking an NPC during trade initiation." # Added description
    },
    {
        "intent_pair": ["attack", "trade_buy_item"],
        "applies_to": [{"conflict_name_template": "disrupted_trade_npc", "target_prefixes": ["npc:", "npc_name:"]}],
        "description": "Attacking an NPC during a buy transaction." # Added description
    },
    {
        "intent_pair": ["attack", "trade_sell_item"],
        "applies_to": [{"conflict_name_template": "disrupted_trade_npc", "target_prefixes": ["npc:", "npc_name:"]}],
        "description": "Attacking an NPC during a sell transaction." # Added description
    },
    {
        "intent_pair": ["interact", "destroy_object"], # Assuming "destroy_object" is a valid intent
        "applies_to": [{"conflict_name_template": "object_state_conflict", "target_prefixes": ["obj_static:", "obj_name:", "use_obj_static:", "use_obj_name:"]}], # Expanded target_prefixes
        "description": "Interacting with an object while another tries to destroy it."
    },
    {
        "intent_pair": ["talk", "use"], # 'use' can be item or skill on NPC
        "applies_to": [{"conflict_name_template": "npc_interaction_interference", "target_prefixes": ["npc:", "npc_name:"]}],
        "description": "Talking to an NPC while another tries to 'use' an item/skill on them."
    },
    # Conceptual rule for future expansion
    # {
    #     "intent_pair": ["activate_portal_step1", "activate_portal_step2"], # Hypothetical sequence
    #     "applies_to": [{"conflict_name_template": "portal_activation_sequence_conflict", "target_prefixes": ["obj_static:portal_main"]}],
    #     "description": "Two actors trying to perform different steps of a sequential activation on the same portal.",
    #     # "requires_sequence_order": true, # Hypothetical property
    #     # "actor_must_not_be_same": true # Hypothetical: different actors conflict, same actor is fine
    # },
]

async def _get_rules_same_intent_same_target(session: AsyncSession, guild_id: int) -> Dict[str, Tuple[set[str], Optional[Tuple[str, ...]]]]:
    rules_from_db = await get_rule(session, guild_id, "conflict_simulation:rules_same_intent_same_target", DEFAULT_RULES_SAME_INTENT_SAME_TARGET_CFG)

    formatted_rules: Dict[str, Tuple[set[str], Optional[Tuple[str, ...]]]] = {}
    if isinstance(rules_from_db, dict):
        for category, details in rules_from_db.items():
            if isinstance(details, dict) and "intents" in details:
                intents_set = set(details.get("intents", []))
                prefixes_list = details.get("target_prefixes")
                # Ensure prefixes_tuple is None if prefixes_list is empty or None, otherwise it's a tuple
                prefixes_tuple = tuple(prefixes_list) if prefixes_list else None
                formatted_rules[category] = (intents_set, prefixes_tuple)
    return formatted_rules

async def _get_rules_conflicting_intent_pairs(session: AsyncSession, guild_id: int) -> Dict[frozenset[str], List[Tuple[str, Tuple[str, ...]]]]:
    rules_list_from_db = await get_rule(session, guild_id, "conflict_simulation:rules_conflicting_intent_pairs", DEFAULT_RULES_CONFLICTING_INTENT_PAIRS_CFG)

    formatted_rules: Dict[frozenset[str], List[Tuple[str, Tuple[str, ...]]]] = {}
    if isinstance(rules_list_from_db, list):
        for rule_item in rules_list_from_db:
            if isinstance(rule_item, dict) and "intent_pair" in rule_item and "applies_to" in rule_item:
                intent_pair_list = rule_item.get("intent_pair", [])
                if isinstance(intent_pair_list, list) and len(intent_pair_list) == 2:
                    key = frozenset(sorted(intent_pair_list)) # Ensure order for frozenset key
                    applies_to_list_data = rule_item.get("applies_to", [])
                    if isinstance(applies_to_list_data, list):
                        processed_applies_to = []
                        for app_to_item in applies_to_list_data:
                            if isinstance(app_to_item, dict) and "conflict_name_template" in app_to_item and "target_prefixes" in app_to_item:
                                prefixes = app_to_item.get("target_prefixes", [])
                                if isinstance(prefixes, list):
                                     processed_applies_to.append(
                                        (app_to_item["conflict_name_template"], tuple(prefixes))
                                    )
                        if processed_applies_to:
                            formatted_rules[key] = processed_applies_to
    return formatted_rules

async def _is_use_self_vs_take_check_enabled(session: AsyncSession, guild_id: int) -> bool:
    config = await get_rule(session, guild_id, "conflict_simulation:enable_use_self_vs_take_check", {"enabled": True})
    if isinstance(config, dict):
        return config.get("enabled", True)
    return True


def _apply_same_intent_conflict_rules(
    actions_on_this_target: List[Tuple[SimulatedActionActor, ParsedAction]],
    target_sig: str,
    guild_id: int,
    rules_to_apply: Dict[str, Tuple[set[str], Optional[Tuple[str, ...]]]]
) -> List[PydanticConflictForSim]:
    """Applies Rule 1: Multiple actors performing the same 'exclusive category' intent on the same target."""
    conflicts: List[PydanticConflictForSim] = []
    for category_name, (exclusive_intents, target_prefixes) in rules_to_apply.items():
        if target_prefixes is not None and not any(target_sig.startswith(p) for p in target_prefixes):
            continue

        relevant_actions_for_category = [
            (actor, p_action) for actor, p_action in actions_on_this_target if p_action.intent in exclusive_intents
        ]

        if len(relevant_actions_for_category) > 1:
            intents_in_relevant_actions = {p_action.intent for _, p_action in relevant_actions_for_category}
            for specific_intent_from_category in intents_in_relevant_actions:
                actions_with_this_specific_intent = [
                    (actor, p_action) for actor, p_action in relevant_actions_for_category if p_action.intent == specific_intent_from_category
                ]
                if len(actions_with_this_specific_intent) > 1:
                    involved_entities_json = [
                        {"entity_id": actor_sim.id, "entity_type": actor_sim.entity_type.value,
                         "action_intent": p_action.intent, "action_text": p_action.raw_text,
                         "action_entities": [e.model_dump() for e in p_action.entities]}
                        for actor_sim, p_action in actions_with_this_specific_intent
                    ]
                    conflict_type_str: str
                    target_sig_simplified = target_sig.replace(':', '_')
                    if category_name == "COMBAT_ENGAGEMENT_SHARED_TARGET" and specific_intent_from_category == "attack":
                        conflict_type_str = f"sim_multi_attack_on_{target_sig_simplified}"
                    elif category_name == "EXCLUSIVE_ITEM_MANIPULATION" and specific_intent_from_category == "take":
                        conflict_type_str = f"sim_item_take_contention_on_{target_sig_simplified}"
                    else:
                        conflict_type_str = f"sim_{category_name.lower()}_on_{specific_intent_from_category}_for_{target_sig_simplified}"

                    current_resolution_details: Dict[str, Any]
                    if category_name == "COMBAT_ENGAGEMENT_SHARED_TARGET" and specific_intent_from_category == "attack":
                        current_resolution_details = {"target_signature": target_sig}
                    elif category_name == "EXCLUSIVE_ITEM_MANIPULATION" and specific_intent_from_category == "take":
                        current_resolution_details = {"target_signature": target_sig}
                    else:
                        current_resolution_details = {"target_signature": target_sig, "category": category_name, "conflicting_intent": specific_intent_from_category}

                    sim_conflict = PydanticConflictForSim(
                        guild_id=guild_id,
                        conflict_type=conflict_type_str,
                        status=ConflictStatus.SIMULATED_INTERNAL_CONFLICT,
                        involved_entities_json=involved_entities_json,
                        resolution_details_json=current_resolution_details,
                        turn_number=0
                    )
                    # print(f"[DEBUG] Rule 1: CONFLICT CREATED for {target_sig} with intent {specific_intent_from_category}") # DEBUG
                    conflicts.append(sim_conflict)
                    logger.info(f"Conflict (Rule 1): {category_name} with intent '{specific_intent_from_category}' on '{target_sig}'. Actors: {[a.id for a, _ in actions_with_this_specific_intent]}")
                    # return conflicts
    return conflicts

def _apply_conflicting_intent_pairs_rules(
    actions_on_this_target: List[Tuple[SimulatedActionActor, ParsedAction]],
    target_sig: str,
    guild_id: int,
    existing_conflicts: List[PydanticConflictForSim],
    rules_to_apply: Dict[frozenset[str], List[Tuple[str, Tuple[str, ...]]]]
) -> List[PydanticConflictForSim]:
    """Applies Rule 2: Check for conflicting intent pairs on the same target."""
    new_conflicts: List[PydanticConflictForSim] = []
    if len(actions_on_this_target) < 2:
        return new_conflicts

    for i in range(len(actions_on_this_target)):
        for j in range(i + 1, len(actions_on_this_target)):
            actor1_sim, action1 = actions_on_this_target[i]
            actor2_sim, action2 = actions_on_this_target[j]

            intent_pair = frozenset(sorted({action1.intent, action2.intent})) # Ensure order for key lookup
            if intent_pair in rules_to_apply:
                rules_for_pair = rules_to_apply[intent_pair]
                for conflict_name_tpl, target_category_pattern_tuple in rules_for_pair:
                    if any(target_sig.startswith(p) for p in target_category_pattern_tuple):
                        involved_entities_json = [
                            {"entity_id": actor1_sim.id, "entity_type": actor1_sim.entity_type.value, "action_intent": action1.intent, "action_text": action1.raw_text, "action_entities": [e.model_dump() for e in action1.entities]},
                            {"entity_id": actor2_sim.id, "entity_type": actor2_sim.entity_type.value, "action_intent": action2.intent, "action_text": action2.raw_text, "action_entities": [e.model_dump() for e in action2.entities]}
                        ]
                        target_sig_simplified = target_sig.replace(':', '_')
                        # Generalize conflict type name, remove specific intents from it
                        current_conflict_type = f"sim_{conflict_name_tpl}_on_{target_sig_simplified}"

                        sim_conflict = PydanticConflictForSim(
                            guild_id=guild_id,
                            conflict_type=current_conflict_type,
                            status=ConflictStatus.SIMULATED_INTERNAL_CONFLICT,
                            involved_entities_json=involved_entities_json,
                            resolution_details_json={"target_signature": target_sig, "intents": sorted(list(intent_pair))},
                            turn_number=0
                        )

                        is_duplicate = False
                        # Ensure consistent order for frozenset of involved actors for duplication check
                        current_actors_involved_tuples = sorted(
                            ( (e["entity_id"], e["action_intent"]) for e in involved_entities_json),
                            key=lambda x: (x[0], x[1])
                        )
                        current_actors_involved = frozenset(current_actors_involved_tuples)

                        for existing_conflict in existing_conflicts + new_conflicts:
                            existing_actors_inv_tuples = sorted(
                                ( (e["entity_id"], e["action_intent"]) for e in existing_conflict.involved_entities_json),
                                key=lambda x: (x[0], x[1])
                            )
                            existing_actors_inv = frozenset(existing_actors_inv_tuples)

                            if existing_conflict.conflict_type == current_conflict_type and \
                               existing_actors_inv == current_actors_involved and \
                               existing_conflict.resolution_details_json.get("target_signature") == target_sig:
                                is_duplicate = True
                                break
                        if not is_duplicate:
                            new_conflicts.append(sim_conflict)
                            logger.info(f"Conflict (Rule 2): Intents '{action1.intent}' and '{action2.intent}' on '{target_sig}'. Actors: {actor1_sim.id}, {actor2_sim.id}")
                        break
    return new_conflicts

def _check_use_self_vs_take_conflicts(
    simulated_actors: List[SimulatedActionActor],
    guild_id: int,
    _extract_primary_target_signature_func: Callable[[ParsedAction], Optional[str]]
) -> List[PydanticConflictForSim]:
    """Checks for conflicts between 'use on self' and 'take' for the same item."""
    conflicts: List[PydanticConflictForSim] = []
    use_on_self_actions = []
    take_actions_map: Dict[str, List[Tuple[SimulatedActionActor, ParsedAction]]] = {}
    # print("[DEBUG] Rule 3: Starting _check_use_self_vs_take_conflicts") # DEBUG

    for sim_actor in simulated_actors:
        if not sim_actor.collected_actions_json: continue
        action_dict = sim_actor.collected_actions_json[0]
        parsed_action = ParsedAction(**action_dict)
        # print(f"[DEBUG] Rule 3: Processing Actor ID {sim_actor.id}, Intent '{parsed_action.intent}'") # DEBUG

        if parsed_action.intent == "use":
            sig = _extract_primary_target_signature_func(parsed_action)
            # print(f"[DEBUG] Rule 3: Use action, sig='{sig}'") # DEBUG
            if sig and sig.startswith("use_on_self:"):
                item_part_of_sig = sig.split("use_on_self:", 1)[1]
                # print(f"[DEBUG] Rule 3: Added use_on_self action for item_sig '{item_part_of_sig}' by actor {sim_actor.id}") # DEBUG
                use_on_self_actions.append({"actor": sim_actor, "action": parsed_action, "item_signature": item_part_of_sig})
        elif parsed_action.intent == "take":
            item_sig_for_take = _extract_primary_target_signature_func(parsed_action)
            # print(f"[DEBUG] Rule 3: Take action, item_sig_for_take='{item_sig_for_take}'") # DEBUG
            if item_sig_for_take:
                if item_sig_for_take not in take_actions_map:
                    take_actions_map[item_sig_for_take] = []
                take_actions_map[item_sig_for_take].append((sim_actor, parsed_action))
                # print(f"[DEBUG] Rule 3: Added take action for item_sig '{item_sig_for_take}' by actor {sim_actor.id}") # DEBUG

    # print(f"[DEBUG] Rule 3: use_on_self_actions count: {len(use_on_self_actions)}") # DEBUG
    # print(f"[DEBUG] Rule 3: take_actions_map: {list(take_actions_map.keys())}") # DEBUG

    for u_action_info in use_on_self_actions:
        item_being_used_sig = u_action_info["item_signature"]
        # print(f"[DEBUG] Rule 3: Checking use_on_self item_sig '{item_being_used_sig}' against take_actions_map") # DEBUG
        if item_being_used_sig in take_actions_map:
            # print(f"[DEBUG] Rule 3: MATCH FOUND for item_sig '{item_being_used_sig}'!") # DEBUG
            for t_actor_sim, t_action in take_actions_map[item_being_used_sig]:
                involved_entities_json = [
                    {"entity_id": u_action_info["actor"].id, "entity_type": u_action_info["actor"].entity_type.value, "action_intent": u_action_info["action"].intent, "action_text": u_action_info["action"].raw_text, "action_entities": [e.model_dump() for e in u_action_info["action"].entities]},
                    {"entity_id": t_actor_sim.id, "entity_type": t_actor_sim.entity_type.value, "action_intent": t_action.intent, "action_text": t_action.raw_text, "action_entities": [e.model_dump() for e in t_action.entities]}
                ]
                # Specific type for "use on self" vs "take"
                conflict_type = f"sim_item_use_self_vs_take_{item_being_used_sig.replace(':', '_').lower()}"
                # Specific resolution detail expected by some tests for this exact conflict type
                resolution_details = {"item_signature": item_being_used_sig}

                sim_conflict = PydanticConflictForSim(
                    guild_id=guild_id,
                    conflict_type=conflict_type,
                    status=ConflictStatus.SIMULATED_INTERNAL_CONFLICT,
                    involved_entities_json=involved_entities_json,
                    resolution_details_json=resolution_details,
                    turn_number=0
                )
                conflicts.append(sim_conflict)
                logger.info(f"Conflict (Rule 3): Use on self vs Take for item '{item_being_used_sig}'. Actors: {u_action_info['actor'].id} (use), {t_actor_sim.id} (take)")
    return conflicts

async def simulate_conflict_detection(
    session: AsyncSession,
    guild_id: int,
    actions_input_data: List[Dict[str, Any]]
) -> List[PydanticConflictForSim]:
    try:
        simulated_actors: List[SimulatedActionActor] = []
        for action_data in actions_input_data:
            actor_id = action_data.get("actor_id")
            actor_type_str = action_data.get("actor_type")
            raw_parsed_action_dict = action_data.get("parsed_action")
            # print(f"[DEBUG] raw_parsed_action_dict for actor {action_data.get('actor_id')}: {raw_parsed_action_dict}")

            if not all([actor_id, actor_type_str, raw_parsed_action_dict]):
                logger.warning(f"Skipping invalid action data (missing actor_id, actor_type, or parsed_action): {action_data}")
                continue

            assert actor_id is not None
            assert actor_type_str is not None
            assert raw_parsed_action_dict is not None

            # 1. Fetch actor_player or actor_npc first
            actor_player: Optional[Player] = None
            actor_npc: Optional[GeneratedNpc] = None
            current_actor_db_id = actor_id # Keep original actor_id for fetching

            if actor_type_str.lower() == RelationshipEntityType.PLAYER.value:
                actor_player = await player_crud.get(session, current_actor_db_id)
                if not actor_player or actor_player.guild_id != guild_id:
                    logger.warning(f"Player {current_actor_db_id} not found or not in guild {guild_id} for simulation.")
                    continue
            elif actor_type_str.lower() == RelationshipEntityType.GENERATED_NPC.value:
                actor_npc = await npc_crud.get(session, current_actor_db_id)
                if not actor_npc or actor_npc.guild_id != guild_id:
                    logger.warning(f"NPC {current_actor_db_id} not found or not in guild {guild_id} for simulation.")
                    continue
            else:
                logger.warning(f"Unsupported actor_type '{actor_type_str}' for simulation for actor_id {current_actor_db_id}.")
                continue

            # 2. Now prepare ParsedAction
            parsed_action_instance: Optional[ParsedAction] = None
            action_intent: str = "unknown_intent"
            action_raw_text: str = ""
            action_entities_dicts: list = [] # Default to empty list

            try:
                action_intent = raw_parsed_action_dict.get("intent", "unknown_intent")
                action_raw_text = raw_parsed_action_dict.get("raw_text", "")
                action_entities_dicts = raw_parsed_action_dict.get("entities", [])

                parsed_entities: List[ActionEntity] = []
                if isinstance(action_entities_dicts, list):
                    for entity_dict in action_entities_dicts:
                        if isinstance(entity_dict, dict):
                            try:
                                parsed_entities.append(ActionEntity(**entity_dict))
                            except Exception as entity_parse_e:
                                logger.warning(f"Could not parse entity dict {entity_dict} into ActionEntity: {entity_parse_e}")
                        else:
                             logger.warning(f"Entity item {entity_dict} is not a dictionary, skipping.")
                else:
                    logger.warning(f"Entities data {action_entities_dicts} is not a list, cannot parse entities.")

                actor_discord_id_for_action: Optional[int] = None
                if actor_player: # Use the fetched actor_player
                    actor_discord_id_for_action = actor_player.discord_id

                parsed_action_instance = ParsedAction(
                    raw_text=action_raw_text,
                    intent=action_intent,
                    entities=parsed_entities,
                    guild_id=guild_id,
                    player_id=actor_discord_id_for_action
                )
            except Exception as e:
                logged_entities_str = str(action_entities_dicts) # Basic string conversion
                try:
                    if isinstance(action_entities_dicts, list): # Attempt more detailed if list
                        logged_entities_str = str([str(ed) for ed in action_entities_dicts])
                except: pass
                logger.warning(f"Skipping action data due to ParsedAction validation error: repr(e)='{repr(e)}' - Input dict: {raw_parsed_action_dict}, Parsed args: raw_text='{action_raw_text}', intent='{action_intent}', entities_original_type={type(action_entities_dicts)}, entities_logged_str={logged_entities_str}, Guild: {guild_id}, Actor: {current_actor_db_id}", exc_info=True)
                continue

            if parsed_action_instance is None:
                logger.error(f"parsed_action_instance is None for actor {current_actor_db_id}, skipping.")
                continue

            sim_actor = SimulatedActionActor(guild_id=guild_id, parsed_action=parsed_action_instance, player=actor_player, npc=actor_npc)
            simulated_actors.append(sim_actor)

        if not simulated_actors:
            return []

        # logger.info(f"Simulating conflict detection for {len(simulated_actors)} actions in guild {guild_id}.")
        # # ---- DEBUG PRINT ----
        # print(f"[DEBUG] Main: Number of simulated_actors: {len(simulated_actors)}")
        # for i, sa in enumerate(simulated_actors):
        #     print(f"[DEBUG] Main: Actor {i} - ID: {sa.id}, Type: {sa.entity_type}, Name: {sa.name}")
        #     if sa.collected_actions_json:
        #         print(f"[DEBUG] Main:   Action: {sa.collected_actions_json[0]}")
        #     else:
        #         print(f"[DEBUG] Main:   NO ACTION JSON")
        # # ---- END DEBUG PRINT ----
        simulated_pending_conflicts: List[PydanticConflictForSim] = []
        if len(simulated_actors) < 2:
            # print("[DEBUG] Main: Less than 2 simulated actors, returning empty conflicts.") # DEBUG
            return []

        # Fetch conflict rules once
        rules_same_intent = await _get_rules_same_intent_same_target(session, guild_id)
        rules_conflicting_pairs = await _get_rules_conflicting_intent_pairs(session, guild_id)
        use_take_check_enabled = await _is_use_self_vs_take_check_enabled(session, guild_id)


        actions_by_target_sig: Dict[str, List[Tuple[SimulatedActionActor, ParsedAction]]] = {}
        # print("[DEBUG] Main: Grouping actions by target signature...") # DEBUG
        for sim_actor in simulated_actors:
            if not sim_actor.collected_actions_json: continue
            try:
                action_dict = sim_actor.collected_actions_json[0]
                parsed_action = ParsedAction(**action_dict)
            except Exception as e:
                logger.error(f"Error re-parsing action for target grouping: {e} for actor {sim_actor.id}")
                continue
            target_sig = _extract_primary_target_signature(parsed_action)
            # print(f"[DEBUG] Main: Actor ID {sim_actor.id}, Action '{parsed_action.raw_text}', Intent '{parsed_action.intent}', Entities '{parsed_action.entities}', Target_Sig: '{target_sig}'") # DEBUG
            if target_sig:
                if target_sig not in actions_by_target_sig:
                    actions_by_target_sig[target_sig] = []
                actions_by_target_sig[target_sig].append((sim_actor, parsed_action))

        # # ---- DEBUG PRINT ----
        # print(f"[DEBUG] Main: actions_by_target_sig content:")
        # for ts, act_list in actions_by_target_sig.items():
        #     print(f"[DEBUG] Main:   '{ts}': {len(act_list)} actions")
        #     for sa_dbg, pa_dbg in act_list:
        #          print(f"[DEBUG] Main:     Actor {sa_dbg.id}, Intent {pa_dbg.intent}")
        # # ---- END DEBUG PRINT ----

        for target_sig, actions_on_this_target in actions_by_target_sig.items():
            # print(f"[DEBUG] Main: Processing target_sig '{target_sig}' with {len(actions_on_this_target)} actions.") # DEBUG
            if len(actions_on_this_target) < 2:
                # print(f"[DEBUG] Main: Skipping target_sig '{target_sig}' due to < 2 actions.") # DEBUG
                continue
            rule1_conflicts = _apply_same_intent_conflict_rules(actions_on_this_target, target_sig, guild_id, rules_same_intent)
            if rule1_conflicts:
                simulated_pending_conflicts.extend(rule1_conflicts)
            rule2_conflicts = _apply_conflicting_intent_pairs_rules(actions_on_this_target, target_sig, guild_id, simulated_pending_conflicts, rules_conflicting_pairs)
            simulated_pending_conflicts.extend(rule2_conflicts)

        if use_take_check_enabled:
            rule3_conflicts = _check_use_self_vs_take_conflicts(simulated_actors, guild_id, _extract_primary_target_signature)
            for r3_conflict_item in rule3_conflicts: # Iterate with a new variable name
                is_r3_duplicate = False
                # Now use r3_conflict_item for checks and appending
                r3_involved_actors_set = frozenset( (e["entity_id"], e["action_intent"]) for e in r3_conflict_item.involved_entities_json )
                for existing_c in simulated_pending_conflicts:
                    ex_involved_actors_set = frozenset( (e["entity_id"], e["action_intent"]) for e in existing_c.involved_entities_json )
                    if existing_c.conflict_type == r3_conflict_item.conflict_type and \
                       ex_involved_actors_set == r3_involved_actors_set and \
                       existing_c.resolution_details_json.get("item_signature") == r3_conflict_item.resolution_details_json.get("item_signature"):
                        is_r3_duplicate = True
                        break
                if not is_r3_duplicate:
                    simulated_pending_conflicts.append(r3_conflict_item) # Append the item from the current iteration

        if simulated_pending_conflicts:
            logger.info(f"Detected {len(simulated_pending_conflicts)} simulated conflict(s) in guild {guild_id} after all checks.")
        return simulated_pending_conflicts
    except Exception as e_outer:
        logger.error(f"!!! CRITICAL ERROR in simulate_conflict_detection: {e_outer}", exc_info=True)
        return []

async def setup_conflict_simulation_system():
    logger.info("Conflict Simulation System initialized (if any setup was needed).")
