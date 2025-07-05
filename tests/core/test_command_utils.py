import sys
import os
from typing import Union # Added Union
import pytest
import asyncio # For async tests
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import discord # Moved import discord to the top

# Add the project root to sys.path to allow imports from src
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Imports from src
from src.core.command_utils import (
    _get_localized_string,
    _extract_parameter_details,
    _extract_command_details,
    get_bot_commands
)
from src.models.command_info import CommandInfo, CommandParameterInfo

# Mocking discord.py specific classes that are not easily instantiated
# discord.app_commands.locale_str
class MockLocaleStr:
    def __init__(self, message: str, message_map: dict = None):
        self.message = message
        self.message_map = message_map if message_map else {}

    def __str__(self):
        return self.message

# Tests for _get_localized_string
def test_get_localized_string_with_plain_string():
    assert _get_localized_string("hello", "en") == "hello"
    assert _get_localized_string("hello", None) == "hello"
    assert _get_localized_string("你好", "zh-CN") == "你好"

def test_get_localized_string_with_mock_locale_str():
    ls = MockLocaleStr("hello", {"en": "Hello", "ru": "Привет"})
    assert _get_localized_string(ls, "en") == "Hello" # type: ignore
    assert _get_localized_string(ls, "ru") == "Привет" # type: ignore
    assert _get_localized_string(ls, "fr") == "hello"  # type: ignore # Fallback to default message
    assert _get_localized_string(ls, None) == "hello" # type: ignore # Fallback to default message

def test_get_localized_string_with_none_value():
    assert _get_localized_string(value=None, lang_code="en") is None
    assert _get_localized_string(value=None, lang_code="en", default_str="default") == "default"


# Tests for _extract_parameter_details
@pytest.mark.asyncio # Mark as async if any part uses await, though this one is sync
async def test_extract_parameter_details_simple():
    mock_param = MagicMock(spec=discord.app_commands.Parameter)
    mock_param.name = "amount"
    mock_param.description = "The amount"
    # mock_param.type = Mock(name='integer') # This was the old way
    mock_param.type = Mock() # Create a mock for the type object itself
    mock_param.type.name = 'integer' # Set the name attribute of this mock
    mock_param.required = True
    mock_param.choices = None

    param_info = _extract_parameter_details(mock_param, "en")
    assert param_info.name == "amount"
    assert param_info.description == "The amount"
    assert param_info.type == "integer"
    assert param_info.required is True

@pytest.mark.asyncio
async def test_extract_parameter_details_with_locale_str_description():
    mock_desc = MockLocaleStr("Default desc", {"ru": "Русское описание"})
    mock_param = MagicMock(spec=discord.app_commands.Parameter)
    mock_param.name = "channel"
    mock_param.description = mock_desc
    mock_param.type = Mock()
    mock_param.type.name = 'text_channel'
    mock_param.required = False
    mock_param.choices = None

    param_info_ru = _extract_parameter_details(mock_param, "ru")
    assert param_info_ru.description == "Русское описание"

    param_info_fr = _extract_parameter_details(mock_param, "fr")
    assert param_info_fr.description == "Default desc" # Fallback

# Tests for _extract_command_details (Simplified, focusing on single command)
@pytest.mark.asyncio
async def test_extract_command_details_single_command():
    mock_cmd = MagicMock(spec=discord.app_commands.Command)
    mock_cmd.name = "ping"
    mock_cmd.description = "Checks latency"
    mock_cmd.parameters = []

    cmd_infos = _extract_command_details(mock_cmd, "en")
    assert len(cmd_infos) == 1
    cmd_info = cmd_infos[0]
    assert cmd_info.name == "ping"
    assert cmd_info.description == "Checks latency"
    assert cmd_info.parameters == []

@pytest.mark.asyncio
async def test_extract_command_details_command_with_params_and_locale_desc():
    mock_desc = MockLocaleStr("Default ping desc", {"ru": "Пинг описание"})
    mock_param_desc = MockLocaleStr("User to ping", {"ru": "Пользователь для пинга"})

    mock_param1 = MagicMock(spec=discord.app_commands.Parameter)
    mock_param1.name = "user"
    mock_param1.description = mock_param_desc
    mock_param1.type = Mock()
    mock_param1.type.name = 'user'
    mock_param1.required = True
    mock_param1.choices = None

    mock_cmd = MagicMock(spec=discord.app_commands.Command)
    mock_cmd.name = "greet"
    mock_cmd.description = mock_desc
    mock_cmd.parameters = [mock_param1]

    cmd_infos_ru = _extract_command_details(mock_cmd, "ru")
    assert len(cmd_infos_ru) == 1
    cmd_info_ru = cmd_infos_ru[0]
    assert cmd_info_ru.name == "greet"
    assert cmd_info_ru.description == "Пинг описание"
    assert len(cmd_info_ru.parameters) == 1
    assert cmd_info_ru.parameters[0].name == "user"
    assert cmd_info_ru.parameters[0].description == "Пользователь для пинга"

# Tests for get_bot_commands (More complex, involves mocking bot.tree)
@pytest.mark.asyncio
async def test_get_bot_commands_empty():
    mock_bot = AsyncMock(spec=discord.ext.commands.Bot) # type: ignore
    mock_bot.tree = AsyncMock(spec=discord.app_commands.CommandTree)
    mock_bot.tree.get_commands = MagicMock(return_value=[]) # Ensure it's not awaitable if get_commands is sync

    commands = await get_bot_commands(mock_bot, language="en")
    assert commands == []

@pytest.mark.asyncio
async def test_get_bot_commands_with_simple_command():
    mock_cmd_obj = MagicMock(spec=discord.app_commands.Command)
    mock_cmd_obj.name = "testcmd"
    mock_cmd_obj.description = "A test command"
    mock_cmd_obj.parameters = []

    mock_bot = AsyncMock(spec=discord.ext.commands.Bot) # type: ignore
    mock_bot.tree = AsyncMock(spec=discord.app_commands.CommandTree)
    mock_bot.tree.get_commands = MagicMock(return_value=[mock_cmd_obj])

    commands = await get_bot_commands(mock_bot, language="en")
    assert len(commands) == 1
    assert commands[0].name == "testcmd"
    assert commands[0].description == "A test command"

@pytest.mark.asyncio
async def test_get_bot_commands_with_group():
    # Subcommand
    mock_sub_cmd = MagicMock(spec=discord.app_commands.Command)
    mock_sub_cmd.name = "sub"
    mock_sub_cmd.description = "A subcommand"
    mock_sub_cmd.parameters = []

    # Group
    mock_group = MagicMock(spec=discord.app_commands.Group)
    mock_group.name = "grp"
    mock_group.description = "A group"
    mock_group.commands = [mock_sub_cmd] # commands is a list of Command or Group

    mock_bot = AsyncMock(spec=discord.ext.commands.Bot) # type: ignore
    mock_bot.tree = AsyncMock(spec=discord.app_commands.CommandTree)
    mock_bot.tree.get_commands = MagicMock(return_value=[mock_group])

    # Patch _extract_command_details to simplify the test for get_bot_commands structure
    # We've already tested _extract_command_details separately.
    # Here, we focus on get_bot_commands' ability to iterate and collect.
    # However, the current implementation of get_bot_commands directly calls _extract_command_details
    # which itself handles groups. So, direct test is better.

    commands = await get_bot_commands(mock_bot, language="en")
    assert len(commands) == 1
    assert commands[0].name == "grp sub" # Qualified name
    assert commands[0].description == "A subcommand"

@pytest.mark.asyncio
async def test_get_bot_commands_mixed_commands_and_groups_and_sorting():
    mock_cmd_ping = MagicMock(spec=discord.app_commands.Command)
    mock_cmd_ping.name = "ping"
    mock_cmd_ping.description = "Ping command"
    mock_cmd_ping.parameters = []

    mock_sub_alpha = MagicMock(spec=discord.app_commands.Command)
    mock_sub_alpha.name = "alpha"
    mock_sub_alpha.description = "Alpha sub"
    mock_sub_alpha.parameters = []

    mock_group_config = MagicMock(spec=discord.app_commands.Group)
    mock_group_config.name = "config"
    mock_group_config.description = "Config group"
    mock_group_config.commands = [mock_sub_alpha]

    mock_cmd_zeta = MagicMock(spec=discord.app_commands.Command)
    mock_cmd_zeta.name = "zeta"
    mock_cmd_zeta.description = "Zeta command"
    mock_cmd_zeta.parameters = []

    mock_bot = AsyncMock(spec=discord.ext.commands.Bot) # type: ignore
    mock_bot.tree = AsyncMock(spec=discord.app_commands.CommandTree)
    # Return in unsorted order to test sorting
    mock_bot.tree.get_commands = MagicMock(return_value=[mock_cmd_zeta, mock_group_config, mock_cmd_ping])

    commands = await get_bot_commands(mock_bot, language="en")
    assert len(commands) == 3
    assert commands[0].name == "config alpha" # Sorted first
    assert commands[1].name == "ping"
    assert commands[2].name == "zeta"


# This is to allow running the test file directly for quick checks if needed.
if __name__ == "__main__":
    pytest.main()
