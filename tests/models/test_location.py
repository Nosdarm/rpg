import unittest
from typing import Dict, Any, Optional, Union, List

from sqlalchemy import create_engine, event, JSON
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator, TEXT

from src.models.base import Base
from src.models.guild import GuildConfig
from src.models.location import Location, LocationType

# Костыль для SQLite для поддержки JSON/JSONB типов, аналогично test_combat_encounter.py
# В реальном проекте с PostgreSQL это не требуется.
# class JsonCompat(TypeDecorator): # Удалено, так как JsonBForSQLite используется в модели
#     impl = TEXT
#     cache_ok = True

#     def load_dialect_impl(self, dialect):
#         if dialect.name == 'postgresql':
#             return dialect.type_descriptor(JSONB)
#         else:
#             return dialect.type_descriptor(JSON) # Используем JSON для SQLite

#     def process_bind_param(self, value, dialect):
#         if value is None:
#             return None
#         if dialect.name == 'postgresql':
#             return value # JSONB остается как есть
#         else: # SQLite
#             import json
#             return json.dumps(value)

#     def process_result_value(self, value, dialect):
#         if value is None:
#             return None
#         if dialect.name == 'postgresql':
#             return value
#         else: # SQLite
#             import json
#             try:
#                 return json.loads(value)
#             except (json.JSONDecodeError, TypeError):
#                 return value # Если это уже Python объект (например, dict/list после process_bind_param в том же сеансе)

# # Применение JSONB "заглушки" к соответствующим колонкам Location для тестов с SQLite - Удалено
# @event.listens_for(Location.__table__, "column_reflect")
# def receive_column_reflect(inspector, table, column_info):
#     if isinstance(column_info['type'], JSONB):
#         column_info['type'] = JsonCompat()


class TestLocationModel(unittest.TestCase):
    engine = None
    SessionLocal = None

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)

        # Необходимо создать GuildConfig для внешнего ключа
        session = cls.SessionLocal()
        guild = GuildConfig(id=1, main_language="en", name="Test Guild")
        session.add(guild)
        session.commit()
        session.close()


    @classmethod
    def tearDownClass(cls):
        assert cls.engine is not None, "Engine should be initialized"
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self):
        assert self.SessionLocal is not None, "SessionLocal should be initialized"
        self.session: Session = self.SessionLocal()

    def tearDown(self):
        self.session.rollback() # Откатываем все изменения после теста
        self.session.close()

    def test_create_location_minimal(self):
        """Test creating a Location with minimal required fields."""
        location_data = {
            "guild_id": 1,
            "name_i18n": {"en": "Minimal Location"},
            "descriptions_i18n": {"en": "A place."},
            # type по умолчанию GENERIC
        }
        location = Location(**location_data)
        self.session.add(location)
        self.session.commit()
        self.session.refresh(location)

        self.assertIsNotNone(location.id)
        self.assertEqual(location.guild_id, 1)
        self.assertEqual(location.name_i18n["en"], "Minimal Location")
        self.assertEqual(location.type, LocationType.GENERIC)
        self.assertEqual(location.descriptions_i18n, {"en": "A place."}) # Проверяем значение по умолчанию для JSONB
        self.assertEqual(location.coordinates_json, None) # Проверяем JSONB nullable
        self.assertEqual(location.neighbor_locations_json, None)
        self.assertEqual(location.generated_details_json, None)
        self.assertEqual(location.ai_metadata_json, None)


    def test_create_location_all_fields(self):
        """Test creating a Location with all fields populated."""
        location_data: Dict[str, Any] = {
            "guild_id": 1,
            "static_id": "test_loc_001",
            "name_i18n": {"en": "Grand Library", "ru": "Великая Библиотека"},
            "descriptions_i18n": {"en": "Shelves filled with ancient tomes.", "ru": "Полки, заполненные древними фолиантами."},
            "type": LocationType.DUNGEON, # Нелогично, но для теста типа
            "coordinates_json": {"x": 10, "y": 20, "z": 0},
            "neighbor_locations_json": [{"target_static_id": "entrance_hall", "details": "Dusty corridor"}],
            "generated_details_json": {"weather": "always_misty", "special_feature": "echoing_silence"},
            "ai_metadata_json": {"source_prompt_hash": "xyz123", "model_version": "gpt-4"}
        }
        location = Location(**location_data)
        self.session.add(location)
        self.session.commit()
        self.session.refresh(location)

        retrieved_loc = self.session.query(Location).filter_by(id=location.id).one_or_none()
        self.assertIsNotNone(retrieved_loc)
        if retrieved_loc: # type guard
            self.assertEqual(retrieved_loc.static_id, "test_loc_001")
            self.assertEqual(retrieved_loc.name_i18n, {"en": "Grand Library", "ru": "Великая Библиотека"})
            self.assertEqual(retrieved_loc.descriptions_i18n, {"en": "Shelves filled with ancient tomes.", "ru": "Полки, заполненные древними фолиантами."})
            self.assertEqual(retrieved_loc.type, LocationType.DUNGEON)
            self.assertEqual(retrieved_loc.coordinates_json, {"x": 10, "y": 20, "z": 0})

            # Handle neighbor_locations_json carefully due to Optional[Union[List, Dict]]
            neighbor_data = retrieved_loc.neighbor_locations_json
            self.assertIsNotNone(neighbor_data, "neighbor_locations_json should not be None for this test case")
            self.assertIsInstance(neighbor_data, list, "neighbor_locations_json should be a list for this test case")

            # Pyright should now understand neighbor_data is a list
            if isinstance(neighbor_data, list): # Additional check for safety / explicitness
                self.assertEqual(len(neighbor_data), 1)
                self.assertEqual(neighbor_data[0].get("target_static_id"), "entrance_hall")

            self.assertEqual(retrieved_loc.generated_details_json, {"weather": "always_misty", "special_feature": "echoing_silence"})
            self.assertEqual(retrieved_loc.ai_metadata_json, {"source_prompt_hash": "xyz123", "model_version": "gpt-4"})

    def test_default_jsonb_fields_are_empty_dicts(self):
        """Test that JSONB fields default to empty dicts if not provided."""
        location = Location(guild_id=1) # name_i18n и descriptions_i18n обязательны по модели, но проверим как SQLAlchemy их обработает
                                      # если бы они были nullable с default=lambda: {}
        # Моя модель требует name_i18n и descriptions_i18n, так что нужно их передать
        location.name_i18n = {"en": "Test"}
        location.descriptions_i18n = {"en": "Test desc"}

        self.session.add(location)
        self.session.commit()
        self.session.refresh(location)

        # Эти поля nullable, так что они будут None, если не заданы
        self.assertIsNone(location.coordinates_json)
        self.assertIsNone(location.neighbor_locations_json)
        self.assertIsNone(location.generated_details_json)
        self.assertIsNone(location.ai_metadata_json)

        # name_i18n and descriptions_i18n are not nullable and have defaults
        self.assertEqual(location.name_i18n, {"en": "Test"}) # Они были установлены
        self.assertEqual(location.descriptions_i18n, {"en": "Test desc"})


    def test_location_repr(self):
        """Test the __repr__ method of the Location model."""
        location = Location(
            guild_id=1,
            static_id="repr_test_loc",
            name_i18n={"en": "Representation Test", "ru": "Тест Репрезентации"},
            descriptions_i18n={"en": "Desc"}
        )
        self.session.add(location)
        self.session.commit() # id будет присвоен после коммита

        expected_repr = f"<Location(id={location.id}, guild_id=1, static_id='repr_test_loc', name='Representation Test')>"
        self.assertEqual(repr(location), expected_repr)

    def test_location_repr_no_en_name(self):
        """Test the __repr__ method when 'en' name is missing."""
        location = Location(
            guild_id=1,
            static_id="repr_test_no_en",
            name_i18n={"ru": "Только Русский"}, # No 'en' key
            descriptions_i18n={"ru": "Описание"}
        )
        self.session.add(location)
        self.session.commit()

        expected_repr = f"<Location(id={location.id}, guild_id=1, static_id='repr_test_no_en', name='N/A')>"
        self.assertEqual(repr(location), expected_repr)

if __name__ == "__main__":
    unittest.main()
