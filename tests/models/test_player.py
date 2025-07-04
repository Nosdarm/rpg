import unittest
from typing import Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy import event, JSON, select
from sqlalchemy.orm import selectinload # Added selectinload
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator, TEXT
from sqlalchemy.exc import IntegrityError

from src.models.base import Base
from src.models.guild import GuildConfig
from src.models.location import Location, LocationType # Removed JsonBForSQLite alias
from src.models.party import Party, PartyTurnStatus # Removed JsonBForSQLite alias
from src.models.player import Player, PlayerStatus
from src.models.custom_types import JsonBForSQLite # General custom type for Player model


# Apply JsonBForSQLite to relevant columns for SQLite testing if not already handled by the model itself
# This might be redundant if models correctly use JsonBForSQLite or if tests use PostgreSQL
@event.listens_for(Player.__table__, "column_reflect")
def _player_column_reflect(inspector, table, column_info):
    if column_info['name'] == 'collected_actions_json' and isinstance(column_info['type'], JSON):
         # In models, collected_actions_json is JSON, not JSONB. If it were JSONB:
         # column_info['type'] = JsonBForSQLite()
         pass # It's already JSON, compatible with SQLite's JSON type.

@event.listens_for(Location.__table__, "column_reflect")
def _location_column_reflect(inspector, table, column_info):
    # Ensure Location's JSONB fields are handled for SQLite if Location model itself doesn't use JsonBForSQLite
    # This is more of a safeguard for dependent models in tests
    if column_info['name'] in ['name_i18n', 'descriptions_i18n', 'coordinates_json', 'neighbor_locations_json', 'generated_details_json', 'ai_metadata_json']:
        if not isinstance(column_info['type'], JsonBForSQLite): # Changed LocationJsonBForSQLite to JsonBForSQLite
             column_info['type'] = JsonBForSQLite()


@event.listens_for(Party.__table__, "column_reflect")
def _party_column_reflect(inspector, table, column_info):
    if column_info['name'] == 'player_ids_json' and isinstance(column_info['type'], JSON):
        # In models, player_ids_json is JSON, not JSONB.
        pass


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
    def tearDownClass(cls): # Changed to sync
        if cls.engine:
            import asyncio
            asyncio.run(cls.engine.dispose()) # Run async dispose

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
            guild = GuildConfig(id=self.test_guild_id, main_language="en", name="Test Guild")
            self.session.add(guild)
            await self.session.commit()

        # Setup Location
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

        # Setup Party (Optional, for players who might be in a party)
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
            # selected_language, xp, level, etc., should use defaults
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
        self.assertIsNone(player.collected_actions_json)
        self.assertIsNone(player.current_party_id)
        self.assertIsNone(player.current_location_id) # Not provided, should be None

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
        for key, value in player_data.items():
            self.assertEqual(getattr(retrieved_player, key), value)

        # Check relationships
        self.assertIsNotNone(retrieved_player.location)
        if retrieved_player.location: # type guard
            self.assertEqual(retrieved_player.location.id, self.test_location_id)

        self.assertIsNotNone(retrieved_player.party)
        if retrieved_player.party: # type guard
             self.assertEqual(retrieved_player.party.id, self.test_party_id)


    async def test_player_unique_constraint_guild_discord_id(self):
        common_discord_id = 1003
        player1 = Player(guild_id=self.test_guild_id, discord_id=common_discord_id, name="Player1")
        self.session.add(player1)
        await self.session.commit()

        player2_data = {"guild_id": self.test_guild_id, "discord_id": common_discord_id, "name": "Player2"}
        player2 = Player(**player2_data)
        self.session.add(player2)
        with self.assertRaises(IntegrityError): # Specific to SQLAlchemy dialects, e.g. psycopg2.errors.UniqueViolation
            await self.session.commit()
        await self.session.rollback() # Important to rollback after expected error

        # Should be able to add if guild_id is different
        player3_data = {"guild_id": self.test_guild_id + 1, "discord_id": common_discord_id, "name": "Player3"}
         # Need to create the other guild first
        other_guild = GuildConfig(id=self.test_guild_id + 1, main_language="de", name="Other Guild")
        self.session.add(other_guild)
        await self.session.commit()

        player3 = Player(**player3_data)
        self.session.add(player3)
        await self.session.commit() # Should not raise error
        self.assertIsNotNone(player3.id)


    async def test_player_repr(self):
        player = Player(
            guild_id=self.test_guild_id,
            discord_id=1004,
            name="ReprPlayer",
            level=5
        )
        self.session.add(player)
        await self.session.commit() # ID is assigned after commit

        expected_repr = (f"<Player(id={player.id}, name='ReprPlayer', guild_id={self.test_guild_id}, "
                         f"discord_id=1004, level=5)>")
        self.assertEqual(repr(player), expected_repr)

if __name__ == "__main__":
    unittest.main()
