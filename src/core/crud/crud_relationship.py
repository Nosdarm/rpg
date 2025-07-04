from typing import Optional, Sequence

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..crud_base_definitions import CRUDBase
from ...models.relationship import Relationship, RelationshipEntityType


class CRUDRelationship(CRUDBase[Relationship]):
    async def get_relationship_between_entities(
        self,
        db: AsyncSession,
        *,
        guild_id: int,
        entity1_type: RelationshipEntityType,
        entity1_id: int,
        entity2_type: RelationshipEntityType,
        entity2_id: int,
    ) -> Optional[Relationship]:
        """
        Retrieves a relationship between two specific entities, regardless of the order
        in which they are stored in the database.
        """
        # stmt = select(self.model).where(
        #     self.model.guild_id == guild_id,
        #     or_(
        #         (self.model.entity1_type == entity1_type) &
        #         (self.model.entity1_id == entity1_id) &
        #         (self.model.entity2_type == entity2_type) &
        #         (self.model.entity2_id == entity2_id),
        #         (self.model.entity1_type == entity2_type) &
        #         (self.model.entity1_id == entity2_id) &
        #         (self.model.entity2_type == entity1_type) &
        #         (self.model.entity2_id == entity1_id)
        #     )
        # )
        # Use direct string comparison for enums if they are stored as strings
        # If enums are stored as actual enum types in DB, then direct comparison is fine.
        # Given RelationshipEntityType is an enum, direct comparison should work.

        stmt = select(self.model).where(
            self.model.guild_id == guild_id
        ).where(
            or_(
                (
                    (self.model.entity1_type == entity1_type) &
                    (self.model.entity1_id == entity1_id) &
                    (self.model.entity2_type == entity2_type) &
                    (self.model.entity2_id == entity2_id)
                ),
                (
                    (self.model.entity1_type == entity2_type) &
                    (self.model.entity1_id == entity2_id) &
                    (self.model.entity2_type == entity1_type) &
                    (self.model.entity2_id == entity1_id)
                )
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_relationships_for_entity(
        self,
        db: AsyncSession,
        *,
        guild_id: int,
        entity_type: RelationshipEntityType,
        entity_id: int,
        limit: int = 100,
        skip: int = 0
    ) -> Sequence[Relationship]:
        """
        Retrieves all relationships involving a specific entity.
        """
        stmt = select(self.model).where(
            self.model.guild_id == guild_id,
            or_(
                (self.model.entity1_type == entity_type) & (self.model.entity1_id == entity_id),
                (self.model.entity2_type == entity_type) & (self.model.entity2_id == entity_id)
            )
        ).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()


crud_relationship = CRUDRelationship(Relationship)
