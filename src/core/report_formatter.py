# src/core/report_formatter.py
import logging
from typing import List, Dict, Any, Union, Tuple, Set
from sqlalchemy.ext.asyncio import AsyncSession

# Removed direct import of get_localized_entity_name
# from .localization_utils import get_localized_entity_name
from .localization_utils import get_batch_localized_entity_names # Import the new batch function

logger = logging.getLogger(__name__)

# Helper to safely get potentially nested dictionary values
def _safe_get(data: Dict, path: List[Union[str, int]], default: Any = None) -> Any:
    current = data
    for key_or_index in path:
        if isinstance(key_or_index, str):
            if not isinstance(current, dict) or key_or_index not in current:
                return default
            current = current[key_or_index]
        elif isinstance(key_or_index, int):
            if not isinstance(current, list) or not (0 <= key_or_index < len(current)):
                return default
            current = current[key_or_index]
        else:
            logger.warning(f"_safe_get encountered unexpected key type: {type(key_or_index)}")
            return default
    return current

async def _format_log_entry_with_names_cache(
    log_entry_details_json: Dict[str, Any],
    language: str,
    names_cache: Dict[Tuple[str, int], str]
) -> str:
    """
    Formats a single log entry's details_json into a human-readable string
    in the specified language, using a pre-filled cache for entity names.
    """
    guild_id = log_entry_details_json.get("guild_id")
    event_type_str = str(log_entry_details_json.get("event_type", "UNKNOWN_EVENT")).upper()

    if not guild_id: # Should ideally be caught before calling this if names_cache is guild-specific
        logger.warning("_format_log_entry_with_names_cache: 'guild_id' not found.")
        return "Error: Missing guild information in log entry (formatter)."
    if not event_type_str or event_type_str == "UNKNOWN_EVENT":
        logger.warning(f"_format_log_entry_with_names_cache: 'event_type' missing for guild {guild_id}.")
        return f"Error: Missing event type in log entry (guild {guild_id})."

    def get_name_from_cache(entity_type: str, entity_id: int, default_prefix: str = "Entity") -> str:
        return names_cache.get((entity_type.lower(), entity_id), f"[{default_prefix} ID: {entity_id} (Cached?)]")

    fallback_message = ""
    if language == "ru":
        fallback_message = f"Произошло событие типа '{event_type_str}'. Детали: {str(log_entry_details_json)[:150]}..."
    else:
        fallback_message = f"Event of type '{event_type_str}' occurred. Details: {str(log_entry_details_json)[:150]}..."

    if event_type_str == "PLAYER_ACTION":
        action_intent = _safe_get(log_entry_details_json, ["action", "intent"], "unknown_action")
        actor_id = _safe_get(log_entry_details_json, ["actor", "id"])
        actor_type = _safe_get(log_entry_details_json, ["actor", "type"], "entity")
        target_name_str = _safe_get(log_entry_details_json, ["action", "entities", 0, "name"], "something")

        actor_name = get_name_from_cache(actor_type, actor_id, actor_type.capitalize()) if actor_id and actor_type else "Someone"

        if action_intent == "examine":
            target_description = _safe_get(log_entry_details_json, ["result", "description"], "nothing special")
            if language == "ru":
                return f"{actor_name} осматривает '{target_name_str}'. Вы видите: {target_description}"
            return f"{actor_name} examines '{target_name_str}'. You see: {target_description}"
        elif action_intent == "interact":
            interaction_result = _safe_get(log_entry_details_json, ["result", "message"], "nothing happens.")
            if language == "ru":
                return f"{actor_name} взаимодействует с '{target_name_str}'. В результате: {interaction_result}"
            return f"{actor_name} interacts with '{target_name_str}'. As a result: {interaction_result}"
        elif action_intent == "go_to":
            sublocation_name = target_name_str
            if language == "ru":
                return f"{actor_name} перемещается к '{sublocation_name}' внутри текущей локации."
            return f"{actor_name} moves to '{sublocation_name}' within the current location."
        else:
            if language == "ru":
                return f"{actor_name} выполняет действие '{action_intent}' на '{target_name_str}'."
            return f"{actor_name} performs action '{action_intent}' on '{target_name_str}'."

    elif event_type_str == "PLAYER_MOVE":
        player_id = log_entry_details_json.get("player_id")
        old_loc_id = log_entry_details_json.get("old_location_id")
        new_loc_id = log_entry_details_json.get("new_location_id")

        player_name = get_name_from_cache("player", player_id, "Player") if player_id else "Unknown Player"
        old_loc_name = get_name_from_cache("location", old_loc_id, "Location") if old_loc_id else "an unknown place"
        new_loc_name = get_name_from_cache("location", new_loc_id, "Location") if new_loc_id else "a new mysterious place"

        if language == "ru":
            return f"{player_name} переместился из '{old_loc_name}' в '{new_loc_name}'."
        return f"{player_name} moved from '{old_loc_name}' to '{new_loc_name}'."

    elif event_type_str == "ITEM_ACQUIRED":
        player_id = log_entry_details_json.get("player_id")
        item_id = log_entry_details_json.get("item_id")
        quantity = log_entry_details_json.get("quantity", 1)
        source = log_entry_details_json.get("source", "somewhere")

        player_name = get_name_from_cache("player", player_id, "Player") if player_id else "Someone"
        item_name = get_name_from_cache("item", item_id, "Item") if item_id else "an item"

        if language == "ru":
            return f"{player_name} получает {item_name} (x{quantity}) из {source}."
        return f"{player_name} acquired {item_name} (x{quantity}) from {source}."

    elif event_type_str == "COMBAT_ACTION":
        actor_id = _safe_get(log_entry_details_json, ["actor", "id"])
        actor_type = _safe_get(log_entry_details_json, ["actor", "type"], "combatant")
        target_id = _safe_get(log_entry_details_json, ["target", "id"])
        target_type = _safe_get(log_entry_details_json, ["target", "type"], "combatant")
        action_name = log_entry_details_json.get("action_name", "an action")
        damage = log_entry_details_json.get("damage")

        actor_name = get_name_from_cache(actor_type, actor_id, actor_type.capitalize()) if actor_id and actor_type else "A combatant"
        target_name = get_name_from_cache(target_type, target_id, target_type.capitalize()) if target_id and target_type else "another combatant"

        if damage is not None:
            if language == "ru":
                return f"{actor_name} использует '{action_name}' против {target_name}, нанося {damage} урона."
            return f"{actor_name} uses '{action_name}' on {target_name}, dealing {damage} damage."
        else:
            if language == "ru":
                return f"{actor_name} использует '{action_name}' против {target_name}."
            return f"{actor_name} uses '{action_name}' on {target_name}."

    logger.warning(f"Unhandled event_type '{event_type_str}' in _format_log_entry_with_names_cache for guild {guild_id}. Returning fallback.")
    return fallback_message


def _collect_entity_refs_from_log_entry(log_entry_details: Dict[str, Any]) -> Set[Tuple[str, int]]:
    """Helper to extract (type, id) tuples from a single log entry for batch name fetching."""
    refs: Set[Tuple[str, int]] = set()
    event_type_str = str(log_entry_details.get("event_type", "")).upper()

    if event_type_str == "PLAYER_ACTION":
        actor_id = _safe_get(log_entry_details, ["actor", "id"])
        actor_type = _safe_get(log_entry_details, ["actor", "type"])
        if actor_id and actor_type: refs.add((str(actor_type).lower(), actor_id))
        # Note: target_name_str from entities[0]['name'] is not an ID, so not added here.
        # If entities contained IDs, they would be added.

    elif event_type_str == "PLAYER_MOVE":
        player_id = log_entry_details.get("player_id")
        old_loc_id = log_entry_details.get("old_location_id")
        new_loc_id = log_entry_details.get("new_location_id")
        if player_id: refs.add(("player", player_id))
        if old_loc_id: refs.add(("location", old_loc_id))
        if new_loc_id: refs.add(("location", new_loc_id))

    elif event_type_str == "ITEM_ACQUIRED":
        player_id = log_entry_details.get("player_id")
        item_id = log_entry_details.get("item_id")
        if player_id: refs.add(("player", player_id))
        if item_id: refs.add(("item", item_id))

    elif event_type_str == "COMBAT_ACTION":
        actor_id = _safe_get(log_entry_details, ["actor", "id"])
        actor_type = _safe_get(log_entry_details, ["actor", "type"])
        target_id = _safe_get(log_entry_details, ["target", "id"])
        target_type = _safe_get(log_entry_details, ["target", "type"])
        if actor_id and actor_type: refs.add((str(actor_type).lower(), actor_id))
        if target_id and target_type: refs.add((str(target_type).lower(), target_id))

    # Add extraction logic for other event types as they are implemented
    return refs


async def format_turn_report(
    session: AsyncSession,
    guild_id: int,
    log_entries: List[Dict[str, Any]],
    player_id: int,
    language: str,
    fallback_language: str = "en" # Added fallback_language
) -> str:
    """
    Formats a list of log entries into a single turn report string.
    Optimized to pre-fetch all necessary localized entity names.
    """
    if not log_entries:
        if language == "ru":
            return "За этот ход ничего значительного не произошло."
        return "Nothing significant happened this turn."

    # 1. Collect all unique entity references from all log entries
    all_entity_refs: Set[Tuple[str, int]] = set()
    # Add the player for whom the report is generated, to ensure their name is in the cache for the header
    if player_id is not None:
        all_entity_refs.add(("player", player_id))

    prepared_log_entries = []
    for entry in log_entries:
        current_entry_guild_id = entry.get("guild_id")
        if current_entry_guild_id is None:
            logger.debug(f"Entry missing guild_id, injecting main report guild_id: {guild_id} into a copy.")
            entry_with_guild_id = entry.copy()
            entry_with_guild_id["guild_id"] = guild_id
            prepared_log_entries.append(entry_with_guild_id)
        elif current_entry_guild_id == guild_id:
            prepared_log_entries.append(entry)
        else:
            logger.warning(f"Guild ID mismatch in log entry for report. Expected {guild_id}, got {current_entry_guild_id}. Skipping entry.")
            # This entry is skipped and will not be processed further

    # Now, collect entity_refs from the prepared_log_entries
    for entry_details in prepared_log_entries:
        all_entity_refs.update(_collect_entity_refs_from_log_entry(entry_details))

    # 2. Batch fetch localized names for all collected references
    names_cache: Dict[Tuple[str, int], str] = {}
    if all_entity_refs: # Only call if there are refs to fetch
        names_cache = await get_batch_localized_entity_names(
            session, guild_id, list(all_entity_refs), language, fallback_language
        )

    # 3. Format each *prepared* log entry using the names_cache
    formatted_parts = []
    for entry_details in prepared_log_entries: # Iterate over prepared_log_entries
        # guild_id is guaranteed to be in entry_details here due to preparation step
        formatted_line = await _format_log_entry_with_names_cache(
            entry_details, language, names_cache
        )
        formatted_parts.append(formatted_line)

    report_separator = "\n"
    player_name = names_cache.get(("player", player_id), f"Player {player_id}") # Get player name from cache if available

    if language == "ru":
        report_header = f"Отчет по ходу для {player_name}:\n"
        return report_header + report_separator.join(formatted_parts)

    report_header = f"Turn Report for {player_name}:\n"
    return report_header + report_separator.join(formatted_parts)

logger.info("Report formatter module (report_formatter.py) created with placeholder functions.")
