from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import GlobalNpc # Corrected relative import
from ..crud_base_definitions import CRUDBase


class CRUDGlobalNpc(CRUDBase[GlobalNpc]):
    async def get_multi_by_guild_id(
        self, session: AsyncSession, *, guild_id: int, skip: int = 0, limit: int = 100
    ) -> Sequence[GlobalNpc]:
        result = await session.execute(
            select(self.model)
            .filter(self.model.guild_id == guild_id)
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_multi_by_guild_id_active(
        self, session: AsyncSession, *, guild_id: int, skip: int = 0, limit: int = 100
    ) -> Sequence[GlobalNpc]:
        # Placeholder: For now, "active" means all.
        # This should ideally filter based on a status in properties_json.
        # Example: .filter(self.model.properties_json["status"].astext == "active")
        # Requires properties_json to have a reliable 'status' field.
        return await self.get_multi_by_guild_id(session, guild_id=guild_id, skip=skip, limit=limit)

    async def get_multi_by_location_id(
        self, session: AsyncSession, *, guild_id: int, location_id: int, skip: int = 0, limit: int = 100
    ) -> Sequence[GlobalNpc]:
        result = await session.execute(
            select(self.model)
            .filter(self.model.guild_id == guild_id, self.model.current_location_id == location_id)
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()


global_npc_crud = CRUDGlobalNpc(GlobalNpc)
