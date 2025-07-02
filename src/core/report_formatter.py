# src/core/report_formatter.py
import logging
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from .localization_utils import get_localized_entity_name
# from .rules import get_rule # Example, if RuleConfig terms are needed

logger = logging.getLogger(__name__)

# Helper to safely get potentially nested dictionary values
def _safe_get(data: Dict, path: List[str], default: Any = None) -> Any:
    current = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current

async def format_log_entry(
    session: AsyncSession,
    log_entry_details_json: Dict[str, Any],
    language: str
) -> str:
    """
    Formats a single log entry's details_json into a human-readable string
    in the specified language.
    """
    guild_id = log_entry_details_json.get("guild_id")
    # Ensure event_type is treated as a string, as it comes from JSON
    event_type_str = str(log_entry_details_json.get("event_type", "UNKNOWN_EVENT")).upper()


    if not guild_id:
        logger.warning("format_log_entry: 'guild_id' not found in log_entry_details_json.")
        # Provide a generic error message that doesn't depend on language if basic context is missing
        return "Error: Missing guild information in log entry (format_log_entry)."
    if not event_type_str or event_type_str == "UNKNOWN_EVENT":
        logger.warning(f"format_log_entry: 'event_type' missing or unknown in log_entry_details_json for guild {guild_id}.")
        return f"Error: Missing or unknown event type in log entry (guild {guild_id})."

    # --- Event Type Specific Formatting ---
    # Each event type will need its own logic to extract data and format the string.
    # We'll use the get_localized_entity_name for entity names.

    # Default fallback message
    fallback_message = ""
    if language == "ru":
        fallback_message = f"Произошло событие типа '{event_type_str}'. Детали: {str(log_entry_details_json)[:150]}..."
    else:
        fallback_message = f"Event of type '{event_type_str}' occurred. Details: {str(log_entry_details_json)[:150]}..."

    # --- PLAYER_ACTION event type (generic wrapper for NLU actions) ---
    if event_type_str == "PLAYER_ACTION":
        action_intent = _safe_get(log_entry_details_json, ["action", "intent"], "unknown_action")
        actor_id = _safe_get(log_entry_details_json, ["actor", "id"])
        actor_type = _safe_get(log_entry_details_json, ["actor", "type"], "entity") # e.g. "player"
        target_name_str = _safe_get(log_entry_details_json, ["action", "entities", 0, "name"], "something") # simple first entity

        actor_name = "Someone"
        if actor_id and actor_type:
            actor_name = await get_localized_entity_name(session, guild_id, actor_type, actor_id, language)

        # Sub-dispatch based on intent
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

        elif action_intent == "go_to": # For sublocations
            sublocation_name = target_name_str # Assuming target_name_str is the sublocation
            if language == "ru":
                return f"{actor_name} перемещается к '{sublocation_name}' внутри текущей локации."
            return f"{actor_name} moves to '{sublocation_name}' within the current location."

        else: # Fallback for other PLAYER_ACTION intents
            if language == "ru":
                return f"{actor_name} выполняет действие '{action_intent}' на '{target_name_str}'."
            return f"{actor_name} performs action '{action_intent}' on '{target_name_str}'."


    # --- PLAYER_MOVE event (between map locations) ---
    elif event_type_str == "PLAYER_MOVE":
        player_id = log_entry_details_json.get("player_id")
        old_loc_id = log_entry_details_json.get("old_location_id")
        new_loc_id = log_entry_details_json.get("new_location_id")

        player_name = await get_localized_entity_name(session, guild_id, "player", player_id, language) if player_id else "Unknown Player"
        old_loc_name = await get_localized_entity_name(session, guild_id, "location", old_loc_id, language) if old_loc_id else "an unknown place"
        new_loc_name = await get_localized_entity_name(session, guild_id, "location", new_loc_id, language) if new_loc_id else "a new mysterious place"

        if language == "ru":
            return f"{player_name} переместился из '{old_loc_name}' в '{new_loc_name}'."
        return f"{player_name} moved from '{old_loc_name}' to '{new_loc_name}'."

    # --- Example: ITEM_ACQUIRED ---
    elif event_type_str == "ITEM_ACQUIRED":
        player_id = log_entry_details_json.get("player_id")
        item_id = log_entry_details_json.get("item_id")
        quantity = log_entry_details_json.get("quantity", 1)
        source = log_entry_details_json.get("source", "somewhere") # e.g., "loot", "quest reward", "shop"

        player_name = await get_localized_entity_name(session, guild_id, "player", player_id, language) if player_id else "Someone"
        item_name = await get_localized_entity_name(session, guild_id, "item", item_id, language) if item_id else "an item"

        if language == "ru":
            return f"{player_name} получает {item_name} (x{quantity}) из {source}."
        return f"{player_name} acquired {item_name} (x{quantity}) from {source}."

    # --- Example: COMBAT_ACTION ---
    elif event_type_str == "COMBAT_ACTION":
        actor_id = _safe_get(log_entry_details_json, ["actor", "id"])
        actor_type = _safe_get(log_entry_details_json, ["actor", "type"], "combatant")
        target_id = _safe_get(log_entry_details_json, ["target", "id"])
        target_type = _safe_get(log_entry_details_json, ["target", "type"], "combatant")
        action_name = log_entry_details_json.get("action_name", "an action") # e.g., "Attack", "Fireball"
        damage = log_entry_details_json.get("damage")

        actor_name = await get_localized_entity_name(session, guild_id, actor_type, actor_id, language) if actor_id and actor_type else "A combatant"
        target_name = await get_localized_entity_name(session, guild_id, target_type, target_id, language) if target_id and target_type else "another combatant"

        if damage is not None:
            if language == "ru":
                return f"{actor_name} использует '{action_name}' против {target_name}, нанося {damage} урона."
            return f"{actor_name} uses '{action_name}' on {target_name}, dealing {damage} damage."
        else:
            if language == "ru":
                return f"{actor_name} использует '{action_name}' против {target_name}."
            return f"{actor_name} uses '{action_name}' on {target_name}."

    # Add more event_type handlers here...
    # elif event_type_str == "QUEST_ACCEPTED": ...
    # elif event_type_str == "NPC_DIALOGUE": ...

    logger.warning(f"Unhandled event_type '{event_type_str}' in format_log_entry for guild {guild_id}. Returning fallback.")
    return fallback_message


async def format_turn_report(
    session: AsyncSession,
    guild_id: int,
    log_entries: List[Dict[str, Any]],
    player_id: int, # Potentially used for player-specific context in the future
    language: str
) -> str:
    """
    Formats a list of log entries (details_json parts) into a single turn report string
    for a specific player in their language.

    Args:
        session: The database session.
        guild_id: The ID of the guild for this report.
        log_entries: A list of log entry details (dictionaries from StoryLog.details_json).
        player_id: The ID of the player for whom this report is generated.
        language: The target language for the report.

    Returns:
        A formatted, localized turn report string.
    """
    if not log_entries:
        if language == "ru":
            return "За этот ход ничего значительного не произошло."
        return "Nothing significant happened this turn."

    formatted_parts = []
    for entry_details in log_entries:
        # Ensure guild_id from log entry matches, or inject if necessary (though task says it's in details_json)
        if "guild_id" not in entry_details:
            entry_details_with_guild = entry_details.copy()
            entry_details_with_guild["guild_id"] = guild_id # Inject if missing, for format_log_entry
            formatted_line = await format_log_entry(session, entry_details_with_guild, language)
        else:
            if entry_details.get("guild_id") != guild_id:
                logger.warning(f"Guild ID mismatch in log entry for report. Expected {guild_id}, got {entry_details.get('guild_id')}. Skipping.")
                continue # Or handle as an error
            formatted_line = await format_log_entry(session, entry_details, language)

        formatted_parts.append(formatted_line)

    # Join parts with newlines or other appropriate formatting
    report_separator = "\n"
    if language == "ru":
        report_header = f"Отчет по ходу для игрока {player_id}:\n"
        return report_header + report_separator.join(formatted_parts)

    report_header = f"Turn Report for Player {player_id}:\n"
    return report_header + report_separator.join(formatted_parts)

logger.info("Report formatter module (report_formatter.py) created with placeholder functions.")
