import sys
import os
import pytest
import asyncio
import json
import logging
import datetime
from unittest.mock import AsyncMock, patch, MagicMock, call, ANY

import discord # For discord.Message in process_player_message_for_nlu
from discord.ext import commands # For commands.Bot in process_player_message_for_nlu

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession

# Removed _load_and_clear_actions from import
from backend.core.action_processor import process_actions_for_guild
from backend.models import Player, Party
from backend.models.actions import ParsedAction, ActionEntity
from backend.models.enums import PlayerStatus, PartyTurnStatus

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
    # Async methods correctly mocked as AsyncMock
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock()
    session.scalars = AsyncMock()

    # Synchronous methods should be MagicMock
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.delete = MagicMock()
    session.merge = MagicMock()
    session.expire = MagicMock()
    session.expunge = MagicMock()
    session.is_modified = MagicMock()
    # session.get_bind() is also sync, but less likely to cause this specific warning unless called.

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
    mocker.patch('backend.core.action_processor._handle_placeholder_action', new=mock_placeholder_handler)
    mocker.patch('backend.core.action_processor._handle_move_action_wrapper', new=mock_move_handler)
    mocker.patch('backend.core.action_processor._handle_intra_location_action_wrapper', new=mock_intra_location_handler)

    # Critically, update the ACTION_DISPATCHER dictionary itself to use these mocks,
    # because it captured references to the original functions at module definition time.
    import backend.core.action_processor

    # Ensure these specific keys in the live ACTION_DISPATCHER point to our new mocks.
    # For intents that are supposed to use the default _handle_placeholder_action (now mock_placeholder_handler),
    # if they are explicitly listed, they also need to be updated.
    # Based on the second (active) definition of ACTION_DISPATCHER in action_processor.py:
    backend.core.action_processor.ACTION_DISPATCHER["move"] = mock_move_handler
    backend.core.action_processor.ACTION_DISPATCHER["look"] = mock_placeholder_handler
    backend.core.action_processor.ACTION_DISPATCHER["attack"] = mock_placeholder_handler
    backend.core.action_processor.ACTION_DISPATCHER["take"] = mock_placeholder_handler
    backend.core.action_processor.ACTION_DISPATCHER["use"] = mock_placeholder_handler
    backend.core.action_processor.ACTION_DISPATCHER["talk"] = mock_placeholder_handler
    backend.core.action_processor.ACTION_DISPATCHER["examine"] = mock_intra_location_handler
    backend.core.action_processor.ACTION_DISPATCHER["interact"] = mock_intra_location_handler
    backend.core.action_processor.ACTION_DISPATCHER["go_to"] = mock_intra_location_handler
    # Any other intents in the live ACTION_DISPATCHER would need similar treatment if not using the default.

@pytest.fixture(autouse=True)
def configure_module_logging(caplog):
    caplog.set_level(logging.DEBUG, logger="backend.core.action_processor")

@pytest.mark.asyncio
@patch("backend.core.action_processor.get_db_session")
@patch("backend.core.crud.crud_player.player_crud.get_many_by_ids", new_callable=AsyncMock) # Patch for player_crud
@patch("backend.core.crud.crud_party.party_crud.get_many_by_ids", new_callable=AsyncMock)   # Patch for party_crud
@patch("backend.core.action_processor.log_event", new_callable=AsyncMock)
# mock_get_player and mock_get_party might not be needed if _load_and_clear_all_actions only uses get_many_by_ids
# but _finalize_turn_processing still uses get_player/get_party individually.
@patch("backend.core.action_processor.get_player", new_callable=AsyncMock)
@patch("backend.core.action_processor.get_party", new_callable=AsyncMock)
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
    import backend.core.action_processor
    placeholder_handler_mock: AsyncMock = backend.core.action_processor._handle_placeholder_action # type: ignore
    move_handler_mock: AsyncMock = backend.core.action_processor._handle_move_action_wrapper # type: ignore

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

    # START MOCK CONFIGURATION FOR CONFLICT CHECK and action loading
    # Simpler approach: Make session.execute return the count mock directly first.
    # This might break subsequent calls if they expect a different structure,
    # but it will test if the conflict check itself passes.

    # This sync_mock_result represents the SQLAlchemy Result object
    sync_mock_result_for_count = MagicMock()
    sync_mock_result_for_count.scalar_one_or_none.return_value = 0  # Simulate 0 pending conflicts

    # mock_session.execute is an AsyncMock. Its return_value (after await) should be sync_mock_result_for_count.
    mock_session.execute.side_effect = None # Clear any previous side_effect
    mock_session.execute.return_value = sync_mock_result_for_count
    # END MOCK CONFIGURATION

    await process_actions_for_guild(DEFAULT_GUILD_ID, [{"id": PLAYER_ID_PK_1, "type": "player"}])

    placeholder_handler_mock.assert_called_once()
    move_handler_mock.assert_not_called()
    # ... (further assertions on args and player state)

@pytest.mark.asyncio
@patch("backend.core.action_processor.get_db_session")
@patch("backend.core.crud.crud_player.player_crud.get_many_by_ids", new_callable=AsyncMock)
@patch("backend.core.crud.crud_party.party_crud.get_many_by_ids", new_callable=AsyncMock)
@patch("backend.core.action_processor.log_event", new_callable=AsyncMock)
@patch("backend.core.action_processor.get_player", new_callable=AsyncMock) # For _finalize_turn_processing
@patch("backend.core.action_processor.get_party", new_callable=AsyncMock)   # For _finalize_turn_processing (not used in this test)
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
    import backend.core.action_processor
    placeholder_handler_mock: AsyncMock = backend.core.action_processor._handle_placeholder_action # type: ignore
    move_handler_mock: AsyncMock = backend.core.action_processor._handle_move_action_wrapper # type: ignore

    placeholder_handler_mock.reset_mock()
    move_handler_mock.reset_mock()
    mock_log_event_ap.reset_mock()

    mock_player_crud_get_many.return_value = [mock_player_1_with_both_actions]
    mock_party_crud_get_many.return_value = []
    mock_get_player_ap.return_value = mock_player_1_with_both_actions # For finalize step

    mock_session_maker_in_ap.return_value.__aenter__.return_value = mock_session

    # START MOCK CONFIGURATION FOR CONFLICT CHECK and action loading
    # These mocks represent synchronous SQLAlchemy Result objects
    sync_mock_result_for_count = MagicMock()
    sync_mock_result_for_count.scalar_one_or_none.return_value = 0  # Simulate 0 pending conflicts

    sync_mock_result_for_player_load = MagicMock()
    mock_player_load_scalars = MagicMock() # This mock represents the object returned by .scalars()
    mock_player_load_scalars.all.return_value = [mock_player_1_with_both_actions]
    sync_mock_result_for_player_load.scalars.return_value = mock_player_load_scalars

    sync_mock_result_for_party_load = MagicMock()
    mock_party_load_scalars = MagicMock()
    mock_party_load_scalars.all.return_value = []
    sync_mock_result_for_party_load.scalars.return_value = mock_party_load_scalars

    default_sync_mock_result = MagicMock()
    default_sync_mock_result.scalar_one_or_none.return_value = None
    default_mock_scalars = MagicMock()
    default_mock_scalars.all.return_value = []
    default_sync_mock_result.scalars.return_value = default_mock_scalars

    def complex_execute_side_effect(*args, **kwargs):
        statement_str = str(args[0]).lower()
        # session.execute is an AsyncMock. Its side_effect (this function) should return
        # a synchronous MagicMock that mimics the SQLAlchemy Result object.
        if "count(" in statement_str and "pending_conflicts" in statement_str:
            return sync_mock_result_for_count
        elif "from players" in statement_str or "join players" in statement_str:
            return sync_mock_result_for_player_load
        elif "from parties" in statement_str or "join parties" in statement_str:
             return sync_mock_result_for_party_load
        return default_sync_mock_result

    mock_session.execute.side_effect = complex_execute_side_effect
    # END MOCK CONFIGURATION

    await process_actions_for_guild(DEFAULT_GUILD_ID, [{"id": PLAYER_ID_PK_1, "type": "player"}])

    assert placeholder_handler_mock.call_count == 1
    assert move_handler_mock.call_count == 1
    # ... (further assertions)

@pytest.mark.asyncio
@patch("backend.core.action_processor.get_db_session")
@patch("backend.core.crud.crud_player.player_crud.get_many_by_ids", new_callable=AsyncMock)
@patch("backend.core.crud.crud_party.party_crud.get_many_by_ids", new_callable=AsyncMock)
@patch("backend.core.action_processor.log_event", new_callable=AsyncMock)
@patch("backend.core.action_processor.get_player", new_callable=AsyncMock) # For _finalize_turn_processing
@patch("backend.core.action_processor.get_party", new_callable=AsyncMock)   # For _finalize_turn_processing
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
    import backend.core.action_processor
    placeholder_handler_mock: AsyncMock = backend.core.action_processor._handle_placeholder_action # type: ignore
    move_handler_mock: AsyncMock = backend.core.action_processor._handle_move_action_wrapper # type: ignore

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

    # START MOCK CONFIGURATION FOR CONFLICT CHECK and action loading
    sync_mock_result_for_count = MagicMock()
    sync_mock_result_for_count.scalar_one_or_none.return_value = 0

    sync_mock_result_for_player_load = MagicMock()
    mock_player_load_scalars = MagicMock()
    mock_player_load_scalars.all.return_value = [mock_player_1_with_both_actions]
    sync_mock_result_for_player_load.scalars.return_value = mock_player_load_scalars

    sync_mock_result_for_party_load = MagicMock()
    mock_party_load_scalars = MagicMock()
    mock_party_load_scalars.all.return_value = [mock_party_with_player_1]
    sync_mock_result_for_party_load.scalars.return_value = mock_party_load_scalars

    default_sync_mock_result = MagicMock()
    default_sync_mock_result.scalar_one_or_none.return_value = None
    default_mock_scalars = MagicMock()
    default_mock_scalars.all.return_value = []
    default_sync_mock_result.scalars.return_value = default_mock_scalars

    def complex_execute_side_effect(*args, **kwargs):
        statement_str = str(args[0]).lower()
        if "count(" in statement_str and "pending_conflicts" in statement_str:
            return sync_mock_result_for_count
        elif "from players" in statement_str or "join players" in statement_str:
            return sync_mock_result_for_player_load
        elif "from parties" in statement_str or "join parties" in statement_str:
             return sync_mock_result_for_party_load
        return default_sync_mock_result
    mock_session.execute.side_effect = complex_execute_side_effect
    # END MOCK CONFIGURATION

    await process_actions_for_guild(DEFAULT_GUILD_ID, [{"id": PARTY_ID_PK_1, "type": "party"}])

    assert placeholder_handler_mock.call_count == 1
    assert move_handler_mock.call_count == 1
    # ... (further assertions)

@pytest.mark.asyncio
@patch("backend.core.action_processor.get_db_session")
@patch("backend.core.action_processor.get_player", new_callable=AsyncMock)
@patch("backend.core.action_processor.log_event", new_callable=AsyncMock)
async def test_process_actions_player_no_actions(
    mock_log_event_ap: AsyncMock, mock_get_player: AsyncMock,
    mock_session_maker_in_ap: MagicMock, mock_session: AsyncMock,
    mock_player_2_no_actions: Player
):
    import backend.core.action_processor
    placeholder_handler_mock: AsyncMock = backend.core.action_processor._handle_placeholder_action # type: ignore

    placeholder_handler_mock.reset_mock()

    mock_session_maker_in_ap.return_value.__aenter__.return_value = mock_session
    mock_get_player.return_value = mock_player_2_no_actions

    await process_actions_for_guild(DEFAULT_GUILD_ID, [{"id": PLAYER_ID_PK_2, "type": "player"}])

    placeholder_handler_mock.assert_not_called()
    # ... (further assertions)

@pytest.mark.asyncio
@patch("backend.core.action_processor.get_db_session")
@patch("backend.core.crud.crud_player.player_crud.get_many_by_ids", new_callable=AsyncMock)
@patch("backend.core.crud.crud_party.party_crud.get_many_by_ids", new_callable=AsyncMock)
@patch("backend.core.action_processor.log_event", new_callable=AsyncMock)
@patch("backend.core.action_processor.get_player", new_callable=AsyncMock) # For _finalize_turn_processing
@patch("backend.core.action_processor.get_party", new_callable=AsyncMock)   # For _finalize_turn_processing
async def test_process_actions_unknown_intent_uses_placeholder(
    mock_get_party_ap: AsyncMock,
    mock_get_player_ap: AsyncMock,
    mock_log_event_ap: AsyncMock,
    mock_party_crud_get_many: AsyncMock,
    mock_player_crud_get_many: AsyncMock,
    mock_session_maker_in_ap: MagicMock,
    mock_session: AsyncMock
):
    import backend.core.action_processor
    placeholder_handler_mock: AsyncMock = backend.core.action_processor._handle_placeholder_action # type: ignore
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

    # START MOCK CONFIGURATION FOR CONFLICT CHECK and action loading
    sync_mock_result_for_count = MagicMock()
    sync_mock_result_for_count.scalar_one_or_none.return_value = 0

    sync_mock_result_for_player_load = MagicMock()
    mock_player_load_scalars = MagicMock()
    mock_player_load_scalars.all.return_value = [player_for_test]
    sync_mock_result_for_player_load.scalars.return_value = mock_player_load_scalars

    sync_mock_result_for_party_load = MagicMock()
    mock_party_load_scalars = MagicMock()
    mock_party_load_scalars.all.return_value = []
    sync_mock_result_for_party_load.scalars.return_value = mock_party_load_scalars

    default_sync_mock_result = MagicMock()
    default_sync_mock_result.scalar_one_or_none.return_value = None
    default_mock_scalars = MagicMock()
    default_mock_scalars.all.return_value = []
    default_sync_mock_result.scalars.return_value = default_mock_scalars

    def complex_execute_side_effect(*args, **kwargs):
        statement_str = str(args[0]).lower()
        if "count(" in statement_str and "pending_conflicts" in statement_str:
            return sync_mock_result_for_count
        elif "from players" in statement_str or "join players" in statement_str:
            return sync_mock_result_for_player_load
        elif "from parties" in statement_str or "join parties" in statement_str:
             return sync_mock_result_for_party_load
        return default_sync_mock_result
    mock_session.execute.side_effect = complex_execute_side_effect
    # END MOCK CONFIGURATION

    await process_actions_for_guild(DEFAULT_GUILD_ID, [{"id": PLAYER_ID_PK_1, "type": "player"}])

    placeholder_handler_mock.assert_called_once()
    # ... (further assertions on args)

# --- Granular tests for helper functions ---

from backend.core.action_processor import _load_and_clear_all_actions, _execute_player_actions, _finalize_turn_processing

@pytest.mark.asyncio
async def test_load_and_clear_all_actions_empty_entities(mock_session: AsyncMock):
    actions = await _load_and_clear_all_actions(mock_session, DEFAULT_GUILD_ID, [])
    assert actions == []

@pytest.mark.asyncio
@patch("backend.core.crud.crud_player.player_crud.get_many_by_ids", new_callable=AsyncMock)
@patch("backend.core.crud.crud_party.party_crud.get_many_by_ids", new_callable=AsyncMock)
async def test_load_and_clear_all_actions_single_player_with_actions(
    mock_party_crud_get_many: AsyncMock,
    mock_player_crud_get_many: AsyncMock,
    mock_session: AsyncMock,
    mock_player_1_with_both_actions: Player # Has 2 actions
):
    mock_player_crud_get_many.return_value = [mock_player_1_with_both_actions]
    mock_party_crud_get_many.return_value = [] # No parties

    entities_to_process = [{"id": PLAYER_ID_PK_1, "type": "player"}]

    player_action_tuples = await _load_and_clear_all_actions(mock_session, DEFAULT_GUILD_ID, entities_to_process)

    assert len(player_action_tuples) == 2
    assert player_action_tuples[0][0] == PLAYER_ID_PK_1
    assert player_action_tuples[0][1].intent == "look"
    assert player_action_tuples[1][0] == PLAYER_ID_PK_1
    assert player_action_tuples[1][1].intent == "move"

    # Check that actions were cleared and player added to session
    assert mock_player_1_with_both_actions.collected_actions_json == []
    mock_session.add.assert_called_with(mock_player_1_with_both_actions)
    mock_player_crud_get_many.assert_called_once_with(session=mock_session, ids=[PLAYER_ID_PK_1], guild_id=DEFAULT_GUILD_ID) # Changed db to session
    mock_party_crud_get_many.assert_not_called()


@pytest.mark.asyncio
@patch("backend.core.crud.crud_player.player_crud.get_many_by_ids", new_callable=AsyncMock)
@patch("backend.core.crud.crud_party.party_crud.get_many_by_ids", new_callable=AsyncMock)
async def test_load_and_clear_all_actions_party_with_player_actions(
    mock_party_crud_get_many: AsyncMock,
    mock_player_crud_get_many: AsyncMock,
    mock_session: AsyncMock,
    mock_player_1_with_look_action: Player, # Has 1 action
    mock_party_with_player_1: Party # Party contains player 1
):
    # Modify fixture for this test: party contains player_1_with_look_action
    mock_party_with_player_1.player_ids_json = [mock_player_1_with_look_action.id]

    mock_party_crud_get_many.return_value = [mock_party_with_player_1]
    mock_player_crud_get_many.return_value = [mock_player_1_with_look_action]

    entities_to_process = [{"id": PARTY_ID_PK_1, "type": "party"}]

    player_action_tuples = await _load_and_clear_all_actions(mock_session, DEFAULT_GUILD_ID, entities_to_process)

    assert len(player_action_tuples) == 1
    assert player_action_tuples[0][0] == mock_player_1_with_look_action.id
    assert player_action_tuples[0][1].intent == "look"

    assert mock_player_1_with_look_action.collected_actions_json == []
    mock_session.add.assert_called_with(mock_player_1_with_look_action)
    mock_party_crud_get_many.assert_called_once_with(session=mock_session, ids=[PARTY_ID_PK_1], guild_id=DEFAULT_GUILD_ID) # Changed db to session
    mock_player_crud_get_many.assert_called_once_with(session=mock_session, ids=[mock_player_1_with_look_action.id], guild_id=DEFAULT_GUILD_ID) # Changed db to session


@pytest.mark.asyncio
@patch("backend.core.crud.crud_player.player_crud.get_many_by_ids", new_callable=AsyncMock)
async def test_load_and_clear_all_actions_player_malformed_json(
    mock_player_crud_get_many: AsyncMock,
    mock_session: AsyncMock
):
    malformed_player = Player(
        id=PLAYER_ID_PK_1, discord_id=PLAYER_DISCORD_ID_1, guild_id=DEFAULT_GUILD_ID,
        name="MalformedPlayer", collected_actions_json='[{"intent": "test", "entities": []}, {"bad_json"', # Malformed
        current_status=PlayerStatus.PROCESSING_GUILD_TURN
    )
    mock_player_crud_get_many.return_value = [malformed_player]
    entities_to_process = [{"id": PLAYER_ID_PK_1, "type": "player"}]

    with patch('backend.core.action_processor.logger.error') as mock_logger_error:
        player_action_tuples = await _load_and_clear_all_actions(mock_session, DEFAULT_GUILD_ID, entities_to_process)

    assert len(player_action_tuples) == 0 # Should skip malformed and not load actions
    assert malformed_player.collected_actions_json == [] # Actions should be cleared
    mock_session.add.assert_called_with(malformed_player)
    mock_logger_error.assert_any_call(f"[ACTION_PROCESSOR] Failed to decode actions for player {PLAYER_ID_PK_1}", exc_info=True)


@pytest.mark.asyncio
@patch("backend.core.crud.crud_player.player_crud.get_many_by_ids", new_callable=AsyncMock)
async def test_load_and_clear_all_actions_player_action_parsing_error(
    mock_player_crud_get_many: AsyncMock,
    mock_session: AsyncMock
):
    # Valid JSON, but content doesn't match ParsedAction model (e.g., missing 'intent')
    action_bad_schema = {"raw_text": "do something", "timestamp": fixed_dt_str}
    player_bad_action_schema = Player(
        id=PLAYER_ID_PK_1, discord_id=PLAYER_DISCORD_ID_1, guild_id=DEFAULT_GUILD_ID,
        name="PlayerBadActionSchema", collected_actions_json=json.dumps([look_action_data, action_bad_schema]),
        current_status=PlayerStatus.PROCESSING_GUILD_TURN
    )
    mock_player_crud_get_many.return_value = [player_bad_action_schema]
    entities_to_process = [{"id": PLAYER_ID_PK_1, "type": "player"}]

    with patch('backend.core.action_processor.logger.error') as mock_logger_error:
        player_action_tuples = await _load_and_clear_all_actions(mock_session, DEFAULT_GUILD_ID, entities_to_process)

    assert len(player_action_tuples) == 1 # Only the valid 'look' action
    assert player_action_tuples[0][1].intent == "look"
    assert player_bad_action_schema.collected_actions_json == []
    mock_session.add.assert_called_with(player_bad_action_schema)
    mock_logger_error.assert_any_call(f"Player {PLAYER_ID_PK_1}, action item 1 failed Pydantic parsing: {action_bad_schema}", exc_info=True)


@pytest.mark.asyncio
async def test_execute_player_actions_empty_list(mock_session_maker: MagicMock):
    results = await _execute_player_actions(mock_session_maker, DEFAULT_GUILD_ID, [])
    assert results == []
    mock_session_maker.assert_not_called()


@pytest.mark.asyncio
@patch("backend.core.action_processor.log_event", new_callable=AsyncMock) # For logging ACTION_PROCESSING_ERROR
async def test_execute_player_actions_handler_exception(
    mock_log_event_execute: AsyncMock,
    mock_session_maker: MagicMock, # From conftest or defined here
    mock_session: AsyncMock # The session object returned by the maker
):
    import backend.core.action_processor # To access patched ACTION_DISPATCHER

    failing_action = ParsedAction(**look_action_data) # Use look_action_data for structure
    failing_action.intent = "failing_intent" # Ensure it's a distinct intent for mocking

    # Mock the specific handler for "failing_intent" to raise an error
    mock_failing_handler = AsyncMock(side_effect=ValueError("Handler boom!"))
    original_dispatcher_entry = backend.core.action_processor.ACTION_DISPATCHER.get("failing_intent")
    backend.core.action_processor.ACTION_DISPATCHER["failing_intent"] = mock_failing_handler

    actions_to_run = [(PLAYER_ID_PK_1, failing_action)]

    results = await _execute_player_actions(mock_session_maker, DEFAULT_GUILD_ID, actions_to_run)

    assert len(results) == 1
    assert results[0]["player_id"] == PLAYER_ID_PK_1
    assert results[0]["action"]["intent"] == "failing_intent"
    assert results[0]["result"]["status"] == "error"
    assert "Handler boom!" in results[0]["result"]["message"]

    mock_failing_handler.assert_called_once_with(mock_session, DEFAULT_GUILD_ID, PLAYER_ID_PK_1, failing_action)

    # Check that ACTION_PROCESSING_ERROR was logged
    mock_log_event_execute.assert_called_once()
    log_call_args = mock_log_event_execute.call_args[0] # Positional args
    log_call_kwargs = mock_log_event_execute.call_args[1] # Keyword args

    assert log_call_kwargs.get('event_type') == "ACTION_PROCESSING_ERROR" # Accessing via .get for safety
    assert log_call_kwargs.get('details_json', {}).get('player_id') == PLAYER_ID_PK_1
    assert "Handler boom!" in log_call_kwargs.get('details_json', {}).get('error', "")

    # Restore original dispatcher if it existed, or remove the test entry
    if original_dispatcher_entry:
        backend.core.action_processor.ACTION_DISPATCHER["failing_intent"] = original_dispatcher_entry
    else:
        del backend.core.action_processor.ACTION_DISPATCHER["failing_intent"]


@pytest.mark.asyncio
async def test_execute_player_actions_dispatch_and_results(
    mock_session_maker: MagicMock, # From conftest or defined here
    mock_session: AsyncMock, # The session object returned by the maker
):
    # Uses handlers patched by patch_action_handlers_directly fixture
    import backend.core.action_processor
    placeholder_handler_mock: AsyncMock = backend.core.action_processor._handle_placeholder_action # type: ignore
    move_handler_mock: AsyncMock = backend.core.action_processor._handle_move_action_wrapper # type: ignore

    placeholder_handler_mock.reset_mock()
    move_handler_mock.reset_mock()
    # Ensure specific return values for this test if needed, or rely on fixture defaults
    placeholder_handler_mock.return_value = {"status": "placeholder_done"}
    move_handler_mock.return_value = {"status": "move_done"}


    action1 = ParsedAction(**look_action_data) # Uses placeholder
    action2 = ParsedAction(**move_action_data) # Uses move_handler

    actions_to_run = [
        (PLAYER_ID_PK_1, action1),
        (PLAYER_ID_PK_2, action2)
    ]

    results = await _execute_player_actions(mock_session_maker, DEFAULT_GUILD_ID, actions_to_run)

    assert len(results) == 2
    placeholder_handler_mock.assert_called_once_with(mock_session, DEFAULT_GUILD_ID, PLAYER_ID_PK_1, action1)
    move_handler_mock.assert_called_once_with(mock_session, DEFAULT_GUILD_ID, PLAYER_ID_PK_2, action2)

    assert results[0]["result"] == {"status": "placeholder_done"}
    assert results[1]["result"] == {"status": "move_done"}
    assert mock_session_maker.call_count == 2 # One session per action
    # Each session should have begin/commit called by its context manager
    assert mock_session.begin.call_count == 2 # begin is on the session obj
    # The commit is on the transaction context manager returned by begin()
    # The mock_session fixture's begin() returns a CM that calls session.commit() on exit.
    assert mock_session.commit.call_count == 2


@pytest.mark.asyncio
@patch("backend.core.action_processor.log_event", new_callable=AsyncMock)
@patch("backend.core.action_processor.get_player", new_callable=AsyncMock)
@patch("backend.core.action_processor.get_party", new_callable=AsyncMock)
async def test_finalize_turn_processing_updates_statuses_and_logs(
    mock_get_party_finalize: AsyncMock,
    mock_get_player_finalize: AsyncMock,
    mock_log_event_finalize: AsyncMock,
    mock_session_maker: MagicMock, # From conftest or defined here
    mock_session: AsyncMock, # The session object returned by the maker
    mock_player_1_with_look_action: Player, # Re-use existing fixture, status will be PROCESSING_GUILD_TURN
    mock_party_with_player_1: Party # Re-use existing fixture, status will be PROCESSING_GUILD_TURN
):
    # Ensure fixtures are in the state expected by _finalize_turn_processing
    mock_player_1_with_look_action.current_status = PlayerStatus.PROCESSING_GUILD_TURN
    # Player 2 is part of the party but will be fetched individually by id if party.player_ids_json is processed
    player_2_in_party = Player(id=PLAYER_ID_PK_2, guild_id=DEFAULT_GUILD_ID, current_status=PlayerStatus.PROCESSING_GUILD_TURN)

    mock_party_with_player_1.turn_status = PartyTurnStatus.PROCESSING_GUILD_TURN
    mock_party_with_player_1.player_ids_json = [mock_player_1_with_look_action.id, player_2_in_party.id]

    entities_to_process = [
        {"id": mock_player_1_with_look_action.id, "type": "player"}, # This player is also in party
        {"id": mock_party_with_player_1.id, "type": "party"}
    ]

    # Side effect for get_player: return specific players based on ID
    def get_player_side_effect(session, guild_id, player_id_pk):
        if player_id_pk == mock_player_1_with_look_action.id:
            return mock_player_1_with_look_action
        if player_id_pk == player_2_in_party.id:
            return player_2_in_party
        return None
    mock_get_player_finalize.side_effect = get_player_side_effect
    mock_get_party_finalize.return_value = mock_party_with_player_1

    await _finalize_turn_processing(mock_session_maker, DEFAULT_GUILD_ID, entities_to_process, 5) # 5 dummy results count

    # Player 1 status (directly processed and as party member)
    assert mock_player_1_with_look_action.current_status == PlayerStatus.EXPLORING
    # Player 2 status (as party member)
    assert player_2_in_party.current_status == PlayerStatus.EXPLORING
    # Party status
    assert mock_party_with_player_1.turn_status == PartyTurnStatus.IDLE

    # Check session.add calls
    expected_add_calls = [
        call(mock_player_1_with_look_action), # Updated directly
        call(mock_party_with_player_1),       # Party updated
        # call(mock_player_1_with_look_action), # Updated again as party member - MagicMock tracks unique calls by default
        call(player_2_in_party)               # Player 2 as party member updated
    ]
    # mock_session.add.assert_has_calls(expected_add_calls, any_order=True)
    # More robust: check how many times add was called on each specific object
    # For this, we'd need to inspect call_args_list of mock_session.add
    # For simplicity, let's check total calls to add. Player1 is added twice effectively if not careful.
    # The code adds player1 first, then party, then iterates party members.
    # If player1 is already EXPLORING, it won't be added again. But the first add would have happened.
    # Let's check the number of distinct objects added.
    added_objects = {c.args[0] for c in mock_session.add.call_args_list}
    assert mock_player_1_with_look_action in added_objects
    assert mock_party_with_player_1 in added_objects
    assert player_2_in_party in added_objects
    assert len(added_objects) == 3


    mock_log_event_finalize.assert_called_once()
    log_kwargs = mock_log_event_finalize.call_args[1]
    assert log_kwargs["event_type"] == "GUILD_TURN_PROCESSED"
    assert log_kwargs["guild_id"] == DEFAULT_GUILD_ID
    assert log_kwargs["details_json"]["processed_entities"] == entities_to_process
    assert log_kwargs["details_json"]["results_summary_count"] == 5

    assert mock_session.commit.call_count == 1 # Commit by the session's context manager in finalize

@pytest.mark.asyncio
@patch("backend.core.action_processor.log_event", new_callable=AsyncMock)
@patch("backend.core.action_processor.get_player", new_callable=AsyncMock)
async def test_finalize_turn_processing_player_not_processing(
    mock_get_player_finalize: AsyncMock,
    mock_log_event_finalize: AsyncMock,
    mock_session_maker: MagicMock,
    mock_session: AsyncMock,
):
    player_exploring = Player(id=PLAYER_ID_PK_1, guild_id=DEFAULT_GUILD_ID, current_status=PlayerStatus.EXPLORING)
    mock_get_player_finalize.return_value = player_exploring
    entities_to_process = [{"id": PLAYER_ID_PK_1, "type": "player"}]

    await _finalize_turn_processing(mock_session_maker, DEFAULT_GUILD_ID, entities_to_process, 0)

    assert player_exploring.current_status == PlayerStatus.EXPLORING # Should remain unchanged
    # mock_session.add should not be called for this player as status didn't change
    # However, if other entities were processed and changed, add would be called for them.
    # Here, only one player, no change.
    # If we want to be strict, we'd check that add was NOT called with player_exploring.
    # For this isolated test, it means add wasn't called at all for entity updates.

    # Check if session.add was called with player_exploring
    player_added_to_session = False
    for call_args_tuple in mock_session.add.call_args_list:
        if call_args_tuple.args[0] == player_exploring:
            player_added_to_session = True
            break
    assert not player_added_to_session

    mock_log_event_finalize.assert_called_once() # Log event still happens
    assert mock_session.commit.call_count == 1

# --- Tests for _handle_move_action_wrapper specifically ---

from backend.core.action_processor import _handle_move_action_wrapper

@pytest.mark.asyncio
# Corrected patch path to where execute_move_for_player_action is defined
@patch("backend.core.movement_logic.execute_move_for_player_action", new_callable=AsyncMock)
async def test_handle_move_action_wrapper_success(
    mock_execute_move: AsyncMock,
    mock_session: AsyncMock
):
    player_id_pk = PLAYER_ID_PK_1
    target_id = "the_void"
    action = ParsedAction(
        raw_text="move the_void", intent="move", guild_id=DEFAULT_GUILD_ID, player_id=PLAYER_DISCORD_ID_1,
        timestamp=datetime.datetime.fromisoformat(fixed_dt_str),
        entities=[ActionEntity(type="location_static_id", value=target_id)]
    )
    expected_result = {"status": "success", "message": "Moved to the_void"}
    mock_execute_move.return_value = expected_result

    result = await _handle_move_action_wrapper(mock_session, DEFAULT_GUILD_ID, player_id_pk, action)

    assert result == expected_result
    mock_execute_move.assert_called_once_with(
        session=mock_session,
        guild_id=DEFAULT_GUILD_ID,
        player_id=player_id_pk,
        target_location_identifier=target_id
    )

@pytest.mark.asyncio
@patch("backend.core.movement_logic.execute_move_for_player_action", new_callable=AsyncMock)
async def test_handle_move_action_wrapper_extracts_target_from_location_name_entity(
    mock_execute_move: AsyncMock,
    mock_session: AsyncMock
):
    player_id_pk = PLAYER_ID_PK_1
    target_name = "Old Town"
    action = ParsedAction(
        raw_text="go Old Town", intent="move", guild_id=DEFAULT_GUILD_ID, player_id=PLAYER_DISCORD_ID_1,
        timestamp=datetime.datetime.fromisoformat(fixed_dt_str),
        entities=[ActionEntity(type="location_name", value=target_name)]
    )
    mock_execute_move.return_value = {"status": "success"} # Result doesn't matter for this check

    await _handle_move_action_wrapper(mock_session, DEFAULT_GUILD_ID, player_id_pk, action)
    mock_execute_move.assert_called_once_with(
        session=mock_session, guild_id=DEFAULT_GUILD_ID, player_id=player_id_pk,
        target_location_identifier=target_name
    )

@pytest.mark.asyncio
@patch("backend.core.movement_logic.execute_move_for_player_action", new_callable=AsyncMock)
async def test_handle_move_action_wrapper_extracts_target_from_single_untyped_entity(
    mock_execute_move: AsyncMock,
    mock_session: AsyncMock
):
    player_id_pk = PLAYER_ID_PK_1
    target_value = "market_square"
    action = ParsedAction(
        raw_text="move market_square", intent="move", guild_id=DEFAULT_GUILD_ID, player_id=PLAYER_DISCORD_ID_1,
        timestamp=datetime.datetime.fromisoformat(fixed_dt_str),
        entities=[ActionEntity(type="destination", value=target_value)] # type "destination" is generic
    )
    mock_execute_move.return_value = {"status": "success"}

    # Test relies on the heuristic that if one entity of type "destination", "target", "location",
    # or if it's the *only* entity, its value is used.
    await _handle_move_action_wrapper(mock_session, DEFAULT_GUILD_ID, player_id_pk, action)
    mock_execute_move.assert_called_once_with(
        session=mock_session, guild_id=DEFAULT_GUILD_ID, player_id=player_id_pk,
        target_location_identifier=target_value
    )

@pytest.mark.asyncio
async def test_handle_move_action_wrapper_no_target_identifier(
    mock_session: AsyncMock
):
    player_id_pk = PLAYER_ID_PK_1
    action_no_target = ParsedAction( # No entities or unclear entities
        raw_text="move", intent="move", guild_id=DEFAULT_GUILD_ID, player_id=PLAYER_DISCORD_ID_1,
        timestamp=datetime.datetime.fromisoformat(fixed_dt_str), entities=[]
    )
    result = await _handle_move_action_wrapper(mock_session, DEFAULT_GUILD_ID, player_id_pk, action_no_target)
    assert result["status"] == "error"
    assert "Target location not specified clearly" in result["message"]

    action_multiple_unclear_entities = ParsedAction(
        raw_text="move north fast", intent="move", guild_id=DEFAULT_GUILD_ID, player_id=PLAYER_DISCORD_ID_1,
        timestamp=datetime.datetime.fromisoformat(fixed_dt_str),
        entities=[ActionEntity(type="direction", value="north"), ActionEntity(type="manner", value="fast")]
    )
    result_multi = await _handle_move_action_wrapper(mock_session, DEFAULT_GUILD_ID, player_id_pk, action_multiple_unclear_entities)
    assert result_multi["status"] == "error"
    assert "Target location not specified clearly" in result_multi["message"]


@pytest.mark.asyncio
@patch("backend.core.movement_logic.execute_move_for_player_action", new_callable=AsyncMock)
async def test_handle_move_action_wrapper_execute_move_raises_exception(
    mock_execute_move: AsyncMock,
    mock_session: AsyncMock
):
    player_id_pk = PLAYER_ID_PK_1
    target_id = "dangerous_lair"
    action = ParsedAction(
        raw_text="move dangerous_lair", intent="move", guild_id=DEFAULT_GUILD_ID, player_id=PLAYER_DISCORD_ID_1,
        timestamp=datetime.datetime.fromisoformat(fixed_dt_str),
        entities=[ActionEntity(type="location_static_id", value=target_id)]
    )
    error_message = "It's too spooky!"
    mock_execute_move.side_effect = Exception(error_message)

    result = await _handle_move_action_wrapper(mock_session, DEFAULT_GUILD_ID, player_id_pk, action)

    assert result["status"] == "error"
    assert f"Failed to execute move action due to an internal error: {error_message}" in result["message"]
    mock_execute_move.assert_called_once()

# --- Tests for Conflict Signaling in process_actions_for_guild ---

@pytest.mark.asyncio
@patch("backend.core.action_processor.get_db_session") # Patches the session_maker for process_actions_for_guild
@patch("backend.core.crud.crud_pending_conflict.pending_conflict_crud") # Patched at definition/import site
@patch("backend.core.action_processor._load_and_clear_all_actions", new_callable=AsyncMock) # To check if called
@patch("backend.core.action_processor.log_event", new_callable=AsyncMock) # To check error logging
async def test_process_actions_halts_if_conflict_pending(
    mock_log_event_conflict_check: AsyncMock,
    mock_load_actions: AsyncMock,
    mock_actual_pending_conflict_crud: MagicMock, # This is the mock for the imported object
    mock_session_maker_in_ap: MagicMock, # This is the patched get_db_session
    mock_session: AsyncMock, # Session returned by the maker
    caplog # For checking log messages
):
    """
    Tests that process_actions_for_guild halts if pending_conflict_crud indicates active conflicts.
    """
    guild_id_test = DEFAULT_GUILD_ID
    mock_session_maker_in_ap.return_value.__aenter__.return_value = mock_session

    # Simulate active conflicts pending
    mock_actual_pending_conflict_crud.count_by_attributes = AsyncMock(return_value=1) # Configure the method on the mock

    caplog.clear() # Clear previous log captures
    with caplog.at_level(logging.INFO, logger="backend.core.action_processor"):
        await process_actions_for_guild(guild_id_test, [{"id": PLAYER_ID_PK_1, "type": "player"}])

    # Assertions
    # The actual object used inside process_actions_for_guild is pending_conflict_crud from its local import.
    # So, we assert on mock_actual_pending_conflict_crud.
    from backend.models.enums import ConflictStatus # Import for assertion
    mock_actual_pending_conflict_crud.count_by_attributes.assert_called_once_with(
        session=mock_session,
        guild_id=guild_id_test,
        status=ConflictStatus.PENDING_MASTER_RESOLUTION
    )
    mock_load_actions.assert_not_called() # Core processing step should be skipped

    assert any(
        f"Guild {guild_id_test}: Turn processing halted. 1 active conflict(s) require master resolution." in record.message
        for record in caplog.records
        if record.name == "backend.core.action_processor" # Ensure message is from the correct logger
    ), "Expected log message about halting due to conflict not found."

    # Ensure no error was logged for the conflict check itself
    # (i.e., the CONFLICT_CHECK_ERROR log_event was not called)
    # Check calls to mock_log_event_conflict_check
    found_conflict_check_error_log = False
    for call_obj in mock_log_event_conflict_check.call_args_list:
        if call_obj.kwargs.get('event_type') == "CONFLICT_CHECK_ERROR":
            found_conflict_check_error_log = True
            break
    assert not found_conflict_check_error_log, "CONFLICT_CHECK_ERROR should not have been logged."


@pytest.mark.asyncio
@patch("backend.core.action_processor.get_db_session")
@patch("backend.core.crud.crud_pending_conflict.pending_conflict_crud") # Patched at definition/import site
@patch("backend.core.action_processor._load_and_clear_all_actions", new_callable=AsyncMock)
@patch("backend.core.action_processor._execute_player_actions", new_callable=AsyncMock) # Further step
@patch("backend.core.action_processor._finalize_turn_processing", new_callable=AsyncMock) # Final step
@patch("backend.core.action_processor.log_event", new_callable=AsyncMock)
async def test_process_actions_proceeds_if_no_conflict_pending(
    mock_log_event_no_conflict: AsyncMock,
    mock_finalize_turn: AsyncMock,
    mock_execute_actions: AsyncMock,
    mock_load_actions: AsyncMock,
    mock_actual_pending_conflict_crud: MagicMock, # Mock for the imported object
    mock_session_maker_in_ap: MagicMock,
    mock_session: AsyncMock,
    caplog
):
    """
    Tests that process_actions_for_guild proceeds if no conflicts are pending.
    """
    guild_id_test = DEFAULT_GUILD_ID
    mock_session_maker_in_ap.return_value.__aenter__.return_value = mock_session

    # Simulate no active conflicts
    mock_actual_pending_conflict_crud.count_by_attributes = AsyncMock(return_value=0)
    mock_load_actions.return_value = [] # Simulate no actions loaded to simplify test

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="backend.core.action_processor"):
        await process_actions_for_guild(guild_id_test, [{"id": PLAYER_ID_PK_1, "type": "player"}])

    from backend.models.enums import ConflictStatus # Import for assertion
    mock_actual_pending_conflict_crud.count_by_attributes.assert_called_once_with(
        session=mock_session, guild_id=guild_id_test, status=ConflictStatus.PENDING_MASTER_RESOLUTION
    )
    mock_load_actions.assert_called_once() # Should be called if no conflict
    # If mock_load_actions.return_value is [], _execute_player_actions should NOT be called.
    if mock_load_actions.return_value:
        mock_execute_actions.assert_called_once()
    else:
        mock_execute_actions.assert_not_called()
    mock_finalize_turn.assert_called_once() # Should always be called at the end if not halted early

    assert not any(
        "Turn processing halted" in record.message for record in caplog.records
        if record.name == "backend.core.action_processor"
    ), "Log message about halting should not be present."

    found_conflict_check_error_log = False
    for call_obj in mock_log_event_no_conflict.call_args_list:
        if call_obj.kwargs.get('event_type') == "CONFLICT_CHECK_ERROR":
            found_conflict_check_error_log = True
            break
    assert not found_conflict_check_error_log, "CONFLICT_CHECK_ERROR should not have been logged."

@pytest.mark.asyncio
@patch("backend.core.action_processor.get_db_session")
@patch("backend.core.crud.crud_pending_conflict.pending_conflict_crud") # Patched at definition/import site
@patch("backend.core.action_processor._load_and_clear_all_actions", new_callable=AsyncMock)
@patch("backend.core.action_processor.log_event", new_callable=AsyncMock) # For logging CONFLICT_CHECK_ERROR
async def test_process_actions_handles_exception_during_conflict_check(
    mock_log_event_conflict_exception: AsyncMock,
    mock_load_actions_exception: AsyncMock, # Renamed to avoid clash
    mock_actual_pending_conflict_crud: MagicMock, # Mock for the imported object
    mock_session_maker_in_ap: MagicMock,
    mock_session: AsyncMock, # Session object
    caplog
):
    guild_id_test = DEFAULT_GUILD_ID
    mock_session_maker_in_ap.return_value.__aenter__.return_value = mock_session

    # Simulate an exception during the conflict check
    test_exception = Exception("DB connection error during conflict check")
    mock_actual_pending_conflict_crud.count_by_attributes = AsyncMock(side_effect=test_exception)

    caplog.clear()
    with caplog.at_level(logging.ERROR, logger="backend.core.action_processor"):
        await process_actions_for_guild(guild_id_test, [{"id": PLAYER_ID_PK_1, "type": "player"}])

    mock_actual_pending_conflict_crud.count_by_attributes.assert_called_once()
    mock_load_actions_exception.assert_not_called() # Processing should halt

    assert any(
        f"Error during pre-check for active conflicts: {test_exception}" in record.message
        for record in caplog.records
        if record.name == "backend.core.action_processor"
    ), "Expected error log for conflict check failure not found."

    # Check that CONFLICT_CHECK_ERROR was logged via log_event
    mock_log_event_conflict_exception.assert_called_once()
    log_call_args = mock_log_event_conflict_exception.call_args[0]
    log_call_kwargs = mock_log_event_conflict_exception.call_args[1]

    assert log_call_kwargs.get('guild_id') == guild_id_test
    assert log_call_kwargs.get('event_type') == "CONFLICT_CHECK_ERROR"
    assert log_call_kwargs.get('details_json', {}).get('error') == str(test_exception)
    assert log_call_kwargs.get('details_json', {}).get('phase') == "pre_conflict_check"


# --- Tests for process_player_message_for_nlu ---

from backend.core.action_processor import process_player_message_for_nlu
from backend.models.enums import PlayerStatus # Already imported but good for clarity
from backend.models.actions import ParsedAction, ActionEntity # Already imported

@pytest.fixture
def mock_bot_message():
    mock_message = MagicMock()
    mock_message.guild.id = DEFAULT_GUILD_ID
    mock_message.author.id = PLAYER_DISCORD_ID_1
    mock_message.content = "Hello NPC"
    mock_message.channel.send = AsyncMock()
    return mock_message

@pytest.fixture
def mock_player_dialogue_status():
    player = Player(
        id=PLAYER_ID_PK_1,
        discord_id=PLAYER_DISCORD_ID_1,
        guild_id=DEFAULT_GUILD_ID,
        name="DialoguePlayer",
        current_status=PlayerStatus.DIALOGUE,
        collected_actions_json="[]"
    )
    return player

@pytest.fixture
def mock_player_exploring_status():
    player = Player(
        id=PLAYER_ID_PK_1,
        discord_id=PLAYER_DISCORD_ID_1,
        guild_id=DEFAULT_GUILD_ID,
        name="ExploringPlayer",
        current_status=PlayerStatus.EXPLORING,
        collected_actions_json="[]"
    )
    return player

@pytest.mark.asyncio
@patch("backend.core.action_processor.player_crud.get_by_discord_id", new_callable=AsyncMock)
@patch("backend.core.nlu_service.parse_player_input", new_callable=AsyncMock) # Patched at source
@patch("backend.core.dialogue_system.handle_dialogue_input", new_callable=AsyncMock) # Patched at source
async def test_process_player_message_for_nlu_player_in_dialogue(
    mock_handle_dialogue_input: AsyncMock,
    mock_parse_nlu: AsyncMock,
    mock_get_player_by_discord_id: AsyncMock,
    mock_bot_message: MagicMock,
    mock_player_dialogue_status: Player,
    mock_session: AsyncMock # Re-use existing session mock
):
    mock_get_player_by_discord_id.return_value = mock_player_dialogue_status

    # NLU returns a specific action
    nlu_result_action = ParsedAction(
        raw_text=mock_bot_message.content, intent="talk_to_npc", guild_id=DEFAULT_GUILD_ID,
        player_id=PLAYER_DISCORD_ID_1, timestamp=datetime.datetime.now(datetime.timezone.utc),
        entities=[ActionEntity(type="npc_name", value="NPC")]
    )
    mock_parse_nlu.return_value = nlu_result_action

    # Dialogue system returns success
    mock_handle_dialogue_input.return_value = (True, "NPC says hello back", {"npc_name": "Friendly NPC"})

    await process_player_message_for_nlu(MagicMock(spec=commands.Bot), mock_bot_message, session=mock_session)

    mock_parse_nlu.assert_called_once_with(
        raw_text=mock_bot_message.content,
        guild_id=DEFAULT_GUILD_ID,
        player_id=mock_player_dialogue_status.id # Use DB id
    )
    mock_handle_dialogue_input.assert_called_once_with(
        session=mock_session,
        guild_id=DEFAULT_GUILD_ID,
        player_id=PLAYER_ID_PK_1,
        message_text=mock_bot_message.content,
        parsed_intent=nlu_result_action.intent,
            # Expect a list of dicts, as ActionEntity objects are converted
            parsed_entities=[entity.model_dump() for entity in nlu_result_action.entities]
    )
    mock_bot_message.channel.send.assert_called_once_with("**Friendly NPC**: NPC says hello back")
    assert mock_player_dialogue_status.collected_actions_json == "[]" # Actions not queued
    mock_session.add.assert_not_called() # Player status not changed by this path directly

@pytest.mark.asyncio
@patch("backend.core.action_processor.player_crud.get_by_discord_id", new_callable=AsyncMock)
@patch("backend.core.nlu_service.parse_player_input", new_callable=AsyncMock) # Patched at source
@patch("backend.core.dialogue_system.handle_dialogue_input", new_callable=AsyncMock) # Patched at source
async def test_process_player_message_for_nlu_player_not_in_dialogue_queues_action(
    mock_handle_dialogue_input: AsyncMock,
    mock_parse_nlu: AsyncMock,
    mock_get_player_by_discord_id: AsyncMock,
    mock_bot_message: MagicMock,
    mock_player_exploring_status: Player,
    mock_session: AsyncMock
):
    mock_get_player_by_discord_id.return_value = mock_player_exploring_status

    nlu_result_action = ParsedAction(
        raw_text=mock_bot_message.content, intent="look_around", guild_id=DEFAULT_GUILD_ID,
        player_id=PLAYER_DISCORD_ID_1, timestamp=datetime.datetime.now(datetime.timezone.utc),
        entities=[]
    )
    mock_parse_nlu.return_value = nlu_result_action

    await process_player_message_for_nlu(MagicMock(spec=commands.Bot), mock_bot_message, session=mock_session)

    mock_parse_nlu.assert_called_once_with(
        raw_text=mock_bot_message.content,
        guild_id=DEFAULT_GUILD_ID,
        player_id=mock_player_exploring_status.id # Use DB id
    )
    mock_handle_dialogue_input.assert_not_called()

    # Check that action was queued
    # The mock_player_exploring_status.collected_actions_json is initially "[]"
    # After adding one action, it should be a list containing one action dict
    expected_queued_actions = [nlu_result_action.model_dump(mode='json')]
    # The actual value in player.collected_actions_json might be a list or a JSON string
    # depending on how SQLAlchemy handles it. The code sets it to a list.
    assert mock_player_exploring_status.collected_actions_json == expected_queued_actions
    mock_session.add.assert_called_once_with(mock_player_exploring_status)

@pytest.mark.asyncio
@patch("backend.core.action_processor.player_crud.get_by_discord_id", new_callable=AsyncMock)
@patch("backend.core.nlu_service.parse_player_input", new_callable=AsyncMock) # Patched at source
@patch("backend.core.dialogue_system.handle_dialogue_input", new_callable=AsyncMock) # Patched at source
async def test_process_player_message_for_nlu_player_in_dialogue_nlu_unknown_intent(
    mock_handle_dialogue_input: AsyncMock,
    mock_parse_nlu: AsyncMock,
    mock_get_player_by_discord_id: AsyncMock,
    mock_bot_message: MagicMock,
    mock_player_dialogue_status: Player,
    mock_session: AsyncMock
):
    mock_get_player_by_discord_id.return_value = mock_player_dialogue_status

    nlu_unknown_action = ParsedAction(
        raw_text=mock_bot_message.content, intent="unknown_intent", guild_id=DEFAULT_GUILD_ID,
        player_id=PLAYER_DISCORD_ID_1, timestamp=datetime.datetime.now(datetime.timezone.utc),
        entities=[]
    )
    mock_parse_nlu.return_value = nlu_unknown_action
    mock_handle_dialogue_input.return_value = (True, "NPC seems confused", {"npc_name": "Confused NPC"})

    await process_player_message_for_nlu(MagicMock(spec=commands.Bot), mock_bot_message, session=mock_session)

    mock_parse_nlu.assert_called_once()
    mock_handle_dialogue_input.assert_called_once_with(
        session=mock_session,
        guild_id=DEFAULT_GUILD_ID,
        player_id=PLAYER_ID_PK_1,
        message_text=mock_bot_message.content,
        parsed_intent="unknown_intent", # Intent is unknown
        parsed_entities=[] # Entities are empty
    )
    mock_bot_message.channel.send.assert_called_once_with("**Confused NPC**: NPC seems confused")
    assert mock_player_dialogue_status.collected_actions_json == "[]"

@pytest.mark.asyncio
@patch("backend.core.action_processor.player_crud.get_by_discord_id", new_callable=AsyncMock)
@patch("backend.core.nlu_service.parse_player_input", new_callable=AsyncMock) # Patched at source
async def test_process_player_message_for_nlu_player_not_in_dialogue_unknown_intent_not_queued(
    mock_parse_nlu: AsyncMock,
    mock_get_player_by_discord_id: AsyncMock,
    mock_bot_message: MagicMock,
    mock_player_exploring_status: Player,
    mock_session: AsyncMock
):
    mock_get_player_by_discord_id.return_value = mock_player_exploring_status

    nlu_unknown_action = ParsedAction(
        raw_text=mock_bot_message.content, intent="unknown_intent", guild_id=DEFAULT_GUILD_ID,
        player_id=PLAYER_DISCORD_ID_1, timestamp=datetime.datetime.now(datetime.timezone.utc),
        entities=[]
    )
    mock_parse_nlu.return_value = nlu_unknown_action

    await process_player_message_for_nlu(MagicMock(spec=commands.Bot), mock_bot_message, session=mock_session)

    mock_parse_nlu.assert_called_once()
    assert mock_player_exploring_status.collected_actions_json == "[]" # Unknown intent not queued
    mock_session.add.assert_not_called() # Player not modified if action not queued


# --- Tests for _handle_talk_to_npc_action_wrapper with name lookup ---
from backend.core.action_processor import _handle_talk_to_npc_action_wrapper
from backend.models import GeneratedNpc # For creating mock NPC

@pytest.mark.asyncio
@patch("backend.core.action_processor.player_crud.get_by_id_and_guild", new_callable=AsyncMock)
@patch("backend.core.action_processor.npc_crud.get_npcs_by_name_in_location", new_callable=AsyncMock)
@patch("backend.core.dialogue_system.start_dialogue", new_callable=AsyncMock)
async def test_handle_talk_to_npc_name_lookup_success(
    mock_start_dialogue: AsyncMock,
    mock_get_npcs_by_name_loc: AsyncMock,
    mock_get_player: AsyncMock,
    mock_session: AsyncMock
):
    player_id_pk = PLAYER_ID_PK_1
    npc_name = "Old Man Willow"
    npc_id_resolved = 55
    player_location_id = 100

    action = ParsedAction(
        raw_text=f"talk to {npc_name}", intent="talk", guild_id=DEFAULT_GUILD_ID, player_id=PLAYER_DISCORD_ID_1,
        timestamp=datetime.datetime.fromisoformat(fixed_dt_str),
        entities=[ActionEntity(type="npc_name", value=npc_name)] # NLU provides name
    )

    mock_player = Player(id=player_id_pk, guild_id=DEFAULT_GUILD_ID, current_location_id=player_location_id)
    mock_get_player.return_value = mock_player

    mock_npc_found = GeneratedNpc(id=npc_id_resolved, guild_id=DEFAULT_GUILD_ID, name_i18n={"en": npc_name}, current_location_id=player_location_id)
    mock_get_npcs_by_name_loc.return_value = [mock_npc_found]

    mock_start_dialogue.return_value = (True, "dialogue_started_key", {"npc_name": npc_name})

    result = await _handle_talk_to_npc_action_wrapper(mock_session, DEFAULT_GUILD_ID, player_id_pk, action)

    mock_get_player.assert_called_once_with(mock_session, id=player_id_pk, guild_id=DEFAULT_GUILD_ID)
    mock_get_npcs_by_name_loc.assert_called_once_with(
        session=mock_session, guild_id=DEFAULT_GUILD_ID, location_id=player_location_id, npc_name=npc_name
    )
    mock_start_dialogue.assert_called_once_with(
        session=mock_session, guild_id=DEFAULT_GUILD_ID, player_id=player_id_pk, target_npc_id=npc_id_resolved
    )
    assert result["status"] == "success"
    assert result["message_key"] == "dialogue_started_key"

@pytest.mark.asyncio
@patch("backend.core.action_processor.player_crud.get_by_id_and_guild", new_callable=AsyncMock)
@patch("backend.core.action_processor.npc_crud.get_npcs_by_name_in_location", new_callable=AsyncMock)
@patch("backend.core.dialogue_system.start_dialogue", new_callable=AsyncMock)
async def test_handle_talk_to_npc_name_lookup_not_found(
    mock_start_dialogue: AsyncMock,
    mock_get_npcs_by_name_loc: AsyncMock,
    mock_get_player: AsyncMock,
    mock_session: AsyncMock
):
    player_id_pk = PLAYER_ID_PK_1
    npc_name = "Ghostly Figure"
    player_location_id = 101

    action = ParsedAction(
        raw_text=f"talk {npc_name}", intent="talk", guild_id=DEFAULT_GUILD_ID, player_id=PLAYER_DISCORD_ID_1,
        timestamp=datetime.datetime.fromisoformat(fixed_dt_str),
        entities=[ActionEntity(type="npc_name", value=npc_name)]
    )
    mock_player = Player(id=player_id_pk, guild_id=DEFAULT_GUILD_ID, current_location_id=player_location_id)
    mock_get_player.return_value = mock_player
    mock_get_npcs_by_name_loc.return_value = [] # NPC not found

    result = await _handle_talk_to_npc_action_wrapper(mock_session, DEFAULT_GUILD_ID, player_id_pk, action)

    mock_get_npcs_by_name_loc.assert_called_once_with(
        session=mock_session, guild_id=DEFAULT_GUILD_ID, location_id=player_location_id, npc_name=npc_name
    )
    mock_start_dialogue.assert_not_called()
    assert result["status"] == "error"
    assert result["message_key"] == "dialogue_error_npc_not_found_by_name"
    assert result["feedback_params"]["npc_name"] == npc_name

@pytest.mark.asyncio
@patch("backend.core.action_processor.player_crud.get_by_id_and_guild", new_callable=AsyncMock)
@patch("backend.core.action_processor.npc_crud.get_npcs_by_name_in_location", new_callable=AsyncMock)
@patch("backend.core.dialogue_system.start_dialogue", new_callable=AsyncMock)
async def test_handle_talk_to_npc_name_lookup_ambiguous(
    mock_start_dialogue: AsyncMock,
    mock_get_npcs_by_name_loc: AsyncMock,
    mock_get_player: AsyncMock,
    mock_session: AsyncMock
):
    player_id_pk = PLAYER_ID_PK_1
    npc_name = "Guard"
    player_location_id = 102
    resolved_npc_id_for_first_guard = 60

    action = ParsedAction(
        raw_text=f"talk Guard", intent="talk", guild_id=DEFAULT_GUILD_ID, player_id=PLAYER_DISCORD_ID_1,
        timestamp=datetime.datetime.fromisoformat(fixed_dt_str),
        entities=[ActionEntity(type="npc", value=npc_name)] # Generic type "npc" with name
    )
    mock_player = Player(id=player_id_pk, guild_id=DEFAULT_GUILD_ID, current_location_id=player_location_id)
    mock_get_player.return_value = mock_player

    # Simulate finding multiple NPCs with the same name
    mock_npc1 = GeneratedNpc(id=resolved_npc_id_for_first_guard, name_i18n={"en": npc_name})
    mock_npc2 = GeneratedNpc(id=61, name_i18n={"en": npc_name})
    mock_get_npcs_by_name_loc.return_value = [mock_npc1, mock_npc2]

    # Current logic picks the first one if ambiguous
    mock_start_dialogue.return_value = (True, "dialogue_with_first_guard", {"npc_name": npc_name})


    result = await _handle_talk_to_npc_action_wrapper(mock_session, DEFAULT_GUILD_ID, player_id_pk, action)

    mock_get_npcs_by_name_loc.assert_called_once_with(
        session=mock_session, guild_id=DEFAULT_GUILD_ID, location_id=player_location_id, npc_name=npc_name
    )
    # Verify it started dialogue with the first NPC found
    mock_start_dialogue.assert_called_once_with(
        session=mock_session, guild_id=DEFAULT_GUILD_ID, player_id=player_id_pk, target_npc_id=resolved_npc_id_for_first_guard
    )
    assert result["status"] == "success"
    # If in future ambiguous names return an error, this test would change:
    # assert result["message_key"] == "dialogue_error_npc_name_ambiguous"
