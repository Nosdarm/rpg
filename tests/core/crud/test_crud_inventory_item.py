import asyncio
import unittest
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.models.base import Base
from src.models.item import Item
from src.models.inventory_item import InventoryItem
from src.models.guild import GuildConfig
from src.models.enums import OwnerEntityType
from src.core.crud.crud_inventory_item import inventory_item_crud
from src.core.crud.crud_item import item_crud # To create items for tests

# Use an in-memory SQLite database for testing
ASYNC_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

async_engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)
# type: ignore[var-annotated] # Pyright can sometimes struggle with complex sessionmaker types
AsyncSessionLocal = sessionmaker(
    bind=async_engine, class_=AsyncSession, expire_on_commit=False
)

class TestCRUDInventoryItem(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.session: AsyncSession = AsyncSessionLocal() # type: ignore[assignment] # If pyright still complains after above ignore

        self.guild_config = GuildConfig(id=1, name="Test Guild")
        self.session.add(self.guild_config)
        await self.session.commit()
        await self.session.refresh(self.guild_config)

        self.item1_data = {
            "guild_id": self.guild_config.id, "static_id": "sword1",
            "name_i18n": {"en": "Test Sword"}, "is_stackable": False
        }
        self.item2_data = {
            "guild_id": self.guild_config.id, "static_id": "potion1",
            "name_i18n": {"en": "Healing Potion"}, "is_stackable": True
        }
        self.db_item1 = await item_crud.create(self.session, obj_in=self.item1_data)
        self.db_item2 = await item_crud.create(self.session, obj_in=self.item2_data)


    async def asyncTearDown(self):
        await self.session.close()
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async def test_create_inventory_item(self):
        inv_item_data: Dict[str, Any] = {
            "guild_id": self.guild_config.id,
            "owner_entity_id": 1,
            "owner_entity_type": OwnerEntityType.PLAYER,
            "item_id": self.db_item1.id,
            "quantity": 1,
            "equipped_status": "main_hand"
        }
        created_inv_item = await inventory_item_crud.create(self.session, obj_in=inv_item_data)

        self.assertIsNotNone(created_inv_item.id)
        self.assertEqual(created_inv_item.item_id, self.db_item1.id)
        self.assertEqual(created_inv_item.owner_entity_id, 1)
        self.assertEqual(created_inv_item.equipped_status, "main_hand")

    async def test_get_inventory_for_owner(self):
        owner_id = 2
        owner_type = OwnerEntityType.PLAYER

        await inventory_item_crud.create(self.session, obj_in={
            "guild_id": self.guild_config.id, "owner_entity_id": owner_id,
            "owner_entity_type": owner_type, "item_id": self.db_item1.id, "quantity": 1
        })
        await inventory_item_crud.create(self.session, obj_in={
            "guild_id": self.guild_config.id, "owner_entity_id": owner_id,
            "owner_entity_type": owner_type, "item_id": self.db_item2.id, "quantity": 5
        })
        # Item for another owner
        await inventory_item_crud.create(self.session, obj_in={
            "guild_id": self.guild_config.id, "owner_entity_id": owner_id + 1,
            "owner_entity_type": owner_type, "item_id": self.db_item1.id, "quantity": 1
        })

        owner_inventory = await inventory_item_crud.get_inventory_for_owner(
            self.session, guild_id=self.guild_config.id, owner_entity_id=owner_id, owner_entity_type=owner_type
        )
        self.assertEqual(len(owner_inventory), 2)
        item_ids_in_inventory = {item.item_id for item in owner_inventory}
        self.assertIn(self.db_item1.id, item_ids_in_inventory)
        self.assertIn(self.db_item2.id, item_ids_in_inventory)

    async def test_add_item_to_owner_new_item(self):
        owner_id = 3
        owner_type = OwnerEntityType.PLAYER

        added_item = await inventory_item_crud.add_item_to_owner(
            self.session, guild_id=self.guild_config.id, owner_entity_id=owner_id,
            owner_entity_type=owner_type, item_id=self.db_item2.id, quantity=3
        )
        self.assertIsNotNone(added_item)
        self.assertEqual(added_item.item_id, self.db_item2.id)
        self.assertEqual(added_item.quantity, 3)

    async def test_add_item_to_owner_stack_existing(self):
        # This test relies on the simplified stacking due to uq_inventory_owner_item constraint
        owner_id = 4
        owner_type = OwnerEntityType.PLAYER

        # Add initial stack
        await inventory_item_crud.add_item_to_owner(
            self.session, guild_id=self.guild_config.id, owner_entity_id=owner_id,
            owner_entity_type=owner_type, item_id=self.db_item2.id, quantity=2
        )
        # Add more to the stack
        updated_item = await inventory_item_crud.add_item_to_owner(
            self.session, guild_id=self.guild_config.id, owner_entity_id=owner_id,
            owner_entity_type=owner_type, item_id=self.db_item2.id, quantity=3
        )
        self.assertEqual(updated_item.quantity, 5)

        # Verify only one inventory entry for this item_id for this owner
        inventory = await inventory_item_crud.get_inventory_for_owner(
            self.session, guild_id=self.guild_config.id, owner_entity_id=owner_id, owner_entity_type=owner_type
        )
        self.assertEqual(len(inventory), 1)
        self.assertEqual(inventory[0].item_id, self.db_item2.id)

    async def test_remove_item_from_owner_decrease_quantity(self):
        owner_id = 5
        owner_type = OwnerEntityType.PLAYER

        await inventory_item_crud.add_item_to_owner(
            self.session, guild_id=self.guild_config.id, owner_entity_id=owner_id,
            owner_entity_type=owner_type, item_id=self.db_item2.id, quantity=5
        )

        updated_item = await inventory_item_crud.remove_item_from_owner(
            self.session, guild_id=self.guild_config.id, owner_entity_id=owner_id,
            owner_entity_type=owner_type, item_id=self.db_item2.id, quantity=2
        )
        self.assertIsNotNone(updated_item, "Updated item should not be None after decreasing quantity.")
        if updated_item: # Added check for Pyright and robustness
            self.assertEqual(updated_item.quantity, 3)

    async def test_remove_item_from_owner_delete_stack(self):
        owner_id = 6
        owner_type = OwnerEntityType.PLAYER

        await inventory_item_crud.add_item_to_owner(
            self.session, guild_id=self.guild_config.id, owner_entity_id=owner_id,
            owner_entity_type=owner_type, item_id=self.db_item2.id, quantity=3
        )

        result_item = await inventory_item_crud.remove_item_from_owner(
            self.session, guild_id=self.guild_config.id, owner_entity_id=owner_id,
            owner_entity_type=owner_type, item_id=self.db_item2.id, quantity=3 # Remove all
        )
        self.assertIsNone(result_item) # Item entry should be deleted

        inventory = await inventory_item_crud.get_inventory_for_owner(
            self.session, guild_id=self.guild_config.id, owner_entity_id=owner_id, owner_entity_type=owner_type
        )
        self.assertEqual(len(inventory), 0)

    async def test_remove_item_from_owner_item_not_found(self):
        result = await inventory_item_crud.remove_item_from_owner(
            self.session, guild_id=self.guild_config.id, owner_entity_id=99,
            owner_entity_type=OwnerEntityType.PLAYER, item_id=self.db_item1.id
        )
        self.assertIsNone(result)

# Removed standard unittest runner, assumed pytest or similar will be used.
# if __name__ == '__main__':
#     asyncio.run(unittest.main())
