# Этот файл делает директорию 'core' пакетом Python.

# Можно импортировать ключевые элементы для удобства доступа
# from .database import engine, AsyncSessionLocal, get_db_session, init_db

# __all__ = [
#     "engine",
#     "AsyncSessionLocal",
#     "get_db_session",
#     "init_db"
# ]

# Пока оставим пустым. Импорты будут производиться напрямую из src.core.database
import logging
logger = logging.getLogger(__name__)
logger.info("Пакет core инициализирован.")
