import pytest
import asyncio
import json
import logging
import datetime
from unittest.mock import AsyncMock, patch, MagicMock, call, ANY

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.action_processor import process_actions_for_guild, _load_and_clear_actions
from src.models import Player, Party
from src.models.actions import ParsedAction, ActionEntity
from src.models.enums import PlayerStatus, PartyTurnStatus

DEFAULT_GUILD_ID = 1
PLAYER_ID_PK_1 = 1
PLAYER_DISCORD_ID_1 = 101
PLAYER_ID_PK_2 = 2
PLAYER_DISCORD_ID_2 = 102
PARTY_ID_PK_1 = 10

# Using direct dicts for collected_actions_json to ensure exact parsing input
fixed_dt_str = datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc).isoformat()

look_action_data = {
    "raw_text": "look", "intent": "look", "guild_id": DEFAULT_GUILD_ID,
    "player_id": PLAYER_DISCORD_ID_1, "timestamp": fixed_dt_str, "entities": []
}
move_action_data = {
    "raw_text": "move somewhere", "intent": "move",
    "entities":[ActionEntity(type="direction", value="somewhere").model_dump(mode='json')],
    "guild_id": DEFAULT_GUILD_ID, "player_id": PLAYER_DISCORD_ID_1, "timestamp": fixed_dt_str
}

@pytest.fixture
def mock_player_1_with_look_action() -> Player:
    return Player(
        id=PLAYER_ID_PK_1, discord_id=PLAYER_DISCORD_ID_1, guild_id=DEFAULT_GUILD_ID,
        name="Player1WithLookAction", collected_actions_json=json.dumps([look_action_data]),
        current_status=PlayerStatus.PROCESSING_GUILD_TURN
    )

@pytest.fixture
def mock_player_1_with_move_action() -> Player:
    return Player(
        id=PLAYER_ID_PK_1, discord_id=PLAYER_DISCORD_ID_1, guild_id=DEFAULT_GUILD_ID,
        name="Player1WithMoveAction", collected_actions_json=json.dumps([move_action_data]),
        current_status=PlayerStatus.PROCESSING_GUILD_TURN
    )

@pytest.fixture
def mock_player_1_with_both_actions() -> Player:
    return Player(
        id=PLAYER_ID_PK_1, discord_id=PLAYER_DISCORD_ID_1, guild_id=DEFAULT_GUILD_ID,
        name="Player1WithBothActions", collected_actions_json=json.dumps([look_action_data, move_action_data]),
        current_status=PlayerStatus.PROCESSING_GUILD_TURN
    )

@pytest.fixture
def mock_player_2_no_actions() -> Player:
    return Player(
        id=PLAYER_ID_PK_2, discord_id=PLAYER_DISCORD_ID_2, guild_id=DEFAULT_GUILD_ID,
        name="Player2NoActions", collected_actions_json="[]",
        current_status=PlayerStatus.PROCESSING_GUILD_TURN
    )

@pytest.fixture
def mock_party_with_player_1(mock_player_1_with_both_actions: Player) -> Party:
    return Party(
        id=PARTY_ID_PK_1, guild_id=DEFAULT_GUILD_ID, name="TestParty",
        player_ids_json=[mock_player_1_with_both_actions.id],
        turn_status=PartyTurnStatus.PROCESSING_GUILD_TURN
    )

@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    mock_transaction_cm = AsyncMock()
    async def mock_aenter_for_begin(): return None
    async def mock_aexit_for_begin(exc_type, exc, tb):
        if exc_type is None: await session.commit()
        else: await session.rollback()
        return None
    mock_transaction_cm.__aenter__ = AsyncMock(side_effect=mock_aenter_for_begin)
    mock_transaction_cm.__aexit__ = AsyncMock(side_effect=mock_aexit_for_begin)
    session.begin = MagicMock(return_value=mock_transaction_cm)
    return session

@pytest.fixture
def mock_session_maker(mock_session: AsyncMock) -> MagicMock:
    maker = MagicMock()
    maker.return_value.__aenter__.return_value = mock_session
    maker.return_value.__aexit__.return_value = None
    return maker

@pytest.fixture(autouse=True)
def patch_action_handlers_directly(mocker):
    mocker.patch('src.core.action_processor._handle_placeholder_action', new_callable=AsyncMock, return_value={"status": "success_placeholder"})
    mocker.patch('src.core.action_processor._handle_move_action_wrapper', new_callable=AsyncMock, return_value={"status": "success_move"})
    mocker.patch('src.core.action_processor._handle_intra_location_action_wrapper', new_callable=AsyncMock, return_value={"status": "success_intra_location"})

@pytest.mark.asyncio
@patch("src.core.action_processor.get_db_session")
@patch("src.core.action_processor.get_player", new_callable=AsyncMock)
@patch("src.core.action_processor.log_event", new_callable=AsyncMock)
async def test_process_actions_single_player_only_look(
    mock_log_event_ap: AsyncMock, mock_get_player: AsyncMock,
    mock_session_maker_in_ap: MagicMock, mock_session: AsyncMock,
    mock_player_1_with_look_action: Player
):
    from src.core.action_processor import _handle_placeholder_action, _handle_move_action_wrapper
    _handle_placeholder_action.reset_mock(); _handle_move_action_wrapper.reset_mock()
    mock_session_maker_in_ap.return_value.__aenter__.return_value = mock_session
    mock_get_player.return_value = mock_player_1_with_look_action

    await process_actions_for_guild(DEFAULT_GUILD_ID, [{"id": PLAYER_ID_PK_1, "type": "player"}])

    _handle_placeholder_action.assert_called_once()
    _handle_move_action_wrapper.assert_not_called()
    # ... (further assertions on args and player state)

@pytest.mark.asyncio
@patch("src.core.action_processor.get_db_session")
@patch("src.core.action_processor.get_player", new_callable=AsyncMock)
@patch("src.core.action_processor.log_event", new_callable=AsyncMock)
async def test_process_actions_single_player_with_both_actions(
    mock_log_event_ap: AsyncMock, mock_get_player: AsyncMock,
    mock_session_maker_in_ap: MagicMock, mock_session: AsyncMock,
    mock_player_1_with_both_actions: Player
):
    from src.core.action_processor import _handle_placeholder_action, _handle_move_action_wrapper
    _handle_placeholder_action.reset_mock(); _handle_move_action_wrapper.reset_mock()
    mock_session_maker_in_ap.return_value.__aenter__.return_value = mock_session
    mock_get_player.return_value = mock_player_1_with_both_actions

    await process_actions_for_guild(DEFAULT_GUILD_ID, [{"id": PLAYER_ID_PK_1, "type": "player"}])

    assert _handle_placeholder_action.call_count == 1
    assert _handle_move_action_wrapper.call_count == 1
    # ... (further assertions)

@pytest.mark.asyncio
@patch("src.core.action_processor.get_db_session")
@patch("src.core.action_processor.get_player", new_callable=AsyncMock)
@patch("src.core.action_processor.get_party", new_callable=AsyncMock)
@patch("src.core.action_processor.log_event", new_callable=AsyncMock)
async def test_process_actions_party_with_one_player_actions(
    mock_log_event_ap: AsyncMock, mock_get_party: AsyncMock, mock_get_player: AsyncMock,
    mock_session_maker_in_ap: MagicMock, mock_session: AsyncMock,
    mock_player_1_with_both_actions: Player, mock_party_with_player_1: Party
):
    from src.core.action_processor import _handle_placeholder_action, _handle_move_action_wrapper
    _handle_placeholder_action.reset_mock(); _handle_move_action_wrapper.reset_mock()
    mock_session_maker_in_ap.return_value.__aenter__.return_value = mock_session
    mock_get_player.return_value = mock_player_1_with_both_actions
    mock_get_party.return_value = mock_party_with_player_1

    await process_actions_for_guild(DEFAULT_GUILD_ID, [{"id": PARTY_ID_PK_1, "type": "party"}])

    assert _handle_placeholder_action.call_count == 1
    assert _handle_move_action_wrapper.call_count == 1
    # ... (further assertions)

@pytest.mark.asyncio
@patch("src.core.action_processor.get_db_session")
@patch("src.core.action_processor.get_player", new_callable=AsyncMock)
@patch("src.core.action_processor.log_event", new_callable=AsyncMock)
async def test_process_actions_player_no_actions(
    mock_log_event_ap: AsyncMock, mock_get_player: AsyncMock,
    mock_session_maker_in_ap: MagicMock, mock_session: AsyncMock,
    mock_player_2_no_actions: Player
):
    from src.core.action_processor import _handle_placeholder_action
    _handle_placeholder_action.reset_mock()
    mock_session_maker_in_ap.return_value.__aenter__.return_value = mock_session
    mock_get_player.return_value = mock_player_2_no_actions

    await process_actions_for_guild(DEFAULT_GUILD_ID, [{"id": PLAYER_ID_PK_2, "type": "player"}])

    _handle_placeholder_action.assert_not_called()
    # ... (further assertions)

@pytest.mark.asyncio
@patch("src.core.action_processor.get_db_session")
@patch("src.core.action_processor.get_player", new_callable=AsyncMock)
@patch("src.core.action_processor.log_event", new_callable=AsyncMock)
async def test_process_actions_unknown_intent_uses_placeholder(
    mock_log_event_ap: AsyncMock, mock_get_player: AsyncMock,
    mock_session_maker_in_ap: MagicMock, mock_session: AsyncMock
):
    from src.core.action_processor import _handle_placeholder_action
    _handle_placeholder_action.reset_mock()
    mock_session_maker_in_ap.return_value.__aenter__.return_value = mock_session

    fixed_dt_unknown_str = datetime.datetime(2023, 1, 1, 12, 0, 5, tzinfo=datetime.timezone.utc).isoformat()
    unknown_action_data = {
        "raw_text": "gibberish", "intent": "unknown_intent", "guild_id": DEFAULT_GUILD_ID,
        "player_id": PLAYER_DISCORD_ID_1, "timestamp": fixed_dt_unknown_str, "entities": []
    }
    player_for_test = Player(
        id=PLAYER_ID_PK_1, discord_id=PLAYER_DISCORD_ID_1, guild_id=DEFAULT_GUILD_ID, name="TestPlayerUnknown",
        collected_actions_json=json.dumps([unknown_action_data]),
        current_status=PlayerStatus.PROCESSING_GUILD_TURN
    )
    mock_get_player.return_value = player_for_test

    await process_actions_for_guild(DEFAULT_GUILD_ID, [{"id": PLAYER_ID_PK_1, "type": "player"}])

    _handle_placeholder_action.assert_called_once()
    # ... (further assertions on args)

@pytest.mark.asyncio
@patch("src.core.action_processor.get_player", new_callable=AsyncMock)
@patch("src.core.database.transactional")
async def test_load_and_clear_actions_invalid_json(
    mock_transactional_on_load_clear: MagicMock, mock_get_player: AsyncMock,
    mock_session: AsyncMock,
):
    def passthrough_deco(func):
        import functools
        @functools.wraps(func)
        async def wrapper(*args,**kwargs): return await func(*args,**kwargs)
        return wrapper
    mock_transactional_on_load_clear.side_effect = passthrough_deco

    player_with_bad_json = Player(
        id=PLAYER_ID_PK_1, discord_id=PLAYER_DISCORD_ID_1, guild_id=DEFAULT_GUILD_ID,
        name="BadJsonPlayer", collected_actions_json="[this is not valid json",
        current_status=PlayerStatus.PROCESSING_GUILD_TURN
    )
    mock_get_player.return_value = player_with_bad_json

    actions = await _load_and_clear_actions(mock_session, DEFAULT_GUILD_ID, PLAYER_ID_PK_1, "player")

    assert actions == []
    assert player_with_bad_json.collected_actions_json == []
    mock_session.add.assert_called_with(player_with_bad_json)
    mock_session.commit.assert_not_called()
