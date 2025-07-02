import pytest
import asyncio
import json
import logging
import datetime
from unittest.mock import AsyncMock, patch, MagicMock, call, ANY

from sqlalchemy.ext.asyncio import AsyncSession

# Removed _load_and_clear_actions from import
from src.core.action_processor import process_actions_for_guild
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
    # These are the mock objects we want to be called.
    mock_placeholder_handler = AsyncMock(return_value={"status": "success_placeholder_mocked"})
    mock_move_handler = AsyncMock(return_value={"status": "success_move_mocked"})
    mock_intra_location_handler = AsyncMock(return_value={"status": "success_intra_location_mocked"})

    # Patch the names in the module. If ACTION_DISPATCHER.get uses its default, it will pick these up.
    mocker.patch('src.core.action_processor._handle_placeholder_action', new=mock_placeholder_handler)
    mocker.patch('src.core.action_processor._handle_move_action_wrapper', new=mock_move_handler)
    mocker.patch('src.core.action_processor._handle_intra_location_action_wrapper', new=mock_intra_location_handler)

    # Critically, update the ACTION_DISPATCHER dictionary itself to use these mocks,
    # because it captured references to the original functions at module definition time.
    import src.core.action_processor

    # Ensure these specific keys in the live ACTION_DISPATCHER point to our new mocks.
    # For intents that are supposed to use the default _handle_placeholder_action (now mock_placeholder_handler),
    # if they are explicitly listed, they also need to be updated.
    # Based on the second (active) definition of ACTION_DISPATCHER in action_processor.py:
    src.core.action_processor.ACTION_DISPATCHER["move"] = mock_move_handler
    src.core.action_processor.ACTION_DISPATCHER["look"] = mock_placeholder_handler
    src.core.action_processor.ACTION_DISPATCHER["attack"] = mock_placeholder_handler
    src.core.action_processor.ACTION_DISPATCHER["take"] = mock_placeholder_handler
    src.core.action_processor.ACTION_DISPATCHER["use"] = mock_placeholder_handler
    src.core.action_processor.ACTION_DISPATCHER["talk"] = mock_placeholder_handler
    src.core.action_processor.ACTION_DISPATCHER["examine"] = mock_intra_location_handler
    src.core.action_processor.ACTION_DISPATCHER["interact"] = mock_intra_location_handler
    src.core.action_processor.ACTION_DISPATCHER["go_to"] = mock_intra_location_handler
    # Any other intents in the live ACTION_DISPATCHER would need similar treatment if not using the default.

@pytest.fixture(autouse=True)
def configure_module_logging(caplog):
    caplog.set_level(logging.DEBUG, logger="src.core.action_processor")

@pytest.mark.asyncio
@patch("src.core.action_processor.get_db_session")
@patch("src.core.crud.crud_player.player_crud.get_many_by_ids", new_callable=AsyncMock) # Patch for player_crud
@patch("src.core.crud.crud_party.party_crud.get_many_by_ids", new_callable=AsyncMock)   # Patch for party_crud
@patch("src.core.action_processor.log_event", new_callable=AsyncMock)
# mock_get_player and mock_get_party might not be needed if _load_and_clear_all_actions only uses get_many_by_ids
# but _finalize_turn_processing still uses get_player/get_party individually.
@patch("src.core.action_processor.get_player", new_callable=AsyncMock)
@patch("src.core.action_processor.get_party", new_callable=AsyncMock)
async def test_process_actions_single_player_only_look(
    mock_get_party_ap: AsyncMock, # Renamed to avoid conflict if used elsewhere
    mock_get_player_ap: AsyncMock, # Renamed
    mock_log_event_ap: AsyncMock,
    mock_party_crud_get_many: AsyncMock,
    mock_player_crud_get_many: AsyncMock,
    mock_session_maker_in_ap: MagicMock, # This is patching get_db_session in action_processor
    mock_session: AsyncMock, # This is the session object returned by the maker
    mock_player_1_with_look_action: Player
):
    import src.core.action_processor
    placeholder_handler_mock: AsyncMock = src.core.action_processor._handle_placeholder_action # type: ignore
    move_handler_mock: AsyncMock = src.core.action_processor._handle_move_action_wrapper # type: ignore

    placeholder_handler_mock.reset_mock()
    move_handler_mock.reset_mock()
    mock_log_event_ap.reset_mock()

    # Setup mocks for _load_and_clear_all_actions
    mock_player_crud_get_many.return_value = [mock_player_1_with_look_action]
    mock_party_crud_get_many.return_value = [] # No parties in this test case

    # Setup mocks for _finalize_turn_processing (uses individual getters)
    mock_get_player_ap.return_value = mock_player_1_with_look_action
    # mock_get_party_ap is not strictly needed here as no parties are processed

    mock_session_maker_in_ap.return_value.__aenter__.return_value = mock_session

    await process_actions_for_guild(DEFAULT_GUILD_ID, [{"id": PLAYER_ID_PK_1, "type": "player"}])

    placeholder_handler_mock.assert_called_once()
    move_handler_mock.assert_not_called()
    # ... (further assertions on args and player state)

@pytest.mark.asyncio
@patch("src.core.action_processor.get_db_session")
@patch("src.core.crud.crud_player.player_crud.get_many_by_ids", new_callable=AsyncMock)
@patch("src.core.crud.crud_party.party_crud.get_many_by_ids", new_callable=AsyncMock)
@patch("src.core.action_processor.log_event", new_callable=AsyncMock)
@patch("src.core.action_processor.get_player", new_callable=AsyncMock) # For _finalize_turn_processing
@patch("src.core.action_processor.get_party", new_callable=AsyncMock)   # For _finalize_turn_processing (not used in this test)
async def test_process_actions_single_player_with_both_actions(
    mock_get_party_ap: AsyncMock,
    mock_get_player_ap: AsyncMock,
    mock_log_event_ap: AsyncMock,
    mock_party_crud_get_many: AsyncMock,
    mock_player_crud_get_many: AsyncMock,
    mock_session_maker_in_ap: MagicMock,
    mock_session: AsyncMock,
    mock_player_1_with_both_actions: Player
):
    import src.core.action_processor
    placeholder_handler_mock: AsyncMock = src.core.action_processor._handle_placeholder_action # type: ignore
    move_handler_mock: AsyncMock = src.core.action_processor._handle_move_action_wrapper # type: ignore

    placeholder_handler_mock.reset_mock()
    move_handler_mock.reset_mock()
    mock_log_event_ap.reset_mock()

    mock_player_crud_get_many.return_value = [mock_player_1_with_both_actions]
    mock_party_crud_get_many.return_value = []
    mock_get_player_ap.return_value = mock_player_1_with_both_actions # For finalize step

    mock_session_maker_in_ap.return_value.__aenter__.return_value = mock_session

    await process_actions_for_guild(DEFAULT_GUILD_ID, [{"id": PLAYER_ID_PK_1, "type": "player"}])

    assert placeholder_handler_mock.call_count == 1
    assert move_handler_mock.call_count == 1
    # ... (further assertions)

@pytest.mark.asyncio
@patch("src.core.action_processor.get_db_session")
@patch("src.core.crud.crud_player.player_crud.get_many_by_ids", new_callable=AsyncMock)
@patch("src.core.crud.crud_party.party_crud.get_many_by_ids", new_callable=AsyncMock)
@patch("src.core.action_processor.log_event", new_callable=AsyncMock)
@patch("src.core.action_processor.get_player", new_callable=AsyncMock) # For _finalize_turn_processing
@patch("src.core.action_processor.get_party", new_callable=AsyncMock)   # For _finalize_turn_processing
async def test_process_actions_party_with_one_player_actions(
    mock_get_party_ap: AsyncMock,
    mock_get_player_ap: AsyncMock,
    mock_log_event_ap: AsyncMock,
    mock_party_crud_get_many: AsyncMock,
    mock_player_crud_get_many: AsyncMock,
    mock_session_maker_in_ap: MagicMock,
    mock_session: AsyncMock,
    mock_player_1_with_both_actions: Player, mock_party_with_player_1: Party
):
    import src.core.action_processor
    placeholder_handler_mock: AsyncMock = src.core.action_processor._handle_placeholder_action # type: ignore
    move_handler_mock: AsyncMock = src.core.action_processor._handle_move_action_wrapper # type: ignore

    placeholder_handler_mock.reset_mock()
    move_handler_mock.reset_mock()
    mock_log_event_ap.reset_mock()

    mock_party_crud_get_many.return_value = [mock_party_with_player_1]
    # _load_and_clear_all_actions will fetch players based on party.player_ids_json
    mock_player_crud_get_many.return_value = [mock_player_1_with_both_actions]

    # For _finalize_turn_processing
    mock_get_player_ap.return_value = mock_player_1_with_both_actions
    mock_get_party_ap.return_value = mock_party_with_player_1


    mock_session_maker_in_ap.return_value.__aenter__.return_value = mock_session

    await process_actions_for_guild(DEFAULT_GUILD_ID, [{"id": PARTY_ID_PK_1, "type": "party"}])

    assert placeholder_handler_mock.call_count == 1
    assert move_handler_mock.call_count == 1
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
    import src.core.action_processor
    placeholder_handler_mock: AsyncMock = src.core.action_processor._handle_placeholder_action # type: ignore

    placeholder_handler_mock.reset_mock()

    mock_session_maker_in_ap.return_value.__aenter__.return_value = mock_session
    mock_get_player.return_value = mock_player_2_no_actions

    await process_actions_for_guild(DEFAULT_GUILD_ID, [{"id": PLAYER_ID_PK_2, "type": "player"}])

    placeholder_handler_mock.assert_not_called()
    # ... (further assertions)

@pytest.mark.asyncio
@patch("src.core.action_processor.get_db_session")
@patch("src.core.crud.crud_player.player_crud.get_many_by_ids", new_callable=AsyncMock)
@patch("src.core.crud.crud_party.party_crud.get_many_by_ids", new_callable=AsyncMock)
@patch("src.core.action_processor.log_event", new_callable=AsyncMock)
@patch("src.core.action_processor.get_player", new_callable=AsyncMock) # For _finalize_turn_processing
@patch("src.core.action_processor.get_party", new_callable=AsyncMock)   # For _finalize_turn_processing
async def test_process_actions_unknown_intent_uses_placeholder(
    mock_get_party_ap: AsyncMock,
    mock_get_player_ap: AsyncMock,
    mock_log_event_ap: AsyncMock,
    mock_party_crud_get_many: AsyncMock,
    mock_player_crud_get_many: AsyncMock,
    mock_session_maker_in_ap: MagicMock,
    mock_session: AsyncMock
):
    import src.core.action_processor
    placeholder_handler_mock: AsyncMock = src.core.action_processor._handle_placeholder_action # type: ignore
    placeholder_handler_mock.reset_mock()
    mock_log_event_ap.reset_mock()

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

    mock_player_crud_get_many.return_value = [player_for_test]
    mock_party_crud_get_many.return_value = []
    mock_get_player_ap.return_value = player_for_test # For finalize step

    mock_session_maker_in_ap.return_value.__aenter__.return_value = mock_session

    await process_actions_for_guild(DEFAULT_GUILD_ID, [{"id": PLAYER_ID_PK_1, "type": "player"}])

    placeholder_handler_mock.assert_called_once()
    # ... (further assertions on args)
