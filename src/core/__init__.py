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
from . import locations_utils
from . import player_utils
from . import party_utils
from . import movement_logic
from . import game_events
from . import ai_prompt_builder

logger = logging.getLogger(__name__)
logger.info("Core package initialized. Loaded: crud, database, rules, locations_utils, player_utils, party_utils, movement_logic, game_events, ai_prompt_builder.")

# Define __all__ for explicit public API of the 'core' package, if desired.
# This controls what 'from core import *' imports.
__all__ = [
    "crud",
    "database",
    "rules",
    "locations_utils",
    "player_utils",
    "party_utils",
    "movement_logic",
    "game_events",
    "ai_prompt_builder",
]
