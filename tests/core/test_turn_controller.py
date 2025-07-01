import pytest
import asyncio
import logging # For capturing logs in tests if needed
from unittest.mock import AsyncMock, patch, MagicMock, call

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.engine import Result # For mocking query results

from src.core.turn_controller import (
    process_guild_turn_if_ready,
    trigger_guild_turn_processing,
    _guild_turn_processing_locks, # To inspect/manipulate for tests
)
from src.models import Player, Party # GuildConfig not directly used in tested functions here
from src.models.enums import PlayerStatus, PartyTurnStatus

DEFAULT_GUILD_ID = 1
PLAYER_ID_1 = 10
PLAYER_ID_2 = 11
PARTY_ID_1 = 20


@pytest.fixture(autouse=True)
def clear_locks_after_test():
    """Ensures the global lock dictionary is cleared after each test."""
    yield
    _guild_turn_processing_locks.clear()

@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    mock_result = AsyncMock(spec=Result) # General mock for query results
    session.execute = AsyncMock(return_value=mock_result)
    return session

@pytest.fixture
def mock_player_pending_1() -> Player:
    return Player(
        id=PLAYER_ID_1,
        guild_id=DEFAULT_GUILD_ID,
        discord_id=1001,
        name="PlayerPending1",
        current_status=PlayerStatus.TURN_ENDED_PENDING_RESOLUTION
    )

@pytest.fixture
def mock_player_pending_2() -> Player:
    return Player(
        id=PLAYER_ID_2,
        guild_id=DEFAULT_GUILD_ID,
        discord_id=1002,
        name="PlayerPending2",
        current_status=PlayerStatus.TURN_ENDED_PENDING_RESOLUTION # Default, can be changed in test
    )

@pytest.fixture
def mock_party_pending_1(mock_player_pending_2: Player) -> Party:
    party = Party(
        id=PARTY_ID_1,
        guild_id=DEFAULT_GUILD_ID,
        name="PartyPending1",
        turn_status=PartyTurnStatus.TURN_ENDED_PENDING_RESOLUTION,
        player_ids_json=[mock_player_pending_2.id]
    )
    return party


@pytest.mark.asyncio
@patch("src.core.turn_controller._start_action_processing_worker", new_callable=AsyncMock)
async def test_process_guild_turn_no_pending_entities(
    mock_start_worker: AsyncMock,
    mock_session: AsyncMock
):
    mock_player_result = AsyncMock(spec=Result)
    mock_player_result.scalars.return_value.all.return_value = []
    mock_party_result = AsyncMock(spec=Result)
    mock_party_result.scalars.return_value.all.return_value = []
    mock_session.execute.side_effect = [mock_player_result, mock_party_result]

    await process_guild_turn_if_ready(mock_session, DEFAULT_GUILD_ID)

    assert DEFAULT_GUILD_ID not in _guild_turn_processing_locks
    mock_start_worker.assert_not_called()
    mock_session.add.assert_not_called()

@pytest.mark.asyncio
@patch("src.core.turn_controller.asyncio.create_task")
@patch("src.core.turn_controller._start_action_processing_worker", new_callable=AsyncMock)
async def test_process_guild_turn_one_player_pending(
    mock_start_worker_direct_call: AsyncMock,
    mock_create_task: MagicMock,
    mock_session: AsyncMock,
    mock_player_pending_1: Player
):
    mock_player_result = AsyncMock(spec=Result)
    mock_player_result.scalars.return_value.all.return_value = [mock_player_pending_1]
    mock_party_result = AsyncMock(spec=Result)
    mock_party_result.scalars.return_value.all.return_value = []
    mock_session.execute.side_effect = [mock_player_result, mock_party_result]

    await process_guild_turn_if_ready(mock_session, DEFAULT_GUILD_ID)

    assert mock_player_pending_1.current_status == PlayerStatus.PROCESSING_GUILD_TURN
    mock_session.add.assert_called_with(mock_player_pending_1)

    expected_entities = [{"id": mock_player_pending_1.id, "type": "player", "discord_id": mock_player_pending_1.discord_id}]
    mock_start_worker_direct_call.assert_called_once_with(DEFAULT_GUILD_ID, expected_entities)
    mock_create_task.assert_called_once()
    assert DEFAULT_GUILD_ID not in _guild_turn_processing_locks

@pytest.mark.asyncio
@patch("src.core.turn_controller.asyncio.create_task")
@patch("src.core.turn_controller._start_action_processing_worker", new_callable=AsyncMock)
async def test_process_guild_turn_one_party_pending_with_member(
    mock_start_worker_direct_call: AsyncMock,
    mock_create_task: MagicMock,
    mock_session: AsyncMock,
    mock_player_pending_2: Player,
    mock_party_pending_1: Party
):
    mock_player_pending_2.current_status = PlayerStatus.EXPLORING

    mock_player_result = AsyncMock(spec=Result)
    mock_player_result.scalars.return_value.all.return_value = []
    mock_party_result = AsyncMock(spec=Result)
    mock_party_result.scalars.return_value.all.return_value = [mock_party_pending_1]
    mock_session.execute.side_effect = [mock_player_result, mock_party_result]
    mock_session.get.return_value = mock_player_pending_2

    await process_guild_turn_if_ready(mock_session, DEFAULT_GUILD_ID)

    assert mock_party_pending_1.turn_status == PartyTurnStatus.PROCESSING_GUILD_TURN
    assert mock_player_pending_2.current_status == PlayerStatus.PROCESSING_GUILD_TURN

    mock_session.add.assert_any_call(mock_party_pending_1)
    mock_session.add.assert_any_call(mock_player_pending_2)

    expected_entities = [{"id": mock_party_pending_1.id, "type": "party", "name": mock_party_pending_1.name}]
    mock_start_worker_direct_call.assert_called_once_with(DEFAULT_GUILD_ID, expected_entities)
    mock_create_task.assert_called_once()
    assert DEFAULT_GUILD_ID not in _guild_turn_processing_locks

@pytest.mark.asyncio
@patch("src.core.turn_controller._start_action_processing_worker", new_callable=AsyncMock)
async def test_process_guild_turn_lock_prevents_concurrent(
    mock_start_worker: AsyncMock,
    mock_session: AsyncMock,
    mock_player_pending_1: Player
):
    _guild_turn_processing_locks[DEFAULT_GUILD_ID] = True

    mock_player_result = AsyncMock(spec=Result)
    mock_player_result.scalars.return_value.all.return_value = [mock_player_pending_1]
    mock_session.execute.return_value = mock_player_result

    await process_guild_turn_if_ready(mock_session, DEFAULT_GUILD_ID)

    mock_start_worker.assert_not_called()
    assert _guild_turn_processing_locks[DEFAULT_GUILD_ID] is True

@pytest.mark.asyncio
@patch("src.core.turn_controller.process_guild_turn_if_ready", new_callable=AsyncMock)
async def test_trigger_guild_turn_processing_calls_process_ready(
    mock_process_ready: AsyncMock,
):
    mock_session_instance = AsyncMock(spec=AsyncSession)
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__.return_value = mock_session_instance
    mock_session_maker.return_value.__aexit__.return_value = None

    await trigger_guild_turn_processing(DEFAULT_GUILD_ID, mock_session_maker)

    mock_process_ready.assert_called_once_with(mock_session_instance, DEFAULT_GUILD_ID)

@pytest.mark.asyncio
@patch("src.core.turn_controller.asyncio.create_task")
@patch("src.core.turn_controller._start_action_processing_worker", new_callable=AsyncMock)
async def test_process_guild_turn_releases_lock_on_exception(
    mock_start_worker_direct_call: AsyncMock,
    mock_create_task: MagicMock,
    mock_session: AsyncMock,
    mock_player_pending_1: Player
):
    mock_player_result = AsyncMock(spec=Result)
    mock_player_result.scalars.return_value.all.return_value = [mock_player_pending_1]
    mock_party_result = AsyncMock(spec=Result)
    mock_party_result.scalars.return_value.all.return_value = []
    mock_session.execute.side_effect = [mock_player_result, mock_party_result]

    mock_start_worker_direct_call.side_effect = Exception("Worker failed intentionally")

    async def simulated_create_task(coro):
        # Simulate task execution that might raise an error
        # The error from coro (i.e. from mock_start_worker_direct_call) will be caught
        # by the try-except block in process_guild_turn_if_ready
        try:
            await coro
        except Exception:
            # This simulates the task's exception being handled/logged by an asyncio loop
            # or the task itself if it has internal try/except.
            # process_guild_turn_if_ready doesn't await create_task's result,
            # so it relies on its own try/except around the worker part.
            pass

    mock_create_task.side_effect = simulated_create_task

    # process_guild_turn_if_ready should catch the exception from the worker call
    # (or more accurately, the exception during the worker's execution if it were awaited,
    # but since it's create_task, the exception happens in the task)
    # and log it, then proceed to the finally block to release the lock.
    await process_guild_turn_if_ready(mock_session, DEFAULT_GUILD_ID)

    assert DEFAULT_GUILD_ID not in _guild_turn_processing_locks
    mock_start_worker_direct_call.assert_called_once()


@pytest.mark.asyncio
@patch("src.core.turn_controller.asyncio.create_task")
@patch("src.core.turn_controller._start_action_processing_worker", new_callable=AsyncMock)
async def test_process_guild_turn_multiple_entities(
    mock_start_worker_direct_call: AsyncMock,
    mock_create_task: MagicMock,
    mock_session: AsyncMock,
    mock_player_pending_1: Player,
    mock_party_pending_1: Party,
    mock_player_pending_2: Player
):
    mock_player_pending_2.current_status = PlayerStatus.TURN_ENDED_PENDING_RESOLUTION

    mock_player_result = AsyncMock(spec=Result)
    mock_player_result.scalars.return_value.all.return_value = [mock_player_pending_1]
    mock_party_result = AsyncMock(spec=Result)
    mock_party_result.scalars.return_value.all.return_value = [mock_party_pending_1]
    mock_session.execute.side_effect = [mock_player_result, mock_party_result]
    mock_session.get.return_value = mock_player_pending_2

    await process_guild_turn_if_ready(mock_session, DEFAULT_GUILD_ID)

    assert mock_player_pending_1.current_status == PlayerStatus.PROCESSING_GUILD_TURN
    assert mock_party_pending_1.turn_status == PartyTurnStatus.PROCESSING_GUILD_TURN
    assert mock_player_pending_2.current_status == PlayerStatus.PROCESSING_GUILD_TURN

    mock_session.add.assert_any_call(mock_player_pending_1)
    mock_session.add.assert_any_call(mock_party_pending_1)
    mock_session.add.assert_any_call(mock_player_pending_2)

    expected_entities_arg = [
        {"id": mock_player_pending_1.id, "type": "player", "discord_id": mock_player_pending_1.discord_id},
        {"id": mock_party_pending_1.id, "type": "party", "name": mock_party_pending_1.name}
    ]
    mock_start_worker_direct_call.assert_called_once_with(DEFAULT_GUILD_ID, expected_entities_arg)
    mock_create_task.assert_called_once()
    assert DEFAULT_GUILD_ID not in _guild_turn_processing_locks
