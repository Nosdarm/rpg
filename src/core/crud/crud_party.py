from typing import Optional, List, Any

from sqlalchemy import select, update as sqlalchemy_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import JSONB

from ..crud_base_definitions import CRUDBase
from models.party import Party, PartyTurnStatus
from models.player import Player # Needed for updating Player.current_party_id


class CRUDParty(CRUDBase[Party]):
    async def get_by_name(
        self, db: AsyncSession, *, guild_id: int, name: str
    ) -> Optional[Party]:
        """
        Get a party by its name and Guild ID.
        Party names might not be unique, so this could return the first match.
        Consider if names should be unique per guild or if this is just a convenience.
        """
        statement = (
            select(self.model)
            .where(self.model.guild_id == guild_id, self.model.name == name)
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none() # Returns first match or None

    async def add_player_to_party_json(
        self, db: AsyncSession, *, party: Party, player_id: int
    ) -> Party:
        """
        Adds a player's ID to the party's player_ids_json list.
        This method only updates the JSON list in the Party model.
        It does NOT update Player.current_party_id.
        """
        if party.player_ids_json is None:
            party.player_ids_json = []

        if player_id not in party.player_ids_json:
            # Create a new list to ensure SQLAlchemy detects the change to the mutable JSON type
            new_player_ids = list(party.player_ids_json)
            new_player_ids.append(player_id)
            party.player_ids_json = new_player_ids

            db.add(party)
            await db.flush()
            await db.refresh(party)
        return party

    async def remove_player_from_party_json(
        self, db: AsyncSession, *, party: Party, player_id: int
    ) -> Party:
        """
        Removes a player's ID from the party's player_ids_json list.
        This method only updates the JSON list in the Party model.
        It does NOT update Player.current_party_id.
        """
        if party.player_ids_json and player_id in party.player_ids_json:
            # Create a new list to ensure SQLAlchemy detects the change
            new_player_ids = [pid for pid in party.player_ids_json if pid != player_id]
            party.player_ids_json = new_player_ids

            db.add(party)
            await db.flush()
            await db.refresh(party)
        return party

    # Note: Managing Player.current_party_id should be handled at a higher service level
    # to ensure consistency, often in the same transaction as modifying Party.player_ids_json.
    # For example, a "join_party_service" would:
    # 1. Call add_player_to_party_json
    # 2. Update Player.current_party_id for the joined player
    # All within one transaction.

party_crud = CRUDParty(Party)
