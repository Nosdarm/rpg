from typing import Optional, List, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.crud import CRUDBase # Adjust import if CRUDBase is in a different location relative to this file
from models.location import Location, LocationType


class CRUDLocation(CRUDBase[Location]):
    async def get_by_static_id(
        self, db: AsyncSession, *, guild_id: int, static_id: str
    ) -> Optional[Location]:
        """
        Get a location by its static_id and guild_id.
        """
        statement = (
            select(self.model)
            .where(self.model.guild_id == guild_id, self.model.static_id == static_id)
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def create_with_guild(
        self, db: AsyncSession, *, obj_in: Dict[str, Any], guild_id: int
    ) -> Location:
        """
        Create a new location, ensuring guild_id is set.
        obj_in is a dictionary of fields for the Location model.
        """
        # The CRUDBase.create method already handles setting guild_id if present in its signature
        # and if the model has a guild_id attribute.
        # We can pass guild_id directly to it.
        return await super().create(db, obj_in=obj_in, guild_id=guild_id)

    async def get_locations_by_type(
        self, db: AsyncSession, *, guild_id: int, location_type: LocationType, skip: int = 0, limit: int = 100
    ) -> List[Location]:
        """
        Get all locations of a specific type for a guild.
        """
        statement = (
            select(self.model)
            .where(self.model.guild_id == guild_id, self.model.type == location_type)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(statement)
        return list(result.scalars().all())

    # get_multi from CRUDBase can be used for getting all locations for a guild:
    # await location_crud.get_multi(db, guild_id=guild_id)

    # get from CRUDBase can be used for get_location_by_id (PK) and guild_id:
    # await location_crud.get(db, id=location_pk_id, guild_id=guild_id)


location_crud = CRUDLocation(Location)
