import sys
import os
import unittest
import random
from typing import List, Tuple

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Adjust the import path based on your project structure
# If src is a top-level package and your tests are run from the project root:
from backend.core.dice_roller import roll_dice

class TestDiceRoller(unittest.TestCase):

    def setUp(self):
        # Seed random for predictable test outcomes if necessary,
        # but for dice rolling, we often want to test the range.
        # For specific sum tests with modifiers, seeding might be useful
        # if we mock random.randint. Here, we check properties.
        pass

    def _assert_roll_properties(self,
                                dice_string: str,
                                expected_num_dice: int,
                                expected_sides: int,
                                expected_modifier: int = 0):
        """Helper to assert properties of a dice roll."""
        total, individual_rolls = roll_dice(dice_string)

        self.assertEqual(len(individual_rolls), expected_num_dice)
        self.assertEqual(sum(individual_rolls) + expected_modifier, total)

        for roll in individual_rolls:
            self.assertTrue(1 <= roll <= expected_sides,
                            f"Roll {roll} out of range for 1d{expected_sides}")

    def test_simple_rolls(self):
        self._assert_roll_properties("1d6", 1, 6)
        self._assert_roll_properties("d6", 1, 6) # Default to 1 die
        self._assert_roll_properties("1d20", 1, 20)
        self._assert_roll_properties("3d8", 3, 8)

    def test_rolls_with_positive_modifier(self):
        self._assert_roll_properties("1d20+5", 1, 20, 5)
        self._assert_roll_properties("2d6+3", 2, 6, 3)
        self._assert_roll_properties("d10+1", 1, 10, 1)

    def test_rolls_with_negative_modifier(self):
        self._assert_roll_properties("1d20-5", 1, 20, -5)
        self._assert_roll_properties("3d4-1", 3, 4, -1)
        self._assert_roll_properties("d12-10", 1, 12, -10)

    def test_rolls_with_zero_modifier(self):
        self._assert_roll_properties("1d6+0", 1, 6, 0)
        self._assert_roll_properties("2d8-0", 2, 8, 0)

    def test_multiple_dice_sum_and_count(self):
        # Specific seed to test sums if needed, or mock randint
        # For now, general properties are tested by _assert_roll_properties
        random.seed(12345) # Example seed
        total, rolls = roll_dice("5d6")
        self.assertEqual(len(rolls), 5)
        expected_sum = sum(rolls)
        self.assertEqual(total, expected_sum)
        for roll in rolls:
            self.assertTrue(1 <= roll <= 6)

        total_mod, rolls_mod = roll_dice("5d6+5")
        self.assertEqual(len(rolls_mod), 5)
        expected_sum_mod = sum(rolls_mod) + 5
        self.assertEqual(total_mod, expected_sum_mod)

    def test_whitespace_insensitivity(self):
        self._assert_roll_properties(" 1d6 ", 1, 6)
        self._assert_roll_properties("2 d 10 + 3", 2, 10, 3)
        self._assert_roll_properties(" 3d4 - 1 ", 3, 4, -1)

    def test_invalid_formats(self):
        invalid_strings = [
            "d", "1d", "2d+", "3d-", "abc", "1d6+abc", "1d6x",
            "1.5d6", "1d6.5", "1d6+1.5",
            "", " ", "+5", "-2", "d6d6"
        ]
        for s in invalid_strings:
            with self.assertRaises(ValueError, msg=f"Expected ValueError for '{s}'"):
                roll_dice(s)

    def test_invalid_dice_numbers(self):
        invalid_strings = [
            "0d6", "-1d6", "1d0", "1d-2",
            "1001d6", # Exceeds safety limit
            "1d1001", # Exceeds safety limit
        ]
        for s in invalid_strings:
            with self.assertRaises(ValueError, msg=f"Expected ValueError for '{s}'"):
                roll_dice(s)

if __name__ == "__main__":
    unittest.main()
