import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from typing import Optional, Union, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
import datetime

from src.core.ability_system import activate_ability, apply_status, remove_status
from src.models import Player, GeneratedNpc, Ability, StatusEffect, ActiveStatusEffect, GuildConfig
from src.models.ability_outcomes import AbilityOutcomeDetails, DamageDetail, HealingDetail, AppliedStatusDetail, CasterUpdateDetail
from src.models.enums import RelationshipEntityType, EventType, PlayerStatus

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
    setattr(npc, 'current_location_id', npc.properties_json.get("current_location_id", 1)) # Default to 1 if not in json
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
    mock_execute_result = AsyncMock()
    mock_scalars_result = MagicMock()
    mock_scalars_result.first.return_value = None
    mock_execute_result.scalars.return_value = mock_scalars_result
    session.execute.return_value = mock_execute_result
    return session

@pytest.fixture
def mock_session_with_existing_status_factory():
    def _factory(existing_status_instance: Optional[ActiveStatusEffect]):
        session = AsyncMock(spec=AsyncSession)
        mock_execute_result = AsyncMock()
        mock_scalars_result = MagicMock()
        mock_scalars_result.first.return_value = existing_status_instance
        mock_execute_result.scalars.return_value = mock_scalars_result
        session.execute.return_value = mock_execute_result
        return session
    return _factory

COMMON_PATCH_BASE = 'src.core.ability_system.'
PATCHES = {
    'log_event': patch(COMMON_PATCH_BASE + 'log_event', new_callable=AsyncMock),
    'get_rule': patch(COMMON_PATCH_BASE + 'get_rule', new_callable=AsyncMock),
    'ability_crud': patch(COMMON_PATCH_BASE + 'ability_crud', new_callable=MagicMock),
    '_get_entity': patch(COMMON_PATCH_BASE + '_get_entity', new_callable=AsyncMock),
    'get_entity_stat': patch(COMMON_PATCH_BASE + 'get_entity_stat'),
    'change_entity_stat': patch(COMMON_PATCH_BASE + 'change_entity_stat'),
    'get_entity_hp': patch(COMMON_PATCH_BASE + 'get_entity_hp'),
    'change_entity_hp': patch(COMMON_PATCH_BASE + 'change_entity_hp'),
    'status_effect_crud': patch(COMMON_PATCH_BASE + 'status_effect_crud', new_callable=MagicMock),
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
        mock_session_no_existing_status.add.assert_called_once()
        added_obj = mock_session_no_existing_status.add.call_args[0][0]
        assert isinstance(added_obj, ActiveStatusEffect)
        mock_log_event.assert_called_once()

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
        mock_session.add.assert_called_once_with(existing_active)
        assert existing_active.applied_at == fixed_now
        mock_log_event.assert_called_once()
        mock_sqlalchemy_func_now.assert_called()

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
        mock_session_no_existing_status.delete.assert_called_once_with(active_status_to_remove)
        mock_log_event.assert_called_once()

# (Many TODOs from previous block still apply and will be implemented incrementally)
# ...
