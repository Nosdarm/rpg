from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession

from models.player import Player
from core.crud.crud_player import player_crud # Specific CRUD for Player

async def get_player(db: AsyncSession, guild_id: int, player_id: int) -> Optional[Player]:
    """
    Retrieves a specific player by their primary ID, ensuring they belong to the specified guild.

    :param db: The database session.
    :param guild_id: The ID of the guild.
    :param player_id: The primary key ID of the player.
    :return: The Player object or None if not found or not matching guild_id.
    """
    # CRUDBase.get() from player_crud handles filtering by primary key and guild_id
    return await player_crud.get(db, id=player_id, guild_id=guild_id)

async def get_player_by_discord_id(db: AsyncSession, guild_id: int, discord_id: int) -> Optional[Player]:
    """
    Retrieves a specific player by their Discord ID, ensuring they belong to the specified guild.
    """
    return await player_crud.get_by_discord_id(db, guild_id=guild_id, discord_id=discord_id)

async def get_players_in_location(db: AsyncSession, guild_id: int, location_id: int, limit: int = 100) -> List[Player]:
    """
    Retrieves all players in a specific location within a guild.

    :param db: The database session.
    :param guild_id: The ID of the guild.
    :param location_id: The ID of the location.
    :param limit: Max number of players to return.
    :return: A list of Player objects.
    """
    return await player_crud.get_multi_by_location(db, guild_id=guild_id, location_id=location_id, limit=limit)

async def get_players_in_party(db: AsyncSession, guild_id: int, party_id: int, limit: int = 100) -> List[Player]:
    """
    Retrieves all players in a specific party within a guild.
    """
    return await player_crud.get_multi_by_party_id(db, guild_id=guild_id, party_id=party_id, limit=limit)

import logging
logger = logging.getLogger(__name__)
logger.info("Player utility functions defined (get_player, get_players_in_location, get_players_in_party).")
