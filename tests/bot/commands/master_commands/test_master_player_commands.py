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

# Correct the import path based on actual file location
from src.bot.commands.master_commands.player_master_commands import PlayerMasterCommandsCog
from src.models import Player
from src.models.enums import PlayerStatus
from src.core.crud.crud_player import player_crud # Ensure this is the correct way to access player_crud

# --- Pytest Fixtures ---

@pytest.fixture
def mock_bot_fixture():
    """Mocks the discord.ext.commands.Bot."""
    return AsyncMock(spec=commands.Bot)

@pytest.fixture
def guild_id_fixture() -> int:
    """Provides a consistent guild ID for tests."""
    return 777 # Example Guild ID

@pytest.fixture
def master_user_id_fixture() -> int:
    """Provides a consistent Discord user ID for the master user invoking commands."""
    return 999 # Example Master User ID

@pytest.fixture
def command_locale_fixture() -> str:
    """Provides a command locale (e.g., 'en', 'ru')."""
    return "en" # Default to English for tests, can be overridden

@pytest.fixture
def mock_interaction_fixture(guild_id_fixture, master_user_id_fixture, command_locale_fixture):
    """Mocks a discord.Interaction object."""
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.guild_id = guild_id_fixture
    interaction.user = AsyncMock(spec=discord.User)
    interaction.user.id = master_user_id_fixture
    interaction.locale = command_locale_fixture
    interaction.response = AsyncMock(spec=discord.InteractionResponse)
    interaction.followup = AsyncMock(spec=discord.Webhook) # For followup.send
    # interaction.client = AsyncMock(spec=commands.Bot) # If client is accessed, e.g. interaction.client.user
    return interaction

@pytest.fixture
def mock_session_fixture():
    """Mocks an SQLAlchemy AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = AsyncMock()
    return session

@pytest.fixture
def new_player_id_fixture() -> int:
    return 101

@pytest.fixture
def created_player_fixture(guild_id_fixture, new_player_id_fixture) -> Player:
    """A sample Player object that would be 'created'."""
    return Player(
        id=new_player_id_fixture,
        guild_id=guild_id_fixture,
        discord_id=123456789, # Sample discord_id
        name="Newbie",
        level=1,
        xp=0,
        unspent_xp=0,
        gold=10,
        current_hp=100,
        max_hp=100,
        current_status=PlayerStatus.IDLE,
        attributes_json={"strength": 10, "dexterity": 10},
        selected_language="en"
    )

# --- Test Cases ---

@pytest.mark.asyncio
@patch('src.bot.commands.master_commands.player_master_commands.player_crud', autospec=True)
@patch('src.bot.commands.master_commands.player_master_commands.get_localized_message_template', new_callable=AsyncMock)
async def test_master_player_create_success(
    mock_get_localized_template: AsyncMock,
    mock_player_crud_instance: MagicMock, # Renamed from mock_player_crud
    mock_bot_fixture: commands.Bot,
    mock_interaction_fixture: discord.Interaction,
    mock_session_fixture: AsyncSession,
    guild_id_fixture: int,
    new_player_id_fixture: int,
    created_player_fixture: Player,
    command_locale_fixture: str
):
    """Tests successful player creation using /master_player create command."""
    cog = PlayerMasterCommandsCog(mock_bot_fixture)

    discord_id_to_create = 123456789
    name_to_create = "Newbie"
    player_id_to_create = new_player_id_fixture # Master specifies this

    # Mock the CRUD create method
    mock_player_crud_instance.create_with_specific_id.return_value = created_player_fixture

    # Mock localization
    success_template_str = "Player {player_name} (ID: {player_id}, Discord: {discord_id}) created successfully for guild {guild_id}."
    mock_get_localized_template.return_value = success_template_str

    # Call the command
    await cog.player_create.callback(
        cog,
        mock_interaction_fixture,
        player_id=player_id_to_create,
        discord_id=discord_id_to_create,
        name=name_to_create,
        level=1, # Optional params with defaults
        xp=0,
        unspent_xp=0,
        gold=10,
        current_hp=100,
        max_hp=100,
        current_status_str=PlayerStatus.IDLE.value, # Pass as string
        attributes_json_str=None, # Default
        selected_language="en" # Default
    )

    # Assertions
    mock_interaction_fixture.response.defer.assert_called_once_with(ephemeral=True)

    mock_player_crud_instance.create_with_specific_id.assert_called_once()
    call_args = mock_player_crud_instance.create_with_specific_id.call_args[0] # Get positional arguments

    assert call_args[0] == mock_session_fixture # First arg is session
    create_data = call_args[1] # Second arg is obj_in (PlayerCreate schema or dict)

    assert create_data['id'] == player_id_to_create
    assert create_data['guild_id'] == guild_id_fixture
    assert create_data['discord_id'] == discord_id_to_create
    assert create_data['name'] == name_to_create
    assert create_data['level'] == 1
    assert create_data['gold'] == 10
    assert create_data['current_status'] == PlayerStatus.IDLE
    assert create_data['attributes_json'] == {} # Default if None passed for attributes_json_str
    assert create_data['selected_language'] == "en"

    mock_get_localized_template.assert_called_once_with(
        ANY, # session
        guild_id_fixture,
        "player_create:success",
        command_locale_fixture,
        ANY # default message
    )

    expected_message = success_template_str.format(
        player_name=name_to_create,
        player_id=player_id_to_create,
        discord_id=discord_id_to_create,
        guild_id=guild_id_fixture
    )
    mock_interaction_fixture.followup.send.assert_called_once_with(expected_message, ephemeral=True)

@pytest.mark.asyncio
@patch('src.bot.commands.master_commands.player_master_commands.get_db_session')
@patch('src.bot.commands.master_commands.player_master_commands.player_crud', autospec=True)
@patch('src.bot.commands.master_commands.player_master_commands.get_localized_message_template', new_callable=AsyncMock)
async def test_master_player_create_handles_guild_none(
    mock_get_localized_template: AsyncMock,
    mock_player_crud_instance: MagicMock,
    mock_get_db_session: MagicMock, # Patch for get_db_session
    mock_bot_fixture: commands.Bot,
    mock_interaction_fixture: discord.Interaction, # Original interaction
    mock_session_fixture: AsyncSession,
    command_locale_fixture: str
):
    """Tests that player_create handles interaction.guild_id being None."""
    cog = PlayerMasterCommandsCog(mock_bot_fixture)

    # Modify interaction fixture for this test
    mock_interaction_fixture.guild_id = None

    # Mock get_db_session to return our mock_session_fixture
    mock_get_db_session.return_value.__aenter__.return_value = mock_session_fixture

    guild_only_error_template = "This command must be used in a server (guild)."
    mock_get_localized_template.return_value = guild_only_error_template

    await cog.player_create.callback(
        cog,
        mock_interaction_fixture,
        player_id=1, discord_id=123, name="Test" # Dummy values
    )

    mock_interaction_fixture.response.defer.assert_called_once_with(ephemeral=True)

    # Check that get_localized_message_template was called for the guild_only error
    mock_get_localized_template.assert_called_once_with(
        mock_session_fixture, # Session from get_db_session
        None, # guild_id is None
        "common:error_guild_only_command",
        command_locale_fixture,
        ANY # default message
    )

    mock_interaction_fixture.followup.send.assert_called_once_with(guild_only_error_template, ephemeral=True)
    mock_player_crud_instance.create_with_specific_id.assert_not_called()

# To run these tests:
# Ensure pytest and pytest-asyncio are installed
# From the project root: pytest tests/bot/commands/master_commands/test_master_player_commands.py
# (You might need to adjust Python path or conftest.py settings if imports fail)

# Placeholder for setup if this file were to be loaded as a Cog (not typical for test files)
# async def setup(bot: commands.Bot):
#     await bot.add_cog(PlayerMasterCommandsCog(bot))
#     logger.info("PlayerMasterCommandsCog loaded for testing (if applicable).")
#     pass

# Example of how to mock json.loads if attributes_json_str is used
@pytest.mark.asyncio
@patch('src.bot.commands.master_commands.player_master_commands.player_crud', autospec=True)
@patch('src.bot.commands.master_commands.player_master_commands.get_localized_message_template', new_callable=AsyncMock)
@patch('json.loads') # Mock json.loads
async def test_master_player_create_with_attributes_json(
    mock_json_loads: MagicMock,
    mock_get_localized_template: AsyncMock,
    mock_player_crud_instance: MagicMock,
    mock_bot_fixture: commands.Bot,
    mock_interaction_fixture: discord.Interaction,
    mock_session_fixture: AsyncSession,
    guild_id_fixture: int,
    new_player_id_fixture: int,
    created_player_fixture: Player,
    command_locale_fixture: str
):
    cog = PlayerMasterCommandsCog(mock_bot_fixture)
    attributes_str = '{"charisma": 12, "intelligence": 14}'
    parsed_attributes = {"charisma": 12, "intelligence": 14}
    mock_json_loads.return_value = parsed_attributes
    mock_player_crud_instance.create_with_specific_id.return_value = created_player_fixture
    mock_get_localized_template.return_value = "Success" # Simplified for this test

    await cog.player_create.callback(
        cog,
        mock_interaction_fixture,
        player_id=new_player_id_fixture,
        discord_id=12345,
        name="AttrPlayer",
        attributes_json_str=attributes_str
    )

    mock_json_loads.assert_called_once_with(attributes_str)

    call_args = mock_player_crud_instance.create_with_specific_id.call_args[0]
    create_data = call_args[1]
    assert create_data['attributes_json'] == parsed_attributes
    mock_interaction_fixture.followup.send.assert_called_once_with("Success", ephemeral=True)

@pytest.mark.asyncio
@patch('src.bot.commands.master_commands.player_master_commands.player_crud', autospec=True)
@patch('src.bot.commands.master_commands.player_master_commands.get_localized_message_template', new_callable=AsyncMock)
@patch('json.loads') # Mock json.loads
async def test_master_player_create_bad_attributes_json(
    mock_json_loads: MagicMock,
    mock_get_localized_template: AsyncMock,
    mock_player_crud_instance: MagicMock, # Unused here but part of decorator stack
    mock_bot_fixture: commands.Bot,
    mock_interaction_fixture: discord.Interaction,
    mock_session_fixture: AsyncSession, # Unused here
    guild_id_fixture: int, # Unused here
    command_locale_fixture: str
):
    cog = PlayerMasterCommandsCog(mock_bot_fixture)
    attributes_str = '{"charisma": 12, "intelligence": 14 # unterminated'
    mock_json_loads.side_effect = json.JSONDecodeError("Error", "doc", 0)

    error_template = "Invalid JSON provided for {field_name}: {error_details}"
    mock_get_localized_template.return_value = error_template

    await cog.player_create.callback(
        cog,
        mock_interaction_fixture,
        player_id=1,
        discord_id=12345,
        name="BadJsonPlayer",
        attributes_json_str=attributes_str
    )

    mock_json_loads.assert_called_once_with(attributes_str)

    mock_get_localized_template.assert_called_once_with(
        ANY, # session
        guild_id_fixture, # Comes from interaction fixture
        "common:error_invalid_json",
        command_locale_fixture,
        ANY # default message
    )

    expected_error_message = error_template.format(field_name="attributes_json", error_details="Error") # Simplified error
    # Actual error from JSONDecodeError might be more complex, adjust if needed.
    # For this test, we assume the localization utility handles the formatting.
    # The key is that the correct template was requested.

    # Check the followup.send call with the formatted message
    sent_message = mock_interaction_fixture.followup.send.call_args[0][0]
    assert "Invalid JSON provided for attributes_json" in sent_message # Check for key parts
    assert "Error" in sent_message # Check for error detail (simplified)
    assert mock_interaction_fixture.followup.send.call_args[1]['ephemeral'] == True

    mock_player_crud_instance.create_with_specific_id.assert_not_called()
