import sys
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, ANY

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.commands.character_commands import CharacterCog #, logger
from src.models import Player
from src.models.enums import PlayerStatus

@pytest.fixture
def mock_bot_fixture():
    return AsyncMock(spec=commands.Bot)

@pytest.fixture
def mock_interaction_fixture(guild_id_fixture, discord_user_id_fixture, player_locale_fixture):
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.guild_id = guild_id_fixture
    interaction.user = AsyncMock(spec=discord.User)
    interaction.user.id = discord_user_id_fixture
    interaction.locale = player_locale_fixture
    interaction.response = AsyncMock(spec=discord.InteractionResponse)
    return interaction

@pytest.fixture
def guild_id_fixture() -> int:
    return 123

@pytest.fixture
def discord_user_id_fixture() -> int:
    return 456

@pytest.fixture
def player_locale_fixture() -> str:
    return "ru"

@pytest.fixture
def mock_player_fixture(guild_id_fixture, discord_user_id_fixture, player_locale_fixture) -> Player:
    return Player(
        id=1,
        guild_id=guild_id_fixture,
        discord_id=discord_user_id_fixture,
        name="Test Player",
        level=2,
        xp=50,
        unspent_xp=3,
        attributes_json={"strength": 10, "dexterity": 8},
        selected_language=player_locale_fixture,
        current_status=PlayerStatus.IDLE
    )

@pytest.fixture
def mock_session_fixture() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.mark.asyncio
@patch('src.bot.commands.character_commands.player_crud.get_by_discord_id', new_callable=AsyncMock)
@patch('src.bot.commands.character_commands.spend_attribute_points', new_callable=AsyncMock)
@patch('src.bot.commands.character_commands.rules.get_rule', new_callable=AsyncMock)
@patch('src.bot.commands.character_commands.localization_utils.get_localized_text')
async def test_levelup_command_success(
    mock_get_localized_text: MagicMock,
    mock_get_rule: AsyncMock,
    mock_spend_points_api: AsyncMock,
    mock_get_player: AsyncMock,
    mock_bot_fixture: AsyncMock,
    mock_interaction_fixture: AsyncMock,
    mock_player_fixture: Player,
    mock_session_fixture: AsyncSession,
    player_locale_fixture: str
):
    cog = CharacterCog(mock_bot_fixture)
    mock_get_player.return_value = mock_player_fixture

    mock_spend_points_api.return_value = (
        True,
        "levelup_success",
        {"attribute_name": "Сила", "new_value": 11, "remaining_xp": 2, "spent_points": 1}
    )

    i18n_template_for_levelup_success = {"ru": "{attribute_name} улучшен до {new_value}. Осталось очков: {remaining_xp}."}
    mock_get_rule.return_value = i18n_template_for_levelup_success

    expected_ru_template_str = i18n_template_for_levelup_success["ru"]
    mock_get_localized_text.return_value = expected_ru_template_str

    await cog._levelup_internal(mock_interaction_fixture, "strength", 1, session=mock_session_fixture)

    mock_get_player.assert_called_once_with(
        db=mock_session_fixture, guild_id=mock_interaction_fixture.guild_id, discord_id=mock_interaction_fixture.user.id
    )
    mock_spend_points_api.assert_called_once_with(
        session=mock_session_fixture,
        player=mock_player_fixture,
        attribute_name="strength",
        points_to_spend=1,
        guild_id=mock_interaction_fixture.guild_id
    )
    mock_get_rule.assert_called_once_with(mock_session_fixture, mock_interaction_fixture.guild_id, "levelup_success")

    mock_get_localized_text.assert_called_once_with(
        i18n_template_for_levelup_success,
        player_locale_fixture,
        "en"
    )

    final_formatted_message = "Сила улучшен до 11. Осталось очков: 2."
    mock_interaction_fixture.response.send_message.assert_called_once_with(
        final_formatted_message, ephemeral=True
    )

@pytest.mark.asyncio
@patch('src.bot.commands.character_commands.player_crud.get_by_discord_id', new_callable=AsyncMock)
@patch('src.bot.commands.character_commands.localization_utils.get_localized_text')
async def test_levelup_command_no_unspent_xp(
    mock_get_localized_text: MagicMock,
    mock_get_player: AsyncMock,
    mock_bot_fixture: AsyncMock,
    mock_interaction_fixture: AsyncMock,
    mock_player_fixture: Player,
    mock_session_fixture: AsyncSession,
    player_locale_fixture: str
):
    cog = CharacterCog(mock_bot_fixture)
    mock_player_fixture.unspent_xp = 0
    mock_get_player.return_value = mock_player_fixture

    expected_message = "У вас нет нераспределенных очков атрибутов."
    if player_locale_fixture == "en":
        expected_message = "You have no unspent attribute points to spend."

    mock_get_localized_text.return_value = expected_message

    await cog._levelup_internal(mock_interaction_fixture, "strength", 1, session=mock_session_fixture)

    mock_get_localized_text.assert_called_once_with(
        {"en": "You have no unspent attribute points to spend.", "ru": "У вас нет нераспределенных очков атрибутов."},
        player_locale_fixture
    )
    mock_interaction_fixture.response.send_message.assert_called_once_with(
        expected_message, ephemeral=True
    )

@pytest.mark.asyncio
@patch('src.bot.commands.character_commands.player_crud.get_by_discord_id', new_callable=AsyncMock)
@patch('src.bot.commands.character_commands.spend_attribute_points', new_callable=AsyncMock)
@patch('src.bot.commands.character_commands.rules.get_rule', new_callable=AsyncMock)
@patch('src.bot.commands.character_commands.localization_utils.get_localized_text')
async def test_levelup_command_api_error_not_enough_points(
    mock_get_localized_text: MagicMock,
    mock_get_rule: AsyncMock,
    mock_spend_points_api: AsyncMock,
    mock_get_player: AsyncMock,
    mock_bot_fixture: AsyncMock,
    mock_interaction_fixture: AsyncMock,
    mock_player_fixture: Player,
    mock_session_fixture: AsyncSession,
    player_locale_fixture: str
):
    cog = CharacterCog(mock_bot_fixture)
    mock_get_player.return_value = mock_player_fixture

    spend_api_details = {"unspent_xp": 3, "requested": 5}
    mock_spend_points_api.return_value = (
        False,
        "levelup_error_not_enough_xp",
        spend_api_details
    )

    i18n_template_error = {"ru": "Недостаточно очков ({unspent_xp}) для траты {requested} очков."}
    i18n_template_error["en"] = "Not enough points ({unspent_xp}) to spend {requested} points."

    mock_get_rule.return_value = i18n_template_error

    expected_template_str = i18n_template_error[player_locale_fixture]
    mock_get_localized_text.return_value = expected_template_str

    await cog._levelup_internal(mock_interaction_fixture, "strength", 5, session=mock_session_fixture)

    mock_spend_points_api.assert_called_once_with(
        session=mock_session_fixture,
        player=mock_player_fixture,
        attribute_name="strength",
        points_to_spend=5,
        guild_id=mock_interaction_fixture.guild_id
    )
    mock_get_rule.assert_called_once_with(mock_session_fixture, mock_interaction_fixture.guild_id, "levelup_error_not_enough_xp")
    mock_get_localized_text.assert_called_once_with(i18n_template_error, player_locale_fixture, "en")

    full_details_for_format = {
        "attribute_name": "strength", "new_value": "N/A",
        "remaining_xp": mock_player_fixture.unspent_xp,
        "spent_points": 5, "points": 5, "requested_stats": 5, "total_cost": 5,
        **spend_api_details
    }

    expected_final_message = expected_template_str.format(**full_details_for_format)

    mock_interaction_fixture.response.send_message.assert_called_once_with(
        expected_final_message, ephemeral=True
    )

@pytest.mark.asyncio
@patch('src.bot.commands.character_commands.player_crud.get_by_discord_id', new_callable=AsyncMock)
@patch('src.bot.commands.character_commands.localization_utils.get_localized_text')
async def test_levelup_command_player_not_found(
    mock_get_localized_text: MagicMock,
    mock_get_player: AsyncMock,
    mock_bot_fixture: AsyncMock,
    mock_interaction_fixture: AsyncMock,
    mock_session_fixture: AsyncSession
):
    cog = CharacterCog(mock_bot_fixture)
    mock_get_player.return_value = None

    await cog._levelup_internal(mock_interaction_fixture, "strength", 1, session=mock_session_fixture)

    mock_interaction_fixture.response.send_message.assert_called_once_with(
        "Сначала вам нужно начать игру с помощью команды `/start`.", ephemeral=True
    )

@pytest.mark.asyncio
@patch('src.bot.commands.character_commands.player_crud.get_by_discord_id', new_callable=AsyncMock)
@patch('src.bot.commands.character_commands.spend_attribute_points', new_callable=AsyncMock)
@patch('src.bot.commands.character_commands.rules.get_rule', new_callable=AsyncMock)
@patch('src.bot.commands.character_commands.localization_utils.get_localized_text')
async def test_levelup_command_message_formatting_fallback(
    mock_get_localized_text: MagicMock,
    mock_get_rule: AsyncMock,
    mock_spend_points_api: AsyncMock,
    mock_get_player: AsyncMock,
    mock_bot_fixture: AsyncMock,
    mock_interaction_fixture: AsyncMock,
    mock_player_fixture: Player,
    mock_session_fixture: AsyncSession
):
    cog = CharacterCog(mock_bot_fixture)
    mock_get_player.return_value = mock_player_fixture

    mock_spend_points_api.return_value = (
        False,
        "levelup_error_invalid_attribute",
        {"attribute_name": "wisdom"}
    )

    mock_get_rule.return_value = None

    await cog._levelup_internal(mock_interaction_fixture, "wisdom", 1, session=mock_session_fixture)

    mock_get_localized_text.assert_not_called()

    expected_default_message = "Атрибут '{attribute_name}' не найден или недоступен для улучшения."
    formatted_expected_message = expected_default_message.format(attribute_name="wisdom")

    mock_interaction_fixture.response.send_message.assert_called_once_with(
        formatted_expected_message, ephemeral=True
    )

@pytest.mark.asyncio
@patch('src.bot.commands.character_commands.player_crud.get_by_discord_id', new_callable=AsyncMock)
@patch('src.bot.commands.character_commands.spend_attribute_points', new_callable=AsyncMock)
@patch('src.bot.commands.character_commands.rules.get_rule', new_callable=AsyncMock)
@patch('src.bot.commands.character_commands.localization_utils.get_localized_text')
async def test_levelup_command_message_formatting_key_error(
    mock_get_localized_text: MagicMock,
    mock_get_rule: AsyncMock,
    mock_spend_points_api: AsyncMock,
    mock_get_player: AsyncMock,
    mock_bot_fixture: AsyncMock,
    mock_interaction_fixture: AsyncMock,
    mock_player_fixture: Player,
    mock_session_fixture: AsyncSession,
    player_locale_fixture: str # 'ru'
):
    cog = CharacterCog(mock_bot_fixture)
    mock_get_player.return_value = mock_player_fixture

    details_for_spend_api = {"new_value": 11}
    mock_spend_points_api.return_value = (
        True,
        "custom_error_template_key",
        details_for_spend_api
    )

    custom_template_string_causes_keyerror = "Атрибут {attribute_name} улучшен. Бонус: {non_existent_placeholder}."
    mock_get_rule.return_value = custom_template_string_causes_keyerror

    await cog._levelup_internal(mock_interaction_fixture, "strength", 1, session=mock_session_fixture)

    mock_get_player.assert_called_once()
    mock_spend_points_api.assert_called_once()
    mock_get_rule.assert_called_once_with(mock_session_fixture, mock_interaction_fixture.guild_id, "custom_error_template_key")
    mock_get_localized_text.assert_not_called()

    # This message comes from default_messages["levelup_error_generic"] in _levelup_internal
    generic_error_message = "Произошла ошибка при распределении очков."
    mock_interaction_fixture.response.send_message.assert_called_once_with(
        generic_error_message, ephemeral=True
    )

@pytest.mark.asyncio
@patch('src.bot.commands.character_commands.CharacterCog._levelup_internal', new_callable=AsyncMock)
async def test_levelup_command_calls_internal(
    mock_levelup_internal: AsyncMock,
    mock_bot_fixture: AsyncMock,
    mock_interaction_fixture: AsyncMock,
):
    cog = CharacterCog(mock_bot_fixture)
    attribute_name_test = "dexterity"
    points_to_spend_test = 2
    await cog.levelup_command.callback(cog, mock_interaction_fixture, attribute_name_test, points_to_spend_test) # type: ignore
    mock_levelup_internal.assert_called_once_with(
        mock_interaction_fixture, attribute_name_test, points_to_spend_test
    )

async def setup(bot: commands.Bot):
    await bot.add_cog(CharacterCog(bot))
    # Assuming 'logger' is defined in character_commands.py, not here.
    # logger.info("CharacterCog успешно загружен.")
    pass
