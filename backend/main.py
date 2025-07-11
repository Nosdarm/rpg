import sys
import os
# Add the project root directory (parent of 'src') to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import asyncio
import logging
import discord
from discord.ext import commands
from fastapi import FastAPI
import uvicorn

from backend.bot.core import BotCore
from backend.config.settings import DISCORD_BOT_TOKEN, LOG_LEVEL, API_HOST, API_PORT
from backend.core.database import init_db
from backend.bot.api.commands_api import router as commands_api_router
from backend.api.routers.auth import router as auth_router # Импортируем новый роутер аутентификации
from backend.bot.api.commands_api import router as command_list_router # Импортируем новый роутер для списка команд

# Настройка логирования
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__)

# Создаем FastAPI приложение
app = FastAPI(title="Text RPG Bot API", version="0.1.0")

# Включаем роутеры API
app.include_router(commands_api_router, prefix="/api/v1", tags=["Bot Commands"])
app.include_router(auth_router) # Регистрируем роутер аутентификации
app.include_router(command_list_router, prefix="/api/v1/command-list", tags=["Command List"]) # Регистрируем новый роутер

# Глобальный экземпляр бота, чтобы FastAPI мог его использовать
# Это упрощенный подход; в более сложных сценариях можно использовать DI или другие методы.
# Важно, чтобы бот был инициализирован до того, как FastAPI попытается его использовать.
# bot_instance_global: Optional[BotCore] = None

async def run_bot(bot_instance: BotCore):
    """Запускает Discord бота."""
    assert DISCORD_BOT_TOKEN is not None, "DISCORD_BOT_TOKEN cannot be None when run_bot is called"
    try:
        logger.info(f"Запуск бота с префиксом: {bot_instance.command_prefix}")
        await bot_instance.start(DISCORD_BOT_TOKEN)
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
    # Сохраняем экземпляр бота в состоянии FastAPI приложения
    # Это позволит зависимостям FastAPI получать доступ к боту.
    app.state.bot = bot_instance

    config = uvicorn.Config(app, host=API_HOST, port=API_PORT, log_level=LOG_LEVEL.lower())
    server = uvicorn.Server(config)
    logger.info(f"Запуск FastAPI сервера на http://{API_HOST}:{API_PORT}")
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
    if not DISCORD_BOT_TOKEN:
        logger.error("Токен бота Discord не найден. Пожалуйста, установите переменную окружения DISCORD_BOT_TOKEN.")
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

    from backend.config.settings import BOT_PREFIX
    bot = BotCore(command_prefix=commands.when_mentioned_or(BOT_PREFIX), intents=intents)

    # bot_instance_global = bot # Присваиваем глобальной переменной

    # Задачи для асинхронного выполнения
    discord_bot_task = asyncio.create_task(run_bot(bot))
    api_server_task = asyncio.create_task(run_api_server(bot)) # Передаем бота в API

    # Ожидаем завершения обеих задач
    # Если одна из задач завершится (например, из-за ошибки или штатного завершения),
    # мы должны попытаться остановить и другую.
    done, pending = await asyncio.wait(
        [discord_bot_task, api_server_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        logger.info(f"Одна из основных задач завершилась, отменяем ожидающие задачи: {task.get_name()}")
        task.cancel()

    # Даем возможность отмененным задачам завершиться
    if pending:
        await asyncio.wait(pending, timeout=5.0) # Ждем не более 5 секунд


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Завершение работы по команде пользователя (Ctrl+C)")
    except Exception as e:
        logger.critical(f"Неперехваченное исключение в main: {e}", exc_info=True)
    finally:
        logger.info("Приложение полностью остановлено.")
