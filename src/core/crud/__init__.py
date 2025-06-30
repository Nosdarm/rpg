# This file makes 'crud' a subpackage.

from .crud_location import location_crud # Example if you have specific CRUD objects
# You can also import base CRUD if needed to be exposed from here, though it's already in core.crud
# from ..crud import CRUDBase

import logging
logger = logging.getLogger(__name__)
logger.info("CRUD subpackage initialized.")

__all__ = [
    "location_crud",
]
