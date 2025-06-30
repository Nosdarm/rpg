# This file makes 'crud' a subpackage.

from .crud_location import location_crud
from .crud_player import player_crud
from .crud_party import party_crud

# You can also import base CRUD if needed to be exposed from here,
# though it's already in core.crud (parent module)
# from ..crud import CRUDBase

import logging
logger = logging.getLogger(__name__)
logger.info("CRUD subpackage initialized. Loaded: location_crud, player_crud, party_crud.")

__all__ = [
    "location_crud",
    "player_crud",
    "party_crud",
]
