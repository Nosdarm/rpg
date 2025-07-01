import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class ActionEntity(BaseModel):
    """Represents a single recognized entity in player input."""
    type: str  # E.g., "direction", "target_npc", "item_name", "location_name"
    value: str  # The raw string value of the entity
    # display_name: Optional[str] = None # Optional: for i18n or resolved name
    # resolved_id: Optional[Any] = None # Optional: if the entity was resolved to a DB ID

class ParsedAction(BaseModel):
    """
    Represents a player's parsed action, ready to be stored or processed.
    """
    raw_text: str
    intent: str = Field(default="unknown_intent")
    entities: List[ActionEntity] = Field(default_factory=list)

    # Optional fields for more advanced NLU or processing
    parser_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    # target_entity_id: Optional[int] = None # If a primary target is resolved
    # target_entity_type: Optional[str] = None # E.g., "npc", "item", "location_feature"

    # Contextual information
    guild_id: int # Should always be present
    player_id: int # Discord ID of the player

    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now)

    # For storage in Player.collected_actions_json, we'll likely convert this to dict.
    # model_config = {
    #     "json_encoders": {
    #         datetime.datetime: lambda v: v.isoformat(),
    #     }
    # }


# Example Usage (not part of the file, just for thought):
# action_entities_example = [
#     ActionEntity(type="direction", value="north"),
#     ActionEntity(type="item_name", value="rusty sword")
# ]
# parsed_action_example = ParsedAction(
#     raw_text="go north and get the rusty sword",
#     intent="multi_action", # Or could be broken down further by NLU
#     entities=action_entities_example,
#     parser_confidence=0.85,
#     guild_id=123456789012345678,
#     player_id=987654321098765432
# )
# action_dict = parsed_action_example.model_dump(mode="json")
# print(action_dict)

# Ensure this new model is findable, update src/models/__init__.py
# (This will be done in a separate step if needed by other modules, or as part of this step's completion)
import logging
logger = logging.getLogger(__name__)
logger.info("Action models (ParsedAction, ActionEntity) defined.")
