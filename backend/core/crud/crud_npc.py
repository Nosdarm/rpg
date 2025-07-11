from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..crud_base_definitions import CRUDBase # Corrected import path
from ...models.generated_npc import GeneratedNpc


class CRUDNpc(CRUDBase[GeneratedNpc]):
    # You can add NPC-specific CRUD methods here if needed
    async def get_by_static_id(
        self, session: AsyncSession, *, guild_id: int, static_id: str
    ) -> Optional[GeneratedNpc]:
        """
        Get an NPC by their static_id and Guild ID.
        """
        return await self.get_by_attribute(session, attribute="static_id", value=static_id, guild_id=guild_id)

    async def get_by_id_and_guild(self, session: AsyncSession, *, id: int, guild_id: int) -> Optional[GeneratedNpc]:
        """
        Retrieves an NPC by its ID and Guild ID.
        Ensures the NPC belongs to the specified guild.
        """
        return await self.get(session, id=id, guild_id=guild_id)

    async def get_npcs_by_name_in_location(
        self, session: AsyncSession, *, guild_id: int, location_id: int, npc_name: str
    ) -> list[GeneratedNpc]:
        """
        Get NPCs by name (case-insensitive search on name_i18n['en']) in a specific location.
        """
        # Using func.lower for case-insensitive comparison on JSON field.
        # This might be database-specific in its efficiency or exact syntax for JSON path.
        # For PostgreSQL, this should work with name_i18n ->> 'en' to get the text value.
        # For SQLite, JSON functions might need to be enabled or handled differently if not using JSONB.
        # Assuming name_i18n is a JSON column that can be queried this way.
        # The model uses JsonBForSQLite which should handle this.
        from sqlalchemy import func as sql_func # Explicit import for clarity
        from sqlalchemy.future import select

        # Case-insensitive comparison for the 'en' key in name_i18n JSON field
        # The ->> operator extracts a JSON object field as text.
        stmt = (
            select(self.model)
            .where(
                self.model.guild_id == guild_id,
                self.model.current_location_id == location_id,
                sql_func.lower(self.model.name_i18n.op("->>")("en")) == npc_name.lower()
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


# Placeholder for the actual get_npc function if it needs more complex logic than generic get
async def get_npc(session: AsyncSession, npc_id: int, guild_id: int) -> Optional[GeneratedNpc]:
    """Placeholder for fetching an NPC. For now, uses the generic get."""
    # In a real implementation, this might involve more complex logic or joins
    return await npc_crud.get(session=session, id=npc_id, guild_id=guild_id)


npc_crud = CRUDNpc(GeneratedNpc)
