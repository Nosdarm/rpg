from typing import Any, List, Optional, Dict, Union
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select


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
from src.models.enums import RelationshipEntityType, EventType
from src.core.crud_base_definitions import CRUDBase # Corrected import
from src.core.crud.crud_ability import ability_crud
from src.core.crud.crud_status_effect import status_effect_crud
from src.core.crud.crud_player import player_crud
from src.core.crud.crud_npc import npc_crud
from src.core.game_events import log_event
from src.core.rules import get_rule

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

async def activate_ability(
    session: AsyncSession,
    guild_id: int,
    entity_id: int, # ID of the entity using the ability (Player or NPC)
    entity_type: str, # "player" or "npc"
    ability_id: int,
    target_entity_ids: Optional[List[int]] = None,
    target_entity_types: Optional[List[str]] = None # Parallel to target_entity_ids
) -> AbilityOutcomeDetails:
    """
    Handles the activation of an ability by an entity.
    """
    outcome = AbilityOutcomeDetails(success=False, message="Ability activation failed.")

    # 1. Load Ability
    db_ability = await ability_crud.get(session, id=ability_id) # Abilities can be global or guild-specific
    if not db_ability:
        outcome.message = "Ability not found."
        return outcome
    if db_ability.guild_id is not None and db_ability.guild_id != guild_id:
        outcome.message = "Ability not found for this guild."
        return outcome

    outcome.raw_ability_properties = db_ability.properties_json

    # 2. Load Caster Entity
    caster = await _get_entity(session, guild_id, entity_id, entity_type)
    if not caster:
        outcome.message = f"{entity_type.capitalize()} (caster) not found."
        return outcome

    # 3. Load Target Entities (if any)
    targets: List[Union[Player, GeneratedNpc]] = []
    if target_entity_ids and target_entity_types and len(target_entity_ids) == len(target_entity_types):
        for i, target_id in enumerate(target_entity_ids):
            target_type = target_entity_types[i]
            target_entity = await _get_entity(session, guild_id, target_id, target_type)
            if target_entity:
                targets.append(target_entity)
            else:
                logger.warning(f"Target entity {target_type} ID {target_id} not found for ability {db_ability.static_id}.")

    # Placeholder for actual ability logic
    logger.info(f"Ability '{db_ability.static_id}' activated by {entity_type} ID {entity_id} on {len(targets)} targets.")
    # TODO: Implement checks (resources, cooldowns, conditions based on RuleConfig)
    # TODO: Implement effects (damage, healing, status application based on db_ability.properties_json and RuleConfig)
    # TODO: Update caster and target states
    # TODO: Call log_event

    outcome.success = True # Placeholder
    outcome.message = f"Ability '{db_ability.static_id}' activated successfully (MVP)." # Placeholder

    # Example of logging (actual details would come from effect processing)
    # await log_event(
    #     session=session,
    #     guild_id=guild_id,
    #     event_type=EventType.ABILITY_USED, # Needs to be added to EventType enum
    #     details_json={
    #         "caster_id": caster.id,
    #         "caster_type": entity_type,
    #         "ability_id": db_ability.id,
    #         "ability_static_id": db_ability.static_id,
    #         "targets": [{"id": t.id, "type": t.__class__.__name__.lower()} for t in targets],
    #         "outcome": outcome.model_dump()
    #     },
    #     player_id=caster.id if isinstance(caster, Player) else None,
    #     # location_id=caster.current_location_id # If applicable
    # )

    return outcome


async def apply_status(
    session: AsyncSession,
    guild_id: int,
    entity_id: int, # ID of the entity receiving the status
    entity_type: str, # "player" or "npc"
    status_static_id: str,
    duration: Optional[int] = None, # Duration in turns or seconds, interpretation depends on rules
    source_ability_id: Optional[int] = None,
    source_entity_id: Optional[int] = None, # Entity that caused this status
    source_entity_type: Optional[str] = None
) -> bool:
    """
    Applies a status effect to an entity.
    """
    # 1. Load StatusEffect definition
    # Statuses can be global (guild_id is None) or guild-specific
    stmt = select(StatusEffect).where(StatusEffect.static_id == status_static_id)
    results = await session.execute(stmt)
    possible_statuses = results.scalars().all()

    db_status_effect: Optional[StatusEffect] = None
    if possible_statuses:
        # Prefer guild-specific if available, else global
        guild_specific = next((s for s in possible_statuses if s.guild_id == guild_id), None)
        if guild_specific:
            db_status_effect = guild_specific
        else:
            db_status_effect = next((s for s in possible_statuses if s.guild_id is None), None)

    if not db_status_effect:
        logger.error(f"StatusEffect definition with static_id '{status_static_id}' not found for guild {guild_id} or globally.")
        return False

    # 2. Load Target Entity
    target_entity = await _get_entity(session, guild_id, entity_id, entity_type)
    if not target_entity:
        logger.error(f"Entity {entity_type} ID {entity_id} not found for applying status '{status_static_id}'.")
        return False

    # 3. Create ActiveStatusEffect record
    # Check for existing non-stackable status, etc. (placeholder)

    owner_type_enum_val = RelationshipEntityType.PLAYER if entity_type.lower() == "player" else RelationshipEntityType.NPC

    active_status = ActiveStatusEffect(
        owner_id=target_entity.id,
        owner_type=owner_type_enum_val, # Ensure this matches your enum values
        status_effect_id=db_status_effect.id,
        guild_id=guild_id, # ActiveStatusEffect is always guild-scoped
        duration=duration,
        source_ability_id=source_ability_id,
        source_entity_id=source_entity_id,
        # source_entity_type needs to be RelationshipEntityType enum if that's what model expects
    )
    if source_entity_type:
        try:
            active_status.source_entity_type = RelationshipEntityType(source_entity_type.lower())
        except ValueError:
            logger.warning(f"Invalid source_entity_type '{source_entity_type}' for ActiveStatusEffect. Setting to None.")
            active_status.source_entity_type = None


    session.add(active_status)
    await session.flush() # To get active_status.id for logging if needed immediately

    logger.info(f"Status '{db_status_effect.static_id}' applied to {entity_type} ID {entity_id}.")

    # TODO: Call log_event
    # await log_event(
    #     session=session,
    #     guild_id=guild_id,
    #     event_type=EventType.STATUS_APPLIED, # Needs to be added
    #     details_json={
    #         "target_id": target_entity.id,
    #         "target_type": entity_type,
    #         "status_effect_id": db_status_effect.id,
    #         "status_static_id": db_status_effect.static_id,
    #         "duration": duration,
    #         "source_ability_id": source_ability_id,
    #         "active_status_id": active_status.id
    #     },
    #     player_id=target_entity.id if isinstance(target_entity, Player) else None,
    #     # location_id=target_entity.current_location_id # If applicable
    # )

    return True

# TODO: Implement remove_status API
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

    await session.delete(active_status_effect)
    await session.flush()
    logger.info(f"ActiveStatusEffect ID {active_status_id} removed.")
    # TODO: log_event
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
# For now, using direct model operations or assuming they will be available.
# For Ability and StatusEffect, specific finders by static_id + guild_id/global might be needed.
# For _get_entity, player_crud and npc_crud are assumed to exist.

# Example for ability_crud (to be placed in its own file)
# from src.models import Ability
# from src.core.crud_base_definitions import CRUDBase
# from sqlalchemy.future import select
# from sqlalchemy.ext.asyncio import AsyncSession
# from typing import Optional
# class CRUDAbility(CRUDBase[Ability]):
#     async def get_by_static_id(self, db: AsyncSession, *, static_id: str, guild_id: Optional[int] = None) -> Optional[Ability]:
#         # This logic needs to handle global (guild_id IS NULL) vs specific guild_id
#         # For simplicity here, assuming direct ID lookup or that static_id is globally unique for now
#         # A more robust version would query considering guild_id and nullable guild_id for globals
#         stmt = select(self.model).where(self.model.static_id == static_id)
#         if guild_id:
#             stmt = stmt.where(self.model.guild_id == guild_id)
#         else: # For global abilities
#             stmt = stmt.where(self.model.guild_id.is_(None))
#
#         results = await db.execute(stmt)
#         return results.scalars().first()

# ability_crud = CRUDAbility(Ability)

# Example for status_effect_crud
# from src.models import StatusEffect
# ...
# class CRUDStatusEffect(CRUDBase[StatusEffect]):
#      async def get_by_static_id(self, db: AsyncSession, *, static_id: str, guild_id: Optional[int] = None) -> Optional[StatusEffect]:
#        # Similar logic to CRUDAbility.get_by_static_id
#        pass
# status_effect_crud = CRUDStatusEffect(StatusEffect)

# Actual CRUD instances will be imported from their respective files once created.
# For now, `ability_crud.get` will be a placeholder.
# `status_effect_crud` will be a placeholder.

# A more concrete way to get Ability and StatusEffect without dedicated CRUDs yet for get_by_static_id:
async def get_ability_by_id_or_static_id(session: AsyncSession, ability_identifier: Union[int, str], guild_id: Optional[int]=None) -> Optional[Ability]:
    if isinstance(ability_identifier, int):
        return await session.get(Ability, ability_identifier)

    # Search by static_id, preferring guild-specific then global
    stmt = select(Ability).where(Ability.static_id == ability_identifier)
    results = await session.execute(stmt)
    possible_abilities = results.scalars().all()
    if not possible_abilities: return None

    if guild_id:
        guild_specific = next((a for a in possible_abilities if a.guild_id == guild_id), None)
        if guild_specific: return guild_specific

    return next((a for a in possible_abilities if a.guild_id is None), None)


async def get_status_effect_by_static_id(session: AsyncSession, static_id: str, guild_id: Optional[int]=None) -> Optional[StatusEffect]:
    stmt = select(StatusEffect).where(StatusEffect.static_id == static_id)
    results = await session.execute(stmt)
    possible_statuses = results.scalars().all()
    if not possible_statuses: return None

    if guild_id:
        guild_specific = next((s for s in possible_statuses if s.guild_id == guild_id), None)
        if guild_specific: return guild_specific

    return next((s for s in possible_statuses if s.guild_id is None), None)

# Re-wire activate_ability and apply_status to use these temp direct getters
# (This is a temporary step until CRUDs are fully fleshed out or if we decide to use such helpers directly)

async def activate_ability_v2( # Renamed to avoid clash while showing evolution
    session: AsyncSession,
    guild_id: int,
    entity_id: int,
    entity_type: str,
    ability_identifier: Union[int, str], # Can be ID or static_id
    target_entity_ids: Optional[List[int]] = None,
    target_entity_types: Optional[List[str]] = None
) -> AbilityOutcomeDetails:
    outcome = AbilityOutcomeDetails(success=False, message="Ability activation failed.")

    db_ability = await get_ability_by_id_or_static_id(session, ability_identifier, guild_id)
    if not db_ability:
        outcome.message = f"Ability '{ability_identifier}' not found."
        return outcome
    # Ensure guild consistency if ability is guild_specific
    if db_ability.guild_id is not None and db_ability.guild_id != guild_id:
        outcome.message = f"Ability '{ability_identifier}' not found for this guild." # Should be caught by get_ability...
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

    # 1. Check and apply costs (Placeholder)
    if db_ability.properties_json and "cost" in db_ability.properties_json:
        cost_info = db_ability.properties_json["cost"]
        # TODO: Deduct cost_info["amount"] of cost_info["resource"] from caster
        # For now, log it
        logger.info(f"Caster needs to pay {cost_info.get('amount')} of {cost_info.get('resource')}")
        outcome.caster_updates.append(CasterUpdateDetail(resource_type=cost_info.get('resource', 'unknown'), change= -1 * cost_info.get('amount',0)))


    # 2. Apply effects (Placeholder for complex targeting and RuleConfig)
    if db_ability.properties_json and "effects" in db_ability.properties_json:
        for effect_data in db_ability.properties_json.get("effects", []):
            effect_type = effect_data.get("type")
            # MVP: assume "first" target or self if no targets and effect implies self
            current_targets = targets # Basic targeting - apply to all specified targets
            if not current_targets and effect_data.get("target") == "self": # Example for self-target
                 current_targets = [caster]

            for target_individual in current_targets: # Iterate over chosen targets for this effect
                target_individual_type = "player" if isinstance(target_individual, Player) else "npc"

                if effect_type == "damage":
                    # TODO: Get damage amount from RuleConfig if formula-based
                    damage_amount = effect_data.get("amount", 0)
                    # TODO: Apply damage to target_individual.current_hp or target_individual.stats_json['hp']
                    # For now, just log and add to outcome
                    logger.info(f"Dealt {damage_amount} {effect_data.get('damage_type','physical')} damage to {target_individual_type} ID {target_individual.id}")
                    outcome.damage_dealt.append(DamageDetail(
                        target_entity_id=target_individual.id,
                        target_entity_type=target_individual_type,
                        amount=damage_amount,
                        damage_type=effect_data.get("damage_type")
                    ))

                elif effect_type == "apply_status":
                    status_to_apply_static_id = effect_data.get("status_static_id")
                    status_duration = effect_data.get("duration")
                    if status_to_apply_static_id:
                        applied_successfully = await apply_status_v2( # use v2 of apply_status
                            session, guild_id,
                            target_individual.id, target_individual_type,
                            status_to_apply_static_id, status_duration,
                            source_ability_id=db_ability.id,
                            source_entity_id=caster.id,
                            source_entity_type=entity_type
                        )
                        if applied_successfully:
                             outcome.applied_statuses.append(AppliedStatusDetail(
                                 status_static_id=status_to_apply_static_id,
                                 target_entity_id=target_individual.id,
                                 target_entity_type=target_individual_type,
                                 duration=status_duration
                             ))
                        else:
                            logger.warning(f"Failed to apply status {status_to_apply_static_id} from ability {db_ability.static_id}")

                # TODO: Add "healing" effect type

    # --- End of MVP Ability Logic ---

    outcome.success = True
    outcome.message = f"Ability '{db_ability.static_id}' processed (MVP)."

    # Actual Logging
    log_details = {
        "caster_id": caster.id,
        "caster_type": entity_type,
        "ability_id": db_ability.id,
        "ability_static_id": db_ability.static_id,
        "targets": [{"id": t.id, "type": "player" if isinstance(t, Player) else "npc" } for t in targets],
        "outcome_summary": outcome.message,
        "damage_dealt": [d.model_dump() for d in outcome.damage_dealt],
        "statuses_applied": [s.model_dump() for s in outcome.applied_statuses],
        "caster_updates": [cu.model_dump() for cu in outcome.caster_updates]
    }
    outcome.log_event_details = log_details

    # Determine player_id for log_event
    event_player_id = caster.id if isinstance(caster, Player) else None
    if not event_player_id and targets: # If caster is NPC, check if first target is player
        if isinstance(targets[0], Player):
            event_player_id = targets[0].id

    await log_event(
        session=session,
        guild_id=guild_id,
        event_type=EventType.ABILITY_USED, # Will add this to EventType enum
        details_json=log_details,
        player_id=event_player_id, # Log relative to caster if player, or first target if player
        # location_id=caster.current_location_id # If applicable
    )
    return outcome


async def apply_status_v2( # Renamed
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
    db_status_effect = await get_status_effect_by_static_id(session, status_static_id, guild_id)
    if not db_status_effect:
        logger.error(f"StatusEffect definition '{status_static_id}' not found for apply_status.")
        return False

    target_entity = await _get_entity(session, guild_id, entity_id, entity_type)
    if not target_entity:
        logger.error(f"Entity {entity_type} ID {entity_id} not found for applying status '{status_static_id}'.")
        return False

    owner_type_enum_val = RelationshipEntityType(entity_type.lower())

    # Diagnostic: Instantiate then set attributes
    active_status = ActiveStatusEffect()
    active_status.owner_id = target_entity.id
    active_status.owner_type = owner_type_enum_val
    active_status.status_effect_id = db_status_effect.id
    active_status.guild_id = guild_id
    active_status.duration = duration
    active_status.source_ability_id = source_ability_id
    active_status.source_entity_id = source_entity_id

    if source_entity_type:
        try:
            active_status.source_entity_type = RelationshipEntityType(source_entity_type.lower())
        except ValueError:
            active_status.source_entity_type = None
            logger.warning(f"Invalid source_entity_type '{source_entity_type}' for ActiveStatusEffect. Set to None.")
    else:
        active_status.source_entity_type = None


    session.add(active_status)
    await session.flush()

    logger.info(f"Status '{db_status_effect.static_id}' (ID: {db_status_effect.id}, ActiveID: {active_status.id}) applied to {entity_type} ID {entity_id}.")

    # Determine player_id for log_event
    event_player_id = target_entity.id if isinstance(target_entity, Player) else None
    if not event_player_id and source_entity_id and source_entity_type and source_entity_type.lower() == "player":
        event_player_id = source_entity_id

    await log_event(
        session=session,
        guild_id=guild_id,
        event_type=EventType.STATUS_APPLIED, # Will add this to EventType enum
        details_json={
            "target_id": target_entity.id,
            "target_type": entity_type,
            "status_effect_id": db_status_effect.id,
            "status_static_id": db_status_effect.static_id,
            "active_status_id": active_status.id,
            "duration": duration,
            "source_ability_id": source_ability_id,
            "source_entity_id": source_entity_id,
            "source_entity_type": source_entity_type
        },
        player_id=event_player_id,
    )
    return True

# Placeholder for remove_status, using active_status_id from ActiveStatusEffect table
# async def remove_status_v2(...)
