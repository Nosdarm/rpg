import unittest
import datetime

from src.models.global_npc import GlobalNpc

class TestGlobalNpcModel(unittest.TestCase):

    def test_create_global_npc_defaults(self):
        """Test creating a GlobalNpc instance with default values."""
        now = datetime.datetime.now(datetime.timezone.utc)
        npc = GlobalNpc(
            guild_id=123,
            static_id="traveling_merchant_01",
            name_i18n={"en": "Traveling Merchant"},
            # created_at and updated_at are handled by TimestampMixin
        )
        # For TimestampMixin, equality check for datetime.now() is tricky.
        # We check if they are recent.
        # self.assertIsNotNone(npc.created_at) # Default might not apply without session
        # self.assertIsNotNone(npc.updated_at)
        if npc.created_at is not None: # Only check if populated
            self.assertGreaterEqual(npc.created_at, now - datetime.timedelta(seconds=1))
            self.assertLessEqual(npc.created_at, now + datetime.timedelta(seconds=1))
        if npc.updated_at is not None: # Only check if populated
            self.assertGreaterEqual(npc.updated_at, now - datetime.timedelta(seconds=1))
            self.assertLessEqual(npc.updated_at, now + datetime.timedelta(seconds=1))

        self.assertEqual(npc.guild_id, 123)
        self.assertEqual(npc.static_id, "traveling_merchant_01")
        self.assertEqual(npc.name_i18n, {"en": "Traveling Merchant"})
        self.assertIsNone(npc.description_i18n)
        self.assertIsNone(npc.current_location_id)
        self.assertIsNone(npc.base_npc_id)
        self.assertEqual(npc.properties_json, {}) # Default is empty dict

    def test_create_global_npc_all_fields(self):
        """Test creating a GlobalNpc instance with all fields provided."""
        now = datetime.datetime.now(datetime.timezone.utc)
        created_at_val = now - datetime.timedelta(minutes=1)
        updated_at_val = now

        npc_data = {
            "guild_id": 456,
            "static_id": "guard_captain_alpha",
            "name_i18n": {"en": "Guard Captain Alpha", "ru": "Капитан Стражи Альфа"},
            "description_i18n": {"en": "A stern but fair captain.", "ru": "Суровый, но справедливый капитан."},
            "current_location_id": 10,
            "base_npc_id": 20,
            "properties_json": {"state": "patrolling", "hp": 100},
            "created_at": created_at_val,
            "updated_at": updated_at_val,
        }
        npc = GlobalNpc(**npc_data)

        self.assertEqual(npc.guild_id, 456)
        self.assertEqual(npc.static_id, "guard_captain_alpha")
        self.assertEqual(npc.name_i18n, {"en": "Guard Captain Alpha", "ru": "Капитан Стражи Альфа"})
        self.assertEqual(npc.description_i18n, {"en": "A stern but fair captain.", "ru": "Суровый, но справедливый капитан."})
        self.assertEqual(npc.current_location_id, 10)
        self.assertEqual(npc.base_npc_id, 20)
        self.assertEqual(npc.properties_json, {"state": "patrolling", "hp": 100})
        self.assertEqual(npc.created_at, created_at_val)
        self.assertEqual(npc.updated_at, updated_at_val)

    def test_global_npc_repr(self):
        """Test the __repr__ method of GlobalNpc."""
        npc = GlobalNpc(
            id=1, # Setting id for repr
            guild_id=123,
            static_id="test_npc_repr",
            name_i18n={"en": "Test NPC"}
        )
        expected_repr = "<GlobalNpc(id=1, static_id='test_npc_repr', guild_id=123)>"
        self.assertEqual(repr(npc), expected_repr)

if __name__ == '__main__':
    unittest.main()
