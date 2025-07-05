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
) -> Optional["StoryLog"]: # Modified to return StoryLog or None
    """
    Logs a game event to the StoryLog and returns the created entry.
    The event_type should match a key in the EventType enum.
    The caller is responsible for session management (commit/rollback).
    """
    logger.info(
        f"Attempting to log event. Guild: {guild_id}, EventType: {event_type}, Player: {player_id}, Party: {party_id}, Location: {location_id}"
    )

    from src.models.story_log import StoryLog
    from src.models.enums import EventType

    try:
        event_type_enum_member = EventType[event_type.upper()]
    except KeyError:
        logger.error(f"Invalid event_type string: {event_type}. Cannot log event for guild {guild_id}.")
        return None

    final_entity_ids: dict = entity_ids_json.copy() if entity_ids_json is not None else {}
    if player_id is not None:
        final_entity_ids.setdefault("players", []).append(player_id)
        final_entity_ids["players"] = list(set(final_entity_ids["players"]))
    if party_id is not None:
        final_entity_ids.setdefault("parties", []).append(party_id)
        final_entity_ids["parties"] = list(set(final_entity_ids["parties"]))

    log_entry = StoryLog(
        guild_id=guild_id,
        event_type=event_type_enum_member,
        details_json=details_json,
        location_id=location_id,
        entity_ids_json=final_entity_ids if final_entity_ids else None,
    )
    session.add(log_entry)
    try:
        await session.flush() # Flush to get the ID and other server-set defaults like timestamp
        await session.refresh(log_entry) # Refresh to load all attributes
        logger.debug(f"StoryLog entry (ID: {log_entry.id}) added and flushed for guild {guild_id}, event: {event_type}")
        return log_entry
    except Exception as e:
        logger.error(f"Error flushing/refreshing StoryLog entry for guild {guild_id}, event {event_type}: {e}", exc_info=True)
        # Depending on policy, might want to await session.rollback() here or let caller handle.
        # For now, just return None as the entry wasn't successfully prepared.
        return None
