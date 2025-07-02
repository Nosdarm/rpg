import pytest
import pytest_asyncio # For async fixtures
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.ability_system import activate_ability_v2, apply_status_v2, remove_status, _get_entity
from src.models import Player, GeneratedNpc, Ability, StatusEffect, ActiveStatusEffect, GuildConfig, RuleConfig
from src.models.ability_outcomes import AbilityOutcomeDetails
from src.models.enums import RelationshipEntityType, EventType, PlayerStatus

# --- Mocks for Models ---
@pytest.fixture
def mock_player() -> Player:
    player = MagicMock(spec=Player)
    player.id = 1
    player.guild_id = 100
    player.discord_id = 1000
    player.name = "Test Player"
    player.current_hp = 50
    player.current_status = PlayerStatus.EXPLORING
    # Add other fields as needed by tests
    return player

@pytest.fixture
def mock_npc() -> GeneratedNpc:
    npc = MagicMock(spec=GeneratedNpc)
    npc.id = 2
    npc.guild_id = 100
    npc.name = "Test NPC"
    npc.stats_json = {"hp": 30, "mana": 20} # Example
    # Add other fields
    return npc

@pytest.fixture
def mock_ability_fireball() -> Ability:
    ability = MagicMock(spec=Ability)
    ability.id = 10
    ability.static_id = "fireball"
    ability.guild_id = None # Global ability
    ability.name_i18n = {"en": "Fireball", "ru": "Огненный шар"}
    ability.properties_json = {
        "cost": {"resource": "mana", "amount": 10},
        "effects": [
            {"type": "damage", "amount": 15, "damage_type": "fire", "target": "first"},
            {"type": "apply_status", "status_static_id": "burning", "duration": 3, "target": "first"}
        ]
    }
    return ability

@pytest.fixture
def mock_ability_guild_specific() -> Ability:
    ability = MagicMock(spec=Ability)
    ability.id = 11
    ability.static_id = "guild_blast"
    ability.guild_id = 100
    ability.name_i18n = {"en": "Guild Blast"}
    ability.properties_json = {"effects": [{"type": "damage", "amount": 25, "target": "all"}]}
    return ability

@pytest.fixture
def mock_status_effect_burning() -> StatusEffect:
    status = MagicMock(spec=StatusEffect)
    status.id = 20
    status.static_id = "burning"
    status.guild_id = None # Global
    status.name_i18n = {"en": "Burning", "ru": "Горение"}
    status.effects_json = {"damage_per_turn": 5}
    return status

@pytest_asyncio.fixture
async def mock_session() -> AsyncSession:
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock() # For session.get(Model, id)
    session.execute = AsyncMock() # For select statements
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    session.delete = MagicMock()
    return session

# --- Test _get_entity ---
@pytest.mark.asyncio
async def test_get_entity_player(mock_session, mock_player):
    with patch('src.core.ability_system.player_crud.get', new_callable=AsyncMock, return_value=mock_player) as mock_crud_get:
        entity = await _get_entity(mock_session, mock_player.guild_id, mock_player.id, RelationshipEntityType.PLAYER.value)
        assert entity == mock_player
        mock_crud_get.assert_called_once_with(mock_session, id=mock_player.id, guild_id=mock_player.guild_id)

@pytest.mark.asyncio
async def test_get_entity_npc(mock_session, mock_npc):
     with patch('src.core.ability_system.npc_crud.get', new_callable=AsyncMock, return_value=mock_npc) as mock_crud_get:
        entity = await _get_entity(mock_session, mock_npc.guild_id, mock_npc.id, RelationshipEntityType.GENERATED_NPC.value)
        assert entity == mock_npc
        mock_crud_get.assert_called_once_with(mock_session, id=mock_npc.id, guild_id=mock_npc.guild_id)

@pytest.mark.asyncio
async def test_get_entity_not_found(mock_session):
    with patch('src.core.ability_system.player_crud.get', new_callable=AsyncMock, return_value=None):
        entity = await _get_entity(mock_session, 100, 999, RelationshipEntityType.PLAYER.value)
        assert entity is None

# --- Test activate_ability_v2 ---
@pytest.mark.asyncio
@patch('src.core.ability_system.log_event', new_callable=AsyncMock)
@patch('src.core.ability_system.apply_status_v2', new_callable=AsyncMock, return_value=True) # Assume status applies successfully
async def test_activate_ability_fireball_on_npc(
    mock_apply_status, mock_log_event, mock_session,
    mock_player, mock_npc, mock_ability_fireball, mock_status_effect_burning
):
    # Arrange
    guild_id = mock_player.guild_id

    # Mock _get_entity (used by activate_ability_v2)
    async def mock_internal_get_entity(session, g_id, e_id, e_type_str):
        if e_id == mock_player.id and e_type_str.lower() == RelationshipEntityType.PLAYER.value.lower(): return mock_player
        if e_id == mock_npc.id and e_type_str.lower() == RelationshipEntityType.GENERATED_NPC.value.lower(): return mock_npc
        return None

    # Mock CRUD operations
    mock_ability_crud_get = AsyncMock(return_value=mock_ability_fireball)
    mock_ability_crud_get_by_static_id = AsyncMock(return_value=mock_ability_fireball)

    with patch('src.core.ability_system.ability_crud.get', mock_ability_crud_get), \
         patch('src.core.ability_system.ability_crud.get_by_static_id', mock_ability_crud_get_by_static_id), \
         patch('src.core.ability_system._get_entity', side_effect=mock_internal_get_entity) as mock_get_entity_patched:

        # Act: Test with static_id
        outcome_static_id = await activate_ability_v2(
            session=mock_session,
            guild_id=guild_id,
            entity_id=mock_player.id,
            entity_type=RelationshipEntityType.PLAYER.value,
            ability_identifier=mock_ability_fireball.static_id, # Use static_id
            target_entity_ids=[mock_npc.id],
            target_entity_types=[RelationshipEntityType.GENERATED_NPC.value]
        )

        # Assert for static_id case
        assert outcome_static_id.success is True
        mock_ability_crud_get_by_static_id.assert_called_with(mock_session, static_id=mock_ability_fireball.static_id, guild_id=guild_id)

        # Reset mocks for next call if necessary or use separate tests
        mock_ability_crud_get.reset_mock()
        mock_ability_crud_get_by_static_id.reset_mock()
        mock_get_entity_patched.reset_mock() # Reset this if side_effect calls are counted across tests
        mock_apply_status.reset_mock()
        mock_log_event.reset_mock()

        # Act: Test with id
        outcome = await activate_ability_v2(
            session=mock_session,
            guild_id=guild_id,
            entity_id=mock_player.id,
            entity_type=RelationshipEntityType.PLAYER.value,
            ability_identifier=mock_ability_fireball.id, # Use ID
            target_entity_ids=[mock_npc.id],
            target_entity_types=[RelationshipEntityType.GENERATED_NPC.value]
        )

        # Assert for ID case
        assert outcome.success is True
        assert "processed (MVP)" in outcome.message
        mock_ability_crud_get.assert_called_with(mock_session, id=mock_ability_fireball.id)

        assert len(outcome.damage_dealt) == 1
        assert outcome.damage_dealt[0].target_entity_id == mock_npc.id
        assert outcome.damage_dealt[0].amount == 15
        assert outcome.damage_dealt[0].damage_type == "fire"

        assert len(outcome.applied_statuses) == 1
        assert outcome.applied_statuses[0].status_static_id == "burning"
        assert outcome.applied_statuses[0].target_entity_id == mock_npc.id

        mock_apply_status.assert_called_once()
        called_args_tuple = mock_apply_status.call_args[0]
        assert called_args_tuple[4] == "burning"
        assert called_args_tuple[2] == mock_npc.id

        mock_log_event.assert_called_once()
        log_args, log_kwargs = mock_log_event.call_args
        assert log_kwargs['event_type'] == EventType.ABILITY_USED
        assert log_kwargs['details_json']['ability_static_id'] == "fireball"
        assert log_kwargs['player_id'] == mock_player.id

# --- Test apply_status_v2 ---
@pytest.mark.asyncio
@patch('src.core.ability_system.log_event', new_callable=AsyncMock)
async def test_apply_status_burning_on_player(
    mock_log_event, mock_session, mock_player, mock_status_effect_burning
):
    guild_id = mock_player.guild_id

    # Mock _get_entity (used by apply_status_v2)
    async def mock_internal_get_entity(session, g_id, e_id, e_type_str):
        if e_id == mock_player.id and e_type_str.lower() == "player": return mock_player
        return None

    mock_status_effect_crud_get_by_static_id = AsyncMock(return_value=mock_status_effect_burning)

    with patch('src.core.ability_system.status_effect_crud.get_by_static_id', mock_status_effect_crud_get_by_static_id), \
         patch('src.core.ability_system._get_entity', side_effect=mock_internal_get_entity) as mock_get_target_entity:

        success = await apply_status_v2(
            session=mock_session,
            guild_id=guild_id,
            entity_id=mock_player.id,
            entity_type=RelationshipEntityType.PLAYER.value,
            status_static_id=mock_status_effect_burning.static_id,
            duration=3
        )

        assert success is True
        mock_status_effect_crud_get_by_static_id.assert_called_once_with(
            mock_session, static_id=mock_status_effect_burning.static_id, guild_id=guild_id
        )
        mock_get_target_entity.assert_called_once() # Check it was called

        mock_session.add.assert_called_once()
        added_obj = mock_session.add.call_args[0][0]
        assert isinstance(added_obj, ActiveStatusEffect)
        assert added_obj.entity_id == mock_player.id # Corrected: owner_id to entity_id
        assert added_obj.status_effect_id == mock_status_effect_burning.id
        assert added_obj.duration_turns == 3 # Corrected: duration to duration_turns

        mock_log_event.assert_called_once() # type: ignore[attr-defined]
        log_args, log_kwargs = mock_log_event.call_args
        assert log_kwargs['event_type'] == EventType.STATUS_APPLIED
        assert log_kwargs['details_json']['status_static_id'] == "burning"
        assert log_kwargs['player_id'] == mock_player.id


@pytest.mark.asyncio
@patch('src.core.ability_system.ability_crud.get_by_static_id', new_callable=AsyncMock, return_value=None)
async def test_activate_ability_not_found(mock_get_ability_static_id, mock_session, mock_player):
    outcome = await activate_ability_v2(
        session=mock_session,
        guild_id=mock_player.guild_id,
        entity_id=mock_player.id,
        entity_type=RelationshipEntityType.PLAYER.value,
        ability_identifier="non_existent_ability_static_id"
    )
    assert outcome.success is False
    assert "not found" in outcome.message.lower()
    mock_get_ability_static_id.assert_called_once_with(mock_session, static_id="non_existent_ability_static_id", guild_id=mock_player.guild_id)


# TODO: More tests:
# - activate_ability: caster not found, target not found
# - activate_ability: guild-specific ability used in wrong guild (or by non-guild member if applicable)
# - activate_ability: global ability usage
# - activate_ability: no targets
# - activate_ability: cost deduction (mock entity stats & verify change)
# - activate_ability: HP update on Player/NPC (mock entity & verify change)
# - activate_ability: different effects (healing)
# - apply_status: status_effect not found (global and guild-specific cases)
# - apply_status: target entity not found
# - remove_status tests
# - Test interaction with RuleConfig (when logic is added)
