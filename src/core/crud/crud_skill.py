from typing import Optional, Sequence

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func # Added for func.count

from .crud_base_definitions import CRUDBase
from ...models.skill import Skill


class CRUDSkill(CRUDBase[Skill]):
    async def get_by_static_id(
        self, session: AsyncSession, *, static_id: str, guild_id: Optional[int] = None
    ) -> Optional[Skill]:
        """
        Get a skill by its static_id and optionally by guild_id.
        If guild_id is None, it fetches a global skill.
        If guild_id is provided, it fetches a guild-specific skill.
        """
        statement = select(self.model).where(self.model.static_id == static_id)
        if guild_id is not None:
            statement = statement.where(self.model.guild_id == guild_id)
        else:
            statement = statement.where(self.model.guild_id.is_(None))

        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def get_multi_by_guild_or_global(
        self, session: AsyncSession, *, guild_id: Optional[int], skip: int = 0, limit: int = 100
    ) -> Sequence[Skill]:
        """
        Get multiple skills for a specific guild OR global skills.
        If guild_id is None, only global skills are fetched.
        If guild_id is provided, both guild-specific and global skills are fetched.
        """
        if guild_id is not None:
            statement = (
                select(self.model)
                .where(and_(self.model.guild_id == guild_id) | (self.model.guild_id.is_(None)))
                .offset(skip)
                .limit(limit)
                .order_by(self.model.id) # type: ignore
            )
        else: # Only global
            statement = (
                select(self.model)
                .where(self.model.guild_id.is_(None))
                .offset(skip)
                .limit(limit)
                .order_by(self.model.id) # type: ignore
            )
        result = await session.execute(statement)
        return result.scalars().all()

    async def get_all_for_guild_or_global_count(
        self, session: AsyncSession, *, guild_id: Optional[int]
    ) -> int:
        """
        Get the total count of skills for a specific guild OR global skills.
        """
        if guild_id is not None:
            statement = select(func.count(self.model.id)).where( # type: ignore
                (self.model.guild_id == guild_id) | (self.model.guild_id.is_(None))
            )
        else: # Only global
            statement = select(func.count(self.model.id)).where(self.model.guild_id.is_(None)) # type: ignore

        result = await session.execute(statement)
        count = result.scalar_one_or_none()
        return count if count is not None else 0


skill_crud = CRUDSkill(Skill)
