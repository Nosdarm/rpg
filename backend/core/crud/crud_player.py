from typing import Optional, List, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..crud_base_definitions import CRUDBase
from ...models.player import Player, PlayerStatus
from ..rules import get_rule # Added import for get_rule


class CRUDPlayer(CRUDBase[Player]):
    async def get_by_discord_id(
        self, session: AsyncSession, *, guild_id: int, discord_id: int
    ) -> Optional[Player]:
        """
        Get a player by their Discord ID and Guild ID.
        """
        statement = (
            select(self.model)
            .where(self.model.guild_id == guild_id, self.model.discord_id == discord_id)
        )
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def get_multi_by_location(
        self, session: AsyncSession, *, guild_id: int, location_id: int, skip: int = 0, limit: int = 100
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
        result = await session.execute(statement)
        return list(result.scalars().all())

    async def get_multi_by_party_id(
        self, session: AsyncSession, *, guild_id: int, party_id: int, skip: int = 0, limit: int = 100
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
        result = await session.execute(statement)
        return list(result.scalars().all())

    async def create_with_defaults(
        self,
        session: AsyncSession,
        *,
        guild_id: int,
        discord_id: int,
        name: str,
        current_location_id: Optional[int] = None,
        selected_language: str = "en" # Default language
    ) -> Player:
        """
        Create a new player with default values for level, xp, gold, status, and attributes.
        """
        player_data = {
            "guild_id": guild_id,
            "discord_id": discord_id,
            "name": name,
            "current_location_id": current_location_id,
            "selected_language": selected_language,
            "xp": 0,
            "level": 1, # Default, can be overridden by starting_stats
            "unspent_xp": 0,
            "gold": 0, # Default, can be overridden by starting_stats
            "hp": 100, # Default, can be overridden by starting_stats
            "current_status": PlayerStatus.EXPLORING, # As per Task 1.2 plan for /start
            # attributes_json will be populated from rules
        }

        # Get starting stats from RuleConfig
        starting_stats = await get_rule(
            session,
            guild_id=guild_id,
            key="player:starting_stats",
            default={"hp": 100, "xp": 0, "level": 1, "gold": 10, "unspent_xp": 0} # Fallback default
        )
        if starting_stats and isinstance(starting_stats, dict):
            player_data["xp"] = starting_stats.get("xp", player_data["xp"])
            player_data["level"] = starting_stats.get("level", player_data["level"])
            player_data["unspent_xp"] = starting_stats.get("unspent_xp", player_data["unspent_xp"])
            player_data["gold"] = starting_stats.get("gold", player_data["gold"])
            # 'hp' from starting_stats should set both current_hp and max_hp for a new player
            initial_hp = starting_stats.get("hp", player_data["hp"]) # player_data["hp"] has the default 100
            player_data["current_hp"] = initial_hp
            player_data["max_hp"] = initial_hp
            if "hp" in player_data: # remove the generic 'hp' key if it was set from default
                del player_data["hp"]

        # Get base attributes from RuleConfig
        base_attributes = await get_rule(
            session,
            guild_id=guild_id,
            key="character_attributes:base_values",
            default={} # Fallback default
        )
        player_data["attributes_json"] = base_attributes if isinstance(base_attributes, dict) else {}


        return await super().create(session, obj_in=player_data) # guild_id is in player_data, CRUDBase.create will use it.

    async def get_by_id_and_guild(self, session: AsyncSession, *, id: int, guild_id: int) -> Optional[Player]:
        """
        Retrieves a player by their ID and Guild ID.
        Ensures the player belongs to the specified guild.
        """
        return await self.get(session, id=id, guild_id=guild_id)

player_crud = CRUDPlayer(Player)
