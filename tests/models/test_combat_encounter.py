import sys
import os
import unittest
from sqlalchemy import create_engine, BigInteger, Integer, Text, Enum as SQLAlchemyEnum
from sqlalchemy.orm import sessionmaker, Mapped, mapped_column
# Removed: from sqlalchemy.dialects.postgresql import JSONB
# Removed: from sqlalchemy.ext.compiler import compiles
# Removed: from sqlalchemy.types import JSON
import datetime

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.models.base import Base
from backend.models.enums import CombatStatus
from backend.models.combat_encounter import CombatEncounter # This model now uses JsonBForSQLite

DATABASE_URL = "sqlite:///:memory:"

# Removed the @compiles(JSONB, 'sqlite') decorator as CombatEncounter model handles JSONB compatibility via JsonBForSQLite

class TestCombatEncounterModel(unittest.TestCase):
    engine = None
    SessionLocal = None

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(DATABASE_URL)
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        if cls.engine:
            Base.metadata.drop_all(cls.engine)
            cls.engine.dispose()

    def setUp(self):
        assert self.SessionLocal is not None, "SessionLocal should be initialized by setUpClass"
        self.session = self.SessionLocal()

    def tearDown(self):
        if self.session:
            self.session.rollback()
            self.session.close()

    def test_create_combat_encounter_defaults(self):
        """Тест создания CombatEncounter с минимальными обязательными полями и значениями по умолчанию."""
        combat = CombatEncounter(guild_id=123456789012345678)

        self.session.add(combat)
        self.session.commit()
        self.session.refresh(combat)

        self.assertIsNotNone(combat.id)
        self.assertEqual(combat.guild_id, 123456789012345678)
        self.assertEqual(combat.status, CombatStatus.PENDING_START)
        self.assertIsNone(combat.location_id)
        self.assertIsNone(combat.current_turn_entity_id)
        self.assertIsNone(combat.current_turn_entity_type)
        self.assertIsNone(combat.turn_order_json)
        self.assertIsNone(combat.rules_config_snapshot_json)
        self.assertIsNone(combat.participants_json)
        self.assertIsNone(combat.combat_log_json)

    def test_create_combat_encounter_all_fields(self):
        """Тест создания CombatEncounter со всеми указанными полями."""
        guild_id = 111
        location_id = 222
        status = CombatStatus.ACTIVE
        current_turn_entity_id = 333
        current_turn_entity_type = "player"
        turn_order = {"order": [{"id": 333, "type": "player"}, {"id": 444, "type": "npc"}], "current_index": 0}
        rules_snapshot = {"some_rule": "some_value"}
        participants = {"entities": [{"id": 333, "type": "player", "hp": 100}, {"id": 444, "type": "npc", "hp": 50}]}
        combat_log = {"entries": [{"action": "player attacks npc"}]}

        combat = CombatEncounter(
            guild_id=guild_id,
            location_id=location_id,
            status=status,
            current_turn_entity_id=current_turn_entity_id,
            current_turn_entity_type=current_turn_entity_type,
            turn_order_json=turn_order,
            rules_config_snapshot_json=rules_snapshot,
            participants_json=participants,
            combat_log_json=combat_log
        )
        self.session.add(combat)
        self.session.commit()
        self.session.refresh(combat)

        self.assertIsNotNone(combat.id)
        self.assertEqual(combat.guild_id, guild_id)
        self.assertEqual(combat.location_id, location_id)
        self.assertEqual(combat.status, status)
        self.assertEqual(combat.current_turn_entity_id, current_turn_entity_id)
        self.assertEqual(combat.current_turn_entity_type, current_turn_entity_type)
        self.assertEqual(combat.turn_order_json, turn_order)
        self.assertEqual(combat.rules_config_snapshot_json, rules_snapshot)
        self.assertEqual(combat.participants_json, participants)
        self.assertEqual(combat.combat_log_json, combat_log)

    def test_repr_method(self):
        """Тест __repr__ метода."""
        combat = CombatEncounter(guild_id=987, status=CombatStatus.ENDED_VICTORY_PLAYERS)
        self.session.add(combat)
        self.session.commit()
        self.session.refresh(combat)

        expected_repr = f"<CombatEncounter(id={combat.id}, guild_id=987, status='ended_victory_players')>"
        self.assertEqual(repr(combat), expected_repr)

if __name__ == '__main__':
    unittest.main()
