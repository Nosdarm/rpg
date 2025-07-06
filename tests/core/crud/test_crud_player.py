import sys
import os
import unittest
from typing import Optional, List

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy import event, select
from sqlalchemy.dialects.postgresql import JSONB # Not directly used here, but models might reference it
from sqlalchemy.types import TypeDecorator, TEXT, JSON # For event listener type checking

from src.models.base import Base
from src.models.guild import GuildConfig
from src.models.location import Location, LocationType
from src.models.party import Party, PartyTurnStatus
# JsonBForSQLite is already imported from custom_types below, so this specific alias for Location is not needed here.
# from src.models.location import Location, LocationType, JsonBForSQLite as LocationJsonBForSQLite
from src.models.player import Player, PlayerStatus
from src.core.crud.crud_player import player_crud
from src.core.crud.crud_location import location_crud # For creating test locations
from src.core.crud.crud_party import party_crud # For creating test parties
from src.models.rule_config import RuleConfig # Added import
from src.core.crud_base_definitions import CRUDBase # Corrected import path
from src.core.rules import update_rule_config # For adding rules
from src.models.custom_types import JsonBForSQLite # This is the one we need

# Event listeners for SQLite compatibility (similar to model tests)
@event.listens_for(Player.__table__, "column_reflect")
def _player_column_reflect_crud(inspector, table, column_info):
    if column_info['name'] == 'collected_actions_json' and isinstance(column_info['type'], JSON):
        pass

@event.listens_for(Location.__table__, "column_reflect")
def _location_column_reflect_crud(inspector, table, column_info):
    if column_info['name'] in ['name_i18n', 'descriptions_i18n', 'coordinates_json', 'neighbor_locations_json', 'generated_details_json', 'ai_metadata_json']:
        if not isinstance(column_info['type'], JsonBForSQLite): # Changed LocationJsonBForSQLite to JsonBForSQLite
             column_info['type'] = JsonBForSQLite()

@event.listens_for(Party.__table__, "column_reflect")
def _party_column_reflect_crud(inspector, table, column_info):
    if column_info['name'] == 'player_ids_json' and isinstance(column_info['type'], JSON):
        pass


class TestCRUDPlayer(unittest.IsolatedAsyncioTestCase):
    engine: Optional[AsyncEngine] = None
    SessionLocal: Optional[async_sessionmaker[AsyncSession]] = None

    test_guild_id = 101
    other_guild_id = 102
    test_loc_id: Optional[int] = None
    test_party_id: Optional[int] = None

    @classmethod
    def setUpClass(cls):
        cls.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        cls.SessionLocal = async_sessionmaker(
            bind=cls.engine, class_=AsyncSession, expire_on_commit=False
        )

    @classmethod
    def tearDownClass(cls): # Changed to sync
        if cls.engine:
            import asyncio
            asyncio.run(cls.engine.dispose()) # Run async dispose

    async def asyncSetUp(self):
        assert self.SessionLocal is not None
        self.session: AsyncSession = self.SessionLocal()

        assert self.engine is not None
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        # Setup GuildConfigs
        for gid in [self.test_guild_id, self.other_guild_id]:
            guild = await self.session.get(GuildConfig, gid)
            if not guild:
                self.session.add(GuildConfig(id=gid, main_language="en", name=f"Guild {gid}"))

        # Setup Location for test_guild_id
        loc = await location_crud.create(self.session, obj_in={
            "guild_id": self.test_guild_id, "static_id": "crud_test_loc",
            "name_i18n": {"en": "CRUD Test Location"}, "descriptions_i18n": {"en": "Desc"},
            "type": LocationType.GENERIC
        })
        self.test_loc_id = loc.id

        # Setup Party for test_guild_id
        party = await party_crud.create(self.session, obj_in={
            "guild_id": self.test_guild_id, "name": "CRUD Test Party",
            "current_location_id": self.test_loc_id
        })
        self.test_party_id = party.id

        await self.session.commit()


    async def asyncTearDown(self):
        if hasattr(self, 'session') and self.session:
            await self.session.rollback()
            await self.session.close()

    async def test_create_player_with_defaults(self):
        player = await player_crud.create_with_defaults(
            self.session, guild_id=self.test_guild_id, discord_id=201, name="Default Player",
            current_location_id=self.test_loc_id
        )
        self.assertIsNotNone(player, "player_crud.create_with_defaults returned None")
        if player: # Guard for Pyright
            self.assertIsNotNone(player.id)
            self.assertEqual(player.name, "Default Player")
            self.assertEqual(player.guild_id, self.test_guild_id)
            self.assertEqual(player.discord_id, 201)
            self.assertEqual(player.level, 1)
            self.assertEqual(player.xp, 0)
            self.assertEqual(player.gold, 0)
            self.assertEqual(player.current_status, PlayerStatus.IDLE)
            self.assertEqual(player.current_location_id, self.test_loc_id)
            # This specific check for empty attributes_json when no rule is set will be more explicitly
            # covered in test_create_player_with_defaults_no_base_attributes_rule.
            # Here, we just ensure it doesn't fail and has a dict.
            self.assertIsInstance(player.attributes_json, dict)


    async def test_create_player_with_defaults_no_base_attributes_rule(self):
        """Tests that attributes_json is empty if no 'character_attributes:base_values' rule exists."""
        # Ensure no rule exists (or it's empty) for this guild for the specific key
        # This is the default state unless a rule is explicitly added in another test or setup
        player = await player_crud.create_with_defaults(
            self.session, guild_id=self.test_guild_id, discord_id=250, name="NoAttrRulePlayer"
        )
        self.assertEqual(player.attributes_json, {}, "attributes_json should be empty when no rule is present")

    async def test_create_player_with_defaults_with_base_attributes_rule(self):
        """Tests that attributes_json is populated from 'character_attributes:base_values' rule."""
        base_attrs_rule = {"strength": 12, "dexterity": 10, "intelligence": 8}
        await update_rule_config(
            self.session,
            guild_id=self.test_guild_id,
            key="character_attributes:base_values",
            value=base_attrs_rule
        )
        await self.session.commit() # Ensure rule is saved before creating player

        player = await player_crud.create_with_defaults(
            self.session, guild_id=self.test_guild_id, discord_id=251, name="AttrRulePlayer"
        )
        self.assertEqual(player.attributes_json, base_attrs_rule)

        # Test with a different guild to ensure isolation
        other_guild_player = await player_crud.create_with_defaults(
            self.session, guild_id=self.other_guild_id, discord_id=252, name="OtherGuildAttrPlayer"
        )
        self.assertEqual(other_guild_player.attributes_json, {}, "Attributes rule for one guild should not affect another")


    async def test_get_player_by_discord_id(self):
        await player_crud.create_with_defaults(
            self.session, guild_id=self.test_guild_id, discord_id=202, name="Discord Player"
        )

        found_player = await player_crud.get_by_discord_id(self.session, guild_id=self.test_guild_id, discord_id=202)
        self.assertIsNotNone(found_player)
        if found_player: # Guard for Pyright
            self.assertEqual(found_player.name, "Discord Player")

        not_found_player = await player_crud.get_by_discord_id(self.session, guild_id=self.test_guild_id, discord_id=999)
        self.assertIsNone(not_found_player)

        wrong_guild_player = await player_crud.get_by_discord_id(self.session, guild_id=self.other_guild_id, discord_id=202)
        self.assertIsNone(wrong_guild_player)

    async def test_get_multi_by_location(self):
        assert self.test_loc_id is not None
        p1 = await player_crud.create_with_defaults(
            self.session, guild_id=self.test_guild_id, discord_id=203, name="LocPlayer1", current_location_id=self.test_loc_id
        )
        p2 = await player_crud.create_with_defaults(
            self.session, guild_id=self.test_guild_id, discord_id=204, name="LocPlayer2", current_location_id=self.test_loc_id
        )
        # Player in another location (or no location)
        await player_crud.create_with_defaults(
            self.session, guild_id=self.test_guild_id, discord_id=205, name="OtherLocPlayer"
        )

        players_in_loc = await player_crud.get_multi_by_location(self.session, guild_id=self.test_guild_id, location_id=self.test_loc_id)
        self.assertEqual(len(players_in_loc), 2)
        player_names = {p.name for p in players_in_loc}
        self.assertIn("LocPlayer1", player_names)
        self.assertIn("LocPlayer2", player_names)

        players_in_other_loc = await player_crud.get_multi_by_location(self.session, guild_id=self.test_guild_id, location_id=999)
        self.assertEqual(len(players_in_other_loc), 0)

    async def test_get_multi_by_party_id(self):
        assert self.test_party_id is not None
        p1_data = {"guild_id": self.test_guild_id, "discord_id": 206, "name": "PartyPlayer1", "current_party_id": self.test_party_id}
        p2_data = {"guild_id": self.test_guild_id, "discord_id": 207, "name": "PartyPlayer2", "current_party_id": self.test_party_id}

        p1 = await player_crud.create(self.session, obj_in=p1_data)
        p2 = await player_crud.create(self.session, obj_in=p2_data)

        # Player in another party (or no party)
        await player_crud.create_with_defaults(
            self.session, guild_id=self.test_guild_id, discord_id=208, name="OtherPartyPlayer"
        )

        players_in_party = await player_crud.get_multi_by_party_id(self.session, guild_id=self.test_guild_id, party_id=self.test_party_id)
        self.assertEqual(len(players_in_party), 2)
        player_names = {p.name for p in players_in_party}
        self.assertIn("PartyPlayer1", player_names)
        self.assertIn("PartyPlayer2", player_names)

        players_in_other_party = await player_crud.get_multi_by_party_id(self.session, guild_id=self.test_guild_id, party_id=999)
        self.assertEqual(len(players_in_other_party), 0)

    async def test_update_player(self):
        player = await player_crud.create_with_defaults(
            self.session, guild_id=self.test_guild_id, discord_id=209, name="UpdateMe"
        )
        update_data = {"name": "UpdatedName", "level": 5, "gold": 1000}
        updated_player = await player_crud.update(self.session, db_obj=player, obj_in=update_data)

        self.assertEqual(updated_player.name, "UpdatedName")
        self.assertEqual(updated_player.level, 5)
        self.assertEqual(updated_player.gold, 1000)
        self.assertEqual(updated_player.discord_id, 209) # Ensure other fields are unchanged

    async def test_delete_player(self):
        player = await player_crud.create_with_defaults(
            self.session, guild_id=self.test_guild_id, discord_id=210, name="DeleteMe"
        )
        player_id = player.id

        await player_crud.delete(self.session, id=player_id, guild_id=self.test_guild_id)
        deleted_player = await player_crud.get(self.session, id=player_id, guild_id=self.test_guild_id)
        self.assertIsNone(deleted_player)

        # Try deleting non-existent
        await player_crud.delete(self.session, id=9999, guild_id=self.test_guild_id) # Should not raise error

    async def test_get_by_id_and_guild(self):
        player = await player_crud.create_with_defaults(
            self.session, guild_id=self.test_guild_id, discord_id=211, name="GetMeGuild"
        )
        player_id = player.id

        found_player = await player_crud.get_by_id_and_guild(self.session, id=player_id, guild_id=self.test_guild_id)
        self.assertIsNotNone(found_player)
        if found_player: # Guard for Pyright
            self.assertEqual(found_player.name, "GetMeGuild")

        wrong_guild_player = await player_crud.get_by_id_and_guild(self.session, id=player_id, guild_id=self.other_guild_id)
        self.assertIsNone(wrong_guild_player)


if __name__ == "__main__":
    unittest.main()
