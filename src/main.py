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

from src.bot.core import BotCore
from src.config.settings import DISCORD_BOT_TOKEN, LOG_LEVEL # Добавлен LOG_LEVEL
from src.core.database import init_db # Импортируем init_db

# Настройка логирования
# Уровень логирования теперь берется из настроек
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__)

async def main():
    """
    Главная функция для запуска бота.
    """
    if not DISCORD_BOT_TOKEN:
        logger.error("Токен бота Discord не найден. Пожалуйста, установите переменную окружения DISCORD_BOT_TOKEN.")
        return

    # Инициализация базы данных (создание таблиц, если их нет)
    # ВАЖНО: В продакшене это должно быть заменено на Alembic миграции.
    # Эту строку можно закомментировать после первого успешного запуска
    # или если вы управляете схемой через Alembic.
    try:
        logger.info("Попытка инициализации базы данных (создание таблиц)...")
        await init_db()
        logger.info("Инициализация базы данных успешно завершена (или таблицы уже существовали).")
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}", exc_info=True)
        logger.error("Бот не будет запущен из-за ошибки БД. Устраните проблему и перезапустите.")
        return


    intents = discord.Intents.default()
    intents.messages = True  # Необходимо для on_message
    intents.guilds = True    # Необходимо для on_guild_join/remove
    intents.message_content = True # Необходимо для чтения содержимого сообщений (если бот будет это делать)

    # Используем BOT_PREFIX из настроек
    from src.config.settings import BOT_PREFIX
    bot_instance = BotCore(command_prefix=commands.when_mentioned_or(BOT_PREFIX), intents=intents)

    try:
        logger.info(f"Запуск бота с префиксом: {BOT_PREFIX}") # Обновлено для отображения префикса
        await bot_instance.start(DISCORD_BOT_TOKEN)
    except discord.LoginFailure:
        logger.error("Ошибка входа: неверный токен Discord.")
        return # Explicit return
    except Exception as e:
        logger.error(f"Произошла ошибка при запуске бота: {e}")
        return # Explicit return
    finally:
        if not bot_instance.is_closed(): # Ensure bot_instance is defined before using
            await bot_instance.close()
        logger.info("Бот остановлен.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Завершение работы по команде пользователя (Ctrl+C)")
