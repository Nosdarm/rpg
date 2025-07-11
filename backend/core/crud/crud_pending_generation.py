from backend.core.crud_base_definitions import CRUDBase
from backend.models import PendingGeneration

from sqlalchemy.ext.asyncio import AsyncSession # Added import
from sqlalchemy import select, func, and_, not_ # Added imports
from typing import List # Added import
from ...models.enums import ModerationStatus # Added import

class CRUDPendingGeneration(CRUDBase[PendingGeneration]):
    async def count_other_active_pending_for_user(
        self,
        session: AsyncSession,
        *,
        guild_id: int,
        user_id: int,
        exclude_pending_generation_id: int,
        statuses: List[ModerationStatus]
    ) -> int:
        """
        Counts other PendingGeneration records for a user that are in one of the specified statuses,
        excluding a specific PendingGeneration ID.
        """
        stmt = (
            select(func.count(self.model.id))
            .where(
                and_(
                    self.model.guild_id == guild_id,
                    self.model.triggered_by_user_id == user_id,
                    not_(self.model.id == exclude_pending_generation_id),
                    self.model.status.in_(statuses)
                )
            )
        )
        result = await session.execute(stmt)
        count = result.scalar_one_or_none()
        return count if count is not None else 0

pending_generation_crud = CRUDPendingGeneration(PendingGeneration)
