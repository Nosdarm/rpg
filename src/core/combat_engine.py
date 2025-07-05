import logging
from typing import Any, Dict, Optional, Union, Callable, Tuple, List # Added Tuple, List

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Player, GeneratedNpc, CombatEncounter
from ..models.combat_outcomes import CombatActionResult
from ..models.check_results import CheckResult, CheckOutcome, ModifierDetail # Ensure these are imported
from ..models.enums import EventType, CombatStatus # Added CombatStatus
from .rules import get_rule as core_get_rule
from . import check_resolver as core_check_resolver
from . import dice_roller as core_dice_roller
from . import game_events as core_game_events
from .crud_base_definitions import get_entity_by_id

logger = logging.getLogger(__name__)

# --- Вспомогательные функции (уже реализованы на предыдущем шаге) ---

async def _get_combat_rule(
    combat_rules_snapshot: Optional[Dict[str, Any]],
    session: AsyncSession,
    guild_id: int,
    rule_key: str,
    default: Optional[Any] = None
) -> Any:
    if combat_rules_snapshot and rule_key in combat_rules_snapshot:
        val = combat_rules_snapshot[rule_key]
        logger.debug(f"Rule '{rule_key}' found in snapshot: {val}")
        return val
    return await core_get_rule(session, guild_id, rule_key, default=default)

async def _calculate_attribute_modifier(
    base_value: int,
    session: AsyncSession,
    guild_id: int,
    combat_rules_snapshot: Optional[Dict[str, Any]],
    default_formula: str = "(value - 10) // 2"
) -> int:
    formula_key = "combat:attributes:modifier_formula"
    formula = await _get_combat_rule(
        combat_rules_snapshot, session, guild_id,
        formula_key,
        default=default_formula
    )
    try:
        scope = {"value": base_value}
        modifier = eval(formula, {"__builtins__": {}}, scope)
        if not isinstance(modifier, int):
            logger.warning(f"Attribute modifier formula '{formula}' (from key '{formula_key}') for value {base_value} did not return an int. Got: {modifier}. Attempting conversion.")
            try:
                return int(modifier)
            except (ValueError, TypeError):
                logger.error(f"Could not convert modifier '{modifier}' to int. Using default calculation (base_value - 10) // 2.")
                return (base_value - 10) // 2
        return modifier
    except Exception as e:
        logger.error(f"Error evaluating attribute modifier formula '{formula}' (from key '{formula_key}') with value {base_value}: {e}. Using default calculation.")
        return (base_value - 10) // 2

async def _get_participant_stat(
    participant_data_from_encounter: Optional[Dict[str, Any]],
    base_entity_model: Union[Player, GeneratedNpc],
    stat_path: str,
    session: AsyncSession,
    guild_id: int,
    combat_rules_snapshot: Optional[Dict[str, Any]],
    default: Optional[Any] = None
) -> Any:
    if participant_data_from_encounter:
        keys = stat_path.split('.')
        temp_val = participant_data_from_encounter
        found_in_override = True
        is_base_for_modifier_in_override = False

        # Check if the exact path exists in overrides
        current_ptr = temp_val
        for key_part_idx, key in enumerate(keys):
            if isinstance(current_ptr, dict) and key in current_ptr:
                current_ptr = current_ptr[key]
            else:
                found_in_override = False
                break
        if found_in_override:
             # If requesting "strength_modifier" and "strength" is in override, calculate from override
            if stat_path.endswith("_modifier") and isinstance(current_ptr, int): # e.g. found "strength_modifier" directly
                 logger.debug(f"Stat '{stat_path}' (modifier) found directly in participant_data_from_encounter: {current_ptr}")
                 return current_ptr # Assume it's pre-calculated if full modifier path is present
            elif not stat_path.endswith("_modifier"): # e.g. found "strength" or "current_hp" directly
                 logger.debug(f"Stat '{stat_path}' found directly in participant_data_from_encounter: {current_ptr}")
                 return current_ptr


        # If requesting "strength_modifier" and only "strength" (base) is in override
        if stat_path.endswith("_modifier"):
            base_name_for_modifier = stat_path[:-9] # "strength" from "strength_modifier"
            base_val_in_override = None

            # Check if base_name_for_modifier exists at the root of participant_data
            if base_name_for_modifier in temp_val and isinstance(temp_val[base_name_for_modifier], int):
                 base_val_in_override = temp_val[base_name_for_modifier]
            else: # Check if it's nested, e.g. participant_data['stats']['strength']
                b_keys = base_name_for_modifier.split('.')
                b_ptr = temp_val
                b_found = True
                for bk in b_keys:
                    if isinstance(b_ptr, dict) and bk in b_ptr:
                        b_ptr = b_ptr[bk]
                    else:
                        b_found = False; break
                if b_found and isinstance(b_ptr, int):
                    base_val_in_override = b_ptr

            if base_val_in_override is not None:
                logger.debug(f"Calculating modifier for overridden base stat '{base_name_for_modifier}'={base_val_in_override} for path '{stat_path}'")
                return await _calculate_attribute_modifier(base_val_in_override, session, guild_id, combat_rules_snapshot)


    is_modifier_requested = stat_path.endswith("_modifier")
    path_to_query_on_model = stat_path[:-9] if is_modifier_requested else stat_path

    raw_value: Optional[Any] = None

    if isinstance(base_entity_model, Player):
        if hasattr(base_entity_model, path_to_query_on_model):
            raw_value = getattr(base_entity_model, path_to_query_on_model)
        elif path_to_query_on_model == "max_hp": # Example rule for player max_hp
            raw_value = await _get_combat_rule(combat_rules_snapshot, session, guild_id, f"player:stats:default_max_hp", default=50)
    elif isinstance(base_entity_model, GeneratedNpc):
        if base_entity_model.properties_json and "stats" in base_entity_model.properties_json:
            stats_dict = base_entity_model.properties_json["stats"]
            keys = path_to_query_on_model.split('.')
            current_level = stats_dict
            val_found = True
            for key_part in keys:
                if isinstance(current_level, dict) and key_part in current_level:
                    current_level = current_level[key_part]
                else:
                    val_found = False; break
            if val_found:
                raw_value = current_level

    if is_modifier_requested:
        if isinstance(raw_value, int):
            logger.debug(f"Calculating modifier for base model stat '{path_to_query_on_model}'={raw_value} for entity {base_entity_model.id}")
            return await _calculate_attribute_modifier(raw_value, session, guild_id, combat_rules_snapshot)
        else:
            default_mod_key = "combat:attributes:default_modifier_if_stat_missing"
            default_mod_val = await _get_combat_rule(combat_rules_snapshot, session, guild_id, default_mod_key, default=0)
            logger.warning(f"Cannot calculate modifier for '{stat_path}'. Base stat '{path_to_query_on_model}' from model is not int or not found (value: {raw_value}). Default: {default_mod_val}")
            return default_mod_val

    if raw_value is not None:
        logger.debug(f"Stat '{stat_path}' (resolved to '{path_to_query_on_model}') from base_entity_model {base_entity_model.id}: {raw_value}")
        return raw_value

    logger.warning(f"Stat '{stat_path}' not found for entity {base_entity_model.id} ({type(base_entity_model).__name__}). Returning default value: {default}")
    return default

# --- Основная функция ---

async def process_combat_action(
    guild_id: int,
    session: AsyncSession,
    combat_instance_id: int,
    actor_id: int,
    actor_type: str,
    action_data: dict
) -> CombatActionResult:
    """
    Processes a combat action for a given actor within a combat encounter.
    """
    logger.info(f"Processing combat action for guild {guild_id}, combat {combat_instance_id}, actor {actor_type}:{actor_id}")
    logger.debug(f"Action data: {action_data}")

    action_type_str = action_data.get("action_type", "unknown")
    combat_action_result = CombatActionResult(
        success=False, action_type=action_type_str, actor_id=actor_id, actor_type=actor_type,
        description_i18n={"en": "Action processing started."} # Default message
    )

    combat_encounter = await session.get(CombatEncounter, combat_instance_id)
    if not combat_encounter or combat_encounter.guild_id != guild_id:
        msg = f"Combat encounter {combat_instance_id} not found or does not belong to guild {guild_id}."
        logger.error(msg)
        combat_action_result.description_i18n = {"en": msg.replace(str(combat_instance_id), "ID").replace(str(guild_id), "ID")} # Generic error
        return combat_action_result

    if combat_encounter.status != CombatStatus.ACTIVE:
        msg = f"Combat encounter {combat_instance_id} is not active (status: {combat_encounter.status.value})."
        logger.warning(msg)
        combat_action_result.description_i18n = {"en": "Combat is not active."}
        return combat_action_result

    actor_model_class = Player if actor_type.lower() == "player" else GeneratedNpc if actor_type.lower() == "npc" else None
    if not actor_model_class:
        msg = f"Invalid actor_type: {actor_type}."
        logger.error(msg)
        combat_action_result.description_i18n = {"en": msg}
        return combat_action_result

    actor_entity = await get_entity_by_id(session, actor_model_class, actor_id, guild_id=guild_id)
    if not actor_entity:
        msg = f"Actor {actor_id} ({actor_type}) not found in guild {guild_id}."
        logger.error(msg)
        combat_action_result.description_i18n = {"en": f"Actor {actor_type} not found."} # Generic
        return combat_action_result

    # Ensure participants_json and its 'entities' list exist
    if combat_encounter.participants_json is None: combat_encounter.participants_json = {}
    if "entities" not in combat_encounter.participants_json: combat_encounter.participants_json["entities"] = []

    actor_participant_data = next((p for p in combat_encounter.participants_json["entities"] if p["id"] == actor_id and p["type"] == actor_type), None)
    if not actor_participant_data:
        # This might happen if an entity joins combat mid-way and isn't in participants_json yet
        # Or if actor_id/type from input doesn't match anyone in the current encounter's list
        msg = f"Actor {actor_type}:{actor_id} not found in combat encounter {combat_instance_id} participants list."
        logger.error(msg)
        combat_action_result.description_i18n = {"en": "Actor not found in this combat."}
        return combat_action_result

    # --- Action-specific logic ---
    if action_type_str == "attack":
        target_id = action_data.get("target_id")
        target_type = action_data.get("target_type")

        if target_id is None or target_type is None:
            combat_action_result.description_i18n = {"en": "Attack action requires target_id and target_type."}
            return combat_action_result

        combat_action_result.target_id = target_id
        combat_action_result.target_type = target_type

        target_model_class = Player if target_type.lower() == "player" else GeneratedNpc if target_type.lower() == "npc" else None
        if not target_model_class:
            msg = f"Invalid target_type: {target_type}."
            logger.error(msg)
            combat_action_result.description_i18n = {"en": msg}
            return combat_action_result

        target_entity = await get_entity_by_id(session, target_model_class, target_id, guild_id=guild_id)
        if not target_entity:
            combat_action_result.description_i18n = {"en": f"Target {target_type} not found."}
            return combat_action_result

        target_participant_data = next((p for p in combat_encounter.participants_json["entities"] if p["id"] == target_id and p["type"] == target_type), None)
        if not target_participant_data:
            combat_action_result.description_i18n = {"en": "Target not found in this combat."}
            return combat_action_result

        if target_participant_data.get("current_hp", 0) <= 0:
            combat_action_result.description_i18n = {"en": "Target is already defeated."}
            combat_action_result.success = True # Action taken, but no effect
            return combat_action_result

        # Get rules for attack
        rules_snapshot = combat_encounter.rules_config_snapshot_json
        check_type = await _get_combat_rule(rules_snapshot, session, guild_id, "combat:attack:check_type", "attack_roll")

        # Attacker's attribute for the check (e.g., "strength" or "dexterity" to get modifier from)
        attacker_base_attribute_name = await _get_combat_rule(rules_snapshot, session, guild_id, "combat:attack:attacker_main_attribute", "strength")
        attacker_check_modifier_val = await _get_participant_stat(actor_participant_data, actor_entity, f"{attacker_base_attribute_name}_modifier", session, guild_id, rules_snapshot, 0)

        # Target's defense attribute for DC (e.g., "armor_class")
        target_defense_attribute_name = await _get_combat_rule(rules_snapshot, session, guild_id, "combat:attack:target_defense_attribute", "armor_class")
        dc_value = await _get_participant_stat(target_participant_data, target_entity, target_defense_attribute_name, session, guild_id, rules_snapshot, 10)

        # Resolve the attack check
        # Note: resolve_check itself uses _get_participant_stat for its base_attribute.
        # We pass the specific attribute name to be used for the check via context or ensure rules are set up.
        # For now, resolve_check might need adjustment or we rely on its internal rule fetching for "base_attribute".
        # Let's assume resolve_check is configured to use the correct attacker attribute for the given check_type.
        # The `attacker_check_modifier_val` calculated above is one way to get the modifier,
        # but resolve_check will calculate it internally based on `base_attribute` rule for the check_type.
        # We should ensure `checks:{check_type}:base_attribute` is set to `attacker_base_attribute_name`.

        # To be extremely explicit, we can pass the modifier directly if resolve_check supports it,
        # or ensure rules are configured. For now, rely on resolve_check's rule-based modifier calculation.
        # A potential modification to resolve_check would be to accept an optional `base_modifier_override`.

        attack_roll_result = await core_check_resolver.resolve_check(
            session=session, guild_id=guild_id, check_type=check_type, # FIX: db to session
            actor_entity_id=actor_id, actor_entity_type=actor_type, # FIX: Renamed parameters
            target_entity_id=target_id, target_entity_type=target_type,
            difficulty_dc=dc_value,
            check_context={"actor_participant_data": actor_participant_data, "target_participant_data": target_participant_data}
        )
        combat_action_result.check_result = attack_roll_result

        actor_name_i18n = actor_entity.name_i18n if isinstance(actor_entity, GeneratedNpc) else {"en": actor_entity.name, "ru": actor_entity.name}
        target_name_i18n = target_entity.name_i18n if isinstance(target_entity, GeneratedNpc) else {"en": target_entity.name, "ru": target_entity.name}
        actor_loc_name = actor_name_i18n.get("en", actor_type) # Default to type if name not found
        target_loc_name = target_name_i18n.get("en", target_type)


        if attack_roll_result.outcome.status in ["success", "critical_success"]:
            combat_action_result.success = True
            damage_formula = await _get_combat_rule(rules_snapshot, session, guild_id, "combat:attack:damage_formula", "1d4")
            damage_base_attribute_name = await _get_combat_rule(rules_snapshot, session, guild_id, "combat:attack:damage_attribute", "strength") # e.g. strength
            damage_modifier_val = await _get_participant_stat(actor_participant_data, actor_entity, f"{damage_base_attribute_name}_modifier", session, guild_id, rules_snapshot, 0)

            base_damage_roll, _ = core_dice_roller.roll_dice(damage_formula)
            total_damage = base_damage_roll + damage_modifier_val

            if attack_roll_result.outcome.status == "critical_success":
                crit_multiplier = await _get_combat_rule(rules_snapshot, session, guild_id, "combat:attack:crit_damage_multiplier", 2.0)
                # Option 1: Multiply total damage
                # total_damage = int(total_damage * crit_multiplier)
                # Option 2: Maximize base dice then add another roll + modifier (common D&D rule)
                # For simplicity now, let's use multiplier on calculated damage (base_roll + mod)
                # A more robust crit system would be defined by rules (e.g. "max_dice", "add_dice")
                # max_base_damage_roll = sum(core_dice_roller.roll_dice(damage_formula.split('+')[0])[1]) # Maximize dice part
                # if '+' in damage_formula: # If formula is like "1d6+2", only maximize "1d6"
                #     max_base_damage_roll = sum(core_dice_roller.roll_dice(re.sub(r'\d*d\d+', lambda m: str(int(m.group(0).split('d')[0]) * int(m.group(0).split('d')[1])), damage_formula.split('+')[0]))[1])
                # ^^^ Эта логика перенесена внутрь "maximize_and_add_dice"


                # Simplified crit: double dice or double total. Rule: "crit_type": "double_dice" or "double_total"
                # Let's assume rule "combat:attack:crit_effect" -> "double_damage_dice" or "multiply_total_damage"
                crit_effect_rule = await _get_combat_rule(rules_snapshot, session, guild_id, "combat:attack:crit_effect", "multiply_total_damage")
                logger.debug(f"DEBUG: crit_effect_rule is: {crit_effect_rule}")


                if crit_effect_rule == "double_damage_dice":
                    damage_formula_dice_part = damage_formula
                    if '+' in damage_formula_dice_part:
                        damage_formula_dice_part = damage_formula.split('+')[0]

                    extra_crit_damage_roll, _ = core_dice_roller.roll_dice(damage_formula_dice_part)
                    total_damage = base_damage_roll + extra_crit_damage_roll + damage_modifier_val
                    combat_action_result.additional_details = {"crit_effect": "double_damage_dice"}

                elif crit_effect_rule == "maximize_and_add_dice": # D&D 5e common house rule
                    dice_part = damage_formula.split('+')[0] # e.g., "2d6" from "2d6+3"

                    # Calculate maximized base dice value
                    # Assuming simple NdX format for dice_part for maximization
                    num_dice_str, sides_str = dice_part.split('d')
                    num_dice_val = int(num_dice_str) if num_dice_str else 1
                    sides_val = int(sides_str)
                    maximized_dice_value = num_dice_val * sides_val

                    additional_roll_crit, _ = core_dice_roller.roll_dice(dice_part) # Roll dice again
                    total_damage = maximized_dice_value + additional_roll_crit + damage_modifier_val
                    combat_action_result.additional_details = {"crit_effect": "maximize_and_add_dice"}

                else: # Default: multiply_total_damage
                    total_damage = int(total_damage * crit_multiplier)
                    combat_action_result.additional_details = {"crit_effect": "multiply_total_damage", "multiplier": crit_multiplier}

                desc_en = f"{actor_loc_name} critically strikes {target_loc_name} for {total_damage} damage!"
            else:
                desc_en = f"{actor_loc_name} hits {target_loc_name} for {total_damage} damage."

            total_damage = max(0, total_damage) # Damage cannot be negative
            combat_action_result.damage_dealt = total_damage

            target_participant_data["current_hp"] = max(0, target_participant_data.get("current_hp", 0) - total_damage)
            combat_action_result.description_i18n = {"en": desc_en}

        elif attack_roll_result.outcome.status == "critical_failure":
            combat_action_result.success = False # Usually means miss, but could have other effects
            combat_action_result.description_i18n = {"en": f"{actor_loc_name}'s attack against {target_loc_name} critically fails!"}
        else: # Failure
            combat_action_result.success = False
            combat_action_result.description_i18n = {"en": f"{actor_loc_name} misses {target_loc_name}."}

    else: # Unknown action type
        combat_action_result.description_i18n = {"en": f"Action type '{action_type_str}' is not recognized."}
        return combat_action_result # Early exit for unknown action

    # Update combat encounter log (simple log for now)
    if combat_encounter.combat_log_json is None: combat_encounter.combat_log_json = {"entries": []}
    if "entries" not in combat_encounter.combat_log_json: combat_encounter.combat_log_json["entries"] = []

    # Use a Pydantic model for log entries if structure becomes complex
    log_entry_details = combat_action_result.model_dump(exclude_none=True)
    # Remove redundant info if it's already in the higher-level story log
    log_entry_details.pop("actor_id", None)
    log_entry_details.pop("actor_type", None)

    combat_encounter.combat_log_json["entries"].append({
        "turn": combat_encounter.turn_order_json.get("current_turn_number", 0) if combat_encounter.turn_order_json else 0, # Assuming turn number is tracked
        "actor": f"{actor_type}:{actor_id}",
        "action_details": log_entry_details
    })

    session.add(combat_encounter) # Mark for saving

    # Log to global StoryLog
    # Prepare entity_ids for StoryLog
    story_log_entity_ids = {"actors": [actor_id]}
    if combat_action_result.target_id:
        story_log_entity_ids.setdefault("targets", []).append(combat_action_result.target_id)

    await core_game_events.log_event(
        session=session,
        guild_id=guild_id,
        event_type=EventType.COMBAT_ACTION.name, # Use enum member name
        details_json=combat_action_result.model_dump(exclude_none=True),
        location_id=combat_encounter.location_id,
        entity_ids_json=story_log_entity_ids
    )

    logger.info(f"Combat action processed. Result: Success={combat_action_result.success}, Damage={combat_action_result.damage_dealt}")
    return combat_action_result

logger.info("Combat engine module initialized with process_combat_action.")
