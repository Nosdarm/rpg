from typing import Optional, List, Dict, Any
from sqlalchemy import select, desc, asc, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import func

from src.core.crud_base_definitions import CRUDBase
from src.models import StoryLog, EventType # Assuming EventType is available for filtering
from src.models.custom_types import JsonBForSQLite # If filtering by JSON fields

# For type hinting if using specific JSON structures for entity_ids_json
from src.models.enums import RelationshipEntityType

class CRUDStoryLog(CRUDBase[StoryLog]):
    async def get_multi_by_guild_with_filters(
        self,
        session: AsyncSession,
        *,
        guild_id: int,
        skip: int = 0,
        limit: int = 10,
        event_type: Optional[EventType] = None,
        # For entity_ids_json, we might want to filter if a specific entity was involved.
        # This is a simplified example; more complex JSON queries might be needed.
        involved_entity_id: Optional[int] = None,
        involved_entity_type: Optional[RelationshipEntityType] = None, # e.g., PLAYER, NPC
        turn_number: Optional[int] = None,
        timestamp_after: Optional[Any] = None, # Expects datetime object
        timestamp_before: Optional[Any] = None, # Expects datetime object
        order_by: str = "timestamp", # "timestamp", "id", "turn_number"
        descending: bool = True,
    ) -> List[StoryLog]:
        statement = select(self.model).where(self.model.guild_id == guild_id)

        if event_type:
            statement = statement.where(self.model.event_type == event_type)
        if turn_number is not None:
            statement = statement.where(self.model.turn_number == turn_number)
        if timestamp_after:
            statement = statement.where(self.model.timestamp >= timestamp_after)
        if timestamp_before:
            statement = statement.where(self.model.timestamp <= timestamp_before)

        if involved_entity_id is not None and involved_entity_type is not None:
            # This is a basic JSON containment check.
            # For PostgreSQL, more advanced JSON operators could be used.
            # For SQLite with JSON1 extension, json_each or similar might be used,
            # but that's more complex to implement generally here.
            # This example assumes entity_ids_json stores lists of IDs under keys like "player_ids", "npc_ids".
            # Adjust the path and query method based on the actual structure of entity_ids_json.
            # Example: entity_ids_json = {"player_ids": [1,2], "npc_ids": [101]}
            # We need to construct the key like "player_ids" from RelationshipEntityType

            # This is a placeholder for actual JSONB path/containment query
            # For SQLite, this would require custom functions or very specific JSON structures.
            # For PostgreSQL, you could use:
            # from sqlalchemy.dialects.postgresql import JSONB
            # entity_key = f"{involved_entity_type.value.lower()}_ids" # e.g. "player_ids"
            # statement = statement.where(self.model.entity_ids_json[entity_key].astext.cast(Integer).contains([involved_entity_id]))
            # or statement = statement.where(self.model.entity_ids_json[entity_key].astext == str(involved_entity_id)) if it's not a list
            # For now, this filter part is conceptual for non-PostgreSQL JSON handling in SQLAlchemy ORM core
            # A simple string "like" might be a fallback for SQLite if numbers are stored as strings in a list.
            # e.g. entity_ids_json_str_contains = f'"key": [{involved_entity_id},' or f'"key": [{involved_entity_id}]'
            # This is highly database-specific and schema-specific.
            # Let's assume a simpler filter for now or leave it for more specific implementation if needed.
            # For this basic CRUD, we might omit direct JSON filtering or use a very simple LIKE.
            pass # Omitting complex JSON query for this generic CRUD.

        if order_by == "timestamp":
            order_field = self.model.timestamp
        elif order_by == "id":
            order_field = self.model.id
        elif order_by == "turn_number":
            order_field = self.model.turn_number
        else:
            order_field = self.model.timestamp # Default

        if descending:
            statement = statement.order_by(desc(order_field))
        else:
            statement = statement.order_by(asc(order_field))

        statement = statement.offset(skip).limit(limit)
        result = await session.execute(statement)
        return list(result.scalars().all())

    async def count_by_guild_with_filters(
        self,
        session: AsyncSession,
        *,
        guild_id: int,
        event_type: Optional[EventType] = None,
        involved_entity_id: Optional[int] = None,
        involved_entity_type: Optional[RelationshipEntityType] = None,
        turn_number: Optional[int] = None,
        timestamp_after: Optional[Any] = None,
        timestamp_before: Optional[Any] = None,
    ) -> int:
        statement = select(func.count()).select_from(self.model).where(self.model.guild_id == guild_id)

        if event_type:
            statement = statement.where(self.model.event_type == event_type)
        if turn_number is not None:
            statement = statement.where(self.model.turn_number == turn_number)
        if timestamp_after:
            statement = statement.where(self.model.timestamp >= timestamp_after)
        if timestamp_before:
            statement = statement.where(self.model.timestamp <= timestamp_before)

        # Placeholder for JSON filtering as in get_multi_by_guild_with_filters
        if involved_entity_id is not None and involved_entity_type is not None:
            pass

        result = await session.execute(statement)
        count = result.scalar_one_or_none()
        return count if count is not None else 0


story_log_crud = CRUDStoryLog(StoryLog)
