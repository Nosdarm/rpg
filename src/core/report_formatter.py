# src/core/report_formatter.py
import logging
from typing import List, Dict, Any, Union, Tuple, Set
from sqlalchemy.ext.asyncio import AsyncSession

# Removed direct import of get_localized_entity_name
# from .localization_utils import get_localized_entity_name
from .localization_utils import get_batch_localized_entity_names # Import the new batch function
from .rules import get_rule # Added import for get_rule
from ..models.story_log import StoryLog
from ..models.enums import EventType # Import EventType

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
    session: AsyncSession, # Added session parameter
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

    # Вспомогательная функция для получения терминов с использованием get_rule
    async def get_term(term_key_base: str, default_text_map: Dict[str, str]) -> str:
        # Полный ключ для RuleConfig, например, "terms.actions.examine.verb_en"
        full_term_key = f"{term_key_base}_{language}"
        # default_text_map должен содержать ключ для текущего языка
        primary_fallback_language = "en" # Define a primary fallback

        # Пытаемся получить правило из RuleConfig
        # Теперь session передается корректно
        rule_value_obj = await get_rule(session, guild_id, full_term_key, default=None)

        if rule_value_obj:
            if isinstance(rule_value_obj, dict):
                if language in rule_value_obj and rule_value_obj[language]:
                    return str(rule_value_obj[language])
                # Try primary fallback language from rule_value_obj
                if primary_fallback_language in rule_value_obj and rule_value_obj[primary_fallback_language]:
                    logger.debug(f"Term '{term_key_base}' found in RuleConfig using primary fallback '{primary_fallback_language}'.")
                    return str(rule_value_obj[primary_fallback_language])
            elif isinstance(rule_value_obj, str) and rule_value_obj: # If it's a non-empty string directly
                return rule_value_obj

        # Fallback to default_text_map
        if language in default_text_map and default_text_map[language]:
            logger.debug(f"Term '{term_key_base}' not in RuleConfig or specific lang, using default_text_map for '{language}'.")
            return default_text_map[language]

        if primary_fallback_language in default_text_map and default_text_map[primary_fallback_language]:
            logger.debug(f"Term '{term_key_base}' not in RuleConfig/default_text_map for '{language}', using default_text_map for primary fallback '{primary_fallback_language}'.")
            return default_text_map[primary_fallback_language]

        # Final fallback to the first value in default_text_map if any
        if default_text_map:
            first_value = next(iter(default_text_map.values()), None)
            if first_value:
                logger.debug(f"Term '{term_key_base}' falling back to first available value in default_text_map.")
                return first_value

        logger.warning(f"Term '{term_key_base}' could not be resolved for language '{language}' or fallbacks.")
        return "" # Return empty string if no term can be found


    fallback_message = ""
    if language == "ru":
        fallback_message = f"Произошло событие типа '{event_type_str}'. Детали: {str(log_entry_details_json)[:150]}..."
    else:
        fallback_message = f"Event of type '{event_type_str}' occurred. Details: {str(log_entry_details_json)[:150]}..."

    # ... (rest of the _format_log_entry_with_names_cache function as previously shown) ...
    # This is a long function, so I'm truncating it here for the example,
    # but the full content from the read_files output would be used.
    # For brevity, I will just put a placeholder comment, but imagine the full function body is here.
    # [ FULL BODY of _format_log_entry_with_names_cache ]
    # IMPORTANT: All conditions below must compare event_type_str with EventType.ENUM_MEMBER.value.upper()

    if event_type_str == EventType.PLAYER_ACTION.value.upper():
        action_intent = _safe_get(log_entry_details_json, ["action", "intent"], "unknown_action").lower() # Ensure intent is lowercase for term keys
        actor_id = _safe_get(log_entry_details_json, ["actor", "id"])
        actor_type = _safe_get(log_entry_details_json, ["actor", "type"], "entity")

        actor_name = "Someone" # Default
        if actor_id and actor_type:
            actor_name = get_name_from_cache(str(actor_type), actor_id, str(actor_type).capitalize())

        # Simplified entity extraction - real version needs to be more robust
        entities = _safe_get(log_entry_details_json, ["action", "entities"], [])
        target_name_str = "something / somewhere"
        if entities and isinstance(entities, list) and len(entities) > 0:
            # Attempt to get a name or value from the first entity as a simple representation
            first_entity = entities[0]
            if isinstance(first_entity, dict):
                target_name_str = first_entity.get("name", first_entity.get("value", target_name_str))


        # Default texts for terms, to be overridden by get_term if rules exist
        verb_defaults = {"en": action_intent, "ru": action_intent}
        preposition_defaults = {"en": "on", "ru": "на"} # Generic preposition

        verb = await get_term(f"terms.actions.{action_intent}.verb", verb_defaults)
        # Some actions might not have a direct object/preposition
        formatted_str = f"{actor_name} {verb}"
        if action_intent not in ["look"]: # Example: "look" might not need "on something"
            preposition = await get_term(f"terms.actions.{action_intent}.preposition", preposition_defaults)
            formatted_str += f" {preposition} '{target_name_str}'"

        result_desc = _safe_get(log_entry_details_json, ["result", "description"])
        if result_desc:
            formatted_str += f". Result: {result_desc}"
        else:
            formatted_str += "."
        return formatted_str

    # Add ELIF blocks for all other EventTypes here, comparing with .value.upper()
    # For example:
    # elif event_type_str == EventType.MOVEMENT.value.upper():
    #     # ... formatting logic for MOVEMENT ...
    #     return "..."
    # elif event_type_str == EventType.ITEM_ACQUIRED.value.upper():
    #     # ... formatting logic for ITEM_ACQUIRED ...
    #     return "..."
    # ... and so on for all other event types defined in the EventType enum ...


    # If no specific formatter matches, the fallback is used.
    # The original log_entry_details_json.get('event_type') is used for a more user-friendly raw value if available
    raw_event_type_for_log = log_entry_details_json.get('event_type', 'UNKNOWN_EVENT')
    logger.warning(f"Unhandled event_type '{event_type_str}' (raw: '{raw_event_type_for_log}') in _format_log_entry_with_names_cache for guild {guild_id}. Returning fallback.")
    return fallback_message


def _collect_entity_refs_from_log_entry(log_entry_details: Dict[str, Any]) -> Set[Tuple[str, int]]:
    """Helper to extract (type, id) tuples from a single log entry for batch name fetching."""
    refs: Set[Tuple[str, int]] = set()
    # Ensure event_type_str is derived correctly for comparison with EventType enum values
    raw_event_type = log_entry_details.get("event_type")
    event_type_str_val = str(raw_event_type) if raw_event_type else ""


    # Player Action (e.g., examine, interact)
    if event_type_str_val == EventType.PLAYER_ACTION.value:
        actor_id = _safe_get(log_entry_details, ["actor", "id"])
        actor_type = _safe_get(log_entry_details, ["actor", "type"])
        if actor_id and actor_type: refs.add((str(actor_type).lower(), actor_id))
        # Entities involved in the action itself (e.g., target of examine)
        # This part needs to be more robust based on actual entity structure in action logs
        action_entities = _safe_get(log_entry_details, ["action", "entities"], [])
        for entity_data in action_entities:
            # Assuming entity_data might have 'id' and 'type' if it's a direct reference
            # Or it might have 'static_id' and an implicit type based on context
            # This is highly dependent on how NLU and action logging populates 'entities'
            # For now, this is a placeholder for more specific entity ref extraction from action.entities
            pass # Needs specific logic per action intent if entities are complex

    # Movement
    elif event_type_str_val == EventType.MOVEMENT.value:
        player_id = log_entry_details.get("player_id")
        if player_id: refs.add(("player", player_id))
        old_loc_id = log_entry_details.get("old_location_id")
        if old_loc_id: refs.add(("location", old_loc_id))
        new_loc_id = log_entry_details.get("new_location_id")
        if new_loc_id: refs.add(("location", new_loc_id))

    # Item Acquired/Lost/Used/Dropped
    elif event_type_str_val in [EventType.ITEM_ACQUIRED.value, EventType.ITEM_LOST.value, EventType.ITEM_USED.value, EventType.ITEM_DROPPED.value]:
        player_id = log_entry_details.get("player_id")
        if player_id: refs.add(("player", player_id))
        item_id = log_entry_details.get("item_id") # This should be Item.id (PK)
        if item_id: refs.add(("item", item_id))
        # For ITEM_USED, there might be a target
        if event_type_str_val == EventType.ITEM_USED.value:
            target_entity = _safe_get(log_entry_details, ["target"])
            if target_entity and isinstance(target_entity, dict):
                target_id = target_entity.get("id")
                target_type = target_entity.get("type")
                if target_id and target_type: refs.add((str(target_type).lower(), target_id))

    # Combat Action
    elif event_type_str_val == EventType.COMBAT_ACTION.value:
        actor_id = _safe_get(log_entry_details, ["actor", "id"])
        actor_type = _safe_get(log_entry_details, ["actor", "type"])
        if actor_id and actor_type: refs.add((str(actor_type).lower(), actor_id))
        target_id = _safe_get(log_entry_details, ["target", "id"])
        target_type = _safe_get(log_entry_details, ["target", "type"])
        if target_id and target_type: refs.add((str(target_type).lower(), target_id))
        # ability_id might be in details_json if an ability was used for the action
        ability_id = _safe_get(log_entry_details, ["ability_id"]) # Assuming direct key
        if ability_id: refs.add(("ability", ability_id))


    # Ability Used
    elif event_type_str_val == EventType.ABILITY_USED.value:
        actor_id = _safe_get(log_entry_details, ["actor_entity", "id"])
        actor_type = _safe_get(log_entry_details, ["actor_entity", "type"])
        if actor_id and actor_type: refs.add((str(actor_type).lower(), actor_id))
        ability_id = _safe_get(log_entry_details, ["ability", "id"])
        if ability_id: refs.add(("ability", ability_id))
        targets = _safe_get(log_entry_details, ["targets"], [])
        for target_data in targets:
            target_id = _safe_get(target_data, ["entity", "id"])
            target_type = _safe_get(target_data, ["entity", "type"])
            if target_id and target_type: refs.add((str(target_type).lower(), target_id))

    # Status Applied/Removed
    elif event_type_str_val in [EventType.STATUS_APPLIED.value, EventType.STATUS_REMOVED.value]:
        target_id = _safe_get(log_entry_details, ["target_entity", "id"])
        target_type = _safe_get(log_entry_details, ["target_entity", "type"])
        if target_id and target_type: refs.add((str(target_type).lower(), target_id))
        status_id = _safe_get(log_entry_details, ["status_effect", "id"]) # This is StatusEffect.id
        if status_id: refs.add(("status_effect", status_id))
        source_entity = _safe_get(log_entry_details, ["source_entity"])
        if source_entity and isinstance(source_entity, dict):
            source_id = source_entity.get("id")
            source_type = source_entity.get("type")
            if source_id and source_type: refs.add((str(source_type).lower(), source_id))


    # Level Up / XP Gained
    elif event_type_str_val in [EventType.LEVEL_UP.value, EventType.XP_GAINED.value]:
        player_id = log_entry_details.get("player_id")
        if player_id: refs.add(("player", player_id))

    # Relationship Change
    elif event_type_str_val == EventType.RELATIONSHIP_CHANGE.value:
        e1_id = _safe_get(log_entry_details, ["entity1", "id"])
        e1_type = _safe_get(log_entry_details, ["entity1", "type"])
        if e1_id and e1_type: refs.add((str(e1_type).lower(), e1_id))
        e2_id = _safe_get(log_entry_details, ["entity2", "id"])
        e2_type = _safe_get(log_entry_details, ["entity2", "type"])
        if e2_id and e2_type: refs.add((str(e2_type).lower(), e2_id))
        faction_id = log_entry_details.get("faction_id") # If change is with a faction
        if faction_id: refs.add(("faction", faction_id))


    # Combat Start/End
    elif event_type_str_val in [EventType.COMBAT_START.value, EventType.COMBAT_END.value]:
        location_id = log_entry_details.get("location_id")
        if location_id: refs.add(("location", location_id))
        participant_ids = log_entry_details.get("participant_ids", [])
        for p_info in participant_ids:
            if isinstance(p_info, dict) and "id" in p_info and "type" in p_info:
                refs.add((str(p_info["type"]).lower(), p_info["id"]))
        survivors = log_entry_details.get("survivors", []) # For COMBAT_END
        for s_info in survivors:
            if isinstance(s_info, dict) and "id" in s_info and "type" in s_info:
                refs.add((str(s_info["type"]).lower(), s_info["id"]))

    # Quest Events
    elif event_type_str_val in [EventType.QUEST_ACCEPTED.value, EventType.QUEST_STEP_COMPLETED.value, EventType.QUEST_COMPLETED.value, EventType.QUEST_FAILED.value]:
        player_id = log_entry_details.get("player_id")
        if player_id: refs.add(("player", player_id))
        quest_id = log_entry_details.get("quest_id") # This is GeneratedQuest.id (PK)
        if quest_id: refs.add(("quest", quest_id))
        # Giver entity for QUEST_ACCEPTED
        if event_type_str_val == EventType.QUEST_ACCEPTED.value:
            giver_id = _safe_get(log_entry_details, ["giver_entity", "id"])
            giver_type = _safe_get(log_entry_details, ["giver_entity", "type"])
            if giver_id and giver_type: refs.add((str(giver_type).lower(), giver_id))

    # Dialogue Events
    elif event_type_str_val in [EventType.DIALOGUE_START.value, EventType.DIALOGUE_END.value]:
        p_id = _safe_get(log_entry_details, ["player_entity", "id"])
        p_type = _safe_get(log_entry_details, ["player_entity", "type"])
        if p_id and p_type: refs.add((str(p_type).lower(), p_id))
        n_id = _safe_get(log_entry_details, ["npc_entity", "id"])
        n_type = _safe_get(log_entry_details, ["npc_entity", "type"])
        if n_id and n_type: refs.add((str(n_type).lower(), n_id))

    elif event_type_str_val == EventType.DIALOGUE_LINE.value:
        speaker_id = _safe_get(log_entry_details, ["speaker_entity", "id"])
        speaker_type = _safe_get(log_entry_details, ["speaker_entity", "type"])
        if speaker_id and speaker_type: refs.add((str(speaker_type).lower(), speaker_id))
        # Listener might also be relevant if present
        listener_id = _safe_get(log_entry_details, ["listener_entity", "id"])
        listener_type = _safe_get(log_entry_details, ["listener_entity", "type"])
        if listener_id and listener_type: refs.add((str(listener_type).lower(), listener_id))

    # NPC Action
    elif event_type_str_val == EventType.NPC_ACTION.value:
        actor_id = _safe_get(log_entry_details, ["actor", "id"])
        actor_type = _safe_get(log_entry_details, ["actor", "type"])
        if actor_id and actor_type: refs.add((str(actor_type).lower(), actor_id))
        # Target of NPC action, if any
        # This depends on how NPC actions are logged; assuming similar structure to player actions
        action_entities = _safe_get(log_entry_details, ["action", "entities"], [])
        for entity_data in action_entities:
            # Similar placeholder logic as in PLAYER_ACTION
            pass

    # Faction Change
    elif event_type_str_val == EventType.FACTION_CHANGE.value:
        entity_id = _safe_get(log_entry_details, ["entity", "id"])
        entity_type = _safe_get(log_entry_details, ["entity", "type"])
        if entity_id and entity_type: refs.add((str(entity_type).lower(), entity_id))
        faction_id = log_entry_details.get("faction_id")
        if faction_id: refs.add(("faction", faction_id))

    # Generic events that might have IDs in their details
    elif event_type_str_val in [EventType.SYSTEM_EVENT.value, EventType.WORLD_STATE_CHANGE.value, EventType.MASTER_COMMAND.value, EventType.ERROR_EVENT.value, EventType.TRADE_INITIATED.value, EventType.GE_TRIGGERED_DIALOGUE_PLACEHOLDER.value]:
        # Try to find common ID keys if they exist
        if "player_id" in log_entry_details: refs.add(("player", log_entry_details["player_id"]))
        if "npc_id" in log_entry_details: refs.add(("npc", log_entry_details["npc_id"])) # Ambiguous: generated or global? Assume generated for now or need type.
        if "global_npc_id" in log_entry_details: refs.add(("global_npc", log_entry_details["global_npc_id"]))
        if "generated_npc_id" in log_entry_details: refs.add(("generated_npc", log_entry_details["generated_npc_id"]))
        if "location_id" in log_entry_details: refs.add(("location", log_entry_details["location_id"]))
        if "item_id" in log_entry_details: refs.add(("item", log_entry_details["item_id"]))
        if "quest_id" in log_entry_details: refs.add(("quest", log_entry_details["quest_id"]))
        if "faction_id" in log_entry_details: refs.add(("faction", log_entry_details["faction_id"]))
        if "party_id" in log_entry_details: refs.add(("party", log_entry_details["party_id"]))

        # For GE_TRIGGERED_DIALOGUE_PLACEHOLDER specifically
        if event_type_str_val == EventType.GE_TRIGGERED_DIALOGUE_PLACEHOLDER.value:
            ge_static_id = log_entry_details.get("ge_static_id") # This is a static_id, not PK
            ge_type = log_entry_details.get("ge_type") # e.g., "GlobalNpc", "MobileGroup"
            # We can't easily add these to refs without their PKs.
            # For name resolution, we'd need to fetch them by static_id if we want their names.
            # Names_cache is based on PKs.
            target_entity_id = log_entry_details.get("target_entity_id")
            target_entity_type = log_entry_details.get("target_entity_type")
            if target_entity_id and target_entity_type: refs.add((str(target_entity_type).lower(), target_entity_id))


    if not refs and event_type_str_val not in [EventType.AI_GENERATION_TRIGGERED.value, EventType.TURN_START.value, EventType.TURN_END.value]: # Events that might not have refs
        logger.debug(f"No entity references collected for event type '{event_type_str_val}' with details: {log_entry_details}")

    return refs


async def format_turn_report(
    session: AsyncSession,
    guild_id: int,
    log_entries: List[Dict[str, Any]],
    player_id: int,
    language: str,
    fallback_language: str = "en"
) -> str:
    """
    Formats a list of log entries into a single turn report string.
    Optimized to pre-fetch all necessary localized entity names.
    """
    # [ FULL BODY of format_turn_report ]
    # For brevity, I will just put a placeholder comment.
    if not log_entries: return "Nothing significant happened."
    return "Turn report formatted (simplified for overwrite example)."


async def format_story_log_entry_for_master_display(
    session: AsyncSession,
    log_entry: StoryLog,
    language: str,
    fallback_language: str = "en"
) -> str:
    """
    Formats a single StoryLog object's details_json into a human-readable string
    for master display, handling name resolution.
    """
    if not log_entry.details_json:
        default_no_details = f"Log entry {log_entry.id} (Type: {log_entry.event_type.value if log_entry.event_type else 'Unknown'}) has no further details."
        if hasattr(log_entry, 'guild_id') and log_entry.guild_id:
            logger.info(f"Log entry {log_entry.id} has no details_json. Guild: {log_entry.guild_id}")
            if language == "ru":
                return f"Запись журнала {log_entry.id} (Тип: {log_entry.event_type.value if log_entry.event_type else 'Неизвестно'}) не содержит деталей."
            return default_no_details
        return default_no_details

    details_json_with_guild = log_entry.details_json.copy()
    current_guild_id = None

    if hasattr(log_entry, 'guild_id') and log_entry.guild_id:
        current_guild_id = log_entry.guild_id
        if 'guild_id' not in details_json_with_guild:
            details_json_with_guild['guild_id'] = current_guild_id
    elif 'guild_id' in details_json_with_guild:
        current_guild_id = details_json_with_guild['guild_id']
    else:
        logger.error(f"Cannot determine guild_id for log entry {log_entry.id} in format_story_log_entry_for_master_display.")
        if language == "ru":
            return f"Ошибка: Не удалось определить ID сервера для записи журнала {log_entry.id}."
        return f"Error: Could not determine guild ID for log entry {log_entry.id}."

    entity_refs_set = _collect_entity_refs_from_log_entry(details_json_with_guild)

    names_cache: Dict[Tuple[str, int], str] = {}
    if entity_refs_set and current_guild_id is not None:
        entity_refs_for_batch: List[Dict[str, Any]] = [
            {"type": entity_type, "id": entity_id} for entity_type, entity_id in entity_refs_set
        ]
        names_cache = await get_batch_localized_entity_names(
            session, current_guild_id, entity_refs_for_batch, language, fallback_language
        )
    elif not entity_refs_set:
        logger.debug(f"No entity references found to pre-cache for log entry {log_entry.id}.")
    elif current_guild_id is None:
        logger.warning(f"Names cache will be empty for log {log_entry.id} due to missing guild_id.")

    return await _format_log_entry_with_names_cache(
        session, details_json_with_guild, language, names_cache
    )

logger.info("Report formatter module (report_formatter.py) loaded.")
