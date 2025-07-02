import logging
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union

from sqlalchemy import select, update as sqlalchemy_update, delete as sqlalchemy_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from ..models.base import Base # Assuming Base is your declarative base

logger = logging.getLogger(__name__)

ModelType = TypeVar("ModelType", bound=Base)


class CRUDBase(Generic[ModelType]):
    def __init__(self, model: Type[ModelType]):
        """
        CRUD object with default methods to Create, Read, Update, Delete (CRUD).

        **Parameters**

        * `model`: A SQLAlchemy model class
        """
        self.model = model

    async def create(
        self, db: AsyncSession, *, obj_in: Dict[str, Any], guild_id: Optional[int] = None
    ) -> ModelType:
        """
        Create a new record in the database.

        :param db: The database session.
        :param obj_in: A dictionary containing the data for the new object.
        :param guild_id: Optional guild ID to associate the object with, if the model supports it.
        :return: The created object.
        """
        obj_in_data = dict(obj_in)
        if guild_id is not None and hasattr(self.model, "guild_id"):
            obj_in_data["guild_id"] = guild_id

        db_obj = self.model(**obj_in_data)
        db.add(db_obj)
        await db.flush() # Use flush to get ID before commit if needed, and to ensure guild_id constraint is checked early
        await db.refresh(db_obj)
        log_id = getattr(db_obj, 'id', 'N/A') if hasattr(db_obj, 'id') else 'N/A'
        logger.info(f"Created {self.model.__name__} with ID {log_id}"
                    f"{f' for guild {guild_id}' if guild_id else ''}")
        return db_obj

    async def get(
        self, db: AsyncSession, id: Any, *, guild_id: Optional[int] = None
    ) -> Optional[ModelType]:
        """
        Get a record by its ID.

        :param db: The database session.
        :param id: The ID of the object.
        :param guild_id: Optional guild ID to filter by, if the model supports it.
                         If the model has 'guild_id' and this is provided, it will be used in the query.
                         If the model has 'guild_id' and this is None, it might fetch a global record or fail if ambiguous.
        :return: The object, or None if not found.
        """
        statement = select(self.model)

        # Attempt to find the primary key column name. Common names are 'id' or 'static_id'.
        # This is a simplification; a more robust way would be to inspect self.model.__mapper__.primary_key.
        pk_column_name = "id" # Default assumption
        if hasattr(self.model, "static_id") and not hasattr(self.model, "id"): # Example for models with static_id as PK
             pk_column_name = "static_id"

        if hasattr(self.model, pk_column_name):
             statement = statement.where(getattr(self.model, pk_column_name) == id)
        else:
            logger.error(f"Model {self.model.__name__} does not have a recognized PK attribute ('id' or 'static_id') for get operation.")
            return None

        if guild_id is not None and hasattr(self.model, "guild_id"):
            statement = statement.where(getattr(self.model, "guild_id") == guild_id)

        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def get_multi(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100, guild_id: Optional[int] = None
    ) -> List[ModelType]:
        """
        Get multiple records with optional pagination and guild filtering.

        :param db: The database session.
        :param skip: Number of records to skip.
        :param limit: Maximum number of records to return.
        :param guild_id: Optional guild ID to filter by.
        :return: A list of objects.
        """
        statement = select(self.model)
        if guild_id is not None and hasattr(self.model, "guild_id"):
            statement = statement.where(getattr(self.model, "guild_id") == guild_id)

        statement = statement.offset(skip).limit(limit)
        result = await db.execute(statement)
        return list(result.scalars().all())

    async def update(
        self, db: AsyncSession, *, db_obj: ModelType, obj_in: Union[Dict[str, Any], ModelType]
    ) -> ModelType:
        """
        Update an existing record in the database.

        :param db: The database session.
        :param db_obj: The existing database object to update.
        :param obj_in: A dictionary or model instance containing the new data.
        :return: The updated object.
        """
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = {
                column.name: getattr(obj_in, column.name)
                for column in self.model.__table__.columns
                if hasattr(obj_in, column.name)
            }

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
            else:
                logger.warning(f"Field {field} not found in model {self.model.__name__} during update.")

        db.add(db_obj) # Add to session if it was detached or to mark as dirty
        await db.flush()
        await db.refresh(db_obj)
        log_id = getattr(db_obj, 'id', 'N/A') if hasattr(db_obj, 'id') else 'N/A'
        logger.info(f"Updated {self.model.__name__} with ID {log_id}")
        return db_obj

    async def delete(self, db: AsyncSession, *, id: Any, guild_id: Optional[int] = None) -> Optional[ModelType]:
        """
        Delete a record by its ID.

        :param db: The database session.
        :param id: The ID of the object to delete.
        :param guild_id: Optional guild ID for targeted deletion.
        :return: The deleted object, or None if not found.
        """
        obj = await self.get(db, id=id, guild_id=guild_id)
        if obj:
            await db.delete(obj)
            await db.flush()
            logger.info(f"Deleted {self.model.__name__} with ID {id}"
                        f"{f' for guild {guild_id}' if guild_id else ''}")
            return obj
        logger.warning(f"Attempted to delete non-existent {self.model.__name__} with ID {id}"
                       f"{f' for guild {guild_id}' if guild_id else ''}")
        return None

    async def get_by_attribute(
        self, db: AsyncSession, *, attribute: Union[str, InstrumentedAttribute], value: Any, guild_id: Optional[int] = None
    ) -> Optional[ModelType]:
        """
        Get a single record by a specific attribute and its value.

        :param db: The database session.
        :param attribute: The model attribute (column name as string or InstrumentedAttribute).
        :param value: The value to filter by.
        :param guild_id: Optional guild ID to further filter by.
        :return: The object, or None if not found.
        """
        attr = getattr(self.model, attribute) if isinstance(attribute, str) else attribute

        statement = select(self.model).where(attr == value)
        if guild_id is not None and hasattr(self.model, "guild_id"):
            statement = statement.where(getattr(self.model, "guild_id") == guild_id)

        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def get_multi_by_attribute(
        self, db: AsyncSession, *, attribute: Union[str, InstrumentedAttribute], value: Any,
        guild_id: Optional[int] = None, skip: int = 0, limit: int = 100
    ) -> List[ModelType]:
        """
        Get multiple records by a specific attribute and its value.

        :param db: The database session.
        :param attribute: The model attribute.
        :param value: The value to filter by.
        :param guild_id: Optional guild ID to further filter by.
        :param skip: Number of records to skip.
        :param limit: Maximum number of records to return.
        :return: A list of objects.
        """
        attr = getattr(self.model, attribute) if isinstance(attribute, str) else attribute

        statement = select(self.model).where(attr == value)
        if guild_id is not None and hasattr(self.model, "guild_id"):
            statement = statement.where(getattr(self.model, "guild_id") == guild_id)

        statement = statement.offset(skip).limit(limit)
        result = await db.execute(statement)
        return list(result.scalars().all())

    async def get_many_by_ids(
        self, db: AsyncSession, *, ids: List[Any], guild_id: Optional[int] = None
    ) -> List[ModelType]:
        """
        Get multiple records by a list of their IDs.

        :param db: The database session.
        :param ids: A list of IDs to fetch.
        :param guild_id: Optional guild ID to filter by.
        :return: A list of objects. Returns empty list if ids is empty.
        """
        if not ids:
            return []

        pk_column_name = "id" # Default assumption
        if hasattr(self.model, "static_id") and not hasattr(self.model, "id"):
             pk_column_name = "static_id"

        if not hasattr(self.model, pk_column_name):
            logger.error(f"Model {self.model.__name__} does not have a recognized PK attribute ('id' or 'static_id') for get_many_by_ids operation.")
            return []

        pk_column = getattr(self.model, pk_column_name)
        statement = select(self.model).where(pk_column.in_(ids))

        if guild_id is not None and hasattr(self.model, "guild_id"):
            statement = statement.where(getattr(self.model, "guild_id") == guild_id)

        result = await db.execute(statement) # This was missing await previously for execute
        # For execute returning a result, scalars().all() is correct.
        # If result itself was awaitable (e.g. from a different ORM or raw driver), then await result would be needed.
        # SQLAlchemy's execute() on an AsyncSession returns a Result object, not a coroutine.
        return list(result.scalars().all())


# Example of how to use it for a specific model (e.g., GuildConfig)
# from models.guild import GuildConfig
#
# class CRUDGuildConfig(CRUDBase[GuildConfig]):
#     async def get_by_guild_id(self, db: AsyncSession, *, guild_id: int) -> Optional[GuildConfig]:
#         # GuildConfig's primary key *is* guild_id, so self.get() can be used directly.
#         return await self.get(db, id=guild_id) # No need for additional guild_id filter here
#
# guild_config_crud = CRUDGuildConfig(GuildConfig)

# For RuleConfig
# from models.rule_config import RuleConfig
#
# class CRUDRuleConfig(CRUDBase[RuleConfig]):
#     async def get_by_guild_and_key(self, db: AsyncSession, *, guild_id: int, key: str) -> Optional[RuleConfig]:
#         statement = select(self.model).where(self.model.guild_id == guild_id, self.model.key == key)
#         result = await db.execute(statement)
#         return result.scalar_one_or_none()
#
#     async def get_all_for_guild(self, db: AsyncSession, *, guild_id: int) -> List[RuleConfig]:
#         return await self.get_multi_by_attribute(db, attribute="guild_id", value=guild_id, limit=1000) # Adjust limit as needed
#
# rule_config_crud = CRUDRuleConfig(RuleConfig)

# Generic functions as requested by Task 0.3 (not tied to CRUDBase class instances)
# These will use CRUDBase internally or operate directly.

async def create_entity(db: AsyncSession, model: Type[ModelType], data: Dict[str, Any], guild_id: Optional[int] = None) -> ModelType:
    """
    Generic function to create an entity.
    If guild_id is provided and the model has a 'guild_id' attribute, it will be set.
    """
    crud = CRUDBase(model)
    # Ensure guild_id from param is prioritized if model has it
    if guild_id is not None and hasattr(model, "guild_id"):
        data["guild_id"] = guild_id
    elif "guild_id" in data and not hasattr(model, "guild_id"):
        # If data has guild_id but model doesn't, remove it to prevent errors
        del data["guild_id"]

    return await crud.create(db, obj_in=data) # guild_id in data will be handled by crud.create if model supports it

async def get_entity_by_id(db: AsyncSession, model: Type[ModelType], entity_id: Any, guild_id: Optional[int] = None) -> Optional[ModelType]:
    """
    Generic function to get an entity by its ID.
    If guild_id is provided and the model has 'guild_id', it filters by it.
    For models where 'guild_id' is part of the PK or essential, it should be provided.
    """
    crud = CRUDBase(model)
    # The CRUDBase.get method already handles guild_id if the model supports it.
    return await crud.get(db, id=entity_id, guild_id=guild_id)

async def update_entity(db: AsyncSession, entity: ModelType, data: Dict[str, Any]) -> ModelType:
    """
    Generic function to update an existing entity.
    Note: This function expects the `entity` SQLAlchemy model instance, not its ID.
    Guild_id context for update should be inherent in the `entity` if it was fetched correctly.
    """
    crud = CRUDBase(type(entity))
    # Prevent guild_id from being changed via this generic update if it exists in data and on model
    if hasattr(entity, "guild_id") and "guild_id" in data:
        current_guild_id = getattr(entity, "guild_id")
        if data["guild_id"] != current_guild_id:
            entity_id_for_log = getattr(entity, 'id', "N/A") if hasattr(entity, 'id') else "N/A"
            logger.warning(f"Attempt to change guild_id during update of {type(entity).__name__} ID {entity_id_for_log} blocked.")
            del data["guild_id"]

    return await crud.update(db, db_obj=entity, obj_in=data)

async def delete_entity(db: AsyncSession, model: Type[ModelType], entity_id: Any, guild_id: Optional[int] = None) -> Optional[ModelType]:
    """
    Generic function to delete an entity by its ID.
    If guild_id is provided, it's used to ensure the correct entity is targeted for deletion.
    """
    crud = CRUDBase(model)
    # The CRUDBase.delete method handles guild_id for targeting the get prior to delete.
    return await crud.delete(db, id=entity_id, guild_id=guild_id)

# Example usage:
# async def example_usage(db: AsyncSession):
#     from models.guild import GuildConfig
#     new_config_data = {"id": 12345, "main_language": "fr"} # id is guild_id for GuildConfig
#     # For GuildConfig, guild_id is the PK, so it's passed as 'id' to create_entity if that's how the model is structured,
#     # or it could be passed via the guild_id parameter if 'id' is a separate auto-incrementing PK.
#     # Assuming GuildConfig.id is the Discord Guild ID (PK)
#     created_config = await create_entity(db, GuildConfig, new_config_data)
#
#     retrieved_config = await get_entity_by_id(db, GuildConfig, entity_id=12345)
#
#     if retrieved_config:
#         updated_config = await update_entity(db, retrieved_config, {"master_channel_id": 98765})
#
#     # For RuleConfig which has a separate auto-inc PK and a guild_id FK
#     from models.rule_config import RuleConfig
#     new_rule_data = {"key": "welcome_message", "value_json": {"text": "Hello!"}}
#     created_rule = await create_entity(db, RuleConfig, new_rule_data, guild_id=12345)
#
#     retrieved_rule = await get_entity_by_id(db, RuleConfig, entity_id=created_rule.id, guild_id=12345)
#
#     if retrieved_rule:
#         await delete_entity(db, RuleConfig, entity_id=retrieved_rule.id, guild_id=12345)

logger.info("CRUDBase and generic CRUD functions (create_entity, get_entity_by_id, update_entity, delete_entity) defined.")

# Create src/core/__init__.py if it doesn't exist
# (This part is a note for myself, not code to be written to crud.py)
# Content for src/core/__init__.py:
# from . import crud
# from . import database
# from . import rules
# __all__ = ["crud", "database", "rules"]
