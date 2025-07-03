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
from src.core.check_resolver import resolve_check, CheckResult, CheckError # For skill checks/attacks
from src.core.game_events import log_event # For logging combat events
from src.core.dice_roller import roll_dice # For parsing damage formulas

logger = logging.getLogger(__name__)

async def _get_combat_rule(
    session: AsyncSession,
    guild_id: int,
    rule_key: str,
    default_value: Any,
    snapshot_rules: Optional[Dict[str, Any]]
) -> Any:
    """Helper to fetch a rule, prioritizing snapshot then RuleConfig."""
    if snapshot_rules and rule_key in snapshot_rules:
        # Ensure that if a rule is explicitly null in snapshot, it's treated as such,
        # not falling back to default unless that's the desired behavior for 'null'.
        # For now, if key exists, use its value.
        return snapshot_rules[rule_key]
    return await get_rule(session, guild_id, rule_key, default_value)

async def _get_participant_stat(
    session: AsyncSession,
    guild_id: int,
    participant_data: Dict[str, Any],
    base_entity: Union[Player, GeneratedNpc],
    stat_name: str,
    default_value: Any,
    snapshot_rules: Optional[Dict[str, Any]]
) -> Any:
    # 1. Check participant_data (live combat state)
    if stat_name in participant_data:
        return participant_data[stat_name]

    # 2. Fallback to base_entity model
    if isinstance(base_entity, GeneratedNpc) and base_entity.properties_json and "stats" in base_entity.properties_json:
        if stat_name in base_entity.properties_json["stats"]:
            return base_entity.properties_json["stats"][stat_name]

    if hasattr(base_entity, stat_name): # For direct attributes like Player.level
        return getattr(base_entity, stat_name)

    # 3. Special handling for "modifiers" if the stat_name requests one directly
    if stat_name.endswith("_modifier"):
        base_stat_name = stat_name.replace("_modifier", "")
        # Need to prevent infinite recursion if base_stat_name itself ends up calling for _modifier
        # This recursive call for base_stat_value should fetch the raw stat.
        base_stat_value = await _get_participant_stat(
            session, guild_id, participant_data, base_entity,
            base_stat_name, 10, # Default base stat value if not found
            snapshot_rules
        )
        if isinstance(base_stat_value, int):
            return await _calculate_attribute_modifier(session, guild_id, base_stat_value, base_stat_name, snapshot_rules)
        else:
            logger.warning(f"Could not find base stat '{base_stat_name}' to calculate modifier '{stat_name}' for entity {participant_data.get('type')}:{participant_data.get('id')}. Defaulting modifier to 0.")
            return 0

    logger.warning(f"Stat '{stat_name}' not found for entity {participant_data.get('type')}:{participant_data.get('id')} (name: {base_entity.name if isinstance(base_entity, Player) else base_entity.name_i18n.get('en', 'Unknown')}). Returning default: {default_value}")
    return default_value

async def _calculate_attribute_modifier(
    session: AsyncSession,
    guild_id: int,
    base_attribute_value: int,
    attribute_name: str, # e.g. "strength"
    snapshot_rules: Optional[Dict[str, Any]]
) -> int:
    """Calculates modifier from a base attribute value based on RuleConfig formula."""
    formula_key = f"combat:attributes:{attribute_name}:modifier_formula"
    # Example formula: "(value - 10) // 2"
    # More complex formulas could use 'eval' with a safe context, or a dedicated parser.
    # For MVP, we'll support a simple "(value - X) // Y" or direct if formula is "value"
    modifier_formula = await _get_combat_rule(session, guild_id, formula_key, "(value - 10) // 2", snapshot_rules)

    if modifier_formula == "value": # Means the base_attribute_value is already the modifier
        return base_attribute_value

    # Basic parsing for "(value - X) // Y"
    # This is a simplified parser; a more robust solution might be needed for complex formulas.
    import re
    match = re.match(r"\(value\s*-\s*(\d+)\)\s*//\s*(\d+)", modifier_formula)
    if match:
        x = int(match.group(1))
        y = int(match.group(2))
        if y == 0: return 0 # Avoid division by zero
        return (base_attribute_value - x) // y
    else:
        logger.warning(f"Unsupported modifier formula '{modifier_formula}' for attribute '{attribute_name}'. Defaulting to 0.")
        return 0


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
        combat_encounter = await combat_encounter_crud.get(session, id=combat_instance_id, guild_id=guild_id)
        if not combat_encounter: # guild_id check is now part of the query
            logger.error(f"CombatEncounter not found for id {combat_instance_id} in guild {guild_id}")
            return CombatActionResult(success=False, action_type=action_data.get("action_type", "unknown"), actor_id=actor_id, actor_type=actor_type_str, description_i18n={"en": f"Combat encounter {combat_instance_id} not found."})

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
            target_type_str = target_participant_data.get("type") # This is the type from participants_json

            if not target_type_str:
                logger.error(f"Target with id {target_id} found in participants_json but 'type' field is missing.")
                return CombatActionResult(success=False, action_type=action_data.get("action_type", "unknown"), actor_id=actor_id, actor_type=actor_type_str, target_id=target_id, description_i18n={"en": "Target data corrupted in combat."})

            if target_type_str.lower() == RelationshipEntityType.PLAYER.value:
                target_entity = await player_crud.get_by_id_and_guild(session, id=target_id, guild_id=guild_id)
            elif target_type_str.lower() == RelationshipEntityType.GENERATED_NPC.value:
                target_entity = await npc_crud.get_by_id_and_guild(session, id=target_id, guild_id=guild_id)
            else:
                logger.warning(f"Unsupported target_type '{target_type_str}' found in participants_json for target_id {target_id}.")
                # Depending on strictness, could return error here. For now, allow proceeding if target_entity is not strictly needed.
                # target_entity will remain None.

            if not target_entity and target_participant_data: # If entity not in DB but was in participants
                 logger.warning(f"Target entity {target_type_str} id {target_id} found in participants_json but not in DB for guild {guild_id}.")
            # The case of not target_participant_data was already handled by the check for potential_targets.


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

        # 2. Determine Rules
        snapshot_rules = combat_encounter.rules_config_snapshot_json
        action_type = action_data.get("action_type", "unknown_action").lower()


        # Rule keys for the current action_type
        # These keys are dynamically generated based on the action_type
        # Example for "attack": "combat:actions:attack:check_type"
        # Example for "power_strike": "combat:actions:power_strike:check_type"

        action_rules_prefix = f"combat:actions:{action_type}"

        check_type_key = f"{action_rules_prefix}:check_type"
        # dice_notation_for_check_key = f"{action_rules_prefix}:dice_notation_for_check" # Used by check_resolver if not overridden
        actor_attribute_for_check_key = f"{action_rules_prefix}:actor_attribute_for_check" # e.g., "strength"

        dc_base_key = f"{action_rules_prefix}:dc_base"
        dc_target_attribute_for_modifier_key = f"{action_rules_prefix}:dc_target_attribute_for_modifier" # e.g., "dexterity"

        damage_formula_key = f"{action_rules_prefix}:damage_formula" # e.g., "1d8+@actor_strength_modifier"
        actor_attribute_for_damage_key = f"{action_rules_prefix}:actor_attribute_for_damage" # e.g. "strength"

        crit_natural_threshold_key = "combat:critical_hit:threshold:natural"
        crit_damage_multiplier_key = "combat:critical_hit:damage_multiplier"

        # Fetching rules using the helper
        resolved_check_type = await _get_combat_rule(session, guild_id, check_type_key, "default_attack_check", snapshot_rules)
        # resolved_dice_notation_for_check = await _get_combat_rule(session, guild_id, dice_notation_for_check_key, "1d20", snapshot_rules) # check_resolver also has defaults
        resolved_actor_attribute_for_check = await _get_combat_rule(session, guild_id, actor_attribute_for_check_key, "strength", snapshot_rules)

        resolved_dc_base = await _get_combat_rule(session, guild_id, dc_base_key, 10, snapshot_rules)
        resolved_dc_target_attribute = await _get_combat_rule(session, guild_id, dc_target_attribute_for_modifier_key, "dexterity", snapshot_rules)

        resolved_damage_formula = await _get_combat_rule(session, guild_id, damage_formula_key, "1d4", snapshot_rules)
        resolved_actor_attribute_for_damage = await _get_combat_rule(session, guild_id, actor_attribute_for_damage_key, "strength", snapshot_rules)

        resolved_crit_natural_threshold = await _get_combat_rule(session, guild_id, crit_natural_threshold_key, 20, snapshot_rules)
        resolved_crit_damage_multiplier = await _get_combat_rule(session, guild_id, crit_damage_multiplier_key, 2.0, snapshot_rules)

        active_rules_for_action = {
            check_type_key: resolved_check_type,
            # dice_notation_for_check_key: resolved_dice_notation_for_check,
            actor_attribute_for_check_key: resolved_actor_attribute_for_check,
            dc_base_key: resolved_dc_base,
            dc_target_attribute_for_modifier_key: resolved_dc_target_attribute,
            damage_formula_key: resolved_damage_formula,
            actor_attribute_for_damage_key: resolved_actor_attribute_for_damage,
            crit_natural_threshold_key: resolved_crit_natural_threshold,
            crit_damage_multiplier_key: resolved_crit_damage_multiplier,
        }
        logger.debug(f"Active rules for action '{action_type}': {active_rules_for_action}")

        # 3. Action Processing Logic
        if action_type == "attack": # This can be expanded to a dictionary mapping action_type to handler functions
            if not target_participant_data or not target_id:
                logger.warning(f"Attack action by actor {actor_id} missing target in combat {combat_instance_id}.")
                return CombatActionResult(success=False, action_type=action_type, actor_id=actor_id, actor_type=actor_type_str, description_i18n={"en": "Attack target not specified or found."})

            # --- Effective Stats / Attribute Fetching ---
            # Actor's attribute for the check (e.g., strength)
            # This is used by resolve_check internally based on the 'base_attribute_name' for the check_type
            # Target's attribute for DC calculation (e.g., dexterity)
            target_base_attribute_for_dc_value = await _get_participant_stat(
                session, guild_id, target_participant_data, target_entity,
                resolved_dc_target_attribute, 10, snapshot_rules
            )
            if not isinstance(target_base_attribute_for_dc_value, int):
                logger.error(f"Could not retrieve valid base attribute '{resolved_dc_target_attribute}' for target {target_id} for DC calculation. Defaulting to 10.")
                target_base_attribute_for_dc_value = 10

            target_dc_attribute_modifier = await _calculate_attribute_modifier(
                session, guild_id, target_base_attribute_for_dc_value,
                resolved_dc_target_attribute, snapshot_rules
            )

            calculated_dc = resolved_dc_base + target_dc_attribute_modifier
            logger.debug(f"Calculated DC for attack: {calculated_dc} (Base: {resolved_dc_base}, Target Mod ({resolved_dc_target_attribute}): {target_dc_attribute_modifier})")

            # --- Check Resolution ---
            # resolve_check will use its own logic to fetch actor's attribute for the check (resolved_actor_attribute_for_check)
            # and calculate the modifier using its internal _get_entity_attribute and potentially a rule for modifier calculation.
            logger.debug(f"Calling resolve_check for '{resolved_check_type}' by {actor_type_str}:{actor_id} (attr: {resolved_actor_attribute_for_check}) vs target {target_participant_data.get('type')}:{target_id} with DC {calculated_dc}")

            try:
                attack_check_result: CheckResult = await resolve_check(
                    db=session,
                    guild_id=guild_id,
                    check_type=resolved_check_type, # This tells resolve_check which rules to use for dice, base_attr etc.
                    entity_doing_check_id=actor_id,
                    entity_doing_check_type=actor_relationship_type.value,
                    target_entity_id=target_id,
                    target_entity_type=target_participant_data.get("type"),
                    difficulty_dc=calculated_dc,
                    # check_context can pass situational modifiers if any: e.g. {"situational_bonus": 2}
                )
            except CheckError as e:
                logger.error(f"CheckError during combat action '{action_type}': {e}")
                return CombatActionResult(success=False, action_type=action_type, actor_id=actor_id, actor_type=actor_type_str, description_i18n={"en": f"Error during check: {e}"})
            except Exception as e: # Catch other unexpected errors from resolve_check
                logger.exception(f"Unexpected error during resolve_check for action '{action_type}': {e}")
                return CombatActionResult(success=False, action_type=action_type, actor_id=actor_id, actor_type=actor_type_str, description_i18n={"en": "Internal error during check resolution."})


            # --- Damage Calculation ---
            actual_damage = 0
            if attack_check_result.outcome.status in ["success", "critical_success"]:
                # Actor's attribute for damage (e.g., strength)
                actor_base_attribute_for_damage_value = await _get_participant_stat(
                    session, guild_id, actor_participant_data, actor,
                    resolved_actor_attribute_for_damage, 10, snapshot_rules # Default base stat 10
                )
                if not isinstance(actor_base_attribute_for_damage_value, int):
                    logger.warning(f"Could not get valid damage attribute '{resolved_actor_attribute_for_damage}' for actor {actor_id}. Defaulting to 10 for modifier calc.")
                    actor_base_attribute_for_damage_value = 10

                actor_damage_modifier = await _calculate_attribute_modifier(
                    session, guild_id, actor_base_attribute_for_damage_value,
                    resolved_actor_attribute_for_damage, snapshot_rules
                )
                logger.debug(f"Actor {actor_id} damage attribute '{resolved_actor_attribute_for_damage}' base value: {actor_base_attribute_for_damage_value}, modifier: {actor_damage_modifier}")

                raw_damage_formula = resolved_damage_formula

                # Replace @actor_attribute_modifier placeholder.
                # This is a simple placeholder. More complex formulas might need a dedicated parser.
                # E.g. @actor_strength_modifier, @actor_dexterity_modifier
                formula_placeholder = f"@actor_{resolved_actor_attribute_for_damage}_modifier"
                formula_to_roll = raw_damage_formula.replace(formula_placeholder, str(actor_damage_modifier))

                try:
                    base_damage_roll, _ = roll_dice(formula_to_roll)
                    actual_damage = base_damage_roll
                    logger.debug(f"Damage roll for formula '{formula_to_roll}' (original: '{raw_damage_formula}') -> {base_damage_roll}")
                except ValueError as e:
                    logger.error(f"Error rolling damage dice for formula '{formula_to_roll}' (original: '{raw_damage_formula}'): {e}. Defaulting damage to 1.")
                    actual_damage = 1

                if attack_check_result.outcome.status == "critical_success":
                    crit_multiplier = resolved_crit_damage_multiplier
                    # Crit logic: Could be multiplier, max dice, extra dice etc.
                    # For multiplier:
                    actual_damage = int(actual_damage * crit_multiplier)
                    logger.debug(f"Critical hit! Damage multiplied by {crit_multiplier} to {actual_damage}")
                    # TODO: Add rule for "max_dice_on_crit" or "extra_dice_on_crit" for more TTRPG-like crits

                actual_damage = max(0, actual_damage) # Ensure damage is not negative

                target_current_hp = await _get_participant_stat(session, guild_id, target_participant_data, target_entity, "current_hp", 0, snapshot_rules)
                target_new_hp = target_current_hp - actual_damage

                for p_idx, p_data in enumerate(participants_data):
                    if p_data.get("id") == target_id and p_data.get("type") == target_participant_data.get("type"):
                        participants_data[p_idx]["current_hp"] = target_new_hp
                        logger.debug(f"Target {target_id} HP updated from {target_current_hp} to {target_new_hp}")
                        break

            actor_name = actor.name if isinstance(actor, Player) else actor.name_i18n.get("en", actor.static_id or f"NPC {actor.id}")
            target_name = "target" # default
            if target_entity: # target_entity is the model instance
                target_name = target_entity.name if isinstance(target_entity, Player) else target_entity.name_i18n.get("en", target_entity.static_id or f"NPC {target_entity.id}")
            elif target_participant_data: # Fallback to name from participant JSON if DB load failed
                target_name = target_participant_data.get("name", f"Entity {target_id}")


            outcome_description = f"{actor_name} attacks {target_name}. "
            if attack_check_result.outcome.status == "critical_success":
                outcome_description += f"CRITICAL HIT! Deals {actual_damage} damage."
            elif attack_check_result.outcome.status == "success":
                outcome_description += f"Hits and deals {actual_damage} damage."
            elif attack_check_result.outcome.status == "critical_failure":
                outcome_description += "CRITICAL MISS!"
            else: # failure
                outcome_description += "Misses."


            # --- Status Effect Application (Placeholder) ---
            status_effects_applied_list = []
            # Example Rule: f"{action_rules_prefix}:on_hit_apply_status" -> {"status_static_id": "bleeding", "chance": 0.25, "duration": 3, "save_dc_attribute": "constitution"}
            # on_hit_status_rule = await _get_combat_rule(session, guild_id, f"{action_rules_prefix}:on_hit_apply_status", None, snapshot_rules)
            # if on_hit_status_rule and attack_check_result.outcome.status in ["success", "critical_success"]:
            #     # Complex logic here:
            #     # 1. Check 'chance' if present.
            #     # 2. If status requires a save:
            #     #    target_save_attribute = on_hit_status_rule.get("save_attribute", "constitution")
            #     #    save_dc = await _get_combat_rule(session, guild_id, f"combat:status_effects:{on_hit_status_rule['status_static_id']}:save_dc_base", 10, snapshot_rules) + actor_spellcasting_modifier (example)
            #     #    saving_throw_result = await resolve_check(db=session, guild_id=guild_id, check_type="saving_throw", entity_doing_check_id=target_id, ...)
            #     #    if saving_throw_result.outcome.status not in ["success", "critical_success"]:
            #     #        # Apply status
            #     # 3. If auto-apply or save failed:
            #     #    status_def = await _get_combat_rule(session, guild_id, f"combat:status_effects:{on_hit_status_rule['status_static_id']}:definition", {}, snapshot_rules)
            #     #    status_to_apply = { "static_id": on_hit_status_rule['status_static_id'], "duration": on_hit_status_rule.get('duration', 3), ... }
            #     #    status_effects_applied_list.append(status_to_apply)
            #     #    # Update target_participant_data['status_effects']
            #     pass # End of placeholder status effect block

            # --- Resource Costs (Placeholder) ---
            costs_paid_list = []
            # Example Rule: f"{action_rules_prefix}:resource_cost" -> {"resource_name": "stamina", "amount": 1}
            # resource_cost_rule = await _get_combat_rule(session, guild_id, f"{action_rules_prefix}:resource_cost", None, snapshot_rules)
            # if resource_cost_rule:
            #     # 1. Check if actor has enough resources (this should ideally be done *before* executing the action)
            #     #    current_resource = await _get_participant_stat(...)
            #     #    if current_resource < resource_cost_rule['amount']: return ActionResult indicating failure
            #     # 2. Deduct resource from actor_participant_data
            #     # 3. Add to costs_paid_list
            #     pass # End of placeholder resource cost block


            action_result = CombatActionResult(
                success=attack_check_result.outcome.status in ["success", "critical_success"],
                action_type=action_type,
                actor_id=actor_id,
                actor_type=actor_type_str,
                target_id=target_id,
                target_type=target_participant_data.get("type"),
                damage_dealt=actual_damage if actual_damage > 0 else None,
                check_result=attack_check_result,
                status_effects_applied=status_effects_applied_list if status_effects_applied_list else None,
                costs_paid=costs_paid_list if costs_paid_list else None,
                description_i18n={"en": outcome_description},
                additional_details=active_rules_for_action # Log the rules used
            )

        # TODO: Implement other action types like "cast_spell", "use_item", "defend"
        # elif action_type == "cast_spell":
        #     # ... similar logic for spell effects, checks (e.g., spell attack roll or target saving throw), resource costs ...
        #     pass

        else: # Fallback for unknown or not-yet-implemented action_type
            logger.warning(f"Unknown or not implemented action_type '{action_type}' received in combat {combat_instance_id}")
            # Try to get a generic description if possible for the action_type from rules
            generic_action_desc_key = f"combat:actions:{action_type}:description_i18n"
            desc_i18n = await _get_combat_rule(session, guild_id, generic_action_desc_key, {"en": f"Action '{action_type}' is not recognized or implemented."}, snapshot_rules)

            return CombatActionResult(
                success=False,
                action_type=action_type,
                actor_id=actor_id,
                actor_type=actor_type_str,
                description_i18n=desc_i18n if isinstance(desc_i18n, dict) else {"en": f"Action '{action_type}' is not recognized or implemented."}
            )

        # 4. Update State (DB) - This mainly refers to combat_encounter.participants_json
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
        # First call to log_event removed.

        # Ensure actor_relationship_type has a value before using it, or handle its Optional nature.
        # It should have been set if actor was loaded successfully.
        if not actor_relationship_type:
            # This case should ideally be caught earlier when actor is loaded.
            # Adding a fallback or raising an error if it's None here.
            logger.critical(f"actor_relationship_type is None for actor {actor_id}, this should not happen.")
            # Fallback to actor_type_str or handle error appropriately
            # For now, assume it's set.

        involved_entity_ids = {}
        # Actor
        if actor_relationship_type == RelationshipEntityType.PLAYER:
            involved_entity_ids.setdefault("players", []).append(actor_id)
        elif actor_relationship_type == RelationshipEntityType.GENERATED_NPC:
            involved_entity_ids.setdefault("npcs", []).append(actor_id)

        # Target, if any
        if action_result.target_id and action_result.target_type:
            target_type_lower = action_result.target_type.lower()
            if target_type_lower == RelationshipEntityType.PLAYER.value:
                involved_entity_ids.setdefault("players", []).append(action_result.target_id)
            elif target_type_lower == RelationshipEntityType.GENERATED_NPC.value:
                involved_entity_ids.setdefault("npcs", []).append(action_result.target_id)

        # Ensure uniqueness of IDs in lists
        if "players" in involved_entity_ids:
            involved_entity_ids["players"] = list(set(involved_entity_ids["players"]))
        if "npcs" in involved_entity_ids:
            involved_entity_ids["npcs"] = list(set(involved_entity_ids["npcs"]))


        await log_event(
            session=session,
            guild_id=guild_id,
            event_type=EventType.COMBAT_ACTION.name,
            details_json=event_details,
            location_id=combat_encounter.location_id,
            entity_ids_json=involved_entity_ids if involved_entity_ids else None
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
