from typing import Any, List, Optional, Dict, Union
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import datetime # ADDED IMPORT


from src.models import (
    Player,
    GeneratedNpc,
    Ability,
    StatusEffect,
    ActiveStatusEffect,
    GuildConfig,
    RuleConfig
)
from src.models.ability_outcomes import AbilityOutcomeDetails, AppliedStatusDetail, DamageDetail, HealingDetail, CasterUpdateDetail
from src.models.enums import RelationshipEntityType, EventType, PlayerStatus
# Removed CRUDBase import as it's not directly used here, but through specific cruds
from src.core.crud.crud_ability import ability_crud
from src.core.crud.crud_status_effect import status_effect_crud
from src.core.crud.crud_player import player_crud
from src.core.crud.crud_npc import npc_crud
from src.core.game_events import log_event
from src.core.rules import get_rule
from src.core.entity_stats_utils import get_entity_hp, set_entity_hp, change_entity_hp, get_entity_stat, set_entity_stat, change_entity_stat # Added
from sqlalchemy.sql import func # Added

logger = logging.getLogger(__name__)

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

    targets: List[Union[Player, GeneratedNpc]] = []
    if target_entity_ids and target_entity_types and len(target_entity_ids) == len(target_entity_types):
        for i, target_id in enumerate(target_entity_ids):
            target_type = target_entity_types[i]
            target_entity = await _get_entity(session, guild_id, target_id, target_type)
            if target_entity: targets.append(target_entity)

    logger.info(f"Ability '{db_ability.static_id}' (ID: {db_ability.id}) activated by {entity_type} ID {entity_id} on {len(targets)} targets.")

    # --- Start of MVP Ability Logic ---
    # For MVP, we'll assume properties_json might have:
    # "cost": {"resource": "mana", "amount": 10}
    # "effects": [
    #   {"type": "damage", "amount": 15, "damage_type": "fire", "target": "first"},
    #   {"type": "apply_status", "status_static_id": "burning", "duration": 3, "target": "first"}
    # ]

    # TODO: Implement check for ability availability for the caster (e.g., learned abilities)
    # TODO: Implement cooldown checks

    # 1. Check and apply costs
    if db_ability.properties_json and "cost" in db_ability.properties_json:
        cost_info = db_ability.properties_json["cost"]
        resource_type = cost_info.get("resource")
        amount_required = cost_info.get("amount")

        if resource_type and isinstance(amount_required, int) and amount_required > 0:
            current_resource_value = get_entity_stat(caster, resource_type)
            if not isinstance(current_resource_value, int) or current_resource_value < amount_required:
                outcome.message = f"Not enough {resource_type} to use ability '{db_ability.static_id}'. Required: {amount_required}, Available: {current_resource_value if isinstance(current_resource_value, int) else 0}."
                outcome.success = False
                # No log_event here as the ability wasn't successfully used.
                # Consider a different type of log entry if "failed attempts" should be logged.
                return outcome

            # Deduct resource
            if not change_entity_stat(caster, resource_type, -amount_required):
                logger.error(f"Failed to deduct {resource_type} from {entity_type} ID {entity_id} for ability {db_ability.static_id}.")
                # This case should ideally not happen if get_entity_stat and current_resource_value check passed.
                # But as a safeguard:
                outcome.message = f"Error processing resource cost for ability '{db_ability.static_id}'."
                outcome.success = False
                return outcome

            logger.info(f"Caster {entity_type} ID {entity_id} paid {amount_required} of {resource_type} for ability '{db_ability.static_id}'.")
            outcome.caster_updates.append(CasterUpdateDetail(resource_type=resource_type, change= -amount_required))
        elif amount_required == 0: # No cost
             logger.info(f"Ability '{db_ability.static_id}' has no resource cost.")
        else:
            logger.warning(f"Invalid cost_info for ability '{db_ability.static_id}': {cost_info}")

    # 2. Check Activation Conditions from RuleConfig (Example)
    activation_conditions_key = f"ability_rules:{db_ability.static_id}:activation_conditions"
    activation_conditions = await get_rule(session, guild_id, activation_conditions_key) # activation_conditions might be a list or dict

    if activation_conditions and isinstance(activation_conditions, list): # Assuming conditions are a list of strings
        if "caster_must_be_in_combat" in activation_conditions:
            caster_combat_status = None
            if isinstance(caster, Player):
                # Assuming PlayerStatus.COMBAT enum member exists and is comparable
                caster_combat_status = caster.current_status == PlayerStatus.COMBAT.value # Compare with the enum's value
            elif isinstance(caster, GeneratedNpc):
                # Assuming NPC status is stored in properties_json['stats']['status']
                npc_status_str = get_entity_stat(caster, "status")
                caster_combat_status = npc_status_str == "in_combat" # Or use an enum/constant

            if not caster_combat_status:
                outcome.message = f"Ability '{db_ability.static_id}' can only be used while in combat."
                outcome.success = False
                return outcome

        # Add more condition checks here as needed based on RuleConfig structure
        # e.g., "requires_specific_status_on_caster": "status_xyz_static_id"
        # e.g., "target_must_be_enemy": true

    # 3. Apply effects
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
                    # TODO: Get damage amount from RuleConfig if formula-based
                    damage_amount = effect_data.get("amount", 0)
                    # TODO: Apply damage to target_individual.current_hp or target_individual.properties_json['stats']['hp']
                    # For now, just log and add to outcome
                    # Use new utility function to change HP
                    damage_applied = change_entity_hp(target_individual, -damage_amount) # Negative amount for damage
                    if damage_applied:
                        logger.info(f"Dealt {damage_amount} {effect_data.get('damage_type','physical')} damage to {target_individual_type_str} ID {target_individual.id}")
                        outcome.damage_dealt.append(DamageDetail(
                            target_entity_id=target_individual.id,
                            target_entity_type=target_individual_type_str,
                            amount=damage_amount, # Report positive damage amount
                            damage_type=effect_data.get("damage_type")
                        ))
                    else:
                        logger.warning(f"Failed to apply damage to {target_individual_type_str} ID {target_individual.id} using change_entity_hp.")
                    # else: logger.warning for unhandled hp update

                    # logger.info(f"Dealt {damage_amount} {effect_data.get('damage_type','physical')} damage to {target_individual_type_str} ID {target_individual.id}")
                    # outcome.damage_dealt.append(DamageDetail( # This is now handled above
                    #     target_entity_id=target_individual.id,
                    #     target_entity_type=target_individual_type_str,
                    #     amount=damage_amount,
                    #     damage_type=effect_data.get("damage_type")
                    # )) # Removed extra parenthesis if the block is commented

                elif effect_type == "apply_status":
                    status_to_apply_static_id = effect_data.get("status_static_id")
                    status_duration = effect_data.get("duration")
                    if status_to_apply_static_id:
                        applied_successfully = await apply_status(
                            session, guild_id,
                            target_individual.id, target_individual_type_str,
                            status_to_apply_static_id, status_duration,
                            source_ability_id=db_ability.id,
                            source_entity_id=caster.id,
                            source_entity_type=entity_type
                        )
                        if applied_successfully:
                             outcome.applied_statuses.append(AppliedStatusDetail(
                                 status_static_id=status_to_apply_static_id,
                                 target_entity_id=target_individual.id,
                                 target_entity_type=target_individual_type_str,
                                 duration=status_duration
                             ))
                        else:
                            logger.warning(f"Failed to apply status {status_to_apply_static_id} from ability {db_ability.static_id} to {target_individual_type_str} ID {target_individual.id}")

                elif effect_type == "healing":
                    healing_amount = effect_data.get("amount", 0)
                    if not isinstance(healing_amount, int) or healing_amount <= 0:
                        logger.warning(f"Invalid healing_amount '{healing_amount}' for ability '{db_ability.static_id}'. Skipping healing effect.")
                        continue

                    # TODO: Get healing amount/formula from RuleConfig, consider caster stats, target max HP
                    healed_successfully = change_entity_hp(target_individual, healing_amount) # Positive amount for healing

                    if healed_successfully:
                        actual_hp_after_heal = get_entity_hp(target_individual)
                        logger.info(f"Healed {target_individual_type_str} ID {target_individual.id} for {healing_amount} HP. Current HP: {actual_hp_after_heal}")
                        outcome.healing_done.append(HealingDetail(
                            target_entity_id=target_individual.id,
                            target_entity_type=target_individual_type_str,
                            amount=healing_amount # Report positive healing amount
                        ))
                    else:
                        logger.warning(f"Failed to apply healing to {target_individual_type_str} ID {target_individual.id} using change_entity_hp.")

    # --- End of MVP Ability Logic ---

    outcome.success = True
    outcome.message = f"Ability '{db_ability.static_id}' processed (MVP)."

    log_details = {
        "caster_id": caster.id,
        "caster_type": entity_type,
        "ability_id": db_ability.id,
        "ability_static_id": db_ability.static_id,
        "targets": [{"id": t.id, "type": "player" if isinstance(t, Player) else "npc" } for t in targets],
        "outcome_summary": outcome.message,
        "damage_dealt": [d.model_dump() for d in outcome.damage_dealt],
        "healing_done": [h.model_dump() for h in outcome.healing_done],
        "statuses_applied": [s.model_dump() for s in outcome.applied_statuses],
        "caster_updates": [cu.model_dump() for cu in outcome.caster_updates]
    }
    outcome.log_event_details = log_details

    # Ensure the final outcome message reflects success if no specific failure message was set
    if outcome.success and outcome.message == "Ability activation failed.": # Default initial message
        outcome.message = f"Ability '{db_ability.static_id}' processed successfully."


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

    can_refresh_duration = db_status_effect.properties_json.get("duration_refresh", False)
    # TODO: Add stackable logic here if db_status_effect.properties_json.get("stackable", False)

    if existing_status_instance:
        if can_refresh_duration:
            existing_status_instance.duration_turns = duration # Update to new full duration
            existing_status_instance.remaining_turns = duration # Reset remaining turns
            existing_status_instance.applied_at = func.now() # type: ignore[assignment] # Use SQLAlchemy func.now
            existing_status_instance.source_ability_id = source_ability_id # Update source if it changed
            existing_status_instance.source_entity_id = source_entity_id
            if source_entity_type:
                 try: existing_status_instance.source_entity_type = RelationshipEntityType(source_entity_type.lower()).value
                 except ValueError: existing_status_instance.source_entity_type = None
            else: existing_status_instance.source_entity_type = None

            session.add(existing_status_instance)
            await session.flush()
            logger.info(f"Refreshed duration for status '{db_status_effect.static_id}' (ActiveID: {existing_status_instance.id}) on {entity_type} ID {entity_id}.")
            # Update log_details to reflect refresh? Or is the general STATUS_APPLIED fine?
            # For now, the existing log_event after this block will log the "application" or "refresh".
            # To be more specific, we might need a STATUS_REFRESHED event type.
            active_status = existing_status_instance # Use the existing instance for logging details
        else:
            # Status exists, but cannot be refreshed. Do nothing.
            logger.info(f"Status '{db_status_effect.static_id}' already active on {entity_type} ID {entity_id} and cannot be refreshed. No action taken.")
            return False # Indicate that no new status was effectively applied or old one changed in a way that needs re-logging as "new"
    else:
        # No existing status, add the new one
        session.add(active_status)
        await session.flush() # To get active_status.id for logging if needed immediately

    logger.info(f"Status '{db_status_effect.static_id}' (ID: {db_status_effect.id}, ActiveID: {active_status.id}) applied/refreshed on {entity_type} ID {entity_id}.")

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
