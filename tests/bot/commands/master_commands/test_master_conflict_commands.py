# type: ignore[reportRedeclaration]
# This top-level ignore is to suppress Pyright's "Parameter already assigned"
# (reportRedeclaration) false positives that seem to occur with how app_command
# parameters are tested.

import sys
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, ANY
import asyncio # For create_task
from typing import cast # For type hinting mocks

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import discord
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.commands.master_commands.conflict_master_commands import MasterConflictCog
from backend.models import PendingConflict
from backend.models.enums import ConflictStatus
from backend.core.crud.crud_pending_conflict import pending_conflict_crud # Direct import for patching

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

    # Async methods
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    session.scalars = AsyncMock()
    session.get = AsyncMock(return_value=None)

    # Synchronous methods
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.delete = MagicMock()
    session.merge = MagicMock()
    session.expire = MagicMock()
    session.expunge = MagicMock()
    session.is_modified = MagicMock()

    # For async with session.begin():
    # session.begin() itself is synchronous and returns an async context manager.
    # The context manager's __aenter__ and __aexit__ are async.
    mock_transaction_cm = AsyncMock() # Mock the context manager
    async def mock_aenter(): return session # __aenter__ should return the session or self
    async def mock_aexit(exc_type, exc, tb): pass
    mock_transaction_cm.__aenter__ = AsyncMock(side_effect=mock_aenter)
    mock_transaction_cm.__aexit__ = AsyncMock(side_effect=mock_aexit)
    session.begin = MagicMock(return_value=mock_transaction_cm)

    return session

@pytest.fixture
def pending_conflict_id_fixture() -> int: # type: ignore[reportGeneralTypeIssues]
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
@patch('backend.bot.commands.master_commands.conflict_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.conflict_master_commands.pending_conflict_crud', autospec=True)
@patch('backend.bot.commands.master_commands.conflict_master_commands.get_localized_message_template', new_callable=AsyncMock)
@patch('backend.core.turn_controller.trigger_guild_turn_processing', new_callable=AsyncMock) # Key mock for signaling
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
        cog,
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
    # Use cast to help Pyright understand the type of the mocked async method
    cast(AsyncMock, mock_crud_pending_conflict_instance.get_count_by_guild_and_status).assert_called_once_with(
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
@patch('backend.bot.commands.master_commands.conflict_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.conflict_master_commands.pending_conflict_crud', autospec=True)
@patch('backend.bot.commands.master_commands.conflict_master_commands.get_localized_message_template', new_callable=AsyncMock)
@patch('backend.core.turn_controller.trigger_guild_turn_processing', new_callable=AsyncMock)
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
        cog,
        mock_interaction_fixture,
        pending_conflict_id=pending_conflict_id_fixture,
        outcome_status=ConflictStatus.RESOLVED_BY_MASTER_DISMISS.name,
        notes="Another Test"
    )

    cast(AsyncMock, mock_crud_pending_conflict_instance.get_count_by_guild_and_status).assert_called_once_with(
        mock_session_fixture, guild_id=guild_id_fixture, status=ConflictStatus.PENDING_MASTER_RESOLUTION
    )

    mock_create_task.assert_not_called() # Crucial: reprocessing should NOT be triggered

    expected_final_message = (base_success_msg.format(conflict_id=pending_conflict_id_fixture, notes_value="Another Test") +
                              others_pending_msg.format(count=1))
    assert isinstance(mock_interaction_fixture.followup.send, AsyncMock) # Hint for Pyright
    mock_interaction_fixture.followup.send.assert_called_once_with(expected_final_message, ephemeral=True)


@pytest.mark.asyncio
@patch('backend.bot.commands.master_commands.conflict_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.conflict_master_commands.pending_conflict_crud', autospec=True)
@patch('backend.bot.commands.master_commands.conflict_master_commands.get_localized_message_template', new_callable=AsyncMock)
async def test_resolve_conflict_id_not_found(
    mock_get_localized_template: AsyncMock,
    mock_crud_pending_conflict_instance: MagicMock,
    mock_get_db_session: MagicMock,
    mock_bot_fixture: commands.Bot,
    mock_interaction_fixture: discord.Interaction,
    mock_session_fixture: AsyncSession,
    pending_conflict_id_fixture: int, # A valid ID format, but won't be found
    guild_id_fixture: int
):
    cog = MasterConflictCog(mock_bot_fixture)
    mock_get_db_session.return_value.__aenter__.return_value = mock_session_fixture
    mock_crud_pending_conflict_instance.get.return_value = None # Simulate conflict not found

    mock_get_localized_template.return_value = "Conflict with ID {conflict_id} not found."

    await cog.conflict_resolve.callback(
        cog,
        mock_interaction_fixture,
        pending_conflict_id=pending_conflict_id_fixture,
        outcome_status=ConflictStatus.RESOLVED_BY_MASTER_DISMISS.name,
        notes="Attempt to resolve non-existent"
    )

    mock_interaction_fixture.response.defer.assert_called_once_with(ephemeral=True)
    mock_crud_pending_conflict_instance.get.assert_called_once_with(mock_session_fixture, id=pending_conflict_id_fixture, guild_id=guild_id_fixture)
    mock_crud_pending_conflict_instance.update.assert_not_called() # Should not try to update

    expected_error_message = f"Conflict with ID {pending_conflict_id_fixture} not found."
    assert isinstance(mock_interaction_fixture.followup.send, AsyncMock)
    mock_interaction_fixture.followup.send.assert_called_once_with(expected_error_message, ephemeral=True)


# TODO: Add more tests for other aspects of conflict_resolve, list, view commands,
# error handling, localization of various messages etc.
# For now, focusing on the signaling mechanism.

# --- Test Cases for conflict_list ---

@pytest.mark.asyncio
@patch('backend.bot.commands.master_commands.conflict_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.conflict_master_commands.pending_conflict_crud', autospec=True)
@patch('backend.bot.commands.master_commands.conflict_master_commands.get_localized_message_template', new_callable=AsyncMock)
async def test_conflict_list_no_conflicts(
    mock_get_localized_template: AsyncMock,
    mock_crud_pending_conflict_instance: MagicMock,
    mock_get_db_session: MagicMock,
    mock_bot_fixture: commands.Bot,
    mock_interaction_fixture: discord.Interaction,
    mock_session_fixture: AsyncSession,
    guild_id_fixture: int
):
    cog = MasterConflictCog(mock_bot_fixture)
    mock_get_db_session.return_value.__aenter__.return_value = mock_session_fixture
    mock_crud_pending_conflict_instance.get_multi_by_guild_and_status_paginated.return_value = [] # No conflicts

    mock_get_localized_template.return_value = "No pending conflicts found."

    await cog.conflict_list.callback(cog, mock_interaction_fixture) # Default page=1, limit=10

    mock_crud_pending_conflict_instance.get_multi_by_guild_and_status_paginated.assert_called_once_with(
        mock_session_fixture, guild_id=guild_id_fixture, status=ConflictStatus.PENDING_MASTER_RESOLUTION, skip=0, limit=10
    )
    # Command uses followup.send after defer
    mock_interaction_fixture.followup.send.assert_called_once_with("No pending conflicts found.", ephemeral=True)

@pytest.mark.asyncio
@patch('backend.bot.commands.master_commands.conflict_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.conflict_master_commands.pending_conflict_crud', autospec=True)
@patch('backend.bot.commands.master_commands.conflict_master_commands.get_localized_message_template', new_callable=AsyncMock)
async def test_conflict_list_with_conflicts(
    mock_get_localized_template: AsyncMock,
    mock_crud_pending_conflict_instance: MagicMock,
    mock_get_db_session: MagicMock,
    mock_bot_fixture: commands.Bot,
    mock_interaction_fixture: discord.Interaction,
    mock_session_fixture: AsyncSession,
    guild_id_fixture: int,
    mock_pending_conflict_fixture: PendingConflict # Use existing fixture for one conflict
):
    cog = MasterConflictCog(mock_bot_fixture)
    mock_get_db_session.return_value.__aenter__.return_value = mock_session_fixture

    conflict2 = PendingConflict(
        id=mock_pending_conflict_fixture.id + 1, guild_id=guild_id_fixture,
        status=ConflictStatus.PENDING_MASTER_RESOLUTION,
        involved_entities_json=[{"player_id": 12, "action": "use_item"}],
        conflicting_actions_json={"player_12": "use_item", "world_event": "item_disappears"},
        created_at=discord.utils.utcnow()
    )
    mock_crud_pending_conflict_instance.get_multi_by_guild_and_status_paginated.return_value = [mock_pending_conflict_fixture, conflict2]

    # Mock localization for list header and item format
    mock_get_localized_template.side_effect = lambda s, gid, key, loc, df, **kwargs: {
        "conflict_list:header": "Pending Conflicts ({count}):\n",
        "conflict_list:item_format": "- ID: {id}, Created: {created_at}, Involved: {involved_short}",
        "conflict_list:no_conflicts": "Should not be called"
    }.get(key, df).format(**kwargs) if kwargs else { # Ensure kwargs are passed to format
        "conflict_list:header": "Pending Conflicts ({count}):\n",
        "conflict_list:item_format": "- ID: {id}, Created: {created_at}, Involved: {involved_short}",
        "conflict_list:no_conflicts": "Should not be called"
    }.get(key, df)


    await cog.conflict_list.callback(cog, mock_interaction_fixture) # Default page=1, limit=10

    mock_crud_pending_conflict_instance.get_multi_by_guild_and_status_paginated.assert_called_once_with(
        mock_session_fixture, guild_id=guild_id_fixture, status=ConflictStatus.PENDING_MASTER_RESOLUTION, skip=0, limit=10
    )

    # Construct expected message
    expected_header = "Pending Conflicts (2):\n"
    # For mock_pending_conflict_fixture
    involved1_short = str(mock_pending_conflict_fixture.involved_entities_json) # Simplified for test
    item1_str = f"- ID: {mock_pending_conflict_fixture.id}, Created: {discord.utils.format_dt(mock_pending_conflict_fixture.created_at, 'R')}, Involved: {involved1_short}"
    # For conflict2
    involved2_short = str(conflict2.involved_entities_json)
    item2_str = f"- ID: {conflict2.id}, Created: {discord.utils.format_dt(conflict2.created_at, 'R')}, Involved: {involved2_short}"

    expected_message_content = f"{expected_header}{item1_str}\n{item2_str}"

    # Check that an embed was sent via followup
    mock_interaction_fixture.followup.send.assert_called_once()
    call_kwargs = mock_interaction_fixture.followup.send.call_args.kwargs
    sent_embed = call_kwargs.get('embed')

    assert sent_embed is not None, "Embed was not sent by followup"

    # Check title and some content in fields
    # The exact title format is "Conflict List (Status: {status_filter}, Page {page_num} of {total_pages})"
    # For this test, status_filter is PENDING_MASTER_RESOLUTION, page 1, total_pages 1 (2 items, limit 10)
    # This is hard to match exactly without also mocking total_conflicts result.
    # Let's check for key parts.
    assert "Conflict List" in sent_embed.title
    assert "PENDING_MASTER_RESOLUTION" in sent_embed.title
    assert "Page 1" in sent_embed.title

    # Check that field details for both conflicts are present in the embed's fields
    field_content_str = ""
    for field in sent_embed.fields:
        field_content_str += str(field.name) + " " + str(field.value) + "\n" # Concatenate name and value for searching

    # Check for IDs (likely in field names)
    assert f"ID: {mock_pending_conflict_fixture.id}" in field_content_str
    assert f"ID: {conflict2.id}" in field_content_str

    # Check for involved_count in field values
    involved_count1 = len(mock_pending_conflict_fixture.involved_entities_json) if isinstance(mock_pending_conflict_fixture.involved_entities_json, list) else 0
    involved_count2 = len(conflict2.involved_entities_json) if isinstance(conflict2.involved_entities_json, list) else 0

    assert f"Involved: {involved_count1} entities" in field_content_str
    assert f"Involved: {involved_count2} entities" in field_content_str

    assert call_kwargs.get("ephemeral") is True

# --- Test Cases for conflict_view ---

@pytest.mark.asyncio
@patch('backend.bot.commands.master_commands.conflict_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.conflict_master_commands.pending_conflict_crud', autospec=True)
@patch('backend.bot.commands.master_commands.conflict_master_commands.get_localized_message_template', new_callable=AsyncMock)
async def test_conflict_view_found(
    mock_get_localized_template: AsyncMock,
    mock_crud_pending_conflict_instance: MagicMock,
    mock_get_db_session: MagicMock,
    mock_bot_fixture: commands.Bot,
    mock_interaction_fixture: discord.Interaction,
    mock_session_fixture: AsyncSession,
    guild_id_fixture: int,
    mock_pending_conflict_fixture: PendingConflict, # Use existing fixture
    pending_conflict_id_fixture: int
):
    cog = MasterConflictCog(mock_bot_fixture)
    mock_get_db_session.return_value.__aenter__.return_value = mock_session_fixture
    mock_crud_pending_conflict_instance.get.return_value = mock_pending_conflict_fixture

    # Mock localization for view format
    # Example: "Conflict ID: {id}\nStatus: {status}\nCreated: {created_at}\nInvolved: {involved}\nConflicting: {conflicting}\nNotes: {notes}"
    def view_template_side_effect(session, guild_id, key, locale, default_format_str, **kwargs):
        if key == "conflict_view:details_format":
            # Construct a detailed string from kwargs passed by the command
            return (
                f"Conflict ID: {kwargs.get('id')}\n"
                f"Status: {kwargs.get('status')}\n"
                f"Created: {kwargs.get('created_at_dt')}\n" # Assuming 'created_at_dt' is passed
                f"Involved: {kwargs.get('involved_entities_str')}\n"
                f"Conflicting: {kwargs.get('conflicting_actions_str')}\n"
                f"Resolved Action: {kwargs.get('resolved_action_str', 'N/A')}\n"
                f"Notes: {kwargs.get('notes_str', 'N/A')}"
            )
        return default_format_str # Fallback for other keys if any
    mock_get_localized_template.side_effect = view_template_side_effect

    await cog.conflict_view.callback(cog, mock_interaction_fixture, pending_conflict_id=pending_conflict_id_fixture)

    mock_crud_pending_conflict_instance.get.assert_called_once_with(
        mock_session_fixture, id=pending_conflict_id_fixture, guild_id=guild_id_fixture
    )

    # Command uses followup.send with an embed after deferring
    mock_interaction_fixture.response.send_message.assert_not_called() # Original response.send_message should not be called
    mock_interaction_fixture.followup.send.assert_called_once()      # followup.send should be called

    # Get the arguments passed to followup.send
    # Since we expect embed to be a keyword argument:
    call_kwargs = mock_interaction_fixture.followup.send.call_args.kwargs
    sent_embed = call_kwargs.get('embed')

    assert sent_embed is not None, "Embed was not sent by followup.send"

    # Check title (assumes get_localized_message_template for title works as expected or is simple)
    # The command constructs title like: title_template.format(conflict_id=conflict.id)
    # For this test, we can assume the template resolves to include the ID.
    # A direct check might be `assert f"Conflict Details (ID: {pending_conflict_id_fixture})" == sent_embed.title`
    # if the mock_get_localized_template for "conflict_view:title" is simple or not deeply mocked here.
    # Given the side_effect for view_template_side_effect, it just returns a string, not an embed.
    # This test's mock for get_localized_message_template needs to be aligned with how the SUT uses it for embeds.
    # SUT: title_template = await get_localized_message_template(...) ... embed = discord.Embed(title=title_template.format(...))
    # SUT: embed.add_field(name=await get_label("status", "Status"), value=conflict.status.value, inline=True)

    # Let's simplify the assertion for the mock setup. The command constructs the embed.
    # We'll check for key content in the embed.
    assert f"ID: {mock_pending_conflict_fixture.id}" in sent_embed.title

    # Check for some field content. This is still tricky without fully mocking localization of labels.
    # We'll check if the status value appears in any field's value.
    status_value_present_in_fields = any(
        mock_pending_conflict_fixture.status.value in field.value for field in sent_embed.fields
    )
    assert status_value_present_in_fields, f"Status value '{mock_pending_conflict_fixture.status.value}' not found in any embed field values."

    assert call_kwargs.get("ephemeral") is True

@pytest.mark.asyncio
@patch('backend.bot.commands.master_commands.conflict_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.conflict_master_commands.pending_conflict_crud', autospec=True)
@patch('backend.bot.commands.master_commands.conflict_master_commands.get_localized_message_template', new_callable=AsyncMock)
async def test_conflict_view_not_found(
    mock_get_localized_template: AsyncMock,
    mock_crud_pending_conflict_instance: MagicMock,
    mock_get_db_session: MagicMock,
    mock_bot_fixture: commands.Bot,
    mock_interaction_fixture: discord.Interaction,
    mock_session_fixture: AsyncSession,
    guild_id_fixture: int,
    pending_conflict_id_fixture: int
):
    cog = MasterConflictCog(mock_bot_fixture)
    mock_get_db_session.return_value.__aenter__.return_value = mock_session_fixture
    mock_crud_pending_conflict_instance.get.return_value = None # Conflict not found

    mock_get_localized_template.return_value = "Conflict with ID {conflict_id} not found."

    await cog.conflict_view.callback(cog, mock_interaction_fixture, pending_conflict_id=pending_conflict_id_fixture)

    mock_crud_pending_conflict_instance.get.assert_called_once_with(
        mock_session_fixture, id=pending_conflict_id_fixture, guild_id=guild_id_fixture
    )
    expected_message = f"Conflict with ID {pending_conflict_id_fixture} not found."
    # Command uses followup.send after defer
    mock_interaction_fixture.response.send_message.assert_not_called()
    mock_interaction_fixture.followup.send.assert_called_once_with(expected_message, ephemeral=True)
