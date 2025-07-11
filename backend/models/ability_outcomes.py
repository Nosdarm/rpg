from typing import Any, List, Optional, Dict
from pydantic import BaseModel

class AppliedStatusDetail(BaseModel):
    """Details of a status effect applied by an ability."""
    status_static_id: str
    target_entity_id: int
    target_entity_type: str
    duration: Optional[int] = None

class DamageDetail(BaseModel):
    """Details of damage dealt by an ability."""
    target_entity_id: int
    target_entity_type: str
    amount: int
    damage_type: Optional[str] = "physical" # Default or from ability

class HealingDetail(BaseModel):
    """Details of healing done by an ability."""
    target_entity_id: int
    target_entity_type: str
    amount: int

class CasterUpdateDetail(BaseModel):
    """Details of updates to the caster's state."""
    resource_type: str # e.g., "mana", "stamina", "gold"
    change: int # Positive for gain, negative for cost

class AbilityOutcomeDetails(BaseModel):
    """Structured result of activating an ability."""
    success: bool
    message: str  # User-facing feedback message
    applied_statuses: List[AppliedStatusDetail] = []
    damage_dealt: List[DamageDetail] = []
    healing_done: List[HealingDetail] = []
    caster_updates: List[CasterUpdateDetail] = []
    raw_ability_properties: Optional[Dict[str, Any]] = None # For logging/debugging
    log_event_details: Optional[Dict[str, Any]] = None # For structured logging
