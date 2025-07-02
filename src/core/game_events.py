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

from sqlalchemy.ext.asyncio import AsyncSession

# logger = logging.getLogger(__name__) # Logger already initialized at the top of the file

# The second definition of on_enter_location was here and has been removed.

async def log_event(
    session: AsyncSession,
    guild_id: int,
    event_type: str, # This should be a string key of EventType enum, e.g., "PLAYER_ACTION"
    details_json: dict,
    player_id: Optional[int] = None, # Retained for placeholder info, not directly on StoryLog model
    party_id: Optional[int] = None,  # Retained for placeholder info, not directly on StoryLog model
    location_id: Optional[int] = None,
    entity_ids_json: Optional[dict] = None,
):
    """
    Logs a game event to the StoryLog.
    The event_type should match a key in the EventType enum.
    The caller is responsible for session management (commit/rollback).
    """
    # Log basic info for now, even if it was a placeholder before.
    # The detailed logging now happens via the StoryLog entry itself.
    logger.info(
        f"Attempting to log event. Guild: {guild_id}, EventType: {event_type}, Player: {player_id}, Party: {party_id}, Location: {location_id}"
    )

    from src.models.story_log import StoryLog
    from src.models.enums import EventType

    # Validate event_type against EventType enum
    try:
        # If event_type is string, try to convert to Enum member.
        event_type_enum_member = EventType[event_type.upper()]
    except KeyError:
        logger.error(f"Invalid event_type string: {event_type}. Cannot log event for guild {guild_id}.")
        return

    # Prepare entity_ids_json
    final_entity_ids: dict = entity_ids_json.copy() if entity_ids_json is not None else {}

    if player_id is not None:
        final_entity_ids.setdefault("players", []).append(player_id)
        # Ensure uniqueness if player_id might be duplicated by caller
        final_entity_ids["players"] = list(set(final_entity_ids["players"]))

    if party_id is not None:
        final_entity_ids.setdefault("parties", []).append(party_id)
        # Ensure uniqueness
        final_entity_ids["parties"] = list(set(final_entity_ids["parties"]))

    log_entry = StoryLog(
        guild_id=guild_id,
        event_type=event_type_enum_member,
        details_json=details_json,
        location_id=location_id,
        entity_ids_json=final_entity_ids if final_entity_ids else None, # Store None if empty after processing
        # timestamp is server_default
    )
    session.add(log_entry)
    logger.debug(f"StoryLog entry added to session for guild {guild_id}, event: {event_type}")
    # The caller is responsible for committing the session.
