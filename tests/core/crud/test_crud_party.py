import unittest
from typing import Optional, List

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy import event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator, TEXT, JSON

from src.models.base import Base
from src.models.guild import GuildConfig
from src.models.location import Location, LocationType, JsonBForSQLite as LocationJsonBForSQLite
from src.models.player import Player # Needed for leader_player_id
from src.models.party import Party, PartyTurnStatus
from src.core.crud.crud_party import party_crud
from src.core.crud.crud_location import location_crud
from src.core.crud.crud_player import player_crud # For creating leader player
from src.models.custom_types import JsonBForSQLite


# Event listeners for SQLite compatibility
@event.listens_for(Party.__table__, "column_reflect")
def _party_column_reflect_crud_party(inspector, table, column_info):
    if column_info['name'] == 'player_ids_json' and isinstance(column_info['type'], JSON):
        pass

@event.listens_for(Location.__table__, "column_reflect")
def _location_column_reflect_crud_party(inspector, table, column_info):
    if column_info['name'] in ['name_i18n', 'descriptions_i18n', 'coordinates_json', 'neighbor_locations_json', 'generated_details_json', 'ai_metadata_json']:
        if not isinstance(column_info['type'], LocationJsonBForSQLite):
             column_info['type'] = LocationJsonBForSQLite()
@event.listens_for(Player.__table__, "column_reflect")
def _player_column_reflect_crud_party(inspector, table, column_info):
    if column_info['name'] == 'collected_actions_json' and isinstance(column_info['type'], JSON):
         pass


class TestCRUDParty(unittest.IsolatedAsyncioTestCase):
    engine: Optional[AsyncEngine] = None
    SessionLocal: Optional[async_sessionmaker[AsyncSession]] = None

    test_guild_id = 201
    other_guild_id = 202
    test_loc_id: Optional[int] = None
    test_leader_id: Optional[int] = None
    p1_id: Optional[int] = None
    p2_id: Optional[int] = None


    @classmethod
    def setUpClass(cls):
        cls.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        cls.SessionLocal = async_sessionmaker(
            bind=cls.engine, class_=AsyncSession, expire_on_commit=False
        )

    @classmethod
    async def tearDownClass(cls):
        if cls.engine:
            await cls.engine.dispose()

    async def asyncSetUp(self):
        assert self.SessionLocal is not None
        self.session: AsyncSession = self.SessionLocal()

        assert self.engine is not None
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        for gid in [self.test_guild_id, self.other_guild_id]:
            guild = await self.session.get(GuildConfig, gid)
            if not guild:
                self.session.add(GuildConfig(id=gid, main_language="en", name=f"Guild {gid}"))

        loc = await location_crud.create(self.session, obj_in={
            "guild_id": self.test_guild_id, "static_id": "party_crud_loc",
            "name_i18n": {"en": "Party CRUD Loc"}, "descriptions_i18n": {"en": "Desc"},
            "type": LocationType.GENERIC
        })
        self.test_loc_id = loc.id

        leader = await player_crud.create_with_defaults(self.session, guild_id=self.test_guild_id, discord_id=301, name="PartyLeaderCRUD")
        self.test_leader_id = leader.id

        p1 = await player_crud.create_with_defaults(self.session, guild_id=self.test_guild_id, discord_id=302, name="PartyMember1CRUD")
        self.p1_id = p1.id
        p2 = await player_crud.create_with_defaults(self.session, guild_id=self.test_guild_id, discord_id=303, name="PartyMember2CRUD")
        self.p2_id = p2.id

        await self.session.commit()

    async def asyncTearDown(self):
        if hasattr(self, 'session') and self.session:
            await self.session.rollback()
            await self.session.close()

    async def test_create_party(self):
        party_data = {
            "guild_id": self.test_guild_id,
            "name": "Test Create Party",
            "current_location_id": self.test_loc_id,
            "leader_player_id": self.test_leader_id,
            "player_ids_json": [self.p1_id, self.p2_id]
        }
        party = await party_crud.create(self.session, obj_in=party_data)
        self.assertIsNotNone(party.id)
        self.assertEqual(party.name, "Test Create Party")
        self.assertEqual(party.guild_id, self.test_guild_id)
        self.assertEqual(party.current_location_id, self.test_loc_id)
        self.assertEqual(party.leader_player_id, self.test_leader_id)
        self.assertListEqual(party.player_ids_json if party.player_ids_json else [], [self.p1_id, self.p2_id])
        self.assertEqual(party.turn_status, PartyTurnStatus.IDLE) # Default

    async def test_get_party_by_name(self):
        await party_crud.create(self.session, obj_in={"guild_id": self.test_guild_id, "name": "NamedParty"})

        found_party = await party_crud.get_by_name(self.session, guild_id=self.test_guild_id, name="NamedParty")
        self.assertIsNotNone(found_party)
        self.assertEqual(found_party.name, "NamedParty")

        not_found_party = await party_crud.get_by_name(self.session, guild_id=self.test_guild_id, name="NonExistentParty")
        self.assertIsNone(not_found_party)

        wrong_guild_party = await party_crud.get_by_name(self.session, guild_id=self.other_guild_id, name="NamedParty")
        self.assertIsNone(wrong_guild_party)

    async def test_add_player_to_party_json(self):
        assert self.p1_id is not None and self.p2_id is not None
        party = await party_crud.create(self.session, obj_in={
            "guild_id": self.test_guild_id, "name": "AddPlayerParty", "player_ids_json": [self.p1_id]
        })

        updated_party = await party_crud.add_player_to_party_json(self.session, party=party, player_id=self.p2_id)
        self.assertIsNotNone(updated_party.player_ids_json)
        if updated_party.player_ids_json: # type guard
             self.assertIn(self.p1_id, updated_party.player_ids_json)
             self.assertIn(self.p2_id, updated_party.player_ids_json)
             self.assertEqual(len(updated_party.player_ids_json), 2)

        # Try adding same player again (should not duplicate)
        party_after_duplicate_add = await party_crud.add_player_to_party_json(self.session, party=updated_party, player_id=self.p2_id)
        self.assertIsNotNone(party_after_duplicate_add.player_ids_json)
        if party_after_duplicate_add.player_ids_json: # type guard
            self.assertEqual(len(party_after_duplicate_add.player_ids_json), 2)


    async def test_remove_player_from_party_json(self):
        assert self.p1_id is not None and self.p2_id is not None
        party = await party_crud.create(self.session, obj_in={
            "guild_id": self.test_guild_id, "name": "RemovePlayerParty", "player_ids_json": [self.p1_id, self.p2_id]
        })

        updated_party = await party_crud.remove_player_from_party_json(self.session, party=party, player_id=self.p1_id)
        self.assertIsNotNone(updated_party.player_ids_json)
        if updated_party.player_ids_json: # type guard
            self.assertNotIn(self.p1_id, updated_party.player_ids_json)
            self.assertIn(self.p2_id, updated_party.player_ids_json)
            self.assertEqual(len(updated_party.player_ids_json), 1)

        # Try removing non-existent player from list
        party_after_false_remove = await party_crud.remove_player_from_party_json(self.session, party=updated_party, player_id=999)
        self.assertIsNotNone(party_after_false_remove.player_ids_json)
        if party_after_false_remove.player_ids_json: # type guard
             self.assertEqual(len(party_after_false_remove.player_ids_json), 1) # Should remain 1

    async def test_update_party(self):
        party = await party_crud.create(self.session, obj_in={"guild_id": self.test_guild_id, "name": "UpdateMyParty"})

        update_data = {"name": "PartyIsUpdated", "turn_status": PartyTurnStatus.PROCESSING_GUILD_TURN}
        updated_party = await party_crud.update(self.session, db_obj=party, obj_in=update_data)

        self.assertEqual(updated_party.name, "PartyIsUpdated")
        self.assertEqual(updated_party.turn_status, PartyTurnStatus.PROCESSING_GUILD_TURN)

    async def test_delete_party(self):
        party = await party_crud.create(self.session, obj_in={"guild_id": self.test_guild_id, "name": "DeleteThisParty"})
        party_id = party.id

        await party_crud.delete(self.session, id=party_id, guild_id=self.test_guild_id)
        deleted_party = await party_crud.get(self.session, id=party_id, guild_id=self.test_guild_id)
        self.assertIsNone(deleted_party)

        # Try deleting non-existent
        await party_crud.delete(self.session, id=9999, guild_id=self.test_guild_id) # Should not raise error


if __name__ == "__main__":
    unittest.main()
