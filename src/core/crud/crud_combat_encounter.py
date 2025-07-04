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
        return [] # Return empty list to satisfy type hint

    async def get_by_id_and_guild(self, db: AsyncSession, *, id: int, guild_id: int) -> Optional[CombatEncounter]:
        """
        Retrieves a combat encounter by its ID and Guild ID.
        Ensures the encounter belongs to the specified guild.
        """
        query = select(self.model).filter(self.model.id == id, self.model.guild_id == guild_id)
        result = await db.execute(query)
        return result.scalars().first()

    async def get_active_combat_for_entity(
        self, db: AsyncSession, *, guild_id: int, entity_id: int, entity_type: str
    ) -> Optional[CombatEncounter]:
        """
        Retrieves the active combat encounter for a specific entity in a guild.
        An entity is considered in active combat if it's listed in participants_json
        of a CombatEncounter with status ACTIVE.
        """
        # This query is a bit complex due to JSONB operations.
        # It checks if the participants_json array contains an object with the given id and type.
        # Note: JSONB path operators like @> are specific to PostgreSQL.
        # For broader compatibility or if not using PostgreSQL, this might need adjustment
        # (e.g., fetching encounters and filtering in Python, which is less efficient).

        # Constructing the JSON path element to search for
        # Example: '[{"id": 123, "type": "player"}]' - checks if this entity is in the list
        # A more precise check would be participants_json['entities'] @> jsonb_build_array(jsonb_build_object('id', entity_id, 'type', entity_type))
        # However, SQLAlchemy's JSONB support might require specific syntax.
        # Let's try a simpler contains approach first, assuming 'id' and 'type' are top-level in participant entries.

        # This is a simplified approach for demonstration.
        # A robust way needs to iterate through participants_json in Python or use more complex JSON queries.
        # For now, we fetch all active combats for the guild and filter in Python.
        # This is NOT efficient for many active combats.
        stmt = select(self.model).where(
            self.model.guild_id == guild_id,
            self.model.status == CombatStatus.ACTIVE
        )
        result = await db.execute(stmt)
        active_combats = result.scalars().all()

        for combat in active_combats:
            if combat.participants_json and "entities" in combat.participants_json:
                for participant in combat.participants_json["entities"]:
                    if isinstance(participant, dict) and \
                       participant.get("id") == entity_id and \
                       participant.get("type") == entity_type:
                        # Check participant's current_hp > 0 as well? Or combat status is enough?
                        # For now, if they are in an active combat, return it.
                        # Defeated participants might still be in the list until combat ends.
                        return combat
        return None

combat_encounter_crud = CRUDCombatEncounter(CombatEncounter)
