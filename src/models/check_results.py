from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class ModifierDetail(BaseModel):
    source: str = Field(..., description="Source of the modifier (e.g., 'base_stat:strength', 'skill:perception', 'item:magic_amulet', 'status:blessed')")
    value: int = Field(..., description="Value of this specific modifier component")
    description: Optional[str] = Field(None, description="Optional description of the modifier")

class CheckOutcome(BaseModel):
    status: str = Field(..., description="Result of the check (e.g., 'critical_failure', 'failure', 'success', 'critical_success')")
    description: Optional[str] = Field(None, description="Narrative description of the outcome, if any")

class CheckResult(BaseModel):
    guild_id: int = Field(..., description="Guild ID for which the check was resolved")
    check_type: str = Field(..., description="Type of check being performed (e.g., 'strength_check', 'attack_roll')")

    entity_doing_check_id: int
    entity_doing_check_type: str # Should ideally be an Enum or a constrained string
    target_entity_id: Optional[int] = None
    target_entity_type: Optional[str] = None # Should ideally be an Enum or a constrained string

    difficulty_class: Optional[int] = Field(None, description="The DC of the check, if applicable")

    dice_notation: str = Field(..., description="The dice rolled (e.g., '1d20', '2d6')")
    raw_rolls: List[int] = Field(..., description="List of individual dice results before any modifiers or interpretation")
    roll_used: int = Field(..., description="The specific dice roll value used for calculation after considering advantage/disadvantage, but before modifiers.")

    total_modifier: int = Field(..., description="The sum of all modifiers applied to the roll_used.")
    modifier_details: List[ModifierDetail] = Field(default_factory=list, description="Detailed breakdown of all modifiers")

    final_value: int = Field(..., description="The final result of the check (roll_used + total_modifier)")

    outcome: CheckOutcome = Field(..., description="The determined outcome of the check")

    rule_config_snapshot: Optional[Dict[str, Any]] = Field(None, description="Snapshot of relevant RuleConfig rules used for this check")
    check_context_provided: Optional[Dict[str, Any]] = Field(None, description="The check_context that was passed into resolve_check")

    class Config:
        from_attributes = True # If these models might be created from ORM objects
        # For Pydantic v2, forward refs are generally handled well, but if issues arise:
        # model_config = {'rebuild_fields': True} # This is not a standard Pydantic V2 config option.
                                                # Forward refs are usually handled by string literals + model_rebuild()
                                                # or by ensuring types are defined/imported before use.
                                                # Since these are self-contained, it should be fine.

# If ModifierDetail or CheckOutcome were complex and defined elsewhere,
# CheckResult.model_rebuild() might be needed here.
# But since they are simple and defined above, it's not necessary.
