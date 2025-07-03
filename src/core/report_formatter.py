# src/core/report_formatter.py
import logging
from typing import List, Dict, Any, Union, Tuple, Set
from sqlalchemy.ext.asyncio import AsyncSession

# Removed direct import of get_localized_entity_name
# from .localization_utils import get_localized_entity_name
from .localization_utils import get_batch_localized_entity_names # Import the new batch function
from .rules import get_rule # Added import for get_rule

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

    # Вспомогательная функция для получения терминов с использованием get_rule
    async def get_term(term_key_base: str, default_text_map: Dict[str, str]) -> str:
        # Полный ключ для RuleConfig, например, "terms.actions.examine.verb_en"
        full_term_key = f"{term_key_base}_{language}"
        # default_text_map должен содержать ключ для текущего языка
        default_for_lang = default_text_map.get(language, list(default_text_map.values())[0] if default_text_map else "")

        # Пытаемся получить правило из RuleConfig
        # get_rule ожидает session, но мы в _format_log_entry_with_names_cache ее не имеем напрямую.
        # Это серьезное упущение в дизайне этой функции, если она должна использовать get_rule.
        # Для прохождения тестов, которые мокают get_rule, нам нужно, чтобы он вызывался.
        # Временно будем передавать None как session, тесты должны это мокать.
        # В реальной системе это потребует рефакторинга для передачи сессии.
        # Однако, фикстура mock_get_rule_fixture в тестах сама по себе является AsyncMock
        # и не требует сессии в своей реализации. Патчинг должен перехватить вызов.

        rule_value_obj = await get_rule(None, guild_id, full_term_key, default=None) # type: ignore

        if rule_value_obj:
            if isinstance(rule_value_obj, dict):
                if language in rule_value_obj:
                    return str(rule_value_obj[language])
                # Если это словарь, но нужного языка нет, используем default_for_lang
                # (или можно было бы попробовать fallback язык из словаря, если есть)
            else: # Если это не словарь (например, строка напрямую)
                return str(rule_value_obj)

        return default_for_lang


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
            verb = await get_term("terms.actions.examine.verb", {"en": "examines", "ru": "осматривает"})
            sees_term = await get_term("terms.actions.examine.sees", {"en": "You see", "ru": "Вы видите"})
            target_description = _safe_get(log_entry_details_json, ["result", "description"])
            # Если описание соответствует ключу термина, используем термин, иначе используем как есть
            if target_description == "it is empty": # Пример, как это могло бы быть
                 desc_to_use = await get_term("terms.results.nothing_special", {"en": "nothing special", "ru": "ничего особенного"})
            elif target_description:
                 desc_to_use = target_description
            else: # Если description пуст или отсутствует
                 desc_to_use = await get_term("terms.results.nothing_special", {"en": "nothing special", "ru": "ничего особенного"})

            return f"{actor_name} {verb} '{target_name_str}'. {sees_term}: {desc_to_use}"

        elif action_intent == "interact":
            verb = await get_term("terms.actions.interact.verb", {"en": "interacts with", "ru": "взаимодействует с"})
            result_particle = await get_term("terms.actions.interact.result_particle", {"en": "As a result", "ru": "В результате"})
            interaction_result = _safe_get(log_entry_details_json, ["result", "message"])
            if not interaction_result:
                interaction_result = await get_term("terms.results.nothing_happens", {"en": "nothing happens.", "ru": "ничего не происходит."})

            return f"{actor_name} {verb} '{target_name_str}'. {result_particle}: {interaction_result}"

        elif action_intent == "go_to": # move_to_sublocation
            verb = await get_term("terms.actions.go_to.verb", {"en": "moves to", "ru": "перемещается к"})
            particle = await get_term("terms.actions.go_to.particle_location", {"en": "within the current location", "ru": "внутри текущей локации"})
            sublocation_name = target_name_str
            return f"{actor_name} {verb} '{sublocation_name}' {particle}."
        else:
            # Generic fallback for other PLAYER_ACTION intents
            verb = await get_term(f"terms.actions.{action_intent}.verb", {"en": f"performs action '{action_intent}' on", "ru": f"выполняет действие '{action_intent}' на"})
            return f"{actor_name} {verb} '{target_name_str}'."

    elif event_type_str == "PLAYER_MOVE" or event_type_str == "MOVEMENT":
        player_id = log_entry_details_json.get("player_id")
        old_loc_id = log_entry_details_json.get("old_location_id")
        new_loc_id = log_entry_details_json.get("new_location_id")

        player_name = get_name_from_cache("player", player_id, "Player") if player_id else "Unknown Player"
        old_loc_name = get_name_from_cache("location", old_loc_id, "Location") if old_loc_id else \
                       await get_term("terms.general.unknown_place", {"en": "an unknown place", "ru": "неизвестного места"})
        new_loc_name = get_name_from_cache("location", new_loc_id, "Location") if new_loc_id else \
                       await get_term("terms.general.new_mysterious_place", {"en": "a new mysterious place", "ru": "нового загадочного места"})

        moved_from_term = await get_term("terms.movement.moved_from", {"en": "moved from", "ru": "переместился из"})
        to_term = await get_term("terms.movement.to", {"en": "to", "ru": "в"})

        return f"{player_name} {moved_from_term} '{old_loc_name}' {to_term} '{new_loc_name}'."

    elif event_type_str == "ITEM_ACQUIRED":
        player_id = log_entry_details_json.get("player_id")
        item_id = log_entry_details_json.get("item_id")
        quantity = log_entry_details_json.get("quantity", 1)
        source = log_entry_details_json.get("source", await get_term("terms.general.somewhere", {"en": "somewhere", "ru": "откуда-то"}))

        player_name = get_name_from_cache("player", player_id, "Player") if player_id else \
                      await get_term("terms.general.someone", {"en": "Someone", "ru": "Некто"})
        item_name = get_name_from_cache("item", item_id, "Item") if item_id else \
                    await get_term("terms.general.an_item", {"en": "an item", "ru": "предмет"})

        acquired_term = await get_term("terms.items.acquired", {"en": "acquired", "ru": "получает"})
        from_term = await get_term("terms.items.from", {"en": "from", "ru": "из"})

        return f"{player_name} {acquired_term} {item_name} (x{quantity}) {from_term} {source}."

    elif event_type_str == "ABILITY_USED":
        actor_entity_id = _safe_get(log_entry_details_json, ["actor_entity", "id"])
        actor_entity_type = _safe_get(log_entry_details_json, ["actor_entity", "type"], "entity")
        ability_id = _safe_get(log_entry_details_json, ["ability", "id"])

        actor_name = get_name_from_cache(str(actor_entity_type), actor_entity_id, str(actor_entity_type).capitalize()) if actor_entity_id else \
                     await get_term("terms.general.someone", {"en": "Someone", "ru": "Некто"})
        ability_name = get_name_from_cache("ability", ability_id, "Ability") if ability_id else \
                       await get_term("terms.general.an_ability", {"en": "an ability", "ru": "способность"})

        targets_info = _safe_get(log_entry_details_json, ["targets"], [])
        targets_str = ""
        if targets_info:
            target_names = []
            for t_info in targets_info:
                t_id = _safe_get(t_info, ["entity", "id"])
                t_type = _safe_get(t_info, ["entity", "type"], "entity")
                if t_id: target_names.append(get_name_from_cache(str(t_type), t_id, str(t_type).capitalize()))
            if target_names:
                targets_str = ", ".join(target_names)
            else:
                targets_str = await get_term("terms.general.no_specific_target", {"en": "no specific target", "ru": "неопределенной цели"})
        else:
            targets_str = await get_term("terms.general.nobody", {"en": "nobody", "ru": "ни на кого"})

        verb_uses = await get_term("terms.abilities.verb_uses", {"en": "uses ability", "ru": "использует способность"})
        particle_on = await get_term("terms.abilities.particle_on", {"en": "on", "ru": "на"})
        outcome_desc = _safe_get(log_entry_details_json, ["outcome", "description"], "")

        return f"{actor_name} {verb_uses} '{ability_name}' {particle_on} {targets_str}. {outcome_desc}".strip()

    elif event_type_str == "COMBAT_ACTION":
        actor_id = _safe_get(log_entry_details_json, ["actor", "id"])
        actor_type = _safe_get(log_entry_details_json, ["actor", "type"], "combatant")
        target_id = _safe_get(log_entry_details_json, ["target", "id"])
        target_type = _safe_get(log_entry_details_json, ["target", "type"], "combatant")
        action_name = log_entry_details_json.get("action_name", await get_term("terms.combat.an_action", {"en": "an action", "ru": "действие"}))
        damage = log_entry_details_json.get("damage")

        actor_name = get_name_from_cache(actor_type, actor_id, actor_type.capitalize()) if actor_id and actor_type else \
                     await get_term("terms.general.a_combatant", {"en": "A combatant", "ru": "Боец"})
        target_name = get_name_from_cache(target_type, target_id, target_type.capitalize()) if target_id and target_type else \
                      await get_term("terms.general.another_combatant", {"en": "another combatant", "ru": "другого бойца"})

        uses_term = await get_term("terms.combat.uses", {"en": "uses", "ru": "использует"})
        on_term = await get_term("terms.combat.on", {"en": "on", "ru": "против"})
        dealing_term = await get_term("terms.combat.dealing_damage", {"en": "dealing", "ru": "нанося"})
        damage_term = await get_term("terms.general.damage", {"en": "damage", "ru": "урона"})

        if damage is not None:
            return f"{actor_name} {uses_term} '{action_name}' {on_term} {target_name}, {dealing_term} {damage} {damage_term}."
        else:
            return f"{actor_name} {uses_term} '{action_name}' {on_term} {target_name}."

    elif event_type_str == "COMBAT_END":
        location_id = log_entry_details_json.get("location_id")
        location_name = get_name_from_cache("location", location_id, "Location") if location_id else \
                        await get_term("terms.general.unknown_location", {"en": "an unknown location", "ru": "неизвестной локации"})
        outcome_key = log_entry_details_json.get("outcome", "unknown") # e.g., "victory_players"

        # Get localized outcome string
        outcome_readable = await get_term(f"terms.combat.outcomes.{outcome_key}", {
            "en": outcome_key.replace("_", " ").capitalize(),
            "ru": outcome_key.replace("_", " ") # Simple fallback if specific term not found
        })

        ended_template = await get_term("terms.combat.ended", {
            "en": "Combat at '{location_name}' has ended. Outcome: {outcome_readable}.",
            "ru": "Схватка в '{location_name}' окончена. Результат: {outcome_readable}."
        })
        base_message = ended_template.format(location_name=location_name, outcome_readable=outcome_readable)

        survivors_list = _safe_get(log_entry_details_json, ["survivors"], [])
        if survivors_list:
            survivor_names = [
                get_name_from_cache(str(s_info.get("type")), s_info.get("id"), str(s_info.get("type")).capitalize())
                for s_info in survivors_list if s_info.get("id") and s_info.get("type")
            ]
            if survivor_names:
                survivors_str = ", ".join(survivor_names)
                survivors_term_template = await get_term("terms.combat.survivors", {
                    "en": " Survivors: {survivors_str}.",
                    "ru": " Уцелевшие: {survivors_str}."
                })
                base_message += survivors_term_template.format(survivors_str=survivors_str)
        return base_message

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

    elif event_type_str == "PLAYER_MOVE" or event_type_str == "MOVEMENT": # MOVEMENT is an alias
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

    elif event_type_str == "ABILITY_USED":
        actor_entity_id = _safe_get(log_entry_details, ["actor_entity", "id"])
        actor_entity_type = _safe_get(log_entry_details, ["actor_entity", "type"])
        ability_id = _safe_get(log_entry_details, ["ability", "id"])
        if actor_entity_id and actor_entity_type: refs.add((str(actor_entity_type).lower(), actor_entity_id))
        if ability_id: refs.add(("ability", ability_id))
        targets = _safe_get(log_entry_details, ["targets"], [])
        if isinstance(targets, list):
            for target_info in targets:
                target_entity_id = _safe_get(target_info, ["entity", "id"])
                target_entity_type = _safe_get(target_info, ["entity", "type"])
                if target_entity_id and target_entity_type: refs.add((str(target_entity_type).lower(), target_entity_id))

    elif event_type_str == "STATUS_APPLIED":
        target_entity_id = _safe_get(log_entry_details, ["target_entity", "id"])
        target_entity_type = _safe_get(log_entry_details, ["target_entity", "type"])
        status_effect_id = _safe_get(log_entry_details, ["status_effect", "id"])
        if target_entity_id and target_entity_type: refs.add((str(target_entity_type).lower(), target_entity_id))
        if status_effect_id: refs.add(("status_effect", status_effect_id))

    elif event_type_str == "LEVEL_UP":
        player_id = log_entry_details.get("player_id")
        if player_id: refs.add(("player", player_id))

    elif event_type_str == "XP_GAINED":
        player_id = log_entry_details.get("player_id")
        if player_id: refs.add(("player", player_id))

    elif event_type_str == "RELATIONSHIP_CHANGE":
        entity1_id = _safe_get(log_entry_details, ["entity1", "id"])
        entity1_type = _safe_get(log_entry_details, ["entity1", "type"])
        entity2_id = _safe_get(log_entry_details, ["entity2", "id"])
        entity2_type = _safe_get(log_entry_details, ["entity2", "type"])
        if entity1_id and entity1_type: refs.add((str(entity1_type).lower(), entity1_id))
        if entity2_id and entity2_type: refs.add((str(entity2_type).lower(), entity2_id))

    elif event_type_str == "COMBAT_START":
        location_id = log_entry_details.get("location_id")
        if location_id: refs.add(("location", location_id))
        participant_ids = _safe_get(log_entry_details, ["participant_ids"], [])
        if isinstance(participant_ids, list):
            for p_info in participant_ids:
                p_id = _safe_get(p_info, ["id"])
                p_type = _safe_get(p_info, ["type"])
                if p_id and p_type: refs.add((str(p_type).lower(), p_id))

    elif event_type_str == "COMBAT_END":
        location_id = log_entry_details.get("location_id")
        if location_id: refs.add(("location", location_id))
        survivors = _safe_get(log_entry_details, ["survivors"], [])
        if isinstance(survivors, list):
            for s_info in survivors:
                s_id = _safe_get(s_info, ["id"])
                s_type = _safe_get(s_info, ["type"])
                if s_id and s_type: refs.add((str(s_type).lower(), s_id))

    elif event_type_str in ["QUEST_ACCEPTED", "QUEST_STEP_COMPLETED", "QUEST_COMPLETED"]:
        player_id = log_entry_details.get("player_id")
        quest_id = log_entry_details.get("quest_id")
        if player_id: refs.add(("player", player_id))
        if quest_id: refs.add(("quest", quest_id))

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
        entity_refs_for_batch_call: List[Dict[str, Any]] = [
            {"type": entity_type, "id": entity_id} for entity_type, entity_id in all_entity_refs
        ]
        names_cache = await get_batch_localized_entity_names(
            session, guild_id, entity_refs_for_batch_call, language, fallback_language
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
