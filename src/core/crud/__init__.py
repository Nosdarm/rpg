# This file makes 'crud' a subpackage.

from .crud_location import location_crud
from .crud_player import player_crud
from .crud_party import party_crud
from .crud_pending_generation import pending_generation_crud
from .crud_npc import npc_crud
from .crud_item import item_crud
from .crud_ability import ability_crud
from .crud_status_effect import status_effect_crud, active_status_effect_crud


# You can also import base CRUD if needed to be exposed from here,
# though it's already in core.crud (parent module)
# from ..crud import CRUDBase

import logging
logger = logging.getLogger(__name__)
logger.info(
    "CRUD subpackage initialized. Loaded: location_crud, player_crud, party_crud, "
    "pending_generation_crud, npc_crud, item_crud, ability_crud, "
    "status_effect_crud, active_status_effect_crud."
)

__all__ = [
    "location_crud",
    "player_crud",
    "party_crud",
    "pending_generation_crud",
    "npc_crud",
    "item_crud",
    "ability_crud",
    "status_effect_crud",
    "active_status_effect_crud",
]
