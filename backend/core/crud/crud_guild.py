from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...models.guild import GuildConfig
from ..crud_base_definitions import CRUDBase


class CRUDGuild(CRUDBase[GuildConfig]):
    async def get_by_id(self, db: AsyncSession, *, id: int) -> Optional[GuildConfig]:
        """
        Get a guild by its ID (which is the Discord Guild ID).
        """
        # CRUDBase.get() can be used if the primary key is consistently named 'id'
        # and if guild_id filtering is not needed for GuildConfig itself.
        return await super().get(db, id=id)

    # Add any guild-specific CRUD methods here if needed in the future.


guild_crud = CRUDGuild(GuildConfig)
