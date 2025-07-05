import sys
import os
import asyncio
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession
from src.models.player import Player
from src.models.generated_npc import GeneratedNpc
from src.core.check_resolver import resolve_check, CheckError
from src.models.relationship import Relationship, RelationshipEntityType
from src.models.check_results import CheckResult, CheckOutcome, ModifierDetail


DEFAULT_RULE_VALUES = {
    "checks:some_check:dice_notation": "1d20",
    "checks:some_check:base_attribute": "strength_mod", # Changed
    "checks:some_check:critical_success_threshold": 20,
    "checks:some_check:critical_failure_threshold": 1,
    "checks:attack:dice_notation": "1d20",
    "checks:attack:base_attribute": "attack_bonus",
    "checks:attack:critical_success_threshold": 20,
    "checks:attack:critical_failure_threshold": 1,
    "checks:damage:dice_notation": "1d6",
}

class TestCheckResolver(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_db_session = AsyncMock(spec=AsyncSession)
        self.guild_id = 1
        self.player_id = 100
        self.npc_id = 200
        self.mock_player = Player(id=self.player_id, guild_id=self.guild_id, discord_id=12345, name="TestPlayer")
        setattr(self.mock_player, "strength_mod", 3)
        setattr(self.mock_player, "attack_bonus", 5)
        setattr(self.mock_player, "charisma_mod", 1)
        setattr(self.mock_player, "stealth_mod", 2)
        setattr(self.mock_player, "deception_skill", 3)
        setattr(self.mock_player, "speech_mod", 0)
        setattr(self.mock_player, "wisdom_mod", 0)

        self.mock_npc = GeneratedNpc(id=self.npc_id, guild_id=self.guild_id, name_i18n={"en": "Test Goblin"})
        setattr(self.mock_npc, "strength_mod", 1)
        setattr(self.mock_npc, "attack_bonus", 2)

    async def asyncSetUp(self):
        self.patch_get_rule = patch('src.core.check_resolver.get_rule', new_callable=AsyncMock)
        self.mock_get_rule = self.patch_get_rule.start()

        self.patch_roll_dice = patch('src.core.check_resolver.roll_dice')
        self.mock_roll_dice = self.patch_roll_dice.start()

        self.patch_get_entity_attribute = patch('src.core.check_resolver._get_entity_attribute', new_callable=AsyncMock)
        self.mock_get_entity_attribute = self.patch_get_entity_attribute.start()

        self.patch_get_entity_by_id_and_type_str = patch('src.core.check_resolver.get_entity_by_id_and_type_str', new_callable=AsyncMock)
        self.mock_get_entity_by_id_and_type_str = self.patch_get_entity_by_id_and_type_str.start()
        self.mock_get_entity_by_id_and_type_str.side_effect = lambda db, entity_type_str, entity_id, guild_id: self.mock_player if entity_id == self.player_id else (self.mock_npc if entity_id == self.npc_id else None)

        self.mock_crud_relationship_get_relationships_patcher = patch('src.core.check_resolver.crud_relationship.get_relationships_for_entity', new_callable=AsyncMock)
        self.mock_crud_relationship_get_relationships = self.mock_crud_relationship_get_relationships_patcher.start()
        self.mock_crud_relationship_get_relationships.return_value = []

    async def asyncTearDown(self):
        self.patch_get_rule.stop()
        self.patch_roll_dice.stop()
        self.patch_get_entity_attribute.stop()
        self.patch_get_entity_by_id_and_type_str.stop()
        self.mock_crud_relationship_get_relationships_patcher.stop()

    async def test_simple_success(self):
        check_type = "some_check"
        dc = 15
        self.mock_get_rule.side_effect = lambda db, guild_id, key, default=None: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "strength_mod", # Changed
            f"checks:{check_type}:critical_success_threshold": 20,
            f"checks:{check_type}:critical_failure_threshold": 1,
        }.get(key, default)
        self.mock_get_entity_attribute.return_value = 3
        self.mock_roll_dice.return_value = (14, [14])
        result = await resolve_check(db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type, actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER, difficulty_dc=dc)
        self.assertEqual(result.outcome.status, "success")
        self.assertEqual(result.final_value, 17)

    async def test_simple_failure(self):
        check_type = "some_check"
        dc = 15
        self.mock_get_rule.side_effect = lambda db, guild_id, key, default=None: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "strength_mod", # Changed
        }.get(key, DEFAULT_RULE_VALUES.get(key, default))
        self.mock_get_entity_attribute.return_value = 1
        self.mock_roll_dice.return_value = (10, [10])
        result = await resolve_check(db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type, actor_entity_id=self.npc_id, actor_entity_type=RelationshipEntityType.GENERATED_NPC, difficulty_dc=dc)
        self.assertEqual(result.outcome.status, "failure")
        self.assertEqual(result.final_value, 11)

    async def test_critical_success(self):
        check_type = "attack"
        dc = 10
        self.mock_get_rule.side_effect = lambda db, guild_id, key, default=None: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "attack_bonus",
            f"checks:{check_type}:critical_success_threshold": 20,
            f"checks:{check_type}:critical_failure_threshold": 1,
        }.get(key, default)
        self.mock_get_entity_attribute.return_value = 5
        self.mock_roll_dice.return_value = (20, [20])
        result = await resolve_check(db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type, actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER, difficulty_dc=dc)
        self.assertEqual(result.outcome.status, "critical_success")

    async def test_critical_failure(self):
        check_type = "attack"
        dc = 10
        self.mock_get_rule.side_effect = lambda db, guild_id, key, default=None: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "attack_bonus",
            f"checks:{check_type}:critical_success_threshold": 20,
            f"checks:{check_type}:critical_failure_threshold": 1,
        }.get(key, default)
        self.mock_get_entity_attribute.return_value = 5
        self.mock_roll_dice.return_value = (1, [1])
        result = await resolve_check(db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type, actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER, difficulty_dc=dc)
        self.assertEqual(result.outcome.status, "critical_failure")

    async def test_relationship_influence_roll_modifier_formula_positive(self):
        check_type = "persuasion"
        dc = 15
        self.mock_get_rule.side_effect = lambda db, guild_id, key, default=None: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "charisma_mod",
            f"relationship_influence:checks:{check_type}": { "enabled": True, "relationship_type_pattern": "personal_feeling", "roll_modifier_formula": "(rel_value // 20)" }
        }.get(key, DEFAULT_RULE_VALUES.get(key, default))
        self.mock_get_entity_attribute.return_value = 1
        self.mock_roll_dice.return_value = (10, [10])
        mock_relationship = Relationship(entity1_type=RelationshipEntityType.PLAYER, entity1_id=self.player_id, entity2_type=RelationshipEntityType.GENERATED_NPC, entity2_id=self.npc_id, relationship_type="personal_feeling", value=50, guild_id=self.guild_id)
        self.mock_crud_relationship_get_relationships.return_value = [mock_relationship]
        result = await resolve_check(db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type, actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER, target_entity_id=self.npc_id, target_entity_type=RelationshipEntityType.GENERATED_NPC, difficulty_dc=dc)
        self.assertEqual(result.total_modifier, 1 + 2)
        self.assertEqual(result.final_value, 13)
        self.assertEqual(result.outcome.status, "failure")

    async def test_relationship_influence_threshold_modifier_friendly(self):
        check_type = "diplomacy"
        dc = 12
        self.mock_get_rule.side_effect = lambda db, guild_id, key, default=None: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "speech_mod",
            f"relationship_influence:checks:{check_type}": { "enabled": True, "relationship_type_pattern": "faction_standing", "modifiers": [{"threshold_min": 30, "threshold_max": 100, "modifier": 3, "description_key": "terms.rel_check_mod.faction_ally"}]},
            "terms.rel_check_mod.faction_ally": "Faction Ally Bonus"
        }.get(key, DEFAULT_RULE_VALUES.get(key, default))
        self.mock_get_entity_attribute.return_value = 0
        self.mock_roll_dice.return_value = (10, [10])
        mock_relationship = Relationship(entity1_type=RelationshipEntityType.PLAYER, entity1_id=self.player_id, entity2_type=RelationshipEntityType.GENERATED_FACTION, entity2_id=1, relationship_type="faction_standing", value=70, guild_id=self.guild_id)
        self.mock_crud_relationship_get_relationships.return_value = [mock_relationship]
        result = await resolve_check(db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type, actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER, target_entity_id=1, target_entity_type=RelationshipEntityType.GENERATED_FACTION, difficulty_dc=dc)
        self.assertEqual(result.total_modifier, 3)
        self.assertEqual(result.final_value, 13)
        self.assertEqual(result.outcome.status, "success")

    async def test_relationship_influence_formula_error(self):
        check_type = "deception"
        dc = 10
        self.mock_get_rule.side_effect = lambda db, guild_id, key, default=None: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "deception_skill",
            f"relationship_influence:checks:{check_type}": { "enabled": True, "relationship_type_pattern": "trust_level", "roll_modifier_formula": "rel_value / 'bad_string'" }
        }.get(key, DEFAULT_RULE_VALUES.get(key, default))
        self.mock_get_entity_attribute.return_value = 3
        self.mock_roll_dice.return_value = (7, [7])
        mock_relationship = Relationship(relationship_type="trust_level", value=20, guild_id=self.guild_id, entity1_id=self.player_id, entity1_type=RelationshipEntityType.PLAYER, entity2_id=self.npc_id, entity2_type=RelationshipEntityType.GENERATED_NPC)
        self.mock_crud_relationship_get_relationships.return_value = [mock_relationship]
        result = await resolve_check(db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type, actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER, target_entity_id=self.npc_id, target_entity_type=RelationshipEntityType.GENERATED_NPC, difficulty_dc=dc)
        self.assertEqual(result.total_modifier, 3)
        self.assertEqual(result.outcome.status, "success")
        self.assertIn("relationship_roll_modifier_error", result.rule_config_snapshot)

    async def test_hidden_relationship_roll_modifier_npc_hates_player(self):
        check_type = "intimidation"
        dc = 15
        self.mock_get_rule.side_effect = lambda db, guild_id, key, default=None: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "strength_mod",
            f"hidden_relationship_effects:checks:secret_negative_to_entity": { "enabled": True, "applies_to_check_types": [check_type], "roll_modifier_formula": "-(value // 10)" }
        }.get(key, DEFAULT_RULE_VALUES.get(key, default))
        self.mock_get_entity_attribute.return_value = 2 # This will be for strength_mod
        self.mock_roll_dice.return_value = (16, [16])
        mock_hidden_relationship = Relationship(entity1_id=self.npc_id, entity1_type=RelationshipEntityType.GENERATED_NPC, entity2_id=self.player_id, entity2_type=RelationshipEntityType.PLAYER, relationship_type="secret_negative_to_entity", value=80, guild_id=self.guild_id)
        self.mock_crud_relationship_get_relationships.return_value = [mock_hidden_relationship]
        result = await resolve_check(db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type, actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER, target_entity_id=self.npc_id, target_entity_type=RelationshipEntityType.GENERATED_NPC, difficulty_dc=dc)
        self.assertEqual(result.total_modifier, 2 - 8)
        self.assertEqual(result.final_value, 10)
        self.assertEqual(result.outcome.status, "failure")

    async def test_hidden_relationship_dc_modifier_npc_likes_player(self):
        check_type = "deception"
        dc = 18
        self.mock_get_rule.side_effect = lambda db, guild_id, key, default=None: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "charisma_mod",
            f"hidden_relationship_effects:checks:secret_positive_to_entity": { "enabled": True, "applies_to_check_types": [check_type], "dc_modifier_formula": "-(value // 10)" }
        }.get(key, DEFAULT_RULE_VALUES.get(key, default))
        self.mock_get_entity_attribute.return_value = 1 # This will be for charisma_mod
        self.mock_roll_dice.return_value = (12, [12])
        mock_hidden_relationship = Relationship(entity1_id=self.npc_id, entity1_type=RelationshipEntityType.GENERATED_NPC, entity2_id=self.player_id, entity2_type=RelationshipEntityType.PLAYER, relationship_type="secret_positive_to_entity", value=50, guild_id=self.guild_id)
        self.mock_crud_relationship_get_relationships.return_value = [mock_hidden_relationship]
        result = await resolve_check(db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type, actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER, target_entity_id=self.npc_id, target_entity_type=RelationshipEntityType.GENERATED_NPC, difficulty_dc=dc)
        self.assertEqual(result.outcome.status, "success")
        self.assertEqual(result.total_modifier, 1 + 5)
        self.assertEqual(result.final_value, 18)

    async def test_hidden_relationship_no_relevant_rule_or_disabled(self):
        check_type = "stealth"
        dc = 14
        # Case 1: No rule for "secret_generic_hidden_trait"
        def side_effect_no_rule(db, guild_id, key, default=None):
            rules = {
                "checks:stealth:dice_notation": "1d20",
                "checks:stealth:base_attribute": "stealth_mod"
            }
            return rules.get(key, default)
        self.mock_get_rule.side_effect = side_effect_no_rule
        self.mock_get_entity_attribute.return_value = 2
        self.mock_roll_dice.return_value = (11, [11])
        mock_hidden_relationship = Relationship(entity1_id=self.npc_id, entity1_type=RelationshipEntityType.GENERATED_NPC, entity2_id=self.player_id, entity2_type=RelationshipEntityType.PLAYER, relationship_type="secret_generic_hidden_trait", value=50, guild_id=self.guild_id)
        self.mock_crud_relationship_get_relationships.return_value = [mock_hidden_relationship]
        result_no_rule = await resolve_check(db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type, actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER, target_entity_id=self.npc_id, target_entity_type=RelationshipEntityType.GENERATED_NPC, difficulty_dc=dc)
        self.assertEqual(result_no_rule.total_modifier, 2)
        self.assertEqual(result_no_rule.final_value, 13)
        # Case 2: Rule exists but is disabled
        def side_effect_disabled_rule(db, guild_id, key, default=None):
            rules = {
                "checks:stealth:dice_notation": "1d20",
                "checks:stealth:base_attribute": "stealth_mod",
                "hidden_relationship_effects:checks:secret_generic_hidden_trait": { "enabled": False, "roll_modifier_formula": "value // 10" }
            }
            return rules.get(key, default)
        self.mock_get_rule.side_effect = side_effect_disabled_rule
        result_disabled_rule = await resolve_check(db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type, actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER, target_entity_id=self.npc_id, target_entity_type=RelationshipEntityType.GENERATED_NPC, difficulty_dc=dc)
        self.assertEqual(result_disabled_rule.total_modifier, 2)
        self.assertEqual(result_disabled_rule.final_value, 13)

if __name__ == "__main__":
    unittest.main()
