import logging
import json
import asyncio
from typing import Tuple, Optional, Dict, Any # Added Dict, Any here

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func # Added for func.lower

from .database import transactional, get_db_session
from .crud import player_crud, party_crud, location_crud
from ..models import Player, Party, Location
from .game_events import on_enter_location, log_event
from .rules import get_rule # Now used for guild_main_language as well

logger = logging.getLogger(__name__)

class MovementError(Exception):
    """Custom exception for movement errors."""
    pass

@transactional
async def _update_entities_location(
    # session: AsyncSession, # Session is injected by @transactional as a keyword argument
    guild_id: int,
    player: Player,
    target_location: Location,
    party: Optional[Party] = None,
    *, # Make session a keyword-only argument
    session: AsyncSession
) -> None:
    """
    Helper function to update player and optionally party location in DB
    and log the event. Runs within a transaction. Session is injected.
    """
    player_original_location_id = player.current_location_id
    player.current_location_id = target_location.id
    session.add(player)
    logger.info(f"Player {player.id} (Guild: {guild_id}) moving from {player_original_location_id} to {target_location.id}")

    if party:
        party_original_location_id = party.current_location_id
        party.current_location_id = target_location.id
        session.add(party)
        logger.info(f"Party {party.id} (Guild: {guild_id}) moving from {party_original_location_id} to {target_location.id}")

        # Log party movement
        await log_event(
            session=session,
            guild_id=guild_id,
            event_type="party_move",
            details_json={
                "party_id": party.id,
                "player_id_initiator": player.id,
                "from_location_id": party_original_location_id,
                "to_location_id": target_location.id,
                "to_location_static_id": target_location.static_id,
            },
            party_id=party.id,
            player_id=player.id, # Initiator
            location_id=target_location.id
        )
    else:
        # Log player solo movement
        await log_event(
            session=session,
            guild_id=guild_id,
            event_type="player_move",
            details_json={
                "player_id": player.id,
                "from_location_id": player_original_location_id,
                "to_location_id": target_location.id,
                "to_location_static_id": target_location.static_id,
            },
            player_id=player.id,
            location_id=target_location.id
        )


async def handle_move_action(
    guild_id: int,
    player_discord_id: int, # Changed from player_id to player_discord_id for clarity
    target_location_static_id: str,
) -> Tuple[bool, str]:
    """
    Handles the logic for a player moving to a new location.

    Args:
        guild_id: The ID of the guild.
        player_discord_id: The Discord ID of the player initiating the move.
        target_location_static_id: The static_id of the target location.

    Returns:
        A tuple (success: bool, message: str).
    """
    async with get_db_session() as session:
        try:
            player = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=player_discord_id)
            if not player:
                raise MovementError(f"Player with Discord ID {player_discord_id} not found in guild {guild_id}.")
            if player.current_location_id is None:
                # This case should ideally be handled by ensuring players always have a location.
                # For now, let's try to get the 'start' location or similar default if defined.
                # Or, this could be an error state.
                # For simplicity in this step, we'll assume player.current_location_id is always set after /start.
                raise MovementError(f"Player {player.id} (Guild: {guild_id}) has no current location set.")

            current_location = await location_crud.get(session, id=player.current_location_id)
            if not current_location:
                # This would indicate data inconsistency
                raise MovementError(f"Current location ID {player.current_location_id} for player {player.id} not found.")

            # Ensure current_location.guild_id matches for safety, though player load should ensure this.
            if current_location.guild_id != guild_id:
                 raise MovementError(f"Data integrity issue: Player's current location {current_location.id} does not belong to guild {guild_id}.")


            target_location = await location_crud.get_by_static_id(
                session, guild_id=guild_id, static_id=target_location_static_id
            )
            if not target_location:
                return False, f"Location with ID '{target_location_static_id}' not found in this guild."

            if target_location.id == current_location.id:
                return False, f"You are already at '{target_location.name_i18n.get('en', target_location_static_id)}'."

            # Check for connectivity
            # Location.neighbor_locations_json should be a list of dicts, e.g.,
            # [{"location_id": 123, "connection_type_i18n": {"en": "path"}}, ...]
            # Or simply a list of neighbor location_ids: [123, 124]
            # For MVP, let's assume it's a list of target location_ids or static_ids.
            # The task description says: "Location.neighbor_locations_json (JSONB - list of {location_id: connection_type_i18n})"
            # Let's refine this: assume it's a list of integers (neighboring location IDs) for now for simplicity,
            # as connection_type_i18n isn't used in basic movement check.
            # A more robust implementation would parse this JSON structure.

            neighbors = current_location.neighbor_locations_json
            if not isinstance(neighbors, list):
                logger.warning(f"Location {current_location.id} (static_id: {current_location.static_id}) has malformed or no neighbor_locations_json: {neighbors}")
                neighbors = []

            # Assuming neighbor_locations_json stores a list of neighbor static_ids or primary keys (IDs)
            # For this example, let's assume it stores a list of neighbor location IDs.
            # The Location model has: neighbor_locations_json (JSONB - list of {location_id: connection_type_i18n})
            # So, we need to extract location_id from each item in the list.

            is_neighbor = False
            if isinstance(current_location.neighbor_locations_json, list):
                for neighbor_info in current_location.neighbor_locations_json:
                    if isinstance(neighbor_info, dict) and neighbor_info.get("location_id") == target_location.id:
                        is_neighbor = True
                        break

            if not is_neighbor:
                return False, f"You cannot move directly from '{current_location.name_i18n.get('en', current_location.static_id)}' to '{target_location.name_i18n.get('en', target_location_static_id)}'."

            party: Optional[Party] = None
            if player.current_party_id:
                party = await party_crud.get(session, id=player.current_party_id)
                if not party:
                    logger.warning(f"Player {player.id} has party_id {player.current_party_id} but party not found. Proceeding as solo.")
                elif party.guild_id != guild_id:
                    logger.error(f"Data integrity issue: Player's party {party.id} does not belong to guild {guild_id}.")
                    party = None # Treat as solo if party is from wrong guild

            # For MVP, if in party, party moves. Future: check RuleConfig for party_movement_policy
            # e.g. rule_val = await get_rule(session, guild_id, "party_movement_policy")

            # The actual update is now handled by the transactional helper
            # Note: _update_entities_location is already decorated with @transactional,
            # so it will use the session passed to it by handle_move_action if it's already part of a transaction,
            # or create a new one if called independently.
            # However, get_db_session() creates its own session context.
            # To use the @transactional correctly for the helper, we should pass the session from get_db_session.
            # The @transactional on _update_entities_location will then manage the commit/rollback for its scope.

            # We need to call the transactional function.
            # The @transactional decorator on _update_entities_location will inject the session.
            await _update_entities_location(
                # session=session, # DO NOT pass session explicitly, @transactional handles it
                guild_id=guild_id,
                player=player,
                target_location=target_location,
                party=party
            )
            # If _update_entities_location completes without raising an error, the transaction it manages will commit.

            # Asynchronous call to on_enter_location (fire and forget)
            entity_id_for_event = party.id if party else player.id
            entity_type_for_event = "party" if party else "player"

            # Schedule the on_enter_location call to run after this function returns and releases the session.
            # asyncio.create_task is suitable for fire-and-forget.
            asyncio.create_task(
                on_enter_location(
                    guild_id=guild_id,
                    entity_id=entity_id_for_event,
                    entity_type=entity_type_for_event,
                    location_id=target_location.id,
                )
            )

            moved_entity_message = "You and your party have" if party else "You have"
            return True, f"{moved_entity_message} moved to '{target_location.name_i18n.get('en', target_location_static_id)}'."

        except MovementError as e:
            logger.error(f"MovementError for player {player_discord_id} in guild {guild_id}: {e}")
            return False, str(e)
        except Exception as e:
            logger.exception(
                f"Unexpected error in handle_move_action for player {player_discord_id} in guild {guild_id} "
                f"targeting {target_location_static_id}: {e}"
            )
            return False, "An unexpected error occurred while trying to move."

# Example of how it might be called (for testing or from a command)
async def example_usage():
    # This requires a running DB and some data.
    # For now, this is just a conceptual example.
    # guild_id_example = 12345
    # player_discord_id_example = 67890
    # target_static_id_example = "town_square"
    # success, message = await handle_move_action(guild_id_example, player_discord_id_example, target_static_id_example)
    # print(f"Movement attempt: Success: {success}, Message: {message}")
    pass


async def _find_location_by_identifier(
    session: AsyncSession,
    guild_id: int,
    identifier: str,
    player_language: Optional[str],
    guild_main_language: Optional[str],
) -> Optional[Location]:
    """
    Finds a location by its static_id or name (i18n).
    Priority: static_id, then name by language priority.
    For name search, it's case-insensitive. If multiple names match, logs warning and returns first.
    """
    # 1. Try to find by static_id (exact match)
    location = await location_crud.get_by_static_id(session, guild_id=guild_id, static_id=identifier)
    if location:
        logger.debug(f"Found location by static_id '{identifier}' for guild {guild_id}: {location.id}")
        return location

    # 2. Try to find by name (case-insensitive, language priority)
    # Ensure identifier is in lowercase for case-insensitive comparison
    lower_identifier = identifier.lower()

    language_priority: list[str] = []
    if player_language:
        language_priority.append(player_language)
    if guild_main_language and guild_main_language != player_language: # Avoid duplicate
        language_priority.append(guild_main_language)
    if 'en' not in language_priority: # Add 'en' if not already included
        language_priority.append('en')

    logger.debug(f"Searching for location by name '{identifier}' (normalized: '{lower_identifier}') for guild {guild_id} with language priority: {language_priority}")

    for lang in language_priority:
        # Query for locations where name_i18n->>'lang' ILIKE identifier
        # Using func.lower on the JSONB text value for case-insensitivity.
        # The specific JSON access (->>) and functions depend on the DB backend (PostgreSQL assumed for JSONB).
        stmt = (
            select(Location)
            .where(
                Location.guild_id == guild_id,
                func.lower(Location.name_i18n.op("->>")(lang)) == lower_identifier
            )
        )
        results = await session.execute(stmt)
        found_locations = results.scalars().all()

        if found_locations:
            if len(found_locations) > 1:
                logger.warning(
                    f"Ambiguous location name '{identifier}' (lang: {lang}) for guild {guild_id}. "
                    f"Found {len(found_locations)} locations. Returning the first one: {found_locations[0].id}."
                )
            else:
                logger.debug(f"Found location by name '{identifier}' (lang: {lang}) for guild {guild_id}: {found_locations[0].id}")
            return found_locations[0]

    # TODO: Consider searching other keys in name_i18n if no match in priority languages, though this might be too broad.
    # For now, if not found in priority languages, it's considered not found by name.

    logger.debug(f"Location with identifier '{identifier}' not found for guild {guild_id} by static_id or prioritized names.")
    return None


async def execute_move_for_player_action(
    session: AsyncSession,
    guild_id: int,
    player_id: int, # Primary Key of the player
    target_location_identifier: str,
) -> Dict[str, Any]:
    """
    Handles the logic for a player moving to a new location, designed to be called
    from the action processing system.

    Args:
        session: The SQLAlchemy AsyncSession.
        guild_id: The ID of the guild.
        player_id: The Primary Key of the player initiating the move.
        target_location_identifier: The static_id or name of the target location.

    Returns:
        A dictionary with "status" and "message".
    """
    try:
        player = await player_crud.get(session, id=player_id)
        if not player:
            # This should ideally not happen if player_id comes from a validated context
            raise MovementError(f"Player with ID {player_id} not found.")
        if player.guild_id != guild_id:
            # Security check
            raise MovementError(f"Player {player_id} does not belong to guild {guild_id}.")

        if player.current_location_id is None:
            raise MovementError(f"Player {player.id} (Guild: {guild_id}) has no current location set.")

        current_location = await location_crud.get(session, id=player.current_location_id)
        if not current_location:
            raise MovementError(f"Current location ID {player.current_location_id} for player {player.id} not found.")
        if current_location.guild_id != guild_id:
             raise MovementError(f"Data integrity issue: Player's current location {current_location.id} does not belong to guild {guild_id}.")

        # Resolve target_location_identifier using the new helper
        player_lang = player.selected_language
        # Fetch guild_main_language using get_rule; provide a default if not set or rule system not fully integrated
        guild_main_lang = await get_rule(session, guild_id, "guild_main_language", default="en")
        # Ensure guild_main_lang is a string, as get_rule can return complex types if the rule is complex.
        # For 'guild_main_language', we expect a simple string.
        if not isinstance(guild_main_lang, str):
            logger.warning(f"Rule 'guild_main_language' for guild {guild_id} returned non-string value: {guild_main_lang}. Defaulting to 'en'.")
            guild_main_lang = "en"


        target_location = await _find_location_by_identifier(
            session,
            guild_id,
            target_location_identifier,
            player_language=player_lang,
            guild_main_language=guild_main_lang
        )

        if not target_location:
            logger.info(f"Player {player.id} tried to move to '{target_location_identifier}', but it was not found (guild: {guild_id}).")
            return {"status": "error", "message": f"Location '{target_location_identifier}' could not be found."}

        if target_location.id == current_location.id:
            # Using name_i18n.get for user-facing messages
            # Assuming 'en' as a default fallback if specific language logic isn't fully implemented here
            loc_name = target_location.name_i18n.get(player.selected_language or 'en', target_location.static_id)
            return {"status": "error", "message": f"You are already at '{loc_name}'."}

        # Check for connectivity
        is_neighbor = False
        if isinstance(current_location.neighbor_locations_json, list):
            for neighbor_info in current_location.neighbor_locations_json:
                if isinstance(neighbor_info, dict) and neighbor_info.get("location_id") == target_location.id:
                    is_neighbor = True
                    break

        if not is_neighbor:
            curr_loc_name = current_location.name_i18n.get(player.selected_language or 'en', current_location.static_id)
            target_loc_name = target_location.name_i18n.get(player.selected_language or 'en', target_location.static_id)
            return {"status": "error", "message": f"You cannot move directly from '{curr_loc_name}' to '{target_loc_name}'."}

        party: Optional[Party] = None
        if player.current_party_id:
            party = await party_crud.get(session, id=player.current_party_id)
            if not party:
                logger.warning(f"Player {player.id} has party_id {player.current_party_id} but party not found. Proceeding as solo.")
            elif party.guild_id != guild_id:
                logger.error(f"Data integrity issue: Player's party {party.id} does not belong to guild {guild_id}.")
                party = None # Treat as solo

        # TODO (Task 25): Integrate RuleConfig check for party_movement_policy.
        # Example:
        # party_movement_rule = await get_rule(session, guild_id, "party_movement_policy", default_value="all_move")
        # if party_movement_rule == "leader_only" and (not party or party.leader_id != player.id):
        #     # Logic to prevent movement or handle accordingly
        #     pass
        # if party_movement_rule == "majority_vote":
        #     # Complex logic for voting needed
        #     pass
        # For current MVP (Task 1.3 / Task 25), if player is in a party, the whole party moves.
        # This matches the "all_move" implicit policy.

        await _update_entities_location(
            guild_id=guild_id,
            player=player,
            target_location=target_location,
            party=party,
            session=session # Explicitly pass session to the transactional function
        )

        # Asynchronous call to on_enter_location (fire and forget)
        entity_id_for_event = party.id if party else player.id
        entity_type_for_event = "party" if party else "player"

        # Ensure on_enter_location is called after the current transaction might have committed.
        # It's better to schedule it if it performs its own DB operations or is lengthy.
        asyncio.create_task(
            on_enter_location(
                guild_id=guild_id,
                entity_id=entity_id_for_event,
                entity_type=entity_type_for_event,
                location_id=target_location.id,
            )
        )

        target_loc_display_name = target_location.name_i18n.get(player.selected_language or 'en', target_location.static_id)
        moved_entity_message = "You and your party have" if party else "You have"
        return {"status": "success", "message": f"{moved_entity_message} moved to '{target_loc_display_name}'."}

    except MovementError as e:
        logger.warning(f"MovementError for player {player_id} in guild {guild_id} targeting '{target_location_identifier}': {e}")
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.exception(
            f"Unexpected error in execute_move_for_player_action for player {player_id} in guild {guild_id} "
            f"targeting '{target_location_identifier}': {e}"
        )
        return {"status": "error", "message": "An unexpected internal error occurred while trying to move."}
