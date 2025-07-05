from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.generated_faction import GeneratedFaction
from ..crud_base_definitions import CRUDBase


class CRUDFaction(CRUDBase[GeneratedFaction]):
    async def get_by_static_id(
        self, db: AsyncSession, *, guild_id: int, static_id: str
    ) -> Optional[GeneratedFaction]:
        """
        Retrieves a faction by its static_id and guild_id.
        """
        statement = select(self.model).where(
            self.model.guild_id == guild_id, self.model.static_id == static_id
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def get_multi_by_guild_id(
        self, db: AsyncSession, *, guild_id: int, skip: int = 0, limit: int = 100
    ) -> Sequence[GeneratedFaction]:
        """
        Retrieves multiple factions for a specific guild.
        """
        statement = (
            select(self.model)
            .where(self.model.guild_id == guild_id)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(statement)
        return result.scalars().all()


crud_faction = CRUDFaction(GeneratedFaction)
