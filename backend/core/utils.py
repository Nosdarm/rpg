import logging
from typing import Optional, Any, TYPE_CHECKING
from sqlalchemy.ext.asyncio import AsyncSession
from . import crud
from ..models.story_log import StoryLog

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

async def get_entity_by_id_and_type_str(
    session: AsyncSession,
    entity_type_str: str,
    entity_id: int,
    guild_id: Optional[int] = None,
) -> Optional[Any]:
    """
    Fetches an entity from the database by its ID and string type identifier.
    """
    crud_map = {
        "player": crud.player_crud,
        "generated_npc": crud.npc_crud,
        "global_npc": crud.global_npc_crud,
        "mobile_group": crud.mobile_group_crud,
        "location": crud.location_crud,
        "item": crud.item_crud,
        "party": crud.party_crud,
        "faction": crud.faction_crud,
        # Add other type strings and their corresponding CRUD objects here
    }
    crud_instance = crud_map.get(entity_type_str.lower())
    if not crud_instance:
        logger.warning(f"No CRUD instance found for entity type '{entity_type_str}'")
        return None

    try:
        if guild_id is not None:
            # Assumes a method like get_by_id_and_guild exists on the CRUD base
            entity = await crud_instance.get_by_id_and_guild(session, id=entity_id, guild_id=guild_id)
        else:
            entity = await crud_instance.get(session, id=entity_id)
        return entity
    except Exception as e:
        logger.error(f"Error fetching entity type '{entity_type_str}' with ID {entity_id}: {e}", exc_info=True)
        return None

async def log_event(
    session: AsyncSession,
    guild_id: int,
    event_type: str, # This should be a string key of EventType enum, e.g., "PLAYER_ACTION"
    details_json: dict,
    player_id: Optional[int] = None, # Retained for placeholder info, not directly on StoryLog model
    party_id: Optional[int] = None,  # Retained for placeholder info, not directly on StoryLog model
    location_id: Optional[int] = None,
    entity_ids_json: Optional[dict] = None,
    dry_run: bool = False,
) -> Optional["StoryLog"]: # Modified to return StoryLog or None
    """
    Logs a game event to the StoryLog and returns the created entry.
    If dry_run is True, it simulates logging and returns a mock-like StoryLog without DB interaction.
    The event_type should match a key in the EventType enum.
    The caller is responsible for session management (commit/rollback).
    """
    logger.info(
        f"Attempting to log event. Guild: {guild_id}, EventType: {event_type}, Player: {player_id}, Party: {party_id}, Location: {location_id}"
    )

    from backend.models.enums import EventType

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

    if dry_run:
        logger.info(f"Dry run: StoryLog event '{event_type}' for guild {guild_id} would be created with details: {details_json}")
        # Simulate a StoryLog object without saving to DB.
        # Some fields like id, created_at, updated_at won't be populated as they are DB-generated.
        # This mock StoryLog is primarily for functions that might expect a StoryLog object
        # in a dry_run scenario, though its utility might be limited without DB state.
        mock_log_entry = StoryLog(
            id=0, # Placeholder ID for dry run
            guild_id=guild_id,
            event_type=event_type_enum_member,
            details_json=details_json,
            location_id=location_id,
            entity_ids_json=final_entity_ids if final_entity_ids else None
        )
        # Timestamps could be faked if necessary:
        # from datetime import datetime, timezone
        # now = datetime.now(timezone.utc)
        # mock_log_entry.created_at = now
        # mock_log_entry.updated_at = now
        return mock_log_entry

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
