from typing import Optional, Sequence, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.pending_conflict import PendingConflict
from ...models.enums import ConflictStatus # For filtering by status
from ..crud_base_definitions import CRUDBase # Assuming CRUDBase is in crud_base_definitions.py

import logging
logger = logging.getLogger(__name__)

class CRUDPendingConflict(CRUDBase[PendingConflict]):
    async def get_by_id_and_guild(self, session: AsyncSession, *, id: int, guild_id: int) -> Optional[PendingConflict]:
        """
        Get a specific PendingConflict by its ID and Guild ID.
        """
        stmt = select(self.model).where(self.model.id == id, self.model.guild_id == guild_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_multi_by_guild_and_status_paginated(
        self,
        session: AsyncSession,
        *,
        guild_id: int,
        status: Optional[ConflictStatus] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Sequence[PendingConflict]:
        """
        Get multiple PendingConflict records for a guild, optionally filtered by status, with pagination.
        """
        stmt = select(self.model).where(self.model.guild_id == guild_id)
        if status:
            stmt = stmt.where(self.model.status == status)
        stmt = stmt.order_by(self.model.created_at.desc()).offset(skip).limit(limit) # Order by newest first

        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_count_by_guild_and_status(
        self,
        session: AsyncSession,
        *,
        guild_id: int,
        status: Optional[ConflictStatus] = None,
    ) -> int:
        """
        Get the total count of PendingConflict records for a guild, optionally filtered by status.
        """
        from sqlalchemy import func # Import func for count

        stmt = select(func.count(self.model.id)).where(self.model.guild_id == guild_id)
        if status:
            stmt = stmt.where(self.model.status == status)

        result = await session.execute(stmt)
        count = result.scalar_one_or_none()
        return count if count is not None else 0


pending_conflict_crud = CRUDPendingConflict(PendingConflict)
logger.info("CRUDPendingConflict instance created.")
