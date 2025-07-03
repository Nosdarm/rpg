# tests/bot/commands/test_map_commands.py
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock, ANY # Добавлен ANY

import discord

from src.bot.commands.map_commands import MapMasterCog
from src.models import Location
from src.core.world_generation import generate_location # Для мокирования
from src.core.map_management import add_location_master, remove_location_master, connect_locations_master, disconnect_locations_master # Для мокирования
from src.config import settings

# pytestmark = pytest.mark.asyncio # Если использовать для всего модуля

# Фикстура для мокирования контекста команды
@pytest.fixture
def mock_interaction() -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = 12345 # Пример ID гильдии
    interaction.user = MagicMock(spec=discord.Member) # Используем Member для guild_permissions
    interaction.user.id = 54321 # Пример ID пользователя
    interaction.user.guild_permissions = discord.Permissions(administrator=True) # Права админа по умолчанию для тестов

    # Мокируем response и followup
    interaction.response = MagicMock(spec=discord.InteractionResponse) # Исправлено
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()

    interaction.followup = MagicMock(spec=discord.Webhook) # followup это Webhook
    interaction.followup.send = AsyncMock()
    return interaction

@pytest.fixture
def map_master_cog(mock_bot_class: MagicMock) -> MapMasterCog: # mock_bot_class из conftest.py
    return MapMasterCog(bot=mock_bot_class)

@pytest.mark.asyncio
async def test_generate_location_command_success(
    map_master_cog: MapMasterCog,
    mock_interaction: MagicMock
):
    generated_loc = Location(id=1, guild_id=mock_interaction.guild_id, name_i18n={"en": "AI Loc"})

    with patch("src.bot.commands.map_commands.generate_location", new_callable=AsyncMock, return_value=(generated_loc, None)) as mock_api_call:
        await map_master_cog.generate_location.callback(map_master_cog, mock_interaction) # type: ignore

        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_api_call.assert_called_once()
        mock_interaction.followup.send.assert_called_once_with(
            f"Successfully generated location: AI Loc (ID: 1)",
            ephemeral=True
        )

@pytest.mark.asyncio
async def test_generate_location_command_api_error(
    map_master_cog: MapMasterCog,
    mock_interaction: MagicMock
):
    with patch("src.bot.commands.map_commands.generate_location", new_callable=AsyncMock, return_value=(None, "AI Error")) as mock_api_call:
        await map_master_cog.generate_location.callback(map_master_cog, mock_interaction) # type: ignore

        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_api_call.assert_called_once()
        mock_interaction.followup.send.assert_called_once_with(
            "Error generating location: AI Error",
            ephemeral=True
        )

@pytest.mark.asyncio
async def test_add_location_command_success(
    map_master_cog: MapMasterCog,
    mock_interaction: MagicMock
):
    loc_data_json = json.dumps({"static_id": "new_loc", "name_i18n": {"en":"New"}, "descriptions_i18n":{}, "type":"PLAINS"})
    added_loc = Location(id=2, guild_id=mock_interaction.guild_id, static_id="new_loc", name_i18n={"en":"New"})

    with patch("src.bot.commands.map_commands.add_location_master", new_callable=AsyncMock, return_value=(added_loc, None)) as mock_api_call:
        await map_master_cog.add_location.callback(map_master_cog, mock_interaction, location_data_json=loc_data_json) # type: ignore

        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_api_call.assert_called_once()
        # Проверяем, что json.loads был вызван с правильным аргументом внутри команды (не напрямую)
        mock_interaction.followup.send.assert_called_once_with(
            f"Successfully added location: New (ID: 2)",
            ephemeral=True
        )

@pytest.mark.asyncio
async def test_add_location_command_invalid_json(
    map_master_cog: MapMasterCog,
    mock_interaction: MagicMock
):
    with patch("src.bot.commands.map_commands.add_location_master", new_callable=AsyncMock) as mock_api_call: # Не должен быть вызван
        await map_master_cog.add_location.callback(map_master_cog, mock_interaction, location_data_json="invalid json") # type: ignore

        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_api_call.assert_not_called()
        mock_interaction.followup.send.assert_called_once_with(
            "Invalid JSON provided for location data.",
            ephemeral=True
        )

@pytest.mark.asyncio
async def test_remove_location_command_success(
    map_master_cog: MapMasterCog,
    mock_interaction: MagicMock
):
    location_id_to_remove = 10
    with patch("src.bot.commands.map_commands.remove_location_master", new_callable=AsyncMock, return_value=(True, None)) as mock_api_call:
        await map_master_cog.remove_location.callback(map_master_cog, mock_interaction, location_id=location_id_to_remove) # type: ignore

        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_api_call.assert_called_once_with(ANY, mock_interaction.guild_id, location_id_to_remove) # Проверяем аргументы
        mock_interaction.followup.send.assert_called_once_with(
            f"Successfully removed location ID: {location_id_to_remove}",
            ephemeral=True
        )

@pytest.mark.asyncio
async def test_connect_locations_command_success(
    map_master_cog: MapMasterCog,
    mock_interaction: MagicMock
):
    loc1_id, loc2_id = 1, 2
    conn_type_json = json.dumps({"en": "a bridge"})

    with patch("src.bot.commands.map_commands.connect_locations_master", new_callable=AsyncMock, return_value=(True, None)) as mock_api_call:
        await map_master_cog.connect_locations.callback(map_master_cog, mock_interaction, location1_id=loc1_id, location2_id=loc2_id, connection_type_json=conn_type_json) # type: ignore

        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_api_call.assert_called_once_with(ANY, mock_interaction.guild_id, loc1_id, loc2_id, {"en": "a bridge"})
        mock_interaction.followup.send.assert_called_once_with(
            f"Successfully connected locations {loc1_id} and {loc2_id}.",
            ephemeral=True
        )

@pytest.mark.asyncio
async def test_disconnect_locations_command_success(
    map_master_cog: MapMasterCog,
    mock_interaction: MagicMock
):
    loc1_id, loc2_id = 1, 2
    with patch("src.bot.commands.map_commands.disconnect_locations_master", new_callable=AsyncMock, return_value=(True, None)) as mock_api_call:
        await map_master_cog.disconnect_locations.callback(map_master_cog, mock_interaction, location1_id=loc1_id, location2_id=loc2_id) # type: ignore

        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_api_call.assert_called_once_with(ANY, mock_interaction.guild_id, loc1_id, loc2_id)
        mock_interaction.followup.send.assert_called_once_with(
            f"Successfully disconnected locations {loc1_id} and {loc2_id}.",
            ephemeral=True
        )

@pytest.mark.asyncio
async def test_map_master_cog_check_no_permission(
    map_master_cog: MapMasterCog,
    mock_interaction: MagicMock,
    mock_bot_class: MagicMock # mock_bot_class из conftest.py
):
    mock_interaction.user.guild_permissions.administrator = False # Убираем права админа
    mock_bot_class.is_owner = AsyncMock(return_value=False) # Не владелец бота

    original_master_ids = settings.MASTER_IDS
    settings.MASTER_IDS = [] # Убираем из списка Мастеров на время теста

    allowed = await map_master_cog.interaction_check(mock_interaction)

    assert allowed is False
    mock_interaction.response.send_message.assert_called_once_with(
        "You do not have permission to use this command.",
        ephemeral=True
    )
    settings.MASTER_IDS = original_master_ids # Восстанавливаем

@pytest.mark.asyncio
async def test_map_master_cog_check_is_master_id(
    map_master_cog: MapMasterCog,
    mock_interaction: MagicMock,
    mock_bot_class: MagicMock
):
    mock_interaction.user.guild_permissions.administrator = False
    mock_bot_class.is_owner = AsyncMock(return_value=False)

    original_master_ids = settings.MASTER_IDS
    settings.MASTER_IDS = [str(mock_interaction.user.id)] # Пользователь в списке Мастеров

    allowed = await map_master_cog.interaction_check(mock_interaction)

    assert allowed is True
    mock_interaction.response.send_message.assert_not_called()
    settings.MASTER_IDS = original_master_ids

# Необходимые фикстуры, если они не в conftest.py
# @pytest.fixture
# def mock_bot_class() -> MagicMock:
#     bot = MagicMock(spec=commands.Bot)
#     bot.is_owner = AsyncMock(return_value=False) # По умолчанию не владелец
#     return bot
