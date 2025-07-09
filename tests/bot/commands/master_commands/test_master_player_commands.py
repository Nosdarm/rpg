import sys
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, ANY
import json

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.commands.master_commands.player_master_commands import MasterPlayerCog as PlayerMasterCommandsCog
from src.models import Player
from src.models.enums import PlayerStatus

# --- Pytest Fixtures ---

@pytest.fixture
def mock_bot_fixture():
    return AsyncMock(spec=commands.Bot)

@pytest.fixture
def guild_id_fixture() -> int:
    return 777

@pytest.fixture
def master_user_id_fixture() -> int:
    return 999

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
    interaction.followup.send = AsyncMock() # Ensure 'send' itself is an AsyncMock with assertion methods
    return interaction

@pytest.fixture
def mock_session_fixture():
    session = AsyncMock(spec=AsyncSession)
    return session

@pytest.fixture
def new_player_id_fixture() -> int:
    return 101

@pytest.fixture
def created_player_fixture(guild_id_fixture, new_player_id_fixture) -> Player:
    return Player(
        id=new_player_id_fixture, guild_id=guild_id_fixture, discord_id=123456789,
        name="Newbie", level=1, xp=0, unspent_xp=0, gold=10,
        current_hp=100, max_hp=100, current_status=PlayerStatus.IDLE,
        attributes_json={"strength": 10, "dexterity": 10}, selected_language="en"
    )

# --- Test Cases ---

@pytest.mark.asyncio
@patch('src.bot.commands.master_commands.player_master_commands.get_db_session')
@patch('src.bot.commands.master_commands.player_master_commands.player_crud', autospec=True)
@patch('src.bot.commands.master_commands.player_master_commands.get_localized_message_template', new_callable=AsyncMock)
@patch('src.core.rules.get_rule', new_callable=AsyncMock)
@patch('src.bot.utils.parse_json_parameter', new_callable=AsyncMock) # Patch for parse_json_parameter
async def test_master_player_create_success(
    mock_parse_json_parameter: AsyncMock,
    mock_core_get_rule: AsyncMock,
    mock_get_localized_template_cmd: AsyncMock,
    mock_player_crud_instance: MagicMock,
    mock_get_db_session: MagicMock,
    mock_bot_fixture: commands.Bot,
    mock_interaction_fixture: discord.Interaction,
    mock_session_fixture: AsyncSession,
    guild_id_fixture: int,
    new_player_id_fixture: int,
    created_player_fixture: Player,
    command_locale_fixture: str
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session_fixture
    mock_core_get_rule.return_value = None
    mock_core_get_rule.side_effect = None
    mock_parse_json_parameter.return_value = {}

    def side_effect_cmd_loc(s, gid, key, loc, default, **kwargs):
        if 'player_name' in kwargs and 'player_id' in kwargs:
             return default.format(player_name=kwargs['player_name'], player_id=kwargs['player_id'])
        return default
    mock_get_localized_template_cmd.side_effect = side_effect_cmd_loc

    cog = PlayerMasterCommandsCog(mock_bot_fixture)
    mock_discord_user_arg = AsyncMock(spec=discord.User, id=123456789, locale=MagicMock(value="en")) # Renamed to avoid clash
    mock_player_crud_instance.get_by_discord_id.return_value = None
    mock_player_crud_instance.create_with_defaults.return_value = created_player_fixture

    async def mock_update_entity_side_effect_success(session, entity, data):
        for key, value in data.items():
            setattr(entity, key, value)
        # Crucially, ensure the name is set correctly if it was part of `data` or on `entity`
        # For this test, player_name "Newbie" is passed to create_with_defaults.
        # The 'entity' passed to update_entity is the result of create_with_defaults.
        # If 'name' is in 'data', it would override. Here, 'name' is not in data for update.
        return entity

    with patch('src.bot.commands.master_commands.player_master_commands.update_entity', new_callable=AsyncMock) as mock_update_entity_func:
        mock_update_entity_func.side_effect = mock_update_entity_side_effect_success
        # Corrected: First arg to Command.callback is the interaction.
        # `self` (the cog instance) is implicitly bound when accessing `cog.player_create.callback`.
        await cog.player_create.callback(
            mock_interaction_fixture, # interaction
            discord_user=mock_discord_user_arg, # discord_user parameter
            player_name="Newbie",
            level=1, xp=0, unspent_xp=0, gold=10, current_hp=100, language="en",
            attributes_json_str=None
        )

    mock_parse_json_parameter.assert_called_once_with(
        interaction=mock_interaction_fixture,
        json_str=None,
        field_name="attributes_json_str",
        session=mock_session_fixture
    )
    mock_interaction_fixture.response.defer.assert_called_once_with(ephemeral=True)
    mock_player_crud_instance.get_by_discord_id.assert_called_once_with(mock_session_fixture, guild_id=guild_id_fixture, discord_id=123456789)
    mock_player_crud_instance.create_with_defaults.assert_called_once()
    mock_interaction_fixture.followup.send.assert_called_once()
    sent_embed = mock_interaction_fixture.followup.send.call_args.kwargs["embed"]

    expected_title_default = "Player Created: {player_name} (ID: {player_id})"
    expected_title = expected_title_default.format(player_name="Newbie", player_id=new_player_id_fixture)
    assert sent_embed.title == expected_title


@pytest.mark.asyncio
@patch('src.bot.commands.master_commands.player_master_commands.get_db_session')
@patch('src.bot.commands.master_commands.player_master_commands.player_crud', autospec=True)
@patch('src.bot.commands.master_commands.player_master_commands.get_localized_message_template', new_callable=AsyncMock)
@patch('src.core.rules.get_rule', new_callable=AsyncMock)
async def test_master_player_create_handles_guild_none(
    mock_core_get_rule: AsyncMock,
    mock_get_localized_template_cmd: AsyncMock,
    mock_player_crud_instance: MagicMock,
    mock_get_db_session: MagicMock,
    mock_bot_fixture: commands.Bot,
    mock_interaction_fixture: discord.Interaction,
    mock_session_fixture: AsyncSession,
    command_locale_fixture: str
):
    cog = PlayerMasterCommandsCog(mock_bot_fixture)
    mock_interaction_fixture.guild_id = None
    mock_get_db_session.return_value.__aenter__.return_value = mock_session_fixture

    mock_core_get_rule.return_value = None
    guild_only_error_default = "This command must be used in a server."
    mock_get_localized_template_cmd.return_value = guild_only_error_default

    mock_dummy_user_arg = AsyncMock(spec=discord.User, id=123) # Renamed
    await cog.player_create.callback( cog, mock_interaction_fixture, discord_user=mock_dummy_user_arg, player_name="Test")

    mock_interaction_fixture.response.defer.assert_called_once_with(ephemeral=True)
    mock_get_localized_template_cmd.assert_called_once_with(
        mock_session_fixture, None, "common:error_guild_only_command", command_locale_fixture, ANY
    )
    mock_interaction_fixture.followup.send.assert_called_once_with(guild_only_error_default, ephemeral=True)
    mock_player_crud_instance.create_with_defaults.assert_not_called()


@pytest.mark.asyncio
@patch('src.bot.commands.master_commands.player_master_commands.get_db_session')
@patch('src.bot.commands.master_commands.player_master_commands.player_crud', autospec=True)
@patch('src.bot.commands.master_commands.player_master_commands.get_localized_message_template', new_callable=AsyncMock)
@patch('src.core.rules.get_rule', new_callable=AsyncMock)
@patch('src.bot.utils.parse_json_parameter', new_callable=AsyncMock)
async def test_master_player_create_with_attributes_json(
    mock_parse_json_parameter: AsyncMock,
    mock_core_get_rule: AsyncMock,
    mock_get_localized_template_cmd: AsyncMock,
    mock_player_crud_instance: MagicMock,
    mock_get_db_session: MagicMock,
    mock_bot_fixture: commands.Bot,
    mock_interaction_fixture: discord.Interaction,
    mock_session_fixture: AsyncSession,
    guild_id_fixture: int,
    new_player_id_fixture: int,
    created_player_fixture: Player, # Original fixture with name "Newbie"
    command_locale_fixture: str
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session_fixture
    mock_core_get_rule.return_value = None
    mock_core_get_rule.side_effect = None

    def side_effect_cmd_loc(s, gid, key, loc, default, **kwargs):
        if 'player_name' in kwargs and 'player_id' in kwargs:
             return default.format(player_name=kwargs['player_name'], player_id=kwargs['player_id'])
        return default.format(**kwargs) if kwargs else default
    mock_get_localized_template_cmd.side_effect = side_effect_cmd_loc

    cog = PlayerMasterCommandsCog(mock_bot_fixture)
    attributes_str = '{"charisma": 12, "intelligence": 14}'
    parsed_attributes = {"charisma": 12, "intelligence": 14}

    mock_parse_json_parameter.return_value = parsed_attributes

    # create_with_defaults is called with "AttrPlayer"
    # So the 'entity' passed to update_entity will have name "AttrPlayer"
    # We need to ensure created_player_fixture for this test has the correct name
    # or that create_with_defaults returns a player with the correct name.
    player_after_create = Player(
        id=new_player_id_fixture, guild_id=guild_id_fixture, discord_id=12345, name="AttrPlayer",
        level=1, selected_language="en" # other fields as per defaults
    )
    mock_player_crud_instance.create_with_defaults.return_value = player_after_create

    mock_discord_user_attr_arg = AsyncMock(spec=discord.User, id=12345, locale=MagicMock(value=command_locale_fixture)) # Renamed
    mock_player_crud_instance.get_by_discord_id.return_value = None

    async def mock_update_entity_side_effect(session, entity, data):
        # 'entity' should be player_after_create (name="AttrPlayer")
        # 'data' will contain attributes_json.
        for key, value in data.items():
            setattr(entity, key, value)
        return entity

    with patch('src.bot.commands.master_commands.player_master_commands.update_entity', new_callable=AsyncMock) as mock_update_entity_func_attr:
        mock_update_entity_func_attr.side_effect = mock_update_entity_side_effect
        await cog.player_create.callback(
            cog, # self
            mock_interaction_fixture, # interaction
            discord_user=mock_discord_user_attr_arg, # discord_user parameter
            player_name="AttrPlayer", attributes_json_str=attributes_str
        )

    mock_parse_json_parameter.assert_called_once_with(
        interaction=mock_interaction_fixture,
        json_str=attributes_str,
        field_name="attributes_json_str",
        session=mock_session_fixture
    )
    mock_update_entity_func_attr.assert_called_once()
    called_with_data = mock_update_entity_func_attr.call_args.kwargs['data']
    assert 'name' not in called_with_data
    assert called_with_data['attributes_json'] == parsed_attributes

    mock_player_crud_instance.create_with_defaults.assert_called_once()
    create_defaults_args = mock_player_crud_instance.create_with_defaults.call_args.kwargs
    assert create_defaults_args['discord_id'] == 12345
    assert create_defaults_args['name'] == "AttrPlayer"

    mock_interaction_fixture.followup.send.assert_called_once()
    sent_embed_attr = mock_interaction_fixture.followup.send.call_args.kwargs["embed"]
    expected_title_default = "Player Created: {player_name} (ID: {player_id})"
    # The player_name in the embed should be "AttrPlayer" because update_entity returns the entity
    # which had its name set by create_with_defaults.
    expected_title = expected_title_default.format(player_name="AttrPlayer", player_id=new_player_id_fixture)
    assert sent_embed_attr.title == expected_title


@pytest.mark.asyncio
@patch('src.bot.commands.master_commands.player_master_commands.get_db_session')
@patch('src.bot.commands.master_commands.player_master_commands.player_crud', autospec=True)
@patch('src.bot.commands.master_commands.player_master_commands.get_localized_message_template', new_callable=AsyncMock)
@patch('src.core.rules.get_rule', new_callable=AsyncMock)
@patch('src.bot.utils.parse_json_parameter', new_callable=AsyncMock)
async def test_master_player_create_bad_attributes_json(
    mock_parse_json_parameter: AsyncMock,
    mock_core_get_rule: AsyncMock,
    mock_get_localized_template_cmd: AsyncMock,
    mock_player_crud_instance: MagicMock,
    mock_get_db_session: MagicMock,
    mock_bot_fixture: commands.Bot,
    mock_interaction_fixture: discord.Interaction,
    mock_session_fixture: AsyncSession,
    guild_id_fixture: int,
    command_locale_fixture: str
):
    mock_get_db_session.return_value.__aenter__.return_value = mock_session_fixture
    mock_core_get_rule.return_value = None
    mock_core_get_rule.side_effect = None

    cog = PlayerMasterCommandsCog(mock_bot_fixture)
    attributes_str = '{"charisma": 12, "intelligence": 14 # unterminated'

    # Simulate parse_json_parameter itself sending the message and returning None
    async def mock_parse_json_side_effect(interaction, json_str, field_name, session):
        actual_decode_error_str = ""
        try:
            json.loads(json_str)
        except json.JSONDecodeError as e:
            actual_decode_error_str = str(e)

        default_error_msg_template = "Invalid JSON provided for field '{field_name}': {error_details}"
        error_msg_content = default_error_msg_template.format(field_name=field_name, error_details=actual_decode_error_str)
        await interaction.followup.send(error_msg_content, ephemeral=True)
        return None

    mock_parse_json_parameter.side_effect = mock_parse_json_side_effect

    mock_discord_user_bad_json_arg = AsyncMock(spec=discord.User, id=12345) # Renamed

    await cog.player_create.callback(
        cog, # self
        mock_interaction_fixture, # interaction
        discord_user=mock_discord_user_bad_json_arg, # discord_user parameter
        player_name="BadJsonPlayer", attributes_json_str=attributes_str
    )

    mock_parse_json_parameter.assert_called_once_with(
        interaction=mock_interaction_fixture,
        json_str=attributes_str,
        field_name="attributes_json_str",
        session=mock_session_fixture
    )

    expected_real_decode_error_str = ""
    try:
        json.loads(attributes_str)
    except json.JSONDecodeError as e:
        expected_real_decode_error_str = str(e)

    expected_final_message = f"Invalid JSON provided for field 'attributes_json_str': {expected_real_decode_error_str}"

    mock_interaction_fixture.followup.send.assert_called_once_with(expected_final_message, ephemeral=True)
    mock_player_crud_instance.create_with_defaults.assert_not_called()
