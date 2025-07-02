from typing import Optional, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.crud_base_definitions import CRUDBase
from src.models import StatusEffect, ActiveStatusEffect

class CRUDStatusEffect(CRUDBase[StatusEffect]):
    async def get_by_static_id(
        self, db: AsyncSession, *, static_id: str, guild_id: Optional[int] = None
    ) -> Optional[StatusEffect]:
        """
        Retrieves a status effect definition by its static_id.
        If guild_id is provided, it first tries to find a guild-specific one.
        If not found or guild_id is None, it tries to find a global one (guild_id IS NULL).
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
    ) -> Sequence[StatusEffect]:
        """
        Retrieves multiple status effect definitions, including global and guild-specific.
        """
        stmt = select(self.model).where(
            (self.model.guild_id == guild_id) | (self.model.guild_id.is_(None))
        ).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()

class CRUDActiveStatusEffect(CRUDBase[ActiveStatusEffect]):
    async def get_multi_by_owner(
        self, db: AsyncSession, *, owner_id: int, owner_type: str, guild_id: int, skip: int = 0, limit: int = 100
    ) -> Sequence[ActiveStatusEffect]:
        """
        Retrieves active status effects for a specific owner within a guild.
        Note: owner_type should match the string representation in RelationshipEntityType enum.
        """
        # Ensure owner_type is valid if using RelationshipEntityType directly
        # from src.models.enums import RelationshipEntityType
        from src.models.enums import RelationshipEntityType # Import enum
        try:
            owner_type_enum_val = RelationshipEntityType(owner_type.lower())
        except ValueError:
            # Handle invalid owner_type string if necessary, e.g., return empty list or raise error
            return []

        stmt = select(self.model).where(
            self.model.entity_id == owner_id, # Corrected: owner_id to entity_id
            self.model.entity_type == owner_type_enum_val, # Corrected: owner_type to entity_type and compare with enum
            self.model.guild_id == guild_id
        ).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()


status_effect_crud = CRUDStatusEffect(StatusEffect)
active_status_effect_crud = CRUDActiveStatusEffect(ActiveStatusEffect)
