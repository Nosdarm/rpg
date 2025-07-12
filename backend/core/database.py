import logging
import ssl # Required for SSL context
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from urllib.parse import urlparse # For logging connection details

from ..config.settings import DATABASE_URL, DB_SSL_MODE, DB_SSL_CERT_PATH, DB_SSL_KEY_PATH, DB_SSL_ROOT_CERT_PATH
# Импортируем Base из models, чтобы init_db мог создать таблицы
from ..models.base import Base

logger = logging.getLogger(__name__)

connect_args = {}
if "asyncpg" in DATABASE_URL and DB_SSL_MODE:
    if DB_SSL_MODE == "disable":
        connect_args["ssl"] = False
        logger.info("SSL_MODE is 'disable', SSL will be disabled for asyncpg connection.")
    elif DB_SSL_MODE in ["allow", "prefer", "require", "verify-ca", "verify-full"]:
        # For "allow", "prefer", "require", asyncpg defaults to system CAs if ssl=True or ssl.create_default_context()
        # For "verify-ca", "verify-full", a more specific context is needed if custom CAs are used.

        ssl_context = ssl.create_default_context()
        if DB_SSL_MODE in ["verify-ca", "verify-full"]:
            # These modes imply server certificate verification against a CA.
            # If DB_SSL_ROOT_CERT_PATH is provided, use it. Otherwise, default context might use system CAs.
            if DB_SSL_ROOT_CERT_PATH:
                ssl_context.load_verify_locations(cafile=DB_SSL_ROOT_CERT_PATH)
                logger.info(f"SSL_MODE is '{DB_SSL_MODE}', CA certificate for verification: {DB_SSL_ROOT_CERT_PATH}")
            else:
                logger.info(f"SSL_MODE is '{DB_SSL_MODE}', using default system CA certificates for server verification.")
            ssl_context.check_hostname = DB_SSL_MODE == "verify-full" # check_hostname only for verify-full

        # Client certificate authentication (if client cert and key are provided)
        if DB_SSL_CERT_PATH and DB_SSL_KEY_PATH:
            ssl_context.load_cert_chain(DB_SSL_CERT_PATH, DB_SSL_KEY_PATH)
            logger.info(f"Client SSL certificate and key loaded for asyncpg connection: {DB_SSL_CERT_PATH}, {DB_SSL_KEY_PATH}")

        connect_args["ssl"] = ssl_context
        logger.info(f"SSL_MODE is '{DB_SSL_MODE}', SSL context configured for asyncpg connection.")
    else:
        logger.warning(f"Unsupported DB_SSL_MODE '{DB_SSL_MODE}' for asyncpg. SSL will not be configured.")

# Создаем асинхронный движок SQLAlchemy
# echo=True полезно для отладки, выводит все SQL-запросы. В продакшене лучше отключить.
# echo=False по умолчанию, если не указано. Можно сделать настраиваемым через settings.py
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args=connect_args,
    pool_pre_ping=True  # Add pool_pre_ping
)

# Создаем фабрику асинхронных сессий
# expire_on_commit=False рекомендуется для асинхронных сессий, чтобы объекты были доступны после коммита.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

from typing import AsyncGenerator
import contextlib # Import contextlib

@contextlib.asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]: # Corrected type hint
    """
    Dependency для получения асинхронной сессии базы данных.
    Используется в обработчиках запросов (например, в FastAPI).
    Гарантирует, что сессия будет закрыта после использования.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit() # Коммит транзакции, если все успешно
        except Exception:
            await session.rollback() # Откат транзакции в случае ошибки
            raise
        # finally:
            # await session.close() # session is closed by the outer 'async with AsyncSessionLocal() as session:'

import contextvars
import functools

db_session = contextvars.ContextVar('db_session')

def transactional(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        async with AsyncSessionLocal() as session:
            token = db_session.set(session)
            try:
                result = await func(*args, **kwargs)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
            finally:
                db_session.reset(token)
    return wrapper

async def init_db():
    """
    Инициализирует базу данных, создавая все таблицы на основе метаданных моделей.
    Внимание: Эту функцию следует использовать только для первоначального создания таблиц
    или в разработке. В продакшене для управления схемой БД следует использовать Alembic.
    """
    # Логирование параметров подключения (без пароля)
    from urllib.parse import urlunparse # Ensure urlunparse is available

    parsed_url_for_log = urlparse(DATABASE_URL) # DATABASE_URL already processed by settings.py

    safe_netloc_for_log = parsed_url_for_log.netloc
    if parsed_url_for_log.password:
        if parsed_url_for_log.username:
            safe_netloc_for_log = f"{parsed_url_for_log.username}:*****@{parsed_url_for_log.hostname}"
        else: # Only password, no username
            safe_netloc_for_log = f":*****@{parsed_url_for_log.hostname}"
        if parsed_url_for_log.port:
            safe_netloc_for_log += f":{parsed_url_for_log.port}"

    safe_url_for_log = urlunparse(
        (parsed_url_for_log.scheme,
         safe_netloc_for_log,
         parsed_url_for_log.path,
         parsed_url_for_log.params,
         parsed_url_for_log.query, # Query is already modified (sslmode removed if applicable)
         parsed_url_for_log.fragment)
    )
    logger.info(f"Инициализация БД с URL: {safe_url_for_log}")

    logged_connect_args = {} # Prepare for logging connect_args too
    if connect_args:
        for k, v in connect_args.items():
            if isinstance(v, ssl.SSLContext):
                logged_connect_args[k] = f"<SSLContext configured with mode: {DB_SSL_MODE}>"
            else:
                logged_connect_args[k] = v
        logger.info(f"Дополнительные параметры подключения (connect_args): {logged_connect_args}")

    async with engine.begin() as conn:
        try:
            # await conn.run_sync(Base.metadata.drop_all) # Опционально: удалить все таблицы перед созданием
            # logger.info("Старые таблицы удалены (если были).")
            # await conn.run_sync(Base.metadata.create_all) # IMPORTANT: Commented out to let Alembic manage schema
            # logger.info("Base.metadata.create_all() was previously here. Schema should be managed by Alembic.")
            logger.info("init_db completed. Schema management should be handled by Alembic.") # New log message
        except Exception as e:
            logger.error(f"Ошибка при инициализации таблиц БД ({safe_url_for_log}, connect_args: {logged_connect_args if connect_args else 'None'}): {e}", exc_info=True)
            raise

# Пример использования get_db_session (не для прямого вызова здесь, а в контексте приложения)
# async def some_function_that_uses_db():
#     async for session in get_db_session():
#         # работа с session
#         result = await session.execute(...)
#         print(result.scalars().all())
#         break # Важно, если get_db_session - генератор, который yield-ит один раз

# Если init_db предполагается вызывать как скрипт (например, python -m backend.core.database init)
# if __name__ == "__main__":
#     import asyncio
#     async def main_init():
#         logger.info("Запуск инициализации БД...")
#         await init_db()
#         logger.info("Инициализация БД завершена.")
#     asyncio.run(main_init())
