import unittest
from typing import Optional, List

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy import event, JSON, select
from sqlalchemy.orm import selectinload # Added selectinload
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator, TEXT
from sqlalchemy.exc import IntegrityError

from src.models.base import Base
from src.models.guild import GuildConfig
from src.models.location import Location, LocationType # Removed LocationJsonBForSQLite
from src.models.player import Player, PlayerStatus # Player is needed for leader relationship
from src.models.party import Party, PartyTurnStatus
from src.models.custom_types import JsonBForSQLite # General custom type

# Apply JsonBForSQLite for SQLite testing if models don't handle it internally for all JSON types
@event.listens_for(Party.__table__, "column_reflect")
def _party_column_reflect(inspector, table, column_info):
    if column_info['name'] == 'player_ids_json' and isinstance(column_info['type'], JSON):
        # Party.player_ids_json is JSON, not JSONB in the model.
        pass

@event.listens_for(Location.__table__, "column_reflect")
def _location_column_reflect(inspector, table, column_info):
    if column_info['name'] in ['name_i18n', 'descriptions_i18n', 'coordinates_json', 'neighbor_locations_json', 'generated_details_json', 'ai_metadata_json']:
        if not isinstance(column_info['type'], JsonBForSQLite): # Changed LocationJsonBForSQLite to JsonBForSQLite
             column_info['type'] = JsonBForSQLite()

@event.listens_for(Player.__table__, "column_reflect")
def _player_column_reflect(inspector, table, column_info):
    if column_info['name'] == 'collected_actions_json' and isinstance(column_info['type'], JSON):
         pass


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
    async def tearDownClass(cls):
        if cls.engine:
            await cls.engine.dispose()

    async def asyncSetUp(self):
        assert self.SessionLocal is not None, "SessionLocal not initialized"
        self.session: AsyncSession = self.SessionLocal()

        assert self.engine is not None, "Engine not initialized"
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        # Setup GuildConfig
        guild_exists = await self.session.get(GuildConfig, self.test_guild_id)
        if not guild_exists:
            guild = GuildConfig(id=self.test_guild_id, main_language="en", name="Test Guild For Party")
            self.session.add(guild)
            await self.session.commit()

        # Setup Location
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

        # Setup a Player to be a leader
        leader_player_stmt = select(Player).filter_by(guild_id=self.test_guild_id, discord_id=2001)
        existing_leader = await self.session.execute(leader_player_stmt)
        leader_player = existing_leader.scalar_one_or_none()
        if not leader_player:
            leader_player = Player(guild_id=self.test_guild_id, discord_id=2001, name="PartyLeader")
            self.session.add(leader_player)
            await self.session.commit()
        self.test_leader_player_id = leader_player.id

        # Setup some sample players for player_ids_json
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
            # current_location_id, player_ids_json, turn_status should use defaults or be None
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
        for key, value in party_data.items():
            self.assertEqual(getattr(retrieved_party, key), value)

        # Check relationships
        self.assertIsNotNone(retrieved_party.location)
        if retrieved_party.location: # type guard
            self.assertEqual(retrieved_party.location.id, self.test_location_id)

        self.assertIsNotNone(retrieved_party.leader)
        if retrieved_party.leader: # type guard
             self.assertEqual(retrieved_party.leader.id, self.test_leader_player_id)

        # players relationship might need players to have current_party_id set to this party's id
        # For this model test, we primarily test if the fields are set correctly.
        # Testing the back-population of Player.party would be more of an integration test
        # or a test for the service layer that manages party joining.


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
            player_ids_json=None # or []
        )
        self.session.add(party)
        await self.session.commit()

        expected_repr = (f"<Party(id={party.id}, name='EmptyParty', guild_id={self.test_guild_id}, "
                         f"member_count=0)>")
        self.assertEqual(repr(party), expected_repr)


if __name__ == "__main__":
    unittest.main()
