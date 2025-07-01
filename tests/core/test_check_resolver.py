import asyncio
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

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

        # Default mock behaviors
        self.mock_get_rule.side_effect = lambda db, guild_id, key: DEFAULT_RULE_VALUES.get(key)


    async def asyncTearDown(self):
        self.patch_get_rule.stop()
        self.patch_roll_dice.stop()
        self.patch_get_entity_attribute.stop()

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
            entity_doing_check_id=self.player_id,
            entity_doing_check_type=ENTITY_TYPE_PLAYER,
            difficulty_dc=dc
        )

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
            entity_doing_check_id=self.npc_id,
            entity_doing_check_type=ENTITY_TYPE_NPC,
            difficulty_dc=dc
        )
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
            entity_doing_check_id=self.player_id, entity_doing_check_type=ENTITY_TYPE_PLAYER,
            difficulty_dc=dc
        )
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
            entity_doing_check_id=self.player_id, entity_doing_check_type=ENTITY_TYPE_PLAYER,
            difficulty_dc=dc
        )
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
            entity_doing_check_id=self.player_id, entity_doing_check_type=ENTITY_TYPE_PLAYER,
            difficulty_dc=dc, check_context=context
        )
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
            entity_doing_check_id=self.player_id, entity_doing_check_type=ENTITY_TYPE_PLAYER,
            difficulty_dc=dc, check_context=context
        )
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
            entity_doing_check_id=self.player_id, entity_doing_check_type=ENTITY_TYPE_PLAYER
        )
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
                entity_doing_check_id=self.player_id, entity_doing_check_type=ENTITY_TYPE_PLAYER,
                difficulty_dc=10
            )

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
            entity_doing_check_id=self.player_id, entity_doing_check_type=ENTITY_TYPE_PLAYER,
            difficulty_dc=dc
        )

        self.assertEqual(result.outcome.status, "success") # 12 (roll) + 0 (mod) >= 10
        self.assertEqual(result.total_modifier, 0)
        self.assertEqual(result.final_value, 12)
        # Check that no modifier detail was added for the missing base_stat, or it was added with value 0
        self.assertFalse(any(md.source == "base_stat:non_existent_stat" and md.value != 0 for md in result.modifier_details))


if __name__ == "__main__":
    unittest.main()
