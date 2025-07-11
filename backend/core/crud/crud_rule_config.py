from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import RuleConfig # Adjusted import from ...models
from ..crud_base_definitions import CRUDBase


class CRUDRuleConfig(CRUDBase[RuleConfig]):
    async def get_by_key(
        self, session: AsyncSession, *, guild_id: int, key: str
    ) -> Optional[RuleConfig]:
        result = await session.execute(
            select(self.model).filter(self.model.guild_id == guild_id, self.model.key == key)
        )
        return result.scalars().first()

    async def get_multi_by_guild_id(
        self, session: AsyncSession, *, guild_id: int, skip: int = 0, limit: int = 1000 # Increased limit for rules
    ) -> Sequence[RuleConfig]:
        result = await session.execute(
            select(self.model)
            .filter(self.model.guild_id == guild_id)
            .order_by(self.model.key) # Optional: order by key
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    # Add create_or_update method if rules are managed this way
    async def create_or_update(
        self, session: AsyncSession, *, guild_id: int, key: str, value_json: dict
    ) -> RuleConfig:
        db_obj = await self.get_by_key(session, guild_id=guild_id, key=key)
        if db_obj:
            db_obj.value_json = value_json
            # db_obj.updated_at = datetime.utcnow() # If TimestampMixin is used and needs manual update
        else:
            db_obj = self.model(guild_id=guild_id, key=key, value_json=value_json)
            session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    async def get_multi_by_guild_and_prefix(
        self, session: AsyncSession, *, guild_id: int, prefix: str, skip: int = 0, limit: int = 100
    ) -> Sequence[RuleConfig]:
        """
        Get multiple RuleConfig records for a guild, filtered by key prefix.
        """
        statement = (
            select(self.model)
            .where(self.model.guild_id == guild_id, self.model.key.startswith(prefix))
            .order_by(self.model.key)
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(statement)
        return result.scalars().all()

    async def count_by_guild_and_prefix(
        self, session: AsyncSession, *, guild_id: int, prefix: str
    ) -> int:
        """
        Count RuleConfig records for a guild, filtered by key prefix.
        """
        from sqlalchemy.sql.expression import func # Local import for func
        statement = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.guild_id == guild_id, self.model.key.startswith(prefix))
        )
        result = await session.execute(statement)
        count = result.scalar_one_or_none()
        return count if count is not None else 0

rule_config_crud = CRUDRuleConfig(RuleConfig)
