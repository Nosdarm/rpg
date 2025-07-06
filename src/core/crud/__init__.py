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
    "crud_relationship, generated_quest_crud, quest_step_crud, player_quest_progress_crud, questline_crud."
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
]
from .crud_relationship import crud_relationship
from .crud_quest import ( # Added
    generated_quest_crud,
    quest_step_crud,
    player_quest_progress_crud,
    questline_crud
)
