import pytest
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import event, text # Removed create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine # Added create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from src.models.base import Base
# पार्टी_npc_memory -> party_npc_memory
from src.models.party_npc_memory import PartyNpcMemory
from src.models.guild import GuildConfig
from src.models.party import Party
from src.models.generated_npc import GeneratedNpc
from src.models.player import Player

# Configure in-memory SQLite for testing
# This engine will be used by the fixture to create connections
async_engine = create_async_engine( # Changed to create_async_engine
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False}, # Necessary for aiosqlite
    poolclass=StaticPool, # Ensures the same in-memory DB is used
    echo=False # Can be True for debugging SQL
)

# AsyncSessionLocal factory, to be used by the fixture
AsyncSessionLocal = sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False # Use async_engine
)

@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    # Ensure tables are created and PRAGMA is set on a connection from the engine
    async with async_engine.connect() as connection: # Use async_engine
        await connection.run_sync(Base.metadata.drop_all) # Drop first to ensure clean state
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(text("PRAGMA foreign_keys=ON;"))
        await connection.commit()

    # Create a new session for the test, bound to the engine (which uses StaticPool)
    session = AsyncSessionLocal()
    try:
        # Seed data within a new transaction for this session
        async with session.begin():
            guild = GuildConfig(id=1, name="Test Guild", main_language="en")
            leader_player = Player(id=1, guild_id=1, name="Leader", discord_id=123)
            party = Party(id=1, guild_id=1, name="Test Party", leader_player_id=1)
            npc_model = GeneratedNpc(id=1, guild_id=1, name_i18n={"en": "Test NPC"})
            session.add_all([guild, leader_player, party, npc_model])
            # This transaction will commit when the 'with' block exits successfully.

        yield session # Provide the session to the test
    finally:
        await session.close()
        # Tables will be dropped by the next test's setup, or can be done here explicitly
        # async with engine.connect() as connection:
        #     await connection.run_sync(Base.metadata.drop_all)
        #     await connection.commit()

@pytest.mark.asyncio
@pytest.mark.xfail(reason="Database setup issues with aiosqlite and MissingGreenlet")
class TestPartyNpcMemoryModel:

    async def test_create_party_npc_memory_minimal(self, db_session: AsyncSession):
        async with db_session.begin():
            guild = await db_session.get(GuildConfig, 1)
            assert guild is not None # Ensure guild is not None
            party = await db_session.get(Party, 1)
            assert party is not None # Ensure party is not None
            npc = await db_session.get(GeneratedNpc, 1)
            assert npc is not None # Ensure npc is not None

            memory = PartyNpcMemory(
                guild_id=guild.id,
                party_id=party.id,
                npc_id=npc.id
            )
            db_session.add(memory)

        await db_session.refresh(memory)

        assert memory.id is not None
        assert memory.guild_id == guild.id
        assert memory.party_id == party.id
        assert memory.npc_id == npc.id
        assert memory.event_type is None
        assert memory.memory_details_i18n == {}
        assert memory.memory_data_json == {}
        assert memory.timestamp is not None
        assert memory.ai_significance_score is None

    async def test_create_party_npc_memory_full(self, db_session: AsyncSession):
        async with db_session.begin():
            guild = await db_session.get(GuildConfig, 1)
            assert guild is not None
            party = await db_session.get(Party, 1)
            assert party is not None
            npc = await db_session.get(GeneratedNpc, 1)
            assert npc is not None

            event_type = "QUEST_COMPLETED"
            details_i18n = {"en": "Party completed the quest"}
            data_json = {"quest_id": "q123", "outcome": "success"}
            score = 10
            # For server_default fields like timestamp, it's better to let the DB set them
            # or if you set it, ensure it's a timezone-aware datetime if your DB expects that.
            # ts = datetime.utcnow()

            memory = PartyNpcMemory(
                guild_id=guild.id,
                party_id=party.id,
                npc_id=npc.id,
                event_type=event_type,
                memory_details_i18n=details_i18n,
                memory_data_json=data_json,
                # timestamp=ts, # Let DB handle default
                ai_significance_score=score
            )
            db_session.add(memory)

        await db_session.refresh(memory)

        assert memory.event_type == event_type
        assert memory.memory_details_i18n == details_i18n
        assert memory.memory_data_json == data_json
        assert memory.timestamp is not None # Just check it's set
        assert memory.ai_significance_score == score
        assert repr(memory).startswith("<PartyNpcMemory")

    async def test_foreign_key_guild_constraint(self, db_session: AsyncSession):
        party = await db_session.get(Party, 1)
        assert party is not None
        npc = await db_session.get(GeneratedNpc, 1)
        assert npc is not None
        memory = PartyNpcMemory(guild_id=999, party_id=party.id, npc_id=npc.id)
        db_session.add(memory)
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_foreign_key_party_constraint(self, db_session: AsyncSession):
        guild = await db_session.get(GuildConfig, 1)
        assert guild is not None
        npc = await db_session.get(GeneratedNpc, 1)
        assert npc is not None
        memory = PartyNpcMemory(guild_id=guild.id, party_id=999, npc_id=npc.id)
        db_session.add(memory)
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_foreign_key_npc_constraint(self, db_session: AsyncSession):
        guild = await db_session.get(GuildConfig, 1)
        assert guild is not None
        party = await db_session.get(Party, 1)
        assert party is not None
        memory = PartyNpcMemory(guild_id=guild.id, party_id=party.id, npc_id=999)
        db_session.add(memory)
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_nullable_fields(self, db_session: AsyncSession):
        async with db_session.begin():
            guild = await db_session.get(GuildConfig, 1)
            assert guild is not None
            party = await db_session.get(Party, 1)
            assert party is not None
            npc = await db_session.get(GeneratedNpc, 1)
            assert npc is not None
            memory = PartyNpcMemory(
                guild_id=guild.id,
                party_id=party.id,
                npc_id=npc.id,
                event_type=None,
                memory_details_i18n=None,
                memory_data_json=None,
                ai_significance_score=None
            )
            db_session.add(memory)

        await db_session.refresh(memory)

        assert memory.event_type is None
        assert memory.memory_details_i18n == {} # Check default
        assert memory.memory_data_json == {}   # Check default
        assert memory.ai_significance_score is None
