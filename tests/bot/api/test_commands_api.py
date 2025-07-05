import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from discord.ext import commands as ext_commands # Для мока типа бота

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import discord # Added import for discord

# Важно: FastAPI приложение должно быть импортировано ПОСЛЕ sys.path modification
# и ПОСЛЕ того, как моки для зависимостей, используемых при импорте, могут быть установлены.
# В данном случае, главный app из src.main импортирует src.bot.api.commands_api,
# который импортирует src.core.command_utils.
# Главное, чтобы src.main был доступен.

from src.main import app # Импортируем FastAPI app из src.main
from src.main import app # Импортируем FastAPI app из src.main
from src.models.command_info import CommandInfo, CommandListResponse
from src.bot.core import BotCore # Импортируем BotCore для спека

from src.bot.api.commands_api import get_bot_instance as actual_get_bot_instance # Импортируем реальную зависимость

# Фикстура для мока экземпляра бота
@pytest.fixture
def mock_bot_api_instance() -> AsyncMock:
    bot = AsyncMock(spec=BotCore)
    bot.tree = AsyncMock(spec=discord.app_commands.CommandTree)
    return bot

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(autouse=True)
def override_bot_dependency(mock_bot_api_instance: AsyncMock):
    """Overrides the get_bot_instance dependency for all tests in this module."""
    async def mock_get_bot_instance():
        return mock_bot_api_instance
    app.dependency_overrides[actual_get_bot_instance] = mock_get_bot_instance
    yield
    # Очистка после всех тестов в модуле (или после каждого, если scope="function")
    if actual_get_bot_instance in app.dependency_overrides:
        del app.dependency_overrides[actual_get_bot_instance]


# Тесты для API эндпоинта /commands/
def test_list_bot_commands_success_empty(client: TestClient, mocker, mock_bot_api_instance: AsyncMock):
    # Мокаем get_bot_commands, чтобы вернуть пустой список
    mocked_get_commands = mocker.patch("src.bot.api.commands_api.get_bot_commands", new_callable=AsyncMock)
    mocked_get_commands.return_value = []

    response = client.get("/api/v1/commands/")
    assert response.status_code == 200
    data = response.json()
    assert data["commands"] == []
    from src.config import settings # Импорт для доступа к BOT_LANGUAGE
    assert data["language_code"] == settings.BOT_LANGUAGE # Ожидаем язык по умолчанию
    # Убедимся, что mock_bot_api_instance был передан в get_bot_commands
    mocked_get_commands.assert_called_once_with(bot=mock_bot_api_instance, guild_id=None, language=settings.BOT_LANGUAGE)

def test_list_bot_commands_success_with_data_and_lang(client: TestClient, mocker, mock_bot_api_instance: AsyncMock):
    sample_commands = [
        CommandInfo(name="ping", description="Checks latency", parameters=[]),
        CommandInfo(name="help", description="Shows help", parameters=[]),
    ]
    # Мокаем get_bot_commands
    mocked_get_commands = mocker.patch("src.bot.api.commands_api.get_bot_commands", new_callable=AsyncMock)
    mocked_get_commands.return_value = sample_commands

    response = client.get("/api/v1/commands/?lang=ru&guild_id=123")
    assert response.status_code == 200
    data = response.json()

    assert len(data["commands"]) == 2
    assert data["commands"][0]["name"] == "ping"
    assert data["commands"][1]["name"] == "help"
    assert data["language_code"] == "ru" # Язык должен быть передан и возвращен

    mocked_get_commands.assert_called_once_with(bot=mock_bot_api_instance, guild_id=123, language="ru")

def test_list_bot_commands_uses_default_language_if_none_provided(client: TestClient, mocker, mock_bot_api_instance: AsyncMock):
    from src.config import settings # Импортируем здесь, чтобы получить актуальное значение

    mocked_get_commands = mocker.patch("src.bot.api.commands_api.get_bot_commands", new_callable=AsyncMock)
    mocked_get_commands.return_value = [] # Содержимое не важно, важны параметры вызова

    response = client.get("/api/v1/commands/")
    assert response.status_code == 200
    data = response.json()

    # Язык по умолчанию из настроек
    assert data["language_code"] == settings.BOT_LANGUAGE
    mocked_get_commands.assert_called_once_with(bot=mock_bot_api_instance, guild_id=None, language=settings.BOT_LANGUAGE)

def test_list_bot_commands_internal_error(client: TestClient, mocker, mock_bot_api_instance: AsyncMock):
    # Мокаем get_bot_commands, чтобы он вызывал исключение
    mocked_get_commands = mocker.patch("src.bot.api.commands_api.get_bot_commands", new_callable=AsyncMock)
    mocked_get_commands.side_effect = Exception("Internal processing error")

    response = client.get("/api/v1/commands/")
    assert response.status_code == 500
    data = response.json()
    from src.config import settings # Импортируем здесь для языка по умолчанию
    expected_lang = settings.BOT_LANGUAGE
    assert data["detail"] == "Failed to retrieve bot commands."
    # Проверяем, что get_bot_commands был вызван с моком бота
    mocked_get_commands.assert_called_once_with(bot=mock_bot_api_instance, guild_id=None, language=expected_lang)

# Импорты ANY и HTTPException уже вверху файла, дубликаты не нужны.

def test_list_bot_commands_bot_not_available(client: TestClient): # mocker не нужен, mock_bot_api_instance тоже
    # This test aims to check the behavior when the actual get_bot_instance dependency
    # fails (e.g., bot is not initialized in app.state).
    # The autouse fixture 'override_bot_dependency' normally replaces get_bot_instance.
    # We need to temporarily remove that override for this specific test.

    original_dependency_override = app.dependency_overrides.pop(actual_get_bot_instance, None)

    # Save and then clear app.state.bot to simulate bot unavailability for the real dependency
    original_app_state_bot = getattr(app.state, 'bot', None)
    if hasattr(app.state, 'bot'): # Ensure app.state has 'bot' attribute to avoid AttributeError if never set
        delattr(app.state, 'bot') # Or set app.state.bot = None, depending on get_bot_instance logic

    try:
        response = client.get("/api/v1/commands/")
        assert response.status_code == 500
        assert response.json()["detail"] == "Bot instance not available."
    finally:
        # Restore app.state.bot
        if original_app_state_bot is not None: # Only restore if it was something
             app.state.bot = original_app_state_bot
        elif hasattr(app.state, 'bot'): # If it was None initially but now exists due to test
             delattr(app.state, 'bot')


        # Restore the original dependency override if it existed.
        # The autouse fixture's cleanup will run after this test,
        # ensuring its override is active for subsequent tests.
        if original_dependency_override:
            app.dependency_overrides[actual_get_bot_instance] = original_dependency_override
        # If it was None, actual_get_bot_instance was not in overrides, which is what we wanted for this test.
        # The autouse fixture will re-establish its own override for the next test.


# Для запуска тестов напрямую, если нужно (хотя pytest test_file.py предпочтительнее)
if __name__ == "__main__":
    pytest.main([__file__])
