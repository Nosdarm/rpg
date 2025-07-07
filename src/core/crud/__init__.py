# This file makes 'crud' a subpackage.

from .crud_location import location_crud
from .crud_player import player_crud
from .crud_party import party_crud
from .crud_pending_generation import pending_generation_crud
from .crud_npc import npc_crud
from .crud_item import item_crud
from .crud_inventory_item import inventory_item_crud # Added inventory_item_crud
from .crud_ability import ability_crud
from .crud_status_effect import status_effect_crud, active_status_effect_crud
from .crud_guild import guild_crud # Added guild_crud
from .crud_combat_encounter import combat_encounter_crud
from .crud_faction import crud_faction # Added crud_faction


# You can also import base CRUD if needed to be exposed from here,
# though it's already in core.crud (parent module)
# from ..crud import CRUDBase

import logging
logger = logging.getLogger(__name__)
logger.info(
    "CRUD subpackage initialized. Loaded: location_crud, player_crud, party_crud, guild_crud, "
    "pending_generation_crud, npc_crud, item_crud, inventory_item_crud, ability_crud, "
    "status_effect_crud, active_status_effect_crud, combat_encounter_crud, crud_faction, "
    "crud_relationship, generated_quest_crud, quest_step_crud, player_quest_progress_crud, questline_crud, pending_conflict_crud, "
    "crud_crafting_recipe, skill_crud, crud_player_npc_memory, story_log_crud." # Added story_log_crud
)

__all__ = [
    "location_crud",
    "player_crud",
    "party_crud",
    "pending_generation_crud",
    "npc_crud",
    "item_crud",
    "inventory_item_crud", # Added inventory_item_crud
    "ability_crud",
    "status_effect_crud",
    "active_status_effect_crud",
    "guild_crud",
    "combat_encounter_crud",
    "crud_relationship",
    "generated_quest_crud",
    "quest_step_crud",
    "player_quest_progress_crud",
    "questline_crud",
    "crud_faction", # Added crud_faction
    "global_npc_crud", # Task 46
    "mobile_group_crud", # Task 46
    "rule_config_crud", # Added for RuleConfig
    "pending_conflict_crud", # Added for PendingConflict
    "crud_crafting_recipe", # Added for CraftingRecipe
    "skill_crud", # Added for Skill
    "crud_player_npc_memory", # Added for PlayerNpcMemory
    "story_log_crud", # Added StoryLog CRUD
]
from .crud_crafting_recipe import crud_crafting_recipe # Added for CraftingRecipe
from .crud_skill import skill_crud # Added for Skill
from .crud_player_npc_memory import crud_player_npc_memory # Added for PlayerNpcMemory
from .crud_relationship import crud_relationship
from .crud_pending_conflict import pending_conflict_crud # Added for PendingConflict
from .crud_quest import ( # Added
    generated_quest_crud,
    quest_step_crud,
    player_quest_progress_crud,
    questline_crud
)
from .crud_global_npc import global_npc_crud # Task 46
from .crud_mobile_group import mobile_group_crud # Task 46
from .crud_rule_config import rule_config_crud # For RuleConfig specific CRUD
from .crud_story_log import story_log_crud # Added StoryLog CRUD
