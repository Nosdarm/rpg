# Этот файл делает директорию 'core' пакетом Python.

# Можно импортировать ключевые элементы для удобства доступа
# from .database import engine, AsyncSessionLocal, get_db_session, init_db

# __all__ = [
#     "engine",
#     "AsyncSessionLocal",
#     "get_db_session",
#     "init_db",
#     "crud",
#     "rules" # Future module
# ]

import logging

# Import modules to make them available when 'core' is imported,
# and also to allow for easier cross-module imports within 'core'.

from . import crud
from . import database
from . import rules

logger = logging.getLogger(__name__)
logger.info("Core package initialized. Loaded: crud, database, rules.")

# Define __all__ for explicit public API of the 'core' package, if desired.
# This controls what 'from core import *' imports.
__all__ = [
    "crud",
    "database",
    "rules",
]
