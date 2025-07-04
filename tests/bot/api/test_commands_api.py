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
from src.models.command_info import CommandInfo, CommandListResponse

# Фикстура для TestClient
@pytest.fixture(scope="module")
def client():
    # Можно было бы создать TestClient здесь, но чтобы мокнуть get_bot_instance до создания клиента,
    # лучше делать это в каждом тесте или через фикстуру, которая патчит до yield.
    # Но для FastAPI TestClient обычно создается один раз.
    # Мы можем мокнуть зависимость глобально для всех тестов в этом модуле, если это необходимо.
    # Или передавать app в TestClient в каждом тесте после патчинга.
    # Простой вариант:
    with TestClient(app) as c:
        yield c

# Мок для экземпляра бота, который будет возвращаться зависимостью get_bot_instance
mock_bot_instance = AsyncMock(spec=ext_commands.Bot)
mock_bot_instance.tree = AsyncMock(spec=discord.app_commands.CommandTree) # Добавляем атрибут tree

# Мокаем get_bot_instance в src.bot.api.commands_api
# Это нужно делать до того, как TestClient сделает первый запрос к эндпоинту, который использует эту зависимость.
# Лучше всего использовать pytest-mock для этого или делать это в фикстуре.

@pytest.fixture(autouse=True) # autouse=True чтобы применялось ко всем тестам в модуле
def mock_bot_dependency(mocker): # Используем mocker из pytest-mock
    # Патчим функцию get_bot_instance там, где она используется (в commands_api)
    # mocker.patch сам позаботится о восстановлении после теста
    mocker.patch("src.bot.api.commands_api.get_bot_instance", return_value=mock_bot_instance)


# Тесты для API эндпоинта /commands/
def test_list_bot_commands_success_empty(client: TestClient, mocker):
    # Мокаем get_bot_commands, чтобы вернуть пустой список
    mocked_get_commands = mocker.patch("src.bot.api.commands_api.get_bot_commands", new_callable=AsyncMock)
    mocked_get_commands.return_value = []

    response = client.get("/api/v1/commands/")
    assert response.status_code == 200
    data = response.json()
    assert data["commands"] == []
    assert data["language_code"] is None # Так как lang не передавался
    mocked_get_commands.assert_called_once_with(bot=mock_bot_instance, guild_id=None, language=None)

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
