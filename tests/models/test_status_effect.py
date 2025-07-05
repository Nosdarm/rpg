import sys
import os
import unittest
from datetime import datetime

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import JSON

from src.models.base import Base
from src.models.guild import GuildConfig
from src.models.status_effect import ActiveStatusEffect, StatusEffect

# Use an in-memory SQLite database for testing
engine = create_engine("sqlite:///:memory:")

# The models StatusEffect and ActiveStatusEffect now use JsonBForSQLite directly,
# which handles SQLite compatibility by mapping to the standard JSON type (backed by TEXT).
# Therefore, a global event listener to convert JSONB to JSON for all tables in Base.metadata
# is no longer needed for these specific models in this test file.

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class TestStatusEffectModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=engine)

    def setUp(self):
        self.session = SessionLocal()
        # Create a dummy guild for FK constraints
        self.guild = GuildConfig(id=1, main_language="en")
        self.session.add(self.guild)
        self.session.commit()

    def tearDown(self):
        self.session.rollback() # Rollback any uncommitted changes
        # Clean up all data from tables after each test
        for table in reversed(Base.metadata.sorted_tables):
            self.session.execute(table.delete())
        self.session.commit()
        self.session.close()

    def test_create_status_effect(self):
        status_effect_data = {
            "guild_id": self.guild.id,
            "static_id": "test_status",
            "name_i18n": {"en": "Test Status", "ru": "Тестовый статус"},
            "description_i18n": {"en": "This is a test status effect.", "ru": "Это тестовый статусный эффект."},
            "properties_json": {"modifier": {"strength": -1}, "duration": 3},
        }
        status_effect = StatusEffect(**status_effect_data)
        self.session.add(status_effect)
        self.session.flush()
        self.session.refresh(status_effect)
        self.session.commit()

        retrieved_status_effect = self.session.query(StatusEffect).filter_by(static_id="test_status").first()
        self.assertIsNotNone(retrieved_status_effect)
        assert retrieved_status_effect is not None # For Pyright
        self.assertEqual(retrieved_status_effect.name_i18n["en"], "Test Status")
        self.assertEqual(retrieved_status_effect.properties_json["duration"], 3)
        self.assertEqual(retrieved_status_effect.guild_id, self.guild.id)
        # self.assertIn("Test Status", repr(retrieved_status_effect)) # Repr does not include name


    def test_create_active_status_effect(self):
        status_effect = StatusEffect(
            guild_id=self.guild.id,
            static_id="test_debuff",
            name_i18n={"en": "Test Debuff"},
            description_i18n={"en": "A debuff for testing."},
            properties_json={"effect": "slow"},
        )
        self.session.add(status_effect)
        self.session.flush()
        self.session.refresh(status_effect)
        self.session.commit()

        active_status_data = {
            "entity_id": 101,
            "entity_type": "player",
            "status_effect_id": status_effect.id,
            "guild_id": self.guild.id,
            "duration_turns": 5,
            "remaining_turns": 5,
            "source_ability_id": 1,
            "custom_properties_json": {"intensity": 2},
        }
        active_status = ActiveStatusEffect(**active_status_data)
        self.session.add(active_status)
        self.session.flush()
        self.session.refresh(active_status)
        self.session.commit()

        retrieved_active_status = self.session.query(ActiveStatusEffect).filter_by(entity_id=101).first()
        self.assertIsNotNone(retrieved_active_status)
        assert retrieved_active_status is not None # For Pyright
        self.assertEqual(retrieved_active_status.status_effect_id, status_effect.id)
        self.assertEqual(retrieved_active_status.entity_type, "player")
        self.assertEqual(retrieved_active_status.duration_turns, 5)
        self.assertIsNotNone(retrieved_active_status.applied_at)
        self.assertTrue(isinstance(retrieved_active_status.applied_at, datetime))
        self.assertIsNotNone(retrieved_active_status.custom_properties_json, "custom_properties_json should not be None")
        assert retrieved_active_status.custom_properties_json is not None # For Pyright, though assertIsNotNone should be enough
        self.assertEqual(retrieved_active_status.custom_properties_json["intensity"], 2)
        self.assertEqual(retrieved_active_status.guild_id, self.guild.id)
        self.assertIn(f"status_effect_id={status_effect.id}", repr(retrieved_active_status))
        self.assertIn("entity_id=101", repr(retrieved_active_status))

    def test_status_effect_repr(self):
        status_effect = StatusEffect(
            guild_id=self.guild.id,
            static_id="repr_status",
            name_i18n={"en": "Repr Status"},
        )
        self.session.add(status_effect)
        self.session.commit()
        expected_repr = f"<StatusEffect(id={status_effect.id}, static_id='repr_status', guild_id={self.guild.id})>"
        self.assertEqual(repr(status_effect), expected_repr)

    def test_active_status_effect_repr(self):
        status_effect = StatusEffect(
            guild_id=self.guild.id,
            static_id="active_repr_status",
        )
        self.session.add(status_effect)
        self.session.commit()

        active_status = ActiveStatusEffect(
            entity_id=202,
            entity_type="npc",
            status_effect_id=status_effect.id,
            guild_id=self.guild.id,
        )
        self.session.add(active_status)
        self.session.commit()
        expected_repr = f"<ActiveStatusEffect(id={active_status.id}, status_effect_id={status_effect.id}, entity_id=202, entity_type='npc', guild_id={self.guild.id})>"
        self.assertEqual(repr(active_status), expected_repr)

if __name__ == "__main__":
    unittest.main()
