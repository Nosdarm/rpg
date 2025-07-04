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

# Мок для экземпляра бота, который будет использоваться в тестах
mock_bot_instance = AsyncMock(spec=BotCore)
mock_bot_instance.tree = AsyncMock(spec=discord.app_commands.CommandTree)

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

# Тесты для API эндпоинта /commands/
def test_list_bot_commands_success_empty(client: TestClient, mocker):
    # Мокаем get_bot_commands, чтобы вернуть пустой список
    mocked_get_commands = mocker.patch("src.bot.api.commands_api.get_bot_commands", new_callable=AsyncMock)
    mocked_get_commands.return_value = []

    response = client.get("/api/v1/commands/")
    assert response.status_code == 200
    data = response.json()
    assert data["commands"] == []
    from src.config import settings # Импорт для доступа к BOT_LANGUAGE
    assert data["language_code"] == settings.BOT_LANGUAGE # Ожидаем язык по умолчанию
    mocked_get_commands.assert_called_once_with(bot=mock_bot_instance, guild_id=None, language=settings.BOT_LANGUAGE) # И в вызове тоже

def test_list_bot_commands_success_with_data_and_lang(client: TestClient, mocker):
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

    mocked_get_commands.assert_called_once_with(bot=mock_bot_instance, guild_id=123, language="ru")

def test_list_bot_commands_uses_default_language_if_none_provided(client: TestClient, mocker):
    from src.config import settings # Импортируем здесь, чтобы получить актуальное значение

    mocked_get_commands = mocker.patch("src.bot.api.commands_api.get_bot_commands", new_callable=AsyncMock)
    mocked_get_commands.return_value = [] # Содержимое не важно, важны параметры вызова

    response = client.get("/api/v1/commands/")
    assert response.status_code == 200
    data = response.json()

    # Язык по умолчанию из настроек
    assert data["language_code"] == settings.BOT_LANGUAGE
    mocked_get_commands.assert_called_once_with(bot=mock_bot_instance, guild_id=None, language=settings.BOT_LANGUAGE)

def test_list_bot_commands_internal_error(client: TestClient, mocker):
    # Мокаем get_bot_commands, чтобы он вызывал исключение
    mocked_get_commands = mocker.patch("src.bot.api.commands_api.get_bot_commands", new_callable=AsyncMock)
    mocked_get_commands.side_effect = Exception("Internal processing error")

    response = client.get("/api/v1/commands/")
    assert response.status_code == 500
    data = response.json()
    from src.config import settings # Импортируем здесь для языка по умолчанию
    expected_lang = settings.BOT_LANGUAGE
    assert data["detail"] == "Failed to retrieve bot commands."
    mocked_get_commands.assert_called_once_with(bot=mock_bot_instance, guild_id=None, language=expected_lang)

    del app.dependency_overrides[actual_get_bot_instance] # Очистка

# Импорты ANY и HTTPException уже вверху файла, дубликаты не нужны.

def test_list_bot_commands_bot_not_available(client: TestClient, mocker):
    # Переопределяем мок для get_bot_instance на время этого теста, чтобы он вызвал ошибку
    mocker.patch("src.bot.api.commands_api.get_bot_instance", side_effect=HTTPException(status_code=500, detail="Bot instance not available."))

    response = client.get("/api/v1/commands/")
    assert response.status_code == 500
    assert response.json()["detail"] == "Bot instance not available."

# Для запуска тестов напрямую, если нужно (хотя pytest test_file.py предпочтительнее)
if __name__ == "__main__":
    pytest.main([__file__])
