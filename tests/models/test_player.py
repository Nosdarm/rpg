import sys
import os
import unittest
from typing import Optional, List, Dict, Any # Added Dict, Any

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy import event, JSON, select # Removed unused JSONB
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
# from sqlalchemy.dialects.postgresql import JSONB # Not needed
from sqlalchemy.types import TypeDecorator, TEXT
from sqlalchemy.exc import IntegrityError

from src.models.base import Base
from src.models.guild import GuildConfig
from src.models.location import Location, LocationType
from src.models.party import Party, PartyTurnStatus
from src.models.player import Player, PlayerStatus
# from src.models.custom_types import JsonBForSQLite # Not directly used here if models handle their types

# Redundant event listeners removed as models (Location, Player, Party)
# now use JsonBForSQLite directly for JSONB-like fields or standard JSON.

class TestPlayerModel(unittest.IsolatedAsyncioTestCase):
    engine: Optional[AsyncEngine] = None
    SessionLocal: Optional[async_sessionmaker[AsyncSession]] = None

    test_guild_id = 12345
    test_location_id: Optional[int] = None
    test_party_id: Optional[int] = None

    @classmethod
    def setUpClass(cls):
        cls.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        cls.SessionLocal = async_sessionmaker(
            bind=cls.engine, class_=AsyncSession, expire_on_commit=False
        )

    @classmethod
    def tearDownClass(cls):
        if cls.engine:
            import asyncio
            asyncio.run(cls.engine.dispose())

    async def asyncSetUp(self):
        assert self.SessionLocal is not None, "SessionLocal not initialized"
        self.session: AsyncSession = self.SessionLocal()

        assert self.engine is not None, "Engine not initialized"
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        guild_exists = await self.session.get(GuildConfig, self.test_guild_id)
        if not guild_exists:
            guild = GuildConfig(id=self.test_guild_id, main_language="en", name="Test Guild")
            self.session.add(guild)
            await self.session.commit()

        loc_stmt = select(Location).filter_by(guild_id=self.test_guild_id, static_id="test_start_loc")
        existing_loc = await self.session.execute(loc_stmt)
        start_loc = existing_loc.scalar_one_or_none()
        if not start_loc:
            start_loc = Location(
                guild_id=self.test_guild_id, static_id="test_start_loc",
                name_i18n={"en": "Starting Area"}, descriptions_i18n={"en": "A place to start"},
                type=LocationType.GENERIC
            )
            self.session.add(start_loc)
            await self.session.commit()
        self.test_location_id = start_loc.id

        party_stmt = select(Party).filter_by(guild_id=self.test_guild_id, name="Initial Party")
        existing_party = await self.session.execute(party_stmt)
        party_obj = existing_party.scalar_one_or_none()
        if not party_obj:
            party_obj = Party(
                guild_id=self.test_guild_id, name="Initial Party",
                current_location_id=self.test_location_id,
                player_ids_json=[], turn_status=PartyTurnStatus.IDLE
            )
            self.session.add(party_obj)
            await self.session.commit()
        self.test_party_id = party_obj.id


    async def asyncTearDown(self):
        if hasattr(self, 'session') and self.session:
            await self.session.rollback()
            await self.session.close()

    async def test_create_player_minimal(self):
        player_data = {
            "guild_id": self.test_guild_id,
            "discord_id": 1001,
            "name": "MinimalPlayer"
        }
        player = Player(**player_data)
        self.session.add(player)
        await self.session.commit()
        await self.session.refresh(player)

        self.assertIsNotNone(player.id)
        self.assertEqual(player.guild_id, self.test_guild_id)
        self.assertEqual(player.discord_id, 1001)
        self.assertEqual(player.name, "MinimalPlayer")
        self.assertEqual(player.selected_language, "en")
        self.assertEqual(player.xp, 0)
        self.assertEqual(player.level, 1)
        self.assertEqual(player.unspent_xp, 0)
        self.assertEqual(player.gold, 0)
        self.assertEqual(player.current_status, PlayerStatus.IDLE)
        self.assertIsNone(player.current_hp)
        self.assertEqual(player.attributes_json, {})
        self.assertIsNone(player.collected_actions_json)
        self.assertIsNone(player.current_party_id)
        self.assertIsNone(player.current_location_id)

    async def test_create_player_all_fields(self):
        player_data = {
            "guild_id": self.test_guild_id,
            "discord_id": 1002,
            "name": "MaximalPlayer",
            "current_location_id": self.test_location_id,
            "selected_language": "ru",
            "xp": 100,
            "level": 2,
            "unspent_xp": 10,
            "gold": 50,
            "current_hp": 95,
            "current_status": PlayerStatus.EXPLORING,
            "attributes_json": {"strength": 10, "dexterity": 8},
            "collected_actions_json": [{"action": "look", "target": "around"}],
            "current_party_id": self.test_party_id,
            "current_sublocation_name": "The Dusty Corner"
        }
        player = Player(**player_data)
        self.session.add(player)
        await self.session.commit()
        await self.session.refresh(player)

        stmt = select(Player).where(Player.id == player.id).options(
            selectinload(Player.location), selectinload(Player.party)
        )
        result = await self.session.execute(stmt)
        retrieved_player = result.scalar_one_or_none()

        self.assertIsNotNone(retrieved_player)
        if retrieved_player is not None: # Explicit guard for Pyright
            for key, value in player_data.items():
                self.assertEqual(getattr(retrieved_player, key), value)

            self.assertIsNotNone(retrieved_player.location)
            if retrieved_player.location: # This inner guard is fine
                self.assertEqual(retrieved_player.location.id, self.test_location_id)

            self.assertIsNotNone(retrieved_player.party)
            if retrieved_player.party: # This inner guard is fine
                 self.assertEqual(retrieved_player.party.id, self.test_party_id)


    async def test_player_unique_constraint_guild_discord_id(self):
        common_discord_id = 1003
        player1 = Player(guild_id=self.test_guild_id, discord_id=common_discord_id, name="Player1")
        self.session.add(player1)
        await self.session.commit()

        player2_data = {"guild_id": self.test_guild_id, "discord_id": common_discord_id, "name": "Player2"}
        player2 = Player(**player2_data)
        self.session.add(player2)
        with self.assertRaises(IntegrityError):
            await self.session.commit()
        await self.session.rollback()

        player3_data = {"guild_id": self.test_guild_id + 1, "discord_id": common_discord_id, "name": "Player3"}
        other_guild = await self.session.get(GuildConfig, self.test_guild_id + 1)
        if not other_guild:
            other_guild = GuildConfig(id=self.test_guild_id + 1, main_language="de", name="Other Guild")
            self.session.add(other_guild)
            await self.session.commit()

        player3 = Player(**player3_data)
        self.session.add(player3)
        await self.session.commit()
        self.assertIsNotNone(player3.id)


    async def test_player_repr(self):
        player = Player(
            guild_id=self.test_guild_id,
            discord_id=1004,
            name="ReprPlayer",
            level=5
        )
        self.session.add(player)
        await self.session.commit()

        expected_repr = (f"<Player(id={player.id}, name='ReprPlayer', guild_id={self.test_guild_id}, "
                         f"discord_id=1004, level=5)>")
        self.assertEqual(repr(player), expected_repr)

    async def test_player_attributes_json_default_is_new_dict(self):
        """Tests that the default for attributes_json is a new dict instance each time."""
        player1_data = {
            "guild_id": self.test_guild_id,
            "discord_id": 2001, # Changed discord_id to avoid conflict if tests run in certain order
            "name": "AttrDefaultPlayer1"
        }
        player1 = Player(**player1_data)
        self.session.add(player1)

        player2_data = {
            "guild_id": self.test_guild_id,
            "discord_id": 2002, # Changed discord_id
            "name": "AttrDefaultPlayer2"
        }
        player2 = Player(**player2_data)
        self.session.add(player2)

        await self.session.commit()
        await self.session.refresh(player1)
        await self.session.refresh(player2)

        self.assertEqual(player1.attributes_json, {})
        self.assertEqual(player2.attributes_json, {})

        player1.attributes_json["strength"] = 12
        flag_modified(player1, "attributes_json")
        await self.session.commit()
        await self.session.refresh(player1)
        await self.session.refresh(player2)

        self.assertEqual(player1.attributes_json, {"strength": 12})
        self.assertEqual(player2.attributes_json, {}, "Modifying p1.attributes_json should not affect p2.attributes_json")
        self.assertIsNot(player1.attributes_json, player2.attributes_json, "attributes_json should be distinct objects")


if __name__ == "__main__":
    unittest.main()
