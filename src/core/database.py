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

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Извлекаем guild_id из именованных аргументов, если он там есть.
        # Это может быть полезно для логирования или специфичных проверок на уровне декоратора,
        # хотя основная фильтрация по guild_id должна происходить в самих CRUD операциях.
        guild_id_for_log = kwargs.get('guild_id', 'N/A')

        async with get_db_session() as session: # Use async with for the async context manager
            try:
                # Передаем сессию как первый аргумент в декорируемую функцию.
                # args[0] будет сессией, если func это простой метод класса, где self - первый аргумент.
                # Если func - статическая функция или функция модуля, то session будет первым аргументом.
                # Мы предполагаем, что декорируемая функция ожидает сессию первым аргументом.

                # Если args уже содержит self или cls (если func - метод), то session должна быть вставлена после них.
                # Однако, стандартная практика - декоратор предоставляет ресурсы, такие как сессия,
                # и декорируемая функция объявляет их как свои первые параметры.
                # Пример: @transactional async def my_func(session: AsyncSession, other_arg: int): ...

                # Проверим, является ли первый аргумент 'self' или 'cls' (часто для методов класса)
                # Это упрощенная проверка. Более надежно было бы инспектировать сигнатуру func.
                # if args and isinstance(args[0], object) and func.__name__ in dir(args[0]):
                #    result = await func(args[0], session, *args[1:], **kwargs)
                # else:
                #    result = await func(session, *args, **kwargs)

                # Для простоты, предполагаем, что декорируемая функция всегда принимает сессию первым аргументом.
                # Если это метод класса, то сигнатура должна быть def my_method(self, session: AsyncSession, ...).
                # Декоратор тогда должен вызываться как @transactional на методе.
                # В wrapper args[0] будет self.
                # Чтобы передать сессию, нам нужно ее вставить.

                # Более корректный подход: декорируемая функция должна ЯВНО принимать сессию.
                # @transactional
                # async def some_function(session: AsyncSession, guild_id: int): ...
                # wrapper вызовет some_function(session_instance, guild_id=123)

                # В нашем случае, get_db_session() является генератором, который yield-ит сессию.
                # Декоратор должен передать эту сессию в func.

                # Если func это метод экземпляра, то args[0] это self.
                # В этом случае, мы передаем session как второй аргумент.
                # Если func это обычная функция, args будет пустым (или содержать другие аргументы).
                # Мы передаем session как первый аргумент.

                # Давайте стандартизируем: декорируемая функция ДОЛЖНА принимать сессию первым аргументом.
                # Если это метод класса, его сигнатура должна быть: async def method(self, session: AsyncSession, ...)
                # Декоратор будет передавать сессию после self.

                is_method = False
                if args:
                    # Простая эвристика: если первый арг есть и имя функции есть в его атрибутах
                    # Это может быть не всегда точно, но для простоты пока так.
                    # Лучше использовать inspect.signature(func) для определения первого параметра.
                    first_arg_is_class_instance = hasattr(args[0], func.__name__)
                    # Если func это unbound method класса, то args[0] это self.
                    # Если func это bound method экземпляра, то args[0] это self.
                    # Если func это staticmethod, то args не будет содержать self/cls.
                    # Если func это classmethod, то args[0] это cls.

                    # Для простоты, если есть args, предполагаем, что первый - это self/cls
                    # и сессия должна быть вставлена после него.
                    # Это не самый надежный способ, но для начала сойдет.
                    # В идеале, декорируемая функция должна явно принимать 'session' как аргумент.
                    # Мы же будем внедрять сессию в вызов.
                    pass # Мы передадим сессию как первый аргумент, а *args последуют за ним.

                # Передаем сессию как первый аргумент, за которым следуют остальные аргументы.
                # Если func - это метод, то args[0] - это self/cls.
                # Мы должны передать (self, session, *original_args_after_self, **kwargs)
                # Если func - обычная функция, то (session, *original_args, **kwargs)

                # Самый простой и явный способ - это если декорируемая функция
                # явно объявляет сессию как один из своих аргументов (например, первый).
                # Декоратор тогда просто передает ее.

                # В нашем случае, мы передаем сессию первым аргументом в вызов func.
                # Если func - это метод экземпляра (например, MyClass.my_method),
                # то Python автоматически передаст 'self' первым.
                # Если мы сделаем func(session, *args, **kwargs), то для метода это будет:
                # MyClass.my_method(session_obj, self_obj, ...other_args...) -> Ошибка
                # Если это bound method, то self уже "встроен".
                # my_instance.my_method(session_obj, ...other_args...)

                # Чтобы было универсально, функция, которую мы декорируем, должна
                # принимать сессию как первый аргумент *после* self/cls, если они есть.
                # Либо, если это функция модуля, то просто первым аргументом.

                # Давайте придерживаться соглашения:
                # - Для функций модуля: async def my_func(session: AsyncSession, ...)
                # - Для методов класса: async def my_method(self, session: AsyncSession, ...)
                # Декоратор будет внедрять сессию.

                # wrapper(self, *args, **kwargs) если func - метод
                # wrapper(*args, **kwargs) если func - функция
                # Мы получаем *args и **kwargs как они были переданы обернутой функции.

                # Если func - это метод, то args[0] - это self.
                if args and hasattr(args[0], func.__name__) and callable(getattr(args[0], func.__name__)):
                    # Вероятно, это вызов метода: instance.method(arg1, kwarg1=...)
                    # args = (self, arg1)
                    result = await func(args[0], session, *args[1:], **kwargs)
                else:
                    # Вероятно, это вызов обычной функции: module_function(arg1, kwarg1=...)
                    # args = (arg1,)
                    result = await func(session, *args, **kwargs)

                # session.commit() уже вызывается в get_db_session при успешном выходе из блока try
                return result
            except Exception as e:
                # session.rollback() уже вызывается в get_db_session при исключении
                logger.error(f"Ошибка в транзакционной функции {func.__name__} (guild_id: {guild_id_for_log}): {e}", exc_info=True)
                raise
            # finally: session.close() также обрабатывается в get_db_session
    return wrapper

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
