from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional

from src.core.crud_base_definitions import CRUDBase
from src.models.combat_encounter import CombatEncounter


class CRUDCombatEncounter(CRUDBase[CombatEncounter]):
    # Specific methods for CombatEncounter can be added here if needed
    # For example, finding active encounters for a guild, etc.
    async def get_active_for_guild(self, db: AsyncSession, *, guild_id: int) -> list[CombatEncounter]:
        """
        Retrieves all active combat encounters for a specific guild.
        (Example of a specific method, not strictly required by current combat_engine)
        """
        # Assuming CombatStatus has an 'ACTIVE' member or similar relevant statuses
        # from src.models.enums import CombatStatus
        # query = select(self.model).filter(self.model.guild_id == guild_id, self.model.status == CombatStatus.ACTIVE)
        # result = await db.execute(query)
        # return result.scalars().all()
        pass # Placeholder for now

    async def get_by_id_and_guild(self, db: AsyncSession, *, id: int, guild_id: int) -> Optional[CombatEncounter]:
        """
        Retrieves a combat encounter by its ID and Guild ID.
        Ensures the encounter belongs to the specified guild.
        """
        query = select(self.model).filter(self.model.id == id, self.model.guild_id == guild_id)
        result = await db.execute(query)
        return result.scalars().first()

combat_encounter_crud = CRUDCombatEncounter(CombatEncounter)
