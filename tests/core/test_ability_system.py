import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from typing import Optional, Union, List

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
import datetime

from backend.core.ability_system import activate_ability, apply_status, remove_status
from backend.models import Player, GeneratedNpc, Ability, StatusEffect, GuildConfig # Removed ActiveStatusEffect from here
from backend.models.status_effect import ActiveStatusEffect # Direct import
from backend.models.ability_outcomes import AbilityOutcomeDetails, DamageDetail, HealingDetail, AppliedStatusDetail, CasterUpdateDetail
from backend.models.enums import RelationshipEntityType, EventType, PlayerStatus

# Mock data factories
def _create_mock_player(player_id: int, guild_id: int, hp: int = 100, mana: int = 50, status: PlayerStatus = PlayerStatus.IDLE) -> Player:
    player = Player(id=player_id, guild_id=guild_id, discord_id=player_id * 10, name=f"TestPlayer{player_id}", current_hp=hp)
    player.current_status = status
    player.current_location_id = 1
    return player

def _create_mock_npc(npc_id: int, guild_id: int, hp: int = 80, mana: int = 30, status: str = "idle") -> GeneratedNpc:
    npc = GeneratedNpc(id=npc_id, guild_id=guild_id, name_i18n={"en": f"TestNPC{npc_id}"})
    npc.properties_json = {
        "stats": {"hp": hp, "mana": mana, "status": status},
    }
    # Make current_location_id accessible for _get_entity if it needs it from the top level of the object
    setattr(npc, 'current_location_id', npc.properties_json.get("current_location_id", 1)) # type: ignore # Default to 1 if not in json
    return npc

def _create_mock_ability(ability_id: int, static_id: str, guild_id: Optional[int] = None, cost: Optional[dict] = None, effects: Optional[list] = None) -> Ability:
    return Ability(
        id=ability_id,
        guild_id=guild_id,
        static_id=static_id,
        name_i18n={"en": static_id.replace("_", " ").title()},
        description_i18n={"en": "Test description"},
        properties_json={"cost": cost or {}, "effects": effects or []}
    )

def _create_mock_status_effect_def(status_id: int, static_id: str, guild_id: Optional[int] = None, props: Optional[dict] = None) -> StatusEffect:
    actual_guild_id = guild_id if guild_id is not None else 1
    return StatusEffect(
        id=status_id,
        guild_id=actual_guild_id,
        static_id=static_id,
        name_i18n={"en": static_id},
        properties_json=props or {}
    )

def _create_mock_active_status(active_id: int, status_effect_id: int, entity_id: int, entity_type: str, guild_id: int, duration: int = 3, applied_at_val = None) -> ActiveStatusEffect:
    if applied_at_val is None:
        applied_at_val = datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    return ActiveStatusEffect(
        id=active_id,
        status_effect_id=status_effect_id,
        entity_id=entity_id,
        entity_type=entity_type,
        guild_id=guild_id,
        duration_turns=duration,
        remaining_turns=duration,
        applied_at=applied_at_val,
        source_ability_id=None,
        source_entity_id=None,
        source_entity_type=None,
        custom_properties_json=None
    )

@pytest.fixture
def mock_session_no_existing_status() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    # The result of session.execute() is a Result object, not awaitable itself.
    mock_sql_alchemy_result = MagicMock()
    mock_scalars_result = MagicMock()
    mock_scalars_result.first.return_value = None # For .scalars().first()
    mock_sql_alchemy_result.scalars.return_value = mock_scalars_result

    # Async methods
    session.execute = AsyncMock(return_value=mock_sql_alchemy_result) # session.execute is awaitable
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    session.scalars = AsyncMock(return_value=mock_scalars_result)

    # Synchronous methods
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.delete = AsyncMock() # Changed to AsyncMock
    session.merge = MagicMock()
    session.expire = MagicMock()
    session.expunge = MagicMock()
    session.is_modified = MagicMock()
    session.begin = MagicMock()

    return session

@pytest.fixture
def mock_session_with_existing_status_factory():
    def _factory(existing_status_instance: Optional[ActiveStatusEffect]):
        session = AsyncMock(spec=AsyncSession)
        mock_sql_alchemy_result = MagicMock() # Result of execute
        mock_scalars_result = MagicMock()
        mock_scalars_result.first.return_value = existing_status_instance # For .scalars().first()
        mock_sql_alchemy_result.scalars.return_value = mock_scalars_result

        # Async methods
        session.execute = AsyncMock(return_value=mock_sql_alchemy_result) # session.execute is awaitable
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.flush = AsyncMock()
        session.rollback = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        session.scalars = AsyncMock(return_value=mock_scalars_result)

        # Synchronous methods
        session.add = MagicMock()
        session.add_all = MagicMock()
        session.delete = AsyncMock() # Corrected indentation here
        session.merge = MagicMock()
        session.expire = MagicMock()
        session.expunge = MagicMock()
        session.is_modified = MagicMock()
        session.begin = MagicMock()

        return session
    return _factory

COMMON_PATCH_BASE = 'backend.core.ability_system.'
PATCHES = {
    'log_event': patch(COMMON_PATCH_BASE + 'log_event', new_callable=AsyncMock),
    'get_rule': patch(COMMON_PATCH_BASE + 'get_rule', new_callable=AsyncMock),
    'ability_crud': patch(COMMON_PATCH_BASE + 'ability_crud', new_callable=AsyncMock), # Changed to AsyncMock
    '_get_entity': patch(COMMON_PATCH_BASE + '_get_entity', new_callable=AsyncMock),
    'get_entity_stat': patch(COMMON_PATCH_BASE + 'get_entity_stat'),
    'change_entity_stat': patch(COMMON_PATCH_BASE + 'change_entity_stat'),
    'get_entity_hp': patch(COMMON_PATCH_BASE + 'get_entity_hp'),
    'change_entity_hp': patch(COMMON_PATCH_BASE + 'change_entity_hp'),
    'status_effect_crud': patch(COMMON_PATCH_BASE + 'status_effect_crud', new_callable=AsyncMock), # Changed to AsyncMock
}

@pytest.mark.asyncio
async def test_activate_ability_simple_damage(mock_session_no_existing_status: AsyncSession):
    with PATCHES['log_event'] as mock_log_event, \
         PATCHES['get_rule'] as mock_get_rule, \
         PATCHES['ability_crud'] as mock_ability_crud, \
         PATCHES['_get_entity'] as mock_get_entity, \
         PATCHES['get_entity_stat'] as mock_get_stat, \
         PATCHES['change_entity_stat'] as mock_change_stat, \
         PATCHES['change_entity_hp'] as mock_change_hp:

        guild_id, caster_id, target_id, ability_id_val = 1, 10, 20, 100
        caster = _create_mock_player(caster_id, guild_id, mana=50)
        target = _create_mock_npc(target_id, guild_id, hp=80)

        mock_get_entity.side_effect = lambda _s, _gid, eid, _et: caster if eid == caster_id else target
        test_ability_obj = _create_mock_ability(ability_id_val, "fireball", guild_id=guild_id,
            cost={"resource": "mana", "amount": 10},
            effects=[{"type": "damage", "amount": 25, "target_scope": "first_target"}])
        mock_ability_crud.get.return_value = test_ability_obj
        mock_get_stat.return_value = 50
        mock_change_stat.return_value = True
        mock_change_hp.return_value = True
        mock_get_rule.return_value = None

        outcome = await activate_ability(mock_session_no_existing_status, guild_id, caster_id,
                                       RelationshipEntityType.PLAYER.value, ability_id_val,
                                       [target_id], [RelationshipEntityType.GENERATED_NPC.value])
        assert outcome.success is True
        mock_change_stat.assert_called_once_with(caster, "mana", -10)
        mock_change_hp.assert_called_once_with(target, -25)
        mock_log_event.assert_called_once()

@pytest.mark.asyncio
async def test_activate_ability_not_enough_resources(mock_session_no_existing_status: AsyncSession):
    with PATCHES['log_event'] as mock_log_event, \
         PATCHES['ability_crud'] as mock_ability_crud, \
         PATCHES['_get_entity'] as mock_get_entity, \
         PATCHES['get_entity_stat'] as mock_get_stat, \
         PATCHES['get_rule'] as mock_get_rule:

        guild_id, caster_id, ability_id_val = 1, 10, 101
        caster = _create_mock_player(caster_id, guild_id, mana=5)
        mock_get_entity.return_value = caster
        test_ability_obj = _create_mock_ability(ability_id_val, "icelance", cost={"resource": "mana", "amount": 10})
        mock_ability_crud.get.return_value = test_ability_obj
        mock_get_stat.return_value = 5
        mock_get_rule.return_value = None

        outcome = await activate_ability(mock_session_no_existing_status, guild_id, caster_id,
                                       RelationshipEntityType.PLAYER.value, ability_id_val,
                                       [20], [RelationshipEntityType.GENERATED_NPC.value])
        assert outcome.success is False
        assert "Not enough mana" in outcome.message
        mock_log_event.assert_not_called()

@pytest.mark.asyncio
async def test_activate_ability_healing_self(mock_session_no_existing_status: AsyncSession):
    with PATCHES['log_event'] as mock_log_event, \
         PATCHES['ability_crud'] as mock_ability_crud, \
         PATCHES['_get_entity'] as mock_get_entity, \
         PATCHES['get_entity_stat'] as mock_get_stat, \
         PATCHES['change_entity_stat'] as mock_change_stat, \
         PATCHES['change_entity_hp'] as mock_change_hp, \
         PATCHES['get_rule'] as mock_get_rule, \
         PATCHES['get_entity_hp'] as mock_get_hp:

        guild_id, caster_id, ability_id_val = 1, 10, 102
        caster = _create_mock_player(caster_id, guild_id, hp=50, mana=20)
        mock_get_entity.return_value = caster
        test_ability_obj = _create_mock_ability(ability_id_val, "minor_heal", guild_id=guild_id,
            cost={"resource": "mana", "amount": 5},
            effects=[{"type": "healing", "amount": 15, "target_scope": "self"}])
        mock_ability_crud.get.return_value = test_ability_obj
        mock_get_stat.return_value = 20
        mock_change_stat.return_value = True
        mock_change_hp.return_value = True
        mock_get_hp.return_value = 65
        mock_get_rule.return_value = None

        outcome = await activate_ability(mock_session_no_existing_status, guild_id, caster_id,
                                       RelationshipEntityType.PLAYER.value, ability_id_val)
        assert outcome.success is True
        assert len(outcome.healing_done) == 1
        mock_change_hp.assert_called_once_with(caster, 15)
        mock_log_event.assert_called_once()

@pytest.mark.asyncio
async def test_apply_status_new_status(mock_session_no_existing_status: AsyncSession):
    with PATCHES['log_event'] as mock_log_event, \
         PATCHES['status_effect_crud'] as mock_status_effect_crud, \
         PATCHES['_get_entity'] as mock_get_entity:

        guild_id, target_id, status_def_id_val, ab_id = 1, 30, 200, 1
        status_static_id_val = "burning"
        target = _create_mock_player(target_id, guild_id)
        mock_get_entity.return_value = target
        status_def = _create_mock_status_effect_def(status_def_id_val, status_static_id_val, guild_id=guild_id)
        mock_status_effect_crud.get_by_static_id.return_value = status_def

        success = await apply_status(mock_session_no_existing_status, guild_id, target_id,
                                   RelationshipEntityType.PLAYER.value, status_static_id_val,
                                   duration=3, source_ability_id=ab_id)
        assert success is True
        mock_session_no_existing_status.add.assert_called_once() # type: ignore
        added_obj = mock_session_no_existing_status.add.call_args[0][0] # type: ignore
        assert isinstance(added_obj, ActiveStatusEffect) # type: ignore[reportGeneralTypeIssues]
        mock_log_event.assert_called_once() # type: ignore

@pytest.mark.asyncio
async def test_apply_status_refresh_duration(mock_session_with_existing_status_factory: callable):
    guild_id, target_id, status_def_id_val, active_status_id_val, ab_id = 1, 30, 200, 300, 2
    status_static_id_val = "chilled"
    fixed_now = datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)

    existing_active = _create_mock_active_status(active_status_id_val, status_def_id_val, target_id,
                                               RelationshipEntityType.PLAYER.value, guild_id, duration=2, applied_at_val=fixed_now)
    mock_session = mock_session_with_existing_status_factory(existing_active)

    with PATCHES['log_event'] as mock_log_event, \
         PATCHES['status_effect_crud'] as mock_status_effect_crud, \
         PATCHES['_get_entity'] as mock_get_entity, \
         patch('sqlalchemy.sql.func.now', return_value=fixed_now) as mock_sqlalchemy_func_now:

        target = _create_mock_player(target_id, guild_id)
        mock_get_entity.return_value = target
        status_def = _create_mock_status_effect_def(status_def_id_val, status_static_id_val,
                                                  guild_id=guild_id, props={"duration_refresh": True})
        mock_status_effect_crud.get_by_static_id.return_value = status_def

        success = await apply_status(mock_session, guild_id, target_id, RelationshipEntityType.PLAYER.value,
                                   status_static_id_val, duration=5, source_ability_id=ab_id)
        assert success is True
        mock_session.add.assert_called_once_with(existing_active) # type: ignore
        assert existing_active.applied_at == fixed_now
        mock_log_event.assert_called_once() # type: ignore
        mock_sqlalchemy_func_now.assert_called() # type: ignore

@pytest.mark.asyncio
async def test_remove_status_success(mock_session_no_existing_status: AsyncSession):
    with PATCHES['log_event'] as mock_log_event, \
         PATCHES['_get_entity'] as mock_get_entity:

        guild_id, active_status_id_val, entity_id_val, status_def_id_val = 1, 400, 50, 201
        status_static_id_val = "weakened"
        mock_player_for_loc = _create_mock_player(entity_id_val, guild_id)
        mock_get_entity.return_value = mock_player_for_loc

        active_status_to_remove = _create_mock_active_status(active_status_id_val, status_def_id_val, entity_id_val,
                                                           RelationshipEntityType.PLAYER.value, guild_id)
        original_status_def = _create_mock_status_effect_def(status_def_id_val, status_static_id_val, guild_id=guild_id)

        async def get_side_effect(model, record_id):
            if model == ActiveStatusEffect and record_id == active_status_id_val: return active_status_to_remove
            if model == StatusEffect and record_id == status_def_id_val: return original_status_def
            return None
        mock_session_no_existing_status.get = AsyncMock(side_effect=get_side_effect)

        success = await remove_status(mock_session_no_existing_status, guild_id, active_status_id_val)
        assert success is True
        mock_session_no_existing_status.delete.assert_called_once_with(active_status_to_remove) # type: ignore
        mock_log_event.assert_called_once() # type: ignore

# (Many TODOs from previous block still apply and will be implemented incrementally)
# ...

@pytest.mark.asyncio
async def test_activate_ability_prerequisite_not_in_combat(mock_session_no_existing_status: AsyncSession):
    with PATCHES['ability_crud'] as mock_ability_crud, \
         PATCHES['_get_entity'] as mock_get_entity, \
         PATCHES['get_rule'] as mock_get_rule, \
         PATCHES['get_entity_stat'] as mock_get_stat: # Added get_entity_stat

        guild_id, caster_id, ability_id_val = 1, 10, 103
        caster = _create_mock_player(caster_id, guild_id, status=PlayerStatus.IDLE) # Not in combat
        mock_get_entity.return_value = caster
        # Ability definition with prerequisite
        test_ability_obj = _create_mock_ability(
            ability_id_val, "power_strike", guild_id=guild_id,
            cost={"resource": "stamina", "amount": 5},
            effects=[{"type": "damage", "amount": 30, "target_scope": "first_target"}]
        )
        # Add prerequisite to ability's properties_json
        test_ability_obj.properties_json["prerequisites"] = {"status": "in_combat"}
        mock_ability_crud.get.return_value = test_ability_obj
        mock_get_rule.return_value = None # No special RuleConfig needed for this part of the test
        mock_get_stat.return_value = 10 # For stamina check

        outcome = await activate_ability(mock_session_no_existing_status, guild_id, caster_id,
                                       RelationshipEntityType.PLAYER.value, ability_id_val,
                                       [20], [RelationshipEntityType.GENERATED_NPC.value])
        assert outcome.success is False
        assert "Caster must be in combat" in outcome.message

@pytest.mark.asyncio
async def test_activate_ability_target_out_of_range(mock_session_no_existing_status: AsyncSession):
    with PATCHES['ability_crud'] as mock_ability_crud, \
         PATCHES['_get_entity'] as mock_get_entity, \
         PATCHES['get_rule'] as mock_get_rule, \
         PATCHES['get_entity_stat'] as mock_get_stat, \
         patch(COMMON_PATCH_BASE + '_get_entity_location', new_callable=AsyncMock) as mock_get_location:

        guild_id, caster_id, target_id, ability_id_val = 1, 10, 20, 104
        caster = _create_mock_player(caster_id, guild_id, mana=50)
        target = _create_mock_npc(target_id, guild_id, hp=80)

        caster_loc = MagicMock()
        caster_loc.id = 1
        caster_loc.x, caster_loc.y, caster_loc.z = 0, 0, 0
        target_loc = MagicMock()
        target_loc.id = 2
        target_loc.x, target_loc.y, target_loc.z = 100, 0, 0 # Far away

        mock_get_entity.side_effect = lambda _s, _gid, eid, _et: caster if eid == caster_id else target

        def get_loc_side_effect(session, entity_obj):
            if entity_obj == caster: return caster_loc
            if entity_obj == target: return target_loc
            return None
        mock_get_location.side_effect = get_loc_side_effect

        test_ability_obj = _create_mock_ability(
            ability_id_val, "ranged_shot", guild_id=guild_id,
            cost={"resource": "mana", "amount": 5},
            effects=[{"type": "damage", "amount": 15, "target_scope": "first_target"}]
        )
        # Add targeting rules to ability's properties_json
        test_ability_obj.properties_json["targeting_rules"] = {"max_range": 50} # Max range 50, target is at 100
        mock_ability_crud.get.return_value = test_ability_obj
        mock_get_stat.return_value = 50 # For mana check
        mock_get_rule.return_value = None

        outcome = await activate_ability(mock_session_no_existing_status, guild_id, caster_id,
                                       RelationshipEntityType.PLAYER.value, ability_id_val,
                                       [target_id], [RelationshipEntityType.GENERATED_NPC.value])
        assert outcome.success is False
        assert "No valid targets found" in outcome.message or "out of range" in outcome.message # Message can vary slightly

@pytest.mark.asyncio
async def test_activate_ability_effect_amount_from_rule_config(mock_session_no_existing_status: AsyncSession):
    with PATCHES['log_event'], \
         PATCHES['get_rule'] as mock_get_rule, \
         PATCHES['ability_crud'] as mock_ability_crud, \
         PATCHES['_get_entity'] as mock_get_entity, \
         PATCHES['get_entity_stat'] as mock_get_stat, \
         PATCHES['change_entity_stat'] as mock_change_stat, \
         PATCHES['change_entity_hp'] as mock_change_hp:

        guild_id, caster_id, target_id, ability_id_val = 1, 10, 20, 105
        caster = _create_mock_player(caster_id, guild_id, mana=50)
        target = _create_mock_npc(target_id, guild_id, hp=80)

        mock_get_entity.side_effect = lambda _s, _gid, eid, _et: caster if eid == caster_id else target
        # Effect amount is a string, should be fetched from RuleConfig
        test_ability_obj = _create_mock_ability(ability_id_val, "magic_missile", guild_id=guild_id,
            cost={"resource": "mana", "amount": 10},
            effects=[{"type": "damage", "amount": "magic_missile_base_damage", "target_scope": "first_target"}])

        mock_ability_crud.get.return_value = test_ability_obj
        mock_get_stat.return_value = 50 # Caster mana
        mock_change_stat.return_value = True # Mana deduction success
        mock_change_hp.return_value = True # HP change success

        # Mock get_rule to return the damage value for the key
        mock_get_rule.side_effect = lambda _s, _gid, key, default=None: 35 if key == "magic_missile_base_damage" else default

        outcome = await activate_ability(mock_session_no_existing_status, guild_id, caster_id,
                                       RelationshipEntityType.PLAYER.value, ability_id_val,
                                       [target_id], [RelationshipEntityType.GENERATED_NPC.value])
        assert outcome.success is True
        mock_change_hp.assert_called_once_with(target, -35) # Damage should be 35 from RuleConfig
        mock_get_rule.assert_any_call(mock_session_no_existing_status, guild_id, "magic_missile_base_damage")


@pytest.mark.asyncio
async def test_apply_status_stackable_new(mock_session_no_existing_status: AsyncSession):
    with PATCHES['log_event'] as mock_log_event, \
         PATCHES['status_effect_crud'] as mock_status_effect_crud, \
         PATCHES['_get_entity'] as mock_get_entity:

        guild_id, target_id, status_def_id_val = 1, 30, 201
        status_static_id_val = "rend_armor"
        target = _create_mock_player(target_id, guild_id)
        mock_get_entity.return_value = target

        status_def = _create_mock_status_effect_def(
            status_def_id_val, status_static_id_val, guild_id=guild_id,
            props={"stackable": True, "max_stacks": 3, "refresh_duration_on_stack_gain": True}
        )
        mock_status_effect_crud.get_by_static_id.return_value = status_def

        success = await apply_status(mock_session_no_existing_status, guild_id, target_id,
                                   RelationshipEntityType.PLAYER.value, status_static_id_val, duration=5)
        assert success is True
        mock_session_no_existing_status.add.assert_called_once()
        added_obj: ActiveStatusEffect = mock_session_no_existing_status.add.call_args[0][0]
        assert added_obj.custom_properties_json is not None
        assert added_obj.custom_properties_json.get("current_stacks") == 1
        mock_log_event.assert_called_once()

@pytest.mark.asyncio
async def test_apply_status_stackable_add_stack(mock_session_with_existing_status_factory: callable):
    guild_id, target_id, status_def_id_val, active_status_id_val = 1, 30, 201, 301
    status_static_id_val = "rend_armor"
    fixed_now = datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)

    existing_active = _create_mock_active_status(
        active_status_id_val, status_def_id_val, target_id, RelationshipEntityType.PLAYER.value, guild_id,
        duration=3, applied_at_val=fixed_now - datetime.timedelta(seconds=10) # Applied some time ago
    )
    existing_active.custom_properties_json = {"current_stacks": 1} # Already has 1 stack

    mock_session = mock_session_with_existing_status_factory(existing_active)

    with PATCHES['log_event'] as mock_log_event, \
         PATCHES['status_effect_crud'] as mock_status_effect_crud, \
         PATCHES['_get_entity'] as mock_get_entity, \
         patch('sqlalchemy.sql.func.now', return_value=fixed_now) as mock_sqlalchemy_func_now:

        target = _create_mock_player(target_id, guild_id)
        mock_get_entity.return_value = target
        status_def = _create_mock_status_effect_def(
            status_def_id_val, status_static_id_val, guild_id=guild_id,
            props={"stackable": True, "max_stacks": 3, "refresh_duration_on_stack_gain": True}
        )
        mock_status_effect_crud.get_by_static_id.return_value = status_def

        success = await apply_status(mock_session, guild_id, target_id, RelationshipEntityType.PLAYER.value,
                                   status_static_id_val, duration=5) # New application with duration 5
        assert success is True
        mock_session.add.assert_called_once_with(existing_active)
        assert existing_active.custom_properties_json is not None
        assert existing_active.custom_properties_json.get("current_stacks") == 2
        assert existing_active.duration_turns == 5 # Duration should refresh
        assert existing_active.remaining_turns == 5
        assert existing_active.applied_at == fixed_now
        mock_log_event.assert_called_once()
        mock_sqlalchemy_func_now.assert_called()

@pytest.mark.asyncio
async def test_apply_status_stackable_reach_max_stacks_and_refresh(mock_session_with_existing_status_factory: callable):
    guild_id, target_id, status_def_id_val, active_status_id_val = 1, 30, 201, 302
    status_static_id_val = "rend_armor_max_refresh"
    fixed_now = datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)

    existing_active = _create_mock_active_status(
        active_status_id_val, status_def_id_val, target_id, RelationshipEntityType.PLAYER.value, guild_id,
        duration=3, applied_at_val=fixed_now - datetime.timedelta(seconds=10)
    )
    existing_active.custom_properties_json = {"current_stacks": 2} # Current stacks is 2, max is 2

    mock_session = mock_session_with_existing_status_factory(existing_active)

    with PATCHES['log_event'] as mock_log_event, \
         PATCHES['status_effect_crud'] as mock_status_effect_crud, \
         PATCHES['_get_entity'] as mock_get_entity, \
         patch('sqlalchemy.sql.func.now', return_value=fixed_now) as mock_sqlalchemy_func_now:

        target = _create_mock_player(target_id, guild_id)
        mock_get_entity.return_value = target
        status_def = _create_mock_status_effect_def(
            status_def_id_val, status_static_id_val, guild_id=guild_id,
            props={"stackable": True, "max_stacks": 2,
                   "refresh_duration_on_stack_gain": True, # Should not apply as stacks don't increase
                   "refresh_duration_at_max_stacks": True} # This should apply
        )
        mock_status_effect_crud.get_by_static_id.return_value = status_def

        success = await apply_status(mock_session, guild_id, target_id, RelationshipEntityType.PLAYER.value,
                                   status_static_id_val, duration=7) # New duration 7
        assert success is True
        mock_session.add.assert_called_once_with(existing_active)
        assert existing_active.custom_properties_json is not None
        assert existing_active.custom_properties_json.get("current_stacks") == 2 # Stacks remain at max
        assert existing_active.duration_turns == 7 # Duration refreshed to new value
        assert existing_active.remaining_turns == 7
        assert existing_active.applied_at == fixed_now
        mock_log_event.assert_called_once()
        mock_sqlalchemy_func_now.assert_called()

@pytest.mark.asyncio
async def test_apply_status_stackable_at_max_stacks_no_refresh(mock_session_with_existing_status_factory: callable):
    guild_id, target_id, status_def_id_val, active_status_id_val = 1, 30, 201, 303
    status_static_id_val = "rend_armor_max_no_refresh"

    existing_active = _create_mock_active_status(
        active_status_id_val, status_def_id_val, target_id, RelationshipEntityType.PLAYER.value, guild_id, duration=3
    )
    existing_active.custom_properties_json = {"current_stacks": 2} # At max stacks

    mock_session = mock_session_with_existing_status_factory(existing_active)

    with PATCHES['log_event'] as mock_log_event, \
         PATCHES['status_effect_crud'] as mock_status_effect_crud, \
         PATCHES['_get_entity'] as mock_get_entity:

        target = _create_mock_player(target_id, guild_id)
        mock_get_entity.return_value = target
        status_def = _create_mock_status_effect_def(
            status_def_id_val, status_static_id_val, guild_id=guild_id,
            props={"stackable": True, "max_stacks": 2, "refresh_duration_at_max_stacks": False} # No refresh at max
        )
        mock_status_effect_crud.get_by_static_id.return_value = status_def

        success = await apply_status(mock_session, guild_id, target_id, RelationshipEntityType.PLAYER.value,
                                   status_static_id_val, duration=5)
        assert success is False # No action taken
        mock_session.add.assert_not_called() # Should not have been called
        mock_log_event.assert_not_called()
