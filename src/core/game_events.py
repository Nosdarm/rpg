import logging
from typing import Optional

logger = logging.getLogger(__name__)

async def on_enter_location(
    guild_id: int,
    entity_id: int, # Player or Party ID
    entity_type: str, # "player" or "party"
    location_id: int
):
    """
    Placeholder function called when an entity enters a new location.
    This is related to Task 14.
    """
    logger.info(
        f"[Game Event Placeholder] Entity {entity_type} {entity_id} in guild {guild_id} "
        f"entered location {location_id}."
    )

async def log_event(
    session, # SQLAlchemy AsyncSession
    guild_id: int,
    event_type: str,
    details_json: dict,
    player_id: Optional[int] = None,
    party_id: Optional[int] = None,
    location_id: Optional[int] = None,
    entity_ids_json: Optional[dict] = None,
):
    """
    Placeholder for logging game events.
    This is related to Task 19 (StoryLog).
    """
    logger.info(
        f"[Event Log Placeholder] Guild {guild_id}, Event: {event_type}, "
        f"Player: {player_id}, Party: {party_id}, Location: {location_id}, "
        f"Details: {details_json}, Entities: {entity_ids_json}"
    )
    # In a real implementation, this would write to the StoryLog table.
    # For now, it does nothing with the session.
    pass
