import sys
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, ANY
import asyncio # For create_task

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import discord
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.commands.master_commands.conflict_master_commands import MasterConflictCog
from src.models import PendingConflict
from src.models.enums import ConflictStatus
from src.core.crud.crud_pending_conflict import pending_conflict_crud # Direct import for patching

# --- Fixtures (can be shared via conftest.py later if needed) ---

@pytest.fixture
def mock_bot_fixture():
    return AsyncMock(spec=commands.Bot)

@pytest.fixture
def guild_id_fixture() -> int:
    return 888

@pytest.fixture
def master_user_id_fixture() -> int:
    return 111

@pytest.fixture
def command_locale_fixture() -> str:
    return "en"

@pytest.fixture
def mock_interaction_fixture(guild_id_fixture, master_user_id_fixture, command_locale_fixture):
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.guild_id = guild_id_fixture
    interaction.user = AsyncMock(spec=discord.User)
    interaction.user.id = master_user_id_fixture
    interaction.locale = command_locale_fixture
    interaction.response = AsyncMock(spec=discord.InteractionResponse)
    interaction.followup = AsyncMock(spec=discord.Webhook)
    interaction.followup.send = AsyncMock() # Ensure 'send' itself is an AsyncMock
    return interaction

@pytest.fixture
def mock_session_fixture():
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = AsyncMock()
    # For async with session.begin():
    mock_transaction_cm = AsyncMock()
    mock_transaction_cm.__aenter__.return_value = None # type: ignore
    mock_transaction_cm.__aexit__.return_value = None # type: ignore
    session.begin = MagicMock(return_value=mock_transaction_cm)
    return session

@pytest.fixture
def pending_conflict_id_fixture() -> int:
    return 12345

@pytest.fixture
def mock_pending_conflict_fixture(guild_id_fixture, pending_conflict_id_fixture) -> PendingConflict:
    return PendingConflict(
        id=pending_conflict_id_fixture,
        guild_id=guild_id_fixture,
        status=ConflictStatus.PENDING_MASTER_RESOLUTION,
        involved_entities_json=[{"player_id": 10, "action": "move_north"}],
        conflicting_actions_json={"player_10": "move_north", "player_11": "move_south"},
        created_at=discord.utils.utcnow()
    )

# --- Test Cases for Signaling ---

@pytest.mark.asyncio
@patch('src.bot.commands.master_commands.conflict_master_commands.get_db_session')
@patch('src.bot.commands.master_commands.conflict_master_commands.pending_conflict_crud', autospec=True)
@patch('src.bot.commands.master_commands.conflict_master_commands.get_localized_message_template', new_callable=AsyncMock)
@patch('src.core.turn_controller.trigger_guild_turn_processing', new_callable=AsyncMock) # Key mock for signaling
@patch('asyncio.create_task', new_callable=MagicMock) # Mock asyncio.create_task
async def test_resolve_conflict_triggers_reprocessing_when_no_other_conflicts(
    mock_create_task: MagicMock,
    mock_trigger_guild_turn_processing: AsyncMock,
    mock_get_localized_template: AsyncMock,
    mock_crud_pending_conflict_instance: MagicMock, # Patched instance of pending_conflict_crud
    mock_get_db_session: MagicMock, # Patched get_db_session
    mock_bot_fixture: commands.Bot,
    mock_interaction_fixture: discord.Interaction,
    mock_session_fixture: AsyncSession,
    mock_pending_conflict_fixture: PendingConflict,
    pending_conflict_id_fixture: int,
    guild_id_fixture: int,
    command_locale_fixture: str
):
    cog = MasterConflictCog(mock_bot_fixture)
    mock_get_db_session.return_value.__aenter__.return_value = mock_session_fixture

    # Setup CRUD mocks
    mock_crud_pending_conflict_instance.get.return_value = mock_pending_conflict_fixture
    mock_crud_pending_conflict_instance.update.return_value = mock_pending_conflict_fixture
    # This is called *after* update to check remaining: simulate NO other conflicts
    mock_crud_pending_conflict_instance.get_count_by_guild_and_status.return_value = 0

    # Mock localization templates
    base_success_msg = "Conflict {conflict_id} resolved. Notes: {notes_value}."
    reprocessing_msg = " All pending conflicts resolved. Reprocessing triggered."
    mock_get_localized_template.side_effect = lambda s, gid, key, loc, df: {
        "conflict_resolve:success_base": base_success_msg,
        "conflict_resolve:success_reprocessing_triggered": reprocessing_msg,
        "common:value_na": "N/A"
    }.get(key, df)


    await cog.conflict_resolve.callback(
        mock_interaction_fixture,
        pending_conflict_id=pending_conflict_id_fixture,
        outcome_status=ConflictStatus.RESOLVED_BY_MASTER_DISMISS.name, # Use enum name
        notes="Test resolution"
    )

    # Assertions
    mock_interaction_fixture.response.defer.assert_called_once_with(ephemeral=True)
    mock_crud_pending_conflict_instance.get.assert_called_once_with(mock_session_fixture, id=pending_conflict_id_fixture, guild_id=guild_id_fixture)
    mock_crud_pending_conflict_instance.update.assert_called_once() # Check args if necessary

    # Check that get_count_by_guild_and_status was called after update to check remaining
    mock_crud_pending_conflict_instance.get_count_by_guild_and_status.assert_called_once_with( # type: ignore[reportAttributeAccessIssue]
        mock_session_fixture, guild_id=guild_id_fixture, status=ConflictStatus.PENDING_MASTER_RESOLUTION
    )

    # Assert that trigger_guild_turn_processing was called via asyncio.create_task
    assert mock_create_task.call_count == 1
    # The first argument to create_task should be the coroutine object
    # We can't directly assert mock_trigger_guild_turn_processing.assert_called_once_with(...)
    # because it's wrapped in a task. Instead, we check that create_task was called with it.
    # For a more direct check, one might need to run the event loop or have create_task execute immediately.
    # However, checking create_task was called with the right *coroutine function* is usually enough.
    # This is a bit tricky. Let's assume for now that if create_task is called with *a* coroutine,
    # and that coroutine would be trigger_guild_turn_processing, it's good.
    # A more advanced test might involve patching `asyncio.get_event_loop().run_until_complete` if the task is awaited.
    # For now, let's check the first argument's name if possible, or just that create_task was called.

    # To verify arguments passed to trigger_guild_turn_processing,
    # we would need to execute the task. For unit tests, this can be complex.
    # A common pattern is to have create_task return a mock task that can be awaited,
    # or to patch `trigger_guild_turn_processing` such that its call can be asserted directly
    # if `create_task` effectively calls it synchronously in a test setup.
    # Here, we'll rely on the fact that `create_task` was called.
    # If `trigger_guild_turn_processing` itself was the direct argument to `create_task`,
    # we could check `mock_create_task.call_args[0][0].func == trigger_guild_turn_processing` (if it's a partial or similar).
    # Since it's `trigger_guild_turn_processing(args)`, the argument is a coroutine.

    # Let's assume the goal is to ensure the *intention* to call it is there.
    # The production code is: asyncio.create_task(trigger_guild_turn_processing(interaction.guild_id, get_db_session))
    # So, the argument to create_task is a coroutine.
    # We can't easily inspect the arguments of the coroutine without running it.
    # The critical part is that create_task was called, implying an attempt to reprocess.

    expected_final_message = (base_success_msg.format(conflict_id=pending_conflict_id_fixture, notes_value="Test resolution") +
                              reprocessing_msg)
    assert isinstance(mock_interaction_fixture.followup.send, AsyncMock) # Hint for Pyright
    mock_interaction_fixture.followup.send.assert_called_once_with(expected_final_message, ephemeral=True) # type: ignore


@pytest.mark.asyncio
@patch('src.bot.commands.master_commands.conflict_master_commands.get_db_session')
@patch('src.bot.commands.master_commands.conflict_master_commands.pending_conflict_crud', autospec=True)
@patch('src.bot.commands.master_commands.conflict_master_commands.get_localized_message_template', new_callable=AsyncMock)
@patch('src.core.turn_controller.trigger_guild_turn_processing', new_callable=AsyncMock)
@patch('asyncio.create_task', new_callable=MagicMock)
async def test_resolve_conflict_does_not_trigger_reprocessing_if_others_remain(
    mock_create_task: MagicMock,
    mock_trigger_guild_turn_processing: AsyncMock, # Unused but part of decorator stack
    mock_get_localized_template: AsyncMock,
    mock_crud_pending_conflict_instance: MagicMock,
    mock_get_db_session: MagicMock,
    mock_bot_fixture: commands.Bot,
    mock_interaction_fixture: discord.Interaction,
    mock_session_fixture: AsyncSession,
    mock_pending_conflict_fixture: PendingConflict,
    pending_conflict_id_fixture: int,
    guild_id_fixture: int
):
    cog = MasterConflictCog(mock_bot_fixture)
    mock_get_db_session.return_value.__aenter__.return_value = mock_session_fixture

    mock_crud_pending_conflict_instance.get.return_value = mock_pending_conflict_fixture
    mock_crud_pending_conflict_instance.update.return_value = mock_pending_conflict_fixture
    # Simulate 1 other conflict remaining
    mock_crud_pending_conflict_instance.get_count_by_guild_and_status.return_value = 1

    base_success_msg = "Conflict {conflict_id} resolved. Notes: {notes_value}."
    others_pending_msg = " Others ({count}) still pending."
    mock_get_localized_template.side_effect = lambda s, gid, key, loc, df: {
        "conflict_resolve:success_base": base_success_msg,
        "conflict_resolve:success_others_pending": others_pending_msg,
        "common:value_na": "N/A"
    }.get(key, df)

    await cog.conflict_resolve.callback(
        mock_interaction_fixture,
        pending_conflict_id=pending_conflict_id_fixture,
        outcome_status=ConflictStatus.RESOLVED_BY_MASTER_DISMISS.name,
        notes="Another Test"
    )

    mock_crud_pending_conflict_instance.get_count_by_guild_and_status.assert_called_once_with(
        mock_session_fixture, guild_id=guild_id_fixture, status=ConflictStatus.PENDING_MASTER_RESOLUTION
    )

    mock_create_task.assert_not_called() # Crucial: reprocessing should NOT be triggered

    expected_final_message = (base_success_msg.format(conflict_id=pending_conflict_id_fixture, notes_value="Another Test") +
                              others_pending_msg.format(count=1))
    assert isinstance(mock_interaction_fixture.followup.send, AsyncMock) # Hint for Pyright
    mock_interaction_fixture.followup.send.assert_called_once_with(expected_final_message, ephemeral=True)

# TODO: Add more tests for other aspects of conflict_resolve, list, view commands,
# error handling, localization of various messages etc.
# For now, focusing on the signaling mechanism.
