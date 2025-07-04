import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional # Added Optional

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Используем create_async_engine для асинхронного движка
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine # Added AsyncEngine
from sqlalchemy import event, JSON, select # Добавлен select
# from sqlalchemy.orm import sessionmaker # Replaced by async_sessionmaker
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator, TEXT


from src.models.base import Base
from src.models.guild import GuildConfig
from src.models.location import Location, LocationType
from src.core.locations_utils import get_localized_text, get_location, get_location_by_static_id
from src.core.crud.crud_location import location_crud # To potentially mock its methods

# JSON/JSONB compatibility for SQLite (same as in test_location.py)
class JsonCompat(TypeDecorator):
    impl = TEXT
    cache_ok = True
    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(JSONB()) if dialect.name == 'postgresql' else dialect.type_descriptor(JSON())
    def process_bind_param(self, value, dialect):
        if value is None: return None
        return value if dialect.name == 'postgresql' else __import__('json').dumps(value)
    def process_result_value(self, value, dialect):
        if value is None: return None
        if dialect.name == 'postgresql': return value
        try: return __import__('json').loads(value)
        except (__import__('json').JSONDecodeError, TypeError): return value

@event.listens_for(Location.__table__, "column_reflect")
def receive_column_reflect(inspector, table, column_info):
    if isinstance(column_info['type'], JSONB): # type: ignore
        column_info['type'] = JsonCompat()


class TestGetLocalizedText(unittest.TestCase):
    def test_get_primary_language(self):
        mock_entity = MagicMock()
        mock_entity.name_i18n = {"en": "Hello", "ru": "Привет"}
        self.assertEqual(get_localized_text(mock_entity, "name", "ru"), "Привет")

    def test_get_fallback_language(self):
        mock_entity = MagicMock()
        mock_entity.description_i18n = {"en": "Description", "ru": "Описание"}
        self.assertEqual(get_localized_text(mock_entity, "description", "fr", "en"), "Description")

    def test_get_first_available_if_primary_and_fallback_missing(self):
        mock_entity = MagicMock()
        mock_entity.title_i18n = {"de": "Titel"} # No 'en' or 'fr'
        # В текущей реализации get_localized_text, если не найден ни язык, ни fallback,
        # и если в словаре есть хоть что-то, вернется первое значение.
        # Если это нежелательное поведение, get_localized_text нужно изменить.
        # Пока тест отражает текущую логику.
        self.assertEqual(get_localized_text(mock_entity, "title", "fr", "en"), "Titel")


    def test_empty_string_if_no_text_found(self):
        mock_entity = MagicMock()
        mock_entity.name_i18n = {}
        self.assertEqual(get_localized_text(mock_entity, "name", "en"), "")

    def test_empty_string_if_field_missing(self):
        mock_entity = MagicMock() # No name_i18n field
        self.assertEqual(get_localized_text(mock_entity, "name", "en"), "")

    def test_empty_string_if_i18n_field_not_dict(self):
        mock_entity = MagicMock()
        mock_entity.name_i18n = "not_a_dict"
        self.assertEqual(get_localized_text(mock_entity, "name", "en"), "")

    def test_different_field_name_base(self):
        mock_entity = MagicMock()
        mock_entity.descriptions_i18n = {"en": "A test description."}
        self.assertEqual(get_localized_text(mock_entity, "descriptions", "en"), "A test description.")


class TestLocationDBUtils(unittest.IsolatedAsyncioTestCase):
    engine: Optional[AsyncEngine] = None # type hint for clarity
    SessionLocal: Optional[async_sessionmaker[AsyncSession]] = None # type hint for clarity
    test_guild_id = 1

    @classmethod
    def setUpClass(cls):
        cls.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        # Use async_sessionmaker for AsyncSession
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

        guild_exists = await self.session.get(GuildConfig, self.test_guild_id)
        if not guild_exists:
            guild = GuildConfig(id=self.test_guild_id, main_language="en", name="Test Guild")
            self.session.add(guild)
            await self.session.commit()

        self.loc1_data = {
            "guild_id": self.test_guild_id,
            "static_id": "loc_001",
            "name_i18n": {"en": "Test Location 1"},
            "descriptions_i18n": {"en": "Desc 1"},
            "type": LocationType.TOWN
        }

        existing_loc_stmt = select(Location).filter_by(guild_id=self.test_guild_id, static_id="loc_001")
        existing_loc_result = await self.session.execute(existing_loc_stmt)
        scalar_existing_loc = existing_loc_result.scalar_one_or_none()

        if not scalar_existing_loc:
            loc1 = Location(**self.loc1_data)
            self.session.add(loc1)
            await self.session.commit()
            await self.session.refresh(loc1) # Refresh to load ID
            self.loc1_id = loc1.id
        else:
            self.loc1_id = scalar_existing_loc.id
        await self.session.commit()

    async def asyncTearDown(self):
        if hasattr(self, 'session') and self.session:
            await self.session.rollback() # Rollback any pending transaction
            await self.session.close()

    async def test_get_location_existing(self):
        location = await get_location(self.session, guild_id=self.test_guild_id, location_id=self.loc1_id)
        self.assertIsNotNone(location)
        assert location is not None # for type checker
        self.assertEqual(location.id, self.loc1_id)
        self.assertEqual(location.name_i18n["en"], "Test Location 1")

    async def test_get_location_not_existing(self):
        location = await get_location(self.session, guild_id=self.test_guild_id, location_id=999)
        self.assertIsNone(location)

    async def test_get_location_wrong_guild(self):
        location = await get_location(self.session, guild_id=self.test_guild_id + 1, location_id=self.loc1_id)
        self.assertIsNone(location)

    async def test_get_location_by_static_id_existing(self):
        location = await get_location_by_static_id(self.session, guild_id=self.test_guild_id, static_id="loc_001")
        self.assertIsNotNone(location)
        assert location is not None # for type checker
        self.assertEqual(location.static_id, "loc_001")
        self.assertEqual(location.name_i18n["en"], "Test Location 1")

    async def test_get_location_by_static_id_not_existing(self):
        location = await get_location_by_static_id(self.session, guild_id=self.test_guild_id, static_id="non_existent_static_id")
        self.assertIsNone(location)

    async def test_get_location_by_static_id_wrong_guild(self):
        location = await get_location_by_static_id(self.session, guild_id=self.test_guild_id + 1, static_id="loc_001")
        self.assertIsNone(location)

    @patch("src.core.crud.crud_location.location_crud.get", new_callable=AsyncMock)
    async def test_get_location_mocked(self, mock_crud_get):
        mock_location_instance = Location(id=1, guild_id=1, name_i18n={"en":"Mocked"})
        mock_crud_get.return_value = mock_location_instance

        result = await get_location(self.session, guild_id=1, location_id=1)

        mock_crud_get.assert_called_once_with(self.session, id=1, guild_id=1)
        self.assertEqual(result, mock_location_instance)

if __name__ == "__main__":
    unittest.main()
