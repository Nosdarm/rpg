import logging
import re
from typing import List, Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.crud import crud_relationship
from src.core.crud_base_definitions import get_entity_by_id_and_type_str
from src.core.dice_roller import roll_dice
from src.core.rules import get_rule
from src.models import GeneratedNpc, Player, Relationship
from src.models.check_results import CheckResult, ModifierDetail, CheckOutcome
from src.models.enums import RelationshipEntityType

logger = logging.getLogger(__name__)

DEFAULT_RULE_VALUES = {
    "checks:critical_success_threshold": 20,
    "checks:critical_failure_threshold": 1,
    "checks:dice_notation": "1d20"
}

class CheckError(Exception):
    """Custom exception for errors during check resolution."""
    pass


async def _get_entity_attribute(entity_model: Optional[Any], attribute_name: str) -> Optional[int]:
    """
    Safely retrieves a numeric attribute from an entity model.
    This could be expanded to handle different attribute types or lookups.
    """
    if not entity_model:
        return None

    # Example: Check for direct attribute, then properties_json
    if hasattr(entity_model, attribute_name):
        value = getattr(entity_model, attribute_name)
        if isinstance(value, int):
            return value

    # Check in properties_json if it exists and is a dict
    if hasattr(entity_model, 'properties_json') and isinstance(entity_model.properties_json, dict):
        value = entity_model.properties_json.get(attribute_name)
        if isinstance(value, int):
            return value

    # Could add more complex logic here, e.g., for derived stats or looking up in a stats dict
    return None


async def resolve_check(
    session: AsyncSession,
    guild_id: int,
    check_type: str,
    # Actor context (entity performing the check)
    actor_entity_id: int,
    actor_entity_type: RelationshipEntityType, # Use Enum for type safety
    actor_entity_model: Optional[Any] = None, # Allow passing pre-loaded model
    actor_name_override: Optional[str] = None, # For display if model not loaded/available

    # Target context (entity being targeted by the check, if any)
    target_entity_id: Optional[int] = None,
    target_entity_type: Optional[RelationshipEntityType] = None, # Use Enum
    target_entity_model: Optional[Any] = None, # Allow passing pre-loaded model
    target_name_override: Optional[str] = None,

    difficulty_dc: Optional[int] = None,
    check_context: Optional[Dict[str, Any]] = None # General context dictionary
) -> CheckResult:
    """
    Resolves a game check (e.g., skill check, attack roll) based on RuleConfig rules for a guild.
    actor_entity_model and target_entity_model can be passed if already loaded, otherwise they
    will be fetched based on ID/Type.
    """

    logger.info(
        f"Resolving check for guild {guild_id}, type '{check_type}', "
        f"actor {actor_entity_type.value}:{actor_entity_id}, target {target_entity_type.value if target_entity_type else 'N/A'}:{target_entity_id if target_entity_id else 'N/A'}, DC: {difficulty_dc}"
    )
    check_context = check_context or {}
    modifier_details: List[ModifierDetail] = []
    total_modifier: int = 0

    # 1. Fetch relevant rules from RuleConfig
    dice_notation_rule_key = f"checks:{check_type}:dice_notation"
    base_attribute_rule_key = f"checks:{check_type}:base_attribute"
    crit_success_rule_key = f"checks:{check_type}:critical_success_threshold"
    crit_failure_rule_key = f"checks:{check_type}:critical_failure_threshold"

    dice_notation = await get_rule(session, guild_id=guild_id, key=dice_notation_rule_key) or DEFAULT_RULE_VALUES["checks:dice_notation"]
    base_attribute_name = await get_rule(session, guild_id=guild_id, key=base_attribute_rule_key)

    rules_snapshot = {
        dice_notation_rule_key: dice_notation,
        base_attribute_rule_key: base_attribute_name,
    }

    # 2. Calculate Modifiers
    if not actor_entity_model and actor_entity_id and actor_entity_type:
        actor_entity_model = await get_entity_by_id_and_type_str(
            session, entity_type_str=actor_entity_type.value, entity_id=actor_entity_id, guild_id=guild_id
        )
    if not target_entity_model and target_entity_id and target_entity_type:
        target_entity_model = await get_entity_by_id_and_type_str(
            session, entity_type_str=target_entity_type.value, entity_id=target_entity_id, guild_id=guild_id
        )

    current_actor_name = actor_name_override
    if not current_actor_name and actor_entity_model:
        name_attr = getattr(actor_entity_model, 'name', getattr(actor_entity_model, 'name_i18n', None))
        if isinstance(name_attr, dict):
            current_actor_name = name_attr.get(check_context.get("lang", "en"), name_attr.get("en", f"{actor_entity_type.value}_{actor_entity_id}"))
        elif isinstance(name_attr, str):
            current_actor_name = name_attr
    if not current_actor_name: current_actor_name = f"{actor_entity_type.value}_{actor_entity_id}"

    if base_attribute_name:
        attribute_value = await _get_entity_attribute(actor_entity_model, base_attribute_name)
        if isinstance(attribute_value, int):
            stat_modifier = attribute_value
            modifier_details.append(
                ModifierDetail(source=f"base_stat:{base_attribute_name}", value=stat_modifier, description=f"{base_attribute_name} base stat contribution for {current_actor_name}")
            )
            total_modifier += stat_modifier
            rules_snapshot[f"base_attribute_value:{base_attribute_name}"] = attribute_value
        else:
            logger.warning(f"Could not determine modifier for base attribute '{base_attribute_name}' for actor {current_actor_name}.")

    if "bonus_roll_modifier" in check_context and isinstance(check_context["bonus_roll_modifier"], int):
        bonus_mod = check_context["bonus_roll_modifier"]
        modifier_details.append(ModifierDetail(source="context:bonus_roll_modifier", value=bonus_mod, description="Bonus/penalty from interaction context"))
        total_modifier += bonus_mod
    else:
        if "situational_bonus" in check_context and isinstance(check_context["situational_bonus"], int):
            bonus = check_context["situational_bonus"]
            modifier_details.append(ModifierDetail(source="context:situational_bonus", value=bonus, description="Situational bonus from context"))
            total_modifier += bonus
        if "situational_penalty" in check_context and isinstance(check_context["situational_penalty"], int):
            penalty = check_context["situational_penalty"]
            modifier_details.append(ModifierDetail(source="context:situational_penalty", value=-abs(penalty), description="Situational penalty from context"))
            total_modifier -= abs(penalty)

    relevant_npc_for_hidden_rels_model_local: Optional[Any] = None
    relevant_npc_id_local: Optional[int] = None
    relevant_npc_type_enum_local: Optional[RelationshipEntityType] = None
    other_entity_for_hidden_rels_model_local: Optional[Any] = None
    other_entity_id_local: Optional[int] = None
    other_entity_type_enum_local: Optional[RelationshipEntityType] = None

    if isinstance(actor_entity_model, GeneratedNpc):
        relevant_npc_for_hidden_rels_model_local = actor_entity_model
        relevant_npc_id_local = actor_entity_id
        relevant_npc_type_enum_local = actor_entity_type
        if target_entity_model:
            other_entity_for_hidden_rels_model_local = target_entity_model
            other_entity_id_local = target_entity_id
            other_entity_type_enum_local = target_entity_type
    elif isinstance(target_entity_model, GeneratedNpc):
        relevant_npc_for_hidden_rels_model_local = target_entity_model
        relevant_npc_id_local = target_entity_id
        relevant_npc_type_enum_local = target_entity_type
        if actor_entity_model:
            other_entity_for_hidden_rels_model_local = actor_entity_model
            other_entity_id_local = actor_entity_id
            other_entity_type_enum_local = actor_entity_type

    if relevant_npc_id_local is not None and relevant_npc_type_enum_local is not None:
        npc_all_relationships = await crud_relationship.get_relationships_for_entity(
            session=session, guild_id=guild_id, entity_id=relevant_npc_id_local, entity_type=relevant_npc_type_enum_local
        )
        hidden_prefixes = ("secret_", "internal_", "personal_debt", "hidden_fear", "betrayal_")
        for rel in npc_all_relationships:
            if not rel.relationship_type.startswith(hidden_prefixes):
                continue
            applies_to_current_interaction = False
            rel_target_id_for_this_rel = None
            rel_target_type_for_this_rel = None
            if other_entity_id_local is not None and other_entity_type_enum_local is not None:
                is_rel_entity1_npc = (rel.entity1_id == relevant_npc_id_local and rel.entity1_type == relevant_npc_type_enum_local)
                is_rel_entity2_other = (rel.entity2_id == other_entity_id_local and rel.entity2_type == other_entity_type_enum_local)
                is_rel_entity2_npc = (rel.entity2_id == relevant_npc_id_local and rel.entity2_type == relevant_npc_type_enum_local)
                is_rel_entity1_other = (rel.entity1_id == other_entity_id_local and rel.entity1_type == other_entity_type_enum_local)
                if (is_rel_entity1_npc and is_rel_entity2_other):
                    applies_to_current_interaction = True
                    rel_target_id_for_this_rel = other_entity_id_local
                    rel_target_type_for_this_rel = other_entity_type_enum_local
                elif (is_rel_entity2_npc and is_rel_entity1_other):
                    applies_to_current_interaction = True
                    rel_target_id_for_this_rel = other_entity_id_local
                    rel_target_type_for_this_rel = other_entity_type_enum_local
            if not applies_to_current_interaction:
                continue
            base_rel_type_for_rule = rel.relationship_type.split(':')[0]
            rule_key_exact = f"hidden_relationship_effects:checks:{rel.relationship_type}"
            rule_key_generic = f"hidden_relationship_effects:checks:{base_rel_type_for_rule}"
            specific_rule_conf = await get_rule(session, guild_id, rule_key_exact, default=None)
            generic_rule_conf = await get_rule(session, guild_id, rule_key_generic, default=None)
            rule_conf = None
            if specific_rule_conf and isinstance(specific_rule_conf, dict) and specific_rule_conf.get("enabled", False):
                rule_conf = specific_rule_conf
            elif generic_rule_conf and isinstance(generic_rule_conf, dict) and generic_rule_conf.get("enabled", False):
                rule_conf = generic_rule_conf
            if rule_conf:
                applies_to_checks = rule_conf.get("applies_to_check_types", [])
                if check_type not in applies_to_checks and "*" not in applies_to_checks:
                    continue
                actor_is_hidden_relationship_target = (actor_entity_id == rel_target_id_for_this_rel and actor_entity_type == rel_target_type_for_this_rel)
                eval_context = {"__builtins__": {}, "value": rel.value, "player_matches_relationship": actor_is_hidden_relationship_target}
                modifier_value_for_log = 0
                roll_mod_formula = rule_conf.get("roll_modifier_formula")
                if roll_mod_formula:
                    try:
                        mod = int(eval(roll_mod_formula, eval_context))
                        total_modifier += mod
                        modifier_value_for_log = mod
                        logger.debug(f"Hidden rel '{rel.relationship_type}' (val:{rel.value}) roll_mod:{mod} for check '{check_type}'")
                    except Exception as e:
                        logger.error(f"Eval error in hidden_rel roll_mod_formula '{roll_mod_formula}': {e}")
                dc_mod_formula = rule_conf.get("dc_modifier_formula")
                if dc_mod_formula:
                    try:
                        dc_mod = int(eval(dc_mod_formula, eval_context))
                        total_modifier -= dc_mod
                        modifier_value_for_log = -dc_mod
                        logger.debug(f"Hidden rel '{rel.relationship_type}' (val:{rel.value}) dc_mod:{dc_mod} for check '{check_type}'")
                    except Exception as e:
                        logger.error(f"Eval error in hidden_rel dc_mod_formula '{dc_mod_formula}': {e}")
                if modifier_value_for_log != 0:
                    other_entity_name_str = "Unknown"
                    current_other_model_for_name = None
                    if rel_target_id_for_this_rel == other_entity_id_local:
                        current_other_model_for_name = other_entity_for_hidden_rels_model_local
                    elif rel_target_id_for_this_rel == actor_entity_id:
                         current_other_model_for_name = actor_entity_model
                    if current_other_model_for_name:
                        name_attr = getattr(current_other_model_for_name, 'name', getattr(current_other_model_for_name, 'name_i18n', 'N/A'))
                        if isinstance(name_attr, dict):
                            other_entity_name_str = name_attr.get(check_context.get("lang", "en"), name_attr.get("en", "Unknown Target"))
                        elif isinstance(name_attr, str):
                            other_entity_name_str = name_attr
                    mod_detail_desc = (
                        f"Influence from hidden relationship ({rel.relationship_type} value {rel.value} "
                        f"with {other_entity_name_str}) on {check_type} check. "
                        f"Effective roll change: {modifier_value_for_log}."
                    )
                    modifier_details.append(ModifierDetail(
                        source=f"Hidden Relationship ({rel.relationship_type})",
                        value=modifier_value_for_log,
                        description=mod_detail_desc
                    ))
                    if rules_snapshot:
                        if "hidden_relationship_effects_applied" not in rules_snapshot:
                                rules_snapshot["hidden_relationship_effects_applied"] = []
                        rules_snapshot["hidden_relationship_effects_applied"].append({
                            "relationship_type": rel.relationship_type, "value": rel.value,
                            "rule_key_used": rule_key_exact if specific_rule_conf else rule_key_generic,
                            "modifier_applied_to_roll": modifier_value_for_log
                        })

    relationship_influence_rule_key = f"relationship_influence:checks:{check_type}"
    relationship_rule = await get_rule(session, guild_id, relationship_influence_rule_key)
    if relationship_rule and isinstance(relationship_rule, dict) and relationship_rule.get("enabled"):
        rules_snapshot[relationship_influence_rule_key] = relationship_rule
        rel_target_entity_id: Optional[int] = None
        rel_target_entity_type_str: Optional[str] = None
        if target_entity_id is not None and target_entity_type is not None:
            rel_target_entity_id = target_entity_id
            rel_target_entity_type_str = target_entity_type.value
        if rel_target_entity_id is not None and target_entity_type is not None: # Use target_entity_type directly
            try:
                actor_rel_type_enum = actor_entity_type
                # target_entity_type is already the Enum member if not None
                target_rel_type_enum = target_entity_type
                relationships = await crud_relationship.get_relationships_for_entity(
                    session=session,
                    guild_id=guild_id,
                    entity_type=actor_rel_type_enum,
                    entity_id=actor_entity_id
                )
                relationship_type_pattern_str = relationship_rule.get("relationship_type_pattern", ".*")
                applicable_relationship_value: Optional[int] = None
                for rel in relationships:
                    is_with_target = False
                    if rel.entity1_type == actor_rel_type_enum and rel.entity1_id == actor_entity_id and \
                       rel.entity2_type == target_rel_type_enum and rel.entity2_id == rel_target_entity_id:
                        is_with_target = True
                    elif rel.entity2_type == actor_rel_type_enum and rel.entity2_id == actor_entity_id and \
                         rel.entity1_type == target_rel_type_enum and rel.entity1_id == rel_target_entity_id:
                        is_with_target = True
                    if is_with_target:
                        if re.fullmatch(relationship_type_pattern_str, rel.relationship_type):
                            applicable_relationship_value = rel.value
                            rules_snapshot[f"applicable_relationship:{rel.relationship_type}"] = rel.value
                            break
                if applicable_relationship_value is not None:
                    rel_value = applicable_relationship_value
                    roll_mod_formula = relationship_rule.get("roll_modifier_formula")
                    if roll_mod_formula and isinstance(roll_mod_formula, str):
                        try:
                            modifier_val = int(eval(roll_mod_formula, {"__builtins__": {}}, {"rel_value": rel_value}))
                            total_modifier += modifier_val
                            modifier_details.append(ModifierDetail(
                                source=f"relationship:{relationship_type_pattern_str}",
                                value=modifier_val,
                                description=f"From relationship (value: {rel_value}), formula: {roll_mod_formula}"
                            ))
                            rules_snapshot["relationship_roll_modifier_applied"] = modifier_val
                        except Exception as e:
                            logger.error(f"Error evaluating relationship roll_modifier_formula '{roll_mod_formula}': {e}")
                            rules_snapshot["relationship_roll_modifier_error"] = str(e)
                    elif "modifiers" in relationship_rule and isinstance(relationship_rule["modifiers"], list):
                        for mod_def in relationship_rule["modifiers"]:
                            if mod_def.get("threshold_min", -float('inf')) <= rel_value <= mod_def.get("threshold_max", float('inf')):
                                modifier_val = mod_def.get("modifier", 0)
                                total_modifier += modifier_val
                                desc_key = mod_def.get("description_key", f"Relationship value {rel_value}")
                                term_desc = await get_rule(session, guild_id, desc_key, default=desc_key) if "terms." in desc_key else desc_key
                                modifier_details.append(ModifierDetail(
                                    source=f"relationship:{relationship_type_pattern_str}",
                                    value=modifier_val,
                                    description=str(term_desc)
                                ))
                                rules_snapshot["relationship_threshold_modifier_applied"] = modifier_val
                                break
                else:
                    logger.debug(f"No applicable relationship found matching pattern '{relationship_type_pattern_str}' between {actor_rel_type_enum.value}:{actor_entity_id} and {target_rel_type_enum.value}:{rel_target_entity_id}")
                    rules_snapshot["relationship_applicable_value"] = "not_found"
            except ValueError as e:
                logger.warning(f"Invalid entity type for relationship check: {e}")
                rules_snapshot["relationship_error"] = "invalid_entity_type_for_rel_check"
            except Exception as e:
                logger.error(f"Error processing relationship influence for check '{check_type}': {e}", exc_info=True)
                rules_snapshot["relationship_error"] = str(e)
        else:
            logger.debug(f"No target entity defined for relationship influence on check '{check_type}'.")
            rules_snapshot["relationship_target"] = "not_defined_for_check"

    try:
        dice_roll_total, individual_rolls = roll_dice(dice_notation)
    except ValueError as e:
        logger.error(f"Invalid dice notation '{dice_notation}' from rules for check '{check_type}': {e}")
        raise CheckError(f"Configuration error for check '{check_type}': Invalid dice notation '{dice_notation}'.") from e

    roll_used = individual_rolls[0] if len(individual_rolls) == 1 and "d" in dice_notation else dice_roll_total
    final_value = roll_used + total_modifier
    outcome_status = "failure"
    outcome_description = f"Check ({check_type}) failed with {final_value}."
    crit_success_threshold = await get_rule(session, guild_id=guild_id, key=crit_success_rule_key) or DEFAULT_RULE_VALUES["checks:critical_success_threshold"]
    crit_failure_threshold = await get_rule(session, guild_id=guild_id, key=crit_failure_rule_key) or DEFAULT_RULE_VALUES["checks:critical_failure_threshold"]
    rules_snapshot[crit_success_rule_key] = crit_success_threshold
    rules_snapshot[crit_failure_rule_key] = crit_failure_threshold
    is_d20_roll = "d20" in dice_notation.lower()

    if difficulty_dc is not None:
        if final_value >= difficulty_dc:
            outcome_status = "success"
            outcome_description = f"Check ({check_type}) succeeded with {final_value} against DC {difficulty_dc}."
        if is_d20_roll and roll_used >= crit_success_threshold:
            outcome_status = "critical_success"
            outcome_description = f"Critical success on {check_type} (rolled {roll_used}, final {final_value})!"
        elif is_d20_roll and roll_used <= crit_failure_threshold:
            outcome_status = "critical_failure"
            outcome_description = f"Critical failure on {check_type} (rolled {roll_used}, final {final_value})!"
    else:
        outcome_status = "value_determined"
        outcome_description = f"Check ({check_type}) resulted in {final_value} (no DC provided for comparison)."
        if is_d20_roll and roll_used >= crit_success_threshold:
            outcome_status = "critical_success_value"
            outcome_description = f"Critical roll on {check_type} (rolled {roll_used}, final {final_value})!"
        elif is_d20_roll and roll_used <= crit_failure_threshold:
            outcome_status = "critical_failure_value"
            outcome_description = f"Critical fumble on {check_type} (rolled {roll_used}, final {final_value})!"

    return CheckResult(
        guild_id=guild_id,
        check_type=check_type,
        entity_doing_check_id=actor_entity_id,
        entity_doing_check_type=actor_entity_type.value,
        target_entity_id=target_entity_id,
        target_entity_type=target_entity_type.value if target_entity_type else None,
        difficulty_dc=difficulty_dc, # type: ignore # FIX: Changed difficulty_class to difficulty_dc
        dice_notation=dice_notation,
        raw_rolls=individual_rolls,
        roll_used=roll_used,
        total_modifier=total_modifier,
        modifier_details=modifier_details,
        final_value=final_value,
        outcome=CheckOutcome(status=outcome_status, description=outcome_description),
        rule_config_snapshot=rules_snapshot,
        check_context_provided=check_context
    )
