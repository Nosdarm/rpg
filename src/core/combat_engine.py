from typing import Optional, List, Dict, Any, Union
import logging
import datetime # Moved import to the top

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.combat_encounter import CombatEncounter
from src.models.combat_outcomes import CombatActionResult
from src.models.player import Player
from src.models.generated_npc import GeneratedNpc
from src.models.enums import EventType, RelationshipEntityType # Assuming actor_type will align with RelationshipEntityType
from src.core.crud import player_crud, npc_crud # Assuming npc_crud exists or will be created
from src.core.crud.crud_combat_encounter import combat_encounter_crud # Assuming this will be created
from src.core.rules import get_rule # For fetching combat rules
from src.core.check_resolver import resolve_check, CheckResult # For skill checks/attacks
from src.core.game_events import log_event # For logging combat events

logger = logging.getLogger(__name__)

async def process_combat_action(
    guild_id: int,
    session: AsyncSession,
    combat_instance_id: int,
    actor_id: int,
    actor_type_str: str, # "player" or "npc" (or align with RelationshipEntityType)
    action_data: Dict[str, Any] # e.g., {"action_type": "attack", "target_id": 123, "ability_id": 1}
) -> CombatActionResult:
    """
    Processes a single action taken by an actor within a specific combat encounter.
    """
    try:
        # 1. Load Data
        combat_encounter = await combat_encounter_crud.get(session, id=combat_instance_id)
        if not combat_encounter or combat_encounter.guild_id != guild_id:
            logger.error(f"CombatEncounter not found or guild_id mismatch for id {combat_instance_id}, guild {guild_id}")
            # Consider a more specific error result or raising an exception
            return CombatActionResult(success=False, action_type=action_data.get("action_type", "unknown"), actor_id=actor_id, actor_type=actor_type_str, description_i18n={"en": "Combat encounter not found."})

        actor: Union[Player, GeneratedNpc, None] = None
        actor_relationship_type: Optional[RelationshipEntityType] = None

        if actor_type_str.lower() == RelationshipEntityType.PLAYER.value:
            actor = await player_crud.get_by_id_and_guild(session, id=actor_id, guild_id=guild_id)
            actor_relationship_type = RelationshipEntityType.PLAYER
        elif actor_type_str.lower() == RelationshipEntityType.GENERATED_NPC.value:
            actor = await npc_crud.get_by_id_and_guild(session, id=actor_id, guild_id=guild_id) # Assuming npc_crud has this method
            actor_relationship_type = RelationshipEntityType.GENERATED_NPC
        else:
            logger.error(f"Unsupported actor_type: {actor_type_str} for actor_id {actor_id}")
            return CombatActionResult(success=False, action_type=action_data.get("action_type", "unknown"), actor_id=actor_id, actor_type=actor_type_str, description_i18n={"en": "Invalid actor type."})

        if not actor:
            logger.error(f"Actor {actor_type_str} with id {actor_id} not found in guild {guild_id}")
            return CombatActionResult(success=False, action_type=action_data.get("action_type", "unknown"), actor_id=actor_id, actor_type=actor_type_str, description_i18n={"en": "Actor not found."})

        # Participant data from combat_encounter.participants_json
        # Structure assumption: {"entities": [{"id": 123, "type": "player", "current_hp": 80, ...}]}
        participants_data = combat_encounter.participants_json.get("entities", []) if combat_encounter.participants_json else []
        actor_participant_data = next((p for p in participants_data if p.get("id") == actor_id and p.get("type") == actor_type_str.lower()), None)

        if not actor_participant_data:
            logger.error(f"Actor {actor_type_str} id {actor_id} not found in combat participants list for combat {combat_instance_id}")
            return CombatActionResult(success=False, action_type=action_data.get("action_type", "unknown"), actor_id=actor_id, actor_type=actor_type_str, description_i18n={"en": "Actor not found in combat."})

        # Target loading (if any)
        target_id = action_data.get("target_id")
        target_participant_data = None
        target_entity: Union[Player, GeneratedNpc, None] = None # For fetching base stats if needed outside participant_json

        if target_id:
            # Find target in participant list first. Type might not be in action_data, infer from participants.
            potential_targets = [p for p in participants_data if p.get("id") == target_id]
            if not potential_targets:
                logger.error(f"Target with id {target_id} not found in combat participants list.")
                return CombatActionResult(success=False, action_type=action_data.get("action_type", "unknown"), actor_id=actor_id, actor_type=actor_type_str, target_id=target_id, description_i18n={"en": "Target not found in combat."})
            # TODO: Handle multiple entities with same ID but different types if that's possible, or ensure IDs are unique across types in a combat.
            # For now, assume first found is the one. A `target_type` in action_data would be more robust.
            target_participant_data = potential_targets[0]
            target_type_str = target_participant_data.get("type")

            if target_type_str == RelationshipEntityType.PLAYER.value:
                target_entity = await player_crud.get_by_id_and_guild(session, id=target_id, guild_id=guild_id)
            elif target_type_str == RelationshipEntityType.GENERATED_NPC.value:
                target_entity = await npc_crud.get_by_id_and_guild(session, id=target_id, guild_id=guild_id)

            if not target_entity and target_participant_data: # If entity not in DB but was in participants
                 logger.warning(f"Target entity {target_type_str} id {target_id} found in participants_json but not in DB for guild {guild_id}.")
            elif not target_participant_data: # Should have been caught earlier
                 return CombatActionResult(success=False, action_type=action_data.get("action_type", "unknown"), actor_id=actor_id, actor_type=actor_type_str, target_id=target_id, description_i18n={"en": "Target not found."})


        # 2. Determine Rules
        # Prioritize rules from combat_encounter.rules_config_snapshot_json
        # Fallback to RuleConfig for the guild
        combat_rules = {}
        if combat_encounter.rules_config_snapshot_json:
            combat_rules.update(combat_encounter.rules_config_snapshot_json)

        # Example: Fetch a specific rule, e.g., for attack calculations
        # attack_roll_dice_rule = await get_rule(session, guild_id, "combat_attack_roll_dice", "1d20")
        # base_damage_rule = await get_rule(session, guild_id, "combat_base_damage_weapon_default", "1d6")
        # crit_multiplier_rule = await get_rule(session, guild_id, "combat_crit_multiplier", 2)

        # TODO: More sophisticated rule loading based on action_data.get("action_type")

        # 3. Action Processing Logic (MVP for "attack")
        action_type = action_data.get("action_type", "unknown_action")

        if action_type == "attack":
            if not target_participant_data or not target_id: # target_id check redundant if target_participant_data exists
                logger.warning(f"Attack action by {actor_id} missing target in combat {combat_instance_id}.")
                return CombatActionResult(success=False, action_type=action_type, actor_id=actor_id, actor_type=actor_type_str, description_i18n={"en": "Attack target not specified or found."})

            # TODO: TASK_EFFECTIVE_STATS - Placeholder for Effective_Stats System
            # The following stat retrievals are placeholders. A proper Effective_Stats system
            # (potentially from another task, e.g., related to player/NPC models or a dedicated stats module)
            # should be integrated here. This system would calculate stats based on base values,
            # equipment, status effects, abilities, etc.
            # For MVP, we assume that `participants_json` within CombatEncounter is populated
            # with necessary combat-relevant stats like 'attack_power', 'defense', 'current_hp'.
            # These stats might be snapshots taken at combat start or dynamically updated.

            # Example of how stats might be fetched (currently commented out as they are not used in the fixed damage MVP):
            # actor_attack_power = actor_participant_data.get("attack_power", 10) # Default to 10 if not found
            # target_defense = target_participant_data.get("defense", 5) # Default to 5 if not found

            actor_current_hp = actor_participant_data.get("current_hp", 0)
            target_current_hp = target_participant_data.get("current_hp", 0)

            # --- Check Phase (Example for attack roll) ---
            # Rule: "combat_attack_check_dc_base", default 10
            # Rule: "combat_attack_check_attribute_actor", default "strength" (need to get this from actor)
            # Rule: "combat_attack_check_attribute_target", default "dexterity" (for AC calculation, if any)

            # For MVP, let's assume a simple check against a fixed DC or a target attribute.
            # This part heavily relies on CheckResolver (Task 6.3.2) and RuleConfig structure.
            # Example:
            # check_dc = await get_rule(session, guild_id, "combat_attack_dc_vs_npc", 12) # Simplified DC
            # attack_check_type = await get_rule(session, guild_id, "combat_attack_check_type", "melee_attack")

            # For now, let's simulate a always hit scenario for MVP attack, or a very simple check.
            # check_outcome: Optional[CheckResult] = await resolve_check(
            #     db=session,
            #     guild_id=guild_id,
            #     check_type=attack_check_type, # e.g., "melee_attack"
            #     performing_entity_id=actor_id,
            #     performing_entity_type=actor_relationship_type,
            #     # target_entity_id=target_id, # Optional, if DC depends on target
            #     # target_entity_type=target_type_str, # Optional
            #     difficulty_class=check_dc,
            #     # context_modifiers=[...] # Optional
            # )

            # Simplified check for MVP:
            simulated_check_success = True # Assume hit for now
            simulated_check_result_dict = {"roll": 15, "dc": 10, "success": True} # Mocked check_resolver.CheckResult

            if simulated_check_success:
                # --- Calculation Phase ---
                # Rule: "combat_attack_base_damage_formula", default "1d6"
                # Rule: "combat_attack_damage_attribute_modifier", default "strength"
                # damage_formula = await get_rule(session, guild_id, "combat_attack_base_damage_formula", "1d4")
                # For MVP, let's use a fixed damage or simple random.
                damage = 5 # Fixed damage for MVP

                target_new_hp = target_current_hp - damage

                # Update participant_json (in memory for now, will be saved later)
                for p_idx, p_data in enumerate(participants_data):
                    if p_data.get("id") == target_id and p_data.get("type") == target_participant_data.get("type"):
                        participants_data[p_idx]["current_hp"] = target_new_hp
                        break

                # Determine actor and target names correctly
                actor_name = actor.name if isinstance(actor, Player) else actor.name_i18n.get("en", "Unknown Actor")
                target_name = "target" # default
                if target_entity:
                    target_name = target_entity.name if isinstance(target_entity, Player) else target_entity.name_i18n.get("en", "Unknown Target")
                elif target_participant_data: # Fallback if target_entity DB load failed but was in participants
                    target_name = target_participant_data.get("name", "target") # Assuming name might be in participant_json

                action_result = CombatActionResult(
                    success=True,
                    action_type=action_type,
                    actor_id=actor_id,
                    actor_type=actor_type_str,
                    target_id=target_id,
                    target_type=target_participant_data.get("type"),
                    damage_dealt=damage,
                    check_result=simulated_check_result_dict,
                    description_i18n={"en": f"{actor_name} attacks {target_name} for {damage} damage!"}
                )
            else: # Missed
                actor_name = actor.name if isinstance(actor, Player) else actor.name_i18n.get("en", "Unknown Actor")
                target_name = "target"
                if target_entity:
                    target_name = target_entity.name if isinstance(target_entity, Player) else target_entity.name_i18n.get("en", "Unknown Target")
                elif target_participant_data:
                    target_name = target_participant_data.get("name", "target")

                action_result = CombatActionResult(
                    success=False, # Or True if a "miss" is a successful resolution of an attempt
                    action_type=action_type,
                    actor_id=actor_id,
                    actor_type=actor_type_str,
                    target_id=target_id,
                    target_type=target_participant_data.get("type"),
                    check_result=simulated_check_result_dict,
                    description_i18n={"en": f"{actor_name} attacks {target_name} but misses!"}
                )

        else: # Fallback for unknown action_type
            logger.warning(f"Unknown action_type '{action_type}' received in combat {combat_instance_id}")
            return CombatActionResult(success=False, action_type=action_type, actor_id=actor_id, actor_type=actor_type_str, description_i18n={"en": f"Unknown action: {action_type}"})

        # 4. Update State (DB)
        combat_encounter.participants_json = {"entities": participants_data} # Update with modified list

        # Update combat_log_json
        new_log_entry = {
            "actor_id": actor_id,
            "actor_type": actor_type_str,
            "action_type": action_result.action_type,
            "target_id": action_result.target_id,
            "target_type": action_result.target_type,
            "success": action_result.success,
            "damage_dealt": action_result.damage_dealt,
            "healing_done": action_result.healing_done,
            "description": action_result.description_i18n.get("en") if action_result.description_i18n else "Action occurred.",
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat() # Updated to use timezone-aware UTC now
        }
        if combat_encounter.combat_log_json and "entries" in combat_encounter.combat_log_json:
            combat_encounter.combat_log_json["entries"].append(new_log_entry)
        else:
            combat_encounter.combat_log_json = {"entries": [new_log_entry]}

        session.add(combat_encounter)
        # Note: commit is typically handled by the caller (e.g., Combat Cycle or Action Processor)
        # await session.commit() # Usually not here

        # 5. Logging (Game Event Log - StoryLog)
        event_details = {
            "combat_id": combat_instance_id,
            "action_result": action_result.model_dump(exclude_none=True)
        }
        await log_event(
            session=session,
            guild_id=guild_id,
            event_type=EventType.COMBAT_ACTION, # Or a more specific type if available
            details_json=event_details,
            location_id=combat_encounter.location_id,
            # Entity IDs involved in this specific action
            entity_ids_json={"players": [actor_id] if actor_relationship_type == RelationshipEntityType.PLAYER else [],
                             "npcs": [actor_id] if actor_relationship_type == RelationshipEntityType.GENERATED_NPC else []}
                             # TODO: Add target entities to entity_ids_json
        )

        return action_result

    except Exception as e:
        logger.exception(f"Error processing combat action for combat {combat_instance_id}, actor {actor_id}: {e}")
        # Fallback error response
        return CombatActionResult(
            success=False,
            action_type=action_data.get("action_type", "unknown_error"),
            actor_id=actor_id,
            actor_type=actor_type_str,
            description_i18n={"en": "An internal error occurred while processing the combat action."}
        )

# Need to ensure npc_crud and combat_encounter_crud are available.
# For now, this is a structural setup. Implementation of specific actions like "cast_spell", "use_item" etc.
# and detailed rule integration will follow.
