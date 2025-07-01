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

from . import crud_base_definitions
from . import database
from . import rules
from . import locations_utils
from . import player_utils
from . import party_utils
from . import movement_logic
from . import game_events
from . import ai_prompt_builder
from . import ai_response_parser
# Corrected import from CustomValidationError
from .ai_response_parser import parse_and_validate_ai_response, ParsedAiData, CustomValidationError
from . import ai_orchestrator
from .ai_orchestrator import trigger_ai_generation_flow, save_approved_generation
from . import nlu_service # Import the new NLU service module
from .nlu_service import parse_player_input # Import the main function
from . import turn_controller # Import the new turn_controller module
from .turn_controller import trigger_guild_turn_processing, process_guild_turn_if_ready
from . import action_processor # Import the new action_processor module
from .action_processor import process_actions_for_guild


logger = logging.getLogger(__name__)
logger.info("Core package initialized. Loaded: crud_base_definitions, database, rules, locations_utils, player_utils, party_utils, movement_logic, game_events, ai_prompt_builder, ai_response_parser, ai_orchestrator, nlu_service, turn_controller, action_processor.")

# Define __all__ for explicit public API of the 'core' package, if desired.
# This controls what 'from core import *' imports.
__all__ = [
    "crud_base_definitions", # Renamed from "crud"
    # Note: The sub-package src.core.crud is still available as src.core.crud
    "database",
    "rules",
    "locations_utils",
    "player_utils",
    "party_utils",
    "movement_logic",
    "game_events",
    "ai_prompt_builder",
    "ai_response_parser",
    "parse_and_validate_ai_response",
    "ParsedAiData",
    "CustomValidationError", # Corrected export
    "ai_orchestrator",
    "trigger_ai_generation_flow",
    "save_approved_generation",
    "nlu_service",
    "parse_player_input",
    "turn_controller",
    "trigger_guild_turn_processing",
    "process_guild_turn_if_ready", # Though this might be more internal to turn_controller logic
    "action_processor",
    "process_actions_for_guild"
]
