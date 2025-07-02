from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# --- Add this print statement ---
print(f"DEBUG: alembic/env.py: Initial sqlalchemy.url from alembic.ini (if any): {config.get_main_option('sqlalchemy.url')}")
# --- End of added print statement ---

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
# --- Изменения для интеграции с проектом ---
import os
import sys

# Добавляем путь к директории src в sys.path, чтобы Alembic мог найти модули проекта
# Это необходимо, так как alembic/env.py запускается из корневой директории проекта,
# а импорты должны быть относительно src.
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from src.config.settings import DATABASE_URL # Импортируем URL базы данных
from src.models import Base # Импортируем базовую модель из src.models.__init__

# --- Add this print statement ---
print(f"DEBUG: alembic/env.py: DATABASE_URL from src.config.settings: {DATABASE_URL}")
# --- End of added print statement ---

# Устанавливаем URL базы данных из настроек проекта
# Это переопределит sqlalchemy.url из alembic.ini
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# --- Add this print statement ---
print(f"DEBUG: alembic/env.py: Final sqlalchemy.url set for Alembic: {config.get_main_option('sqlalchemy.url')}")
# --- End of added print statement ---

target_metadata = Base.metadata
# --- Конец изменений ---

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # --- Изменения для асинхронного выполнения ---
    # Вместо синхронного engine_from_config используем наш асинхронный движок
    # из src.core.database или создаем новый на основе DATABASE_URL.
    # Для простоты здесь создадим новый, но можно импортировать существующий.
    from sqlalchemy.ext.asyncio import create_async_engine

    # Получаем URL из конфигурации (уже установлен из settings.py)
    db_url = config.get_main_option("sqlalchemy.url")
    if not db_url:
        raise ValueError("DATABASE_URL не настроен в alembic.ini или через env.py")

    # Создаем асинхронный движок
    connectable = create_async_engine(db_url, poolclass=pool.NullPool)

    async def run_async_migrations():
        """Wrapper to run migrations in an async context."""
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)

        await connectable.dispose()

    def do_run_migrations(connection):
        """Helper function to run migrations within a sync context, once connection is established."""
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Для поддержки PostgreSQL JSONB и других специфичных типов при автогенерации
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    import asyncio
    asyncio.run(run_async_migrations())
    # --- Конец изменений для асинхронного выполнения ---

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
