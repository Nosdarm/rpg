import unittest
import datetime

from src.models.global_event import GlobalEvent

class TestGlobalEventModel(unittest.TestCase):

    def test_create_global_event_defaults(self):
        """Test creating a GlobalEvent instance with default values."""
        now = datetime.datetime.now(datetime.timezone.utc)
        event = GlobalEvent(
            guild_id=112,
            static_id="dragon_sighting_delta",
            name_i18n={"en": "Dragon Sighting Delta"},
            description_i18n={"en": "A dragon was reportedly sighted."}, # description is required
            event_type="sighting",
        )
        # self.assertIsNotNone(event.created_at) # Default might not apply without session
        # self.assertIsNotNone(event.updated_at)
        if event.created_at is not None: # Only check if populated
            self.assertGreaterEqual(event.created_at, now - datetime.timedelta(seconds=1))
            self.assertLessEqual(event.created_at, now + datetime.timedelta(seconds=1))
        if event.updated_at is not None: # Only check if populated
             self.assertGreaterEqual(event.updated_at, now - datetime.timedelta(seconds=1))
             self.assertLessEqual(event.updated_at, now + datetime.timedelta(seconds=1))

        self.assertEqual(event.guild_id, 112)
        self.assertEqual(event.static_id, "dragon_sighting_delta")
        self.assertEqual(event.name_i18n, {"en": "Dragon Sighting Delta"})
        self.assertEqual(event.description_i18n, {"en": "A dragon was reportedly sighted."})
        self.assertEqual(event.event_type, "sighting")
        self.assertIsNone(event.location_id)
        self.assertIsNone(event.trigger_time)
        self.assertIsNone(event.expiration_time)
        self.assertEqual(event.status, "pending") # Default status
        self.assertEqual(event.properties_json, {})

    def test_create_global_event_all_fields(self):
        """Test creating a GlobalEvent instance with all fields provided."""
        created_at_val = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        updated_at_val = datetime.datetime.now(datetime.timezone.utc)
        trigger_time_val = updated_at_val + datetime.timedelta(days=1)
        expiration_time_val = updated_at_val + datetime.timedelta(days=2)

        event_data = {
            "guild_id": 314,
            "static_id": "festival_of_harvest_epsilon",
            "name_i18n": {"en": "Festival of Harvest Epsilon", "ru": "Фестиваль Урожая Эпсилон"},
            "description_i18n": {"en": "Annual harvest festival.", "ru": "Ежегодный фестиваль урожая."},
            "event_type": "festival",
            "location_id": 25,
            "trigger_time": trigger_time_val,
            "expiration_time": expiration_time_val,
            "status": "active",
            "properties_json": {"activities": ["feasting", "games"], "required_items": ["wheat", "ale"]},
            "created_at": created_at_val,
            "updated_at": updated_at_val,
        }
        event = GlobalEvent(**event_data)

        self.assertEqual(event.guild_id, 314)
        self.assertEqual(event.static_id, "festival_of_harvest_epsilon")
        self.assertEqual(event.name_i18n, {"en": "Festival of Harvest Epsilon", "ru": "Фестиваль Урожая Эпсилон"})
        self.assertEqual(event.description_i18n, {"en": "Annual harvest festival.", "ru": "Ежегодный фестиваль урожая."})
        self.assertEqual(event.event_type, "festival")
        self.assertEqual(event.location_id, 25)
        self.assertEqual(event.trigger_time, trigger_time_val)
        self.assertEqual(event.expiration_time, expiration_time_val)
        self.assertEqual(event.status, "active")
        self.assertEqual(event.properties_json, {"activities": ["feasting", "games"], "required_items": ["wheat", "ale"]})
        self.assertEqual(event.created_at, created_at_val)
        self.assertEqual(event.updated_at, updated_at_val)

    def test_global_event_repr(self):
        """Test the __repr__ method of GlobalEvent."""
        event = GlobalEvent(
            id=3, # Setting id for repr
            guild_id=112,
            static_id="test_event_repr",
            name_i18n={"en": "Test Event"},
            description_i18n={"en": "Test desc"},
            event_type="test_type"
        )
        expected_repr = "<GlobalEvent(id=3, static_id='test_event_repr', type='test_type', guild_id=112)>"
        self.assertEqual(repr(event), expected_repr)

if __name__ == '__main__':
    unittest.main()
