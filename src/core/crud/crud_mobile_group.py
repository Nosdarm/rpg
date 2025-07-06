from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import MobileGroup # Corrected relative import
from ..crud_base_definitions import CRUDBase


class CRUDMobileGroup(CRUDBase[MobileGroup]):
    async def get_multi_by_guild_id(
        self, session: AsyncSession, *, guild_id: int, skip: int = 0, limit: int = 100
    ) -> Sequence[MobileGroup]:
        result = await session.execute(
            select(self.model)
            .filter(self.model.guild_id == guild_id)
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_multi_by_guild_id_active(
        self, session: AsyncSession, *, guild_id: int, skip: int = 0, limit: int = 100
    ) -> Sequence[MobileGroup]:
        # Placeholder: For now, "active" means all.
        # This should ideally filter based on a status in properties_json.
        return await self.get_multi_by_guild_id(session, guild_id=guild_id, skip=skip, limit=limit)

    async def get_multi_by_location_id(
        self, session: AsyncSession, *, guild_id: int, location_id: int, skip: int = 0, limit: int = 100
    ) -> Sequence[MobileGroup]:
        result = await session.execute(
            select(self.model)
            .filter(self.model.guild_id == guild_id, self.model.current_location_id == location_id)
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()


mobile_group_crud = CRUDMobileGroup(MobileGroup)
