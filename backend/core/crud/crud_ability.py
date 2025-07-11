from typing import Optional, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.crud_base_definitions import CRUDBase
from backend.models import Ability

class CRUDAbility(CRUDBase[Ability]):
    async def get_by_static_id(
        self, db: AsyncSession, *, static_id: str, guild_id: Optional[int] = None
    ) -> Optional[Ability]:
        """
        Retrieves an ability by its static_id.
        If guild_id is provided, it first tries to find a guild-specific ability.
        If not found or guild_id is None, it tries to find a global ability (guild_id IS NULL).
        """
        stmt_guild = select(self.model).where(
            self.model.static_id == static_id,
            self.model.guild_id == guild_id
        )
        if guild_id is not None:
            res_guild = await db.execute(stmt_guild)
            instance_guild = res_guild.scalar_one_or_none()
            if instance_guild:
                return instance_guild

        stmt_global = select(self.model).where(
            self.model.static_id == static_id,
            self.model.guild_id.is_(None)
        )
        res_global = await db.execute(stmt_global)
        return res_global.scalar_one_or_none()

    async def get_multi_by_guild_id_or_global(
        self, db: AsyncSession, *, guild_id: Optional[int] = None, skip: int = 0, limit: int = 100
    ) -> Sequence[Ability]:
        """
        Retrieves multiple abilities, including global ones and those specific to the guild.
        """
        stmt = select(self.model).where(
            (self.model.guild_id == guild_id) | (self.model.guild_id.is_(None))
        ).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()


ability_crud = CRUDAbility(Ability)
