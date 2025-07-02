import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession # For type hinting and spec
from src.core.database import transactional, get_db_session # The decorator and session getter

# --- Test Functions to be Decorated ---

async def successful_operation(session: AsyncSession, data: str = "test"):
    """Simulates an operation that should succeed."""
    session.add(MagicMock()) # Simulate some DB operation
    return f"Success: {data}"

async def failing_operation(session: AsyncSession, data: str = "fail"):
    """Simulates an operation that raises an exception."""
    session.add(MagicMock()) # Simulate some DB operation before failure
    raise ValueError(f"Operation failed: {data}")

async def operation_expecting_guild_id(session: AsyncSession, guild_id: int, data: str = "guild_test"):
    """Simulates an operation that also takes other args."""
    session.add(MagicMock())
    return f"Success: {data}, Guild: {guild_id}"

# --- Fixtures ---

@pytest.fixture
def mock_async_session_instance() -> AsyncMock:
    """Provides a fresh AsyncMock for an AsyncSession instance."""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock() # Though get_db_session context manager handles close
    session.add = AsyncMock()
    return session

@pytest.fixture
def mock_get_db_session_context_manager(mock_async_session_instance: AsyncMock):
    """
    Mocks the get_db_session async context manager.
    It yields the mock_async_session_instance.
    """
    # Create a mock that can be used with "async with"
    # This mock needs to simulate the commit/rollback behavior of the actual get_db_session
    mock_cm = AsyncMock()

    async def aenter_impl():
        mock_async_session_instance.reset_mock() # Reset for each new context entry
        return mock_async_session_instance

    async def aexit_impl(exc_type, exc_val, exc_tb):
        if exc_type:
            await mock_async_session_instance.rollback()
        else:
            await mock_async_session_instance.commit()
        return None # Propagate exception if not handled, or suppress if handled

    mock_cm.__aenter__ = AsyncMock(side_effect=aenter_impl)
    mock_cm.__aexit__ = AsyncMock(side_effect=aexit_impl)

    return mock_cm


# --- Tests for @transactional ---

@pytest.mark.asyncio
async def test_transactional_success_new_session(
    mock_get_db_session_context_manager: AsyncMock,
    mock_async_session_instance: AsyncMock
):
    """Test successful operation creates and commits a new session."""
    decorated_success = transactional(successful_operation)

    with patch("src.core.database.get_db_session", return_value=mock_get_db_session_context_manager):
        result = await decorated_success(data="commit_test")

    assert result == "Success: commit_test"
    mock_get_db_session_context_manager.__aenter__.assert_called_once()
    mock_async_session_instance.add.assert_called_once()
    # get_db_session's own context manager should handle the commit
    # The commit is on the session yielded by get_db_session's context manager
    assert mock_async_session_instance.commit.call_count >= 1 # Allow for potential commit by get_db_session itself
    mock_async_session_instance.rollback.assert_not_called()
    mock_get_db_session_context_manager.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_transactional_failure_new_session_rollbacks(
    mock_get_db_session_context_manager: AsyncMock,
    mock_async_session_instance: AsyncMock
):
    """Test failing operation creates a new session and rolls back."""
    decorated_failure = transactional(failing_operation)

    with patch("src.core.database.get_db_session", return_value=mock_get_db_session_context_manager):
        with pytest.raises(ValueError, match="Operation failed: rollback_test"):
            await decorated_failure(data="rollback_test")

    mock_get_db_session_context_manager.__aenter__.assert_called_once()
    mock_async_session_instance.add.assert_called_once()
    mock_async_session_instance.commit.assert_not_called() # Should not commit on failure
     # Rollback is handled by get_db_session's context manager
    assert mock_async_session_instance.rollback.call_count >= 1
    mock_get_db_session_context_manager.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_transactional_uses_passed_session_positional(mock_async_session_instance: AsyncMock):
    """Test decorator uses an explicitly passed session (positional)."""
    decorated_success = transactional(successful_operation)

    # We are bypassing get_db_session by passing the session directly
    with patch("src.core.database.get_db_session") as mock_get_db_session_func:
        result = await decorated_success(mock_async_session_instance, data="passed_session_pos")

        assert result == "Success: passed_session_pos"
        mock_get_db_session_func.assert_not_called() # Should not create a new session
        mock_async_session_instance.add.assert_called_once()
        # When session is passed, @transactional does not commit/rollback itself
        mock_async_session_instance.commit.assert_not_called()
        mock_async_session_instance.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_transactional_uses_passed_session_keyword(mock_async_session_instance: AsyncMock):
    """Test decorator uses an explicitly passed session (keyword)."""
    decorated_success = transactional(successful_operation)

    with patch("src.core.database.get_db_session") as mock_get_db_session_func:
        result = await decorated_success(session=mock_async_session_instance, data="passed_session_kw")

        assert result == "Success: passed_session_kw"
        mock_get_db_session_func.assert_not_called()
        mock_async_session_instance.add.assert_called_once()
        mock_async_session_instance.commit.assert_not_called()
        mock_async_session_instance.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_transactional_failure_with_passed_session_no_rollback_by_decorator(
    mock_async_session_instance: AsyncMock
):
    """Test failing operation with passed session; decorator itself doesn't rollback."""
    decorated_failure = transactional(failing_operation)

    with patch("src.core.database.get_db_session") as mock_get_db_session_func:
        with pytest.raises(ValueError, match="Operation failed: passed_fail"):
            await decorated_failure(session=mock_async_session_instance, data="passed_fail")

    mock_get_db_session_func.assert_not_called()
    mock_async_session_instance.add.assert_called_once()
    mock_async_session_instance.commit.assert_not_called()
    mock_async_session_instance.rollback.assert_not_called() # Decorator doesn't rollback a passed session


@pytest.mark.asyncio
async def test_transactional_correctly_passes_args_and_kwargs_new_session(
    mock_get_db_session_context_manager: AsyncMock,
    mock_async_session_instance: AsyncMock
):
    """Test args and kwargs are passed correctly when a new session is created."""
    # Session will be injected by decorator as a keyword argument.
    # guild_id is positional, data_kw is keyword-only.
    async def op_with_args(guild_id: int, *, session: AsyncSession, data_kw: str):
        session.add(MagicMock())
        return f"Args: {guild_id}, Kw: {data_kw}"

    decorated_op = transactional(op_with_args)

    with patch("src.core.database.get_db_session", return_value=mock_get_db_session_context_manager):
        # Call with positional guild_id and keyword data_kw. Session is injected.
        result = await decorated_op(123, data_kw="test_data")

    assert result == "Args: 123, Kw: test_data"
    mock_async_session_instance.add.assert_called_once()
    # get_db_session context manager handles commit
    assert mock_async_session_instance.commit.call_count == 1 # Should be exactly 1 by the new mock_get_db_session


@pytest.mark.asyncio
async def test_transactional_correctly_passes_args_and_kwargs_existing_session(
    mock_async_session_instance: AsyncMock
):
    """Test args and kwargs are passed correctly when session is existing."""
    async def op_with_kwargs(session: AsyncSession, *, guild_id: int, data_kw: str):
        session.add(MagicMock())
        return f"KWArgs: {guild_id}, Data: {data_kw}"

    decorated_op = transactional(op_with_kwargs)

    # Test passing session positionally
    result_pos = await decorated_op(mock_async_session_instance, guild_id=789, data_kw="pos_session_data")
    assert result_pos == "KWArgs: 789, Data: pos_session_data"

    mock_async_session_instance.reset_mock() # Reset calls for next assertion

    # Test passing session as keyword
    result_kw = await decorated_op(session=mock_async_session_instance, guild_id=456, data_kw="kw_session_data")
    assert result_kw == "KWArgs: 456, Data: kw_session_data"

    # Check add was called (once per successful decorated_op call)
    # After reset_mock, the call_count for 'add' on the second call to decorated_op should be 1.
    assert mock_async_session_instance.add.call_count == 1
    mock_async_session_instance.commit.assert_not_called() # Decorator shouldn't commit existing session


@pytest.mark.asyncio
async def test_transactional_handles_session_as_kwarg_in_wrapped_func_sig(
    mock_get_db_session_context_manager: AsyncMock,
    mock_async_session_instance: AsyncMock
):
    """
    Test when the wrapped function expects 'session' as a keyword argument,
    and the decorator creates a new session. This tests the fix for the
    movement_logic.py TypeError.
    """
    async def operation_with_session_kwarg(*, session: AsyncSession, guild_id: int, data: str):
        session.add(MagicMock())
        return f"KW Session: {data}, Guild: {guild_id}"

    decorated_op = transactional(operation_with_session_kwarg)

    with patch("src.core.database.get_db_session", return_value=mock_get_db_session_context_manager):
        result = await decorated_op(guild_id=101, data="kw_session_test")

    assert result == "KW Session: kw_session_test, Guild: 101"
    mock_get_db_session_context_manager.__aenter__.assert_called_once()
    mock_async_session_instance.add.assert_called_once()
    assert mock_async_session_instance.commit.call_count == 1 # Should be exactly 1
    mock_async_session_instance.rollback.assert_not_called()
    mock_get_db_session_context_manager.__aexit__.assert_called_once()
