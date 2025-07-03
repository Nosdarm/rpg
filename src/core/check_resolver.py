from typing import List, Optional, Dict, Any, Union
# Pydantic models ModifierDetail, CheckOutcome, CheckResult are now in src.models.check_results
# from pydantic import BaseModel, Field # No longer needed here if all Pydantic models are imported

import logging

# Import the Pydantic models from their new location
from ..models.check_results import ModifierDetail, CheckOutcome, CheckResult


logger = logging.getLogger(__name__)

# Forward declaration for entities, will be refined
# EntityModel = Any # Placeholder for actual entity models like Player, Npc etc.

# Definitions of ModifierDetail, CheckOutcome, CheckResult have been moved.


from sqlalchemy.ext.asyncio import AsyncSession

from .rules import get_rule, get_all_rules_for_guild
from .dice_roller import roll_dice
from ..models.player import Player
from ..models.generated_npc import GeneratedNpc
# Add other entity models as needed, e.g., from ..models.object import ObjectModel
from .crud_base_definitions import get_entity_by_id # Using the generic get_entity_by_id

# Entity types mapping (can be expanded or made more dynamic)
# For now, a simple string mapping. Could use an Enum later.
ENTITY_TYPE_PLAYER = "PLAYER"
ENTITY_TYPE_NPC = "NPC"
ENTITY_TYPE_OBJECT = "OBJECT" # Example

class CheckError(Exception):
    """Custom exception for errors during check resolution."""
    pass


async def _get_entity_attribute(
    db: AsyncSession,
    entity_id: int,
    entity_type: str,
    attribute_name: str,
    guild_id: int
) -> Optional[Any]:
    """
    Helper to fetch a specific attribute from an entity.
    This is a simplified placeholder. A more robust system would involve:
    - Standardized way to access stats/attributes across different models.
    - Calculation of 'effective stats' considering skills, items, statuses.
    """
    model_class: Optional[type] = None
    if entity_type.upper() == ENTITY_TYPE_PLAYER:
        model_class = Player
    elif entity_type.upper() == ENTITY_TYPE_NPC:
        model_class = GeneratedNpc
    # Add more entity types here
    # elif entity_type.upper() == ENTITY_TYPE_OBJECT:
    # model_class = ObjectModel # Assuming an ObjectModel exists

    if not model_class:
        logger.warning(f"Unsupported entity type '{entity_type}' for attribute fetch.")
        return None

    entity = await get_entity_by_id(db, model_class, entity_id, guild_id=guild_id)
    if not entity:
        logger.warning(f"Entity {entity_type}:{entity_id} not found in guild {guild_id}.")
        return None

    if hasattr(entity, attribute_name):
        return getattr(entity, attribute_name)
    else:
        # Fallback: Check common stat structures if models have e.g. a 'stats_json' field
        if hasattr(entity, "stats_json") and isinstance(entity.stats_json, dict) and attribute_name in entity.stats_json:
            return entity.stats_json[attribute_name]
        logger.warning(f"Attribute '{attribute_name}' not found on entity {entity_type}:{entity_id}.")
        return None


async def resolve_check(
    db: AsyncSession, # Added db session
    guild_id: int,
    check_type: str,
    entity_doing_check_id: int,
    entity_doing_check_type: str,
    target_entity_id: Optional[int] = None,
    target_entity_type: Optional[str] = None,
    difficulty_dc: Optional[int] = None,
    check_context: Optional[Dict[str, Any]] = None
) -> CheckResult:
    """
    Resolves a game check (e.g., skill check, attack roll) based on RuleConfig rules for a guild.
    """
    logger.info(
        f"Resolving check for guild {guild_id}, type '{check_type}', "
        f"entity {entity_doing_check_type}:{entity_doing_check_id}, DC: {difficulty_dc}"
    )
    check_context = check_context or {}
    modifier_details: List[ModifierDetail] = []
    total_modifier: int = 0

    # 1. Fetch relevant rules from RuleConfig
    # Example rule keys we might expect for a check_type:
    # - f"checks:{check_type}:dice_notation" (e.g., "1d20")
    # - f"checks:{check_type}:base_attribute" (e.g., "strength", "dexterity")
    # - f"checks:{check_type}:critical_success_threshold" (e.g., 20)
    # - f"checks:{check_type}:critical_failure_threshold" (e.g., 1)
    # - f"checks:{check_type}:dc_formula" (if DC is dynamic, not used if difficulty_dc is passed)
    # - f"checks:{check_type}:adv_disadv_sources" (list of context keys that grant adv/disadv)

    # For simplicity, we'll fetch individual rules. Caching all rules might be better for performance.
    dice_notation_rule_key = f"checks:{check_type}:dice_notation"
    base_attribute_rule_key = f"checks:{check_type}:base_attribute"
    crit_success_rule_key = f"checks:{check_type}:critical_success_threshold"
    crit_failure_rule_key = f"checks:{check_type}:critical_failure_threshold"

    dice_notation = await get_rule(db, guild_id=guild_id, key=dice_notation_rule_key) or "1d20" # Default to 1d20
    base_attribute_name = await get_rule(db, guild_id=guild_id, key=base_attribute_rule_key) # e.g., "strength"

    # Store rules used for logging/transparency
    rules_snapshot = {
        dice_notation_rule_key: dice_notation,
        base_attribute_rule_key: base_attribute_name,
    }

    # 2. Calculate Modifiers
    # 2.a. Base attribute modifier
    if base_attribute_name:
        attribute_value = await _get_entity_attribute(
            db, entity_doing_check_id, entity_doing_check_type, base_attribute_name, guild_id
        )
        if isinstance(attribute_value, int):
            # Assuming attributes are direct modifiers for now.
            # A common TTRPG conversion is (Stat - 10) // 2. This needs to be rule-defined.
            # For now, let's assume 'attribute_value' *is* the modifier if it's from a field like 'strength_modifier'.
            # If it's a raw stat like 'strength:14', it needs conversion rule.
            # Simplified: if attribute_name is 'strength', assume it's the raw stat.
            # This part NEEDS to be defined by RuleConfig: how to derive modifier from attribute.
            # Placeholder: if attribute is e.g. 14, modifier is +2. If it's 8, modifier is -1.
            # For now, if attribute_value is int, we assume it's already a modifier for simplicity in this phase.
            # If not, we need a rule: f"attributes:{base_attribute_name}:modifier_formula" -> "(value - 10) // 2"

            # Simple placeholder: Assume the fetched value is the modifier itself.
            # This needs refinement based on how stats are stored (raw vs. modifier)
            # and how RuleConfig defines conversion.
            stat_modifier = attribute_value

            # Example: If 'strength' is 14, and rule is (val-10)/2, then mod is 2.
            # Let's assume for now RuleConfig gives `base_attribute_modifier_value` directly or we fetch pre-calculated mod.
            # For this phase, if attribute_value is an int, we use it.
            modifier_details.append(
                ModifierDetail(source=f"base_stat:{base_attribute_name}", value=stat_modifier, description=f"{base_attribute_name} base stat contribution")
            )
            total_modifier += stat_modifier
            rules_snapshot[f"base_attribute_value:{base_attribute_name}"] = attribute_value # Log raw value
        else:
            logger.warning(f"Could not determine modifier for base attribute '{base_attribute_name}' for entity {entity_doing_check_type}:{entity_doing_check_id}.")
            # We might add a default 0 modifier or raise an error depending on game rules.
            # modifier_details.append(ModifierDetail(source=f"base_stat:{base_attribute_name}", value=0, description="Attribute not found or not integer"))


    # 2.b. Contextual modifiers (from check_context)
    # RuleConfig should define which keys in check_context provide modifiers.
    # Example: "checks:{check_type}:context_modifiers" -> {"tool_bonus": "integer", "cover_penalty": "integer"}
    # For now, a simple "situational_bonus" or "situational_penalty"
    if "situational_bonus" in check_context and isinstance(check_context["situational_bonus"], int):
        bonus = check_context["situational_bonus"]
        modifier_details.append(ModifierDetail(source="context:situational_bonus", value=bonus, description="Situational bonus from context"))
        total_modifier += bonus
    if "situational_penalty" in check_context and isinstance(check_context["situational_penalty"], int):
        penalty = check_context["situational_penalty"]
        modifier_details.append(ModifierDetail(source="context:situational_penalty", value=-abs(penalty), description="Situational penalty from context")) # Ensure penalty is negative
        total_modifier -= abs(penalty)

    # TODO: Add placeholders for other modifier sources (skills, items, statuses, relationships)
    # These would also fetch rules from RuleConfig on how they apply to 'check_type'
    # E.g., modifier_details.append(ModifierDetail(source="skill:perception", value=skill_mod))

    # 3. Roll Dice
    try:
        dice_roll_total, individual_rolls = roll_dice(dice_notation)
    except ValueError as e:
        logger.error(f"Invalid dice notation '{dice_notation}' from rules for check '{check_type}': {e}")
        raise CheckError(f"Configuration error for check '{check_type}': Invalid dice notation '{dice_notation}'.") from e

    # For now, assume no advantage/disadvantage. The first roll or sum is used.
    # If dice_notation is like "1d20", individual_rolls[0] is the key.
    # If "2d6", dice_roll_total is the sum.
    # The definition of "roll_used" needs to be clear. For a single die like 1d20, it's the result of that die.
    # For multiple dice summed (like 2d6 for damage), "roll_used" could be the sum *before* flat modifiers.
    # Let's assume for typical d20 checks, roll_used is the single die face.
    roll_used = individual_rolls[0] if len(individual_rolls) == 1 and "d" in dice_notation else dice_roll_total
    # This ^ is a simplification. RuleConfig should specify how to interpret raw_rolls (e.g., for adv/disadv)

    # 4. Calculate Final Value
    final_value = roll_used + total_modifier

    # 5. Determine Outcome
    # Default to failure
    outcome_status = "failure"
    outcome_description = f"Check ({check_type}) failed with {final_value}."

    crit_success_threshold = await get_rule(db, guild_id=guild_id, key=crit_success_rule_key) or 20
    crit_failure_threshold = await get_rule(db, guild_id=guild_id, key=crit_failure_rule_key) or 1
    rules_snapshot[crit_success_rule_key] = crit_success_threshold
    rules_snapshot[crit_failure_rule_key] = crit_failure_threshold

    is_d20_roll = "d20" in dice_notation.lower() # Approximation

    if difficulty_dc is not None:
        if final_value >= difficulty_dc:
            outcome_status = "success"
            outcome_description = f"Check ({check_type}) succeeded with {final_value} against DC {difficulty_dc}."
        # Crit success/failure logic (can override normal success/failure based on rules)
        if is_d20_roll and roll_used >= crit_success_threshold:
             # RuleConfig might specify if nat 20 auto-succeeds or just adds bonus
            outcome_status = "critical_success"
            outcome_description = f"Critical success on {check_type} (rolled {roll_used}, final {final_value})!"
        elif is_d20_roll and roll_used <= crit_failure_threshold:
            # RuleConfig might specify if nat 1 auto-fails
            outcome_status = "critical_failure"
            outcome_description = f"Critical failure on {check_type} (rolled {roll_used}, final {final_value})!"
    else:
        # This is a contested check or a check without a fixed DC.
        # The outcome might be determined by comparing to another entity's roll, or just the value itself.
        # Placeholder: if no DC, we can't determine success/failure easily without more rules.
        # For now, let's just record the value.
        outcome_status = "value_determined" # Or some other status
        outcome_description = f"Check ({check_type}) resulted in {final_value} (no DC provided for comparison)."
        # If it was a nat 20/1 on a d20, still flag it.
        if is_d20_roll and roll_used >= crit_success_threshold:
            outcome_status = "critical_success_value" # Or similar
            outcome_description = f"Critical roll on {check_type} (rolled {roll_used}, final {final_value})!"
        elif is_d20_roll and roll_used <= crit_failure_threshold:
            outcome_status = "critical_failure_value"
            outcome_description = f"Critical fumble on {check_type} (rolled {roll_used}, final {final_value})!"


    return CheckResult(
        guild_id=guild_id,
        check_type=check_type,
        entity_doing_check_id=entity_doing_check_id,
        entity_doing_check_type=entity_doing_check_type,
        target_entity_id=target_entity_id,
        target_entity_type=target_entity_type,
        difficulty_class=difficulty_dc,
        dice_notation=dice_notation,
        raw_rolls=individual_rolls,
        roll_used=roll_used, # This needs to be the value of the die for d20 checks before mods for crit checks
        total_modifier=total_modifier,
        modifier_details=modifier_details,
        final_value=final_value,
        outcome=CheckOutcome(status=outcome_status, description=outcome_description),
        rule_config_snapshot=rules_snapshot,
        check_context_provided=check_context
    )


if __name__ == '__main__':
    # Example usage (will be more useful once integrated)
    import asyncio
    from unittest.mock import MagicMock

    async def main(db: Optional[AsyncSession] = None):
        # If no db is provided (as in this example), use a mock
        mock_db_session = MagicMock(spec=AsyncSession) if db is None else db

        example_result = await resolve_check(
            db=mock_db_session, # Pass the db session
            guild_id=123,
            check_type="lockpicking",
            entity_doing_check_id=1,
            entity_doing_check_type="PLAYER",
            target_entity_id=101,
            target_entity_type="OBJECT",
            difficulty_dc=15,
            check_context={"tool_quality": "good", "situational_bonus": 2}
        )
        print(example_result.model_dump_json(indent=2))

        example_crit_fail = await resolve_check(
            db=mock_db_session, # Pass the db session
            guild_id=123,
            check_type="attack",
            entity_doing_check_id=2,
            entity_doing_check_type="NPC",
            target_entity_id=1,
            target_entity_type="PLAYER",
            difficulty_dc=10 # Target AC
        )
        # To simulate crit fail, we'd need to mock dice roll or make the placeholder logic more complex
        # For now, this just shows the structure.
        # Let's assume the placeholder logic for dice roll could be modified to simulate a 1 for this example.
        # (This is not how it will work in prod, just for this __main__ block)

        # A better way to test this here would be to modify the mock_entity_stats or difficulty_dc
        # to force different outcomes with the current simple placeholder logic.
        # For instance, to make the first check fail:
        example_fail_result = await resolve_check(
            db=mock_db_session, # Pass the db session
            guild_id=123,
            check_type="lockpicking",
            entity_doing_check_id=1,
            entity_doing_check_type="PLAYER",
            target_entity_id=101,
            target_entity_type="OBJECT",
            difficulty_dc=25, # Higher DC
            check_context={"tool_quality": "poor", "situational_bonus": -1}
        )
        print("\nExample Fail:")
        print(example_fail_result.model_dump_json(indent=2))


    if __name__ == "__main__": # Redundant check, but common pattern
        asyncio.run(main())
