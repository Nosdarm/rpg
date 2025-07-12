import logging
import asyncio
from typing import Optional, TYPE_CHECKING

from backend.models.story_log import StoryLog # Moved out of TYPE_CHECKING

if TYPE_CHECKING:
    pass # StoryLog is now imported globally, or could remain here for explicit type hinting if preferred

logger = logging.getLogger(__name__)

async def on_enter_location(
    guild_id: int,
    entity_id: int, # Player or Party ID
    entity_type: str, # "player" or "party"
    location_id: int
):
    """
    Handles events when an entity (player or party) enters a new location.
    Currently logs information and sends location description (conceptually).
    """
    from .database import get_db_session # For independent session if needed
    from .crud import location_crud, player_crud, party_crud
    from .localization_utils import get_localized_text
    from .rules import get_rule # For guild default language

    async with get_db_session() as session:
        location = await location_crud.get(session, id=location_id, guild_id=guild_id)
        if not location:
            logger.error(f"on_enter_location: Location {location_id} not found for guild {guild_id}.")
            return

        entity_name = f"{entity_type} {entity_id}"
        language_code = await get_rule(session, guild_id, "guild_main_language", default="en")
        if not isinstance(language_code, str): language_code = "en"


        if entity_type == "player":
            player = await player_crud.get(session, id=entity_id)
            if player:
                entity_name = player.name
                if player.selected_language: # Player's preference
                    language_code = player.selected_language
        elif entity_type == "party":
            party = await party_crud.get(session, id=entity_id)
            if party:
                entity_name = party.name
                if party.leader_player_id: # Use leader's language or guild default
                    leader = await player_crud.get(session, id=party.leader_player_id)
                    if leader and leader.selected_language:
                        language_code = leader.selected_language

        location_name_i18n = location.name_i18n if location.name_i18n else {}
        location_desc_i18n = location.descriptions_i18n if location.descriptions_i18n else {}

        loc_display_name = get_localized_text(location_name_i18n, language_code, location.static_id or f"Location {location.id}")
        loc_description = get_localized_text(location_desc_i18n, language_code, "No description available.")

        logger.info(
            f"[Game Event] Entity '{entity_name}' ({entity_type} {entity_id}) in guild {guild_id} "
            f"entered location '{loc_display_name}' (ID: {location_id})."
        )

        # Messaging is handled by the bot layer, which will format and send the report.
        # This core logic's job is to provide the necessary data.
        # We can log the intent to send a message.
        logger.info(f"Location description for {entity_type} {entity_id} (Guild: {guild_id}, Lang: {language_code}) prepared: {loc_display_name}")

        # 2. Trigger encounters (integration)
        from .conflict_simulation_system import check_for_conflict_on_location_entry
        # This function should be designed to be called here.
        # It will check location properties, rules, and entity states.
        # It might return a conflict object or initiate combat directly.
        await check_for_conflict_on_location_entry(
            session=session,
            guild_id=guild_id,
            entering_entity_id=entity_id,
            entering_entity_type=entity_type,
            location=location
        )
        logger.info(f"Conflict check executed in location {loc_display_name} (ID: {location_id}) for {entity_name}.")

        # 3. Trigger AI for dynamic details/events (integration)
        from .ai_orchestrator import trigger_dynamic_event_generation
        # This function will check rules to see if AI should generate a dynamic event.
        await trigger_dynamic_event_generation(
            session=session,
            guild_id=guild_id,
            context={
                "trigger_type": "location_entry",
                "entity_id": entity_id,
                "entity_type": entity_type,
                "location_id": location_id,
                "location_static_id": location.static_id
            }
        )
        logger.info(f"Dynamic AI event generation triggered for location {loc_display_name} (ID: {location_id}) for {entity_name}.")

        # 4. Call quest system for 'LOCATION_ENTERED' event
        # This requires the StoryLog entry for the movement to have been committed.
        # The movement action should log an event, get its ID, and pass it to on_enter_location,
        # or on_enter_location queries the latest movement log.
        # For now, we assume the StoryLog entry is available or the quest system can handle it.
        from .quest_system import handle_player_event_for_quest
        from backend.models.enums import EventType as GameEventType # Renamed to avoid conflict

        event_details_for_quest = {
            "event_subtype": "entered_location",
            "location_id": location_id,
            "location_static_id": location.static_id,
            "location_name_i18n": location_name_i18n # Pass full i18n name for context
        }
        # We need a StoryLog entry to link. Since on_enter_location is fire-and-forget,
        # it doesn't have the StoryLog object from the movement action directly.
        # A better design might be for the movement action to create a task for on_enter_location
        # and pass the created StoryLog object or its ID.
        # For now, we'll simulate by calling handle_player_event_for_quest without a specific StoryLog entry,
        # or the quest system needs to be robust to this.
        # Let's assume for now that Quest System might query recent logs or not strictly require it for all event types.

        # Create a placeholder StoryLog-like object for the quest system if it needs one.
        # This is a temporary workaround.
        from backend.models.story_log import StoryLog
        from datetime import datetime, timezone

        # The movement event should have already been logged by _update_entities_location
        # We need to find that log entry to pass its ID to handle_player_event_for_quest.
        # This is tricky because on_enter_location is fire-and-forget.
        # A more robust solution would be to pass the StoryLog object or ID from the caller.
        # For now, we'll log a TODO and proceed without a real StoryLog link for the quest system.
        logger.warning("TODO: on_enter_location needs a mechanism to get the StoryLog ID of the preceding movement event for robust quest integration.")

        # Simulate a minimal StoryLog-like structure for the quest system if it's essential
        # and the real one cannot be easily passed.
        # However, it's better if handle_player_event_for_quest can operate without a source_log_id
        # for certain event types or has a way to find it.
        # For now, let's call it, and the quest system will have to be robust.

        if entity_type == "player":
            log_entry = StoryLog(
                guild_id=guild_id,
                event_type=GameEventType.LOCATION_ENTERED,
                details_json=event_details_for_quest,
                location_id=location_id,
                entity_ids_json={"players": [entity_id]},
            )
            asyncio.create_task(handle_player_event_for_quest(
                session,
                log_entry
            ))
            logger.info(f"Quest system notified: Player {entity_id} entered location {location_id}.")
        elif entity_type == "party": # Assuming party is not None if entity_type is "party"
            party_obj = await party_crud.get(session, id=entity_id) # Re-fetch party to get member list if needed by quest system
            if party_obj:
                log_entry = StoryLog(
                    guild_id=guild_id,
                    event_type=GameEventType.LOCATION_ENTERED,
                    details_json=event_details_for_quest,
                    location_id=location_id,
                    entity_ids_json={"parties": [entity_id]},
                )
                asyncio.create_task(handle_player_event_for_quest(
                    session,
                    log_entry
                ))
                logger.info(f"Quest system notified: Party {entity_id} entered location {location_id}.")
            else:
                logger.error(f"on_enter_location: Party {entity_id} not found when trying to notify quest system.")
        else:
            logger.warning(f"Unknown entity_type '{entity_type}' in on_enter_location for quest system notification.")


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
