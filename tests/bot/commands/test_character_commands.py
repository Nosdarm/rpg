import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import discord
from discord import app_commands
from discord.ext import commands # <--- Добавлен импорт
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.commands.character_commands import CharacterCog
from src.models import Player
from src.models.enums import PlayerStatus

# Фикстуры
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
        unspent_xp=3, # Есть очки для траты
        attributes_json={"strength": 10, "dexterity": 8},
        selected_language=player_locale_fixture,
        current_status=PlayerStatus.IDLE
    )

@pytest.fixture
def mock_session_fixture() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    # @transactional декоратор сам управляет commit/rollback, поэтому мокать их не всегда нужно,
    # но для чистоты можно, если мы хотим проверить, что они НЕ вызываются внутри самой команды.
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


# @pytest.mark.asyncio
# @patch('src.bot.commands.character_commands.player_crud.get_by_discord_id', new_callable=AsyncMock)
# @patch('src.bot.commands.character_commands.spend_attribute_points', new_callable=AsyncMock)
# @patch('src.bot.commands.character_commands.rules.get_rule', new_callable=AsyncMock) # Для локализации
# @patch('src.bot.commands.character_commands.localization_utils.get_localized_text') # Для локализации
# async def test_levelup_command_success(
#     mock_get_localized_text: MagicMock,
#     mock_get_rule: AsyncMock,
#     mock_spend_points_api: AsyncMock,
#     mock_get_player: AsyncMock,
#     mock_bot_fixture: AsyncMock,
#     mock_interaction_fixture: AsyncMock,
#     mock_player_fixture: Player,
#     mock_session_fixture: AsyncMock,
#     player_locale_fixture: str
# ):
#     cog = CharacterCog(mock_bot_fixture)
#     mock_get_player.return_value = mock_player_fixture

#     mock_spend_points_api.return_value = (
#         True,
#         "levelup_success",
#         {"attribute_name": "Сила", "new_value": 11, "remaining_xp": 2, "spent_points": 1}
#     )
#     mock_i18n_template = {"ru": "{attribute_name} улучшен до {new_value}. Осталось очков: {remaining_xp}."}
#     mock_get_rule.return_value = mock_i18n_template
#     mock_get_localized_text.return_value = "Сила улучшен до 11. Осталось очков: 2."

#     # Вызываем внутренний метод, к которому применен @transactional
#     await cog._levelup_internal(mock_interaction_fixture, "strength", 1, session=mock_session_fixture)

#     mock_get_player.assert_called_once_with(
#         db=mock_session_fixture, guild_id=mock_interaction_fixture.guild_id, discord_id=mock_interaction_fixture.user.id
#     )
#     mock_spend_points_api.assert_called_once_with(
#         session=mock_session_fixture,
#         player=mock_player_fixture,
#         attribute_name="strength",
#         points_to_spend=1,
#         guild_id=mock_interaction_fixture.guild_id
#     )
#     mock_get_rule.assert_called_once_with(mock_session_fixture, mock_interaction_fixture.guild_id, "levelup_success")
#     mock_get_localized_text.assert_called_once_with(mock_i18n_template, player_locale_fixture, "en")

#     mock_interaction_fixture.response.send_message.assert_called_once_with(
#         "Сила улучшен до 11. Осталось очков: 2.", ephemeral=True
#     )

@pytest.mark.asyncio
@patch('src.bot.commands.character_commands.player_crud.get_by_discord_id', new_callable=AsyncMock)
@patch('src.bot.commands.character_commands.localization_utils.get_localized_text')
async def test_levelup_command_player_not_found(
    mock_get_localized_text: MagicMock, # Не используется напрямую, но нужен для консистентности
    mock_get_player: AsyncMock,
    mock_bot_fixture: AsyncMock,
    mock_interaction_fixture: AsyncMock,
    mock_session_fixture: AsyncMock
):
    cog = CharacterCog(mock_bot_fixture)
    mock_get_player.return_value = None # Игрок не найден

    # mock_get_localized_text.return_value = "Сначала вам нужно начать игру с помощью команды `/start`."
    # Вместо этого, команда использует встроенный текст, если не переопределено правилом.
    # Мы тестируем этот встроенный текст.

    await cog._levelup_internal(mock_interaction_fixture, "strength", 1, session=mock_session_fixture)

    mock_interaction_fixture.response.send_message.assert_called_once_with(
        "Сначала вам нужно начать игру с помощью команды `/start`.", ephemeral=True
    )

# @pytest.mark.asyncio
# @patch('src.bot.commands.character_commands.player_crud.get_by_discord_id', new_callable=AsyncMock)
# @patch('src.bot.commands.character_commands.localization_utils.get_localized_text')
# async def test_levelup_command_no_unspent_xp(
#     mock_get_localized_text: MagicMock,
#     mock_get_player: AsyncMock,
#     mock_bot_fixture: AsyncMock,
#     mock_interaction_fixture: AsyncMock,
#     mock_player_fixture: Player,
#     mock_session_fixture: AsyncMock,
#     player_locale_fixture: str
# ):
#     cog = CharacterCog(mock_bot_fixture)
#     mock_player_fixture.unspent_xp = 0 # У игрока нет очков
#     mock_get_player.return_value = mock_player_fixture

#     # Это сообщение также использует localization_utils.get_localized_text со встроенным словарем
#     mock_get_localized_text.return_value = "У вас нет нераспределенных очков атрибутов."

#     await cog._levelup_internal(mock_interaction_fixture, "strength", 1, session=mock_session_fixture)

#     mock_get_localized_text.assert_called_once_with(
#         {"en": "You have no unspent attribute points to spend.", "ru": "У вас нет нераспределенных очков атрибутов."},
#         player_locale_fixture
#     )
#     mock_interaction_fixture.response.send_message.assert_called_once_with(
#         "У вас нет нераспределенных очков атрибутов.", ephemeral=True
#     )

# @pytest.mark.asyncio
# @patch('src.bot.commands.character_commands.player_crud.get_by_discord_id', new_callable=AsyncMock)
# @patch('src.bot.commands.character_commands.spend_attribute_points', new_callable=AsyncMock)
# @patch('src.bot.commands.character_commands.rules.get_rule', new_callable=AsyncMock)
# @patch('src.bot.commands.character_commands.localization_utils.get_localized_text')
# async def test_levelup_command_api_error_not_enough_points(
#     mock_get_localized_text: MagicMock,
#     mock_get_rule: AsyncMock,
#     mock_spend_points_api: AsyncMock,
#     mock_get_player: AsyncMock,
#     mock_bot_fixture: AsyncMock,
#     mock_interaction_fixture: AsyncMock,
#     mock_player_fixture: Player,
#     mock_session_fixture: AsyncMock,
#     player_locale_fixture: str
# ):
#     cog = CharacterCog(mock_bot_fixture)
#     mock_get_player.return_value = mock_player_fixture # У игрока 3 очка

#     mock_spend_points_api.return_value = (
#         False,
#         "levelup_error_not_enough_xp",
#         {"unspent_xp": 3, "requested": 5} # Пытаемся потратить 5
#     )

#     mock_i18n_template = {"ru": "Недостаточно очков ({unspent_xp}) для траты {requested} очков."}
#     mock_get_rule.return_value = mock_i18n_template
#     mock_get_localized_text.return_value = "Недостаточно очков (3) для траты 5 очков."


#     await cog._levelup_internal(mock_interaction_fixture, "strength", 5, session=mock_session_fixture)

#     mock_spend_points_api.assert_called_once()
#     mock_get_rule.assert_called_once_with(mock_session_fixture, mock_interaction_fixture.guild_id, "levelup_error_not_enough_xp")
#     mock_get_localized_text.assert_called_once_with(mock_i18n_template, player_locale_fixture, "en")

#     mock_interaction_fixture.response.send_message.assert_called_once_with(
#         "Недостаточно очков (3) для траты 5 очков.", ephemeral=True
#     )

# @pytest.mark.asyncio
# @patch('src.bot.commands.character_commands.player_crud.get_by_discord_id', new_callable=AsyncMock)
# @patch('src.bot.commands.character_commands.spend_attribute_points', new_callable=AsyncMock)
# @patch('src.bot.commands.character_commands.rules.get_rule', new_callable=AsyncMock)
# async def test_levelup_command_message_formatting_fallback(
#     mock_get_rule: AsyncMock,
#     mock_spend_points_api: AsyncMock,
#     mock_get_player: AsyncMock,
#     mock_bot_fixture: AsyncMock,
#     mock_interaction_fixture: AsyncMock, # locale="ru"
#     mock_player_fixture: Player,
#     mock_session_fixture: AsyncMock
# ):
#     """Тест проверяет, что используется default_message, если правило не найдено."""
#     cog = CharacterCog(mock_bot_fixture)
#     mock_get_player.return_value = mock_player_fixture

#     mock_spend_points_api.return_value = (
#         False,
#         "levelup_error_invalid_attribute", # Этот ключ не имеет i18n словаря в default_messages
#         {"attribute_name": "wisdom"}
#     )

#     mock_get_rule.return_value = None # Правило не найдено в RuleConfig

#     # localization_utils.get_localized_text не должен вызываться для этого ключа,
#     # так как default_messages["levelup_error_invalid_attribute"] - это строка, а не словарь.

#     await cog._levelup_internal(mock_interaction_fixture, "wisdom", 1, session=mock_session_fixture)

#     expected_default_message = "Атрибут '{attribute_name}' не найден или недоступен для улучшения."
#     formatted_expected_message = expected_default_message.format(attribute_name="wisdom")

#     mock_interaction_fixture.response.send_message.assert_called_once_with(
#         formatted_expected_message, ephemeral=True
#     )

# @pytest.mark.asyncio
# @patch('src.bot.commands.character_commands.player_crud.get_by_discord_id', new_callable=AsyncMock)
# @patch('src.bot.commands.character_commands.spend_attribute_points', new_callable=AsyncMock)
# @patch('src.bot.commands.character_commands.rules.get_rule', new_callable=AsyncMock)
# @patch('src.bot.commands.character_commands.localization_utils.get_localized_text')
# async def test_levelup_command_message_formatting_key_error(
#     mock_get_localized_text: MagicMock,
#     mock_get_rule: AsyncMock,
#     mock_spend_points_api: AsyncMock,
#     mock_get_player: AsyncMock,
#     mock_bot_fixture: AsyncMock,
#     mock_interaction_fixture: AsyncMock,
#     mock_player_fixture: Player,
#     mock_session_fixture: AsyncMock,
#     player_locale_fixture: str
# ):
#     """Тест проверяет, что используется generic_error_message при KeyError в format."""
#     cog = CharacterCog(mock_bot_fixture)
#     mock_get_player.return_value = mock_player_fixture

#     mock_spend_points_api.return_value = (
#         True,
#         "levelup_success",
#         {"attribute_name_WRONG_KEY": "Сила", "new_value": 11} # Не хватает ключей для форматирования
#     )

#     mock_i18n_template = {"ru": "{attribute_name} улучшен до {new_value}. Осталось очков: {remaining_xp}."}
#     mock_get_rule.return_value = mock_i18n_template
#     mock_get_localized_text.return_value = "{attribute_name} улучшен до {new_value}. Осталось очков: {remaining_xp}."


#     await cog._levelup_internal(mock_interaction_fixture, "strength", 1, session=mock_session_fixture)

#     generic_error_message = "Произошла ошибка при форматировании ответа." # Из default_messages["levelup_error_generic"]

#     mock_interaction_fixture.response.send_message.assert_called_once_with(
#         generic_error_message, ephemeral=True
#     )

@pytest.mark.asyncio
@patch('src.bot.commands.character_commands.CharacterCog._levelup_internal', new_callable=AsyncMock)
async def test_levelup_command_calls_internal(
    mock_levelup_internal: AsyncMock,
    mock_bot_fixture: AsyncMock,
    mock_interaction_fixture: AsyncMock,
):
    """Тест проверяет, что команда-обертка levelup_command вызывает _levelup_internal."""
    cog = CharacterCog(mock_bot_fixture)

    attribute_name_test = "dexterity"
    points_to_spend_test = 2

    # Вызываем callback команды, так как это app_command
    await cog.levelup_command.callback(cog, mock_interaction_fixture, attribute_name_test, points_to_spend_test)

    mock_levelup_internal.assert_called_once_with(
        mock_interaction_fixture, attribute_name_test, points_to_spend_test
    )

# TODO: Добавить тесты на случай, если interaction.guild_id или interaction.user отсутствуют (хотя Discord обычно их предоставляет)
# Это покрывается в _levelup_internal, но можно и для levelup_command, если будет отличаться логика.

# Команда setup не является частью логики команд, а служебной функцией для загрузки кога,
# поэтому ее прямое тестирование здесь не так критично, как тестирование самих команд.
# Ее работоспособность проверяется при запуске бота и загрузке когов.
