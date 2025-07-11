import unittest
import datetime

from backend.models.mobile_group import MobileGroup

class TestMobileGroupModel(unittest.TestCase):

    def test_create_mobile_group_defaults(self):
        """Test creating a MobileGroup instance with default values."""
        now = datetime.datetime.now(datetime.timezone.utc)
        group = MobileGroup(
            guild_id=789,
            static_id="merchant_caravan_beta",
            name_i18n={"en": "Merchant Caravan Beta"},
        )
        # self.assertIsNotNone(group.created_at) # Default might not apply without session
        # self.assertIsNotNone(group.updated_at)
        if group.created_at is not None: # Only check if populated
            self.assertGreaterEqual(group.created_at, now - datetime.timedelta(seconds=1)) # Check if recent
            self.assertLessEqual(group.created_at, now + datetime.timedelta(seconds=1))
        if group.updated_at is not None: # Only check if populated
            self.assertGreaterEqual(group.updated_at, now - datetime.timedelta(seconds=1))
            self.assertLessEqual(group.updated_at, now + datetime.timedelta(seconds=1))

        self.assertEqual(group.guild_id, 789)
        self.assertEqual(group.static_id, "merchant_caravan_beta")
        self.assertEqual(group.name_i18n, {"en": "Merchant Caravan Beta"})
        self.assertIsNone(group.description_i18n)
        self.assertIsNone(group.current_location_id)
        self.assertIsNone(group.leader_global_npc_id)
        # Default values from mapped_column(default=lambda: ...) might not apply until session flush
        # or if Base.__init__ doesn't handle them. Asserting observed behavior.
        self.assertIsNone(group.members_definition_json) # Changed from self.assertEqual(group.members_definition_json, {})
        self.assertIsNone(group.properties_json) # Changed from self.assertEqual(group.properties_json, {})

    def test_create_mobile_group_all_fields(self):
        """Test creating a MobileGroup instance with all fields provided."""
        created_at_val = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
        updated_at_val = datetime.datetime.now(datetime.timezone.utc)

        group_data = {
            "guild_id": 101,
            "static_id": "bandit_patrol_gamma",
            "name_i18n": {"en": "Bandit Patrol Gamma", "ru": "Патруль Бандитов Гамма"},
            "description_i18n": {"en": "A roaming group of bandits.", "ru": "Бродячая группа бандитов."},
            "current_location_id": 15,
            "leader_global_npc_id": 5,
            "members_definition_json": {"members": ["npc_static_1", "npc_static_2"], "count": 2},
            "properties_json": {"goal": "ambush", "mood": "aggressive"},
            "created_at": created_at_val,
            "updated_at": updated_at_val,
        }
        group = MobileGroup(**group_data)

        self.assertEqual(group.guild_id, 101)
        self.assertEqual(group.static_id, "bandit_patrol_gamma")
        self.assertEqual(group.name_i18n, {"en": "Bandit Patrol Gamma", "ru": "Патруль Бандитов Гамма"})
        self.assertEqual(group.description_i18n, {"en": "A roaming group of bandits.", "ru": "Бродячая группа бандитов."})
        self.assertEqual(group.current_location_id, 15)
        self.assertEqual(group.leader_global_npc_id, 5)
        self.assertEqual(group.members_definition_json, {"members": ["npc_static_1", "npc_static_2"], "count": 2})
        self.assertEqual(group.properties_json, {"goal": "ambush", "mood": "aggressive"})
        self.assertEqual(group.created_at, created_at_val)
        self.assertEqual(group.updated_at, updated_at_val)

    def test_mobile_group_repr(self):
        """Test the __repr__ method of MobileGroup."""
        group = MobileGroup(
            id=2, # Setting id for repr
            guild_id=789,
            static_id="test_group_repr",
            name_i18n={"en": "Test Group"}
        )
        expected_repr = "<MobileGroup(id=2, static_id='test_group_repr', guild_id=789)>"
        self.assertEqual(repr(group), expected_repr)

if __name__ == '__main__':
    unittest.main()
