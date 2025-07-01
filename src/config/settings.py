import os
from dotenv import load_dotenv

# Загрузка переменных окружения из файла .env
# Это особенно полезно для локальной разработки.
# В продакшене переменные окружения обычно устанавливаются на уровне системы или хостинг-платформы.
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env') # Путь к .env в корне проекта
load_dotenv(dotenv_path=dotenv_path)

# Токен вашего Discord бота
# Получите его с Discord Developer Portal (https://discord.com/developers/applications)
DISCORD_BOT_TOKEN = os.getenv("DISCORD_TOKEN") # Changed from DISCORD_BOT_TOKEN

# Настройки логирования (можно расширить)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Настройки базы данных
# Приоритет отдается DATABASE_URL из .env файла
DATABASE_URL_ENV = os.getenv("DATABASE_URL")

if DATABASE_URL_ENV:
    DATABASE_URL = DATABASE_URL_ENV
else:
    DB_TYPE = os.getenv("DB_TYPE", "postgresql")
    DB_USER = os.getenv("USER", "postgres") # Changed from DB_USER to USER to match .env
    DB_PASSWORD = os.getenv("PASSWORD", "postgres") # Changed from DB_PASSWORD to PASSWORD to match .env
    DB_HOST = os.getenv("HOST", "localhost") # Changed from DB_HOST to HOST to match .env
    DB_PORT = os.getenv("PORT", "5432") # Changed from DB_PORT to PORT to match .env
    DB_NAME = os.getenv("DATABASE", "rpg_bot_db") # Changed from DB_NAME to DATABASE to match .env
    DATABASE_URL = f"{DB_TYPE}+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# OpenAI API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Bot config
BOT_PREFIX = os.getenv("BOT_PREFIX", "!")
BOT_LANGUAGE = os.getenv("BOT_LANGUAGE", "en")

# Secret Key
SECRET_KEY = os.getenv("SECRET_KEY")


# Проверка наличия токена и URL базы данных при импорте модуля
if not DISCORD_BOT_TOKEN:
    print("ПРЕДУПРЕЖДЕНИЕ: Переменная окружения DISCORD_TOKEN не установлена.") # Changed from DISCORD_BOT_TOKEN
    print("Пожалуйста, создайте файл .env в корне проекта и добавьте DISCORD_TOKEN=ваш_токен")
    print("Или установите переменную окружения DISCORD_TOKEN системно.")

if not DATABASE_URL_ENV and "USER" not in os.environ and "DATABASE_URL" not in os.environ: # Check if database config is missing
    print("ИНФОРМАЦИЯ: Переменные окружения для подключения к БД (DATABASE_URL или USER, PASSWORD, HOST, PORT, DATABASE) не установлены.")
    print(f"Будут использованы значения по умолчанию для сборки DATABASE_URL, ведущие к: {DATABASE_URL}")
    print("Для изменения создайте файл .env в корне проекта или установите переменные окружения системно.")

if not OPENAI_API_KEY:
    print("ПРЕДУПРЕЖДЕНИЕ: Переменная окружения OPENAI_API_KEY не установлена.")

if not SECRET_KEY:
    print("ПРЕДУПРЕЖДЕНИЕ: Переменная окружения SECRET_KEY не установлена.")


# Пример .env файла (создайте его в корне проекта, НЕ добавляйте в Git, если он содержит секреты):
"""
DISCORD_TOKEN=your_actual_bot_token_here
DATABASE_URL=postgresql+asyncpg://user:pass@host:port/dbname
# Или отдельные компоненты, если DATABASE_URL не указан:
# HOST=localhost
# PORT=5432
# DATABASE=my_rpg_bot_db
# USER=myuser
# PASSWORD=mypassword

OPENAI_API_KEY=your_openai_api_key_here
BOT_PREFIX=!
BOT_LANGUAGE=en
SECRET_KEY=your_secret_key_here

# Настройки PostgreSQL (пример)
# DB_TYPE=postgresql
# DB_USER=myuser
# DB_PASSWORD=mypassword
# DB_HOST=localhost
# DB_PORT=5432
# DB_NAME=my_rpg_bot_db

# GUILD_ID=your_guild_id_here
"""

# Список когов для загрузки ботом
# Пути указываются относительно корня проекта (где находится main.py или точка входа)
BOT_COGS = [
    "src.bot.commands", # Contains CommandCog with /ping etc.
    "src.bot.events",
    "src.bot.commands.party_commands",
    "src.bot.commands.movement_commands",
    "src.bot.commands.master_ai_commands", # New cog for AI moderation
    "src.bot.commands.turn_commands", # Cog for /end_turn and /end_party_turn
]
