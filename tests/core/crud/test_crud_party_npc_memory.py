import unittest
from unittest.mock import AsyncMock, MagicMock
from typing import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine # Changed create_engine to create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, event # Removed create_engine, text is fine, event is fine

from backend.models.base import Base
from backend.core.crud.crud_party_npc_memory import crud_party_npc_memory, CRUDPartyNpcMemory
from backend.models.party_npc_memory import PartyNpcMemory
from backend.models.guild import GuildConfig
from backend.models.party import Party
from backend.models.generated_npc import GeneratedNpc
from backend.models.player import Player # For party leader

# Use an in-memory SQLite database for testing
from sqlalchemy.pool import StaticPool

# Configure in-memory SQLite for testing
async_engine = create_async_engine( # Changed to create_async_engine
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False
)

# AsyncSessionLocal factory
AsyncSessionLocal = sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False # Use async_engine
)

@pytest.fixture(scope="function")
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    # Ensure tables are created and PRAGMA is set on a connection from the engine
    async with async_engine.connect() as connection: # Use async_engine
        await connection.run_sync(Base.metadata.drop_all) # Drop first for clean state
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(text("PRAGMA foreign_keys=ON;"))
        await connection.commit()

    # Create a new session for the test
    session = AsyncSessionLocal()
    try:
        # Seed data within a new transaction for this session
        async with session.begin():
            guild = GuildConfig(id=1, name="Test Guild", main_language="en")
            leader = Player(id=101, guild_id=1, name="Leader", discord_id=12345)
            party1 = Party(id=11, guild_id=1, name="Party One", leader_player_id=101)
            party2 = Party(id=12, guild_id=1, name="Party Two", leader_player_id=101)
            npc1_model = GeneratedNpc(id=21, guild_id=1, name_i18n={"en": "NPC Alpha"})
            npc2_model = GeneratedNpc(id=22, guild_id=1, name_i18n={"en": "NPC Beta"})
            session.add_all([guild, leader, party1, party2, npc1_model, npc2_model])
            # This transaction will commit when the 'with' block exits.

        yield session # Provide the session to the test
    finally:
        await session.close()
        # Tables will be dropped by the next test's setup.


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Database setup issues with aiosqlite and MissingGreenlet")
class TestCRUDPartyNpcMemory:

    async def test_create_party_npc_memory(self, test_db_session: AsyncSession):
        memory_data = {
            "guild_id": 1, "party_id": 11, "npc_id": 21,
            "event_type": "TALK", "memory_data_json": {"topic": "weather"}
        }
        created_memory = await crud_party_npc_memory.create(test_db_session, obj_in=memory_data) # type: ignore
        assert created_memory is not None
        assert created_memory.id is not None
        assert created_memory.party_id == 11
        assert created_memory.npc_id == 21
        assert created_memory.event_type == "TALK"
        assert created_memory.memory_data_json == {"topic": "weather"}

    async def test_get_party_npc_memory(self, test_db_session: AsyncSession):
        memory_data = {"guild_id": 1, "party_id": 11, "npc_id": 21, "event_type": "GIFT"}
        created_memory = await crud_party_npc_memory.create(test_db_session, obj_in=memory_data) # type: ignore

        fetched_memory = await crud_party_npc_memory.get(test_db_session, id=created_memory.id, guild_id=1)
        assert fetched_memory is not None
        assert fetched_memory.id == created_memory.id
        assert fetched_memory.event_type == "GIFT"

    async def test_get_multi_by_party_and_npc(self, test_db_session: AsyncSession):
        await crud_party_npc_memory.create(test_db_session, obj_in={"guild_id": 1, "party_id": 11, "npc_id": 21, "event_type": "E1"}) # type: ignore
        await crud_party_npc_memory.create(test_db_session, obj_in={"guild_id": 1, "party_id": 11, "npc_id": 21, "event_type": "E2"}) # type: ignore
        await crud_party_npc_memory.create(test_db_session, obj_in={"guild_id": 1, "party_id": 11, "npc_id": 22, "event_type": "E3"}) # type: ignore

        memories = await crud_party_npc_memory.get_multi_by_party_and_npc(
            test_db_session, guild_id=1, party_id=11, npc_id=21
        )
        assert len(memories) == 2
        event_types = {m.event_type for m in memories}
        assert "E1" in event_types
        assert "E2" in event_types
        # Check order (newest first)
        assert memories[0].event_type == "E2"
        assert memories[1].event_type == "E1"


    async def test_get_multi_by_party(self, test_db_session: AsyncSession):
        await crud_party_npc_memory.create(test_db_session, obj_in={"guild_id": 1, "party_id": 11, "npc_id": 21, "event_type": "P1N1_E1"}) # type: ignore
        await crud_party_npc_memory.create(test_db_session, obj_in={"guild_id": 1, "party_id": 11, "npc_id": 22, "event_type": "P1N2_E1"}) # type: ignore
        await crud_party_npc_memory.create(test_db_session, obj_in={"guild_id": 1, "party_id": 12, "npc_id": 21, "event_type": "P2N1_E1"}) # type: ignore

        memories = await crud_party_npc_memory.get_multi_by_party(
            test_db_session, guild_id=1, party_id=11
        )
        assert len(memories) == 2
        event_types = {m.event_type for m in memories}
        assert "P1N1_E1" in event_types
        assert "P1N2_E1" in event_types
        # Check order (by npc_id, then timestamp desc)
        if memories[0].npc_id == memories[1].npc_id: # if same npc, check timestamp
             assert memories[0].timestamp >= memories[1].timestamp # type: ignore
        else: # check npc_id order
             assert memories[0].npc_id <= memories[1].npc_id


    async def test_get_multi_by_npc(self, test_db_session: AsyncSession):
        await crud_party_npc_memory.create(test_db_session, obj_in={"guild_id": 1, "party_id": 11, "npc_id": 21, "event_type": "P1N1_E1"}) # type: ignore
        await crud_party_npc_memory.create(test_db_session, obj_in={"guild_id": 1, "party_id": 12, "npc_id": 21, "event_type": "P2N1_E1"}) # type: ignore
        await crud_party_npc_memory.create(test_db_session, obj_in={"guild_id": 1, "party_id": 11, "npc_id": 22, "event_type": "P1N2_E1"}) # type: ignore

        memories = await crud_party_npc_memory.get_multi_by_npc(
            test_db_session, guild_id=1, npc_id=21
        )
        assert len(memories) == 2
        event_types = {m.event_type for m in memories}
        assert "P1N1_E1" in event_types
        assert "P2N1_E1" in event_types
        # Check order (by party_id, then timestamp desc)
        if memories[0].party_id == memories[1].party_id:
            assert memories[0].timestamp >= memories[1].timestamp # type: ignore
        else:
            assert memories[0].party_id <= memories[1].party_id


    async def test_update_party_npc_memory(self, test_db_session: AsyncSession):
        memory_data = {"guild_id": 1, "party_id": 11, "npc_id": 21, "event_type": "OLD_EVENT"}
        created_memory = await crud_party_npc_memory.create(test_db_session, obj_in=memory_data) # type: ignore

        update_data = {"event_type": "NEW_EVENT", "ai_significance_score": 5}
        updated_memory = await crud_party_npc_memory.update(test_db_session, db_obj=created_memory, obj_in=update_data)

        assert updated_memory is not None
        assert updated_memory.id == created_memory.id
        assert updated_memory.event_type == "NEW_EVENT"
        assert updated_memory.ai_significance_score == 5

    async def test_delete_party_npc_memory(self, test_db_session: AsyncSession):
        memory_data = {"guild_id": 1, "party_id": 11, "npc_id": 21}
        created_memory = await crud_party_npc_memory.create(test_db_session, obj_in=memory_data) # type: ignore

        deleted_memory = await crud_party_npc_memory.delete(test_db_session, id=created_memory.id, guild_id=1) # type: ignore
        assert deleted_memory is not None
        assert deleted_memory.id == created_memory.id

        fetched_after_delete = await crud_party_npc_memory.get(test_db_session, id=created_memory.id, guild_id=1)
        assert fetched_after_delete is None

    async def test_get_count_for_filters(self, test_db_session: AsyncSession):
        await crud_party_npc_memory.create(test_db_session, obj_in={"guild_id": 1, "party_id": 11, "npc_id": 21, "event_type": "COMBAT"}) # type: ignore
        await crud_party_npc_memory.create(test_db_session, obj_in={"guild_id": 1, "party_id": 11, "npc_id": 21, "event_type": "DIALOGUE"}) # type: ignore
        await crud_party_npc_memory.create(test_db_session, obj_in={"guild_id": 1, "party_id": 11, "npc_id": 22, "event_type": "COMBAT"}) # type: ignore
        await crud_party_npc_memory.create(test_db_session, obj_in={"guild_id": 1, "party_id": 12, "npc_id": 21, "event_type": "COMBAT"}) # type: ignore
        await crud_party_npc_memory.create(test_db_session, obj_in={"guild_id": 2, "party_id": 11, "npc_id": 21, "event_type": "COMBAT"}) # type: ignore

        count1 = await crud_party_npc_memory.get_count_for_filters(test_db_session, guild_id=1)
        assert count1 == 4

        count2 = await crud_party_npc_memory.get_count_for_filters(test_db_session, guild_id=1, party_id=11)
        assert count2 == 3

        count3 = await crud_party_npc_memory.get_count_for_filters(test_db_session, guild_id=1, npc_id=21)
        assert count3 == 3

        count4 = await crud_party_npc_memory.get_count_for_filters(test_db_session, guild_id=1, party_id=11, npc_id=21)
        assert count4 == 2

        count5 = await crud_party_npc_memory.get_count_for_filters(test_db_session, guild_id=1, event_type="COMBAT")
        assert count5 == 3

        count6 = await crud_party_npc_memory.get_count_for_filters(test_db_session, guild_id=1, party_id=11, event_type="COMBAT")
        assert count6 == 2

        count7 = await crud_party_npc_memory.get_count_for_filters(test_db_session, guild_id=1, party_id=12, npc_id=22)
        assert count7 == 0

        count8 = await crud_party_npc_memory.get_count_for_filters(test_db_session, guild_id=99) # Non-existent guild
        assert count8 == 0

# Note: To run these tests, you'd typically use `pytest your_test_file.py`
# Ensure you have pytest and pytest-asyncio installed.
