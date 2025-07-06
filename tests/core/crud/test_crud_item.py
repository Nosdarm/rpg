import asyncio
import unittest
from typing import Dict, Any

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.models.base import Base
from src.models.item import Item
from src.models.guild import GuildConfig
from src.core.crud.crud_item import item_crud

# Use an in-memory SQLite database for testing
ASYNC_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

async_engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    bind=async_engine, class_=AsyncSession, expire_on_commit=False
)

class TestCRUDItem(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.session: AsyncSession = AsyncSessionLocal()

        # Create a dummy guild_config for foreign key reference
        self.guild_config = GuildConfig(id=1, name="Test Guild") # guild_discord_id is not a field, id is the discord id
        self.session.add(self.guild_config)
        await self.session.commit()
        await self.session.refresh(self.guild_config)

    async def asyncTearDown(self):
        await self.session.close()
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async def test_create_item(self):
        """Test creating an item using CRUD."""
        item_data: Dict[str, Any] = {
            "guild_id": self.guild_config.id,
            "static_id": "test_item_crud_001",
            "name_i18n": {"en": "CRUD Test Item"},
            "slot_type": "consumable",
            "is_stackable": True,
            "base_value": 10,
            "properties_json": {"effect": "heal_small"}
        }
        created_item = await item_crud.create(self.session, obj_in=item_data)

        self.assertIsNotNone(created_item.id)
        self.assertEqual(created_item.static_id, "test_item_crud_001")
        self.assertEqual(created_item.name_i18n["en"], "CRUD Test Item")
        self.assertTrue(created_item.is_stackable)
        self.assertEqual(created_item.guild_id, self.guild_config.id)

    async def test_get_item(self):
        """Test retrieving an item using CRUD."""
        item_data = {"guild_id": self.guild_config.id, "name_i18n": {"en": "Get Me"}}
        created_item = await item_crud.create(self.session, obj_in=item_data)

        retrieved_item = await item_crud.get(self.session, id=created_item.id, guild_id=self.guild_config.id)

        self.assertIsNotNone(retrieved_item)
        assert retrieved_item is not None # For pyright
        self.assertEqual(retrieved_item.id, created_item.id)
        self.assertEqual(retrieved_item.name_i18n["en"], "Get Me")

    async def test_get_item_not_found(self):
        retrieved_item = await item_crud.get(self.session, id=999, guild_id=self.guild_config.id)
        self.assertIsNone(retrieved_item)

    async def test_get_item_wrong_guild(self):
        item_data = {"guild_id": self.guild_config.id, "name_i18n": {"en": "Guild Item"}}
        created_item = await item_crud.create(self.session, obj_in=item_data)

        retrieved_item_wrong_guild = await item_crud.get(self.session, id=created_item.id, guild_id=999) # Wrong guild_id
        self.assertIsNone(retrieved_item_wrong_guild)


    async def test_get_by_static_id(self):
        """Test retrieving an item by static_id."""
        static_id_val = "static_sword_01"
        item_data = {
            "guild_id": self.guild_config.id,
            "static_id": static_id_val,
            "name_i18n": {"en": "Static Sword"}
        }
        await item_crud.create(self.session, obj_in=item_data)

        retrieved_item = await item_crud.get_by_static_id(self.session, guild_id=self.guild_config.id, static_id=static_id_val)

        self.assertIsNotNone(retrieved_item)
        assert retrieved_item is not None # For pyright
        self.assertEqual(retrieved_item.static_id, static_id_val)

    async def test_get_multi_item(self):
        """Test retrieving multiple items."""
        await item_crud.create(self.session, obj_in={"guild_id": self.guild_config.id, "name_i18n": {"en": "Item A"}})
        await item_crud.create(self.session, obj_in={"guild_id": self.guild_config.id, "name_i18n": {"en": "Item B"}})

        # Create item for another guild to test filtering
        other_guild = GuildConfig(id=2, name="Other Guild") # guild_discord_id is not a field
        self.session.add(other_guild)
        await self.session.commit()
        await item_crud.create(self.session, obj_in={"guild_id": other_guild.id, "name_i18n": {"en": "Item C"}})

        items = await item_crud.get_multi(self.session, guild_id=self.guild_config.id) # Corrected kwarg name
        self.assertEqual(len(items), 2)

        all_items = await item_crud.get_multi(self.session) # No guild filter
        self.assertEqual(len(all_items), 3)


    async def test_update_item(self):
        """Test updating an item."""
        item_data = {"guild_id": self.guild_config.id, "name_i18n": {"en": "Old Name"}, "base_value": 50}
        created_item = await item_crud.create(self.session, obj_in=item_data)

        update_data = {"name_i18n": {"en": "New Name", "ru": "Новое Имя"}, "base_value": 75}
        updated_item = await item_crud.update(self.session, db_obj=created_item, obj_in=update_data)

        self.assertEqual(updated_item.name_i18n["en"], "New Name")
        self.assertEqual(updated_item.name_i18n["ru"], "Новое Имя")
        self.assertEqual(updated_item.base_value, 75)

    async def test_remove_item(self):
        """Test removing an item."""
        item_data = {"guild_id": self.guild_config.id, "name_i18n": {"en": "To Be Deleted"}}
        created_item = await item_crud.create(self.session, obj_in=item_data)

        await item_crud.delete(self.session, id=created_item.id, guild_id=self.guild_config.id) # CRUDBase uses delete

        deleted_item = await item_crud.get(self.session, id=created_item.id, guild_id=self.guild_config.id)
        self.assertIsNone(deleted_item)

# Removed standard unittest runner, assumed pytest or similar will be used.
# if __name__ == '__main__':
#     asyncio.run(unittest.main())
