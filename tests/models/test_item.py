import unittest
from typing import Dict, Any, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as SQLAlchemySession

from src.models.base import Base
from src.models.item import Item
from src.models.guild import GuildConfig # Needed for ForeignKey constraint

# Use an in-memory SQLite database for testing
engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class TestItemModel(unittest.TestCase):

    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.session: SQLAlchemySession = SessionLocal()

        # Create a dummy guild_config for foreign key reference
        self.guild_config = GuildConfig(id=1, name="Test Guild") # guild_discord_id is not a field, id is the discord id
        self.session.add(self.guild_config)
        self.session.commit()
        self.session.refresh(self.guild_config)


    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(bind=engine)

    def test_create_item_minimal(self):
        """Test creating an item with minimal required fields."""
        item_data = {
            "guild_id": self.guild_config.id,
            "name_i18n": {"en": "Test Item", "ru": "Тестовый Предмет"},
            # is_stackable defaults to True
        }
        item = Item(**item_data)
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)

        self.assertIsNotNone(item.id)
        self.assertEqual(item.guild_id, self.guild_config.id)
        self.assertEqual(item.name_i18n["en"], "Test Item")
        self.assertTrue(item.is_stackable) # Check default
        self.assertIsNone(item.slot_type) # Check default (Optional)
        self.assertEqual(item.description_i18n, {}) # Check default
        self.assertEqual(item.properties_json, {}) # Check default

    def test_create_item_all_fields(self):
        """Test creating an item with all fields populated."""
        item_data: Dict[str, Any] = {
            "guild_id": self.guild_config.id,
            "static_id": "test_sword_001",
            "name_i18n": {"en": "Sword of Testing", "ru": "Меч Тестирования"},
            "description_i18n": {"en": "A mighty fine sword for testing purposes.", "ru": "Прекрасный меч для тестов."},
            "item_type_i18n": {"en": "Weapon", "ru": "Оружие"},
            "item_category_i18n": {"en": "One-Handed Sword", "ru": "Одноручный меч"},
            "base_value": 100,
            "properties_json": {"damage": "1d8", "type": "slashing"},
            "slot_type": "weapon_main_hand",
            "is_stackable": False
        }
        item = Item(**item_data)
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)

        self.assertEqual(item.static_id, "test_sword_001")
        self.assertEqual(item.name_i18n["en"], "Sword of Testing")
        self.assertEqual(item.description_i18n["ru"], "Прекрасный меч для тестов.")

        self.assertIsNotNone(item.item_type_i18n, "item_type_i18n should be populated in this test.")
        if item.item_type_i18n: # Check for Pyright and robustness
            self.assertEqual(item.item_type_i18n.get("en"), "Weapon")

        self.assertIsNotNone(item.item_category_i18n, "item_category_i18n should be populated.")
        if item.item_category_i18n: # Check for Pyright
            self.assertEqual(item.item_category_i18n.get("ru"), "Одноручный меч")

        self.assertEqual(item.base_value, 100)

        self.assertIsNotNone(item.properties_json, "properties_json should be populated.")
        if item.properties_json: # Check for Pyright
            self.assertEqual(item.properties_json.get("damage"), "1d8")

        self.assertEqual(item.slot_type, "weapon_main_hand")
        self.assertFalse(item.is_stackable)

    def test_item_repr(self):
        """Test the __repr__ method of the Item model."""
        item = Item(
            guild_id=self.guild_config.id,
            name_i18n={"en": "Representable Item"}
        )
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)

        expected_repr = f"<Item(id={item.id}, guild_id={self.guild_config.id}, static_id='{None}', name='Representable Item')>"
        self.assertEqual(repr(item), expected_repr)

        item_with_static_id = Item(
            guild_id=self.guild_config.id,
            static_id="rep_item_01",
            name_i18n={"en": "Rep Static Item"}
        )
        self.session.add(item_with_static_id)
        self.session.commit()
        self.session.refresh(item_with_static_id)
        expected_repr_static = f"<Item(id={item_with_static_id.id}, guild_id={self.guild_config.id}, static_id='rep_item_01', name='Rep Static Item')>"
        self.assertEqual(repr(item_with_static_id), expected_repr_static)

if __name__ == '__main__':
    unittest.main()
