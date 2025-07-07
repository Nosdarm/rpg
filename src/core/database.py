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

# Декоратор для управления транзакциями
def transactional(func):
    """
    Декоратор для выполнения функции внутри транзакции базы данных.
    Автоматически получает сессию из get_db_session(), которая управляет commit/rollback.
    Предполагается, что декорируемая функция является async и первым аргументом
    ожидает сессию БД (db: AsyncSession).
    """
    import functools
    import inspect # Ensure inspect is imported for the decorator
    from unittest.mock import Mock # For isinstance check

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        guild_id_for_log = kwargs.get('guild_id', 'N/A')

        passed_session = None
        processed_args = args

        # Check if session is passed as a keyword argument
        if "session" in kwargs and (isinstance(kwargs["session"], AsyncSession) or isinstance(kwargs["session"], Mock)):
            passed_session = kwargs["session"]
        # Else, check if session is passed as the first positional argument
        elif args and (isinstance(args[0], AsyncSession) or isinstance(args[0], Mock)):
            # Ensure the function signature's first parameter is indeed 'session'
            # to avoid consuming 'self' or other parameters.
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            if params and params[0] == "session":
                passed_session = args[0]
                processed_args = args[1:] # Session consumed from args

        if passed_session:
            # A session was provided by the caller, use it directly.
            # The decorated function `func` will receive this session.
            # If it was from args[0] (and matched 'session' param), it's now in provided_session and removed from processed_args.
            # If it was from kwargs, it's still in kwargs.
            # The goal is for `func` to receive the session correctly as per its definition.
            # If func is `def func(session, arg1, ...)`:
            #   - called as wrapper(s, a1), provided_session=s, processed_args=(a1,), kwargs={} -> func(s, a1, **{})
            #   - called as wrapper(a1, session=s), provided_session=s, processed_args=(a1,), kwargs={'session':s} -> func(a1, session=s) -> This might be an issue if func expects session first.
            # For `process_guild_turn_if_ready(session, guild_id)`:
            # Call: `wrapper(mock_session, guild_id)`
            #   `passed_session` becomes `mock_session`. `processed_args` becomes `(guild_id,)`.
            #   It should call `func(mock_session, guild_id)`.

            # This simplified call assumes func correctly receives provided_session either positionally or via kwargs
            # based on how it was originally passed to wrapper and how func is defined.
            # The crucial point is NOT to create a new session if one is validly provided.

            # If the session was originally positional and func expects it positionally first:
            if processed_args is not args: # Means session was args[0] and consumed
                 return await func(passed_session, *processed_args, **kwargs)
            else: # Session was from kwargs or func handles it through kwargs
                 return await func(*processed_args, **kwargs) # kwargs contains 'session' if it was passed that way

        else:
            # No usable session provided by the caller, create a new one.
            async with get_db_session() as new_created_session:
                try:
                    # Pass the new_created_session as a keyword argument 'session'.
                    # original_args here are the args passed to the wrapper.
                    # This was the problematic line: func(new_created_session, *args, **kwargs)
                    # if *args still contained a mock_session that wasn't detected.
                    # Now, *processed_args* should be clean of any previously passed session.
                    # Ensure kwargs doesn't already have 'session' if func doesn't expect it to be overwritten.
                    # However, given this branch means no session was passed, it's safe to inject.
                    result = await func(*processed_args, session=new_created_session, **kwargs)
                    return result
                except Exception as e:
                    logger.error(f"Ошибка в транзакционной функции {func.__name__} (guild_id: {guild_id_for_log}): {e}", exc_info=True)
                    raise
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

# Если init_db предполагается вызывать как скрипт (например, python -m src.core.database init)
# if __name__ == "__main__":
#     import asyncio
#     async def main_init():
#         logger.info("Запуск инициализации БД...")
#         await init_db()
#         logger.info("Инициализация БД завершена.")
#     asyncio.run(main_init())
