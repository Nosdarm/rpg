import sys
import os
import asyncio
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession

# Models to be returned by mocked _get_entity_attribute or CRUD calls
from src.models.player import Player
from src.models.generated_npc import GeneratedNpc

from src.core.check_resolver import (
    resolve_check,
    CheckResult,
    CheckOutcome,
    ModifierDetail,
    ENTITY_TYPE_PLAYER,
    ENTITY_TYPE_NPC,
    CheckError
)
from src.models.relationship import Relationship, RelationshipEntityType # Added
from src.core.crud.crud_relationship import CRUDRelationship # Added

# Default values for rule fetching, can be overridden in tests
DEFAULT_RULE_VALUES = {
    "checks:some_check:dice_notation": "1d20",
    "checks:some_check:base_attribute": "strength",
    "checks:some_check:critical_success_threshold": 20,
    "checks:some_check:critical_failure_threshold": 1,
    "checks:attack:dice_notation": "1d20",
    "checks:attack:base_attribute": "attack_bonus",
    "checks:attack:critical_success_threshold": 20,
    "checks:attack:critical_failure_threshold": 1,
    "checks:damage:dice_notation": "1d6", # Example for a different type of check
}

class TestCheckResolver(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_db_session = AsyncMock(spec=AsyncSession)
        self.guild_id = 1
        self.player_id = 100
        self.npc_id = 200

        # Mock player and NPC objects
        self.mock_player = Player(id=self.player_id, guild_id=self.guild_id, discord_id=12345, name="TestPlayer")
        # Add attributes that _get_entity_attribute might fetch
        setattr(self.mock_player, "strength", 3) # Represents a +3 modifier for simplicity
        setattr(self.mock_player, "attack_bonus", 5)

        self.mock_npc = GeneratedNpc(id=self.npc_id, guild_id=self.guild_id, name_i18n={"en": "Test Goblin"})
        setattr(self.mock_npc, "strength", 1) # +1 modifier
        setattr(self.mock_npc, "attack_bonus", 2)


    async def asyncSetUp(self):
        # Patch external dependencies for all tests
        self.patch_get_rule = patch('src.core.check_resolver.get_rule', new_callable=AsyncMock)
        self.mock_get_rule = self.patch_get_rule.start()

        self.patch_roll_dice = patch('src.core.check_resolver.roll_dice')
        self.mock_roll_dice = self.patch_roll_dice.start()

        self.patch_get_entity_attribute = patch('src.core.check_resolver._get_entity_attribute', new_callable=AsyncMock)
        self.mock_get_entity_attribute = self.patch_get_entity_attribute.start()

        self.patch_get_entity_by_id_and_type_str = patch('src.core.check_resolver.get_entity_by_id_and_type_str', new_callable=AsyncMock)
        self.mock_get_entity_by_id_and_type_str = self.patch_get_entity_by_id_and_type_str.start()

        # Default mock behaviors
        self.mock_get_rule.side_effect = lambda db, guild_id, key, default=None: DEFAULT_RULE_VALUES.get(key, default)
        self.mock_crud_relationship_get_relationships = patch('src.core.check_resolver.crud_relationship.get_relationships_for_entity', new_callable=AsyncMock)
        self.mock_crud_relationship_get_relationships.return_value = [] # Default to no relationships
        self.mock_crud_relationship_get_relationships_started = self.mock_crud_relationship_get_relationships.start()


    async def asyncTearDown(self):
        self.patch_get_rule.stop()
        self.patch_roll_dice.stop()
        self.patch_get_entity_attribute.stop()
        self.patch_get_entity_by_id_and_type_str.stop()
        if hasattr(self, 'mock_crud_relationship_get_relationships_started'): # Ensure it was started
            self.mock_crud_relationship_get_relationships_started.stop()


    async def test_simple_success(self):
        check_type = "some_check"
        dc = 15

        self.mock_get_rule.side_effect = lambda db, guild_id, key: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "strength",
            f"checks:{check_type}:critical_success_threshold": 20,
            f"checks:{check_type}:critical_failure_threshold": 1,
        }.get(key)

        self.mock_get_entity_attribute.return_value = 3 # Player's strength modifier
        self.mock_roll_dice.return_value = (14, [14]) # Total, individual rolls

        result = await resolve_check(
            db=self.mock_db_session,
            guild_id=self.guild_id,
            check_type=check_type,
            actor_entity_id=self.player_id, # Updated parameter name
            actor_entity_type=RelationshipEntityType.PLAYER, # Use Enum
            difficulty_dc=dc
        )

        # Check that get_entity_by_id_and_type_str was called for the actor
        self.mock_get_entity_by_id_and_type_str.assert_any_call(
            self.mock_db_session, entity_type_str=RelationshipEntityType.PLAYER.value, entity_id=self.player_id, guild_id=self.guild_id
        )
        # Setup mock_get_entity_attribute to be called with the mocked player model
        self.mock_get_entity_by_id_and_type_str.return_value = self.mock_player


        self.assertEqual(result.outcome.status, "success")
        self.assertEqual(result.roll_used, 14)
        self.assertEqual(result.total_modifier, 3)
        self.assertEqual(result.final_value, 17) # 14 + 3
        self.assertTrue(any(md.source == "base_stat:strength" and md.value == 3 for md in result.modifier_details))

    async def test_simple_failure(self):
        check_type = "some_check"
        dc = 15

        self.mock_get_rule.side_effect = lambda db, guild_id, key: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "strength",
            f"checks:{check_type}:critical_success_threshold": 20,
            f"checks:{check_type}:critical_failure_threshold": 1,
        }.get(key)

        self.mock_get_entity_attribute.return_value = 1 # NPC's strength modifier
        self.mock_roll_dice.return_value = (10, [10])

        result = await resolve_check(
            db=self.mock_db_session,
            guild_id=self.guild_id,
            check_type=check_type,
            actor_entity_id=self.npc_id,
            actor_entity_type=RelationshipEntityType.GENERATED_NPC, # Corrected
            difficulty_dc=dc
        )
        self.mock_get_entity_by_id_and_type_str.assert_any_call(
            self.mock_db_session, entity_type_str=RelationshipEntityType.GENERATED_NPC.value, entity_id=self.npc_id, guild_id=self.guild_id
        )
        self.mock_get_entity_by_id_and_type_str.return_value = self.mock_npc

        self.assertEqual(result.outcome.status, "failure")
        self.assertEqual(result.final_value, 11) # 10 + 1

    async def test_critical_success(self):
        check_type = "attack"
        dc = 10
        self.mock_get_rule.side_effect = lambda db, guild_id, key: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "attack_bonus",
            f"checks:{check_type}:critical_success_threshold": 20,
            f"checks:{check_type}:critical_failure_threshold": 1,
        }.get(key)
        self.mock_get_entity_attribute.return_value = 5 # Player's attack bonus
        self.mock_roll_dice.return_value = (20, [20]) # Natural 20

        result = await resolve_check(
            db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type,
            actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER, # Updated
            difficulty_dc=dc
        )
        self.mock_get_entity_by_id_and_type_str.assert_any_call(
            self.mock_db_session, entity_type_str=RelationshipEntityType.PLAYER.value, entity_id=self.player_id, guild_id=self.guild_id
        )
        self.mock_get_entity_by_id_and_type_str.return_value = self.mock_player
        self.assertEqual(result.outcome.status, "critical_success")
        self.assertEqual(result.roll_used, 20)
        self.assertEqual(result.final_value, 25) # 20 + 5

    async def test_critical_failure(self):
        check_type = "attack"
        dc = 10
        self.mock_get_rule.side_effect = lambda db, guild_id, key: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "attack_bonus",
            f"checks:{check_type}:critical_success_threshold": 20,
            f"checks:{check_type}:critical_failure_threshold": 1,
        }.get(key)
        self.mock_get_entity_attribute.return_value = 5
        self.mock_roll_dice.return_value = (1, [1]) # Natural 1

        result = await resolve_check(
            db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type,
            actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER, # Updated
            difficulty_dc=dc
        )
        self.mock_get_entity_by_id_and_type_str.assert_any_call(
            self.mock_db_session, entity_type_str=RelationshipEntityType.PLAYER.value, entity_id=self.player_id, guild_id=self.guild_id
        )
        self.mock_get_entity_by_id_and_type_str.return_value = self.mock_player
        self.assertEqual(result.outcome.status, "critical_failure")
        self.assertEqual(result.roll_used, 1)
        self.assertEqual(result.final_value, 6) # 1 + 5

    async def test_situational_modifier_bonus(self):
        check_type = "some_check"
        dc = 15
        context = {"situational_bonus": 2}
        self.mock_get_rule.side_effect = lambda db, guild_id, key: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "strength",
        }.get(key, DEFAULT_RULE_VALUES.get(key)) # Fallback to defaults for crit thresholds

        self.mock_get_entity_attribute.return_value = 1 # Base strength mod
        self.mock_roll_dice.return_value = (12, [12])

        result = await resolve_check(
            db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type,
            actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER, # Updated
            difficulty_dc=dc, check_context=context
        )
        self.mock_get_entity_by_id_and_type_str.assert_any_call(
            self.mock_db_session, entity_type_str=RelationshipEntityType.PLAYER.value, entity_id=self.player_id, guild_id=self.guild_id
        )
        self.mock_get_entity_by_id_and_type_str.return_value = self.mock_player
        self.assertEqual(result.outcome.status, "success") # 12 + 1 (base) + 2 (sit) = 15
        self.assertEqual(result.total_modifier, 3) # 1 (base) + 2 (sit)
        self.assertEqual(result.final_value, 15)
        self.assertTrue(any(md.source == "context:situational_bonus" and md.value == 2 for md in result.modifier_details))

    async def test_situational_modifier_penalty(self):
        check_type = "some_check"
        dc = 10
        context = {"situational_penalty": 3}
        self.mock_get_rule.side_effect = lambda db, guild_id, key: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "strength",
        }.get(key, DEFAULT_RULE_VALUES.get(key))

        self.mock_get_entity_attribute.return_value = 2 # Base strength mod
        self.mock_roll_dice.return_value = (10, [10])

        result = await resolve_check(
            db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type,
            actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER, # Updated
            difficulty_dc=dc, check_context=context
        )
        self.mock_get_entity_by_id_and_type_str.assert_any_call(
            self.mock_db_session, entity_type_str=RelationshipEntityType.PLAYER.value, entity_id=self.player_id, guild_id=self.guild_id
        )
        self.mock_get_entity_by_id_and_type_str.return_value = self.mock_player
        self.assertEqual(result.outcome.status, "failure") # 10 + 2 (base) - 3 (sit) = 9
        self.assertEqual(result.total_modifier, -1) # 2 (base) - 3 (sit)
        self.assertEqual(result.final_value, 9)
        self.assertTrue(any(md.source == "context:situational_penalty" and md.value == -3 for md in result.modifier_details))

    async def test_no_dc_provided(self):
        check_type = "perception" # Assuming no specific rules, defaults will be used
        self.mock_get_rule.side_effect = lambda db, guild_id, key: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "wisdom", # Let's say wisdom is not set up on mock
        }.get(key, DEFAULT_RULE_VALUES.get(key))

        self.mock_get_entity_attribute.return_value = 0 # Assume wisdom mod is 0 or attr not found
        self.mock_roll_dice.return_value = (18, [18])

        result = await resolve_check(
            db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type,
            actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER # Updated
        )
        self.mock_get_entity_by_id_and_type_str.assert_any_call(
            self.mock_db_session, entity_type_str=RelationshipEntityType.PLAYER.value, entity_id=self.player_id, guild_id=self.guild_id
        )
        self.mock_get_entity_by_id_and_type_str.return_value = self.mock_player
        self.assertEqual(result.outcome.status, "value_determined")
        self.assertEqual(result.final_value, 18)
        self.assertIsNone(result.difficulty_class)

    async def test_invalid_dice_notation_rule(self):
        check_type = "bad_dice_check"
        self.mock_get_rule.side_effect = lambda db, guild_id, key: {
            f"checks:{check_type}:dice_notation": "invalid_dice", # This will cause roll_dice to fail
            f"checks:{check_type}:base_attribute": "strength",
        }.get(key)

        self.mock_get_entity_attribute.return_value = 1
        # Configure mock_roll_dice to raise ValueError for this specific input
        self.mock_roll_dice.side_effect = lambda dice_str: (_ for _ in ()).throw(ValueError("Bad dice")) if dice_str=="invalid_dice" else (10,[10])


        with self.assertRaisesRegex(CheckError, "Configuration error for check 'bad_dice_check': Invalid dice notation 'invalid_dice'."):
            await resolve_check(
                db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type,
                actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER, # Updated
                difficulty_dc=10
            )
        self.mock_get_entity_by_id_and_type_str.assert_any_call(
            self.mock_db_session, entity_type_str=RelationshipEntityType.PLAYER.value, entity_id=self.player_id, guild_id=self.guild_id
        )
        self.mock_get_entity_by_id_and_type_str.return_value = self.mock_player


    async def test_base_attribute_not_found(self):
        check_type = "some_check"
        dc = 10
        self.mock_get_rule.side_effect = lambda db, guild_id, key: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "non_existent_stat", # This attribute won't be found
        }.get(key, DEFAULT_RULE_VALUES.get(key))

        self.mock_get_entity_attribute.return_value = None # Simulate attribute not found
        self.mock_roll_dice.return_value = (12, [12])

        result = await resolve_check(
            db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type,
            actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER, # Updated
            difficulty_dc=dc
        )
        self.mock_get_entity_by_id_and_type_str.assert_any_call(
            self.mock_db_session, entity_type_str=RelationshipEntityType.PLAYER.value, entity_id=self.player_id, guild_id=self.guild_id
        )
        self.mock_get_entity_by_id_and_type_str.return_value = self.mock_player

        self.assertEqual(result.outcome.status, "success") # 12 (roll) + 0 (mod) >= 10
        self.assertEqual(result.total_modifier, 0)
        self.assertEqual(result.final_value, 12)
        # Check that no modifier detail was added for the missing base_stat, or it was added with value 0
        self.assertFalse(any(md.source == "base_stat:non_existent_stat" and md.value != 0 for md in result.modifier_details))

    # --- Tests for Relationship Influence ---

    async def test_relationship_influence_roll_modifier_formula_positive(self):
        check_type = "persuasion"
        dc = 15
        self.mock_get_rule.side_effect = lambda db, guild_id, key, default=None: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "charisma_mod", # Assuming charisma_mod is fetched
            f"relationship_influence:checks:{check_type}": {
                "enabled": True,
                "relationship_type_pattern": "personal_feeling",
                "roll_modifier_formula": "(rel_value // 20)" # e.g., rel_value=50 -> +2 mod
            }
        }.get(key, DEFAULT_RULE_VALUES.get(key, default))

        self.mock_get_entity_attribute.return_value = 1 # Player's charisma_mod
        self.mock_roll_dice.return_value = (10, [10])

        # Mock relationship
        mock_relationship = Relationship(
            entity1_type=RelationshipEntityType.PLAYER, entity1_id=self.player_id,
            entity2_type=RelationshipEntityType.NPC, entity2_id=self.npc_id,
            relationship_type="personal_feeling", value=50, guild_id=self.guild_id
        )
        self.mock_crud_relationship_get_relationships.return_value = [mock_relationship]

        result = await resolve_check(
            db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type,
            actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER,
            target_entity_id=self.npc_id, target_entity_type=RelationshipEntityType.GENERATED_NPC,
            difficulty_dc=dc
        )
        # Mock calls for loading actor and target models
        self.mock_get_entity_by_id_and_type_str.assert_any_call(
            self.mock_db_session, entity_type_str=RelationshipEntityType.PLAYER.value, entity_id=self.player_id, guild_id=self.guild_id
        )
        self.mock_get_entity_by_id_and_type_str.assert_any_call(
            self.mock_db_session, entity_type_str=RelationshipEntityType.GENERATED_NPC.value, entity_id=self.npc_id, guild_id=self.guild_id
        )
        # Ensure return values are set for subsequent calls if models are re-fetched or used by _get_entity_attribute
        def side_effect_load_entities(db, entity_type_str, entity_id, guild_id):
            if entity_id == self.player_id: return self.mock_player
            if entity_id == self.npc_id: return self.mock_npc
            return None
        self.mock_get_entity_by_id_and_type_str.side_effect = side_effect_load_entities


        # Expected: roll(10) + charisma_mod(1) + rel_mod(50//20 = 2) = 13. Fails vs DC 15.
        # But we are checking the modifier application.
        self.assertEqual(result.total_modifier, 1 + 2) # charisma_mod + relationship_mod
        self.assertEqual(result.final_value, 13)
        self.assertEqual(result.outcome.status, "failure")
        self.assertTrue(any(md.source == "relationship:personal_feeling" and md.value == 2 for md in result.modifier_details))
        self.assertIn(f"relationship_influence:checks:{check_type}", result.rule_config_snapshot)
        self.assertEqual(result.rule_config_snapshot.get("relationship_roll_modifier_applied"), 2)

    async def test_relationship_influence_threshold_modifier_friendly(self):
        check_type = "diplomacy"
        dc = 12
        self.mock_get_rule.side_effect = lambda db, guild_id, key, default=None: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "speech_mod",
            f"relationship_influence:checks:{check_type}": {
                "enabled": True,
                "relationship_type_pattern": "faction_standing",
                "modifiers": [
                    {"threshold_min": 30, "threshold_max": 100, "modifier": 3, "description_key": "terms.rel_check_mod.faction_ally"}
                ]
            },
            "terms.rel_check_mod.faction_ally": "Faction Ally Bonus" # Mock localization
        }.get(key, DEFAULT_RULE_VALUES.get(key, default))

        self.mock_get_entity_attribute.return_value = 0 # Player's speech_mod
        self.mock_roll_dice.return_value = (10, [10])
        mock_relationship = Relationship(
            entity1_type=RelationshipEntityType.PLAYER, entity1_id=self.player_id,
            entity2_type=RelationshipEntityType.GENERATED_FACTION, entity2_id=1, # Corrected Enum
            relationship_type="faction_standing", value=70, guild_id=self.guild_id
        )
        self.mock_crud_relationship_get_relationships.return_value = [mock_relationship]

        def side_effect_load_entities_faction(db, entity_type_str, entity_id, guild_id):
            if entity_id == self.player_id: return self.mock_player
            # Mock for Faction model if needed for name resolution, not strictly needed for this test logic
            # if entity_type_str == RelationshipEntityType.GENERATED_FACTION.value and entity_id == 1: return MagicMock(spec=GeneratedFaction, name="TestFaction")
            return None
        self.mock_get_entity_by_id_and_type_str.side_effect = side_effect_load_entities_faction

        result = await resolve_check(
            db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type,
            actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER,
            target_entity_id=1, target_entity_type=RelationshipEntityType.GENERATED_FACTION, # Corrected Enum
            difficulty_dc=dc
        )
        # Expected: roll(10) + speech_mod(0) + rel_mod(3) = 13. Success vs DC 12.
        self.assertEqual(result.total_modifier, 3)
        self.assertEqual(result.final_value, 13)
        self.assertEqual(result.outcome.status, "success")
        self.assertTrue(any(md.source == "relationship:faction_standing" and md.value == 3 and md.description == "Faction Ally Bonus" for md in result.modifier_details))
        self.assertEqual(result.rule_config_snapshot.get("relationship_threshold_modifier_applied"), 3)

    async def test_relationship_influence_disabled(self):
        check_type = "persuasion"
        dc = 15
        self.mock_get_rule.side_effect = lambda db, guild_id, key, default=None: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "charisma_mod",
            f"relationship_influence:checks:{check_type}": {
                "enabled": False, # Rule is disabled
                "relationship_type_pattern": "personal_feeling",
                "roll_modifier_formula": "(rel_value // 20)"
            }
        }.get(key, DEFAULT_RULE_VALUES.get(key, default))

        self.mock_get_entity_attribute.return_value = 1 # charisma_mod
        self.mock_roll_dice.return_value = (10, [10])
        mock_relationship = Relationship(relationship_type="personal_feeling", value=50, guild_id=self.guild_id, entity1_id=self.player_id, entity1_type=RelationshipEntityType.PLAYER, entity2_id=self.npc_id, entity2_type=RelationshipEntityType.GENERATED_NPC) # Corrected Enum
        self.mock_crud_relationship_get_relationships.return_value = [mock_relationship]
        self.mock_get_entity_by_id_and_type_str.side_effect = \
            lambda db, entity_type_str, entity_id, guild_id: self.mock_player if entity_id == self.player_id else (self.mock_npc if entity_id == self.npc_id else None)

        result = await resolve_check(
            db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type,
            actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER,
            target_entity_id=self.npc_id, target_entity_type=RelationshipEntityType.GENERATED_NPC, # Corrected Enum
            difficulty_dc=dc
        )
        # Expected: roll(10) + charisma_mod(1) = 11. No relationship mod.
        self.assertEqual(result.total_modifier, 1)
        self.assertEqual(result.final_value, 11)
        self.assertNotIn("relationship_roll_modifier_applied", result.rule_config_snapshot)
        self.assertFalse(any(md.source.startswith("relationship:") for md in result.modifier_details))

    async def test_relationship_influence_pattern_mismatch(self):
        check_type = "intimidation"
        dc = 10
        self.mock_get_rule.side_effect = lambda db, guild_id, key, default=None: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "strength_mod",
            f"relationship_influence:checks:{check_type}": {
                "enabled": True,
                "relationship_type_pattern": "rivalry", # Expecting 'rivalry' type
                "roll_modifier_formula": "(rel_value // 10)"
            }
        }.get(key, DEFAULT_RULE_VALUES.get(key, default))

        self.mock_get_entity_attribute.return_value = 2 # strength_mod
        self.mock_roll_dice.return_value = (8, [8])
        # Relationship is 'personal_feeling', not 'rivalry'
        mock_relationship = Relationship(relationship_type="personal_feeling", value=30, guild_id=self.guild_id, entity1_id=self.player_id, entity1_type=RelationshipEntityType.PLAYER, entity2_id=self.npc_id, entity2_type=RelationshipEntityType.GENERATED_NPC) # Corrected Enum
        self.mock_crud_relationship_get_relationships.return_value = [mock_relationship]
        self.mock_get_entity_by_id_and_type_str.side_effect = \
            lambda db, entity_type_str, entity_id, guild_id: self.mock_player if entity_id == self.player_id else (self.mock_npc if entity_id == self.npc_id else None)

        result = await resolve_check(
            db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type,
            actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER,
            target_entity_id=self.npc_id, target_entity_type=RelationshipEntityType.GENERATED_NPC, # Corrected Enum
            difficulty_dc=dc
        )
        # Expected: roll(8) + strength_mod(2) = 10. No relationship mod due to pattern mismatch.
        self.assertEqual(result.total_modifier, 2)
        self.assertEqual(result.final_value, 10) # Success (10 vs 10)
        self.assertEqual(result.outcome.status, "success")
        self.assertEqual(result.rule_config_snapshot.get("relationship_applicable_value"), "not_found")
        self.assertFalse(any(md.source.startswith("relationship:") for md in result.modifier_details))

    async def test_relationship_influence_formula_error(self):
        check_type = "deception"
        dc = 10
        self.mock_get_rule.side_effect = lambda db, guild_id, key, default=None: {
            f"checks:{check_type}:dice_notation": "1d20",
            f"checks:{check_type}:base_attribute": "deception_skill",
            f"relationship_influence:checks:{check_type}": {
                "enabled": True,
                "relationship_type_pattern": "trust_level",
                "roll_modifier_formula": "rel_value / 'bad_string'" # This will cause eval error
            }
        }.get(key, DEFAULT_RULE_VALUES.get(key, default))

        self.mock_get_entity_attribute.return_value = 3 # deception_skill
        self.mock_roll_dice.return_value = (7, [7])
        mock_relationship = Relationship(relationship_type="trust_level", value=20, guild_id=self.guild_id, entity1_id=self.player_id, entity1_type=RelationshipEntityType.PLAYER, entity2_id=self.npc_id, entity2_type=RelationshipEntityType.GENERATED_NPC) # Corrected Enum
        self.mock_crud_relationship_get_relationships.return_value = [mock_relationship]
        self.mock_get_entity_by_id_and_type_str.side_effect = \
            lambda db, entity_type_str, entity_id, guild_id: self.mock_player if entity_id == self.player_id else (self.mock_npc if entity_id == self.npc_id else None)

        result = await resolve_check(
            db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type,
            actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER,
            target_entity_id=self.npc_id, target_entity_type=RelationshipEntityType.GENERATED_NPC, # Corrected Enum
            difficulty_dc=dc
        )
        # Expected: roll(7) + skill(3) = 10. No relationship mod due to formula error.
        self.assertEqual(result.total_modifier, 3)
        self.assertEqual(result.final_value, 10)
        self.assertEqual(result.outcome.status, "success")
        self.assertIn("relationship_roll_modifier_error", result.rule_config_snapshot)
        self.assertFalse(any(md.source.startswith("relationship:") for md in result.modifier_details))

    # --- Tests for Hidden Relationship Influence (Task 38) ---

    async def test_hidden_relationship_roll_modifier_npc_hates_player(self):
        check_type = "intimidation" # Player tries to intimidate NPC
        dc = 15
        # Player is actor, NPC is target. NPC has hidden hate for player.
        # Rule: If NPC secretly hates player (value high), player's intimidation gets a penalty.
        # player_matches_relationship will be true if actor (player) is target of hidden relationship.
        # Here, NPC (target_entity) has a hidden relationship concerning the player (actor_entity).
        # The formula "(value // 10) * (if player_matches_relationship then -1 else 1)"
        # If NPC hates Player (value=80), and player_matches_relationship is True (player is target of this hate),
        # then modifier is (80//10) * -1 = -8 to player's roll.

        def side_effect_get_rule(db, guild_id, key, default=None):
            rules = {
                f"checks:{check_type}:dice_notation": "1d20",
                f"checks:{check_type}:base_attribute": "strength_mod", # Player's strength_mod
                f"hidden_relationship_effects:checks:secret_negative_to_entity": {
                    "enabled": True,
                    "applies_to_check_types": [check_type],
                    # Player is actor, NPC is target. NPC has hidden rel TO player.
                    # So, player_matches_relationship should be True if player is entity2 of the relationship.
                    "roll_modifier_formula": "-(value // 10)" # Simpler: if NPC has secret_negative value 80, player gets -8.
                }
            }
            return rules.get(key, DEFAULT_RULE_VALUES.get(key, default))
        self.mock_get_rule.side_effect = side_effect_get_rule

        self.mock_get_entity_attribute.return_value = 2 # Player's strength_mod
        self.mock_roll_dice.return_value = (16, [16]) # Player rolls 16

        # NPC (id=200) has a secret_negative_to_entity relationship towards Player (id=100)
        mock_hidden_relationship = Relationship(
            entity1_id=self.npc_id, entity1_type=RelationshipEntityType.GENERATED_NPC, # Corrected
            entity2_id=self.player_id, entity2_type=RelationshipEntityType.PLAYER,
            relationship_type="secret_negative_to_entity", value=80, guild_id=self.guild_id
        )
        self.mock_crud_relationship_get_relationships.return_value = [mock_hidden_relationship]

        def mock_load_entity(db_session_arg, entity_type_str, entity_id_arg, guild_id_call_arg): # Renamed args
            if entity_type_str == RelationshipEntityType.PLAYER.value and entity_id_arg == self.player_id:
                return self.mock_player
            if entity_type_str == RelationshipEntityType.GENERATED_NPC.value and entity_id_arg == self.npc_id:
                return self.mock_npc
            return None
        self.mock_get_entity_by_id_and_type_str.side_effect = mock_load_entity

        result = await resolve_check(
            db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type,
            actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER,
            target_entity_id=self.npc_id, target_entity_type=RelationshipEntityType.GENERATED_NPC, # Corrected
            difficulty_dc=dc
        )

        # Expected: roll(16) + str_mod(2) - hidden_rel_penalty(80//10 = 8) = 10. Fails vs DC 15.
        self.assertEqual(result.total_modifier, 2 - 8) # str_mod - penalty
        self.assertEqual(result.final_value, 10)
        self.assertEqual(result.outcome.status, "failure")
        self.assertTrue(any(md.source == "Hidden Relationship (secret_negative_to_entity)" and md.value == -8 for md in result.modifier_details))
        self.assertIn("hidden_relationship_effects_applied", result.rule_config_snapshot)


    async def test_hidden_relationship_dc_modifier_npc_likes_player(self):
        check_type = "deception" # Player tries to deceive NPC
        dc = 18 # Base DC
        # Player is actor, NPC is target. NPC secretly likes player.
        # Rule: If NPC likes player, DC for player's deception check against this NPC is lowered.
        # Formula: "-(value // 10)" means positive 'value' (liking) results in negative DC mod (easier).
        # If NPC likes Player (value=50), DC mod is -(50//10) = -5. New DC = 18 - 5 = 13.

        def side_effect_get_rule(db, guild_id, key, default=None):
            rules = {
                f"checks:{check_type}:dice_notation": "1d20",
                f"checks:{check_type}:base_attribute": "charisma_mod",
                f"hidden_relationship_effects:checks:secret_positive_to_entity": {
                    "enabled": True,
                    "applies_to_check_types": [check_type],
                    "dc_modifier_formula": "-(value // 10)"
                }
            }
            return rules.get(key, DEFAULT_RULE_VALUES.get(key, default))
        self.mock_get_rule.side_effect = side_effect_get_rule

        self.mock_get_entity_attribute.return_value = 1 # Player's charisma_mod
        self.mock_roll_dice.return_value = (12, [12]) # Player rolls 12

        mock_hidden_relationship = Relationship(
            entity1_id=self.npc_id, entity1_type=RelationshipEntityType.GENERATED_NPC, # Corrected
            entity2_id=self.player_id, entity2_type=RelationshipEntityType.PLAYER,
            relationship_type="secret_positive_to_entity", value=50, guild_id=self.guild_id
        )
        self.mock_crud_relationship_get_relationships.return_value = [mock_hidden_relationship]

        def mock_load_entity(db_session_arg, entity_type_str, entity_id_arg, guild_id_call_arg): # Renamed
            if entity_type_str == RelationshipEntityType.PLAYER.value and entity_id_arg == self.player_id:
                return self.mock_player
            if entity_type_str == RelationshipEntityType.GENERATED_NPC.value and entity_id_arg == self.npc_id:
                return self.mock_npc
            return None
        self.mock_get_entity_by_id_and_type_str.side_effect = mock_load_entity

        result = await resolve_check(
            db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type,
            actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER,
            target_entity_id=self.npc_id, target_entity_type=RelationshipEntityType.GENERATED_NPC, # Corrected
            difficulty_dc=dc
        )

        # Original DC = 18. Hidden Rel DC mod = -(50//10) = -5. Effective DC = 13.
        # Player roll = 12, charisma_mod = 1. Total roll = 13.
        # Effective roll change due to DC mod is +5. Total modifier = 1 (charisma) + 5 (from DC change) = 6.
        # Final value = 12 (roll) + 6 (total_modifier_effective) = 18.
        # Success: 13 (effective roll) vs 13 (effective DC).

        self.assertEqual(result.outcome.status, "success")
        # total_modifier reflects changes to the roll. DC decrease of 5 is roll increase of 5.
        self.assertEqual(result.total_modifier, 1 + 5)
        self.assertEqual(result.final_value, 12 + (1+5)) # roll + total_modifier
        self.assertTrue(any(md.source == "Hidden Relationship (secret_positive_to_entity)" and md.value == 5 for md in result.modifier_details))
        self.assertIn("hidden_relationship_effects_applied", result.rule_config_snapshot)
        applied_effect = result.rule_config_snapshot["hidden_relationship_effects_applied"][0]
        self.assertEqual(applied_effect["modifier_applied_to_roll"], 5)


    async def test_hidden_relationship_no_relevant_rule_or_disabled(self):
        check_type = "stealth"
        dc = 14

        # Case 1: No rule for "secret_generic_hidden_trait"
        def side_effect_no_rule(db, guild_id, key, default=None):
            return {"checks:stealth:dice_notation": "1d20"}.get(key, default)
        self.mock_get_rule.side_effect = side_effect_no_rule

        self.mock_get_entity_attribute.return_value = 2 # Player's stealth_mod
        self.mock_roll_dice.return_value = (11, [11]) # Player rolls 11

        mock_hidden_relationship = Relationship(
            entity1_id=self.npc_id, entity1_type=RelationshipEntityType.GENERATED_NPC, # Corrected
            entity2_id=self.player_id, entity2_type=RelationshipEntityType.PLAYER,
            relationship_type="secret_generic_hidden_trait", value=50, guild_id=self.guild_id
        )
        self.mock_crud_relationship_get_relationships.return_value = [mock_hidden_relationship]

        def mock_load_entity(db_session_arg, entity_type_str, entity_id_arg, guild_id_call_arg): # Renamed
            if entity_type_str == RelationshipEntityType.PLAYER.value and entity_id_arg == self.player_id: return self.mock_player
            if entity_type_str == RelationshipEntityType.GENERATED_NPC.value and entity_id_arg == self.npc_id: return self.mock_npc
            return None
        self.mock_get_entity_by_id_and_type_str.side_effect = mock_load_entity

        result_no_rule = await resolve_check(
            db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type,
            actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER,
            target_entity_id=self.npc_id, target_entity_type=RelationshipEntityType.GENERATED_NPC, # Corrected
            difficulty_dc=dc
        )
        # Expected: 11 (roll) + 2 (stealth_mod) = 13. Fails. No hidden rel mod.
        self.assertEqual(result_no_rule.total_modifier, 2)
        self.assertEqual(result_no_rule.final_value, 13)
        self.assertNotIn("hidden_relationship_effects_applied", result_no_rule.rule_config_snapshot)

        # Case 2: Rule exists but is disabled
        def side_effect_disabled_rule(db, guild_id, key, default=None):
            rules = {
                "checks:stealth:dice_notation": "1d20",
                "hidden_relationship_effects:checks:secret_generic_hidden_trait": {
                    "enabled": False, "roll_modifier_formula": "value // 10"
                }
            }
            return rules.get(key, default)
        self.mock_get_rule.side_effect = side_effect_disabled_rule

        result_disabled_rule = await resolve_check(
            db=self.mock_db_session, guild_id=self.guild_id, check_type=check_type,
            actor_entity_id=self.player_id, actor_entity_type=RelationshipEntityType.PLAYER,
            target_entity_id=self.npc_id, target_entity_type=RelationshipEntityType.GENERATED_NPC, # Corrected
            difficulty_dc=dc
        )
        # mock_load_entity is already set from the previous part of this test, assuming it's still valid.
        self.assertEqual(result_disabled_rule.total_modifier, 2)
        self.assertEqual(result_disabled_rule.final_value, 13)
        self.assertNotIn("hidden_relationship_effects_applied", result_disabled_rule.rule_config_snapshot)


if __name__ == "__main__":
    unittest.main()
