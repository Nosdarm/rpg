from typing import Optional, Sequence

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from ..crud_base_definitions import CRUDBase
from ...models.player_npc_memory import PlayerNpcMemory


class CRUDPlayerNpcMemory(CRUDBase[PlayerNpcMemory]):
    async def get_multi_by_player_and_npc(
        self,
        session: AsyncSession,
        *,
        guild_id: int,
        player_id: int,
        npc_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> Sequence[PlayerNpcMemory]:
        """
        Get multiple memory entries for a specific player-NPC pair within a guild.
        """
        statement = (
            select(self.model)
            .where(
                self.model.guild_id == guild_id,
                self.model.player_id == player_id,
                self.model.npc_id == npc_id
            )
            .offset(skip)
            .limit(limit)
            .order_by(self.model.timestamp.desc()) # type: ignore
        )
        result = await session.execute(statement)
        return result.scalars().all()

    async def get_multi_by_player(
        self,
        session: AsyncSession,
        *,
        guild_id: int,
        player_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> Sequence[PlayerNpcMemory]:
        statement = (
            select(self.model)
            .where(
                self.model.guild_id == guild_id,
                self.model.player_id == player_id
            )
            .offset(skip)
            .limit(limit)
            .order_by(self.model.npc_id, self.model.timestamp.desc()) # type: ignore
        )
        result = await session.execute(statement)
        return result.scalars().all()

    async def get_multi_by_npc(
        self,
        session: AsyncSession,
        *,
        guild_id: int,
        npc_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> Sequence[PlayerNpcMemory]:
        statement = (
            select(self.model)
            .where(
                self.model.guild_id == guild_id,
                self.model.npc_id == npc_id
            )
            .offset(skip)
            .limit(limit)
            .order_by(self.model.player_id, self.model.timestamp.desc()) # type: ignore
        )
        result = await session.execute(statement)
        return result.scalars().all()

    async def get_count_for_filters(
        self,
        session: AsyncSession,
        *,
        guild_id: int,
        player_id: Optional[int] = None,
        npc_id: Optional[int] = None,
        event_type: Optional[str] = None
    ) -> int:
        conditions = [self.model.guild_id == guild_id]
        if player_id is not None:
            conditions.append(self.model.player_id == player_id)
        if npc_id is not None:
            conditions.append(self.model.npc_id == npc_id)
        if event_type is not None:
            conditions.append(self.model.event_type == event_type)

        statement = select(func.count(self.model.id)).where(and_(*conditions)) # type: ignore
        result = await session.execute(statement)
        count = result.scalar_one_or_none()
        return count if count is not None else 0


crud_player_npc_memory = CRUDPlayerNpcMemory(PlayerNpcMemory)
