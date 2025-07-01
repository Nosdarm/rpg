import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from discord import Interaction, User, Guild
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession

# Предполагаемые пути к классам и функциям
# Их нужно будет скорректировать под реальную структуру вашего проекта
from src.bot.general_commands import CommandCog
from src.models.player import Player
from src.models.location import Location
from src.core.database import get_db_session # Для мокирования сессии
from src.config.settings import DEFAULT_STARTING_LOCATION_STATIC_ID, DEFAULT_PLAYER_START_PARAMS_JSON

# Фикстуры pytest для упрощения создания моков
@pytest.fixture
def mock_bot():
    """Мок для объекта discord.ext.commands.Bot"""
    bot = MagicMock(spec=commands.Bot)
    bot.user = MagicMock(spec=User)
    bot.user.id = 123456789012345678 # ID бота
    return bot

@pytest.fixture
def mock_interaction():
    """Мок для объекта discord.Interaction"""
    interaction = AsyncMock(spec=Interaction)
    interaction.user = AsyncMock(spec=User)
    interaction.user.id = 12345
    interaction.user.name = "TestUser"
    interaction.guild = AsyncMock(spec=Guild)
    interaction.guild.id = 67890
    interaction.response = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction

@pytest.fixture
def mock_db_session():
    """Мок для сессии SQLAlchemy"""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = AsyncMock()
    session.scalar = AsyncMock()
    session.execute = AsyncMock() # Для более общих запросов
    return session

@pytest.fixture
def command_cog(mock_bot):
    """Экземпляр CommandCog с моком бота"""
    cog = CommandCog(mock_bot)
    return cog

# Тесты для команды /start
@pytest.mark.asyncio
async def test_start_command_new_player(command_cog, mock_interaction, mock_db_session):
    """Тест команды /start для нового игрока."""

    # Настраиваем мок сессии и CRUD операций
    # Предполагаем, что get_player_by_discord_id вернет None (новый игрок)
    mock_get_player = AsyncMock(return_value=None)
    # Предполагаем, что get_location_by_static_id вернет мок локации
    mock_location = MagicMock(spec=Location)
    mock_location.id = 1
    mock_location.static_id = DEFAULT_STARTING_LOCATION_STATIC_ID
    mock_get_location = AsyncMock(return_value=mock_location)

    with patch('src.bot.general_commands.get_db_session', return_value=mock_db_session_context_manager(mock_db_session)):
        with patch('src.core.player_utils.get_player_by_discord_id', mock_get_player):
            with patch('src.core.locations_utils.get_location_by_static_id', mock_get_location):
                await command_cog.start_command.callback(command_cog, mock_interaction)

    # Проверяем, что был вызван поиск игрока
    mock_get_player.assert_called_once_with(
        session=mock_db_session,
        guild_id=mock_interaction.guild.id,
        discord_id=mock_interaction.user.id
    )

    # Проверяем, что был вызван поиск локации
    mock_get_location.assert_called_once_with(
        session=mock_db_session,
        guild_id=mock_interaction.guild.id,
        static_id=DEFAULT_STARTING_LOCATION_STATIC_ID
    )

    # Проверяем, что игрок был добавлен в сессию (создан)
    # mock_db_session.add.assert_called_once() # Может быть вызван не один раз, если есть другие add
    assert mock_db_session.add.call_count > 0
    added_object = mock_db_session.add.call_args_list[0][0][0] # Первый аргумент первого вызова add
    assert isinstance(added_object, Player)
    assert added_object.guild_id == mock_interaction.guild.id
    assert added_object.discord_id == mock_interaction.user.id
    assert added_object.name == mock_interaction.user.name
    assert added_object.current_location_id == mock_location.id
    assert added_object.start_params_json == DEFAULT_PLAYER_START_PARAMS_JSON

    # Проверяем, что был вызван commit
    mock_db_session.commit.assert_called_once()

    # Проверяем, что было отправлено сообщение об успехе
    mock_interaction.response.send_message.assert_called_once()
    # Можно добавить проверку на содержание сообщения, если оно предсказуемо
    # args, kwargs = mock_interaction.response.send_message.call_args
    # assert "Добро пожаловать" in args[0]
    assert "успешно зарегистрированы" in mock_interaction.response.send_message.call_args[0][0]

@pytest.mark.asyncio
async def test_start_command_existing_player(command_cog, mock_interaction, mock_db_session):
    """Тест команды /start для существующего игрока."""

    # Настраиваем мок игрока
    mock_player = MagicMock(spec=Player)
    mock_player.id = 100
    mock_player.name = "OldPlayer"

    mock_get_player = AsyncMock(return_value=mock_player)

    with patch('src.bot.general_commands.get_db_session', return_value=mock_db_session_context_manager(mock_db_session)):
        with patch('src.core.player_utils.get_player_by_discord_id', mock_get_player):
            await command_cog.start_command.callback(command_cog, mock_interaction)

    # Проверяем, что был вызван поиск игрока
    mock_get_player.assert_called_once_with(
        session=mock_db_session,
        guild_id=mock_interaction.guild.id,
        discord_id=mock_interaction.user.id
    )

    # Проверяем, что НЕ был вызван commit (т.к. игрок существует)
    mock_db_session.commit.assert_not_called()
    # Проверяем, что НЕ было попытки добавить нового игрока
    mock_db_session.add.assert_not_called()


    # Проверяем, что было отправлено сообщение о том, что игрок уже существует
    mock_interaction.response.send_message.assert_called_once()
    args, kwargs = mock_interaction.response.send_message.call_args
    assert "Вы уже зарегистрированы" in args[0]
    assert kwargs.get('ephemeral') is True

@pytest.mark.asyncio
async def test_start_command_no_starting_location(command_cog, mock_interaction, mock_db_session):
    """Тест команды /start, если стартовая локация не найдена."""
    mock_get_player = AsyncMock(return_value=None) # Новый игрок
    mock_get_location = AsyncMock(return_value=None) # Локация не найдена

    with patch('src.bot.general_commands.get_db_session', return_value=mock_db_session_context_manager(mock_db_session)):
        with patch('src.core.player_utils.get_player_by_discord_id', mock_get_player):
            with patch('src.core.locations_utils.get_location_by_static_id', mock_get_location):
                await command_cog.start_command.callback(command_cog, mock_interaction)

    mock_get_location.assert_called_once_with(
        session=mock_db_session,
        guild_id=mock_interaction.guild.id,
        static_id=DEFAULT_STARTING_LOCATION_STATIC_ID
    )
    mock_db_session.rollback.assert_called_once() # Проверяем откат транзакции
    mock_interaction.response.send_message.assert_called_once()
    args, kwargs = mock_interaction.response.send_message.call_args
    assert "Ошибка регистрации" in args[0]
    assert "Стартовая локация не найдена" in args[0]
    assert kwargs.get('ephemeral') is True

# Вспомогательная функция для мокирования get_db_session как контекстного менеджера
def mock_db_session_context_manager(mock_session):
    cm = MagicMock()
    cm.__aenter__.return_value = mock_session
    cm.__aexit__.return_value = None # или AsyncMock(return_value=None) если нужно
    return cm

# Тесты для команды !ping (текстовая команда)
@pytest.fixture
def mock_ctx():
    """Мок для объекта discord.ext.commands.Context"""
    ctx = AsyncMock(spec=commands.Context)
    ctx.bot = MagicMock(spec=commands.Bot)
    ctx.bot.latency = 0.123  # Пример задержки
    ctx.send = AsyncMock()
    return ctx

@pytest.mark.asyncio
async def test_ping_command(command_cog, mock_ctx):
    """Тест текстовой команды !ping."""
    await command_cog.ping_command(command_cog, mock_ctx) # Обратите внимание на передачу self (cog)

    # Проверяем, что ctx.send был вызван
    mock_ctx.send.assert_called_once()
    # Проверяем, что ответ содержит "Pong!" и задержку
    args, kwargs = mock_ctx.send.call_args
    assert "Pong!" in args[0]
    assert "123 мс" in args[0] # 0.123 * 1000 = 123

# TODO: Добавить тесты для других команд по аналогии
# TODO: Убедиться, что пути импорта в начале файла корректны для вашей структуры проекта.
# TODO: Возможно, потребуется мокировать `src.config.settings.logger` если он используется напрямую в командах
#       и его вызовы нужно проверить или подавить.

# Для запуска тестов:
# Убедитесь, что pytest и pytest-asyncio установлены: pip install pytest pytest-asyncio
# В корне проекта выполните: python -m pytest tests/bot/test_general_commands_mocked.py
# (или просто `pytest` если структура проекта и pytest.ini настроены соответствующим образом)

# Важно: Эти тесты предполагают определенную структуру кода и имена функций/классов.
# Их нужно будет адаптировать под ваш проект.
# Например, пути к `get_player_by_discord_id` и `get_location_by_static_id`
# могут быть другими (например, `src.bot.general_commands.get_player_by_discord_id`
# если они импортируются напрямую в модуль с командами). Патчить нужно там, где
# объект ищется (т.е. в том модуле, где он используется).
# Если `get_db_session` импортируется как `from src.core.database import get_db_session`
# в `src.bot.general_commands`, то и патчить нужно `src.bot.general_commands.get_db_session`.

# Если вы используете декоратор @transactional, который внедряет сессию,
# то мокировать get_db_session напрямую в модуле команды может быть правильным подходом.
# Тесты для start_command предполагают, что @transactional используется,
# и get_db_session вызывается внутри команды для получения сессии.

# Проверяем, что `DEFAULT_PLAYER_START_PARAMS_JSON` существует и имеет корректный тип
if not isinstance(DEFAULT_PLAYER_START_PARAMS_JSON, dict):
    raise TypeError("DEFAULT_PLAYER_START_PARAMS_JSON должен быть словарем")

# Проверяем, что `DEFAULT_STARTING_LOCATION_STATIC_ID` существует и имеет корректный тип
if not isinstance(DEFAULT_STARTING_LOCATION_STATIC_ID, str):
    raise TypeError("DEFAULT_STARTING_LOCATION_STATIC_ID должен быть строкой")

# Создаем пустую директорию, если она не существует
# import os
# if not os.path.exists("tests/bot"):
#    os.makedirs("tests/bot")
