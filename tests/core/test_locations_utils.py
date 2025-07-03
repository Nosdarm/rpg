import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import create_engine, event, JSON
from sqlalchemy.orm import sessionmaker, Session as SqlAlchemySession # Renamed to avoid conflict
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
        return dialect.type_descriptor(JSONB) if dialect.name == 'postgresql' else dialect.type_descriptor(JSON)
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
    if isinstance(column_info['type'], JSONB):
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
    engine = None
    SessionLocal = None
    test_guild_id = 1

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine, class_=AsyncSession)

        # Setup initial guild
        sync_session_maker = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        sync_session = sync_session_maker()
        if not sync_session.get(GuildConfig, cls.test_guild_id):
            guild = GuildConfig(id=cls.test_guild_id, main_language="en", name="Test Guild")
            sync_session.add(guild)
            sync_session.commit()
        sync_session.close()

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(cls.engine)
        # cls.engine.dispose() # dispose is for async engine

    async def asyncSetUp(self):
        self.session: AsyncSession = self.SessionLocal()
        # Seed one location for testing get methods
        self.loc1_data = {
            "guild_id": self.test_guild_id,
            "static_id": "loc_001",
            "name_i18n": {"en": "Test Location 1"},
            "descriptions_i18n": {"en": "Desc 1"},
            "type": LocationType.TOWN
        }
        loc1 = Location(**self.loc1_data)
        self.session.add(loc1)
        await self.session.commit()
        self.loc1_id = loc1.id


    async def asyncTearDown(self):
        await self.session.rollback()
        await self.session.close()

    async def test_get_location_existing(self):
        location = await get_location(self.session, guild_id=self.test_guild_id, location_id=self.loc1_id)
        self.assertIsNotNone(location)
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
        self.assertEqual(location.static_id, "loc_001")
        self.assertEqual(location.name_i18n["en"], "Test Location 1")

    async def test_get_location_by_static_id_not_existing(self):
        location = await get_location_by_static_id(self.session, guild_id=self.test_guild_id, static_id="non_existent_static_id")
        self.assertIsNone(location)

    async def test_get_location_by_static_id_wrong_guild(self):
        location = await get_location_by_static_id(self.session, guild_id=self.test_guild_id + 1, static_id="loc_001")
        self.assertIsNone(location)

    # Example of mocking crud method if needed for more complex utils
    @patch("src.core.crud.crud_location.location_crud.get", new_callable=AsyncMock)
    async def test_get_location_mocked(self, mock_crud_get):
        mock_location_instance = Location(id=1, guild_id=1, name_i18n={"en":"Mocked"})
        mock_crud_get.return_value = mock_location_instance

        result = await get_location(self.session, guild_id=1, location_id=1)

        mock_crud_get.assert_called_once_with(self.session, id=1, guild_id=1)
        self.assertEqual(result, mock_location_instance)

if __name__ == "__main__":
    unittest.main()
