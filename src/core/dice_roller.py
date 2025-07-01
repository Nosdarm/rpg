import random
import re
from typing import List, Tuple

def roll_dice(dice_string: str) -> Tuple[int, List[int]]:
    """
    Parses a dice string (e.g., "2d6", "1d20+5", "3d8-2") and returns the total sum
    and a list of individual dice results.

    Args:
        dice_string: The string representing the dice roll.
                     Format: NdX[+/-M]
                     N = number of dice (optional, defaults to 1)
                     X = number of sides per die
                     M = modifier (optional, defaults to 0)

    Returns:
        A tuple containing:
            - The total sum of the roll (including modifiers).
            - A list of individual dice results (before modifiers).

    Raises:
        ValueError: If the dice_string is invalid.
    """
    dice_string = dice_string.lower().replace(" ", "")

    # Regex to capture NdX+M or NdX-M or NdX
    # It captures:
    # 1. Number of dice (optional, defaults to 1 if not present before 'd')
    # 2. Number of sides
    # 3. Modifier sign (+ or -) (optional)
    # 4. Modifier value (optional)
    match = re.fullmatch(r"(\d*)d(\d+)([+-])?(\d*)?", dice_string)

    if not match:
        raise ValueError(f"Invalid dice string format: {dice_string}")

    num_dice_str, num_sides_str, mod_sign, mod_val_str = match.groups()

    num_dice = int(num_dice_str) if num_dice_str else 1
    num_sides = int(num_sides_str)

    if num_dice <= 0 or num_sides <= 0:
        raise ValueError("Number of dice and sides must be positive.")
    if num_dice > 1000: # Safety limit
        raise ValueError("Too many dice to roll (max 1000).")
    if num_sides > 1000: # Safety limit
        raise ValueError("Too many sides on a die (max 1000).")


    modifier = 0
    if mod_sign and mod_val_str:
        modifier = int(mod_val_str)
        if mod_sign == "-":
            modifier = -modifier
    elif mod_sign and not mod_val_str: # e.g. "1d6+"
        raise ValueError(f"Invalid modifier format: {dice_string}")


    rolls: List[int] = []
    current_sum = 0

    for _ in range(num_dice):
        roll = random.randint(1, num_sides)
        rolls.append(roll)
        current_sum += roll

    total_sum = current_sum + modifier

    return total_sum, rolls

if __name__ == '__main__':
    # Simple test cases
    test_cases = {
        "1d6": (None, 1, 6),
        "d6": (None, 1, 6), # Default to 1 die
        "2d10": (None, 2, 10),
        "1d20+5": (5, 1, 20),
        "3d8-2": (-2, 3, 8),
        "10d4+0": (0, 10, 4),
        "d20-1": (-1, 1, 20),
    }

    for k, (expected_mod, expected_num_dice, expected_sides) in test_cases.items():
        try:
            total, individual_rolls = roll_dice(k)
            print(f"Rolling {k}: Total = {total}, Rolls = {individual_rolls}")
            assert len(individual_rolls) == expected_num_dice
            for r in individual_rolls:
                assert 1 <= r <= expected_sides
            if expected_mod is not None:
                assert total == sum(individual_rolls) + expected_mod
            else:
                assert total == sum(individual_rolls)
        except ValueError as e:
            print(f"Error rolling {k}: {e}")

    invalid_cases = ["1d", "d", "2d6+", "1d20-", "abc", "1d6+abc", "0d6", "1d0", "1001d6", "1d1001"]
    for k_invalid in invalid_cases:
        try:
            roll_dice(k_invalid)
            print(f"Error: {k_invalid} should have failed but didn't.")
        except ValueError as e:
            print(f"Correctly failed for {k_invalid}: {e}")
