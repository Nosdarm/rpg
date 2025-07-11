import os
import logging
from typing import Optional, List, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, model_validator, Field
from urllib.parse import urlparse, parse_qs, urlunparse

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    # Pydantic V2: model_config replaces Config class
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), '..', '..', '.env'),
        env_file_encoding='utf-8',
        extra='ignore'  # Ignore extra fields from .env that are not in the model
    )

    # Discord Bot Token
    DISCORD_TOKEN: Optional[str] = None # Renamed from DISCORD_BOT_TOKEN to match .env example

    # Logging Settings
    LOG_LEVEL: str = "INFO"

    # Database Settings
    DATABASE_URL: Optional[str] = None
    DB_TYPE: str = "postgresql"
    DB_USER: Optional[str] = Field(default="postgres", alias="USER") # Alias to match .env
    DB_PASSWORD: Optional[str] = Field(default="postgres", alias="PASSWORD") # Alias to match .env
    DB_HOST: Optional[str] = Field(default="localhost", alias="HOST") # Alias to match .env
    DB_PORT: Optional[str] = Field(default="5432", alias="PORT") # Alias to match .env
    DB_NAME: Optional[str] = Field(default="rpg_bot_db", alias="DATABASE") # Alias to match .env

    DB_SSL_MODE: Optional[str] = None
    DB_SSL_CERT_PATH: Optional[str] = None
    DB_SSL_KEY_PATH: Optional[str] = None
    DB_SSL_ROOT_CERT_PATH: Optional[str] = None

    # Processed database URL and SSL mode
    PROCESSED_DATABASE_URL: str = "" # Will be set by model_validator
    EFFECTIVE_DB_SSL_MODE: Optional[str] = None # Will be set by model_validator

    # OpenAI API Key
    OPENAI_API_KEY: Optional[str] = None

    # Bot config
    BOT_PREFIX: str = "!"
    BOT_LANGUAGE: str = "en"

    # Secret Key for JWT and security
    SECRET_KEY: Optional[str] = None

    # API Server settings
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000

    # Discord OAuth2 Configuration
    DISCORD_CLIENT_ID: Optional[str] = None
    DISCORD_CLIENT_SECRET: Optional[str] = None
    DISCORD_REDIRECT_URI: Optional[str] = None
    UI_APP_REDIRECT_URL_AFTER_LOGIN: str = "http://localhost:3000/auth-callback"

    # Master User IDs
    MASTER_IDS_STR: str = Field(default="", alias="MASTER_IDS")
    MASTER_IDS_LIST: List[str] = []

    @model_validator(mode='after')
    def _process_database_settings(self) -> 'Settings':
        db_url_to_process = self.DATABASE_URL
        effective_ssl_mode = self.DB_SSL_MODE

        if db_url_to_process:
            self.PROCESSED_DATABASE_URL = db_url_to_process
            if "asyncpg" in self.PROCESSED_DATABASE_URL:
                parsed_url = urlparse(self.PROCESSED_DATABASE_URL)
                query_params = parse_qs(parsed_url.query)

                if 'sslmode' in query_params:
                    effective_ssl_mode = query_params['sslmode'][0]
                    logger.info(f"Found 'sslmode={effective_ssl_mode}' in DATABASE_URL. It will be removed from URL and processed separately.")
                    del query_params['sslmode']
                    new_query_string = "&".join(f"{k}={v[0]}" for k, v in query_params.items())
                    self.PROCESSED_DATABASE_URL = urlunparse(parsed_url._replace(query=new_query_string))

                    # For logging purposes, mask password in the original URL
                    original_parsed_url = urlparse(db_url_to_process)
                    safe_netloc_for_log = original_parsed_url.netloc
                    if original_parsed_url.password:
                        safe_netloc_for_log = f"{original_parsed_url.username or ''}:*****@{original_parsed_url.hostname}"
                        if original_parsed_url.port:
                            safe_netloc_for_log += f":{original_parsed_url.port}"
                    logged_url = urlunparse(
                        (original_parsed_url.scheme, safe_netloc_for_log, original_parsed_url.path,
                         original_parsed_url.params, new_query_string, original_parsed_url.fragment)
                    )
                    logger.info(f"DATABASE_URL (after processing sslmode, if any): {logged_url}")
        else:
            # Construct DATABASE_URL from components if DATABASE_URL is not set
            self.PROCESSED_DATABASE_URL = f"{self.DB_TYPE}+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            if self.DB_SSL_MODE: # If DB_SSL_MODE is set directly via env var
                 effective_ssl_mode = self.DB_SSL_MODE
                 logger.info(f"DB_SSL_MODE set from environment variable: {effective_ssl_mode}")

        self.EFFECTIVE_DB_SSL_MODE = effective_ssl_mode
        return self

    @field_validator('LOG_LEVEL')
    @classmethod
    def uppercase_log_level(cls, value: str) -> str:
        return value.upper()

    @field_validator('MASTER_IDS_LIST', mode='before')
    @classmethod
    def parse_master_ids(cls, value: Any, values: Any) -> List[str]:
        # This validator is a bit tricky with 'values' context in Pydantic v2
        # We'll access MASTER_IDS_STR from the raw dict 'values.data'
        master_ids_str_val = values.data.get("MASTER_IDS_STR", "") # Use alias "MASTER_IDS" if reading directly from env
        if not master_ids_str_val and "MASTER_IDS" in values.data: # Fallback to original name if alias not picked up yet
            master_ids_str_val = values.data.get("MASTER_IDS", "")

        parsed_ids = [uid.strip() for uid in master_ids_str_val.split(',') if uid.strip()]

        if not master_ids_str_val:
            logger.info("MASTER_IDS environment variable is not set. Master command authorization might be limited.")
        elif not parsed_ids:
            logger.warning("MASTER_IDS environment variable was set but resulted in an empty list.")
        else:
            logger.info(f"Loaded MASTER_IDS: {parsed_ids}")
        return parsed_ids

# Create a single settings instance
settings = Settings()

# Perform initial checks and print warnings
if not settings.DISCORD_TOKEN:
    print("WARNING: Environment variable DISCORD_TOKEN is not set.")
if not settings.PROCESSED_DATABASE_URL: # Check the processed URL
    print("WARNING: Database URL is not configured.")
elif not settings.DATABASE_URL and not settings.DB_USER: # Heuristic: if neither full URL nor components were set
    print("INFO: Database connection variables (DATABASE_URL or USER, PASSWORD, etc.) not set. Defaulting.")
    print(f"Default PROCESSED_DATABASE_URL: {settings.PROCESSED_DATABASE_URL}")

if not settings.OPENAI_API_KEY:
    print("WARNING: Environment variable OPENAI_API_KEY is not set.")
if not settings.SECRET_KEY:
    print("WARNING: Environment variable SECRET_KEY is not set. This is critical for JWT security.")
if not settings.DISCORD_CLIENT_ID:
    print("WARNING: Environment variable DISCORD_CLIENT_ID is not set (required for OAuth2).")
if not settings.DISCORD_CLIENT_SECRET:
    print("WARNING: Environment variable DISCORD_CLIENT_SECRET is not set (required for OAuth2).")
if not settings.DISCORD_REDIRECT_URI:
    print("WARNING: Environment variable DISCORD_REDIRECT_URI is not set (required for OAuth2).")

# For direct access if needed elsewhere, though 'settings.PROCESSED_DATABASE_URL' and 'settings.EFFECTIVE_DB_SSL_MODE' are preferred
DATABASE_URL = settings.PROCESSED_DATABASE_URL
DB_SSL_MODE = settings.EFFECTIVE_DB_SSL_MODE
DB_SSL_CERT_PATH = settings.DB_SSL_CERT_PATH
DB_SSL_KEY_PATH = settings.DB_SSL_KEY_PATH
DB_SSL_ROOT_CERT_PATH = settings.DB_SSL_ROOT_CERT_PATH
LOG_LEVEL = settings.LOG_LEVEL
MASTER_IDS = settings.MASTER_IDS_LIST


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
SECRET_KEY=your_very_secret_and_long_key_for_jwt_and_other_stuff # Обязательно смените на свой!

# --- Discord OAuth2 for UI Authentication ---
# Эти значения должны совпадать с настройками вашего Discord приложения на Developer Portal
# DISCORD_CLIENT_ID=your_discord_application_client_id
# DISCORD_CLIENT_SECRET=your_discord_application_client_secret
# DISCORD_REDIRECT_URI=http://localhost:8000/api/auth/discord/callback # Или ваш публичный URL

# GUILD_ID=your_guild_id_here # Пример дополнительной настройки
"""

# Список когов для загрузки ботом
# Пути указываются относительно корня проекта (где находится main.py или точка входа)
BOT_COGS = [
    "backend.bot.commands.general_commands", # Consolidated general commands (ping, start, etc.)
    "backend.bot.events",
    "backend.bot.commands.party_commands",
    "backend.bot.commands.movement_commands",
    "backend.bot.commands.master_ai_commands", # New cog for AI moderation
    "backend.bot.commands.turn_commands", # Cog for /end_turn and /end_party_turn
    # "backend.bot.commands.map_commands", # Added Map Master commands - Disabled to prevent conflict with master_map_commands
    "backend.bot.commands.master_map_commands", # Cog for Master Map Management
    "backend.bot.commands.character_commands", # Cog for character-related commands like /levelup
    # "backend.bot.commands.master_admin_commands", # Cog for Master Admin general commands - Replaced by specific cogs below
    "backend.bot.commands.master_commands.player_master_commands",
    "backend.bot.commands.master_commands.ruleconfig_master_commands",
    "backend.bot.commands.master_commands.conflict_master_commands",
    "backend.bot.commands.master_commands.party_master_commands",
    "backend.bot.commands.master_commands.npc_master_commands",
    "backend.bot.commands.master_commands.location_master_commands",
    "backend.bot.commands.master_commands.item_master_commands",
    "backend.bot.commands.master_commands.faction_master_commands",
    "backend.bot.commands.master_commands.relationship_master_commands",
    "backend.bot.commands.master_commands.quest_master_commands",
    "backend.bot.commands.master_commands.combat_master_commands",
    "backend.bot.commands.master_commands.global_npc_master_commands",
    "backend.bot.commands.master_commands.mobile_group_master_commands",
    "backend.bot.commands.master_commands.inventory_master_commands",
    "backend.bot.commands.master_commands.ability_master_commands",
    "backend.bot.commands.master_commands.status_effect_master_commands",
    "backend.bot.commands.master_commands.story_log_master_commands",
    "backend.bot.commands.master_commands.master_crafting_recipe_commands", # Added Crafting Recipe Cog
    "backend.bot.commands.master_commands.master_skill_commands", # Added Skill Cog
    "backend.bot.commands.master_commands.master_memory_commands", # Added Memory Cog
    "backend.bot.commands.master_commands.master_simulation_tools_cog", # For Task 48
    "backend.bot.commands.master_commands.monitoring_master_commands", # Added MasterMonitoringCog
    "backend.bot.commands.master_commands.pending_generation_master_commands", # Cog for Task 59
]

# Redundant MASTER_IDS parsing logic removed as it's handled by Settings.MASTER_IDS_LIST

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
