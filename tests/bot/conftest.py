# tests/bot/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from discord.ext import commands

@pytest.fixture
def mock_bot_class() -> MagicMock: # Имя фикстуры изменено на mock_bot_class для соответствия использованию
    """Provides a mock discord.ext.commands.Bot."""
    bot = MagicMock(spec=commands.Bot)
    bot.is_owner = AsyncMock(return_value=False) # По умолчанию не владелец
    bot.user = MagicMock()
    bot.user.id = 1234567890 # ID самого бота
    # Добавьте другие атрибуты/методы бота, которые могут понадобиться в тестах команд
    # bot.get_guild = MagicMock()
    # bot.get_channel = MagicMock()
    # bot.get_user = MagicMock()
    return bot

@pytest.fixture
async def mock_db_session() -> AsyncMock: # Добавляем и сюда, если команды используют сессию напрямую
    """Provides a mock AsyncSession for bot command tests if needed."""
    session = AsyncMock(spec=AsyncSession) # Исправлено на AsyncSession
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    return session
