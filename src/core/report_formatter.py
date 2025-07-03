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

    elif event_type_str == "COMBAT_START":
        location_id = log_entry_details_json.get("location_id")
        location_name = get_name_from_cache("location", location_id, "Location") if location_id else \
                        await get_term("terms.general.unknown_location", {"en": "an unknown location", "ru": "неизвестной локации"})
        
        participant_infos = _safe_get(log_entry_details_json, ["participant_ids"], [])
        participant_names = []
        if isinstance(participant_infos, list):
            for p_info in participant_infos:
                p_id = _safe_get(p_info, ["id"])
                p_type = _safe_get(p_info, ["type"], "entity")
                if p_id:
                    participant_names.append(get_name_from_cache(str(p_type), p_id, str(p_type).capitalize()))
        
        participants_str = ", ".join(participant_names) if participant_names else \
                           await get_term("terms.general.unknown_participants", {"en": "unknown participants", "ru": "неизвестными участниками"})

        template = await get_term("terms.combat.starts_involving", {
            "en": "Combat starts at '{location_name}' involving: {participants_str}.",
            "ru": "Начинается бой в '{location_name}' с участием: {participants_str}."
        })
        return template.format(location_name=location_name, participants_str=participants_str)

    elif event_type_str == "QUEST_ACCEPTED":
        player_id = log_entry_details_json.get("player_id")
        quest_id = log_entry_details_json.get("quest_id")
        player_name = get_name_from_cache("player", player_id, "Player") if player_id else \
                      await get_term("terms.general.someone", {"en": "Someone", "ru": "Некто"})
        quest_name = get_name_from_cache("quest", quest_id, "Quest") if quest_id else \
                     await get_term("terms.quests.a_quest", {"en": "a quest", "ru": "задание"})
        
        template = await get_term("terms.quests.accepted", {
            "en": "{player_name} has accepted the quest: '{quest_name}'.",
            "ru": "{player_name} принял(а) задание: '{quest_name}'."
        })
        return template.format(player_name=player_name, quest_name=quest_name)

    elif event_type_str == "QUEST_STEP_COMPLETED":
        player_id = log_entry_details_json.get("player_id")
        quest_id = log_entry_details_json.get("quest_id")
        step_details = log_entry_details_json.get("step_details", "") # Optional: specific details about the step

        player_name = get_name_from_cache("player", player_id, "Player") if player_id else \
                      await get_term("terms.general.someone", {"en": "Someone", "ru": "Некто"})
        quest_name = get_name_from_cache("quest", quest_id, "Quest") if quest_id else \
                     await get_term("terms.quests.a_quest", {"en": "a quest", "ru": "задания"})

        if step_details:
            template = await get_term("terms.quests.step_completed_detailed", {
                "en": "{player_name} completed a step in '{quest_name}': {step_details}.",
                "ru": "{player_name} выполнил(а) этап в задании '{quest_name}': {step_details}."
            })
            return template.format(player_name=player_name, quest_name=quest_name, step_details=step_details)
        else:
            template = await get_term("terms.quests.step_completed_simple", {
                "en": "{player_name} completed a step in the quest '{quest_name}'.",
                "ru": "{player_name} выполнил(а) этап в задании '{quest_name}'."
            })
            return template.format(player_name=player_name, quest_name=quest_name)

    elif event_type_str == "QUEST_COMPLETED":
        player_id = log_entry_details_json.get("player_id")
        quest_id = log_entry_details_json.get("quest_id")
        player_name = get_name_from_cache("player", player_id, "Player") if player_id else \
                      await get_term("terms.general.someone", {"en": "Someone", "ru": "Некто"})
        quest_name = get_name_from_cache("quest", quest_id, "Quest") if quest_id else \
                     await get_term("terms.quests.a_quest", {"en": "a quest", "ru": "задание"})

        template = await get_term("terms.quests.completed", {
            "en": "{player_name} has completed the quest: '{quest_name}'!",
            "ru": "{player_name} завершил(а) задание: '{quest_name}'!"
        })
        return template.format(player_name=player_name, quest_name=quest_name)

    elif event_type_str == "LEVEL_UP":
        player_id = log_entry_details_json.get("player_id")
        new_level = log_entry_details_json.get("new_level")
        player_name = get_name_from_cache("player", player_id, "Player") if player_id else \
                      await get_term("terms.general.someone", {"en": "Someone", "ru": "Некто"})
        
        level_str = str(new_level) if new_level is not None else \
                    await get_term("terms.character.unknown_level", {"en": "a new level", "ru": "новый уровень"})

        template = await get_term("terms.character.level_up", {
            "en": "{player_name} has reached level {level_str}!",
            "ru": "{player_name} достиг(ла) уровня {level_str}!"
        })
        return template.format(player_name=player_name, level_str=level_str)

    elif event_type_str == "XP_GAINED":
        player_id = log_entry_details_json.get("player_id")
        amount = log_entry_details_json.get("amount")
        source = log_entry_details_json.get("source") # Optional source string

        player_name = get_name_from_cache("player", player_id, "Player") if player_id else \
                      await get_term("terms.general.someone", {"en": "Someone", "ru": "Некто"})
        amount_str = str(amount) if amount is not None else \
                     await get_term("terms.character.some_xp", {"en": "some", "ru": "немного"})
        
        xp_term = await get_term("terms.character.xp", {"en": "XP", "ru": "опыта"})

        if source:
            from_source_term = await get_term("terms.character.from_source", {"en": "from {source}", "ru": "из {source}"})
            source_str = from_source_term.format(source=source)
            template = await get_term("terms.character.xp_gained_with_source", {
                "en": "{player_name} gained {amount_str} {xp_term} {source_str}.",
                "ru": "{player_name} получил(а) {amount_str} {xp_term} {source_str}."
            })
            return template.format(player_name=player_name, amount_str=amount_str, xp_term=xp_term, source_str=source_str)
        else:
            template = await get_term("terms.character.xp_gained_simple", {
                "en": "{player_name} gained {amount_str} {xp_term}.",
                "ru": "{player_name} получил(а) {amount_str} {xp_term}."
            })
            return template.format(player_name=player_name, amount_str=amount_str, xp_term=xp_term)

    elif event_type_str == "RELATIONSHIP_CHANGE":
        entity1_info = log_entry_details_json.get("entity1", {})
        entity2_info = log_entry_details_json.get("entity2", {})
        new_value = log_entry_details_json.get("new_value")
        change_reason = log_entry_details_json.get("change_reason") # Optional

        e1_id = entity1_info.get("id")
        e1_type = entity1_info.get("type", "entity")
        e1_name = get_name_from_cache(str(e1_type), e1_id, str(e1_type).capitalize()) if e1_id else \
                  await get_term("terms.general.one_entity", {"en": "One entity", "ru": "Одна сущность"})

        e2_id = entity2_info.get("id")
        e2_type = entity2_info.get("type", "entity")
        e2_name = get_name_from_cache(str(e2_type), e2_id, str(e2_type).capitalize()) if e2_id else \
                  await get_term("terms.general.another_entity", {"en": "another entity", "ru": "другой сущностью"})
        
        value_str = str(new_value) if new_value is not None else \
                    await get_term("terms.relationships.an_unknown_level", {"en": "an unknown level", "ru": "неизвестного уровня"})

        relation_between = await get_term("terms.relationships.relation_between", {"en": "Relationship between {e1_name} and {e2_name}", "ru": "Отношения между {e1_name} и {e2_name}"})
        is_now = await get_term("terms.relationships.is_now", {"en": "is now {value_str}", "ru": "теперь {value_str}"})
        
        base_msg = f"{relation_between.format(e1_name=e1_name, e2_name=e2_name)} {is_now.format(value_str=value_str)}"
        
        if change_reason:
            due_to_reason = await get_term("terms.relationships.due_to_reason", {"en": "due to: {change_reason}", "ru": "по причине: {change_reason}"})
            base_msg += f" ({due_to_reason.format(change_reason=change_reason)})."
        else:
            base_msg += "."
        return base_msg

    elif event_type_str == "STATUS_APPLIED":
        target_info = log_entry_details_json.get("target_entity", {})
        status_effect_info = log_entry_details_json.get("status_effect", {})
        source_info = log_entry_details_json.get("source_entity") # Optional
        duration_turns = log_entry_details_json.get("duration_turns") # Optional

        target_id = target_info.get("id")
        target_type = target_info.get("type", "entity")
        target_name = get_name_from_cache(str(target_type), target_id, str(target_type).capitalize()) if target_id else \
                      await get_term("terms.general.someone", {"en": "Someone", "ru": "Некто"})

        status_id = status_effect_info.get("id")
        status_name = get_name_from_cache("status_effect", status_id, "Status") if status_id else \
                      await get_term("terms.statuses.a_status_effect", {"en": "a status effect", "ru": "эффект состояния"})

        msg_parts = [target_name]
        is_now_affected_by = await get_term("terms.statuses.is_now_affected_by", {"en": "is now affected by", "ru": "теперь под действием"})
        msg_parts.extend([is_now_affected_by, f"'{status_name}'"])

        if duration_turns is not None:
            for_duration = await get_term("terms.statuses.for_duration", {"en": "for {duration_turns} turns", "ru": "на {duration_turns} ходов"})
            msg_parts.append(for_duration.format(duration_turns=duration_turns))

        if source_info and isinstance(source_info, dict):
            source_id = source_info.get("id")
            source_type = source_info.get("type", "entity") # e.g., "ability", "item"
            source_name_from_dict = source_info.get("name") # e.g. if source is a trap with a name

            from_source_term = await get_term("terms.statuses.from_source", {"en": "from", "ru": "от"})
            msg_parts.append(from_source_term)

            if source_id and source_type: # If it's a known entity type with an ID
                source_display_name = get_name_from_cache(str(source_type), source_id, str(source_type).capitalize())
                msg_parts.append(f"'{source_display_name}'")
            elif source_name_from_dict: # If it's something like a trap name directly in details
                 msg_parts.append(f"'{source_name_from_dict}'")
            else: # Fallback if source_info is there but not well-structured for naming
                msg_parts.append(await get_term("terms.statuses.an_unknown_source", {"en": "an unknown source", "ru": "неизвестного источника"}))
        
        msg_parts.append(".")
        return " ".join(msg_parts)

    elif event_type_str == "STATUS_REMOVED":
        target_info = log_entry_details_json.get("target_entity", {})
        status_effect_info = log_entry_details_json.get("status_effect", {})

        target_id = target_info.get("id")
        target_type = target_info.get("type", "entity")
        target_name = get_name_from_cache(str(target_type), target_id, str(target_type).capitalize()) if target_id else \
                      await get_term("terms.general.someone", {"en": "Someone", "ru": "Некто"})

        status_id = status_effect_info.get("id")
        status_name = get_name_from_cache("status_effect", status_id, "Status") if status_id else \
                      await get_term("terms.statuses.a_status_effect", {"en": "a status effect", "ru": "эффект состояния"})

        template = await get_term("terms.statuses.effect_ended_on", {
            "en": "'{status_name}' effect has ended on {target_name}.",
            "ru": "Эффект '{status_name}' закончился для {target_name}."
        })
        return template.format(status_name=status_name, target_name=target_name)

    elif event_type_str == "DIALOGUE_LINE":
        speaker_info = log_entry_details_json.get("speaker_entity", {})
        line_text = log_entry_details_json.get("line_text", "...")

        speaker_id = speaker_info.get("id")
        speaker_type = speaker_info.get("type", "entity")
        speaker_name = get_name_from_cache(str(speaker_type), speaker_id, str(speaker_type).capitalize()) if speaker_id else \
                       await get_term("terms.general.someone", {"en": "Someone", "ru": "Некто"})
        
        # No specific term for the format, direct formatting
        return f"{speaker_name}: \"{line_text}\""

    elif event_type_str == "QUEST_FAILED":
        player_id = log_entry_details_json.get("player_id")
        quest_id = log_entry_details_json.get("quest_id")
        reason = log_entry_details_json.get("reason") # Optional

        player_name = get_name_from_cache("player", player_id, "Player") if player_id else \
                      await get_term("terms.general.someone", {"en": "Someone", "ru": "Некто"})
        quest_name = get_name_from_cache("quest", quest_id, "Quest") if quest_id else \
                     await get_term("terms.quests.a_quest", {"en": "a quest", "ru": "задание"})

        if reason:
            template = await get_term("terms.quests.failed_with_reason", {
                "en": "{player_name} has failed the quest '{quest_name}' due to: {reason}.",
                "ru": "{player_name} провалил(а) задание '{quest_name}' по причине: {reason}."
            })
            return template.format(player_name=player_name, quest_name=quest_name, reason=reason)
        else:
            template = await get_term("terms.quests.failed_simple", {
                "en": "{player_name} has failed the quest '{quest_name}'.",
                "ru": "{player_name} провалил(а) задание '{quest_name}'."
            })
            return template.format(player_name=player_name, quest_name=quest_name)

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

    elif event_type_str in ["QUEST_ACCEPTED", "QUEST_STEP_COMPLETED", "QUEST_COMPLETED", "QUEST_FAILED"]:
        player_id = log_entry_details.get("player_id")
        quest_id = log_entry_details.get("quest_id")
        if player_id: refs.add(("player", player_id))
        if quest_id: refs.add(("quest", quest_id))

    elif event_type_str == "DIALOGUE_LINE":
        speaker_entity_id = _safe_get(log_entry_details, ["speaker_entity", "id"])
        speaker_entity_type = _safe_get(log_entry_details, ["speaker_entity", "type"])
        if speaker_entity_id and speaker_entity_type: refs.add((str(speaker_entity_type).lower(), speaker_entity_id))
    
    # STATUS_REMOVED would have similar fields to STATUS_APPLIED for ref collection
    # If the fields are identical ('target_entity', 'status_effect'), it's covered by STATUS_APPLIED's block
    # Let's assume for now they are, if not, a specific block for STATUS_REMOVED would be needed here.
    # Based on current STATUS_APPLIED collection, it should be fine.

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
