import sys
import os
import pytest
import pytest_asyncio
import json
from typing import AsyncGenerator # Import AsyncGenerator

# Add the project root to sys.path FIRST
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import Column, Integer, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm.attributes import flag_modified


from src.models.base import Base
from src.models.custom_types import JsonBForSQLite

# --- Test Model using JsonBForSQLite ---
class JsonTestModel(Base):
    __tablename__ = "json_test_table_custom_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    json_data: Mapped[dict] = mapped_column(JsonBForSQLite, nullable=True)
    json_list_data: Mapped[list] = mapped_column(JsonBForSQLite, nullable=True)

# --- Fixtures ---
@pytest_asyncio.fixture # Default scope is "function"
async def db_engine_custom_types():
    # Using a unique name for in-memory DB for each test function to ensure isolation
    # if tests were to run in parallel or if state leaks.
    # For serial execution and function scope, :memory: is usually fine.
    # cache=shared is important for in-memory to be accessible across connections in the same "process".
    engine = create_async_engine(f"sqlite+aiosqlite:///:memory:?cache=shared", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session_custom_types(db_engine_custom_types) -> AsyncGenerator[AsyncSession, None]:
    SessionLocal = async_sessionmaker(
        bind=db_engine_custom_types, class_=AsyncSession, expire_on_commit=False
    )
    async with SessionLocal() as session:
        yield session

# --- Tests for JsonBForSQLite ---

@pytest.mark.asyncio
async def test_jsonb_for_sqlite_stores_and_retrieves_dict(db_session_custom_types: AsyncSession):
    """Test storing and retrieving a dictionary."""
    test_dict = {"key": "value", "number": 123, "nested": {"n_key": "n_value"}}
    new_entry = JsonTestModel(json_data=test_dict)
    db_session_custom_types.add(new_entry)
    await db_session_custom_types.commit()
    await db_session_custom_types.refresh(new_entry)

    retrieved_entry = await db_session_custom_types.get(JsonTestModel, new_entry.id)
    assert retrieved_entry is not None
    assert retrieved_entry.json_data == test_dict

@pytest.mark.asyncio
async def test_jsonb_for_sqlite_stores_and_retrieves_list(db_session_custom_types: AsyncSession):
    """Test storing and retrieving a list."""
    test_list = [1, "string", {"item_key": "item_value"}, None]
    new_entry = JsonTestModel(json_list_data=test_list)
    db_session_custom_types.add(new_entry)
    await db_session_custom_types.commit()
    await db_session_custom_types.refresh(new_entry)

    retrieved_entry = await db_session_custom_types.get(JsonTestModel, new_entry.id)
    assert retrieved_entry is not None
    assert retrieved_entry.json_list_data == test_list

@pytest.mark.asyncio
async def test_jsonb_for_sqlite_stores_and_retrieves_null(db_session_custom_types: AsyncSession):
    """Test storing and retrieving NULL for a JSONB field."""
    new_entry = JsonTestModel(json_data=None, json_list_data=None)
    db_session_custom_types.add(new_entry)
    await db_session_custom_types.commit()
    await db_session_custom_types.refresh(new_entry)

    retrieved_entry = await db_session_custom_types.get(JsonTestModel, new_entry.id)
    assert retrieved_entry is not None
    assert retrieved_entry.json_data is None
    assert retrieved_entry.json_list_data is None

@pytest.mark.asyncio
async def test_jsonb_for_sqlite_stores_empty_dict_and_list(db_session_custom_types: AsyncSession):
    """Test storing and retrieving empty dictionary and list."""
    new_entry = JsonTestModel(json_data={}, json_list_data=[])
    db_session_custom_types.add(new_entry)
    await db_session_custom_types.commit()
    await db_session_custom_types.refresh(new_entry)

    retrieved_entry = await db_session_custom_types.get(JsonTestModel, new_entry.id)
    assert retrieved_entry is not None
    assert retrieved_entry.json_data == {}
    assert retrieved_entry.json_list_data == []

@pytest.mark.asyncio
async def test_jsonb_for_sqlite_update_json_field(db_session_custom_types: AsyncSession):
    """Test updating a JSON field."""
    initial_dict = {"original_key": "original_value"}
    entry = JsonTestModel(json_data=initial_dict)
    db_session_custom_types.add(entry)
    await db_session_custom_types.commit()
    await db_session_custom_types.refresh(entry)

    entry_id = entry.id
    db_session_custom_types.expire_all() # Corrected: expire_all is synchronous

    retrieved_for_update = await db_session_custom_types.get(JsonTestModel, entry_id)
    assert retrieved_for_update is not None

    updated_dict = {"new_key": "new_value", "updated_original": "yes"}
    retrieved_for_update.json_data = updated_dict
    flag_modified(retrieved_for_update, "json_data")
    await db_session_custom_types.commit()

    final_entry = await db_session_custom_types.get(JsonTestModel, entry_id)
    assert final_entry is not None
    assert final_entry.json_data == updated_dict

@pytest.mark.asyncio
async def test_jsonb_for_sqlite_with_real_json_strings_if_needed(db_session_custom_types: AsyncSession):
    json_string_dict = '{"name": "Test JSON String", "valid": true}'
    json_string_list = '[10, "mixed", false, {"obj": "val"}]'

    parsed_dict = json.loads(json_string_dict)
    parsed_list = json.loads(json_string_list)

    new_entry = JsonTestModel(json_data=parsed_dict, json_list_data=parsed_list)
    db_session_custom_types.add(new_entry)
    await db_session_custom_types.commit()
    await db_session_custom_types.refresh(new_entry)

    retrieved_entry = await db_session_custom_types.get(JsonTestModel, new_entry.id)
    assert retrieved_entry is not None
    assert retrieved_entry.json_data == parsed_dict
    assert retrieved_entry.json_list_data == parsed_list

    assert json.dumps(retrieved_entry.json_data, sort_keys=True) == json.dumps(parsed_dict, sort_keys=True)
    assert json.dumps(retrieved_entry.json_list_data, sort_keys=True) == json.dumps(parsed_list, sort_keys=True)
