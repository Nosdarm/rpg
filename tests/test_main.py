import sys
import os

# Add the project root to sys.path FIRST
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import asyncio
import logging
from unittest import mock

import pytest
import discord

# Теперь можно импортировать из src
from src import main as main_module
from src.bot.core import BotCore # Убедимся, что BotCore можно импортировать


@pytest.fixture
def mock_settings(monkeypatch):
    """Мокает настройки и переменные окружения."""
    monkeypatch.setattr(main_module, 'DISCORD_BOT_TOKEN', 'fake_token')
    monkeypatch.setattr(main_module, 'LOG_LEVEL', 'DEBUG')
    monkeypatch.setattr('src.config.settings.BOT_PREFIX', '?')

@pytest.fixture
def mock_bot_core(monkeypatch):
    """Мокает BotCore."""
    mock_bot = mock.AsyncMock(spec=BotCore)
    mock_bot.is_closed.return_value = False
    mock_bot.command_prefix = "?"
    monkeypatch.setattr('src.main.BotCore', mock.MagicMock(return_value=mock_bot))
    return mock_bot

@pytest.fixture
def mock_init_db(monkeypatch):
    """Мокает init_db."""
    mock_db_init = mock.AsyncMock()
    monkeypatch.setattr(main_module, 'init_db', mock_db_init)
    return mock_db_init

@pytest.mark.asyncio
async def test_main_success(mock_settings, mock_bot_core, mock_init_db, caplog):
    """Тестирует успешный запуск main."""
    mock_bot_core.start.side_effect = None
    caplog.set_level(logging.INFO)
    await main_module.main()
    mock_init_db.assert_called_once()
    mock_bot_core.start.assert_called_once_with('fake_token')
    mock_bot_core.close.assert_called_once()
    assert "Запуск бота с префиксом: ?" in caplog.text
    assert "Discord бот остановлен." in caplog.text
    assert "Инициализация базы данных успешно завершена" in caplog.text

@pytest.mark.asyncio
async def test_main_db_init_error(mock_settings, mock_bot_core, mock_init_db, caplog):
    """Тестирует ошибку инициализации БД."""
    caplog.set_level(logging.ERROR)
    mock_init_db.side_effect = Exception("DB Test Error")
    await main_module.main()
    mock_init_db.assert_called_once()
    mock_bot_core.start.assert_not_called()
    assert "Ошибка при инициализации базы данных: DB Test Error" in caplog.text
    assert "Приложение не будет запущено из-за ошибки БД." in caplog.text

@pytest.mark.asyncio
async def test_main_discord_login_failure(mock_settings, mock_bot_core, mock_init_db, caplog, monkeypatch):
    """Тестирует ошибку входа Discord (неверный токен)."""
    caplog.set_level(logging.ERROR)
    mock_intents_instance = discord.Intents.default()
    mock_intents_instance.messages = True; mock_intents_instance.guilds = True; mock_intents_instance.message_content = True
    monkeypatch.setattr(discord, 'Intents', mock.MagicMock(return_value=mock_intents_instance))
    expected_prefix_callable = lambda bot, msg: ['?']
    monkeypatch.setattr('discord.ext.commands.when_mentioned_or', mock.Mock(return_value=expected_prefix_callable))
    mock_bot_core.start.side_effect = discord.LoginFailure("Login failed")
    await main_module.main()
    mock_init_db.assert_called_once()
    assert main_module.BotCore.called, "Конструктор BotCore должен был быть вызван" # type: ignore
    mock_bot_core.start.assert_called_once_with('fake_token')
    mock_bot_core.close.assert_called_once()
    assert "Ошибка входа: неверный токен Discord." in caplog.text

@pytest.mark.asyncio
async def test_main_generic_start_exception(mock_settings, mock_bot_core, mock_init_db, caplog, monkeypatch):
    """Тестирует общую ошибку при запуске бота."""
    caplog.set_level(logging.ERROR)
    mock_intents_instance = discord.Intents.default()
    mock_intents_instance.messages = True; mock_intents_instance.guilds = True; mock_intents_instance.message_content = True
    monkeypatch.setattr(discord, 'Intents', mock.MagicMock(return_value=mock_intents_instance))
    expected_prefix_callable = lambda bot, msg: ['?']
    monkeypatch.setattr('discord.ext.commands.when_mentioned_or', mock.Mock(return_value=expected_prefix_callable))
    mock_bot_core.start.side_effect = Exception("Generic Start Error")
    await main_module.main()
    mock_init_db.assert_called_once()
    assert main_module.BotCore.called, "Конструктор BotCore должен был быть вызван" # type: ignore
    mock_bot_core.start.assert_called_once_with('fake_token')
    mock_bot_core.close.assert_called_once()
    assert "Произошла ошибка при запуске бота: Generic Start Error" in caplog.text

@pytest.mark.asyncio
async def test_main_keyboard_interrupt_handling(mock_settings, mock_bot_core, mock_init_db, caplog, monkeypatch):
    """
    Тестирует обработку KeyboardInterrupt.
    """
    caplog.set_level(logging.INFO)
    mock_intents_instance = discord.Intents.default()
    mock_intents_instance.messages = True; mock_intents_instance.guilds = True; mock_intents_instance.message_content = True
    monkeypatch.setattr(discord, 'Intents', mock.MagicMock(return_value=mock_intents_instance))
    expected_prefix_callable = lambda bot, msg: ['?']
    monkeypatch.setattr('discord.ext.commands.when_mentioned_or', mock.Mock(return_value=expected_prefix_callable))
    mock_bot_core.start.side_effect = KeyboardInterrupt("Simulated Ctrl+C")

    # Ожидаем, что main() поймает KeyboardInterrupt и завершится штатно
    await main_module.main()

    mock_init_db.assert_called_once()
    mock_bot_core.start.assert_called_once_with('fake_token')
    # Проверяем, что bot.close() был вызван в блоке finally в main()
    mock_bot_core.close.assert_called_once()
    assert "Получен сигнал KeyboardInterrupt. Завершение работы..." in caplog.text
    assert "Discord бот остановлен." in caplog.text # Это сообщение из блока finally

@pytest.mark.asyncio
async def test_main_no_token_fixed(mock_settings, mock_bot_core, mock_init_db, caplog, monkeypatch):
    """Тестирует запуск main без токена (исправленный)."""
    caplog.set_level(logging.ERROR)
    monkeypatch.setattr(main_module, 'DISCORD_BOT_TOKEN', None)
    await main_module.main()
    mock_init_db.assert_not_called()
    mock_bot_core.start.assert_not_called()
    assert "Токен бота Discord не найден." in caplog.text

@pytest.mark.asyncio
async def test_main_success_with_bot_args_check(mock_settings, mock_bot_core, mock_init_db, caplog, monkeypatch):
    """Тестирует успешный запуск main и аргументы конструктора BotCore."""
    mock_bot_core.start.side_effect = None
    caplog.set_level(logging.INFO)
    mocked_bot_constructor = main_module.BotCore
    await main_module.main()
    mock_init_db.assert_called_once()
    assert mocked_bot_constructor.called, "Конструктор BotCore должен был быть вызван" # type: ignore
    args, kwargs = mocked_bot_constructor.call_args # type: ignore
    assert 'intents' in kwargs
    assert isinstance(kwargs['intents'], discord.Intents)
    assert kwargs['intents'].messages is True
    assert kwargs['intents'].guilds is True
    assert kwargs['intents'].message_content is True
    from discord.ext import commands
    mock_when_mentioned_or = mock.Mock(return_value=lambda bot, msg: ['?'])
    monkeypatch.setattr(commands, 'when_mentioned_or', mock_when_mentioned_or)
    mock_bot_core.start.assert_called_once_with('fake_token')
    mock_bot_core.close.assert_called_once()
    assert "Запуск бота с префиксом: ?" in caplog.text
    assert "Discord бот остановлен." in caplog.text
    assert "Инициализация базы данных успешно завершена" in caplog.text
