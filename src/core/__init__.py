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
from .ai_response_parser import parse_and_validate_ai_response, ParsedAiData, CustomValidationError, ParsedLocationData
from . import ai_orchestrator
from .ai_orchestrator import trigger_ai_generation_flow, save_approved_generation, generate_narrative
from . import nlu_service # Import the new NLU service module
from .nlu_service import parse_player_input # Import the main function
from . import turn_controller # Import the new turn_controller module
from .turn_controller import trigger_guild_turn_processing, process_guild_turn_if_ready
from . import action_processor # Import the new action_processor module
from .action_processor import process_actions_for_guild
from . import interaction_handlers # Import the new interaction_handlers module
from .interaction_handlers import handle_intra_location_action
from .game_events import log_event, on_enter_location # Make specific functions available
from . import localization_utils # Import new localization utils
from .localization_utils import get_localized_entity_name, get_localized_text, get_batch_localized_entity_names # Make specific functions available
from . import report_formatter # Import new report formatter
# format_log_entry is now internal, only format_turn_report is public
from .report_formatter import format_turn_report
from . import ability_system # Import the new ability_system module
from .ability_system import activate_ability, apply_status, remove_status # Import public functions
from . import world_generation # Added new module
from .world_generation import generate_location # Updated function name
from . import map_management # Import the map_management module
from .map_management import add_location_master, remove_location_master, connect_locations_master, disconnect_locations_master # Import specific functions
from . import combat_engine # Import the new combat_engine module
from .combat_engine import process_combat_action # Import the main function
from ..models.combat_outcomes import CombatActionResult # Import the Pydantic model


logger = logging.getLogger(__name__)
logger.info("Core package initialized. Loaded: crud_base_definitions, database, rules, locations_utils, player_utils, party_utils, movement_logic, game_events, ai_prompt_builder, ai_response_parser, ai_orchestrator, nlu_service, turn_controller, action_processor, interaction_handlers, localization_utils, report_formatter, ability_system, world_generation, map_management, combat_engine.")

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
    "ParsedLocationData", # Added
    "CustomValidationError", # Corrected export
    "ai_orchestrator",
    "trigger_ai_generation_flow",
    "save_approved_generation",
    "generate_narrative", # Added new function
    "nlu_service",
    "parse_player_input",
    "turn_controller",
    "trigger_guild_turn_processing",
    "process_guild_turn_if_ready", # Though this might be more internal to turn_controller logic
    "action_processor",
    "process_actions_for_guild",
    # "ACTION_DISPATCHER", # Should be internal to action_processor
    "interaction_handlers",
    "handle_intra_location_action",
    "log_event", # Added from game_events
    "on_enter_location", # Added from game_events
    "localization_utils",
    "get_localized_entity_name",
    "get_localized_text", # Also exported from localization_utils
    "get_batch_localized_entity_names", # Added
    "report_formatter",
    # "format_log_entry", # This is now an internal helper _format_log_entry_with_names_cache
    "format_turn_report",
    "ability_system",
    "activate_ability",
    "apply_status",
    "remove_status",
    "world_generation",
    "generate_location", # Updated function name
    "map_management", # Added
    "add_location_master", # Added
    "remove_location_master", # Added
    "connect_locations_master", # Added
    "disconnect_locations_master", # Added
    "combat_engine",
    "process_combat_action",
    "CombatActionResult" # Export the Pydantic model as well
]
