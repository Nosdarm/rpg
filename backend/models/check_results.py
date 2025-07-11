from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field # Removed: model_validator

class ModifierDetail(BaseModel):
    """Details of a single modifier applied during a check."""
    source: str  # e.g., "base_stat:strength", "item:magic_sword", "status:blessed"
    value: int
    description: Optional[str] = None

class CheckOutcome(BaseModel):
    """The outcome of a check."""
    status: str  # e.g., "success", "failure", "critical_success", "critical_failure", "value_determined"
    description: Optional[str] = None # Human-readable description of the outcome.

class CheckResult(BaseModel):
    """
    Represents the detailed result of any game check (skill check, attack roll, saving throw).
    """
    guild_id: int
    check_type: str  # e.g., "lockpicking", "attack_melee", "spell_save_dexterity"

    entity_doing_check_id: int
    entity_doing_check_type: str # "PLAYER", "NPC", "OBJECT" etc.

    target_entity_id: Optional[int] = None
    target_entity_type: Optional[str] = None

    difficulty_class: Optional[int] = Field(default=None, alias="dc") # Target number for success

    dice_notation: str  # e.g., "1d20", "2d6+3"
    raw_rolls: List[int] # The actual numbers rolled on the dice, e.g. [15] for 1d20, or [3, 5] for 2d6
    roll_used: int # The specific roll value used for comparison after considering advantage/disadvantage, but before modifiers for d20 checks. For summed rolls (like 2d6 damage), this is the sum of dice.

    total_modifier: int
    modifier_details: List[ModifierDetail] = Field(default_factory=list)

    final_value: int # roll_used + total_modifier

    outcome: CheckOutcome

    # Snapshot of rules or context that influenced this check for transparency/logging
    rule_config_snapshot: Optional[Dict[str, Any]] = None
    check_context_provided: Optional[Dict[str, Any]] = None # Context given to resolve_check

    model_config = {
        "from_attributes": True, # Allows Pydantic to work with ORM models if needed
        "populate_by_name": True, # Allows using 'dc' as an alias for difficulty_class
    }

# Example usage (for testing or understanding):
if __name__ == "__main__":
    sample_check_result = CheckResult(
        guild_id=1,
        check_type="attack_melee",
        entity_doing_check_id=10,
        entity_doing_check_type="PLAYER",
        target_entity_id=20,
        target_entity_type="NPC",
        dc=15, # Using alias
        dice_notation="1d20",
        raw_rolls=[18],
        roll_used=18,
        total_modifier=5,
        modifier_details=[
            ModifierDetail(source="base_stat:strength", value=3, description="Strength modifier"),
            ModifierDetail(source="item:magic_sword", value=2, description="Magic Sword bonus")
        ],
        final_value=23,
        outcome=CheckOutcome(status="critical_success", description="Critical hit! Player smashes the NPC.")
    )
    print(sample_check_result.model_dump_json(indent=2, by_alias=True))

    sample_fail_check = CheckResult(
        guild_id=1,
        check_type="spell_save_dexterity",
        entity_doing_check_id=20, # NPC is making player save
        entity_doing_check_type="NPC", # The spell forces player to save
        target_entity_id=10, # Player is the target of the save
        target_entity_type="PLAYER",
        dc=13,
        dice_notation="1d20",
        raw_rolls=[5],
        roll_used=5,
        total_modifier=1, # Player's dex save bonus
        modifier_details=[ModifierDetail(source="base_stat:dexterity_save", value=1)],
        final_value=6,
        outcome=CheckOutcome(status="failure", description="Player fails the dexterity save.")
    )
    print(sample_fail_check.model_dump_json(indent=2, by_alias=True))
