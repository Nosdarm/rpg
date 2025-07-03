from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..crud_base_definitions import CRUDBase # Corrected import path
from ...models.generated_npc import GeneratedNpc


class CRUDNpc(CRUDBase[GeneratedNpc]):
    # You can add NPC-specific CRUD methods here if needed
    async def get_by_static_id(
        self, db: AsyncSession, *, guild_id: int, static_id: str
    ) -> Optional[GeneratedNpc]:
        """
        Get an NPC by their static_id and Guild ID.
        """
        return await self.get_by_attribute(db, attribute="static_id", value=static_id, guild_id=guild_id)

    async def get_by_id_and_guild(self, db: AsyncSession, *, id: int, guild_id: int) -> Optional[GeneratedNpc]:
        """
        Retrieves an NPC by its ID and Guild ID.
        Ensures the NPC belongs to the specified guild.
        """
        return await self.get(db, id=id, guild_id=guild_id)


# Placeholder for the actual get_npc function if it needs more complex logic than generic get
async def get_npc(session: AsyncSession, npc_id: int, guild_id: int) -> Optional[GeneratedNpc]:
    """Placeholder for fetching an NPC. For now, uses the generic get."""
    # In a real implementation, this might involve more complex logic or joins
    return await npc_crud.get(db=session, id=npc_id, guild_id=guild_id)


npc_crud = CRUDNpc(GeneratedNpc)
