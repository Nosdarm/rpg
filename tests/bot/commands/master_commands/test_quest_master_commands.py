import asyncio
import datetime
import json
from typing import Any, Dict, Optional, Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord.ext import commands
import pytest
from discord import app_commands # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.commands.master_commands.quest_master_commands import MasterQuestCog
from backend.models.quest import GeneratedQuest, QuestStep, PlayerQuestProgress, Questline
from backend.models.player import Player
from backend.models.party import Party
from backend.models.enums import QuestStatus

# Minimal mock for discord.Interaction
class MockDiscordInteraction:
    def __init__(self, guild_id: Optional[int] = 123, user_id: int = 456, locale_str: str = "en"):
        self.guild_id = guild_id
        self.user = MagicMock(id=user_id)
        self.locale = locale_str
        self.response = AsyncMock(spec=discord.InteractionResponse)
        self.response.defer = AsyncMock()
        self.followup = AsyncMock(spec=discord.Webhook)
        self.client = MagicMock(spec=discord.Client)

    async def followup_send(self, *args, **kwargs):
        return await self.followup.send(*args, **kwargs)

@pytest.fixture
def mock_bot() -> MagicMock:
    return MagicMock(spec=commands.Bot)

@pytest.fixture
def master_quest_cog(mock_bot: MagicMock) -> MasterQuestCog:
    return MasterQuestCog(bot=mock_bot)

@pytest.fixture
def mock_interaction() -> MagicMock: # Changed type hint
    # Use MagicMock with spec for better type compatibility
    mock_interaction_obj = MagicMock(spec=discord.Interaction)
    mock_interaction_obj.guild_id = 123
    mock_interaction_obj.user = MagicMock(id=456)
    mock_interaction_obj.locale = "en"
    mock_interaction_obj.response = AsyncMock(spec=discord.InteractionResponse)
    mock_interaction_obj.response.defer = AsyncMock()
    mock_interaction_obj.followup = AsyncMock(spec=discord.Webhook)
    mock_interaction_obj.client = MagicMock(spec=discord.Client)
    return mock_interaction_obj

@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    async_cm = AsyncMock()
    async_cm.__aenter__.return_value = session
    async_cm.__aexit__ = AsyncMock(return_value=None)
    session.begin = MagicMock(return_value=async_cm)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session

def mock_get_localized_message_template_side_effect_factory(expected_message_for_test: str) -> Callable[..., Awaitable[str]]:
    async def side_effect_impl(session: AsyncSession, guild_id: Optional[int], key: str, lang_code: str, default_text: Optional[str] = None, **format_kwargs: Any) -> str:
        # This mock will now use the fixed_return_message provided during its setup.
        # It will attempt to format this message if format_kwargs are provided.
        # The `default_text` from the SUT call is preferred if provided, otherwise use `expected_message_for_test`.
        message_template_to_use = default_text if default_text is not None else expected_message_for_test

        if format_kwargs and isinstance(message_template_to_use, str) and '{' in message_template_to_use:
            try:
                return message_template_to_use.format(**format_kwargs)
            except KeyError: # If specific keys for formatting are missing
                # Fallback for common placeholders if direct formatting fails
                fallback_format_args = {'id': 'test_id', 'list': 'test_list', 'error': 'test_error',
                                        'f': 'test_field', 'details': 'test_details', 'v': 'test_value',
                                        'title': 'test_title', 'order': '1', 'q_id': 'test_q_id',
                                        'step_id': 'test_step_id', 'quest_id': 'test_quest_id',
                                        'owner': 'test_owner', 'status_val': 'test_status',
                                        'filter': 'test_filter', 'p': '1', 'tp': '1', 'c': '1', 't': '1',
                                        'pq_title': 'test_pq_title', 'err': 'test_err'}
                try:
                    # Try formatting with a mix of provided and fallback values
                    return message_template_to_use.format(**{**fallback_format_args, **format_kwargs})
                except KeyError:
                    return message_template_to_use # Return unformatted if still fails
        return str(message_template_to_use)
    return side_effect_impl

# --- Tests for progress_create ---
@pytest.mark.asyncio
@patch('backend.bot.commands.master_commands.quest_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.quest_master_commands.get_localized_message_template')
@patch('backend.bot.commands.master_commands.quest_master_commands.generated_quest_crud')
@patch('backend.bot.commands.master_commands.quest_master_commands.quest_step_crud')
@patch('backend.bot.commands.master_commands.quest_master_commands.player_quest_progress_crud')
@patch('backend.bot.commands.master_commands.quest_master_commands.parse_json_parameter')
@patch('backend.core.crud.crud_player.player_crud')
@patch('backend.core.crud.crud_party.party_crud')
async def test_progress_create_success_player(
    mock_core_party_crud: MagicMock, mock_core_player_crud: MagicMock,
    mock_parse_json: MagicMock,
    mock_pqp_crud: MagicMock, mock_qs_crud: MagicMock, mock_gq_crud: MagicMock,
    mock_get_loc_msg: MagicMock, mock_get_db_session: MagicMock,
    master_quest_cog: MasterQuestCog, mock_interaction: MagicMock, mock_session: AsyncMock
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session

    created_pqp_instance = PlayerQuestProgress(
        id=100, guild_id=123, player_id=1, quest_id=1, status=QuestStatus.IN_PROGRESS,
        progress_data_json={"notes": "test"},
        accepted_at=datetime.datetime.now(datetime.timezone.utc),
        current_step_id=10
    )
    success_msg_template = "Quest Progress Created (ID: {id})"
    mock_get_loc_msg.side_effect = mock_get_localized_message_template_side_effect_factory(success_msg_template)

    mock_gq_crud.get = AsyncMock(return_value=GeneratedQuest(id=1, guild_id=123, static_id="q1", title_i18n={"en":"Test Quest"}))
    mock_qs_crud.get = AsyncMock(return_value=QuestStep(id=10, quest_id=1, step_order=1, title_i18n={"en":"Step 1"}))
    mock_pqp_crud.get_by_player_and_quest = AsyncMock(return_value=None)
    mock_parse_json.return_value = {"notes": "test"}
    mock_pqp_crud.create = AsyncMock(return_value=created_pqp_instance)
    mock_core_player_crud.get = AsyncMock(return_value=Player(id=1, guild_id=123, discord_id="user1", name="Player1"))
    mock_core_party_crud.get = AsyncMock(return_value=None)

    await master_quest_cog.progress_create.callback(
        master_quest_cog,
        mock_interaction,
        quest_id=1,
        player_id=1,
        party_id=None,
        status="IN_PROGRESS",
        current_step_id=10,
        progress_data_json='{"notes": "test"}',
        accepted_at_iso=datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
    mock_gq_crud.get.assert_called_once_with(mock_session, id=1, guild_id=123)
    mock_core_player_crud.get.assert_called_once_with(mock_session, id=1, guild_id=123)
    mock_qs_crud.get.assert_called_once_with(mock_session, id=10)
    mock_pqp_crud.get_by_player_and_quest.assert_called_once_with(mock_session, player_id=1, quest_id=1, guild_id=123)
    mock_pqp_crud.create.assert_called_once()

    mock_interaction.followup.send.assert_called_once()
    call_args = mock_interaction.followup.send.call_args
    assert 'embed' in call_args.kwargs
    embed_sent = call_args.kwargs['embed']
    assert isinstance(embed_sent, discord.Embed)
    assert embed_sent.title is not None and success_msg_template.format(id=created_pqp_instance.id) in embed_sent.title

@pytest.mark.asyncio
@patch('backend.bot.commands.master_commands.quest_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.quest_master_commands.get_localized_message_template')
async def test_progress_create_error_no_owner(
    mock_get_loc_msg: MagicMock, mock_get_db_session: MagicMock,
    master_quest_cog: MasterQuestCog, mock_interaction: MagicMock, mock_session: AsyncMock
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    expected_error_message = "Either player_id or party_id must be provided."
    mock_get_loc_msg.side_effect = mock_get_localized_message_template_side_effect_factory(expected_error_message)

    await master_quest_cog.progress_create.callback(
        master_quest_cog,
        mock_interaction,
        quest_id=1,
        # Ensuring all required parameters are passed, even if None, if they don't have defaults in the signature
        player_id=None,
        party_id=None,
        status=None, # Assuming status might be optional or handled if None
        current_step_id=None,
        progress_data_json=None,
        accepted_at_iso=None
    )
    mock_interaction.followup.send.assert_called_once_with(expected_error_message, ephemeral=True)

@pytest.mark.asyncio
@patch('backend.bot.commands.master_commands.quest_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.quest_master_commands.get_localized_message_template')
@patch('backend.bot.commands.master_commands.quest_master_commands.generated_quest_crud')
async def test_progress_create_error_quest_not_found(
    mock_gq_crud: MagicMock, mock_get_loc_msg: MagicMock,
    mock_get_db_session: MagicMock, master_quest_cog: MasterQuestCog,
    mock_interaction: MagicMock, mock_session: AsyncMock
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    expected_error_message_template = "GeneratedQuest with ID {id} not found."
    mock_get_loc_msg.side_effect = mock_get_localized_message_template_side_effect_factory(expected_error_message_template)
    mock_gq_crud.get = AsyncMock(return_value=None)

    await master_quest_cog.progress_create.callback(
        master_quest_cog,
        mock_interaction,
        quest_id=999,
        player_id=1,
        party_id=None,
        status=None,
        current_step_id=None,
        progress_data_json=None,
        accepted_at_iso=None
    )
    mock_interaction.followup.send.assert_called_once_with(expected_error_message_template.format(id=999), ephemeral=True)

@pytest.mark.asyncio
@patch('backend.bot.commands.master_commands.quest_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.quest_master_commands.get_localized_message_template')
@patch('backend.bot.commands.master_commands.quest_master_commands.generated_quest_crud')
@patch('backend.bot.commands.master_commands.quest_master_commands.quest_step_crud')
@patch('backend.core.crud.crud_player.player_crud')
async def test_progress_create_error_step_not_found(
    mock_core_player_crud: MagicMock,
    mock_qs_crud: MagicMock, mock_gq_crud: MagicMock,
    mock_get_loc_msg: MagicMock, mock_get_db_session: MagicMock,
    master_quest_cog: MasterQuestCog, mock_interaction: MagicMock, mock_session: AsyncMock
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    expected_error_message_template = "QuestStep ID {step_id} not found or does not belong to Quest ID {quest_id}."
    mock_get_loc_msg.side_effect = mock_get_localized_message_template_side_effect_factory(expected_error_message_template)

    mock_gq_crud.get = AsyncMock(return_value=GeneratedQuest(id=1, guild_id=123, static_id="q1", title_i18n={"en":"Test Quest"}))
    mock_core_player_crud.get = AsyncMock(return_value=Player(id=1, guild_id=123, discord_id="user1", name="Player1"))
    mock_qs_crud.get = AsyncMock(return_value=None)

    await master_quest_cog.progress_create.callback(
        master_quest_cog,
        mock_interaction,
        quest_id=1,
        player_id=1,
        current_step_id=999,
        party_id=None,
        status=None,
        progress_data_json=None,
        accepted_at_iso=None
    )
    mock_interaction.followup.send.assert_called_once_with(expected_error_message_template.format(step_id=999, quest_id=1), ephemeral=True)

@pytest.mark.asyncio
@patch('backend.bot.commands.master_commands.quest_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.quest_master_commands.get_localized_message_template')
@patch('backend.bot.commands.master_commands.quest_master_commands.generated_quest_crud')
@patch('backend.bot.commands.master_commands.quest_master_commands.player_quest_progress_crud')
@patch('backend.core.crud.crud_player.player_crud')
async def test_progress_create_error_already_exists(
    mock_core_player_crud: MagicMock,
    mock_pqp_crud: MagicMock, mock_gq_crud: MagicMock,
    mock_get_loc_msg: MagicMock, mock_get_db_session: MagicMock,
    master_quest_cog: MasterQuestCog, mock_interaction: MockDiscordInteraction, mock_session: AsyncMock
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    expected_error_message = "Quest progress already exists for this owner and quest."
    mock_get_loc_msg.side_effect = mock_get_localized_message_template_side_effect_factory(expected_error_message)

    mock_gq_crud.get = AsyncMock(return_value=GeneratedQuest(id=1, guild_id=123, static_id="q1", title_i18n={"en":"Test Quest"}))
    mock_core_player_crud.get = AsyncMock(return_value=Player(id=1, guild_id=123, discord_id="user1", name="Player1"))
    mock_pqp_crud.get_by_player_and_quest = AsyncMock(return_value=PlayerQuestProgress(id=1))

    await master_quest_cog.progress_create.callback(
        master_quest_cog,
        mock_interaction,
        quest_id=1,
        player_id=1,
        party_id=None,
        status=None,
        current_step_id=None,
        progress_data_json=None,
        accepted_at_iso=None
    )
    mock_interaction.followup.send.assert_called_once_with(expected_error_message, ephemeral=True)

@pytest.mark.asyncio
@patch('backend.bot.commands.master_commands.quest_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.quest_master_commands.get_localized_message_template')
async def test_progress_create_guild_only_command(
    mock_get_loc_msg: MagicMock, mock_get_db_session: MagicMock,
    master_quest_cog: MasterQuestCog, mock_session: AsyncMock
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    expected_error_message = "This command must be used in a server."
    mock_get_loc_msg.side_effect = mock_get_localized_message_template_side_effect_factory(expected_error_message)

    interaction_no_guild = MockDiscordInteraction(guild_id=None)

    await master_quest_cog.progress_create.callback(
        master_quest_cog,
        interaction_no_guild,
        quest_id=1,
        player_id=1,
        party_id=None,
        status=None,
        current_step_id=None,
        progress_data_json=None,
        accepted_at_iso=None
    )
    interaction_no_guild.followup.send.assert_called_once_with(expected_error_message, ephemeral=True)

@pytest.mark.asyncio
@patch('backend.bot.commands.master_commands.quest_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.quest_master_commands.get_localized_message_template')
async def test_progress_create_error_both_player_and_party_ids(
    mock_get_loc_msg: MagicMock, mock_get_db_session: MagicMock,
    master_quest_cog: MasterQuestCog, mock_interaction: MockDiscordInteraction, mock_session: AsyncMock
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    expected_error_message = "Provide either player_id or party_id, not both."
    mock_get_loc_msg.side_effect = mock_get_localized_message_template_side_effect_factory(expected_error_message)

    await master_quest_cog.progress_create.callback(
        master_quest_cog,
        mock_interaction,
        quest_id=1,
        player_id=1,
        party_id=1,
        status=None,
        current_step_id=None,
        progress_data_json=None,
        accepted_at_iso=None
    )
    mock_interaction.followup.send.assert_called_once_with(expected_error_message, ephemeral=True)

@pytest.mark.asyncio
@patch('backend.bot.commands.master_commands.quest_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.quest_master_commands.get_localized_message_template')
async def test_progress_create_invalid_status_string(
    mock_get_loc_msg: MagicMock, mock_get_db_session: MagicMock,
    master_quest_cog: MasterQuestCog, mock_interaction: MockDiscordInteraction, mock_session: AsyncMock
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    expected_error_message_template = "Invalid status. Valid: {list}"
    # This mock will return the template, the SUT will format it
    mock_get_loc_msg.side_effect = mock_get_localized_message_template_side_effect_factory(expected_error_message_template)

    await master_quest_cog.progress_create.callback(
        master_quest_cog,
        mock_interaction,
        quest_id=1,
        player_id=1,
        status="INVALID_STATUS_FOO",
        party_id=None,
        current_step_id=None,
        progress_data_json=None,
        accepted_at_iso=None
    )
    mock_interaction.followup.send.assert_called_once()
    args, kwargs = mock_interaction.followup.send.call_args
    valid_statuses_str = ", ".join([s.name for s in QuestStatus])
    assert expected_error_message_template.format(list=valid_statuses_str) == args[0]
    assert kwargs['ephemeral'] is True

@pytest.mark.asyncio
@patch('backend.bot.commands.master_commands.quest_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.quest_master_commands.parse_json_parameter')
@patch('backend.bot.commands.master_commands.quest_master_commands.generated_quest_crud')
@patch('backend.core.crud.crud_player.player_crud')
async def test_progress_create_invalid_progress_data_json(
    mock_core_player_crud: MagicMock,
    mock_gq_crud: MagicMock, mock_parse_json: MagicMock,
    mock_get_db_session: MagicMock, master_quest_cog: MasterQuestCog,
    mock_interaction: MockDiscordInteraction, mock_session: AsyncMock
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session

    # Simulate parse_json_parameter failing and calling followup.send
    async def mock_parse_json_side_effect_capturing_interaction(interaction_arg_from_sut, json_string_arg, param_name_arg, session_arg):
        # Используем interaction_arg_from_sut, который команда передала в parse_json_parameter
        await interaction_arg_from_sut.followup.send("Invalid JSON from mock_parse_json", ephemeral=True)
        return None
    mock_parse_json.side_effect = mock_parse_json_side_effect_capturing_interaction

    mock_gq_crud.get = AsyncMock(return_value=GeneratedQuest(id=1, guild_id=123, static_id="q1", title_i18n={"en":"Test Quest"}))
    mock_core_player_crud.get = AsyncMock(return_value=Player(id=1, guild_id=123, discord_id="user1", name="Player1"))

    await master_quest_cog.progress_create.callback(
        master_quest_cog,
        mock_interaction,
        quest_id=1,
        player_id=1,
        progress_data_json="invalid json",
        party_id=None,
        status=None,
        current_step_id=None,
        accepted_at_iso=None
    )
    # Теперь проверяем, что mock_interaction.followup.send был вызван с ожидаемыми аргументами
    mock_interaction.followup.send.assert_called_once_with("Invalid JSON from mock_parse_json", ephemeral=True)

@pytest.mark.asyncio
@patch('backend.bot.commands.master_commands.quest_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.quest_master_commands.get_localized_message_template')
async def test_progress_create_invalid_accepted_at_iso_format(
    mock_get_loc_msg: MagicMock, mock_get_db_session: MagicMock,
    master_quest_cog: MasterQuestCog, mock_interaction: MockDiscordInteraction, mock_session: AsyncMock
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    expected_error_message = "Invalid ISO 8601 format for accepted_at_iso."
    mock_get_loc_msg.side_effect = mock_get_localized_message_template_side_effect_factory(expected_error_message)

    await master_quest_cog.progress_create.callback(
        master_quest_cog,
        mock_interaction,
        quest_id=1,
        player_id=1,
        accepted_at_iso="not-a-date",
        party_id=None,
        status=None,
        current_step_id=None,
        progress_data_json=None
    )
    mock_interaction.followup.send.assert_called_once_with(expected_error_message, ephemeral=True)

@pytest.mark.asyncio
@patch('backend.bot.commands.master_commands.quest_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.quest_master_commands.get_localized_message_template')
@patch('backend.bot.commands.master_commands.quest_master_commands.generated_quest_crud')
@patch('backend.bot.commands.master_commands.quest_master_commands.player_quest_progress_crud')
@patch('backend.core.crud.crud_player.player_crud')
async def test_progress_create_db_error_on_create(
    mock_core_player_crud: MagicMock,
    mock_pqp_crud: MagicMock, mock_gq_crud: MagicMock,
    mock_get_loc_msg: MagicMock, mock_get_db_session: MagicMock,
    master_quest_cog: MasterQuestCog, mock_interaction: MockDiscordInteraction, mock_session: AsyncMock
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    expected_error_message_template = "Error creating PlayerQuestProgress: {error}"
    mock_get_loc_msg.side_effect = mock_get_localized_message_template_side_effect_factory(expected_error_message_template)

    mock_gq_crud.get = AsyncMock(return_value=GeneratedQuest(id=1, guild_id=123, static_id="q1", title_i18n={"en":"Test Quest"}))
    mock_core_player_crud.get = AsyncMock(return_value=Player(id=1, guild_id=123, discord_id="user1", name="Player1"))
    mock_pqp_crud.get_by_player_and_quest = AsyncMock(return_value=None)
    mock_pqp_crud.create = AsyncMock(side_effect=Exception("DB error"))

    await master_quest_cog.progress_create.callback(
        master_quest_cog,
        mock_interaction,
        quest_id=1,
        player_id=1,
        party_id=None,
        status=None,
        current_step_id=None,
        progress_data_json=None,
        accepted_at_iso=None
    )
    mock_interaction.followup.send.assert_called_once_with(expected_error_message_template.format(error="DB error"), ephemeral=True)

@pytest.mark.asyncio
@patch('backend.bot.commands.master_commands.quest_master_commands.get_db_session')
@patch('backend.bot.commands.master_commands.quest_master_commands.get_localized_message_template')
@patch('backend.bot.commands.master_commands.quest_master_commands.generated_quest_crud')
@patch('backend.bot.commands.master_commands.quest_master_commands.player_quest_progress_crud')
@patch('backend.bot.commands.master_commands.quest_master_commands.parse_json_parameter')
@patch('backend.core.crud.crud_party.party_crud')
@patch('backend.core.crud.crud_player.player_crud')
async def test_progress_create_success_party(
    mock_core_player_crud: MagicMock, mock_core_party_crud: MagicMock,
    mock_parse_json: MagicMock,
    mock_pqp_crud: MagicMock, mock_gq_crud: MagicMock,
    mock_get_loc_msg: MagicMock, mock_get_db_session: MagicMock,
    master_quest_cog: MasterQuestCog, mock_interaction: MockDiscordInteraction, mock_session: AsyncMock
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session
    created_pqp_instance = PlayerQuestProgress(
            id=101, guild_id=123, party_id=1, quest_id=1, status=QuestStatus.NOT_STARTED,
            progress_data_json={}
    )
    success_message_template = "Quest Progress Created (ID: {id})"
    mock_get_loc_msg.side_effect = mock_get_localized_message_template_side_effect_factory(success_message_template)

    mock_gq_crud.get = AsyncMock(return_value=GeneratedQuest(id=1, guild_id=123, static_id="q1", title_i18n={"en":"Test Quest"}))
    mock_core_party_crud.get = AsyncMock(return_value=Party(id=1, guild_id=123, name="The Boys"))
    mock_pqp_crud.get_by_party_and_quest = AsyncMock(return_value=None)
    mock_pqp_crud.create = AsyncMock(return_value=created_pqp_instance)
    mock_parse_json.return_value = {}
    mock_core_player_crud.get = AsyncMock(return_value=None)

    await master_quest_cog.progress_create.callback(
        master_quest_cog,
        mock_interaction,
        quest_id=1,
        player_id=None,
        party_id=1,
        status=None, # Assuming default status or handled if None
        current_step_id=None,
        progress_data_json=None,
        accepted_at_iso=None
    )

    mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
    mock_gq_crud.get.assert_called_once_with(mock_session, id=1, guild_id=123)
    mock_core_party_crud.get.assert_called_once_with(mock_session, id=1, guild_id=123)
    mock_pqp_crud.get_by_party_and_quest.assert_called_once_with(mock_session, party_id=1, quest_id=1, guild_id=123)
    mock_pqp_crud.create.assert_called_once()

    mock_interaction.followup.send.assert_called_once()
    call_args = mock_interaction.followup.send.call_args
    embed_sent = call_args.kwargs['embed']
    assert isinstance(embed_sent, discord.Embed)
    assert embed_sent.title is not None and success_message_template.format(id=created_pqp_instance.id) in embed_sent.title
