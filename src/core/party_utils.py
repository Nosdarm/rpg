from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession

from models.party import Party
from core.crud.crud_party import party_crud # Specific CRUD for Party
from core.crud.crud_player import player_crud # For fetching player details if needed

async def get_party(db: AsyncSession, guild_id: int, party_id: int) -> Optional[Party]:
    """
    Retrieves a specific party by its primary ID, ensuring it belongs to the specified guild.

    :param db: The database session.
    :param guild_id: The ID of the guild.
    :param party_id: The primary key ID of the party.
    :return: The Party object or None if not found or not matching guild_id.
    """
    # CRUDBase.get() from party_crud handles filtering by primary key and guild_id
    return await party_crud.get(db, id=party_id, guild_id=guild_id)

async def get_party_by_name(db: AsyncSession, guild_id: int, name: str) -> Optional[Party]:
    """
    Retrieves a party by its name within a specific guild.
    Note: Party names might not be unique per guild; this returns the first match.
    """
    return await party_crud.get_by_name(db, guild_id=guild_id, name=name)

# Example of a more complex utility that might combine CRUD operations:
# async def get_party_with_member_details(db: AsyncSession, guild_id: int, party_id: int) -> Optional[dict]:
#     """
#     Retrieves a party and details of its members.
#     """
#     party = await party_crud.get(db, id=party_id, guild_id=guild_id)
#     if not party:
#         return None

#     member_details = []
#     if party.player_ids_json:
#         for player_pk_id in party.player_ids_json:
#             player = await player_crud.get(db, id=player_pk_id, guild_id=guild_id) # Ensure guild scope for players too
#             if player:
#                 member_details.append({"id": player.id, "name": player.name, "level": player.level})
#             else:
#                 # Handle case where a player_id in JSON doesn't match a valid player (data integrity issue)
#                 member_details.append({"id": player_pk_id, "name": "[Unknown Player]", "level": 0})

#     return {
#         "party_id": party.id,
#         "party_name": party.name,
#         "location_id": party.current_location_id,
#         "turn_status": party.turn_status.value,
#         "members": member_details
#     }

import logging
logger = logging.getLogger(__name__)
logger.info("Party utility functions defined (get_party, get_party_by_name).")
