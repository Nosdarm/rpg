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
from src.models.enums import PlayerStatus # Import PlayerStatus
from src.core.database import get_db_session # Для мокирования сессии
from src.config.settings import DEFAULT_STARTING_LOCATION_STATIC_ID, DEFAULT_PLAYER_START_PARAMS_JSON

# Фикстуры pytest для упрощения создания моков
@pytest.fixture
def mock_bot():
    """Мок для объекта discord.ext.commands.Bot"""
    bot = MagicMock() # Removed spec for now to ensure direct attribute assignment
    bot.latency = 0.123  # Set latency here
    bot.user = MagicMock(spec=User) # Can keep spec for user if its attributes are complex
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

# Вспомогательная функция для мокирования get_db_session как контекстного менеджера
def mock_db_session_context_manager(mock_session):
    cm = MagicMock()
    cm.__aenter__.return_value = mock_session
    cm.__aexit__.return_value = None # или AsyncMock(return_value=None) если нужно
    return cm

# Тесты для команды !ping (текстовая команда)
@pytest.fixture
def mock_ctx(mock_bot): # Inject the mock_bot fixture
    """Мок для объекта discord.ext.commands.Context"""
    ctx = AsyncMock(spec=commands.Context)
    ctx.bot = mock_bot # Use the injected mock_bot
    # ctx.bot.latency is already set on mock_bot
    ctx.send = AsyncMock()

    # Add author and guild attributes for commands.Context
    # Removing spec=User to allow direct attribute assignment to take precedence more reliably
    author_mock = MagicMock()
    author_mock.id = 12345
    author_mock.name = "TestUser"
    author_mock.display_name = "TestUserDisplay"
    author_mock.mention = f"<@{author_mock.id}>"
    ctx.author = author_mock

    # Using MagicMock for guild as well for consistency
    guild_mock = MagicMock(spec=Guild)
    guild_mock.id = 67890
    guild_mock.name = "TestGuild"
    ctx.guild = guild_mock
    # Removed duplicate assignments for ctx.guild.id and ctx.guild.name
    return ctx


# Тесты для команды /start (которая на самом деле является текстовой командой "start")
@pytest.mark.asyncio
async def test_start_command_new_player(command_cog, mock_ctx, mock_db_session): # Changed mock_interaction to mock_ctx
    """Тест команды /start для нового игрока."""

    # Настраиваем мок сессии и CRUD операций
    # Предполагаем, что get_player_by_discord_id вернет None (новый игрок)
    mock_get_player = AsyncMock(return_value=None) # This will be patched for 'src.core.crud.crud_player.player_crud.get_by_discord_id'
    # Предполагаем, что get_location_by_static_id вернет мок локации
    mock_location = MagicMock(spec=Location)
    mock_location.id = 1
    mock_location.static_id = DEFAULT_STARTING_LOCATION_STATIC_ID # Used for assertion
    mock_location.name_i18n = {"en": "Starting Village Square Test"} # For get_localized_text
    mock_get_location = AsyncMock(return_value=mock_location) # Patched for 'src.core.crud.crud_location.location_crud.get_by_static_id'

    # Mock for player_crud.create to capture its arguments
    mock_player_create = AsyncMock(spec=Player)
    # Mock the return value of player_crud.create to simulate a created player object
    # This player object is used by the command to formulate the response message
    created_player_instance_mock = Player(
            id=1, name="FixedPlayerNameInTest", level=1, selected_language="en", # Use a fixed string
        guild_id=mock_ctx.guild.id, discord_id=mock_ctx.author.id, current_location_id=mock_location.id
    )
    mock_player_create.return_value = created_player_instance_mock

    # Patch target for get_db_session is 'src.core.database.get_db_session'
    # Patch targets for CRUD operations should point to their original definitions
    with patch('src.core.database.get_db_session', return_value=mock_db_session_context_manager(mock_db_session)):
        with patch('src.core.crud.crud_player.player_crud.get_by_discord_id', mock_get_player):
            with patch('src.core.crud.crud_location.location_crud.get_by_static_id', mock_get_location):
                with patch('src.core.crud.crud_player.player_crud.create', mock_player_create):
                    await command_cog.start_command.callback(command_cog, mock_ctx)

    # Проверяем, что был вызван поиск игрока
    mock_get_player.assert_called_once_with(
        mock_db_session,
        guild_id=mock_ctx.guild.id,
        discord_id=mock_ctx.author.id
    )

    # Проверяем, что был вызван поиск локации
    mock_get_location.assert_called_once_with(
        mock_db_session,
        guild_id=mock_ctx.guild.id,
        static_id="starting_village_square" # Value hardcoded in command
    )

    # Проверяем, что игрок был создан (player_crud.create called)
    mock_player_create.assert_called_once()
    # Verify arguments passed to player_crud.create
    args_create, kwargs_create = mock_player_create.call_args
    created_player_data_obj_in = kwargs_create['obj_in'] # player_crud.create receives obj_in as a kwarg

    assert created_player_data_obj_in["guild_id"] == mock_ctx.guild.id
    assert created_player_data_obj_in["discord_id"] == mock_ctx.author.id
    assert created_player_data_obj_in["name"] == mock_ctx.author.display_name
    assert created_player_data_obj_in["current_location_id"] == mock_location.id

    # Проверяем, что было отправлено сообщение об успехе
    mock_ctx.send.assert_called_once()
    args_msg, kwargs_msg = mock_ctx.send.call_args
    assert "Добро пожаловать в мир" in args_msg[0]
    assert "FixedPlayerNameInTest" in args_msg[0] # Check for the fixed string name

@pytest.mark.asyncio
async def test_start_command_existing_player(command_cog, mock_ctx, mock_db_session): # Use mock_ctx
    """Тест команды /start для существующего игрока."""

    # Настраиваем мок существующего игрока
    mock_existing_player = Player(
        id=100, name="OldPlayer", guild_id=mock_ctx.guild.id, discord_id=mock_ctx.author.id,
        current_location_id=1, level=5, gold=100, current_status=PlayerStatus.EXPLORING, selected_language="en"
    )
    mock_player_crud_get_by_discord_id = AsyncMock(return_value=mock_existing_player)

    # Мок для локации существующего игрока
    mock_player_location = MagicMock(spec=Location)
    mock_player_location.name_i18n = {"en": "The Usual Spot"} # Используем i18n поле как в коде
    mock_location_crud_get = AsyncMock(return_value=mock_player_location)

    with patch('src.core.database.get_db_session', return_value=mock_db_session_context_manager(mock_db_session)):
        with patch('src.core.crud.crud_player.player_crud.get_by_discord_id', mock_player_crud_get_by_discord_id):
            with patch('src.core.crud.crud_location.location_crud.get', mock_location_crud_get): # Used for existing player's loc
                await command_cog.start_command.callback(command_cog, mock_ctx)

    # Проверяем вызов player_crud.get_by_discord_id
    mock_player_crud_get_by_discord_id.assert_called_once_with(
        mock_db_session,
        guild_id=mock_ctx.guild.id,
        discord_id=mock_ctx.author.id
    )

    # Проверяем вызов location_crud.get для локации существующего игрока
    mock_location_crud_get.assert_called_once_with(
        mock_db_session, id=mock_existing_player.current_location_id, guild_id=mock_ctx.guild.id
    )

    mock_db_session.add.assert_not_called()

    # Проверяем отправленное сообщение
    mock_ctx.send.assert_called_once()
    args, kwargs = mock_ctx.send.call_args
    assert f"{mock_ctx.author.mention}, ты уже в игре!" in args[0]
    assert mock_existing_player.name in args[0]
    assert "The Usual Spot" in args[0]

@pytest.mark.asyncio
async def test_start_command_no_starting_location(command_cog, mock_ctx, mock_db_session):
    """Тест команды /start, если стартовая локация не найдена."""
    mock_player_crud_get_by_discord_id = AsyncMock(return_value=None) # Новый игрок
    mock_location_crud_get_by_static_id = AsyncMock(return_value=None) # Локация не найдена

    with patch('src.core.database.get_db_session', return_value=mock_db_session_context_manager(mock_db_session)):
        with patch('src.core.crud.crud_player.player_crud.get_by_discord_id', mock_player_crud_get_by_discord_id):
            with patch('src.core.crud.crud_location.location_crud.get_by_static_id', mock_location_crud_get_by_static_id):
                await command_cog.start_command.callback(command_cog, mock_ctx)

    # Проверяем вызов player_crud.get_by_discord_id
    mock_player_crud_get_by_discord_id.assert_called_once_with(
        mock_db_session, guild_id=mock_ctx.guild.id, discord_id=mock_ctx.author.id
    )

    # Проверяем вызов location_crud.get_by_static_id
    mock_location_crud_get_by_static_id.assert_called_once_with(
        mock_db_session,
        guild_id=mock_ctx.guild.id, # Use mock_ctx
        static_id="starting_village_square" # Command uses this hardcoded value
    )
    # mock_db_session.rollback.assert_called_once() # Rollback is handled by get_db_session context manager on error

    # Проверяем отправленное сообщение
    mock_ctx.send.assert_called_once() # Use mock_ctx
    args, kwargs = mock_ctx.send.call_args
    assert "Не могу начать игру: стартовая локация не настроена" in args[0]

# Тесты для команды !ping (текстовая команда)
# Используется фикстура mock_ctx, определенная ранее в файле.
# Вспомогательная функция mock_db_session_context_manager также используется та, что определена ранее.

@pytest.mark.asyncio
async def test_ping_command(command_cog, mock_ctx): # mock_ctx fixture is defined above
    """Тест текстовой команды !ping."""
    await command_cog.ping_command(command_cog, mock_ctx) # Обратите внимание на передачу self (cog)

    # Проверяем, что ctx.send был вызван
    mock_ctx.send.assert_called_once()
    # Проверяем, что ответ содержит "Pong!" и задержку
    args, kwargs = mock_ctx.send.call_args
    assert "Понг!" in args[0] # Changed to Russian "Понг!"
    assert "123ms" in args[0] # Removed space: 0.123 * 1000 = 123

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
