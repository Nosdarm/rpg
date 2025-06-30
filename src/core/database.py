import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from config.settings import DATABASE_URL
# Импортируем Base из models, чтобы init_db мог создать таблицы
from models.base import Base

logger = logging.getLogger(__name__)

# Создаем асинхронный движок SQLAlchemy
# echo=True полезно для отладки, выводит все SQL-запросы. В продакшене лучше отключить.
# echo=False по умолчанию, если не указано. Можно сделать настраиваемым через settings.py
engine = create_async_engine(DATABASE_URL, echo=False)

# Создаем фабрику асинхронных сессий
# expire_on_commit=False рекомендуется для асинхронных сессий, чтобы объекты были доступны после коммита.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db_session() -> AsyncSession:
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
        finally:
            await session.close() # Закрытие сессии

async def init_db():
    """
    Инициализирует базу данных, создавая все таблицы на основе метаданных моделей.
    Внимание: Эту функцию следует использовать только для первоначального создания таблиц
    или в разработке. В продакшене для управления схемой БД следует использовать Alembic.
    """
    async with engine.begin() as conn:
        try:
            # await conn.run_sync(Base.metadata.drop_all) # Опционально: удалить все таблицы перед созданием
            # logger.info("Старые таблицы удалены (если были).")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Таблицы успешно созданы на основе метаданных моделей.")
        except Exception as e:
            logger.error(f"Ошибка при инициализации таблиц БД: {e}", exc_info=True)
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
