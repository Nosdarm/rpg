import asyncio
import logging
import random
from typing import List, Dict, Any, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# Models
from ..models import (
    GlobalNpc,
    MobileGroup,
    Location,
    Player,
    GeneratedNpc,
    Relationship,
    RuleConfig,
    EventType,
    RelationshipEntityType,
    StoryLog,
    CheckResult as CheckResultModel,
    CheckOutcome,
)

# CRUDs
from .crud import (
    global_npc_crud,
    mobile_group_crud,
    player_crud,
    npc_crud as generated_npc_crud, # For fetching local NPCs (GeneratedNpc)
    location_crud,
    crud_relationship,
    rule_config_crud
)

# Core systems
from .rules import get_rule
from .check_resolver import resolve_check, CheckError
from .combat_cycle_manager import start_combat
from .quest_system import handle_player_event_for_quest
from .game_events import log_event

logger = logging.getLogger(__name__)

DEFAULT_REACTION_RULE = {
    "description": "Default fallback reaction: observe and log.",
    "default_actions": [{"action": "log_and_observe", "weight": 100}]
}
DEFAULT_DETECTION_RULE = {"enabled": False, "check_type": "perception", "base_dc": 10} # Added more defaults

async def simulate_global_entities_for_guild(session: AsyncSession, guild_id: int):
    logger.info(f"Starting global entity simulation for guild_id: {guild_id}")

    try:
        # Assuming CRUD methods like get_multi_by_guild_id_active exist or are created.
        # These would ideally filter by a property in properties_json or a dedicated status field.
        # For now, let's assume get_multi_by_guild_id returns all and we filter manually or it has an active flag.
        # Casting to List to satisfy the type hint, assuming the CRUD methods return Sequence or Iterable.
        active_global_npcs_seq = await global_npc_crud.get_multi_by_guild_id(session, guild_id=guild_id) # Assuming this fetches all, replace with _active if exists
        active_global_npcs: List[GlobalNpc] = list(active_global_npcs_seq) if active_global_npcs_seq else []

        active_mobile_groups_seq = await mobile_group_crud.get_multi_by_guild_id(session, guild_id=guild_id) # Assuming this fetches all
        active_mobile_groups: List[MobileGroup] = list(active_mobile_groups_seq) if active_mobile_groups_seq else []
    except Exception as e:
        logger.error(f"Error loading active global entities for guild {guild_id}: {e}", exc_info=True)
        return

    all_global_entities: List[Union[GlobalNpc, MobileGroup]] = [*active_global_npcs, *active_mobile_groups] # This is fine

    if not all_global_entities:
        logger.debug(f"No active global entities found for guild_id: {guild_id}")
        return

    for entity in all_global_entities:
        entity_type_str = entity.__class__.__name__
        try:
            logger.debug(f"Simulating entity: {entity.static_id} ({entity_type_str}) in guild {guild_id}")

            await _simulate_entity_movement(session, guild_id, entity)
            await session.refresh(entity)

            if entity.current_location_id:
                await _simulate_entity_interactions(session, guild_id, entity)
            else:
                logger.debug(f"Entity {entity.static_id} has no current location after movement, skipping interaction.")

        except Exception as e:
            logger.error(f"Error simulating entity {entity.static_id} ({entity_type_str}) in guild {guild_id}: {e}", exc_info=True)
            # Add specific error handling or rollback if needed for a single entity's failure

    logger.info(f"Finished global entity simulation for guild_id: {guild_id}")


async def _determine_next_location_id(session: AsyncSession, guild_id: int, entity: Union[GlobalNpc, MobileGroup]) -> Optional[int]:
    route_info = None
    props = entity.properties_json or {}

    if isinstance(entity, MobileGroup) and entity.route_json:
        route_info = entity.route_json
    elif "route_json" in props:
        route_info = props["route_json"]

    if route_info:
        current_route_index = props.get("current_route_index", 0) # Store index in properties_json
        route_location_static_ids: List[str] = route_info.get("location_static_ids", [])

        if not route_location_static_ids: return None

        next_route_index = current_route_index
        if entity.current_location_id:
            try:
                current_loc_model = await location_crud.get(session, id=entity.current_location_id)
                if current_loc_model and current_loc_model.static_id in route_location_static_ids:
                    current_idx_in_route = route_location_static_ids.index(current_loc_model.static_id)
                    next_route_index = current_idx_in_route + 1
                # If current loc not in route, it will try to move to current_route_index (from props)
            except Exception as e:
                 logger.warning(f"Error finding current_location {entity.current_location_id} in route for {entity.static_id}: {e}")

        if 0 <= next_route_index < len(route_location_static_ids):
            next_location_static_id = route_location_static_ids[next_route_index]
            next_location = await location_crud.get_by_static_id(session, guild_id=guild_id, static_id=next_location_static_id)
            if next_location:
                new_props = props.copy()
                if route_info.get("type") == "cyclical" and next_route_index >= len(route_location_static_ids) - 1:
                    new_props["current_route_index"] = 0
                elif next_route_index < len(route_location_static_ids) -1:
                    new_props["current_route_index"] = next_route_index + 1
                else: # Reached end of non-cyclical route
                    new_props.pop("current_route_index", None)
                    new_props.pop("route_json", None) # Optionally clear route when done
                    logger.info(f"Entity {entity.static_id} reached end of route.")
                entity.properties_json = new_props
                return next_location.id
        return None

    goal_static_id = props.get("goal_location_static_id")
    if goal_static_id:
        target_location = await location_crud.get_by_static_id(session, guild_id=guild_id, static_id=goal_static_id)
        if target_location:
            if target_location.id == entity.current_location_id:
                new_props = props.copy()
                new_props.pop("goal_location_static_id", None)
                entity.properties_json = new_props
                logger.info(f"Entity {entity.static_id} reached goal location {goal_static_id}.")
                # TODO: Trigger goal reached logic (e.g., set new goal, go idle)
                return None
            # Simplified: Assume direct move if not at goal. Real pathfinding needed for non-adjacent.
            # For now, only return if it's a valid different location.
            return target_location.id
    return None

async def _simulate_entity_movement(session: AsyncSession, guild_id: int, entity: Union[GlobalNpc, MobileGroup]):
    entity_name_en = entity.name_i18n.get("en", entity.static_id)
    movement_rule_key = f"global_entity_movement:{entity.__class__.__name__.lower()}:base_steps_per_tick"
    movement_params_result = await get_rule(session, guild_id, movement_rule_key)
    movement_params = movement_params_result if movement_params_result is not None else {"steps": 1}


    steps_to_take = movement_params.get("steps", 1)
    if steps_to_take <= 0:
        logger.debug(f"Entity {entity.static_id} has 0 or negative steps to take this tick.")
        return

    original_location_id = entity.current_location_id
    next_location_id = await _determine_next_location_id(session, guild_id, entity)

    if next_location_id and next_location_id != original_location_id:
        entity.current_location_id = next_location_id
        await session.commit()

        event_details = {
            "entity_id": entity.id, "entity_static_id": entity.static_id,
            "entity_type": entity.__class__.__name__, "entity_name_i18n": entity.name_i18n,
            "old_location_id": original_location_id, "new_location_id": next_location_id,
        }
        try:
            if original_location_id:
                old_loc = await location_crud.get(session, id=original_location_id)
                if old_loc: event_details["old_location_name_i18n"] = old_loc.name_i18n
            new_loc = await location_crud.get(session, id=next_location_id)
            if new_loc: event_details["new_location_name_i18n"] = new_loc.name_i18n
        except Exception as e:
            logger.warning(f"Could not fetch location names for movement log of {entity.static_id}: {e}")

        await log_event(
            session=session, guild_id=guild_id, event_type=EventType.GLOBAL_ENTITY_MOVED.value, # Use .value
            details_json=event_details,
            entity_ids_json={"source_entity_id": entity.id, "source_entity_type": entity.__class__.__name__}
        )
        logger.info(f"Entity {entity.static_id} moved from {original_location_id} to {next_location_id}")
    else:
        logger.debug(f"Entity {entity.static_id} did not move (no valid next location or already at goal/end of route).")

async def _get_entities_in_location(session: AsyncSession, guild_id: int, location_id: int, exclude_entity: Optional[Union[GlobalNpc, MobileGroup]] = None) -> List[Any]:
    entities_in_loc = []

    # Assuming get_multi_by_attribute or a more specific method like get_multi_by_current_location_id exists
    players_seq = await player_crud.get_multi_by_attribute(session, guild_id=guild_id, attribute_name="current_location_id", attribute_value=location_id) # type: ignore
    entities_in_loc.extend(list(players_seq) if players_seq else [])

    local_npcs_seq = await generated_npc_crud.get_multi_by_attribute(session, guild_id=guild_id, attribute_name="current_location_id", attribute_value=location_id) # type: ignore
    entities_in_loc.extend(list(local_npcs_seq) if local_npcs_seq else [])

    global_npcs_seq = await global_npc_crud.get_multi_by_attribute(session, guild_id=guild_id, attribute_name="current_location_id", attribute_value=location_id) # type: ignore
    if global_npcs_seq:
        for gn in global_npcs_seq:
            if exclude_entity and isinstance(exclude_entity, GlobalNpc) and gn.id == exclude_entity.id: continue
            entities_in_loc.append(gn)

    mobile_groups_seq = await mobile_group_crud.get_multi_by_attribute(session, guild_id=guild_id, attribute_name="current_location_id", attribute_value=location_id) # type: ignore
    if mobile_groups_seq:
        for mg in mobile_groups_seq:
            if exclude_entity and isinstance(exclude_entity, MobileGroup) and mg.id == exclude_entity.id: continue
            entities_in_loc.append(mg)

    return entities_in_loc

def _get_entity_type_for_rules(entity: Any) -> str:
    if isinstance(entity, Player): return "player"
    if isinstance(entity, GeneratedNpc): return "generated_npc"
    if isinstance(entity, GlobalNpc): return "global_npc"
    if isinstance(entity, MobileGroup): return "mobile_group"
    logger.warning(f"Unknown entity type for rules: {type(entity)}")
    return "unknown"

def _get_relationship_entity_type_enum(entity: Any) -> Optional[RelationshipEntityType]:
    if isinstance(entity, Player): return RelationshipEntityType.PLAYER
    if isinstance(entity, GeneratedNpc): return RelationshipEntityType.GENERATED_NPC
    if isinstance(entity, GlobalNpc): return RelationshipEntityType.GLOBAL_NPC # Assuming this enum member exists
    if isinstance(entity, MobileGroup): return RelationshipEntityType.MOBILE_GROUP # Assuming this enum member exists
    # Factions would need specific handling if GEs interact with them directly
    return None

async def _choose_reaction_action(
    session: AsyncSession, guild_id: int,
    actor: Union[GlobalNpc, MobileGroup], target: Any,
    reaction_rule: Dict[str, Any], relationship_value: Optional[int]
) -> Optional[str]:
    actor_properties = actor.properties_json or {}
    actions_to_consider = []

    if relationship_value is not None and "relationship_thresholds" in reaction_rule:
        for threshold_rule in reaction_rule["relationship_thresholds"]:
            value = threshold_rule.get("value")
            if value is None: continue
            met = False
            if threshold_rule.get("threshold_type") == "hostile_if_below" and relationship_value < value: met = True
            elif threshold_rule.get("threshold_type") == "friendly_if_above" and relationship_value > value: met = True

            if met:
                if "forced_action" in threshold_rule: return threshold_rule["forced_action"]
                actions_to_consider.extend(threshold_rule.get("action_weights", []))
                break

    if not actions_to_consider and "default_actions" in reaction_rule:
        actions_to_consider.extend(reaction_rule["default_actions"])

    if not actions_to_consider: return None

    valid_actions = [
        aw_entry for aw_entry in actions_to_consider
        if not (req_prop := aw_entry.get("requires_property")) or actor_properties.get(req_prop)
    ]

    if not valid_actions: return None

    total_weight = sum(aw.get("weight", 0) for aw in valid_actions)
    if total_weight <= 0: # Handle if all valid actions have 0 or no weight
        return random.choice(valid_actions).get("action") if valid_actions else None

    roll = random.uniform(0, total_weight)
    current_sum = 0
    for aw_entry in valid_actions:
        current_sum += aw_entry.get("weight", 0)
        if roll <= current_sum:
            return aw_entry.get("action")
    return valid_actions[-1].get("action") if valid_actions else None # Fallback

async def _simulate_entity_interactions(session: AsyncSession, guild_id: int, entity: Union[GlobalNpc, MobileGroup]):
    if not entity.current_location_id: return
    logger.debug(f"Entity {entity.static_id} interaction phase in loc {entity.current_location_id}.")

    other_entities = await _get_entities_in_location(session, guild_id, entity.current_location_id, exclude_entity=entity)
    if not other_entities:
        logger.debug(f"No other entities for {entity.static_id} to interact with in loc {entity.current_location_id}.")
        return

    entity_actor_type_key = _get_entity_type_for_rules(entity)

    for target_entity in other_entities:
        target_entity_type_key = _get_entity_type_for_rules(target_entity)
        target_id_for_log = getattr(target_entity, 'id', 'unknown_id')
        logger.debug(f"{entity.static_id} considering interaction with {target_id_for_log} ({target_entity_type_key}).")

        detection_rule_key = f"global_entity_detection:rules:{entity_actor_type_key}:{target_entity_type_key}"
        detection_rule_result = await get_rule(session, guild_id, detection_rule_key)
        detection_rule = detection_rule_result if detection_rule_result is not None else DEFAULT_DETECTION_RULE


        detected = False
        if detection_rule.get("enabled", False): # type: ignore # detection_rule can be dict
            try:
                actor_rel_type = _get_relationship_entity_type_enum(entity)
                target_rel_type = _get_relationship_entity_type_enum(target_entity)

                if actor_rel_type and target_rel_type:
                    actor_props = entity.properties_json or {}
                    target_props = getattr(target_entity, "properties_json", {}) or {}

                    actor_perception = actor_props.get("perception", 10)
                    target_stealth = target_props.get("stealth", 10)

                    # Ensure parameters match resolve_check signature (assuming it takes these directly or via a details dict)
                    # This part is highly dependent on the actual signature of resolve_check
                    check_result: CheckResultModel = await resolve_check(
                       session, guild_id=guild_id,
                       actor_entity_id=entity.id, actor_entity_type=actor_rel_type,
                       target_entity_id=target_entity.id, target_entity_type=target_rel_type, # type: ignore
                       check_type=str(detection_rule.get("check_type", "perception")), # type: ignore
                       # Assuming resolve_check takes these as specific params or within a details dict
                       # For now, passing them as if they are direct. This might need adjustment.
                       actor_check_modifier=actor_perception, # Example: if resolve_check expects this
                       target_check_modifier=target_stealth,  # Example
                       dc=int(detection_rule.get("base_dc", 10)) # type: ignore
                    )
                    if check_result.outcome == CheckOutcome.SUCCESS: # type: ignore
                       detected = True
                else: # Fallback if types can't be mapped for check resolver
                    logger.warning(f"Cannot resolve relationship types for detection check between {entity_actor_type_key} and {target_entity_type_key}. Assuming detection for rule '{detection_rule_key}'.")
                    detected = True # Fallback to simple rule enabled

            except CheckError as e:
                logger.warning(f"CheckError during detection for {entity.static_id} on target {target_id_for_log}: {e}")
            except Exception as e:
                logger.error(f"Error during detection for {entity.static_id} on target {target_id_for_log}: {e}", exc_info=True)

        if detected:
            log_details_detection = {
                "detector_id": entity.id, "detector_static_id": entity.static_id, "detector_type": entity_actor_type_key,
                "target_id": target_id_for_log, "target_type": target_entity_type_key,
                "location_id": entity.current_location_id, "detection_rule_key": detection_rule_key
            }
            await log_event(session, guild_id, EventType.GLOBAL_ENTITY_DETECTED_ENTITY.value, details_json=log_details_detection) # Use .value

            reaction_rule_key = f"global_entity_reaction:rules:{entity_actor_type_key}:{target_entity_type_key}:default" # Add more situation tags later
            reaction_rule_cfg_result = await get_rule(session, guild_id, reaction_rule_key)
            reaction_rule_cfg = reaction_rule_cfg_result if reaction_rule_cfg_result is not None else DEFAULT_REACTION_RULE


            relationship_val: Optional[int] = None
            actor_rel_type_enum = _get_relationship_entity_type_enum(entity)
            target_rel_type_enum = _get_relationship_entity_type_enum(target_entity)

            if actor_rel_type_enum and target_rel_type_enum:
                try:
                    rel = await crud_relationship.get_relationship_between_entities(
                        session, guild_id=guild_id,
                        entity1_id=entity.id, entity1_type=actor_rel_type_enum,
                        entity2_id=target_entity.id, entity2_type=target_rel_type_enum
                    )
                    if rel: relationship_val = rel.value
                except Exception as e:
                    logger.error(f"Error fetching relationship for reaction between {entity.static_id} and {target_id_for_log}: {e}", exc_info=True)

            chosen_action_key = await _choose_reaction_action(session, guild_id, entity, target_entity, reaction_rule_cfg, relationship_val)
            logger.info(f"Entity {entity.static_id} ({entity_actor_type_key}) chose action '{chosen_action_key}' towards {target_id_for_log} ({target_entity_type_key}) with rel_val {relationship_val}")

            if chosen_action_key:
                action_log_details = {
                    "actor_id": entity.id, "actor_static_id": entity.static_id, "actor_type": entity_actor_type_key,
                    "target_id": target_id_for_log, "target_type": target_entity_type_key,
                    "action_chosen": chosen_action_key, "location_id": entity.current_location_id,
                    "reaction_rule_key": reaction_rule_key, "relationship_value_at_action": relationship_val
                }
                if chosen_action_key == "initiate_combat":
                    if actor_rel_type_enum and target_rel_type_enum:
                        try:
                            participants_for_combat = [
                                {"id": entity.id, "type": actor_rel_type_enum.value, "team": "A"}, # Use .value for string
                                {"id": target_entity.id, "type": target_rel_type_enum.value, "team": "B"}
                            ]
                            # TODO: Expand MobileGroup members into participants list
                            await start_combat(session, guild_id, entity.current_location_id, participants_for_combat)
                            action_log_details["combat_initiated"] = True
                        except Exception as e:
                            logger.error(f"Error starting combat for GE {entity.static_id} vs {target_id_for_log}: {e}", exc_info=True)
                            action_log_details["combat_initiation_error"] = str(e)
                    else:
                        logger.error(f"Cannot initiate combat due to unknown RelationshipEntityType for {entity.static_id} or {target_id_for_log}")

                elif chosen_action_key.startswith("initiate_dialogue_"):
                    dialogue_type = chosen_action_key.split("_")[-1]
                    action_log_details["dialogue_type"] = dialogue_type
                    await log_event(
                        session, guild_id, EventType.GE_TRIGGERED_DIALOGUE_PLACEHOLDER.value, # Use .value
                        details_json={**action_log_details, "message": f"GE {entity.static_id} would start '{dialogue_type}' dialogue with {target_id_for_log}."}
                    )

                await log_event(session, guild_id, EventType.GLOBAL_ENTITY_ACTION.value, details_json=action_log_details) # Use .value
                # For simplicity, one significant interaction per GE per tick.
                # If GE takes a major action (combat, dialogue), it might not interact with others this tick.
                if chosen_action_key not in ["log_and_observe", "ignore"]: # Example: stop after major action
                     break
        # End if detected
    # End for target_entity loop
# End _simulate_entity_interactions

logger.info("Global Entity Manager module (re)loaded.")

# Need to ensure CRUDs have get_multi_by_guild_id_active and get_multi_by_location_id
# Example for global_npc_crud (in src/core/crud/crud_global_npc.py)
# async def get_multi_by_guild_id_active(self, session: AsyncSession, *, guild_id: int, skip: int = 0, limit: int = 100) -> List[GlobalNpc]:
#     # Placeholder: Assumes all are active or needs properties_json filter
#     return await self.get_multi_by_attribute(session, guild_id=guild_id, skip=skip, limit=limit)
#
# async def get_multi_by_location_id(self, session: AsyncSession, *, guild_id: int, location_id: int, skip: int = 0, limit: int = 100) -> List[GlobalNpc]:
#     return await self.get_multi_by_attribute(session, guild_id=guild_id, current_location_id=location_id, skip=skip, limit=limit)

# Similar for mobile_group_crud, player_crud, generated_npc_crud

# Add RelationshipEntityType.GLOBAL_NPC and RelationshipEntityType.MOBILE_GROUP if missing
# In src/models/enums.py:
# class RelationshipEntityType(enum.Enum):
#     PLAYER = "player"
#     PARTY = "party"
#     GENERATED_NPC = "generated_npc"
#     GENERATED_FACTION = "generated_faction"
#     GLOBAL_NPC = "global_npc"        # Added
#     MOBILE_GROUP = "mobile_group"    # Added
#     LOCATION = "location"            # If GEs can have relationships with locations
#     ITEM = "item"                    # If GEs can have relationships with items (less common)

# Note: The `_active` methods are simplified here. A robust implementation might involve
# checking a status field in `properties_json` like `{"status": "active"}`.
# For now, `get_multi_by_guild_id` is used as a stand-in.
# Also RelationshipEntityType needs GLOBAL_NPC and MOBILE_GROUP. I'll assume they exist or add them separately.

# Final small fix for _determine_next_location_id, ensure props is always a dict
# In _determine_next_location_id:
# props = entity.properties_json if entity.properties_json is not None else {}
# This is already handled by `entity.properties_json or {}` but good to be mindful.
# The `entity.properties_json = new_props` line is critical for state persistence.
# Route index update should also use `entity.properties_json = new_props`
# to ensure SQLAlchemy detects the change to the mutable JSON.
# Corrected in the main code block.
