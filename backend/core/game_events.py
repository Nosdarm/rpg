import logging
import asyncio
from typing import Optional, TYPE_CHECKING
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.story_log import StoryLog # Moved out of TYPE_CHECKING
from backend.models.location import Location

if TYPE_CHECKING:
    pass # StoryLog is now imported globally, or could remain here for explicit type hinting if preferred

logger = logging.getLogger(__name__)

async def check_for_conflict_on_location_entry(
    session: AsyncSession,
    guild_id: int,
    entering_entity_id: int,
    entering_entity_type: str, # "player" or "party"
    location: "Location" # Forward ref from models
) -> None:
    """
    Checks for potential conflicts when an entity enters a location.
    This could be based on factions, hostile NPCs, or location state.
    """
    from .crud import npc_crud, player_crud, party_crud, relationship_crud
    from .combat_cycle_manager import start_combat
    from ..models import Relationship

    logger.info(f"Checking for conflicts upon {entering_entity_type} ID {entering_entity_id} entering location {location.id} (Guild: {guild_id})")

    # 1. Get all entities present in the location
    # For now, we only check for hostile NPCs.
    # In the future, this could include other players, parties, etc.
    npcs_in_location = await npc_crud.get_multi_by_location(session, guild_id=guild_id, location_id=location.id)

    # 2. Determine who the entering entities are
    entering_players: List[Player] = []
    if entering_entity_type == "player":
        player = await player_crud.get(session, id=entering_entity_id)
        if player:
            entering_players.append(player)
    elif entering_entity_type == "party":
        party = await party_crud.get(session, id=entering_entity_id)
        if party and party.player_ids_json:
            entering_players = await player_crud.get_multi_by_ids(session, ids=party.player_ids_json)

    if not entering_players:
        logger.warning(f"Could not resolve entering players for {entering_entity_type} ID {entering_entity_id}. Aborting conflict check.")
        return

    # 3. Check for hostile relationships
    # This is a simplified check. A more complex system might involve perception checks.
    hostile_npcs = []
    for npc in npcs_in_location:
        is_hostile = False
        # Check NPC's faction relationship with each player's faction(s)
        # Check personal NPC-to-player relationship
        # For simplicity, we'll assume a basic "hostile" property on the NPC for now.
        npc_properties = npc.properties_json or {}
        if npc_properties.get("disposition") == "hostile_on_sight":
            is_hostile = True

        if is_hostile:
            hostile_npcs.append(npc)

    # 4. If hostile NPCs are found, initiate combat
    if hostile_npcs:
        logger.info(f"Conflict detected! {len(entering_players)} player(s) encountered {len(hostile_npcs)} hostile NPCs in location {location.id}.")

        # The combat system needs a list of all participants
        # The combat system should be able to handle Player and GeneratedNpc objects
        combat_participants = entering_players + hostile_npcs

        # The combat system needs to know who initiated, if anyone. Can be None for ambient conflict.
        # It also needs the location_id to create the CombatEncounter.
        await start_combat(
            session=session,
            guild_id=guild_id,
            location_id=location.id,
            initiating_player_id=entering_players[0].id, # Designate the first player as initiator for now
            participant_entities=combat_participants
        )
        logger.info(f"Combat initiated in location {location.id} for guild {guild_id}.")

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

