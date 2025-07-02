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

    # Mock get_ability_by_id_or_static_id
    async def mock_get_ability(*args, **kwargs):
        if kwargs.get('ability_identifier') == mock_ability_fireball.static_id or kwargs.get('ability_identifier') == mock_ability_fireball.id:
            return mock_ability_fireball
        return None

    # Mock _get_entity
    async def mock_internal_get_entity(session, g_id, e_id, e_type_str):
        if e_id == mock_player.id and e_type_str.lower() == RelationshipEntityType.PLAYER.value.lower(): return mock_player
        if e_id == mock_npc.id and e_type_str.lower() == RelationshipEntityType.GENERATED_NPC.value.lower(): return mock_npc
        return None

    # Simplified patching with return_value
    with patch('src.core.ability_system.get_ability_by_id_or_static_id', new_callable=AsyncMock, return_value=mock_ability_fireball) as mock_get_ability_patched, \
         patch('src.core.ability_system._get_entity', side_effect=mock_internal_get_entity) as mock_get_entity_patched: # keep side_effect for _get_entity as it needs to return different types

        # Act
        outcome = await activate_ability_v2(
            session=mock_session,
            guild_id=guild_id,
            entity_id=mock_player.id,
            entity_type=RelationshipEntityType.PLAYER.value,
            ability_identifier=mock_ability_fireball.static_id,
            target_entity_ids=[mock_npc.id],
            target_entity_types=[RelationshipEntityType.GENERATED_NPC.value]
        )

        # Assert
        assert outcome.success is True
        assert "processed (MVP)" in outcome.message
        assert len(outcome.damage_dealt) == 1
        assert outcome.damage_dealt[0].target_entity_id == mock_npc.id
        assert outcome.damage_dealt[0].amount == 15
        assert outcome.damage_dealt[0].damage_type == "fire"

        assert len(outcome.applied_statuses) == 1
        assert outcome.applied_statuses[0].status_static_id == "burning"
        assert outcome.applied_statuses[0].target_entity_id == mock_npc.id

        mock_apply_status.assert_called_once()
        # apply_status_v2(session, guild_id, entity_id, entity_type, status_static_id, duration, ...)
        # args[0] is a tuple of positional arguments
        called_args_tuple = mock_apply_status.call_args[0]
        assert called_args_tuple[4] == "burning" # status_static_id is the 5th positional arg (index 4)
        assert called_args_tuple[2] == mock_npc.id   # entity_id is the 3rd positional arg (index 2)


        mock_log_event.assert_called_once()
        log_args, log_kwargs = mock_log_event.call_args
        assert log_kwargs['event_type'] == EventType.ABILITY_USED
        assert log_kwargs['details_json']['ability_static_id'] == "fireball"
        assert log_kwargs['player_id'] == mock_player.id # Caster is player

# --- Test apply_status_v2 ---
@pytest.mark.asyncio
@patch('src.core.ability_system.log_event', new_callable=AsyncMock)
async def test_apply_status_burning_on_player(
    mock_log_event, mock_session, mock_player, mock_status_effect_burning
):
    # Arrange
    guild_id = mock_player.guild_id

    async def mock_get_status_effect(*args, **kwargs):
        if kwargs.get('static_id') == mock_status_effect_burning.static_id:
            return mock_status_effect_burning
        return None

    async def mock_internal_get_entity(session, g_id, e_id, e_type_str):
        if e_id == mock_player.id and e_type_str.lower() == "player": return mock_player
        return None

    # Using direct return_value for patched functions for simplicity in this test
    with patch('src.core.ability_system.get_status_effect_by_static_id', new_callable=AsyncMock, return_value=mock_status_effect_burning) as mock_get_status, \
         patch('src.core.ability_system._get_entity', new_callable=AsyncMock, return_value=mock_player) as mock_get_target_entity:

        # Act
        success = await apply_status_v2(
            session=mock_session,
            guild_id=guild_id,
            entity_id=mock_player.id,
            entity_type=RelationshipEntityType.PLAYER.value,
            status_static_id=mock_status_effect_burning.static_id,
            duration=3
        )

        # Assert
        assert success is True
        mock_session.add.assert_called_once()
        added_obj = mock_session.add.call_args[0][0]
        assert isinstance(added_obj, ActiveStatusEffect)
        assert added_obj.owner_id == mock_player.id
        assert added_obj.status_effect_id == mock_status_effect_burning.id
        assert added_obj.duration == 3

        mock_log_event.assert_called_once()
        log_args, log_kwargs = mock_log_event.call_args
        assert log_kwargs['event_type'] == EventType.STATUS_APPLIED
        assert log_kwargs['details_json']['status_static_id'] == "burning"
        assert log_kwargs['player_id'] == mock_player.id


# TODO: More tests:
# - activate_ability: ability not found, caster not found, target not found
# - activate_ability: guild-specific ability used in wrong guild (or by non-guild member if applicable)
# - activate_ability: global ability usage
# - activate_ability: no targets
# - activate_ability: cost deduction (mock entity stats)
# - activate_ability: different effects (healing)
# - apply_status: status_effect not found
# - apply_status: target entity not found
# - apply_status: guild-specific status_effect
# - remove_status tests
# - Test interaction with RuleConfig (when logic is added)
# - Test actual HP/resource updates on mocked entities (when logic is added)

# Placeholder for transactional decorator mock if needed for some test setups
# def transactional_mock(func):
#     @wraps(func)
#     async def wrapper(*args, **kwargs):
#         if 'session' not in kwargs:
#             # If called without session, try to get it from args or create a mock one
#             session_arg_index = -1
#             try:
#                 session_arg_index = func.__code__.co_varnames.index('session')
#             except ValueError:
#                 pass # 'session' not in varnames

#             if session_arg_index != -1 and session_arg_index < len(args) and isinstance(args[session_arg_index], AsyncSession):
#                 kwargs['session'] = args[session_arg_index]
#             elif 'session' not in kwargs: # if still not found
#                 kwargs['session'] = AsyncMock(spec=AsyncSession) # Provide a default mock session

#         # Call the original function with the session ensured
#         return await func(*args, **kwargs)
#     return wrapper
