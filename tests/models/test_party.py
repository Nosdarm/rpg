import sys
import os
import unittest
from typing import Optional, List

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy import event, JSON, select # Removed unused JSONB
from sqlalchemy.orm import selectinload
# from sqlalchemy.dialects.postgresql import JSONB # Not needed
from sqlalchemy.types import TypeDecorator, TEXT
from sqlalchemy.exc import IntegrityError

from backend.models.base import Base
from backend.models.guild import GuildConfig
from backend.models.location import Location, LocationType
from backend.models.player import Player, PlayerStatus
from backend.models.party import Party, PartyTurnStatus
# from backend.models.custom_types import JsonBForSQLite # Not directly used in this test file's logic after listener removal

# Redundant event listeners removed as models (Location, Player, Party)
# now use JsonBForSQLite directly for JSONB-like fields or standard JSON,
# which are compatible with SQLite.

class TestPartyModel(unittest.IsolatedAsyncioTestCase):
    engine: Optional[AsyncEngine] = None
    SessionLocal: Optional[async_sessionmaker[AsyncSession]] = None

    test_guild_id = 67890
    test_location_id: Optional[int] = None
    test_leader_player_id: Optional[int] = None
    sample_player_ids: List[int] = []

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
            guild = GuildConfig(id=self.test_guild_id, main_language="en", name="Test Guild For Party")
            self.session.add(guild)
            await self.session.commit()

        loc_stmt = select(Location).filter_by(guild_id=self.test_guild_id, static_id="party_loc")
        existing_loc = await self.session.execute(loc_stmt)
        party_loc = existing_loc.scalar_one_or_none()
        if not party_loc:
            party_loc = Location(
                guild_id=self.test_guild_id, static_id="party_loc",
                name_i18n={"en": "Party Camp"}, descriptions_i18n={"en": "A common meeting place."},
                type=LocationType.TAVERN
            )
            self.session.add(party_loc)
            await self.session.commit()
        self.test_location_id = party_loc.id

        leader_player_stmt = select(Player).filter_by(guild_id=self.test_guild_id, discord_id=2001)
        existing_leader = await self.session.execute(leader_player_stmt)
        leader_player = existing_leader.scalar_one_or_none()
        if not leader_player:
            leader_player = Player(guild_id=self.test_guild_id, discord_id=2001, name="PartyLeader")
            self.session.add(leader_player)
            await self.session.commit()
        self.test_leader_player_id = leader_player.id

        self.sample_player_ids = []
        for i in range(3):
            player_discord_id = 2002 + i
            player_stmt = select(Player).filter_by(guild_id=self.test_guild_id, discord_id=player_discord_id)
            existing_p = await self.session.execute(player_stmt)
            p = existing_p.scalar_one_or_none()
            if not p:
                p = Player(guild_id=self.test_guild_id, discord_id=player_discord_id, name=f"Member{i+1}")
                self.session.add(p)
                await self.session.commit()
            self.sample_player_ids.append(p.id)


    async def asyncTearDown(self):
        if hasattr(self, 'session') and self.session:
            await self.session.rollback()
            await self.session.close()

    async def test_create_party_minimal(self):
        party_data = {
            "guild_id": self.test_guild_id,
            "name": "The Minimalists",
        }
        party = Party(**party_data)
        self.session.add(party)
        await self.session.commit()
        await self.session.refresh(party)

        self.assertIsNotNone(party.id)
        self.assertEqual(party.guild_id, self.test_guild_id)
        self.assertEqual(party.name, "The Minimalists")
        self.assertIsNone(party.player_ids_json)
        self.assertIsNone(party.current_location_id)
        self.assertEqual(party.turn_status, PartyTurnStatus.IDLE)
        self.assertIsNone(party.leader_player_id)


    async def test_create_party_all_fields(self):
        party_data = {
            "guild_id": self.test_guild_id,
            "name": "The Maximalists",
            "player_ids_json": self.sample_player_ids,
            "leader_player_id": self.test_leader_player_id,
            "current_location_id": self.test_location_id,
            "turn_status": PartyTurnStatus.AWAITING_PARTY_ACTION
        }
        party = Party(**party_data)
        self.session.add(party)
        await self.session.commit()
        await self.session.refresh(party)

        stmt = select(Party).where(Party.id == party.id).options(
            selectinload(Party.location),
            selectinload(Party.leader),
            selectinload(Party.players)
        )
        result = await self.session.execute(stmt)
        retrieved_party = result.scalar_one_or_none()

        self.assertIsNotNone(retrieved_party)
        if retrieved_party is not None: # Explicit guard for Pyright
            for key, value in party_data.items():
                self.assertEqual(getattr(retrieved_party, key), value)

            self.assertIsNotNone(retrieved_party.location)
            if retrieved_party.location: # This inner guard is fine
                self.assertEqual(retrieved_party.location.id, self.test_location_id)

            self.assertIsNotNone(retrieved_party.leader)
            if retrieved_party.leader: # This inner guard is fine
                 self.assertEqual(retrieved_party.leader.id, self.test_leader_player_id)


    async def test_party_repr(self):
        party = Party(
            guild_id=self.test_guild_id,
            name="ReprParty",
            player_ids_json=[1, 2]
        )
        self.session.add(party)
        await self.session.commit()

        expected_repr = (f"<Party(id={party.id}, name='ReprParty', guild_id={self.test_guild_id}, "
                         f"member_count=2)>")
        self.assertEqual(repr(party), expected_repr)

    async def test_party_repr_no_members(self):
        party = Party(
            guild_id=self.test_guild_id,
            name="EmptyParty",
            player_ids_json=None
        )
        self.session.add(party)
        await self.session.commit()

        expected_repr = (f"<Party(id={party.id}, name='EmptyParty', guild_id={self.test_guild_id}, "
                         f"member_count=0)>")
        self.assertEqual(repr(party), expected_repr)


if __name__ == "__main__":
    unittest.main()
