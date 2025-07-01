from typing import Optional, List, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..crud_base_definitions import CRUDBase
from ...models.player import Player, PlayerStatus


class CRUDPlayer(CRUDBase[Player]):
    async def get_by_discord_id(
        self, db: AsyncSession, *, guild_id: int, discord_id: int
    ) -> Optional[Player]:
        """
        Get a player by their Discord ID and Guild ID.
        """
        statement = (
            select(self.model)
            .where(self.model.guild_id == guild_id, self.model.discord_id == discord_id)
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def get_multi_by_location(
        self, db: AsyncSession, *, guild_id: int, location_id: int, skip: int = 0, limit: int = 100
    ) -> List[Player]:
        """
        Get multiple players in a specific location within a guild.
        """
        statement = (
            select(self.model)
            .where(self.model.guild_id == guild_id, self.model.current_location_id == location_id)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(statement)
        return list(result.scalars().all())

    async def get_multi_by_party_id(
        self, db: AsyncSession, *, guild_id: int, party_id: int, skip: int = 0, limit: int = 100
    ) -> List[Player]:
        """
        Get multiple players belonging to a specific party within a guild.
        """
        statement = (
            select(self.model)
            .where(self.model.guild_id == guild_id, self.model.current_party_id == party_id)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(statement)
        return list(result.scalars().all())

    async def create_with_defaults(
        self,
        db: AsyncSession,
        *,
        guild_id: int,
        discord_id: int,
        name: str,
        current_location_id: Optional[int] = None,
        selected_language: str = "en" # Default language
    ) -> Player:
        """
        Create a new player with default values for level, xp, gold, status.
        """
        player_data = {
            "guild_id": guild_id,
            "discord_id": discord_id,
            "name": name,
            "current_location_id": current_location_id,
            "selected_language": selected_language,
            "xp": 0,
            "level": 1,
            "unspent_xp": 0,
            "gold": 0, # Or some starting gold if desired by game rules
            "current_status": PlayerStatus.IDLE, # Or EXPLORING
        }
        return await super().create(db, obj_in=player_data) # guild_id is in player_data, CRUDBase.create will use it.

player_crud = CRUDPlayer(Player)
