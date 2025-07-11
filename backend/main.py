import sys
import os
# Add the project root directory (parent of 'src') to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import asyncio
import logging
from typing import Optional # Added for bot_instance type hint
import discord
from discord.ext import commands
from fastapi import FastAPI
import uvicorn

from backend.bot.core import BotCore
from backend.config.settings import settings # Changed import
from backend.core.database import init_db
from backend.bot.api.commands_api import router as commands_api_router
from backend.api.routers.auth import router as auth_router # Импортируем новый роутер аутентификации
# Assuming command_list_router is distinct or handled by commands_api_router.
# If it's the same as commands_api_router for /api/v1/command-list, one import is fine.
# If it's a different router for that specific path, ensure it's defined and imported.
# For now, assuming commands_api_router covers command listing or it's a typo.
# If command_list_router was meant to be different:
# from backend.api.routers.command_list_api import router as command_list_router

# Настройка логирования
# Ensure LOG_LEVEL is valid for getattr, or use settings.LOG_LEVEL directly if it's already processed
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
                    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__)

# Создаем FastAPI приложение
app = FastAPI(title="Text RPG Bot API", version="0.1.0")

# Включаем роутеры API
app.include_router(commands_api_router, prefix="/api/v1", tags=["Bot Commands"]) # Covers general command listing as per its file
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"]) # Added prefix for consistency


async def run_bot(bot_instance: BotCore):
    """Запускает Discord бота."""
    assert settings.DISCORD_TOKEN is not None, "DISCORD_TOKEN cannot be None when run_bot is called"
    try:
        logger.info(f"Запуск бота с префиксом: {bot_instance.command_prefix}")
        await bot_instance.start(settings.DISCORD_TOKEN)
    except discord.LoginFailure:
        logger.error("Ошибка входа: неверный токен Discord.")
    except Exception as e:
        logger.error(f"Произошла ошибка при запуске бота: {e}", exc_info=True)
    finally:
        if not bot_instance.is_closed():
            await bot_instance.close()
        logger.info("Discord бот остановлен.")

async def run_api_server(bot_instance: BotCore):
    """Запускает FastAPI сервер с Uvicorn."""
    app.state.bot = bot_instance

    config = uvicorn.Config(app, host=settings.API_HOST, port=settings.API_PORT, log_level=settings.LOG_LEVEL.lower())
    server = uvicorn.Server(config)
    logger.info(f"Запуск FastAPI сервера на http://{settings.API_HOST}:{settings.API_PORT}")
    try:
        await server.serve()
    except asyncio.CancelledError:
        logger.info("FastAPI сервер останавливается.")
    except Exception as e:
        logger.error(f"Ошибка FastAPI сервера: {e}", exc_info=True)
    finally:
        logger.info("FastAPI сервер остановлен.")


async def main():
    """
    Главная функция для запуска Discord бота и FastAPI сервера.
    """
    if not settings.DISCORD_TOKEN:
        logger.error("Токен бота Discord не найден. Пожалуйста, установите переменную окружения DISCORD_TOKEN.")
        return

    try:
        logger.info("Попытка инициализации базы данных (создание таблиц)...")
        await init_db()
        logger.info("Инициализация базы данных успешно завершена (или таблицы уже существовали).")
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}", exc_info=True)
        logger.error("Приложение не будет запущено из-за ошибки БД. Устраните проблему и перезапустите.")
        return

    intents = discord.Intents.default()
    intents.messages = True
    intents.guilds = True
    intents.message_content = True

    bot = BotCore(command_prefix=commands.when_mentioned_or(settings.BOT_PREFIX), intents=intents)

    discord_bot_task = asyncio.create_task(run_bot(bot))
    api_server_task = asyncio.create_task(run_api_server(bot))

    done, pending = await asyncio.wait(
        [discord_bot_task, api_server_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        logger.info(f"Одна из основных задач завершилась, отменяем ожидающие задачи: {task.get_name()}")
        task.cancel()

    if pending:
        await asyncio.wait(pending, timeout=5.0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Завершение работы по команде пользователя (Ctrl+C)")
    except Exception as e:
        logger.critical(f"Неперехваченное исключение в main: {e}", exc_info=True)
    finally:
        logger.info("Приложение полностью остановлено.")
