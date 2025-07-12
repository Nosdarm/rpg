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
from .game_events import on_enter_location
from .utils import log_event
from .rules import get_rule # Now used for guild_main_language as well

logger = logging.getLogger(__name__)

class MovementError(Exception):
    """Custom exception for movement errors."""
    pass

# Placeholder for a proper localization utility for player feedback
def _localize_movement_error(message_key: str, default_format_string: str, **kwargs) -> str:
    # In a real system, this would look up `message_key` in a localization file/system
    # for the player's language and format it with kwargs.
    # For now, it just uses the default_format_string.
    # This helper is to mark strings that need localization.
    try:
        return default_format_string.format(**kwargs)
    except KeyError as e:
        logger.error(f"Localization key error for key '{message_key}': Missing key {e} in provided kwargs {kwargs}. Default string: '{default_format_string}'")
        return default_format_string # Return unformatted string if a kwarg is missing

@transactional
async def _update_entities_location(
    # session: AsyncSession, # Session is injected by @transactional as a keyword argument
    guild_id: int,
    player: Player,
    target_location: Location,
    party: Optional[Party] = None,
    resource_deductions: Optional[Dict[str, int]] = None, # New parameter for deductions
    *, # Make session a keyword-only argument
    session: AsyncSession
) -> None:
    """
    Helper function to update player/party location and deduct resources in DB.
    Runs within a transaction. Session is injected.
    """
    player_original_location_id = player.current_location_id
    player.current_location_id = target_location.id

    # Apply resource deductions to the player
    if resource_deductions:
        if player.properties_json is None:
            player.properties_json = {} # Ensure properties_json exists
        if "resources" not in player.properties_json:
            player.properties_json["resources"] = {}

        for resource_name, amount_to_deduct in resource_deductions.items():
            current_amount = player.properties_json["resources"].get(resource_name, 0)
            player.properties_json["resources"][resource_name] = current_amount - amount_to_deduct
            logger.info(f"Deducted {amount_to_deduct} of {resource_name} from player {player.id}. New amount: {player.properties_json['resources'][resource_name]}")
        # Mark properties_json as modified if it's a JSON/JSONB type to ensure SQLAlchemy picks up changes
        # This is often needed for mutable JSON types.
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(player, "properties_json")


    session.add(player)
    logger.info(f"Player {player.id} (Guild: {guild_id}) moving from {player_original_location_id} to {target_location.id}")

    if party:
        # TODO: Party resource deduction logic if party has its own resource pool or if costs are shared.
        # For now, costs are only applied to the initiating player.
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
                    # Corrected to use "target_location_id" to match model spec and execute_move_for_player_action
                    if isinstance(neighbor_info, dict) and neighbor_info.get("target_location_id") == target_location.id:
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
            await _update_entities_location( # type: ignore [call-arg]
                # session is injected by @transactional on _update_entities_location
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
    lower_identifier = identifier.lower()

    language_priority: list[str] = []
    if player_language:
        language_priority.append(player_language)
    if guild_main_language and guild_main_language != player_language:
        language_priority.append(guild_main_language)
    if 'en' not in language_priority:
        language_priority.append('en')

    logger.debug(f"Searching for location by name '{identifier}' (normalized: '{lower_identifier}') for guild {guild_id} with language priority: {language_priority}")

    for lang in language_priority:
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

    # Fallback: search all language keys in name_i18n if not found in priority languages
    logger.debug(f"Location '{identifier}' not found in priority languages. Expanding search to all available languages in name_i18n.")
    # This is a more complex query. We can iterate through all locations and check their name_i18n dict.
    # This is less efficient but will work. A better solution might involve DB-specific JSON functions.
    all_locations_in_guild = await location_crud.get_multi_by_guild(session, guild_id=guild_id, limit=10000) # Assuming a reasonable limit
    for loc in all_locations_in_guild:
        if isinstance(loc.name_i18n, dict):
            for lang_key, name_val in loc.name_i18n.items():
                if isinstance(name_val, str) and name_val.lower() == lower_identifier:
                    logger.warning(f"Found location '{identifier}' by fallback search in lang '{lang_key}'. Location ID: {loc.id}. Consider adding this as a primary language name.")
                    return loc


    logger.debug(f"Location with identifier '{identifier}' not found for guild {guild_id} by static_id or any name.")
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
            raise MovementError(_localize_movement_error("player_not_found", "Player with ID {player_id} not found.", player_id=player_id))
        if player.guild_id != guild_id:
            # Security check - internal error, less critical for player localization
            raise MovementError(f"Player {player_id} does not belong to guild {guild_id}.")

        # Player Status Check
        allowed_statuses_rule = await get_rule(session, guild_id, "movement:allowed_player_statuses", default=["IDLE", "EXPLORING"])
        # Ensure allowed_statuses_rule is a list of strings
        if not isinstance(allowed_statuses_rule, list) or not all(isinstance(s, str) for s in allowed_statuses_rule): # Corrected variable name
            logger.warning(f"Rule 'movement:allowed_player_statuses' for guild {guild_id} is not a list of strings: {allowed_statuses_rule}. Defaulting to ['IDLE', 'EXPLORING'].")
            allowed_statuses_list = ["IDLE", "EXPLORING"]
        else:
            allowed_statuses_list = [status.upper() for status in allowed_statuses_rule] # Corrected variable name

        player_status_upper = player.current_status.value.upper()
        logger.debug(f"Player status for move check: '{player_status_upper}' (type: {type(player_status_upper)})")
        logger.debug(f"Allowed statuses for move: {allowed_statuses_list} (type: {type(allowed_statuses_list)})")
        for i, s_item in enumerate(allowed_statuses_list): # Renamed s to s_item to avoid conflict if logger was a global s
            logger.debug(f"Allowed status item {i}: '{s_item}' (type: {type(s_item)})")

        if player_status_upper not in allowed_statuses_list:
            logger.error(f"Movement denied: Player status '{player_status_upper}' not in allowed list {allowed_statuses_list}.")
            raise MovementError(_localize_movement_error(
                "invalid_status_for_movement",
                "Cannot move while in status: {current_status}. Allowed statuses: {allowed_statuses_list_str}",
                current_status=player.current_status.value,
                allowed_statuses_list_str=', '.join(allowed_statuses_list)
            ))

        if player.current_location_id is None:
            raise MovementError(_localize_movement_error("no_current_location", "Player {player_name} (ID: {player_id}) has no current location set.", player_name=player.name, player_id=player.id))

        current_location = await location_crud.get(session, id=player.current_location_id)
        if not current_location:
            # Internal error
            raise MovementError(f"Current location ID {player.current_location_id} for player {player.id} not found.")
        if current_location.guild_id != guild_id:
             # Internal error
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
            return {"status": "error", "message": _localize_movement_error("target_location_not_found", "Location '{identifier}' could not be found.", identifier=target_location_identifier)}

        if target_location.id == current_location.id:
            # Using name_i18n.get for user-facing messages
            loc_name = target_location.name_i18n.get(player.selected_language or guild_main_lang, target_location.static_id or target_location_identifier)
            return {"status": "error", "message": _localize_movement_error("already_at_location", "You are already at '{location_name}'.", location_name=loc_name)}

        # Check for connectivity and get connection details
        connection_details: Optional[Dict[str, Any]] = None
        logger.debug(f"Checking connectivity from {current_location.id} ({current_location.static_id}) to {target_location.id} ({target_location.static_id})")
        logger.debug(f"Current location neighbors: {current_location.neighbor_locations_json}")
        if isinstance(current_location.neighbor_locations_json, list):
            for i, neighbor_info_item in enumerate(current_location.neighbor_locations_json):
                logger.debug(f"Neighbor {i}: {neighbor_info_item}")
                if isinstance(neighbor_info_item, dict):
                    logger.debug(f"Neighbor dict keys: {list(neighbor_info_item.keys())}") # Log keys
                    neighbor_target_id = neighbor_info_item.get("target_location_id")
                    logger.debug(f"Comparing neighbor target_id {neighbor_target_id} (type: {type(neighbor_target_id)}) with target_location.id {target_location.id} (type: {type(target_location.id)})")
                    if neighbor_target_id == target_location.id:
                        connection_details = neighbor_info_item
                        logger.debug(f"Connection found: {connection_details}")
                        break
                else:
                    logger.warning(f"Neighbor item {neighbor_info_item} is not a dict.")
        else:
            logger.warning(f"current_location.neighbor_locations_json is not a list: {type(current_location.neighbor_locations_json)}")


        if not connection_details:
            curr_loc_name = current_location.name_i18n.get(player.selected_language or guild_main_lang, current_location.static_id or "current location")
            target_loc_name = target_location.name_i18n.get(player.selected_language or guild_main_lang, target_location.static_id or "target location")
            logger.error(f"No direct connection found from {current_location.id} to {target_location.id}. Raising MovementError.")
            raise MovementError(_localize_movement_error("no_direct_connection", "You cannot move directly from '{current_location_name}' to '{target_location_name}'. No valid connection found.", current_location_name=curr_loc_name, target_location_name=target_loc_name))

        # Connection Conditions Check
        conditions = connection_details.get("conditions_json")
        if isinstance(conditions, dict):
            # World Flag Check
            required_world_flag = conditions.get("requires_world_flag")
            if isinstance(required_world_flag, dict): # e.g. {"flag_name": "bridge_repaired", "expected_value": True}
                flag_name = required_world_flag.get("flag_name")
                expected_value = required_world_flag.get("expected_value", True) # Default to True if not specified
                if flag_name:
                    actual_flag_value = await get_rule(session, guild_id, f"worldstate:{flag_name}", default=not expected_value)
                    if actual_flag_value != expected_value:
                        denial_message_key = conditions.get("denial_message_key", "movement_denied_world_flag")
                        # Attempt to get a more specific message from i18n if available in conditions
                        denial_message_i18n = conditions.get("denial_message_i18n")
                        default_denial_str = f"Cannot move: A condition ('{flag_name}') is not met."

                        final_denial_message = default_denial_str
                        if isinstance(denial_message_i18n, dict):
                            final_denial_message = get_localized_text(denial_message_i18n, player.selected_language or guild_main_lang, default_denial_str)

                        raise MovementError(_localize_movement_error(denial_message_key, final_denial_message, flag_name=flag_name))

            # Placeholder for Item Check
            required_item_static_id = conditions.get("requires_item_static_id")
            if required_item_static_id:
                from backend.core.crud import inventory_item_crud, item_crud # For item definition
                from backend.models.enums import OwnerEntityType

                item_definition = await item_crud.get_by_static_id(session, guild_id=guild_id, static_id=required_item_static_id)
                if not item_definition:
                    logger.error(f"Movement condition references unknown item static_id: {required_item_static_id}")
                    raise MovementError(_localize_movement_error("internal_item_misconfigured", "Internal error: Movement requirement misconfigured (item {item_static_id}).", item_static_id=required_item_static_id))

                item_found_in_inventory = False
                # Check player's inventory
                player_inventory = await inventory_item_crud.get_inventory_for_owner(
                    session, guild_id=guild_id, owner_entity_id=player.id, owner_entity_type=OwnerEntityType.PLAYER
                )
                for inv_item in player_inventory:
                    if inv_item.item_id == item_definition.id and inv_item.quantity > 0: # Basic check, quantity could be part of condition
                        item_found_in_inventory = True
                        break

                if not item_found_in_inventory and party:
                    # TODO: Implement RuleConfig check: "party:movement:item_source_policy" (e.g., "any_member", "leader_only", "shared_pool")
                    # For now, check all party members if player doesn't have it.
                    member_ids = party.player_ids_json or []
                    for member_id in member_ids:
                        if member_id == player.id: continue # Already checked
                        member_inventory = await inventory_item_crud.get_inventory_for_owner(
                            session, guild_id=guild_id, owner_entity_id=member_id, owner_entity_type=OwnerEntityType.PLAYER
                        )
                        for inv_item in member_inventory:
                            if inv_item.item_id == item_definition.id and inv_item.quantity > 0:
                                item_found_in_inventory = True
                                break
                        if item_found_in_inventory:
                            break

                if not item_found_in_inventory:
                    item_name_for_message = item_definition.name_i18n.get(player.selected_language or guild_main_lang, required_item_static_id)
                    raise MovementError(_localize_movement_error("missing_required_item_movement", "Missing required item to pass: {item_name}.", item_name=item_name_for_message))

            # Quest Status Check
            required_quest_status_condition = conditions.get("requires_quest_status")
            if isinstance(required_quest_status_condition, dict): # e.g. {"quest_static_id": "main_quest_01", "status": "COMPLETED"}
                quest_static_id = required_quest_status_condition.get("quest_static_id")
                expected_status_str = required_quest_status_condition.get("status")

                if quest_static_id and expected_status_str:
                    from backend.core.crud.crud_quest import generated_quest_crud, player_quest_progress_crud
                    from backend.models.enums import QuestStatus # Assuming QuestStatus is in enums

                    quest_def = await generated_quest_crud.get_by_static_id(session, static_id=quest_static_id, guild_id=guild_id)
                    if not quest_def:
                        logger.error(f"Movement condition references unknown quest static_id: {quest_static_id}")
                        raise MovementError(_localize_movement_error("internal_quest_misconfigured_sid", "Internal error: Movement requirement misconfigured (quest static_id {quest_static_id}).", quest_static_id=quest_static_id))

                    try:
                        expected_status_enum = QuestStatus[expected_status_str.upper()]
                    except KeyError:
                        logger.error(f"Movement condition references invalid quest status: {expected_status_str} for quest {quest_static_id}")
                        raise MovementError(_localize_movement_error("internal_quest_misconfigured_status", "Internal error: Movement requirement misconfigured (quest status {expected_status}).", expected_status=expected_status_str))

                    quest_condition_met = False
                    # Check player's quest progress
                    # Ensure player_quest_progress_crud can filter by guild_id if necessary, or that quest_id is globally unique.
                    # Assuming quest_def.id is the correct quest_id PK.
                    player_progress = await player_quest_progress_crud.get_by_player_and_quest(
                        session, player_id=player.id, quest_id=quest_def.id, guild_id=guild_id
                    )
                    if player_progress and player_progress.status == expected_status_enum:
                        quest_condition_met = True

                    if not quest_condition_met and party:
                        # TODO: Implement RuleConfig check: "party:movement:quest_status_policy"
                        # (e.g., "any_member_has_status", "leader_has_status", "all_members_have_status")
                        # For now, if player doesn't have it, check if party has it (assuming party quest progress might exist)
                        # This assumes PlayerQuestProgress can also link to a party_id.
                        if party.id: # Ensure party object and id exist
                            party_progress = await player_quest_progress_crud.get_by_party_and_quest(
                               session, party_id=party.id, quest_id=quest_def.id, guild_id=guild_id
                            )
                            if party_progress and party_progress.status == expected_status_enum:
                                quest_condition_met = True

                    if not quest_condition_met:
                        quest_name_for_message = quest_def.title_i18n.get(player.selected_language or guild_main_lang, quest_static_id)
                        raise MovementError(_localize_movement_error("quest_condition_not_met_movement", "Cannot move: Quest '{quest_name}' status is not '{expected_status}'.", quest_name=quest_name_for_message, expected_status=expected_status_str))
                else:
                    logger.warning(f"Invalid 'requires_quest_status' condition in movement: {required_quest_status_condition}")

            # Location properties based movement modification
            # Current location outgoing effects
            current_loc_props = current_location.properties_json if isinstance(current_location.properties_json, dict) else {}
            if "blocked_movement_reason_key" in current_loc_props:
                reason_key = current_loc_props["blocked_movement_reason_key"]
                reason_text = get_localized_text(current_loc_props.get('blocked_movement_reason_i18n'), player.selected_language or guild_main_lang, reason_key)
                raise MovementError(_localize_movement_error("movement_blocked_from_current", "Movement from {location_name} is currently blocked: {reason}", location_name=current_loc_name, reason=reason_text))

            # Target location incoming effects
            target_loc_props = target_location.properties_json if isinstance(target_location.properties_json, dict) else {}
            if "blocked_movement_reason_key" in target_loc_props:
                reason_key = target_loc_props["blocked_movement_reason_key"]
                reason_text = get_localized_text(target_loc_props.get('blocked_movement_reason_i18n'), player.selected_language or guild_main_lang, reason_key)
                raise MovementError(_localize_movement_error("movement_blocked_to_target", "Movement to {location_name} is currently blocked: {reason}", location_name=target_loc_name, reason=reason_text))

            movement_dc_modifier_from_loc = current_loc_props.get("movement_dc_modifier", 0) + target_loc_props.get("movement_dc_modifier", 0)
            movement_cost_multiplier_from_loc = current_loc_props.get("movement_cost_multiplier", 1.0) * target_loc_props.get("movement_cost_multiplier", 1.0)


            # Skill Check
            skill_check_info = conditions.get("requires_skill_check") # e.g. {"skill": "climbing", "dc": 15, "attribute": "strength"}
            if isinstance(skill_check_info, dict):
                check_type = skill_check_info.get("check_type", f"movement:{skill_check_info.get('skill', 'generic')}")
                base_attribute_for_check = skill_check_info.get("attribute")
                skill_for_check = skill_check_info.get("skill")
                dc_for_check = skill_check_info.get("dc")

                if isinstance(dc_for_check, int): # Ensure dc_for_check is an int before modifying
                    dc_for_check += movement_dc_modifier_from_loc
                    logger.info(f"Applied location DC modifier {movement_dc_modifier_from_loc}. New DC: {dc_for_check}")


                if dc_for_check is not None: # Only perform check if DC is specified
                    from backend.core.check_resolver import resolve_check, CheckError
                    from backend.models.enums import RelationshipEntityType

                    # Determine who performs the check
                    actor_for_check_id = player.id
                    actor_for_check_type = RelationshipEntityType.PLAYER # Default to player
                    actor_model_for_check = player # Default to player model

                    if party:
                        performer_policy = await get_rule(session, guild_id, "party:movement_skill_check_performer", default="initiator")
                        if performer_policy == "leader":
                            if party.leader_player_id:
                                leader_player_model = await player_crud.get(session, id=party.leader_player_id)
                                if leader_player_model:
                                    actor_for_check_id = leader_player_model.id
                                    actor_model_for_check = leader_player_model
                                    # actor_for_check_type remains PLAYER
                                    logger.info(f"Party movement skill check to be performed by leader: {leader_player_model.name} (ID: {leader_player_model.id})")
                                else:
                                    logger.warning(f"Party leader (ID: {party.leader_player_id}) for party {party.id} not found. Defaulting check performer to initiator {player.name}.")
                            else:
                                logger.warning(f"Party {party.id} has no leader_player_id set. Defaulting check performer to initiator {player.name}.")
                        elif performer_policy == "initiator":
                            logger.info(f"Party movement skill check to be performed by initiator: {player.name} (ID: {player.id})")
                            # Defaults are already set to initiator
                        elif performer_policy == "highest_member_skill":
                            attribute_to_check = skill_check_info.get("attribute")
                            if attribute_to_check:
                                best_performer_model = player
                                try:
                                    max_stat_value = int(player.attributes_json.get(attribute_to_check, -1000))
                                except (ValueError, TypeError):
                                    max_stat_value = -1000 # Treat non-int as very low

                                member_ids = party.player_ids_json or []
                                for member_id in member_ids:
                                    if member_id == player.id: # Initiator already considered
                                        continue
                                    member_player = await player_crud.get(session, id=member_id)
                                    if member_player and isinstance(member_player.attributes_json, dict):
                                        try:
                                            member_stat_value = int(member_player.attributes_json.get(attribute_to_check, -1000))
                                            if member_stat_value > max_stat_value:
                                                max_stat_value = member_stat_value
                                                best_performer_model = member_player
                                        except (ValueError, TypeError):
                                            continue # Ignore member if stat is not int

                                actor_model_for_check = best_performer_model
                                actor_for_check_id = best_performer_model.id
                                logger.info(f"Party movement skill check by 'highest_member_skill' ({attribute_to_check}): {actor_model_for_check.name} (ID: {actor_for_check_id}) with value {max_stat_value}")
                            else:
                                logger.warning(f"'highest_member_skill' policy requires 'attribute' in skill_check_info. Defaulting to initiator.")
                        # TODO: Implement "average_party_skill" policy
                        else:
                            logger.warning(f"Unknown party:movement_skill_check_performer policy '{performer_policy}'. Defaulting to initiator.")

                    check_context_for_resolve = {
                        "base_attribute_override": base_attribute_for_check, # Allow check_resolver to use this
                        "skill_override": skill_for_check, # Allow check_resolver to use this
                        "lang": player.selected_language or guild_main_lang
                    }

                    try:
                        logger.info(f"Performing movement skill check: type='{check_type}', dc={dc_for_check}, actor={actor_for_check_id}")
                        check_result = await resolve_check(
                            session=session,
                            guild_id=guild_id,
                            check_type=check_type,
                            actor_entity_id=actor_for_check_id,
                            actor_entity_type=actor_for_check_type,
                            actor_entity_model=actor_model_for_check,
                            difficulty_dc=dc_for_check,
                            check_context=check_context_for_resolve
                        )
                        # Log the check result (e.g., to StoryLog or movement event details)
                        # For now, just log to debug
                        logger.debug(f"Movement skill check result: {check_result.outcome.status} (Value: {check_result.final_value} vs DC: {dc_for_check})")

                        # Check RuleConfig for what outcomes mean failure for movement
                        fail_on_outcomes = await get_rule(session, guild_id, "movement:fail_on_check_outcome", default=["CRITICAL_FAILURE", "FAILURE"])
                        if not isinstance(fail_on_outcomes, list): fail_on_outcomes = ["CRITICAL_FAILURE", "FAILURE"]

                        if check_result.outcome.status.upper() in fail_on_outcomes:
                            raise MovementError(_localize_movement_error("skill_check_failed_movement", "Skill check for movement failed: {outcome_description}", outcome_description=check_result.outcome.description))

                    except CheckError as ce:
                        logger.error(f"Error during movement skill check: {ce}")
                        raise MovementError(_localize_movement_error("skill_check_error_movement", "Could not perform required skill check: {error_message}", error_message=str(ce)))
                    except Exception as e: # Catch other potential errors from resolve_check
                        logger.exception(f"Unexpected error during resolve_check for movement: {e}")
                        raise MovementError(_localize_movement_error("skill_check_unexpected_error_movement", "An unexpected error occurred during a required skill check."))
                else:
                    logger.debug(f"Skill check defined in connection_details for {target_location.id} but no DC specified. Skipping check.")


        # Placeholder for Costs
        travel_time_minutes = connection_details.get("travel_time_minutes")
        if travel_time_minutes:
            logger.info(f"Movement implies travel time: {travel_time_minutes} minutes. (Effect not yet implemented)")
            # TODO: Add to event log, potentially affect game time or entity resources.

        # Resource Costs Check & Preparation
        resource_costs_to_apply: Dict[str, int] = {}
        defined_resource_costs = connection_details.get("resource_costs_json") # e.g. {"stamina": 5, "rations": 1}

        if not isinstance(defined_resource_costs, dict) or not defined_resource_costs:
            # Fallback to RuleConfig if not in connection_details or if empty
            cost_rule_key = f"movement:costs:{current_location.type.value}:{target_location.type.value}"
            rule_based_costs = await get_rule(session, guild_id, cost_rule_key, default=None)
            if isinstance(rule_based_costs, dict):
                defined_resource_costs = rule_based_costs
                logger.info(f"Using RuleConfig defined costs for movement from {current_location.type.value} to {target_location.type.value}: {defined_resource_costs}")
            else:
                if rule_based_costs is not None: # Rule existed but was not a dict
                    logger.warning(f"RuleConfig key {cost_rule_key} did not return a dictionary. Value: {rule_based_costs}")
                defined_resource_costs = {} # Ensure it's a dict for the next block

        if isinstance(defined_resource_costs, dict) and defined_resource_costs: # Check again if we got costs from RuleConfig
            player_resources = player.properties_json.get("resources", {}) if player.properties_json else {}
            # TODO: Implement party:movement:resource_source_policy from RuleConfig.
            # Current logic assumes initiator (player) pays all costs.
            # If party exists and policy is e.g. "leader_pays", "all_contribute_even", or "first_available":
            # - 'player_resources' would need to be fetched from the correct player(s).
            # - 'resource_costs_to_apply' might need to be split if 'all_contribute_even'.
            # - '_update_entities_location' would need to be adapted to deduct from the correct player(s)
            #   or a shared party resource pool if that model is introduced.
            for resource_name, cost_amount in defined_resource_costs.items():
                if not isinstance(cost_amount, int) or cost_amount <= 0:
                    logger.warning(f"Invalid cost amount {cost_amount} for resource '{resource_name}' in movement connection. Skipping this cost.")
                    continue

                current_player_amount = player_resources.get(resource_name, 0)
                if current_player_amount < cost_amount:
                    raise MovementError(_localize_movement_error("insufficient_resource_movement", "Not enough {resource_name} to move. Required: {required_amount}, You have: {current_amount}.", resource_name=resource_name, required_amount=cost_amount, current_amount=current_player_amount))
                resource_costs_to_apply[resource_name] = cost_amount

            if resource_costs_to_apply and movement_cost_multiplier_from_loc != 1.0:
                logger.info(f"Applying location cost multiplier {movement_cost_multiplier_from_loc} to resource costs.")
                for resource_name in resource_costs_to_apply:
                    original_cost = resource_costs_to_apply[resource_name]
                    multiplied_cost = int(original_cost * movement_cost_multiplier_from_loc)
                    if multiplied_cost < 0 : multiplied_cost = 0 # Cost cannot be negative

                    # Re-check if player can afford the multiplied cost
                    current_player_amount = player_resources.get(resource_name, 0) # Re-fetch in case of multiple costs
                    if current_player_amount < multiplied_cost:
                        raise MovementError(_localize_movement_error("insufficient_resource_modified_movement", "Not enough {resource_name} after location cost modification. Required: {required_amount}, You have: {current_amount}.", resource_name=resource_name, required_amount=multiplied_cost, current_amount=current_player_amount))
                    resource_costs_to_apply[resource_name] = multiplied_cost
                logger.info(f"Player {player.id} final resource costs after location multiplier: {resource_costs_to_apply}")

            if resource_costs_to_apply:
                logger.info(f"Player {player.id} will incur resource costs for movement: {resource_costs_to_apply}")
        # TODO: Implement fallback to RuleConfig for costs if not in connection_details

        party: Optional[Party] = None
        if player.current_party_id:
            party = await party_crud.get(session, id=player.current_party_id)
            if not party:
                logger.warning(f"Player {player.id} has party_id {player.current_party_id} but party not found. Proceeding as solo.")
            elif party.guild_id != guild_id:
                logger.error(f"Data integrity issue: Player's party {party.id} does not belong to guild {guild_id}.")
                party = None # Treat as solo

            if party:
                # Check party movement rules
                party_movement_policy_key = "party:movement:policy" # Corrected key format based on Tasks.txt
                movement_policy = await get_rule(session, guild_id, party_movement_policy_key, default="any_member")

                if movement_policy == "leader_only":
                    if party.leader_player_id != player.id:
                        leader_name_msg = "the party leader"
                        if party.leader_player_id: # Check if leader_player_id is not None
                            leader_player = await player_crud.get(session, id=party.leader_player_id)
                            if leader_player:
                                leader_name_msg = leader_player.name
                        raise MovementError(_localize_movement_error("party_leader_only_movement", "Only {leader_name} can move the party. You are not the leader.", leader_name=leader_name_msg))
                elif movement_policy == "all_members_ready":
                    # This policy implies all members must have an allowed status.
                    # The initiating player's status was already checked.
                    # We need to fetch all party members (excluding the initiator if already checked, or just check all).
                    member_ids = party.player_ids_json or []
                    for member_id in member_ids:
                        if member_id == player.id: # Initiator already checked
                            continue
                        member_player = await player_crud.get(session, id=member_id)
                        if not member_player:
                            logger.warning(f"Party {party.id} references non-existent player ID {member_id}. Skipping status check for this member.")
                            continue
                        if member_player.current_status.value not in allowed_statuses_rule: # Use same allowed_statuses_rule as for initiator
                            raise MovementError(_localize_movement_error("party_member_not_ready_movement", "Party cannot move. Member {member_name} (ID: {member_id}) is not ready (status: {status}).", member_name=member_player.name, member_id=member_id, status=member_player.current_status.value))
                elif movement_policy == "any_member":
                    pass # Any member can move the party, current behavior. Initiator's status already checked.
                else:
                    logger.warning(f"Unknown party movement policy '{movement_policy}' for guild {guild_id}. Defaulting to 'any_member'.")

        await _update_entities_location(
            guild_id=guild_id,
            player=player,
            target_location=target_location,
            party=party,
            resource_deductions=resource_costs_to_apply if resource_costs_to_apply else None,
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

        target_loc_display_name = target_location.name_i18n.get(player.selected_language or guild_main_lang, target_location.static_id or target_location_identifier)
        moved_entity_message_key = "movement_success_party" if party else "movement_success_solo"
        success_default_template = "You and your party have moved to '{location_name}'." if party else "You have moved to '{location_name}'."

        success_message = _localize_movement_error(moved_entity_message_key, success_default_template, location_name=target_loc_display_name)
        return {"status": "success", "message": success_message}

    except MovementError as e:
        logger.warning(f"MovementError for player {player_id} in guild {guild_id} targeting '{target_location_identifier}': {e}")
        # Messages from MovementError are already wrapped with _localize_movement_error or are internal.
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.exception(
            f"Unexpected error in execute_move_for_player_action for player {player_id} in guild {guild_id} "
            f"targeting '{target_location_identifier}': {e}"
        )
        return {"status": "error", "message": _localize_movement_error("generic_movement_error", "An unexpected internal error occurred while trying to move.")}
