import logging
import json
import asyncio
from typing import Tuple, Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select # Ensure this is imported for select statements

from .database import transactional, get_db_session
from .crud import player_crud, party_crud, location_crud
from ..models import Player, Party, Location
from .game_events import on_enter_location, log_event # Placeholders
from .rules import get_rule # For party movement rules, if needed later

logger = logging.getLogger(__name__)

class MovementError(Exception):
    """Custom exception for movement errors."""
    pass

@transactional
async def _update_entities_location(
    session: AsyncSession,
    guild_id: int,
    player: Player,
    target_location: Location,
    party: Optional[Party] = None,
) -> None:
    """
    Helper function to update player and optionally party location in DB
    and log the event. Runs within a transaction.
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
