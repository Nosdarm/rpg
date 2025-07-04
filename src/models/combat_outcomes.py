from typing import Optional, List, Dict, Any, TYPE_CHECKING # Added TYPE_CHECKING
from pydantic import BaseModel

from .check_results import CheckResult # Old location, already correct

class CombatActionResult(BaseModel):
    """
    Represents the detailed result of a combat action.
    """
    success: bool
    action_type: str  # e.g., "attack", "cast_spell", "use_item", "defend", "flee"

    actor_id: int
    actor_type: str  # "player", "npc"

    target_id: Optional[int] = None
    target_type: Optional[str] = None # "player", "npc"

    damage_dealt: Optional[int] = None
    healing_done: Optional[int] = None

    # Example: [{"status_static_id": "burning", "duration_turns": 3, "target_id": 123, "applied_by_actor_id": 456}]
    status_effects_applied: Optional[List[Dict[str, Any]]] = None
    status_effects_removed: Optional[List[Dict[str, Any]]] = None # For future use

    check_result: Optional['CheckResult'] = None # Used string literal

    description_i18n: Optional[Dict[str, str]] = None # Human-readable summary of the action outcome

    # Example: {"resource": "mana", "amount": 10, "actor_id": 123}
    costs_paid: Optional[List[Dict[str, Any]]] = None

    # Additional details specific to the action that might be useful for logging or complex effects
    # E.g., for an attack: {"weapon_used_id": 1, "is_critical_hit": True, "is_miss": False}
    # E.g., for a spell: {"spell_id": 5, "aoe_targets_hit": [101, 102]}
    additional_details: Optional[Dict[str, Any]] = None

    # To ensure model can be used in ORM context if needed (though primarily for API responses)
    class Config:
        from_attributes = True

# CombatActionResult.model_rebuild() # May not be needed with direct import of CheckResult

# Example usage (for testing or understanding):
# if __name__ == "__main__":
#     sample_action_result = CombatActionResult(
#         success=True,
#         action_type="attack",
#         actor_id=1,
#         actor_type="player",
#         target_id=2,
#         target_type="npc",
#         damage_dealt=15,
#         check_result={"roll": 18, "dc": 10, "success": True, "critical_success": False, "critical_failure": False, "total_roll_value": 20},
#         description_i18n={"en": "Player attacks NPC for 15 damage!", "ru": "Игрок атакует НИП на 15 урона!"},
#         additional_details={"weapon_used_id": 101, "is_critical_hit": False}
#     )
#     print(sample_action_result.model_dump_json(indent=2))

#     failed_action_result = CombatActionResult(
#         success=False,
#         action_type="cast_spell",
#         actor_id=5,
#         actor_type="npc",
#         target_id=1,
#         target_type="player",
#         description_i18n={"en": "NPC fails to cast the spell."},
#         costs_paid=[{"resource": "mana", "amount": 20, "actor_id": 5}],
#         additional_details={"spell_id": 7, "reason_for_failure": "not_enough_mana_after_check"} # Example
#     )
#     print(failed_action_result.model_dump_json(indent=2))
