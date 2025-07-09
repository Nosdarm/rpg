# src/core/__init__.py
import logging

# Initialize logger for the core module
logger = logging.getLogger(__name__)
logger.info("Core module initialization started.")

# --- Database and Base CRUD ---
from .database import Base, get_db_session, transactional, AsyncSessionLocal, engine
from .crud_base_definitions import CRUDBase, create_entity, get_entity_by_id, update_entity, delete_entity

# --- Core Utilities & Systems ---
from .rules import get_rule, update_rule_config, load_rules_config_for_guild, get_all_rules_for_guild
from .dice_roller import roll_dice
from .check_resolver import resolve_check, CheckOutcome, CheckResult, ModifierDetail # CheckError is an exception
from .localization_utils import (
    get_localized_text, get_localized_entity_name, get_batch_localized_entity_names,
    get_localized_message_template, get_localized_master_message
)
from .locations_utils import get_location_by_static_id # Other location utils might be more specific
from .player_utils import get_player
from .party_utils import get_party
from .game_events import log_event
from .report_formatter import format_turn_report
# Removed: from .command_utils import process_json_input # General utility

# --- AI Systems ---
from .ai_prompt_builder import (
    prepare_ai_prompt,
    prepare_faction_relationship_generation_prompt,
    prepare_quest_generation_prompt,
    prepare_economic_entity_generation_prompt,
    prepare_dialogue_generation_prompt # Added for Task 50
)
from .ai_response_parser import parse_and_validate_ai_response, CustomValidationError, ParsedAiData
from .ai_orchestrator import trigger_ai_generation_flow, save_approved_generation, _mock_openai_api_call, make_real_ai_call
from .ai_analysis_system import analyze_generated_content # For Task 48 (Master Tools)

# --- Game Mechanics Systems ---
from .movement_logic import execute_move_for_player_action
from .ability_system import activate_ability, apply_status, remove_status
from .combat_engine import process_combat_action
from .npc_combat_strategy import get_npc_combat_action
from .combat_cycle_manager import start_combat, process_combat_turn
from .experience_system import award_xp, spend_attribute_points
from .relationship_system import update_relationship
from .quest_system import handle_player_event_for_quest
from .trade_system import handle_trade_action # Task 44
from .global_entity_manager import simulate_global_entities_for_guild # Task 46
from .dialogue_system import generate_npc_dialogue # Added for Task 50

# --- World Generation ---
from .world_generation import (
    generate_location,
    generate_factions_and_relationships,
    generate_quests_for_guild, # Task 40
    generate_economic_entities # Task 43
)


# --- NLU and Action Processing ---
from .nlu_service import parse_player_input
from .interaction_handlers import handle_intra_location_action
from .action_processor import process_actions_for_guild # process_action is high-level
from .turn_controller import (
    process_guild_turn_if_ready, # Corrected import
    trigger_guild_turn_processing # Added for conflict resolution signaling
)
from .conflict_simulation_system import simulate_conflict_detection # For Task 48 (Master Tools)


# --- Map Management ---
from .map_management import (
    add_location_master, connect_locations_master, disconnect_locations_master
    # generate_map_for_guild, get_map_data_for_guild, # These functions do not exist in map_management.py
    # get_guild_location_details, update_location_details_master, delete_location_master # These functions do not exist in map_management.py
)


# Public API of the core module
__all__ = [
    # Database & Base CRUD
    "Base", "get_db_session", "transactional", "AsyncSessionLocal", "engine",
    "CRUDBase", "create_entity", "get_entity_by_id", "update_entity", "delete_entity",
    # Core Utilities & Systems
    "get_rule", "update_rule_config", "load_rules_config_for_guild", "get_all_rules_for_guild",
    "roll_dice",
    "resolve_check", "CheckOutcome", "CheckResult", "ModifierDetail",
    "get_localized_text", "get_localized_entity_name", "get_batch_localized_entity_names",
    "get_localized_message_template", "get_localized_master_message",
    "get_location_by_static_id",
    "get_player", "get_party",
    "log_event", "format_turn_report",
    # Removed: "process_json_input",
    # AI Systems
    "prepare_ai_prompt", "prepare_faction_relationship_generation_prompt",
    "prepare_quest_generation_prompt", "prepare_economic_entity_generation_prompt",
    "prepare_dialogue_generation_prompt",
    "parse_and_validate_ai_response", "CustomValidationError", "ParsedAiData",
    "trigger_ai_generation_flow", "save_approved_generation", "_mock_openai_api_call", "make_real_ai_call",
    "analyze_generated_content",
    # Game Mechanics Systems
    "execute_move_for_player_action",
    "activate_ability", "apply_status", "remove_status",
    "process_combat_action", "get_npc_combat_action",
    "start_combat", "process_combat_turn",
    "award_xp", "spend_attribute_points",
    "update_relationship",
    "handle_player_event_for_quest",
    "handle_trade_action",
    "simulate_global_entities_for_guild",
    "generate_npc_dialogue",
    # World Generation
    "generate_location", "generate_factions_and_relationships",
    "generate_quests_for_guild",
    "generate_economic_entities",
    # NLU and Action Processing
    "parse_player_input", "handle_intra_location_action",
    "process_actions_for_guild",
    "process_guild_turn_if_ready", # Corrected export
    "trigger_guild_turn_processing",
    "simulate_conflict_detection",
    # Map Management
    "add_location_master", "connect_locations_master", "disconnect_locations_master",
    # "generate_map_for_guild", "get_map_data_for_guild", # These functions do not exist in map_management.py
    # "get_guild_location_details", "update_location_details_master", "delete_location_master", # These functions do not exist in map_management.py
    # Dialogue System (Task 51, 52) - Placeholders for future tasks
    # "start_dialogue",
    # "handle_dialogue_input",
    # "end_dialogue",
    # "add_to_npc_memory",
    # "get_npc_memory",
]

logger.info("Core module initialized with its public API components, including Dialogue System (generate_npc_dialogue).")

# Example of how a system might be structured if it had its own sub-module directory
# from .example_system import example_function
# __all__.append("example_function")
# logger.info("Example system module loaded.")
