from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..crud_base_definitions import CRUDBase # Corrected import path
from ...models.item import Item


class CRUDItem(CRUDBase[Item]):
    # You can add Item-specific CRUD methods here if needed
    async def get_by_static_id(
        self, db: AsyncSession, *, guild_id: int, static_id: str
    ) -> Optional[Item]:
        """
        Get an Item by its static_id and Guild ID.
        """
        return await self.get_by_attribute(db, attribute="static_id", value=static_id, guild_id=guild_id)

# Placeholder for the actual get_item function if it needs more complex logic
async def get_item(session: AsyncSession, item_id: int, guild_id: int) -> Optional[Item]:
    """Placeholder for fetching an item. For now, uses the generic get."""
    return await item_crud.get(db=session, id=item_id, guild_id=guild_id)

item_crud = CRUDItem(Item)
