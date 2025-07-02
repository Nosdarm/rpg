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
import logging # Added for logging
logger = logging.getLogger(__name__) # Added for logging

# Настройки базы данных
# Приоритет отдается DATABASE_URL из .env файла
DATABASE_URL_ENV = os.getenv("DATABASE_URL")
DB_SSL_MODE = None
DB_SSL_CERT_PATH = os.getenv("DB_SSL_CERT_PATH")
DB_SSL_KEY_PATH = os.getenv("DB_SSL_KEY_PATH")
DB_SSL_ROOT_CERT_PATH = os.getenv("DB_SSL_ROOT_CERT_PATH")


if DATABASE_URL_ENV:
    DATABASE_URL = DATABASE_URL_ENV
    # Парсинг sslmode из DATABASE_URL для asyncpg
    if "asyncpg" in DATABASE_URL:
        from urllib.parse import urlparse, parse_qs, urlunparse
        parsed_url = urlparse(DATABASE_URL)
        query_params = parse_qs(parsed_url.query)

        if 'sslmode' in query_params:
            DB_SSL_MODE = query_params['sslmode'][0]
            logger.info(f"Найден 'sslmode={DB_SSL_MODE}' в DATABASE_URL. Он будет удален из URL и обработан отдельно для asyncpg.")
            # Удаляем sslmode из query_params для asyncpg, так как он передается через connect_args
            del query_params['sslmode']
            # Собираем URL обратно без sslmode
            # urlunparse требует кортеж из 6 элементов: scheme, netloc, path, params, query, fragment
            # Нам нужно обновить только query. parse_qs возвращает значения как списки.
            # Мы должны преобразовать их обратно в строку запроса.
            new_query_string = "&".join([f"{k}={v[0]}" for k_list in query_params.values() for k in k_list for v in query_params.get(k, [])])
            # Corrected new_query_string construction to handle multiple values for a key if that edge case arose, though unlikely for sslmode.
            # A more standard way for typical query strings (key=value&key2=value2):
            new_query_string = "&".join(f"{k}={v[0]}" for k, v in query_params.items())


            # Update the actual DATABASE_URL first (without sslmode in query)
            DATABASE_URL = urlunparse(parsed_url._replace(query=new_query_string))

            # Now, create a version for logging with masked password
            # Re-parse the *original* URL to get all parts, especially netloc with password
            original_parsed_url = urlparse(DATABASE_URL_ENV) # Use the original URL from env

            safe_netloc_for_log = original_parsed_url.netloc
            if original_parsed_url.password:
                if original_parsed_url.username:
                    safe_netloc_for_log = f"{original_parsed_url.username}:*****@{original_parsed_url.hostname}"
                else: # Only password, no username (e.g. postgresql://:password@host/db)
                    safe_netloc_for_log = f":*****@{original_parsed_url.hostname}"
                if original_parsed_url.port:
                    safe_netloc_for_log += f":{original_parsed_url.port}"

            # Construct the logged URL using parts from original_parsed_url, but with new_query_string (sslmode removed)
            # and safe_netloc_for_log.
            logged_url = urlunparse(
                (original_parsed_url.scheme,
                 safe_netloc_for_log,
                 original_parsed_url.path,
                 original_parsed_url.params,
                 new_query_string, # Query string without sslmode
                 original_parsed_url.fragment)
            )
            logger.info(f"DATABASE_URL (после обработки sslmode, если был): {logged_url}")

else:
    DB_TYPE = os.getenv("DB_TYPE", "postgresql")
    DB_USER = os.getenv("USER", "postgres") # Changed from DB_USER to USER to match .env
    DB_PASSWORD = os.getenv("PASSWORD", "postgres") # Changed from DB_PASSWORD to PASSWORD to match .env
    DB_HOST = os.getenv("HOST", "localhost") # Changed from DB_HOST to HOST to match .env
    DB_PORT = os.getenv("PORT", "5432") # Changed from DB_PORT to PORT to match .env
    DB_NAME = os.getenv("DATABASE", "rpg_bot_db") # Changed from DB_NAME to DATABASE to match .env
    DATABASE_URL = f"{DB_TYPE}+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    # Если DATABASE_URL не задан, но есть переменные для SSL, их можно использовать
    # Например, DB_SSL_MODE может быть установлен напрямую через переменную окружения
    if os.getenv("DB_SSL_MODE"):
        DB_SSL_MODE = os.getenv("DB_SSL_MODE")
        logger.info(f"DB_SSL_MODE установлен из переменной окружения: {DB_SSL_MODE}")


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

# --- Database Configuration ---
# Вариант 1: Указать полный DATABASE_URL.
# ВАЖНО для asyncpg: НЕ включайте параметр ?sslmode=... в URL.
# Вместо этого используйте переменную DB_SSL_MODE ниже.
DATABASE_URL=postgresql+asyncpg://user:pass@host:port/dbname

# Вариант 2: Указать компоненты БД отдельно (если DATABASE_URL не указан).
# DB_TYPE=postgresql
# DB_USER=myuser
# DB_PASSWORD=mypassword
# DB_HOST=localhost
# DB_PORT=5432
# DB_NAME=my_rpg_bot_db

# --- SSL Configuration for Database (asyncpg) ---
# Используйте эту переменную для управления SSL соединением с PostgreSQL через asyncpg.
# Возможные значения:
#   disable   - Не использовать SSL.
#   allow     - Пытаться использовать SSL, но разрешить соединение без SSL, если сервер не поддерживает.
#   prefer    - Пытаться использовать SSL, но разрешить соединение без SSL, если сервер не поддерживает. (Поведение как 'allow' для asyncpg)
#   require   - Требовать SSL. Соединение не будет установлено, если сервер не поддерживает SSL. Проверка сертификата сервера не производится (если не указаны CA).
#   verify-ca - Требовать SSL и проверять сертификат сервера по известным CA.
#   verify-full - Требовать SSL, проверять сертификат сервера по известным CA и что имя хоста сервера совпадает с именем в сертификате.
# Если DATABASE_URL содержит ?sslmode=..., это значение будет извлечено и использовано здесь, а из URL удалено.
# DB_SSL_MODE=require

# Опциональные пути к SSL файлам (если требуются для 'verify-ca', 'verify-full' или клиентской аутентификации):
# DB_SSL_ROOT_CERT_PATH=/path/to/server-ca.pem  # Путь к файлу корневого сертификата CA для проверки сервера
# DB_SSL_CERT_PATH=/path/to/client-cert.pem    # Путь к файлу SSL сертификата клиента
# DB_SSL_KEY_PATH=/path/to/client-key.pem      # Путь к файлу закрытого ключа клиента

# --- Other Configurations ---
OPENAI_API_KEY=your_openai_api_key_here
BOT_PREFIX=!
BOT_LANGUAGE=en
SECRET_KEY=your_secret_key_here

# GUILD_ID=your_guild_id_here # Пример дополнительной настройки
"""

# Список когов для загрузки ботом
# Пути указываются относительно корня проекта (где находится main.py или точка входа)
BOT_COGS = [
    "src.bot.general_commands", # БЫЛ "src.bot.commands" - содержит CommandCog с /ping etc.
    "src.bot.events",
    "src.bot.commands.party_commands",
    "src.bot.commands.movement_commands",
    "src.bot.commands.master_ai_commands", # New cog for AI moderation
    "src.bot.commands.turn_commands", # Cog for /end_turn and /end_party_turn
    "src.bot.commands.map_commands", # Added Map Master commands
]

# Master User IDs - comma-separated string in .env, parsed into a list here
MASTER_IDS_STR = os.getenv("MASTER_IDS", "")
MASTER_IDS = [uid.strip() for uid in MASTER_IDS_STR.split(',') if uid.strip()]
if not MASTER_IDS_STR: # Проверяем исходную строку, чтобы не логировать пустоту, если переменная вообще не задана
    logger.info("MASTER_IDS environment variable is not set. Master command authorization might be limited to server admins/bot owners.")
elif not MASTER_IDS: # Если строка была, но оказалась пустой после split/strip
    logger.warning("MASTER_IDS environment variable was set but resulted in an empty list (e.g., just commas or whitespace). Master command authorization might be limited.")
else:
    logger.info(f"Loaded MASTER_IDS: {MASTER_IDS}")


# Константы для команды /start и создания игрока по умолчанию
DEFAULT_STARTING_LOCATION_STATIC_ID = "town_square" # Пример ID стартовой локации
DEFAULT_PLAYER_START_PARAMS_JSON = {
    "level": 1,
    "experience": 0,
    "health": 100,
    "max_health": 100,
    "mana": 50,
    "max_mana": 50,
    "attributes": {
        "strength": 10,
        "dexterity": 10,
        "constitution": 10,
        "intelligence": 10,
        "wisdom": 10,
        "charisma": 10
    },
    "inventory": [],
    "equipment": {},
    "gold": 25
}
