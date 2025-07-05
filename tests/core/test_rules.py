import sys
import os
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from typing import AsyncGenerator # Import AsyncGenerator

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import event, JSON, select

from src.models.base import Base
from src.models.guild import GuildConfig
from src.models.rule_config import RuleConfig
from src.core.rules import (
    load_rules_config_for_guild,
    get_rule,
    update_rule_config,
    get_all_rules_for_guild,
    _rules_cache
)
# JsonBForSQLite and specific listeners for RuleConfig's JSONB fields are not needed
# as RuleConfig.value_json is standard JSON. Other models using JSONB-like fields
# have been updated to use JsonBForSQLite directly.

DEFAULT_GUILD_ID = 1
OTHER_GUILD_ID = 2

@pytest.fixture(autouse=True)
def clear_rules_cache_before_each_test():
    _rules_cache.clear()
    yield
    _rules_cache.clear()

@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:?cache=shared", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    SessionLocal = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with SessionLocal() as session:
        guild1_data = {"id":DEFAULT_GUILD_ID, "name":"Test Guild 1", "main_language":"en"}
        guild2_data = {"id":OTHER_GUILD_ID, "name":"Test Guild 2", "main_language":"fr"}

        await session.merge(GuildConfig(**guild1_data))
        await session.merge(GuildConfig(**guild2_data))
        await session.commit()
        yield session


# --- Tests for load_rules_config_for_guild ---
@pytest.mark.asyncio
async def test_load_rules_config_empty_db(db_session: AsyncSession):
    rules = await load_rules_config_for_guild(db_session, DEFAULT_GUILD_ID)
    assert rules == {}
    assert _rules_cache.get(DEFAULT_GUILD_ID) == {}

@pytest.mark.asyncio
async def test_load_rules_config_populates_cache(db_session: AsyncSession):
    rule1_data = {"guild_id": DEFAULT_GUILD_ID, "key": "test_key1", "value_json": {"data": "value1"}}
    rule2_data = {"guild_id": DEFAULT_GUILD_ID, "key": "test_key2", "value_json": True}
    db_session.add(RuleConfig(**rule1_data))
    db_session.add(RuleConfig(**rule2_data))
    await db_session.commit()

    assert DEFAULT_GUILD_ID not in _rules_cache
    rules = await load_rules_config_for_guild(db_session, DEFAULT_GUILD_ID)

    expected_rules = {"test_key1": {"data": "value1"}, "test_key2": True}
    assert rules == expected_rules
    assert _rules_cache[DEFAULT_GUILD_ID] == expected_rules

# --- Tests for get_rule ---
@pytest.mark.asyncio
async def test_get_rule_cache_hit(db_session: AsyncSession):
    _rules_cache[DEFAULT_GUILD_ID] = {"cached_key": "cached_value"}

    with patch("src.core.rules.load_rules_config_for_guild", new_callable=AsyncMock) as mock_load_rules:
        value = await get_rule(db_session, DEFAULT_GUILD_ID, "cached_key", "default")
        assert value == "cached_value"
        mock_load_rules.assert_not_called()

@pytest.mark.asyncio
async def test_get_rule_cache_miss_loads_and_returns(db_session: AsyncSession):
    rule_data = {"guild_id": DEFAULT_GUILD_ID, "key": "db_key", "value_json": "db_value"}
    db_session.add(RuleConfig(**rule_data))
    await db_session.commit()

    assert DEFAULT_GUILD_ID not in _rules_cache
    value = await get_rule(db_session, DEFAULT_GUILD_ID, "db_key", "default")
    assert value == "db_value"
    assert _rules_cache[DEFAULT_GUILD_ID] == {"db_key": "db_value"}

@pytest.mark.asyncio
async def test_get_rule_key_not_found_returns_default(db_session: AsyncSession):
    value = await get_rule(db_session, DEFAULT_GUILD_ID, "non_existent_key", "default_val")
    assert value == "default_val"
    assert _rules_cache.get(DEFAULT_GUILD_ID) == {}

@pytest.mark.asyncio
async def test_get_rule_none_default(db_session: AsyncSession):
    value = await get_rule(db_session, DEFAULT_GUILD_ID, "another_key")
    assert value is None

# --- Tests for update_rule_config ---
@pytest.mark.asyncio
async def test_update_rule_config_creates_new_rule(db_session: AsyncSession):
    key, value = "new_rule_key", {"setting": True}

    assert _rules_cache.get(DEFAULT_GUILD_ID) is None

    created_rule = await update_rule_config(db_session, DEFAULT_GUILD_ID, key, value)

    assert created_rule is not None
    assert created_rule.guild_id == DEFAULT_GUILD_ID
    assert created_rule.key == key
    assert created_rule.value_json == value

    await db_session.commit()
    await db_session.refresh(created_rule)

    stmt = select(RuleConfig).where(RuleConfig.guild_id == DEFAULT_GUILD_ID, RuleConfig.key == key)
    result = await db_session.execute(stmt)
    rule_from_db = result.scalar_one_or_none()
    assert rule_from_db is not None
    assert rule_from_db.value_json == value

    assert _rules_cache[DEFAULT_GUILD_ID][key] == value

@pytest.mark.asyncio
async def test_update_rule_config_updates_existing_rule(db_session: AsyncSession):
    key = "existing_key"
    initial_value = {"setting": "initial"}
    updated_value = {"setting": "updated", "new_prop": 1}

    existing_rule_db = RuleConfig(guild_id=DEFAULT_GUILD_ID, key=key, value_json=initial_value)
    db_session.add(existing_rule_db)
    await db_session.commit()
    await db_session.refresh(existing_rule_db)

    _rules_cache[DEFAULT_GUILD_ID] = {key: initial_value}

    updated_rule = await update_rule_config(db_session, DEFAULT_GUILD_ID, key, updated_value)

    assert updated_rule.value_json == updated_value

    await db_session.commit()
    stmt = select(RuleConfig).where(RuleConfig.id == existing_rule_db.id)
    result = await db_session.execute(stmt)
    rule_from_db = result.scalar_one()
    assert rule_from_db.value_json == updated_value

    assert _rules_cache[DEFAULT_GUILD_ID][key] == updated_value

# --- Tests for get_all_rules_for_guild ---
@pytest.mark.asyncio
async def test_get_all_rules_for_guild_empty(db_session: AsyncSession):
    rules = await get_all_rules_for_guild(db_session, DEFAULT_GUILD_ID)
    assert rules == {}
    assert _rules_cache.get(DEFAULT_GUILD_ID) == {}

@pytest.mark.asyncio
async def test_get_all_rules_for_guild_loads_and_returns(db_session: AsyncSession):
    rule1_data = {"guild_id": DEFAULT_GUILD_ID, "key": "rule_a", "value_json": "val_a"}
    rule2_data = {"guild_id": DEFAULT_GUILD_ID, "key": "rule_b", "value_json": False}
    db_session.add(RuleConfig(**rule1_data))
    db_session.add(RuleConfig(**rule2_data))
    await db_session.commit()

    assert DEFAULT_GUILD_ID not in _rules_cache
    rules = await get_all_rules_for_guild(db_session, DEFAULT_GUILD_ID)

    expected_rules = {"rule_a": "val_a", "rule_b": False}
    assert rules == expected_rules
    assert _rules_cache[DEFAULT_GUILD_ID] == expected_rules

@pytest.mark.asyncio
async def test_get_all_rules_for_guild_uses_cache(db_session: AsyncSession):
    cached_rules = {"cached_rule": "cached_val"}
    _rules_cache[DEFAULT_GUILD_ID] = cached_rules

    with patch("src.core.rules.load_rules_config_for_guild", new_callable=AsyncMock) as mock_load_rules:
        rules = await get_all_rules_for_guild(db_session, DEFAULT_GUILD_ID)
        assert rules == cached_rules
        mock_load_rules.assert_not_called()
