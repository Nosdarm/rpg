import pytest
import json
import discord
import datetime # For PendingGeneration timestamps if needed for asserts
from unittest.mock import AsyncMock, patch, MagicMock, call
from typing import Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession
from discord.ext import commands

from src.core.ai_orchestrator import trigger_ai_generation_flow, save_approved_generation
from src.models import PendingGeneration, Player, GuildConfig, GeneratedNpc, GeneratedQuest, Item
from src.models.enums import ModerationStatus, PlayerStatus
from src.core.ai_response_parser import ParsedAiData, CustomValidationError, ParsedNpcData

DEFAULT_GUILD_ID = 1
DEFAULT_PLAYER_ID_PK = 1
DEFAULT_PLAYER_DISCORD_ID = 101
DEFAULT_LOCATION_ID = 1
PENDING_GEN_ID = 1

@pytest.fixture
def mock_bot() -> AsyncMock:
    bot = AsyncMock(spec=commands.Bot)
    mock_guild = AsyncMock(spec=discord.Guild)
    mock_text_channel = AsyncMock(spec=discord.TextChannel)
    mock_text_channel.send = AsyncMock() # Ensure send is an AsyncMock

    mock_guild.get_channel = MagicMock(return_value=mock_text_channel)
    bot.get_guild = MagicMock(return_value=mock_guild)
    return bot

@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    return session

@pytest.fixture
def mock_player() -> Player:
    return Player(id=DEFAULT_PLAYER_ID_PK, discord_id=DEFAULT_PLAYER_DISCORD_ID, guild_id=DEFAULT_GUILD_ID, current_status=PlayerStatus.EXPLORING, name="TestPlayer")

@pytest.fixture
def mock_guild_config_with_notification_channel() -> GuildConfig:
    return GuildConfig(id=DEFAULT_GUILD_ID, notification_channel_id=123456789, main_language="en")


@pytest.mark.asyncio
@patch("src.core.ai_orchestrator.prepare_ai_prompt", new_callable=AsyncMock)
@patch("src.core.ai_orchestrator._mock_openai_api_call", new_callable=AsyncMock)
@patch("src.core.ai_orchestrator.parse_and_validate_ai_response", new_callable=AsyncMock)
@patch("src.core.ai_orchestrator.create_entity", new_callable=AsyncMock)
@patch("src.core.ai_orchestrator.get_entity_by_id", new_callable=AsyncMock)
@patch("src.core.ai_orchestrator.update_entity", new_callable=AsyncMock)
@patch("src.core.ai_orchestrator.notify_master", new_callable=AsyncMock)
# Patch transactional at the source (database.py) to ensure it's a passthrough for this test
@patch("src.core.database.transactional")
async def test_trigger_ai_generation_flow_success(
    mock_transactional_deco: MagicMock, # For src.core.database.transactional
    mock_notify_master: AsyncMock,
    mock_update_entity: AsyncMock,
    mock_get_entity_by_id: AsyncMock,
    mock_create_entity: AsyncMock,
    mock_parse_validate: AsyncMock,
    mock_openai_call: AsyncMock,
    mock_prepare_prompt: AsyncMock,
    mock_bot: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player,
    mock_guild_config_with_notification_channel: GuildConfig
):
    # Make the @transactional on trigger_ai_generation_flow a passthrough
    def passthrough(func):
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    mock_transactional_deco.side_effect = passthrough

    mock_prepare_prompt.return_value = "Test prompt"
    mock_openai_call.return_value = '{"generated_entities": [{"entity_type": "npc", "name_i18n": {"en": "Test NPC"}, "description_i18n": {"en":"Desc"}}]}' # Added desc

    parsed_npc = ParsedNpcData(name_i18n={"en": "Test NPC"}, description_i18n={"en":"Desc"})
    mock_parsed_ai_data = ParsedAiData(generated_entities=[parsed_npc], raw_ai_output=mock_openai_call.return_value)
    mock_parse_validate.return_value = mock_parsed_ai_data

    # Simulate that create_entity will set an ID on the object passed to it
    async def mock_create_entity_side_effect(session, model_class, obj_in_data):
        # Create a real instance with an ID to simulate DB behavior
        instance = model_class(**obj_in_data)
        instance.id = PENDING_GEN_ID
        return instance
    mock_create_entity.side_effect = mock_create_entity_side_effect

    mock_get_entity_by_id.side_effect = [
        mock_player,
        mock_guild_config_with_notification_channel
    ]

    result = await trigger_ai_generation_flow(
        session=mock_session,
        bot=mock_bot,
        guild_id=DEFAULT_GUILD_ID,
        location_id=DEFAULT_LOCATION_ID,
        player_id=DEFAULT_PLAYER_ID_PK
    )

    assert isinstance(result, PendingGeneration)
    assert result.id == PENDING_GEN_ID
    assert result.status == ModerationStatus.PENDING_MODERATION

    mock_prepare_prompt.assert_called_once_with(mock_session, DEFAULT_GUILD_ID, DEFAULT_LOCATION_ID, DEFAULT_PLAYER_ID_PK)
    mock_openai_call.assert_called_once_with("Test prompt")
    mock_parse_validate.assert_called_once_with(mock_openai_call.return_value, DEFAULT_GUILD_ID)

    create_entity_call_args = mock_create_entity.call_args.args[2]
    assert create_entity_call_args["status"] == ModerationStatus.PENDING_MODERATION
    assert create_entity_call_args["parsed_validated_data_json"] == mock_parsed_ai_data.model_dump()

    mock_get_entity_by_id.assert_any_call(mock_session, Player, DEFAULT_PLAYER_ID_PK, guild_id=DEFAULT_GUILD_ID)
    mock_update_entity.assert_any_call(mock_session, mock_player, {"current_status": PlayerStatus.AWAITING_MODERATION})

    mock_notify_master.assert_called_once()
    assert mock_notify_master.call_args.args[2] == DEFAULT_GUILD_ID


@pytest.mark.asyncio
@patch("src.core.ai_orchestrator.prepare_ai_prompt", new_callable=AsyncMock)
@patch("src.core.ai_orchestrator._mock_openai_api_call", new_callable=AsyncMock)
@patch("src.core.ai_orchestrator.parse_and_validate_ai_response", new_callable=AsyncMock)
@patch("src.core.ai_orchestrator.create_entity", new_callable=AsyncMock)
@patch("src.core.ai_orchestrator.notify_master", new_callable=AsyncMock)
@patch("src.core.database.transactional")
async def test_trigger_ai_generation_validation_failed(
    mock_transactional_deco: MagicMock,
    mock_notify_master: AsyncMock,
    mock_create_entity: AsyncMock,
    mock_parse_validate: AsyncMock,
    mock_openai_call: AsyncMock,
    mock_prepare_prompt: AsyncMock,
    mock_bot: AsyncMock,
    mock_session: AsyncSession,
    mock_guild_config_with_notification_channel: GuildConfig
):
    def passthrough(func):
        async def wrapper(*args, **kwargs): return await func(*args, **kwargs)
        return wrapper
    mock_transactional_deco.side_effect = passthrough

    mock_prepare_prompt.return_value = "Test prompt"
    mock_openai_call.return_value = '{"invalid_json": true}'
    validation_error = CustomValidationError(error_type="TestValidationError", message="It failed.")
    mock_parse_validate.return_value = validation_error

    async def mock_create_entity_side_effect_val_fail(session, model_class, obj_in_data):
        instance = model_class(**obj_in_data)
        instance.id = PENDING_GEN_ID
        return instance
    mock_create_entity.side_effect = mock_create_entity_side_effect_val_fail

    with patch("src.core.ai_orchestrator.get_entity_by_id", new_callable=AsyncMock, return_value=mock_guild_config_with_notification_channel):
        result = await trigger_ai_generation_flow(
            session=mock_session, bot=mock_bot, guild_id=DEFAULT_GUILD_ID
        )

    assert isinstance(result, PendingGeneration)
    assert result.id == PENDING_GEN_ID
    assert result.status == ModerationStatus.VALIDATION_FAILED

    create_entity_call_args = mock_create_entity.call_args.args[2]
    assert create_entity_call_args["status"] == ModerationStatus.VALIDATION_FAILED
    assert create_entity_call_args["validation_issues_json"] == validation_error.model_dump()
    mock_notify_master.assert_called_once()


@pytest.mark.asyncio
@patch("src.core.ai_orchestrator.get_entity_by_id", new_callable=AsyncMock)
@patch("src.core.ai_orchestrator.create_entity", new_callable=AsyncMock)
@patch("src.core.ai_orchestrator.update_entity", new_callable=AsyncMock)
@patch("src.core.database.transactional")
async def test_save_approved_generation_success(
    mock_transactional_deco: MagicMock,
    mock_update_entity: AsyncMock,
    mock_create_entity: AsyncMock,
    mock_get_entity_by_id: AsyncMock,
    mock_session: AsyncSession,
    mock_player: Player
):
    def passthrough(func):
        async def wrapper(*args, **kwargs): return await func(*args, **kwargs)
        return wrapper
    mock_transactional_deco.side_effect = passthrough

    mock_player.current_status = PlayerStatus.AWAITING_MODERATION

    parsed_npc = ParsedNpcData(name_i18n={"en": "Saved NPC"}, description_i18n={"en":"Desc"}, stats={"hp":10})
    parsed_data = ParsedAiData(generated_entities=[parsed_npc], raw_ai_output="raw")

    mock_pending_gen = PendingGeneration(
        id=PENDING_GEN_ID, guild_id=DEFAULT_GUILD_ID,
        status=ModerationStatus.APPROVED,
        parsed_validated_data_json=parsed_data.model_dump(),
        triggered_by_user_id=DEFAULT_PLAYER_ID_PK
    )
    mock_get_entity_by_id.side_effect = [mock_pending_gen, mock_player]

    async def mock_create_entity_save_success(session, model_class, obj_in_data):
        instance = model_class(**obj_in_data)
        instance.id = 101 # Simulate DB assigning an ID
        return instance
    mock_create_entity.side_effect = mock_create_entity_save_success

    success = await save_approved_generation(mock_session, PENDING_GEN_ID, DEFAULT_GUILD_ID)

    assert success is True
    mock_get_entity_by_id.assert_any_call(mock_session, PendingGeneration, PENDING_GEN_ID, guild_id=DEFAULT_GUILD_ID)

    assert mock_create_entity.call_count == 1
    create_npc_call_args = mock_create_entity.call_args.args[2]
    assert isinstance(create_npc_call_args, dict)
    assert create_npc_call_args.get("name_i18n") == parsed_npc.name_i18n
    assert create_npc_call_args.get("description_i18n") == parsed_npc.description_i18n
    assert create_npc_call_args.get("properties_json") == {"stats": parsed_npc.stats}

    update_pending_gen_call = None
    update_player_call = None
    for call_obj in mock_update_entity.call_args_list:
        if call_obj.args[1] == mock_pending_gen:
            update_pending_gen_call = call_obj
        elif call_obj.args[1] == mock_player:
            update_player_call = call_obj

    assert update_pending_gen_call is not None
    assert update_pending_gen_call.args[2]["status"] == ModerationStatus.SAVED

    assert update_player_call is not None
    assert update_player_call.args[2]["current_status"] == PlayerStatus.EXPLORING


@pytest.mark.asyncio
@patch("src.core.ai_orchestrator.get_entity_by_id", new_callable=AsyncMock)
@patch("src.core.database.transactional")
async def test_save_approved_generation_pending_gen_not_found(
    mock_transactional_deco: MagicMock,
    mock_get_entity_by_id: AsyncMock,
    mock_session: AsyncSession,
):
    def passthrough(func):
        async def wrapper(*args, **kwargs): return await func(*args, **kwargs)
        return wrapper
    mock_transactional_deco.side_effect = passthrough
    mock_get_entity_by_id.return_value = None
    success = await save_approved_generation(mock_session, PENDING_GEN_ID, DEFAULT_GUILD_ID)
    assert success is False

@pytest.mark.asyncio
@patch("src.core.ai_orchestrator.get_entity_by_id", new_callable=AsyncMock)
@patch("src.core.ai_orchestrator.update_entity", new_callable=AsyncMock)
@patch("src.core.database.transactional")
async def test_save_approved_generation_not_approved_status(
    mock_transactional_deco: MagicMock,
    mock_update_entity: AsyncMock,
    mock_get_entity_by_id: AsyncMock,
    mock_session: AsyncSession,
):
    def passthrough(func):
        async def wrapper(*args, **kwargs): return await func(*args, **kwargs)
        return wrapper
    mock_transactional_deco.side_effect = passthrough
    mock_pending_gen = PendingGeneration(id=PENDING_GEN_ID, guild_id=DEFAULT_GUILD_ID, status=ModerationStatus.PENDING_MODERATION)
    mock_get_entity_by_id.return_value = mock_pending_gen

    success = await save_approved_generation(mock_session, PENDING_GEN_ID, DEFAULT_GUILD_ID)
    assert success is False
    mock_update_entity.assert_not_called()

@pytest.mark.asyncio
@patch("src.core.ai_orchestrator.get_entity_by_id", new_callable=AsyncMock)
@patch("src.core.ai_orchestrator.update_entity", new_callable=AsyncMock)
@patch("src.core.database.transactional")
async def test_save_approved_generation_no_parsed_data(
    mock_transactional_deco: MagicMock,
    mock_update_entity: AsyncMock,
    mock_get_entity_by_id: AsyncMock,
    mock_session: AsyncSession,
):
    def passthrough(func):
        async def wrapper(*args, **kwargs): return await func(*args, **kwargs)
        return wrapper
    mock_transactional_deco.side_effect = passthrough
    mock_pending_gen = PendingGeneration(
        id=PENDING_GEN_ID, guild_id=DEFAULT_GUILD_ID,
        status=ModerationStatus.APPROVED,
        parsed_validated_data_json=None
    )
    mock_get_entity_by_id.return_value = mock_pending_gen

    success = await save_approved_generation(mock_session, PENDING_GEN_ID, DEFAULT_GUILD_ID)

    assert success is False
    update_call_args = mock_update_entity.call_args.args
    assert update_call_args[1] == mock_pending_gen
    assert update_call_args[2]["status"] == ModerationStatus.ERROR_ON_SAVE
    assert "Missing parsed_validated_data_json" in update_call_args[2]["master_notes"]

@pytest.mark.asyncio
@patch("src.core.ai_orchestrator.get_entity_by_id", new_callable=AsyncMock)
@patch("src.core.ai_orchestrator.create_entity", new_callable=AsyncMock)
@patch("src.core.ai_orchestrator.update_entity", new_callable=AsyncMock)
@patch("src.core.database.transactional")
async def test_save_approved_generation_entity_creation_fails(
    mock_transactional_deco: MagicMock,
    mock_update_entity: AsyncMock,
    mock_create_entity: AsyncMock,
    mock_get_entity_by_id: AsyncMock,
    mock_session: AsyncSession,
):
    def passthrough(func):
        async def wrapper(*args, **kwargs): return await func(*args, **kwargs)
        return wrapper
    mock_transactional_deco.side_effect = passthrough

    parsed_npc = ParsedNpcData(name_i18n={"en": "Buggy NPC"}, description_i18n={"en":"Desc"})
    parsed_data = ParsedAiData(generated_entities=[parsed_npc], raw_ai_output="raw")
    mock_pending_gen = PendingGeneration(
        id=PENDING_GEN_ID, guild_id=DEFAULT_GUILD_ID,
        status=ModerationStatus.APPROVED,
        parsed_validated_data_json=parsed_data.model_dump()
    )
    mock_get_entity_by_id.return_value = mock_pending_gen
    mock_create_entity.side_effect = Exception("DB save error")

    success = await save_approved_generation(mock_session, PENDING_GEN_ID, DEFAULT_GUILD_ID)

    assert success is False
    assert mock_update_entity.call_count > 0
    last_update_call_args = mock_update_entity.call_args_list[-1].args
    assert last_update_call_args[1] == mock_pending_gen
    assert last_update_call_args[2]["status"] == ModerationStatus.ERROR_ON_SAVE
    assert "Saving error: DB save error" in last_update_call_args[2]["master_notes"]
