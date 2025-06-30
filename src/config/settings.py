import os
from dotenv import load_dotenv

# Загрузка переменных окружения из файла .env
# Это особенно полезно для локальной разработки.
# В продакшене переменные окружения обычно устанавливаются на уровне системы или хостинг-платформы.
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env') # Путь к .env в корне проекта
load_dotenv(dotenv_path=dotenv_path)

# Токен вашего Discord бота
# Получите его с Discord Developer Portal (https://discord.com/developers/applications)
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# ID вашего сервера Discord (опционально, может использоваться для специфичных команд)
# GUILD_ID = os.getenv("GUILD_ID")
# Если GUILD_ID нужен как число:
# GUILD_ID = int(os.getenv("GUILD_ID")) if os.getenv("GUILD_ID") else None


# Настройки базы данных (будут добавлены в задаче 0.2)
# DB_TYPE = os.getenv("DB_TYPE", "postgresql") # Например, postgresql или mysql
# DB_USER = os.getenv("DB_USER", "user")
# DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
# DB_HOST = os.getenv("DB_HOST", "localhost")
# DB_PORT = os.getenv("DB_PORT", "5432")
# DB_NAME = os.getenv("DB_NAME", "rpg_bot_db")

# DATABASE_URL = f"{DB_TYPE}+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
# Пример для PostgreSQL с asyncpg. Для других СУБД строка подключения будет отличаться.


# Настройки логирования (можно расширить)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Настройки базы данных
DB_TYPE = os.getenv("DB_TYPE", "postgresql")
DB_USER = os.getenv("DB_USER", "postgres") # Стандартный пользователь для локального PostgreSQL
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres") # Пароль по умолчанию или ваш пароль
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "rpg_bot_db")

# Строка подключения к базе данных SQLAlchemy
# Для asyncpg используется формат: postgresql+asyncpg://user:password@host:port/dbname
DATABASE_URL = f"{DB_TYPE}+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Проверка наличия токена и URL базы данных при импорте модуля
if not DISCORD_BOT_TOKEN:
    print("ПРЕДУПРЕЖДЕНИЕ: Переменная окружения DISCORD_BOT_TOKEN не установлена.")
    print("Пожалуйста, создайте файл .env в корне проекта и добавьте DISCORD_BOT_TOKEN=ваш_токен")
    print("Или установите переменную окружения DISCORD_BOT_TOKEN системно.")

if "DB_USER" not in os.environ: # Проверяем наличие хотя бы одной переменной БД, чтобы не спамить если .env нет
    print("ИНФОРМАЦИЯ: Переменные окружения для подключения к БД (DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME) не установлены.")
    print(f"Будут использованы значения по умолчанию, ведущие к DATABASE_URL: {DATABASE_URL}")
    print("Для изменения создайте файл .env в корне проекта или установите переменные окружения системно.")


# Пример .env файла (создайте его в корне проекта, НЕ добавляйте в Git, если он содержит секреты):
"""
DISCORD_BOT_TOKEN=your_actual_bot_token_here

# Настройки PostgreSQL (пример)
# DB_TYPE=postgresql
# DB_USER=myuser
# DB_PASSWORD=mypassword
# DB_HOST=localhost
# DB_PORT=5432
# DB_NAME=my_rpg_bot_db

# GUILD_ID=your_guild_id_here
"""
