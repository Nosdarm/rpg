import sys
import os
import unittest
from typing import Optional, Dict, Any

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy import event

from src.models.base import Base
from src.models.guild import GuildConfig
from src.models.generated_faction import GeneratedFaction
from src.core.crud.crud_faction import crud_faction
from src.models.custom_types import JsonBForSQLite

# Event listeners for SQLite compatibility for GeneratedFaction JSON fields
@event.listens_for(GeneratedFaction.__table__, "column_reflect")
def _generated_faction_column_reflect_crud(inspector, table, column_info):
    json_fields = ['name_i18n', 'description_i18n', 'ideology_i18n', 'resources_json', 'ai_metadata_json']
    if column_info['name'] in json_fields:
        if not isinstance(column_info['type'], JsonBForSQLite):
            column_info['type'] = JsonBForSQLite()


class TestCRUDFaction(unittest.IsolatedAsyncioTestCase):
    engine: Optional[AsyncEngine] = None
    SessionLocal: Optional[async_sessionmaker[AsyncSession]] = None

    test_guild_id = 201
    other_guild_id = 202

    @classmethod
    def setUpClass(cls):
        cls.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        cls.SessionLocal = async_sessionmaker(
            bind=cls.engine, class_=AsyncSession, expire_on_commit=False
        )

    @classmethod
    def tearDownClass(cls):
        if cls.engine:
            import asyncio
            asyncio.run(cls.engine.dispose())

    async def asyncSetUp(self):
        assert self.SessionLocal is not None
        self.session: AsyncSession = self.SessionLocal()

        assert self.engine is not None
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        # Setup GuildConfigs
        for gid in [self.test_guild_id, self.other_guild_id]:
            guild = await self.session.get(GuildConfig, gid)
            if not guild:
                self.session.add(GuildConfig(id=gid, main_language="en", name=f"Guild {gid}"))

        await self.session.commit()

    async def asyncTearDown(self):
        if hasattr(self, 'session') and self.session:
            await self.session.rollback()
            await self.session.close()

    async def test_create_faction(self):
        faction_data = {
            "guild_id": self.test_guild_id,
            "static_id": "test_faction_001",
            "name_i18n": {"en": "Test Faction 1", "ru": "Тестовая Фракция 1"},
            "description_i18n": {"en": "Description for TF1", "ru": "Описание для ТФ1"},
            "ideology_i18n": {"en": "Testology", "ru": "Тестология"},
            "resources_json": {"gold": 1000, "mana_crystals": 50},
            "ai_metadata_json": {"source_prompt_hash": "abc123xyz"}
        }
        faction = await crud_faction.create(self.session, obj_in=faction_data)
        await self.session.commit()

        self.assertIsNotNone(faction.id)
        self.assertEqual(faction.guild_id, self.test_guild_id)
        self.assertEqual(faction.static_id, "test_faction_001")
        # name_i18n and description_i18n are non-nullable and default to {}
        self.assertEqual(faction.name_i18n["en"], "Test Faction 1")
        self.assertEqual(faction.description_i18n["ru"], "Описание для ТФ1")

        # ideology_i18n, resources_json, ai_metadata_json are Optional[Dict]
        if faction.ideology_i18n:
            self.assertEqual(faction.ideology_i18n.get("en"), "Testology")
        else: # If the test data implies it should exist, this is an issue
            self.assertIsNotNone(faction.ideology_i18n, "ideology_i18n should exist based on input data")

        if faction.resources_json:
            self.assertEqual(faction.resources_json.get("gold"), 1000)
        else:
            self.assertIsNotNone(faction.resources_json, "resources_json should exist based on input data")

        if faction.ai_metadata_json:
            self.assertEqual(faction.ai_metadata_json.get("source_prompt_hash"), "abc123xyz")
        else:
            self.assertIsNotNone(faction.ai_metadata_json, "ai_metadata_json should exist based on input data")


    async def test_get_faction_by_id(self):
        faction_data = {
            "guild_id": self.test_guild_id, "static_id": "get_me_faction",
            "name_i18n": {"en": "GetMe Faction"}, "description_i18n": {"en": "Desc"}
        }
        created_faction = await crud_faction.create(self.session, obj_in=faction_data)
        await self.session.commit()

        self.assertIsNotNone(created_faction.id)
        faction_id = created_faction.id

        # Get existing faction
        fetched_faction = await crud_faction.get(self.session, id=faction_id) # CRUDBase.get does not take guild_id
        self.assertIsNotNone(fetched_faction)
        if fetched_faction: # Guard for Pyright
            self.assertEqual(fetched_faction.id, faction_id)
            # name_i18n is non-nullable, no inner check needed
            self.assertEqual(fetched_faction.name_i18n["en"], "GetMe Faction")
            self.assertEqual(fetched_faction.guild_id, self.test_guild_id) # Important: ensure it's from the correct guild even if get() doesn't filter by it

        # Try to get non-existent faction
        not_found_faction = await crud_faction.get(self.session, id=99999)
        self.assertIsNone(not_found_faction)

        # Try to get faction from another guild (CRUDBase.get won't prevent this, business logic should)
        # This test primarily ensures that if a faction ID from another guild is somehow queried,
        # the data is returned as is. Filtering by guild_id is usually done by methods like get_by_id_and_guild
        # or by the caller.
        # For this test, we'll create one in another guild and try to fetch it by its ID.
        other_guild_faction_data = {
            "guild_id": self.other_guild_id, "static_id": "other_guild_fac",
            "name_i18n": {"en": "OtherGuildFac"}, "description_i18n": {"en": "Desc"}
        }
        other_faction = await crud_faction.create(self.session, obj_in=other_guild_faction_data)
        await self.session.commit()
        self.assertIsNotNone(other_faction.id)

        # Fetching other_faction by its ID should work
        fetched_other_faction = await crud_faction.get(self.session, id=other_faction.id)
        self.assertIsNotNone(fetched_other_faction)
        if fetched_other_faction: # Guard for Pyright
            self.assertEqual(fetched_other_faction.id, other_faction.id)
            self.assertEqual(fetched_other_faction.guild_id, self.other_guild_id)

    async def test_get_faction_by_static_id(self):
        static_id_shared = "shared_static_id"
        faction1_data = {
            "guild_id": self.test_guild_id, "static_id": static_id_shared,
            "name_i18n": {"en": "Faction 1 Shared SID"}, "description_i18n": {"en": "Desc1"}
        }
        faction2_data = {
            "guild_id": self.other_guild_id, "static_id": static_id_shared,
            "name_i18n": {"en": "Faction 2 Shared SID"}, "description_i18n": {"en": "Desc2"}
        }
        faction_unique_sid_data = {
            "guild_id": self.test_guild_id, "static_id": "unique_sid_faction",
            "name_i18n": {"en": "Faction Unique SID"}, "description_i18n": {"en": "DescUnique"}
        }

        await crud_faction.create(self.session, obj_in=faction1_data)
        await crud_faction.create(self.session, obj_in=faction2_data)
        await crud_faction.create(self.session, obj_in=faction_unique_sid_data)
        await self.session.commit()

        # Get faction with unique static_id for test_guild_id
        fetched_unique = await crud_faction.get_by_static_id(self.session, guild_id=self.test_guild_id, static_id="unique_sid_faction")
        self.assertIsNotNone(fetched_unique)
        if fetched_unique: # Guard for Pyright
            self.assertEqual(fetched_unique.name_i18n["en"], "Faction Unique SID") # name_i18n non-nullable
            self.assertEqual(fetched_unique.guild_id, self.test_guild_id)

        # Get faction with shared static_id for test_guild_id
        fetched1 = await crud_faction.get_by_static_id(self.session, guild_id=self.test_guild_id, static_id=static_id_shared)
        self.assertIsNotNone(fetched1)
        if fetched1: # Guard for Pyright
            self.assertEqual(fetched1.name_i18n["en"], "Faction 1 Shared SID") # name_i18n non-nullable
            self.assertEqual(fetched1.guild_id, self.test_guild_id)

        # Get faction with shared static_id for other_guild_id
        fetched2 = await crud_faction.get_by_static_id(self.session, guild_id=self.other_guild_id, static_id=static_id_shared)
        self.assertIsNotNone(fetched2)
        if fetched2: # Guard for Pyright
            self.assertEqual(fetched2.name_i18n["en"], "Faction 2 Shared SID") # name_i18n non-nullable
            self.assertEqual(fetched2.guild_id, self.other_guild_id)

        # Ensure they are different objects
        if fetched1 and fetched2: # Guard for Pyright
            self.assertNotEqual(fetched1.id, fetched2.id)

        # Try to get non-existent static_id
        not_found_sid = await crud_faction.get_by_static_id(self.session, guild_id=self.test_guild_id, static_id="non_existent_sid")
        self.assertIsNone(not_found_sid)

        # Try to get existing static_id but for wrong guild
        wrong_guild_sid = await crud_faction.get_by_static_id(self.session, guild_id=self.other_guild_id, static_id="unique_sid_faction")
        self.assertIsNone(wrong_guild_sid)

    async def test_get_multi_by_guild_id(self):
        # Create factions for test_guild_id
        factions_test_guild = []
        for i in range(5):
            data = {
                "guild_id": self.test_guild_id, "static_id": f"tg_fac_{i}",
                "name_i18n": {"en": f"TestGuild Faction {i}"}, "description_i18n": {"en": "Desc"}
            }
            factions_test_guild.append(await crud_faction.create(self.session, obj_in=data))

        # Create factions for other_guild_id
        for i in range(3):
            data = {
                "guild_id": self.other_guild_id, "static_id": f"og_fac_{i}",
                "name_i18n": {"en": f"OtherGuild Faction {i}"}, "description_i18n": {"en": "Desc"}
            }
            await crud_faction.create(self.session, obj_in=data)
        await self.session.commit()

        # Get all for test_guild_id
        all_test_guild_factions = await crud_faction.get_multi_by_guild_id(self.session, guild_id=self.test_guild_id, limit=10)
        self.assertEqual(len(all_test_guild_factions), 5)
        for fac in all_test_guild_factions:
            self.assertEqual(fac.guild_id, self.test_guild_id)

        # Test pagination: limit
        limited_factions = await crud_faction.get_multi_by_guild_id(self.session, guild_id=self.test_guild_id, limit=2)
        self.assertEqual(len(limited_factions), 2)

        # Test pagination: skip
        skipped_factions = await crud_faction.get_multi_by_guild_id(self.session, guild_id=self.test_guild_id, skip=3, limit=5)
        self.assertEqual(len(skipped_factions), 2) # 5 total, skip 3, leaves 2

        # Test pagination: skip and limit together
        skip_limit_factions = await crud_faction.get_multi_by_guild_id(self.session, guild_id=self.test_guild_id, skip=1, limit=2)
        self.assertEqual(len(skip_limit_factions), 2)

        # Verify the correct items were skipped and limited based on default ordering (ID)
        # This assumes default ordering by ID, which is typical but not guaranteed by all DBs without explicit ORDER BY.
        # For SQLite in-memory, it's usually consistent.
        expected_names_skip_limit = {f.name_i18n["en"] for f in factions_test_guild[1:3]}
        actual_names_skip_limit = {f.name_i18n["en"] for f in skip_limit_factions}
        self.assertSetEqual(actual_names_skip_limit, expected_names_skip_limit)

        # Get for a guild with no factions (create a new temp guild_id)
        no_factions_guild_id = 303
        guild = await self.session.get(GuildConfig, no_factions_guild_id)
        if not guild:
            self.session.add(GuildConfig(id=no_factions_guild_id, main_language="en", name=f"Guild {no_factions_guild_id}"))
            await self.session.commit()

        no_factions = await crud_faction.get_multi_by_guild_id(self.session, guild_id=no_factions_guild_id)
        self.assertEqual(len(no_factions), 0)

    async def test_update_faction(self):
        faction_data = {
            "guild_id": self.test_guild_id, "static_id": "update_me_faction",
            "name_i18n": {"en": "Original Name"}, "description_i18n": {"en": "Original Desc"},
            "resources_json": {"gold": 100}
        }
        faction = await crud_faction.create(self.session, obj_in=faction_data)
        await self.session.commit()

        update_payload = {
            "name_i18n": {"en": "Updated Name", "ru": "Обновленное Имя"}, # Full replace for i18n dict
            "description_i18n": {"en": "Updated Desc"}, # Full replace
            "ideology_i18n": {"en": "New Ideology"}, # Adding new field
            "resources_json": {"gold": 200, "wood": 50}, # Full replace for json field
            "static_id": "new_static_id_should_not_change_if_not_explicitly_coded_in_update"
            # ^ static_id typically isn't updated or is handled specially.
            # CRUDBase.update updates fields present in obj_in (Pydantic model or dict).
            # If static_id is part of the Pydantic model used for update, it would be updated.
            # Here, we are passing a dict.
        }

        # Ensure we are passing a dict to obj_in as per CRUDBase.update signature for obj_in: UpdateSchemaType
        # which is a TypeVar bound to BaseModel. For dicts, it means keys should match model fields.
        updated_faction = await crud_faction.update(self.session, db_obj=faction, obj_in=update_payload)
        await self.session.commit()
        await self.session.refresh(updated_faction) # Refresh to get latest state from DB

        # name_i18n and description_i18n are non-nullable
        self.assertEqual(updated_faction.name_i18n["en"], "Updated Name")
        self.assertEqual(updated_faction.name_i18n.get("ru"), "Обновленное Имя")
        self.assertEqual(updated_faction.description_i18n["en"], "Updated Desc")
        self.assertIsNone(updated_faction.description_i18n.get("ru")) # ru key was not in update payload

        # ideology_i18n, resources_json are Optional[Dict]
        if updated_faction.ideology_i18n:
            self.assertEqual(updated_faction.ideology_i18n.get("en"), "New Ideology")
        else:
            # This would be an error if ideology was expected from update_payload
            self.assertIsNotNone(updated_faction.ideology_i18n, "ideology_i18n should have been set")

        if updated_faction.resources_json:
            self.assertEqual(updated_faction.resources_json.get("gold"), 200)
            self.assertEqual(updated_faction.resources_json.get("wood"), 50)
        else:
            self.assertIsNotNone(updated_faction.resources_json, "resources_json should have been set")


        # Check that static_id DID change, because it was in the update_payload.
        self.assertEqual(updated_faction.static_id, "new_static_id_should_not_change_if_not_explicitly_coded_in_update")

        # Test actual update of static_id again with a different value
        critical_update_payload = {"static_id": "actually_updated_sid_again"}
        updated_faction_sid = await crud_faction.update(self.session, db_obj=faction, obj_in=critical_update_payload)
        await self.session.commit()
        await self.session.refresh(updated_faction_sid)
        self.assertEqual(updated_faction_sid.static_id, "actually_updated_sid_again")


        self.assertEqual(updated_faction.guild_id, self.test_guild_id) # guild_id should not change

    async def test_delete_faction(self):
        faction_data = {
            "guild_id": self.test_guild_id, "static_id": "delete_me_faction",
            "name_i18n": {"en": "DeleteMe"}, "description_i18n": {"en": "Desc"}
        }
        faction = await crud_faction.create(self.session, obj_in=faction_data)
        await self.session.commit()
        faction_id = faction.id
        self.assertIsNotNone(faction_id)

        # Delete the faction
        # CRUDBase.delete takes id directly. No guild_id check in base method.
        await crud_faction.delete(self.session, id=faction_id) # Corrected from remove to delete
        await self.session.commit()

        # Verify it's deleted
        deleted_faction = await crud_faction.get(self.session, id=faction_id)
        self.assertIsNone(deleted_faction)

        # Try deleting non-existent faction (should not raise error)
        await crud_faction.delete(self.session, id=99999) # Corrected from remove to delete
        await self.session.commit()


if __name__ == "__main__":
    unittest.main()
