import unittest
from typing import Dict, Any, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as SQLAlchemySession

from backend.models.base import Base
from backend.models.item import Item
from backend.models.inventory_item import InventoryItem
from backend.models.guild import GuildConfig
from backend.models.enums import OwnerEntityType

# Use an in-memory SQLite database for testing
engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class TestInventoryItemModel(unittest.TestCase):

    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.session: SQLAlchemySession = SessionLocal()

        # Create a dummy guild_config for foreign key reference
        self.guild_config = GuildConfig(id=1, name="Test Guild") # guild_discord_id is not a field, id is the discord id
        self.session.add(self.guild_config)
        self.session.commit()
        self.session.refresh(self.guild_config)

        # Create a dummy item for foreign key reference
        self.test_item = Item(
            guild_id=self.guild_config.id,
            name_i18n={"en": "Test Sword"},
            slot_type="weapon_main_hand",
            is_stackable=False
        )
        self.session.add(self.test_item)
        self.session.commit()
        self.session.refresh(self.test_item)

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(bind=engine)

    def test_create_inventory_item_minimal(self):
        """Test creating an inventory item with minimal required fields."""
        inv_item_data = {
            "guild_id": self.guild_config.id,
            "owner_entity_id": 101, # Example player ID
            "owner_entity_type": OwnerEntityType.PLAYER,
            "item_id": self.test_item.id,
            # quantity defaults to 1
        }
        inv_item = InventoryItem(**inv_item_data)
        self.session.add(inv_item)
        self.session.commit()
        self.session.refresh(inv_item)

        self.assertIsNotNone(inv_item.id)
        self.assertEqual(inv_item.guild_id, self.guild_config.id)
        self.assertEqual(inv_item.owner_entity_id, 101)
        self.assertEqual(inv_item.owner_entity_type, OwnerEntityType.PLAYER)
        self.assertEqual(inv_item.item_id, self.test_item.id)
        self.assertEqual(inv_item.quantity, 1) # Check default
        self.assertIsNone(inv_item.equipped_status) # Check default (Optional)
        self.assertEqual(inv_item.instance_specific_properties_json, {}) # Check default

    def test_create_inventory_item_all_fields(self):
        """Test creating an inventory item with all fields populated."""
        inv_item_data: Dict[str, Any] = {
            "guild_id": self.guild_config.id,
            "owner_entity_id": 102, # Example NPC ID
            "owner_entity_type": OwnerEntityType.GENERATED_NPC,
            "item_id": self.test_item.id,
            "quantity": 5,
            "equipped_status": "main_hand",
            "instance_specific_properties_json": {"quality": "masterwork", "enchantment": "fire"}
        }
        inv_item = InventoryItem(**inv_item_data)
        self.session.add(inv_item)
        self.session.commit()
        self.session.refresh(inv_item)

        self.assertEqual(inv_item.owner_entity_id, 102)
        self.assertEqual(inv_item.owner_entity_type, OwnerEntityType.GENERATED_NPC)
        self.assertEqual(inv_item.quantity, 5)
        self.assertEqual(inv_item.equipped_status, "main_hand")

        self.assertIsNotNone(inv_item.instance_specific_properties_json, "instance_specific_properties_json should be populated in this test.")
        if inv_item.instance_specific_properties_json: # Check for Pyright and robustness
            self.assertEqual(inv_item.instance_specific_properties_json.get("quality"), "masterwork")

    def test_inventory_item_relationship_to_item(self):
        """Test the relationship from InventoryItem to Item."""
        inv_item = InventoryItem(
            guild_id=self.guild_config.id,
            owner_entity_id=103,
            owner_entity_type=OwnerEntityType.PLAYER,
            item_id=self.test_item.id
        )
        self.session.add(inv_item)
        self.session.commit()
        self.session.refresh(inv_item)
        self.session.refresh(self.test_item) # Ensure item is refreshed in session

        self.assertIsNotNone(inv_item.item)
        self.assertEqual(inv_item.item.id, self.test_item.id)
        self.assertEqual(inv_item.item.name_i18n.get("en"), "Test Sword")

    def test_inventory_item_repr(self):
        """Test the __repr__ method of the InventoryItem model."""
        inv_item = InventoryItem(
            guild_id=self.guild_config.id,
            owner_entity_id=104,
            owner_entity_type=OwnerEntityType.PLAYER,
            item_id=self.test_item.id,
            quantity=3
        )
        self.session.add(inv_item)
        self.session.commit()
        self.session.refresh(inv_item)

        expected_repr = f"<InventoryItem(id={inv_item.id}, owner='{OwnerEntityType.PLAYER.value}:{104}', item_id={self.test_item.id}, quantity=3)>"
        self.assertEqual(repr(inv_item), expected_repr)

if __name__ == '__main__':
    unittest.main()
