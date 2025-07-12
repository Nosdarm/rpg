import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.story_log import StoryLog
from backend.models.enums import EventType

logger = logging.getLogger(__name__)

async def log_event(
    session: AsyncSession,
    guild_id: int,
    event_type: str,
    details_json: Dict[str, Any],
    entity_ids_json: Optional[Dict[str, Any]] = None,
    location_id: Optional[int] = None,
) -> StoryLog:
    """
    Logs a game event to the story_logs table.
    """
    # Ensure event_type is a string from the Enum
    if isinstance(event_type, EventType):
        event_type_str = event_type.value
    else:
        event_type_str = event_type

    log_entry = StoryLog(
        guild_id=guild_id,
        event_type=event_type_str,
        details_json=details_json,
        entity_ids_json=entity_ids_json,
        location_id=location_id,
    )
    session.add(log_entry)
    await session.flush()
    await session.refresh(log_entry)
    logger.debug(f"Logged event: {log_entry.id} - {log_entry.event_type}")
    return log_entry
