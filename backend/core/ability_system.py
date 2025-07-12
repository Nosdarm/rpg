from typing import Any, List, Optional, Dict, Union
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import datetime # ADDED IMPORT


from backend.models import (
    Player,
    GeneratedNpc,
    Ability,
    StatusEffect,
    ActiveStatusEffect,
    GuildConfig,
    RuleConfig,
    Location # Added for distance checks
)
from backend.models.ability_outcomes import AbilityOutcomeDetails, AppliedStatusDetail, DamageDetail, HealingDetail, CasterUpdateDetail
from backend.models.enums import RelationshipEntityType, EventType, PlayerStatus
# Removed CRUDBase import as it's not directly used here, but through specific cruds
from backend.core.crud.crud_ability import ability_crud
from backend.core.crud.crud_status_effect import status_effect_crud
from backend.core.crud.crud_player import player_crud
from backend.core.crud.crud_npc import npc_crud
from backend.core.utils import log_event
from backend.core.rules import get_rule
from backend.core.entity_stats_utils import get_entity_hp, set_entity_hp, change_entity_hp, get_entity_stat, set_entity_stat, change_entity_stat # Added
from sqlalchemy.sql import func # Added
import math # Added for distance calculation

logger = logging.getLogger(__name__)

# --- Helper Functions for Checks ---

async def _check_ability_availability(
    caster: Union[Player, GeneratedNpc],
    db_ability: Ability
) -> tuple[bool, str]:
    """
    Checks if the caster knows the ability.
    Placeholder: Assumes all entities know all abilities for now.
    Future: Implement a system for learned abilities (e.g., CharacterAbilities table).
    """
    # Example: if isinstance(caster, Player):
    #   known = await session.execute(select(PlayerLearnedAbility).where(PlayerLearnedAbility.player_id == caster.id, PlayerLearnedAbility.ability_id == db_ability.id))
    #   if not known.scalar_one_or_none():
    #       return False, f"Caster does not know ability '{db_ability.static_id}'."
    logger.debug(f"Placeholder: Ability '{db_ability.static_id}' availability check passed for caster {caster.id}.")
    return True, ""

async def _check_cooldowns(
    session: AsyncSession, # Added session for potential DB access
    guild_id: int, # Added guild_id
    caster: Union[Player, GeneratedNpc],
    db_ability: Ability
) -> tuple[bool, str]:
    """
    Checks if the ability is off cooldown for the caster.
    Placeholder: Assumes abilities have no cooldowns or cooldowns are always met.
    Future: Implement a system for tracking ability cooldowns per entity
            (e.g., EntityAbilityCooldowns table with ability_id, entity_id, last_used_timestamp).
            Cooldown duration could be stored in Ability.properties_json or RuleConfig.
    """
    cooldown_duration_seconds = db_ability.properties_json.get("cooldown_seconds")
    if cooldown_duration_seconds:
        # This is where you'd fetch the last used time for this caster and ability
        # last_used_time = await get_last_used_time(session, caster.id, caster_type, db_ability.id)
        # if last_used_time and (datetime.datetime.utcnow() - last_used_time).total_seconds() < cooldown_duration_seconds:
        #     remaining_cooldown = cooldown_duration_seconds - (datetime.datetime.utcnow() - last_used_time).total_seconds()
        #     return False, f"Ability '{db_ability.static_id}' is on cooldown. {remaining_cooldown:.1f}s remaining."
        pass # Placeholder logic
    logger.debug(f"Placeholder: Cooldown check passed for ability '{db_ability.static_id}' for caster {caster.id}.")
    return True, ""


async def _check_prerequisites(
    session: AsyncSession, # Added session
    guild_id: int, # Added guild_id
    caster: Union[Player, GeneratedNpc],
    db_ability: Ability
) -> tuple[bool, str]:
    """
    Checks for caster state or equipment prerequisites.
    Reads from db_ability.properties_json["prerequisites"]
    Example: {"status": "not_stunned", "equipment_slot": "main_hand", "required_item_type": "sword"}
    """
    prerequisites = db_ability.properties_json.get("prerequisites", {})
    if not prerequisites:
        return True, ""

    # Check caster status prerequisites
    required_status = prerequisites.get("status")
    if required_status:
        caster_current_status = get_entity_stat(caster, "status") # Assumes 'status' is a stat like 'stunned', 'normal'
        # This needs to be more robust: check ActiveStatusEffects for "stunned" etc.
        # For example, if required_status is "not_stunned":
        #   active_stuns = await session.execute(select(ActiveStatusEffect).join(StatusEffect).where(StatusEffect.static_id == "stunned", ActiveStatusEffect.entity_id == caster.id ...))
        #   if active_stuns.scalars().first():
        #       return False, f"Caster cannot use '{db_ability.static_id}' while stunned."
        if required_status == "in_combat" and isinstance(caster, Player):
            if caster.current_status != PlayerStatus.COMBAT.value:
                 return False, f"Caster must be in combat to use '{db_ability.static_id}'."
        elif required_status == "in_combat" and isinstance(caster, GeneratedNpc):
            if get_entity_stat(caster, "status") != "in_combat": # Assuming 'in_combat' is a possible value for NPC status stat
                 return False, f"Caster must be in combat to use '{db_ability.static_id}'."
        # Add more specific status checks here

    # Check equipment prerequisites
    # This would require access to the caster's inventory/equipment.
    # required_equipment_type = prerequisites.get("required_item_type")
    # if required_equipment_type:
    #   equipped_item_in_slot = await get_equipped_item(session, caster, prerequisites.get("equipment_slot", "any"))
    #   if not equipped_item_in_slot or equipped_item_in_slot.item_type != required_item_type:
    #       return False, f"Caster requires a '{required_item_type}' equipped to use '{db_ability.static_id}'."

    logger.debug(f"Placeholder/Partial: Prerequisite check passed for ability '{db_ability.static_id}' for caster {caster.id}.")
    return True, ""

async def _get_entity_location(session: AsyncSession, entity: Union[Player, GeneratedNpc]) -> Optional[Location]:
    """Helper to get the current location of an entity."""
    if not hasattr(entity, 'current_location_id') or not entity.current_location_id:
        return None
    return await session.get(Location, entity.current_location_id)

def _calculate_distance(loc1: Location, loc2: Location) -> float:
    """Calculates Euclidean distance between two locations if they have x, y, z coordinates."""
    if not loc1.properties_json or not loc2.properties_json:
        return float('inf')

    x1 = loc1.properties_json.get("x")
    y1 = loc1.properties_json.get("y")
    x2 = loc2.properties_json.get("x")
    y2 = loc2.properties_json.get("y")

    if x1 is None or y1 is None or x2 is None or y2 is None:
        # Consider locations without coordinates to be infinitely far for targeting,
        # unless they are the same location_id (handled by range 0 check)
        return float('inf')

    # Use z=0 if not present for 2D distance
    z1 = loc1.properties_json.get("z", 0)
    z2 = loc2.properties_json.get("z", 0)

    return math.sqrt((x1 - x2)**2 + (y1 - y2)**2 + (z1 - z2)**2)


async def _validate_targets(
    session: AsyncSession,
    guild_id: int,
    caster: Union[Player, GeneratedNpc],
    targets: List[Union[Player, GeneratedNpc]],
    db_ability: Ability
) -> tuple[bool, str, List[Union[Player, GeneratedNpc]]]:
    """
    Validates targets based on range, LoS (placeholder), and type.
    Reads from db_ability.properties_json["targeting_rules"]
    Example: {"max_range": 30, "requires_los": true, "allowed_target_types": ["enemy", "hostile_npc"]}
    Returns: (isValid, message, valid_targets_list)
    """
    targeting_rules = db_ability.properties_json.get("targeting_rules", {})
    if not targeting_rules: # No specific rules, all targets are considered valid initially
        return True, "", targets

    max_range = targeting_rules.get("max_range") # e.g., in meters or units
    # requires_los = targeting_rules.get("requires_los", False) # Line of Sight
    # allowed_target_types = targeting_rules.get("allowed_target_types", []) # e.g., ["enemy", "self", "ally_player", "any_npc"]

    caster_location = await _get_entity_location(session, caster)
    valid_targets_for_ability: List[Union[Player, GeneratedNpc]] = []

    for target_candidate in targets:
        if target_candidate == caster and targeting_rules.get("can_target_self", True) is False: # Explicitly cannot target self
            logger.debug(f"Target validation failed for '{db_ability.static_id}': Cannot target self.")
            continue # Skip self if not allowed

        if target_candidate == caster and targeting_rules.get("can_target_self", True) is True:
            # Self is always in range and LoS of self. Check other type rules if necessary.
            pass # Will be added to valid_targets_for_ability if other checks pass or are not present

        # Range Check
        if max_range is not None and target_candidate != caster:
            if not caster_location:
                return False, f"Caster location unknown, cannot check range for '{db_ability.static_id}'.", []

            target_location = await _get_entity_location(session, target_candidate)
            if not target_location:
                logger.warning(f"Target {target_candidate.id} location unknown for ability '{db_ability.static_id}'. Skipping target.")
                continue

            # If entities are in the same location node, and range is 0, it's a valid "touch" range.
            if max_range == 0 and caster_location.id == target_location.id:
                 pass # Valid touch range
            elif caster_location.id == target_location.id and caster_location.x is None: # Same abstract location, no coords
                pass # Assume in range
            else: # Calculate distance if coordinates exist
                distance = _calculate_distance(caster_location, target_location)
                if distance > max_range:
                    logger.debug(f"Target validation failed for '{db_ability.static_id}': Target {target_candidate.id} out of range ({distance:.1f} > {max_range}).")
                    continue # Skip this target

        # Line of Sight (LoS) Check - Placeholder
        # if requires_los and target_candidate != caster:
        #   has_los = await check_line_of_sight(session, caster_location, target_location) # Complex function, placeholder
        #   if not has_los:
        #       logger.debug(f"Target validation failed for '{db_ability.static_id}': Target {target_candidate.id} not in line of sight.")
        #       continue

        # Target Type Check (e.g., enemy, ally, specific faction) - Placeholder
        # This would require a relationship/faction system to determine if a target is "enemy" or "ally".
        # For now, we assume any provided target is of an acceptable type if it passes range/LoS.
        # Example:
        # target_relation = await get_relationship_status(session, caster, target_candidate)
        # if "enemy" in allowed_target_types and target_relation != "enemy":
        #    continue
        # if "ally" in allowed_target_types and target_relation != "ally":
        #    continue

        valid_targets_for_ability.append(target_candidate)

    if not targets and db_ability.properties_json.get("requires_target", False): # Ability requires target(s) but none were valid or provided
        return False, f"Ability '{db_ability.static_id}' requires at least one valid target.", []

    if not valid_targets_for_ability and targets: # Had targets, but none were valid
        return False, f"No valid targets found for ability '{db_ability.static_id}' after validation.", []

    logger.debug(f"Target validation passed for ability '{db_ability.static_id}'. Valid targets: {[t.id for t in valid_targets_for_ability]}.")
    return True, "", valid_targets_for_ability


# Helper to get entity - Placeholder, needs refinement for actual stat access
async def _get_entity(session: AsyncSession, guild_id: int, entity_id: int, entity_type: str) -> Optional[Union[Player, GeneratedNpc]]:
    """Loads a player or NPC entity."""
    if entity_type.lower() == RelationshipEntityType.PLAYER.value.lower():
        return await player_crud.get(session, id=entity_id, guild_id=guild_id)
    elif entity_type.lower() == RelationshipEntityType.GENERATED_NPC.value.lower(): # Corrected Enum member
        return await npc_crud.get(session, id=entity_id, guild_id=guild_id)
    logger.warning(f"Unsupported entity type for ability system: {entity_type}")
    return None

async def remove_status(
    session: AsyncSession,
    guild_id: int,
    active_status_id: int
) -> bool:
    """
    Removes an active status effect.
    """
    active_status_effect = await session.get(ActiveStatusEffect, active_status_id)
    if not active_status_effect or active_status_effect.guild_id != guild_id:
        logger.warning(f"ActiveStatusEffect ID {active_status_id} not found or not in guild {guild_id}.")
        return False

    # Store details before deleting for logging
    removed_entity_id = active_status_effect.entity_id
    # Assuming active_status_effect.entity_type stores the string value (e.g., "player", "generated_npc")
    removed_entity_type_str = active_status_effect.entity_type # This is already a string like "player" or "generated_npc"
    removed_status_effect_id = active_status_effect.status_effect_id

    # Fetch the original StatusEffect to get its static_id for logging
    original_status_effect = await session.get(StatusEffect, removed_status_effect_id)
    removed_status_static_id = original_status_effect.static_id if original_status_effect else "unknown_static_id"

    await session.delete(active_status_effect)
    await session.flush() # Ensure delete is processed before trying to log based on it.

    logger.info(f"ActiveStatusEffect ID {active_status_id} (owner: {removed_entity_type_str} {removed_entity_id}) removed.")

    # Determine player_id for log_event
    event_player_id: Optional[int] = None
    location_id_of_entity: Optional[int] = None

    # Compare the string from the DB with the enum's .value attribute
    if removed_entity_type_str == RelationshipEntityType.PLAYER.value:
        event_player_id = removed_entity_id
        # Optionally fetch player to get location_id
        # Pass the string 'removed_entity_type_str' directly to _get_entity
        player_entity = await _get_entity(session, guild_id, removed_entity_id, removed_entity_type_str)
        if player_entity and hasattr(player_entity, 'current_location_id'):
            location_id_of_entity = player_entity.current_location_id
    elif removed_entity_type_str == RelationshipEntityType.GENERATED_NPC.value:
        # If an NPC, we might still want to log if a player was involved in causing this or is nearby.
        # For now, no direct player_id unless it's the entity itself.
        # Optionally fetch NPC to get location_id
        # Pass the string 'removed_entity_type_str' directly to _get_entity
        npc_entity = await _get_entity(session, guild_id, removed_entity_id, removed_entity_type_str)
        if npc_entity and hasattr(npc_entity, 'current_location_id'):
            # This part depends on GeneratedNpc model structure.
            location_id_of_entity = getattr(npc_entity, 'current_location_id', None)


    log_details_status_removed = {
        "active_status_id": active_status_id,
        "entity_id": removed_entity_id,
        "entity_type": removed_entity_type_str, # Use the string directly
        "status_effect_id": removed_status_effect_id,
        "status_static_id": removed_status_static_id
    }

    await log_event(
        session=session,
        guild_id=guild_id,
        event_type=EventType.STATUS_REMOVED.value, # This .value is correct for EventType enum
        details_json=log_details_status_removed,
        player_id=event_player_id, # Log if the affected entity was a player
        location_id=location_id_of_entity
    )
    return True

# CRUD instances that need to be created/moved:
# In src/core/crud/crud_ability.py
# class CRUDAbility(CRUDBase[Ability, ...]): ...
# ability_crud = CRUDAbility(Ability)

# In src/core/crud/crud_status_effect.py
# class CRUDStatusEffect(CRUDBase[StatusEffect, ...]): ...
# status_effect_crud = CRUDStatusEffect(StatusEffect)
# class CRUDActiveStatusEffect(CRUDBase[ActiveStatusEffect, ...]): ...
# active_status_effect_crud = CRUDActiveStatusEffect(ActiveStatusEffect)

# These would then be imported here.
# Using CRUD operations now
# Removed local get_ability_by_id_or_static_id and get_status_effect_by_static_id

async def activate_ability( # Signature updated to use ability_identifier
    session: AsyncSession,
    guild_id: int,
    entity_id: int,
    entity_type: str,
    ability_identifier: Union[int, str], # Can be ID or static_id
    target_entity_ids: Optional[List[int]] = None,
    target_entity_types: Optional[List[str]] = None
) -> AbilityOutcomeDetails:
    outcome = AbilityOutcomeDetails(success=False, message="Ability activation failed.")

    db_ability: Optional[Ability] = None
    if isinstance(ability_identifier, int):
        db_ability = await ability_crud.get(session, id=ability_identifier)
    elif isinstance(ability_identifier, str):
        db_ability = await ability_crud.get_by_static_id(session, static_id=ability_identifier, guild_id=guild_id)

    if not db_ability:
        outcome.message = f"Ability '{ability_identifier}' not found."
        return outcome
    # Ensure guild consistency if ability is guild_specific and was fetched by ID (static_id fetch already handles this)
    if isinstance(ability_identifier, int) and db_ability.guild_id is not None and db_ability.guild_id != guild_id:
        # This case implies an ID from another guild was passed, or a global ability ID was passed
        # but we are in a guild context. If it's a global ability (db_ability.guild_id is None), it's fine.
        # If db_ability.guild_id is not None AND not equal to current guild_id, then it's an error.
         outcome.message = f"Ability ID '{ability_identifier}' does not belong to this guild or is not global."
         return outcome


    outcome.raw_ability_properties = db_ability.properties_json
    caster = await _get_entity(session, guild_id, entity_id, entity_type)
    if not caster:
        outcome.message = f"{entity_type.capitalize()} (caster) not found."
        return outcome

    # --- Initial Checks ---
    # 1. Ability Availability (Learned? Class-specific?)
    available, msg = await _check_ability_availability(caster, db_ability)
    if not available:
        outcome.message = msg
        return outcome

    # 2. Cooldowns
    off_cooldown, msg = await _check_cooldowns(session, guild_id, caster, db_ability)
    if not off_cooldown:
        outcome.message = msg
        return outcome

    # 3. Caster Prerequisites (Status, Equipment)
    prereqs_met, msg = await _check_prerequisites(session, guild_id, caster, db_ability)
    if not prereqs_met:
        outcome.message = msg
        return outcome

    # --- Target Acquisition and Validation ---
    targets: List[Union[Player, GeneratedNpc]] = []
    if target_entity_ids and target_entity_types and len(target_entity_ids) == len(target_entity_types):
        for i, target_id in enumerate(target_entity_ids):
            target_type = target_entity_types[i]
            target_entity = await _get_entity(session, guild_id, target_id, target_type)
            if target_entity: targets.append(target_entity)

    # If ability requires targets but none provided (and not self-targetting by default)
    if not targets and db_ability.properties_json.get("requires_target", False) and \
       not (db_ability.properties_json.get("effects") and \
            any(eff.get("target_scope") == "self" for eff in db_ability.properties_json["effects"])):
        outcome.message = f"Ability '{db_ability.static_id}' requires target(s), but none were provided."
        return outcome

    # 4. Target Validation (Range, LoS, Type)
    # Note: If an ability can be self-targeted and no targets are provided, it should be handled here or by target_scope logic.
    # If targets list is empty AND the ability is not purely self-targeting, validation might be skipped or might fail.
    # For now, if `targets` is empty, `_validate_targets` will handle it based on ability properties.
    targets_valid, msg, validated_targets = await _validate_targets(session, guild_id, caster, targets, db_ability)
    if not targets_valid:
        outcome.message = msg
        return outcome

    targets = validated_targets # Use the list of targets that passed validation

    logger.info(f"Ability '{db_ability.static_id}' (ID: {db_ability.id}) activated by {entity_type} ID {entity_id} on {len(targets)} validated targets.")

    # --- Resource Costs ---
    # This is effectively the final check before applying effects.
    # If this fails, previous checks (like cooldowns) should ideally not be triggered yet,
    # or their effects (like starting a cooldown) should be reverted if costs can't be paid.
    # For simplicity, resource check is done here. A more complex system might pre-validate resources.
    if db_ability.properties_json and "cost" in db_ability.properties_json:
        cost_info = db_ability.properties_json["cost"]
        resource_type = cost_info.get("resource")
        amount_required = cost_info.get("amount")

        if resource_type and isinstance(amount_required, int) and amount_required > 0:
            current_resource_value = get_entity_stat(caster, resource_type)
            if not isinstance(current_resource_value, int) or current_resource_value < amount_required:
                outcome.message = f"Not enough {resource_type} to use ability '{db_ability.static_id}'. Required: {amount_required}, Available: {current_resource_value if isinstance(current_resource_value, int) else 0}."
                # No success=False here yet, as it's set by default.
                return outcome

            if not change_entity_stat(caster, resource_type, -amount_required):
                logger.error(f"Failed to deduct {resource_type} from {entity_type} ID {entity_id} for ability {db_ability.static_id}.")
                outcome.message = f"Error processing resource cost for ability '{db_ability.static_id}'."
                return outcome
            logger.info(f"Caster {entity_type} ID {entity_id} paid {amount_required} of {resource_type} for ability '{db_ability.static_id}'.")
            outcome.caster_updates.append(CasterUpdateDetail(resource_type=resource_type, change= -amount_required))
        elif amount_required == 0:
             logger.info(f"Ability '{db_ability.static_id}' has no resource cost.")
        # else: logger.warning for malformed cost_info could be added.

    # --- RuleConfig Based Activation Conditions (Additional general conditions) ---
    # These are more abstract conditions from RuleConfig, checked after specific prerequisites and costs.
    # Example: "caster_must_be_in_combat" was moved to _check_prerequisites for more specific handling,
    # but other general RuleConfig conditions could be checked here.
    # activation_conditions_key = f"ability_rules:{db_ability.static_id}:activation_conditions"
    # activation_conditions = await get_rule(session, guild_id, activation_conditions_key)
    # if activation_conditions:
    #     # Process these conditions. If any fail:
    #     # outcome.message = "Failed RuleConfig activation condition for '{db_ability.static_id}'."
    #     # return outcome
    #     pass


    # --- Apply Effects ---
    # If all checks passed and costs paid, proceed to apply effects.
    if db_ability.properties_json and "effects" in db_ability.properties_json:
        for effect_data in db_ability.properties_json.get("effects", []): # type: ignore
            effect_type = effect_data.get("type")
            target_scope = effect_data.get("target_scope", "first_target") # Default to first target if not specified

            actual_targets_for_this_effect: List[Union[Player, GeneratedNpc]] = []

            if target_scope == "self":
                actual_targets_for_this_effect = [caster]
            elif target_scope == "first_target":
                if targets:
                    actual_targets_for_this_effect = [targets[0]]
                else:
                    logger.warning(f"Effect type '{effect_type}' for ability '{db_ability.static_id}' targets 'first_target' but no targets were provided or found.")
                    continue # Skip this effect if no valid target
            elif target_scope == "all_targets":
                if targets:
                    actual_targets_for_this_effect = targets
                else:
                    logger.warning(f"Effect type '{effect_type}' for ability '{db_ability.static_id}' targets 'all_targets' but no targets were provided or found.")
                    continue # Skip this effect
            else:
                logger.warning(f"Unknown target_scope '{target_scope}' for effect in ability '{db_ability.static_id}'. Skipping effect.")
                continue

            if not actual_targets_for_this_effect and target_scope != "self": # Self target doesn't strictly need 'targets' list
                logger.warning(f"No valid targets found for effect '{effect_type}' with scope '{target_scope}' in ability '{db_ability.static_id}'.")
                continue

            for target_individual in actual_targets_for_this_effect:
                target_individual_type_str = "player" if isinstance(target_individual, Player) else "npc"

                if effect_type == "damage":
                    raw_amount = effect_data.get("amount", 0)
                    damage_amount = raw_amount
                    # If raw_amount is a string, try to fetch it from RuleConfig
                    if isinstance(raw_amount, str):
                        rule_val = await get_rule(session, guild_id, raw_amount)
                        if isinstance(rule_val, int):
                            damage_amount = rule_val
                        else:
                            logger.warning(f"RuleConfig key '{raw_amount}' for damage amount did not return an integer. Using default from properties_json or 0.")
                            # Attempt to parse original raw_amount as int if it was a string but not a valid rule key
                            try: damage_amount = int(raw_amount)
                            except ValueError: damage_amount = 0

                    if not isinstance(damage_amount, int) or damage_amount < 0: # Damage should be positive or zero
                        logger.warning(f"Invalid damage_amount '{damage_amount}' (resolved from '{raw_amount}') for ability '{db_ability.static_id}'. Skipping damage effect.")
                        continue

                    # TODO: Implement advanced damage calculation using formulas from RuleConfig,
                    # involving caster stats (e.g., caster.strength, caster.spell_power)
                    # and target stats (e.g., target.armor, target.fire_resistance).
                    # Example: damage_formula_key = effect_data.get("damage_formula_key")
                    # if damage_formula_key: damage_amount = calculate_value_from_formula(session, guild_id, damage_formula_key, caster, target_individual)

                    if damage_amount > 0: # Only apply if there's actual damage
                        damage_applied = change_entity_hp(target_individual, -damage_amount)
                        if damage_applied:
                            logger.info(f"Dealt {damage_amount} {effect_data.get('damage_type','physical')} damage to {target_individual_type_str} ID {target_individual.id}")
                            outcome.damage_dealt.append(DamageDetail(
                                target_entity_id=target_individual.id,
                                target_entity_type=target_individual_type_str,
                                amount=damage_amount,
                                damage_type=effect_data.get("damage_type")
                            ))
                        else:
                            logger.warning(f"Failed to apply damage to {target_individual_type_str} ID {target_individual.id} using change_entity_hp.")

                elif effect_type == "apply_status":
                    status_to_apply_static_id = effect_data.get("status_static_id")
                    raw_duration = effect_data.get("duration") # Can be int or string (RuleConfig key)
                    status_duration = raw_duration

                    if isinstance(raw_duration, str):
                        rule_val = await get_rule(session, guild_id, raw_duration)
                        if isinstance(rule_val, int):
                            status_duration = rule_val
                        else:
                            logger.warning(f"RuleConfig key '{raw_duration}' for status duration did not return an integer. Using default from properties_json.")
                            try: status_duration = int(raw_duration) # Attempt to parse original
                            except ValueError: status_duration = None # Or some default like 1 if parsing fails

                    if status_duration is not None and (not isinstance(status_duration, int) or status_duration < 0):
                        logger.warning(f"Invalid status_duration '{status_duration}' (resolved from '{raw_duration}') for ability '{db_ability.static_id}'. Status may not apply correctly.")
                        status_duration = None # Or a default valid duration like 1 turn

                    # TODO: Implement success chance for status application based on RuleConfig or stats.
                    # Example: success_chance_key = effect_data.get("success_chance_key") -> calculate success...

                    if status_to_apply_static_id:
                        applied_successfully = await apply_status(
                            session, guild_id,
                            target_individual.id, target_individual_type_str,
                            status_to_apply_static_id, status_duration, # Pass potentially resolved duration
                            source_ability_id=db_ability.id,
                            source_entity_id=caster.id,
                            source_entity_type=entity_type
                        )
                        if applied_successfully:
                             outcome.applied_statuses.append(AppliedStatusDetail(
                                 status_static_id=status_to_apply_static_id,
                                 target_entity_id=target_individual.id,
                                 target_entity_type=target_individual_type_str,
                                 duration=status_duration # Log the duration that was used
                             ))
                        else:
                            logger.warning(f"Failed to apply status {status_to_apply_static_id} from ability {db_ability.static_id} to {target_individual_type_str} ID {target_individual.id}")

                elif effect_type == "healing":
                    raw_amount = effect_data.get("amount", 0)
                    healing_amount = raw_amount
                    if isinstance(raw_amount, str):
                        rule_val = await get_rule(session, guild_id, raw_amount)
                        if isinstance(rule_val, int):
                            healing_amount = rule_val
                        else:
                            logger.warning(f"RuleConfig key '{raw_amount}' for healing amount did not return an integer. Using default from properties_json or 0.")
                            try: healing_amount = int(raw_amount)
                            except ValueError: healing_amount = 0

                    if not isinstance(healing_amount, int) or healing_amount <= 0:
                        logger.warning(f"Invalid healing_amount '{healing_amount}' (resolved from '{raw_amount}') for ability '{db_ability.static_id}'. Skipping healing effect.")
                        continue

                    # TODO: Implement advanced healing calculation using formulas from RuleConfig,
                    # involving caster stats (e.g., caster.wisdom, caster.healing_power)
                    # and potentially target's max HP for percentage-based heals.
                    # Example: healing_formula_key = effect_data.get("healing_formula_key") ...

                    if healing_amount > 0: # Only apply if there's actual healing
                        healed_successfully = change_entity_hp(target_individual, healing_amount)
                        if healed_successfully:
                            actual_hp_after_heal = get_entity_hp(target_individual)
                            logger.info(f"Healed {target_individual_type_str} ID {target_individual.id} for {healing_amount} HP. Current HP: {actual_hp_after_heal}")
                            outcome.healing_done.append(HealingDetail(
                                target_entity_id=target_individual.id,
                                target_entity_type=target_individual_type_str,
                                amount=healing_amount
                            ))
                        else:
                            logger.warning(f"Failed to apply healing to {target_individual_type_str} ID {target_individual.id} using change_entity_hp.")

    # --- End of Effects Application ---

    outcome.success = True
    outcome.message = f"Ability '{db_ability.static_id}' processed successfully."

    log_details = {
        "caster_id": caster.id,
        "caster_type": entity_type,
        "ability_id": db_ability.id,
        "ability_static_id": db_ability.static_id,
        "targets": [{"id": t.id, "type": "player" if isinstance(t, Player) else "npc"} for t in targets],
        "outcome_summary": outcome.message,
        "damage_dealt": [d.model_dump() for d in outcome.damage_dealt],
        "healing_done": [h.model_dump() for h in outcome.healing_done],
        "statuses_applied": [s.model_dump() for s in outcome.applied_statuses],
        "caster_updates": [cu.model_dump() for cu in outcome.caster_updates]
    }
    outcome.log_event_details = log_details

    event_player_id = caster.id if isinstance(caster, Player) else None
    if not event_player_id and targets and isinstance(targets[0], Player):
        event_player_id = targets[0].id

    await log_event(
        session=session,
        guild_id=guild_id,
        event_type=EventType.ABILITY_USED.value,
        details_json=log_details,
        player_id=event_player_id,
        location_id=caster.current_location_id if hasattr(caster, 'current_location_id') else None
    )
    return outcome


async def apply_status(
    session: AsyncSession,
    guild_id: int,
    entity_id: int,
    entity_type: str,
    status_static_id: str,
    duration: Optional[int] = None,
    source_ability_id: Optional[int] = None,
    source_entity_id: Optional[int] = None,
    source_entity_type: Optional[str] = None
) -> bool:
    db_status_effect = await status_effect_crud.get_by_static_id(session, static_id=status_static_id, guild_id=guild_id)
    if not db_status_effect:
        logger.error(f"StatusEffect definition '{status_static_id}' not found for apply_status.")
        return False

    target_entity = await _get_entity(session, guild_id, entity_id, entity_type)
    if not target_entity:
        logger.error(f"Entity {entity_type} ID {entity_id} not found for applying status '{status_static_id}'.")
        return False

    owner_type_enum_val = RelationshipEntityType(entity_type.lower())

    # Instantiate then set attributes to avoid TypeError with SQLAlchemy constructor
    active_status = ActiveStatusEffect()
    active_status.entity_id = target_entity.id # Corrected: owner_id -> entity_id
    active_status.entity_type = owner_type_enum_val.value # Corrected: owner_type -> entity_type, and use .value
    active_status.status_effect_id = db_status_effect.id
    active_status.guild_id = guild_id
    active_status.duration_turns = duration
    active_status.remaining_turns = duration # Initialize remaining_turns with the full duration
    active_status.source_ability_id = source_ability_id
    active_status.source_entity_id = source_entity_id
    if source_entity_type:
        try:
            active_status.source_entity_type = RelationshipEntityType(source_entity_type.lower()).value
        except ValueError:
            logger.warning(f"Invalid source_entity_type '{source_entity_type}' for ActiveStatusEffect. Setting to None.")
            active_status.source_entity_type = None # Or handle as an error
    else:
        active_status.source_entity_type = None


    # Check for existing active status of the same type on the target
    existing_active_status_stmt = select(ActiveStatusEffect).where(
        ActiveStatusEffect.entity_id == target_entity.id,
        ActiveStatusEffect.entity_type == owner_type_enum_val.value,
        ActiveStatusEffect.status_effect_id == db_status_effect.id,
        ActiveStatusEffect.guild_id == guild_id
    )
    existing_statuses_result = await session.execute(existing_active_status_stmt)
    existing_status_instance = existing_statuses_result.scalars().first()

    is_stackable = db_status_effect.properties_json.get("stackable", False)
    max_stacks = db_status_effect.properties_json.get("max_stacks", 1 if is_stackable else 1)
    can_refresh_duration_non_stackable = db_status_effect.properties_json.get("duration_refresh", False) # For non-stackable

    action_taken = False # Flag to track if any change was made that warrants logging success

    if existing_status_instance:
        existing_custom_props = existing_status_instance.custom_properties_json or {}
        current_stacks = existing_custom_props.get("current_stacks", 1)

        if is_stackable:
            if current_stacks < max_stacks:
                current_stacks += 1
                existing_custom_props["current_stacks"] = current_stacks
                existing_status_instance.custom_properties_json = existing_custom_props

                if db_status_effect.properties_json.get("refresh_duration_on_stack_gain", True):
                    existing_status_instance.duration_turns = duration
                    existing_status_instance.remaining_turns = duration
                existing_status_instance.applied_at = func.now() # type: ignore[assignment]
                existing_status_instance.source_ability_id = source_ability_id # Update source
                existing_status_instance.source_entity_id = source_entity_id
                if source_entity_type:
                    try: existing_status_instance.source_entity_type = RelationshipEntityType(source_entity_type.lower()).value
                    except ValueError: existing_status_instance.source_entity_type = None
                else: existing_status_instance.source_entity_type = None

                session.add(existing_status_instance)
                logger.info(f"Incremented stack for status '{db_status_effect.static_id}' to {current_stacks}/{max_stacks} on {entity_type} ID {entity_id}.")
                action_taken = True
            elif db_status_effect.properties_json.get("refresh_duration_at_max_stacks", True): # At max stacks, check if refresh is allowed
                existing_status_instance.duration_turns = duration
                existing_status_instance.remaining_turns = duration
                existing_status_instance.applied_at = func.now() # type: ignore[assignment]
                existing_status_instance.source_ability_id = source_ability_id # Update source
                existing_status_instance.source_entity_id = source_entity_id
                if source_entity_type:
                    try: existing_status_instance.source_entity_type = RelationshipEntityType(source_entity_type.lower()).value
                    except ValueError: existing_status_instance.source_entity_type = None
                else: existing_status_instance.source_entity_type = None

                # Ensure custom_properties_json has current_stacks if somehow missing
                if "current_stacks" not in existing_custom_props:
                    existing_custom_props["current_stacks"] = max_stacks
                    existing_status_instance.custom_properties_json = existing_custom_props

                session.add(existing_status_instance)
                logger.info(f"Refreshed duration for status '{db_status_effect.static_id}' at max stacks ({current_stacks}/{max_stacks}) on {entity_type} ID {entity_id}.")
                action_taken = True
            else:
                logger.info(f"Status '{db_status_effect.static_id}' at max stacks ({current_stacks}/{max_stacks}) on {entity_type} ID {entity_id}. No duration refresh configured at max.")
                # No action_taken, return False later if this is the only path
        elif can_refresh_duration_non_stackable: # Not stackable, but can refresh duration
            existing_status_instance.duration_turns = duration
            existing_status_instance.remaining_turns = duration
            existing_status_instance.applied_at = func.now() # type: ignore[assignment]
            existing_status_instance.source_ability_id = source_ability_id
            existing_status_instance.source_entity_id = source_entity_id
            if source_entity_type:
                 try: existing_status_instance.source_entity_type = RelationshipEntityType(source_entity_type.lower()).value
                 except ValueError: existing_status_instance.source_entity_type = None
            else: existing_status_instance.source_entity_type = None
            session.add(existing_status_instance)
            logger.info(f"Refreshed duration for non-stackable status '{db_status_effect.static_id}' (ActiveID: {existing_status_instance.id}) on {entity_type} ID {entity_id}.")
            action_taken = True
        else: # Not stackable and cannot refresh
            logger.info(f"Status '{db_status_effect.static_id}' already active on {entity_type} ID {entity_id} and cannot be refreshed or stacked. No action taken.")

        if action_taken:
            active_status = existing_status_instance # Use the updated instance for logging
        else:
            return False # No change made to existing status

    else: # No existing_status_instance, create a new one
        active_status.custom_properties_json = active_status.custom_properties_json or {}
        if is_stackable:
            active_status.custom_properties_json["current_stacks"] = 1

        session.add(active_status)
        # await session.flush() # Flushed later or before logging if active_status.id is needed by then
        action_taken = True
        logger.info(f"Applied new instance of status '{db_status_effect.static_id}' on {entity_type} ID {entity_id}" + (f" with 1/{max_stacks} stacks." if is_stackable else "."))

    if not action_taken: # Should have been caught by return False earlier, but as a safeguard
        return False

    await session.flush() # Ensure ID is available for logging, and all changes are persisted before log.

    log_payload_custom_props = active_status.custom_properties_json or {}
    logger.info(f"Status '{db_status_effect.static_id}' (ID: {db_status_effect.id}, ActiveID: {active_status.id}) applied/updated on {entity_type} ID {entity_id}. Stacks: {log_payload_custom_props.get('current_stacks', 'N/A') if is_stackable else 'Non-stackable'}.")

    event_player_id = target_entity.id if isinstance(target_entity, Player) else None
    if not event_player_id and source_entity_id and source_entity_type and source_entity_type.lower() == "player":
        event_player_id = source_entity_id

    log_details_status = {
        "target_id": target_entity.id,
        "target_type": entity_type,
        "status_effect_id": db_status_effect.id,
        "status_static_id": db_status_effect.static_id,
        "active_status_id": active_status.id,
        "duration": duration,
        "source_ability_id": source_ability_id,
        "source_entity_id": source_entity_id,
        "source_entity_type": source_entity_type
    }

    await log_event(
        session=session,
        guild_id=guild_id,
        event_type=EventType.STATUS_APPLIED.value,
        details_json=log_details_status,
        player_id=event_player_id,
        location_id=target_entity.current_location_id if hasattr(target_entity, 'current_location_id') else None
    )
    return True
