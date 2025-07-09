# src/core/report_formatter.py
import logging
from typing import List, Dict, Any, Union, Tuple, Set, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from .localization_utils import get_batch_localized_entity_names
from .rules import get_rule
from ..models.story_log import StoryLog
from ..models.enums import EventType

logger = logging.getLogger(__name__)

async def get_term(
    session: AsyncSession,
    guild_id: Optional[int],
    language: str,
    term_key_base: str,
    default_text_map: Dict[str, str]
) -> str:
    full_term_key = f"{term_key_base}_{language}"
    primary_fallback_language = "en"
    rule_value_obj = None
    if guild_id is not None:
        rule_value_obj = await get_rule(session, guild_id, full_term_key, default=None)
    if rule_value_obj:
        if isinstance(rule_value_obj, dict):
            if language in rule_value_obj and rule_value_obj[language]:
                return str(rule_value_obj[language])
            if primary_fallback_language in rule_value_obj and rule_value_obj[primary_fallback_language]:
                logger.debug(f"Term '{term_key_base}' (guild {guild_id}) found in RuleConfig using primary fallback '{primary_fallback_language}'.")
                return str(rule_value_obj[primary_fallback_language])
        elif isinstance(rule_value_obj, str) and rule_value_obj:
            return rule_value_obj
    if language in default_text_map and default_text_map[language]:
        logger.debug(f"Term '{term_key_base}' (guild {guild_id}) not in RuleConfig or specific lang, using default_text_map for '{language}'.")
        return default_text_map[language]
    if primary_fallback_language in default_text_map and default_text_map[primary_fallback_language]:
        logger.debug(f"Term '{term_key_base}' (guild {guild_id}) not in RuleConfig/default_text_map for '{language}', using default_text_map for primary fallback '{primary_fallback_language}'.")
        return default_text_map[primary_fallback_language]
    if default_text_map:
        first_value = next(iter(default_text_map.values()), None)
        if first_value:
            logger.debug(f"Term '{term_key_base}' (guild {guild_id}) falling back to first available value in default_text_map.")
            return first_value
    logger.warning(f"Term '{term_key_base}' (guild {guild_id}) could not be resolved for language '{language}' or fallbacks.")
    return f"[{term_key_base}_{language}?]"

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
    session: AsyncSession,
    log_entry_details_json: Dict[str, Any],
    language: str,
    names_cache: Dict[Tuple[str, int], str]
) -> str:
    guild_id = log_entry_details_json.get("guild_id")
    event_type_str = str(log_entry_details_json.get("event_type", "UNKNOWN_EVENT")).upper()

    if not guild_id:
        logger.warning("_format_log_entry_with_names_cache: 'guild_id' not found.")
        return "Error: Missing guild information in log entry (formatter)."
    if not event_type_str or event_type_str == "UNKNOWN_EVENT":
        logger.warning(f"_format_log_entry_with_names_cache: 'event_type' missing for guild {guild_id}.")
        return f"Error: Missing event type in log entry (guild {guild_id})."

    def get_name_from_cache(entity_type: str, entity_id: Optional[int], default_prefix: str = "Entity") -> str:
        if entity_id is None:
            return f"[{default_prefix} ID: None (Invalid)]"
        return names_cache.get((entity_type.lower(), entity_id), f"[{default_prefix} ID: {entity_id} (Not in Cache?)]")

    fallback_message = ""
    if language == "ru":
        fallback_message = f"Произошло событие типа '{event_type_str}'. Детали: {str(log_entry_details_json)[:150]}..."
    else:
        fallback_message = f"Event of type '{event_type_str}' occurred. Details: {str(log_entry_details_json)[:150]}..."

    if event_type_str == EventType.PLAYER_ACTION.value.upper():
        actor_id: Optional[int] = _safe_get(log_entry_details_json, ["actor", "id"])
        actor_type: str = _safe_get(log_entry_details_json, ["actor", "type"], "player")
        actor_name = get_name_from_cache(actor_type, actor_id, "Player")
        action_data = _safe_get(log_entry_details_json, ["action"], {})
        action_intent = str(action_data.get("intent", "unknown")).lower()
        action_entities = action_data.get("entities", [])
        target_desc = _safe_get(action_entities, [0, "name"], "something") if action_entities else "something"
        result_data = _safe_get(log_entry_details_json, ["result"], {})
        result_desc = result_data.get("description", "")
        if action_intent == "examine":
            verb = await get_term(session, guild_id, language, "terms.actions.examine.verb", {"en": "examines", "ru": "осматривает"})
            sees_term = await get_term(session, guild_id, language, "terms.actions.examine.sees", {"en": "Observations", "ru": "Вы видите"})
            if action_entities:
                target_name_from_entity = _safe_get(action_entities, [0, "name"])
                target_static_id = _safe_get(action_entities, [0, "static_id"])
                target_id_from_entity = _safe_get(action_entities, [0, "id"])
                target_type_from_entity = _safe_get(action_entities, [0, "type"], "object")
                if target_id_from_entity and target_type_from_entity:
                    target_desc = get_name_from_cache(target_type_from_entity, target_id_from_entity, target_type_from_entity.capitalize())
                elif target_static_id:
                    target_desc = target_name_from_entity or target_static_id
                elif target_name_from_entity:
                    target_desc = target_name_from_entity
            if not result_desc:
                result_desc = await get_term(session, guild_id, language, "terms.results.nothing_special", {"en": "nothing special.", "ru": "ничего особенного."})
            return f"{actor_name} {verb} '{target_desc}'. {sees_term}: {result_desc}"
        return f"{actor_name} performs action '{action_intent}' on '{target_desc}'. Result: {result_desc}"

    elif event_type_str == EventType.MOVEMENT.value.upper():
        player_id = log_entry_details_json.get("player_id")
        old_loc_id = log_entry_details_json.get("old_location_id")
        new_loc_id = log_entry_details_json.get("new_location_id")
        player_name = get_name_from_cache("player", player_id, "Player") if player_id else "Someone"
        old_loc_name = get_name_from_cache("location", old_loc_id, "an unknown place") if old_loc_id else "an unknown place"
        new_loc_name = get_name_from_cache("location", new_loc_id, "another unknown place") if new_loc_id else "another unknown place"
        template = await get_term(session, guild_id, language, "terms.movement.player_moves", {"en": "{player_name} moves from '{old_loc_name}' to '{new_loc_name}'.", "ru": "{player_name} перемещается из '{old_loc_name}' в '{new_loc_name}'."})
        return template.format(player_name=player_name, old_loc_name=old_loc_name, new_loc_name=new_loc_name)

    elif event_type_str == EventType.ITEM_ACQUIRED.value.upper():
        player_id = log_entry_details_json.get("player_id")
        item_id = log_entry_details_json.get("item_id")
        source = log_entry_details_json.get("source", "somewhere")
        quantity = log_entry_details_json.get("quantity", 1)
        player_name = get_name_from_cache("player", player_id, "Player") if player_id else "Someone"
        item_name = get_name_from_cache("item", item_id, "an item") if item_id else "an item"
        if source == "loot":
            source_str = await get_term(session, guild_id, language, "terms.items.source_loot", {"en": "as loot", "ru": "в качестве добычи"})
        elif source == "quest_reward":
            source_str = await get_term(session, guild_id, language, "terms.items.source_quest_reward", {"en": "as a quest reward", "ru": "в качестве награды за задание"})
        else:
            source_str = await get_term(session, guild_id, language, "terms.items.source_generic", {"en": "from {source_name}", "ru": "из {source_name}"})
            source_str = source_str.format(source_name=source)
        template = await get_term(session, guild_id, language, "terms.items.acquired_item", {"en": "{player_name} acquired '{item_name}' (x{quantity}) {source_str}.", "ru": "{player_name} получил(а) '{item_name}' (x{quantity}) {source_str}."})
        return template.format(player_name=player_name, item_name=item_name, quantity=quantity, source_str=source_str)

    elif event_type_str == EventType.COMBAT_ACTION.value.upper():
        actor_id = _safe_get(log_entry_details_json, ["actor", "id"])
        actor_type = _safe_get(log_entry_details_json, ["actor", "type"], "entity")
        actor_name = get_name_from_cache(actor_type, actor_id, "Actor")
        target_id = _safe_get(log_entry_details_json, ["target", "id"])
        target_type = _safe_get(log_entry_details_json, ["target", "type"], "entity")
        target_name = get_name_from_cache(target_type, target_id, "Target")
        action_name = log_entry_details_json.get("action_name", "an action")
        damage = log_entry_details_json.get("damage")
        uses_term = await get_term(session, guild_id, language, "terms.combat.uses", {"en": "uses", "ru": "использует"})
        on_term = await get_term(session, guild_id, language, "terms.combat.on", {"en": "on", "ru": "против"})
        msg = f"{actor_name} {uses_term} '{action_name}' {on_term} {target_name}"
        if damage is not None and damage > 0:
            dealing_term = await get_term(session, guild_id, language, "terms.combat.dealing_damage", {"en": "dealing", "ru": "нанося"})
            damage_term_val = await get_term(session, guild_id, language, "terms.general.damage", {"en": "damage", "ru": "урона"})
            msg += f", {dealing_term} {damage} {damage_term_val}."
        else:
            msg += "."
        check_res_dict = log_entry_details_json.get("check_result")
        if isinstance(check_res_dict, dict):
            cr_roll = check_res_dict.get("roll_used", "N/A")
            cr_mod = check_res_dict.get("total_modifier", "N/A")
            cr_final = check_res_dict.get("final_value", "N/A")
            cr_dc = check_res_dict.get("difficulty_class", "N/A")
            roll_t = await get_term(session, guild_id, language, "terms.checks.roll", {"en":"Roll", "ru":"Бросок"})
            mod_t = await get_term(session, guild_id, language, "terms.checks.modifier", {"en":"Mod", "ru":"Мод."})
            total_t = await get_term(session, guild_id, language, "terms.checks.total", {"en":"Total", "ru":"Итог"})
            vs_dc_t = await get_term(session, guild_id, language, "terms.checks.vs_dc", {"en":"vs DC", "ru":"против СЛ"})
            msg += f" ({roll_t}: {cr_roll}, {mod_t}: {cr_mod}, {total_t}: {cr_final} {vs_dc_t}: {cr_dc})"
            mod_details = check_res_dict.get("modifier_details", [])
            if mod_details:
                details_descs = [f"{md.get('description', 'Unknown Bonus')} ({'+' if md.get('value', 0) >= 0 else ''}{md.get('value', 0)})" for md in mod_details]
                if details_descs:
                    bonuses_t = await get_term(session, guild_id, language, "terms.checks.bonuses_penalties", {"en":"Bonuses/Penalties", "ru":"Бонусы/Штрафы"})
                    msg += f" [{bonuses_t}: {'; '.join(details_descs)}]"
        return msg

    elif event_type_str == EventType.NPC_ACTION.value.upper():
        actor_id = _safe_get(log_entry_details_json, ["actor", "id"])
        actor_type = _safe_get(log_entry_details_json, ["actor", "type"], "npc")
        actor_name = get_name_from_cache(actor_type, actor_id, "An NPC")
        action_data = _safe_get(log_entry_details_json, ["action"], {})
        action_intent = str(action_data.get("intent", "unknown_intent")).lower()
        action_entities = action_data.get("entities", [])
        target_name_str = _safe_get(action_entities, [0, "name"], "") if action_entities else ""
        result_message = _safe_get(log_entry_details_json, ["result", "message"], "")
        verb_term_default = {"en": f"performs '{action_intent}'", "ru": f"совершает '{action_intent}'"}
        verb_term = await get_term(session, guild_id, language, f"terms.actions.{action_intent}.verb_npc", verb_term_default)

        msg_parts_base = [actor_name, verb_term]
        if target_name_str:
            preposition_term_default = {"en": "on", "ru": "над"}
            preposition_term = await get_term(session, guild_id, language, f"terms.actions.{action_intent}.preposition_npc", default_text_map={})
            if f"preposition_npc_{language}?]" in preposition_term:
                 preposition_term = await get_term(session, guild_id, language, f"terms.actions.{action_intent}.preposition", preposition_term_default)
            msg_parts_base.extend([preposition_term, f"'{target_name_str}'"])

        base_action_msg = " ".join(filter(None, msg_parts_base)).strip()

        final_msg: str
        if result_message:
            if base_action_msg and not base_action_msg.endswith(('.', '!', '?')):
                base_action_msg += "."
            final_msg = f"{base_action_msg} {result_message.strip()}"
            # Remove trailing period from final_msg if result_message did not have it
            # This is to match the test's expectation: "Base. Result" (no period after Result)
            if final_msg.endswith('.') and not result_message.strip().endswith('.'):
                final_msg = final_msg[:-1].strip()
        else:
            final_msg = base_action_msg
            if final_msg and not final_msg.endswith(('.', '!', '?')):
                 final_msg += "."

        return final_msg.strip()

    elif event_type_str == EventType.ITEM_USED.value.upper():
        player_id = log_entry_details_json.get("player_id")
        item_id = log_entry_details_json.get("item_id")
        outcome_desc = log_entry_details_json.get("outcome_description", "")
        target_info = log_entry_details_json.get("target")
        player_name = get_name_from_cache("player", player_id, "Someone")
        item_name = get_name_from_cache("item", item_id, "an item")
        uses_term = await get_term(session, guild_id, language, "terms.items.uses", {"en": "uses", "ru": "использует"})
        msg = f"{player_name} {uses_term} '{item_name}'"
        if target_info and isinstance(target_info, dict):
            target_id = target_info.get("id")
            target_type = target_info.get("type")
            if target_id and target_type:
                target_name_rendered = get_name_from_cache(target_type, target_id, f"target ({target_type} ID {target_id})")
                on_term = await get_term(session, guild_id, language, "terms.items.on", {"en": "on", "ru": "на"})
                msg += f" {on_term} '{target_name_rendered}'"
        msg += "."
        if outcome_desc:
            msg += f" {outcome_desc}"
        return msg.strip()

    elif event_type_str == EventType.ITEM_DROPPED.value.upper():
        player_id = log_entry_details_json.get("player_id")
        item_id = log_entry_details_json.get("item_id")
        quantity = log_entry_details_json.get("quantity", 1)
        player_name = get_name_from_cache("player", player_id, "Someone")
        item_name = get_name_from_cache("item", item_id, "an item")
        drops_term = await get_term(session, guild_id, language, "terms.items.drops", {"en": "drops", "ru": "выбрасывает"})
        return f"{player_name} {drops_term} '{item_name}' (x{quantity})."

    elif event_type_str == EventType.DIALOGUE_START.value.upper():
        player_id = _safe_get(log_entry_details_json, ["player_entity", "id"])
        npc_id = _safe_get(log_entry_details_json, ["npc_entity", "id"])
        player_name = get_name_from_cache("player", player_id, "Player")
        npc_name = get_name_from_cache("npc", npc_id, "NPC")
        template = await get_term(session, guild_id, language, "terms.dialogue.starts_conversation_with", {"en": "{player_name} starts a conversation with {npc_name}.", "ru": "{player_name} начинает разговор с {npc_name}."})
        return template.format(player_name=player_name, npc_name=npc_name)

    elif event_type_str == EventType.DIALOGUE_END.value.upper():
        player_id = _safe_get(log_entry_details_json, ["player_entity", "id"])
        npc_id = _safe_get(log_entry_details_json, ["npc_entity", "id"])
        player_name = get_name_from_cache("player", player_id, "Player")
        npc_name = get_name_from_cache("npc", npc_id, "NPC")
        template = await get_term(session, guild_id, language, "terms.dialogue.ends_conversation_with", {"en": "{player_name} ends the conversation with {npc_name}.", "ru": "{player_name} заканчивает разговор с {npc_name}."})
        return template.format(player_name=player_name, npc_name=npc_name)

    elif event_type_str == EventType.DIALOGUE_LINE.value.upper():
        speaker_id = _safe_get(log_entry_details_json, ["speaker_entity", "id"])
        speaker_type = _safe_get(log_entry_details_json, ["speaker_entity", "type"], "unknown")
        line_text = log_entry_details_json.get("line_text", "...")
        speaker_name = get_name_from_cache(speaker_type, speaker_id, speaker_type.capitalize())
        return f'{speaker_name}: "{line_text}"'

    elif event_type_str == EventType.FACTION_CHANGE.value.upper():
        entity_id = _safe_get(log_entry_details_json, ["entity", "id"])
        entity_type = _safe_get(log_entry_details_json, ["entity", "type"], "entity")
        faction_id = log_entry_details_json.get("faction_id")
        old_s = log_entry_details_json.get("old_standing", "unknown")
        new_s = log_entry_details_json.get("new_standing", "unknown")
        reason = log_entry_details_json.get("reason")
        entity_name = get_name_from_cache(entity_type, entity_id, "An entity")
        faction_name = get_name_from_cache("faction", faction_id, "a faction") if faction_id else "a faction"
        rep_of_t = await get_term(session, guild_id, language, "terms.factions.reputation_of", {"en":"Reputation of", "ru":"Репутация"})
        with_fac_t = await get_term(session, guild_id, language, "terms.factions.with_faction", {"en":"with", "ru":"с"})
        changed_from_t = await get_term(session, guild_id, language, "terms.factions.changed_from", {"en":"changed from", "ru":"изменилась с"})
        to_st_t = await get_term(session, guild_id, language, "terms.factions.to_standing", {"en":"to", "ru":"на"})
        msg = f"{rep_of_t} {entity_name} {with_fac_t} {faction_name} {changed_from_t} {old_s} {to_st_t} {new_s}."
        if reason:
            reason_t = await get_term(session, guild_id, language, "terms.general.reason", {"en":"Reason", "ru":"Причина"})
            msg += f" ({reason_t}: {reason})"
        return msg

    elif event_type_str == EventType.COMBAT_START.value.upper():
        location_id = log_entry_details_json.get("location_id")
        participant_ids_data = log_entry_details_json.get("participant_ids", [])
        location_name = get_name_from_cache("location", location_id, "an unknown location") if location_id else await get_term(session, guild_id, language, "terms.general.unknown_location", {"en":"an unknown location", "ru":"неизвестное место"})
        participant_names = [get_name_from_cache(p_info["type"], p_info["id"], p_info["type"].capitalize()) for p_info in participant_ids_data if isinstance(p_info, dict) and "id" in p_info and "type" in p_info]
        participants_str = ", ".join(participant_names) if participant_names else await get_term(session, guild_id, language, "terms.general.unknown_participants", {"en":"unknown participants", "ru":"неизвестные участники"})
        template = await get_term(session, guild_id, language, "terms.combat.starts_involving", {"en": "Combat starts at '{location_name}' involving: {participants_str}.", "ru": "Начинается бой в '{location_name}' с участием: {participants_str}."})
        return template.format(location_name=location_name, participants_str=participants_str)

    elif event_type_str == EventType.COMBAT_END.value.upper():
        location_id = log_entry_details_json.get("location_id")
        outcome = log_entry_details_json.get("outcome", "unknown")
        survivors_data = log_entry_details_json.get("survivors", [])
        location_name = get_name_from_cache("location", location_id, "an unknown location") if location_id else await get_term(session, guild_id, language, "terms.general.unknown_location", {"en":"an unknown location", "ru":"неизвестное место"})
        outcome_readable_key = f"terms.combat.outcomes.{outcome}"
        outcome_readable_default = outcome.replace("_", " ").capitalize()
        outcome_readable = await get_term(session, guild_id, language, outcome_readable_key, {language: outcome_readable_default, "en": outcome_readable_default})
        ended_template = await get_term(session, guild_id, language, "terms.combat.ended", {"en": "Combat at '{location_name}' has ended. Outcome: {outcome_readable}.", "ru": "Схватка в '{location_name}' окончена. Результат: {outcome_readable}."})
        msg = ended_template.format(location_name=location_name, outcome_readable=outcome_readable)
        if survivors_data:
            survivor_names = [get_name_from_cache(s_info["type"], s_info["id"], s_info["type"].capitalize()) for s_info in survivors_data if isinstance(s_info, dict)]
            if survivor_names:
                survivors_str = ", ".join(survivor_names)
                survivors_template = await get_term(session, guild_id, language, "terms.combat.survivors", {"en": " Survivors: {survivors_str}.", "ru": " Уцелевшие: {survivors_str}."})
                msg += survivors_template.format(survivors_str=survivors_str)
        return msg

    elif event_type_str == EventType.QUEST_ACCEPTED.value.upper():
        player_id = log_entry_details_json.get("player_id")
        quest_id = log_entry_details_json.get("quest_id")
        player_name = get_name_from_cache("player", player_id, "Player")
        quest_name = get_name_from_cache("quest", quest_id, "a quest")
        template = await get_term(session, guild_id, language, "terms.quests.accepted", {"en": "{player_name} has accepted the quest: '{quest_name}'.", "ru": "{player_name} принял(а) задание: '{quest_name}'."})
        return template.format(player_name=player_name, quest_name=quest_name)

    elif event_type_str == EventType.QUEST_STEP_COMPLETED.value.upper():
        player_id = log_entry_details_json.get("player_id")
        quest_id = log_entry_details_json.get("quest_id")
        step_details_text = log_entry_details_json.get("step_details")
        player_name = get_name_from_cache("player", player_id, "Player")
        quest_name = get_name_from_cache("quest", quest_id, "a quest")
        if step_details_text:
            template_key = "terms.quests.step_completed_detailed"
            default_map = {"en": "{player_name} completed a step in '{quest_name}': {step_details}.", "ru": "{player_name} выполнил(а) этап в задании '{quest_name}': {step_details}."}
            template = await get_term(session, guild_id, language, template_key, default_map)
            return template.format(player_name=player_name, quest_name=quest_name, step_details=step_details_text)
        else:
            template_key = "terms.quests.step_completed_simple"
            default_map = {"en": "{player_name} completed a step in the quest '{quest_name}'.", "ru": "{player_name} выполнил(а) этап в задании '{quest_name}'."}
            template = await get_term(session, guild_id, language, template_key, default_map)
            return template.format(player_name=player_name, quest_name=quest_name)

    elif event_type_str == EventType.QUEST_COMPLETED.value.upper():
        player_id = log_entry_details_json.get("player_id")
        quest_id = log_entry_details_json.get("quest_id")
        player_name = get_name_from_cache("player", player_id, "Player")
        quest_name = get_name_from_cache("quest", quest_id, "a quest")
        template = await get_term(session, guild_id, language, "terms.quests.completed", {"en": "{player_name} has completed the quest: '{quest_name}'!", "ru": "{player_name} завершил(а) задание: '{quest_name}'!"})
        return template.format(player_name=player_name, quest_name=quest_name)

    elif event_type_str == EventType.QUEST_FAILED.value.upper():
        player_id = log_entry_details_json.get("player_id")
        quest_id = log_entry_details_json.get("quest_id")
        reason = log_entry_details_json.get("reason")
        player_name = get_name_from_cache("player", player_id, "Player")
        quest_name = get_name_from_cache("quest", quest_id, "a quest")
        if reason:
            template_key = "terms.quests.failed_with_reason"
            default_map = {"en": "{player_name} has failed the quest '{quest_name}' due to: {reason}.", "ru": "{player_name} провалил(а) задание '{quest_name}' по причине: {reason}."}
            template = await get_term(session, guild_id, language, template_key, default_map)
            return template.format(player_name=player_name, quest_name=quest_name, reason=reason)
        else:
            template_key = "terms.quests.failed_simple"
            default_map = {"en": "{player_name} has failed the quest '{quest_name}'.", "ru": "{player_name} провалил(а) задание '{quest_name}'."}
            template = await get_term(session, guild_id, language, template_key, default_map)
            return template.format(player_name=player_name, quest_name=quest_name)

    elif event_type_str == EventType.ABILITY_USED.value.upper():
        actor_id = _safe_get(log_entry_details_json, ["actor_entity", "id"])
        actor_type = _safe_get(log_entry_details_json, ["actor_entity", "type"], "entity")
        actor_name = get_name_from_cache(actor_type, actor_id, "Actor")
        ability_id = _safe_get(log_entry_details_json, ["ability", "id"])
        ability_name = get_name_from_cache("ability", ability_id, "an ability")
        targets_data = _safe_get(log_entry_details_json, ["targets"], [])
        target_names = [get_name_from_cache(t_info["type"], t_info["id"], t_info["type"].capitalize()) for t_info in targets_data if isinstance(t_info, dict) and "id" in t_info and "type" in t_info] if targets_data else []
        outcome_desc = _safe_get(log_entry_details_json, ["outcome", "description"], "")
        verb_uses = await get_term(session, guild_id, language, f"terms.abilities.verb_uses", {"en": "uses ability", "ru": "использует способность"})
        particle_on = await get_term(session, guild_id, language, f"terms.abilities.particle_on", {"en": "on", "ru": "на"})
        msg = f"{actor_name} {verb_uses} '{ability_name}'"
        if target_names:
            msg += f" {particle_on} {', '.join(target_names)}"
        else:
            nobody_term = await get_term(session, guild_id, language, f"terms.general.nobody", {"en": "nobody", "ru": "ни на кого"})
            msg += f" {particle_on} {nobody_term}"
        msg += "."
        if outcome_desc:
            msg += f" {outcome_desc}"
        return msg.strip()

    elif event_type_str == EventType.LEVEL_UP.value.upper():
        player_id = log_entry_details_json.get("player_id")
        new_level = log_entry_details_json.get("new_level")
        player_name = get_name_from_cache("player", player_id, "Player")
        level_str = str(new_level) if new_level is not None else await get_term(session, guild_id, language, "terms.character.unknown_level", {"en":"a new level", "ru":"новый уровень"})
        template = await get_term(session, guild_id, language, "terms.character.level_up", {"en": "{player_name} has reached level {level_str}!", "ru": "{player_name} достиг(ла) уровня {level_str}!"})
        return template.format(player_name=player_name, level_str=level_str)

    elif event_type_str == EventType.XP_GAINED.value.upper():
        player_id = log_entry_details_json.get("player_id")
        amount = log_entry_details_json.get("amount")
        source = log_entry_details_json.get("source")
        player_name = get_name_from_cache("player", player_id, "Player")
        amount_str = str(amount) if amount is not None else await get_term(session, guild_id, language, "terms.character.some_xp", {"en":"some", "ru":"немного"})
        xp_term = await get_term(session, guild_id, language, "terms.character.xp", {"en":"XP", "ru":"опыта"})
        if source:
            source_prefix_template = await get_term(session, guild_id, language, "terms.character.from_source", {"en":"from {source_name}", "ru":"из {source_name}"})
            source_str_rendered = ""
            try:
                source_str_rendered = source_prefix_template.format(source_name=source)
            except KeyError:
                try:
                    source_str_rendered = source_prefix_template.format(source=source)
                    logger.warning(f"Placeholder '{{source_name}}' not found, but '{{source}}' worked for XP_GAINED's from_source. Template: '{source_prefix_template}'")
                except KeyError:
                    logger.warning(f"Placeholders for source not found in source_prefix_template for XP_GAINED. Using raw source. Template: '{source_prefix_template}'")
                    source_str_rendered = str(source)

            template_key = "terms.character.xp_gained_with_source"
            default_map = {"en": "{player_name} gained {amount_str} {xp_term} {source_str}.", "ru": "{player_name} получил(а) {amount_str} {xp_term} {source_str}."}
            template = await get_term(session, guild_id, language, template_key, default_map)
            return template.format(player_name=player_name, amount_str=amount_str, xp_term=xp_term, source_str=source_str_rendered)
        else:
            template_key = "terms.character.xp_gained_simple"
            default_map = {"en": "{player_name} gained {amount_str} {xp_term}.", "ru": "{player_name} получил(а) {amount_str} {xp_term}."}
            template = await get_term(session, guild_id, language, template_key, default_map)
            return template.format(player_name=player_name, amount_str=amount_str, xp_term=xp_term)

    elif event_type_str == EventType.RELATIONSHIP_CHANGE.value.upper():
        e1_id = _safe_get(log_entry_details_json, ["entity1", "id"])
        e1_type = _safe_get(log_entry_details_json, ["entity1", "type"], "entity")
        e2_id = _safe_get(log_entry_details_json, ["entity2", "id"])
        e2_type = _safe_get(log_entry_details_json, ["entity2", "type"], "entity")
        new_value = log_entry_details_json.get("new_value")
        reason = log_entry_details_json.get("change_reason")
        e1_name = get_name_from_cache(e1_type, e1_id, "One entity")
        e2_name = get_name_from_cache(e2_type, e2_id, "Another entity")
        value_str = str(new_value) if new_value is not None else await get_term(session, guild_id, language, "terms.relationships.an_unknown_level", {"en":"an unknown level", "ru":"неизвестного уровня"})
        rel_between_t = await get_term(session, guild_id, language, "terms.relationships.relation_between", {"en":"Relationship between {e1_name} and {e2_name}", "ru":"Отношения между {e1_name} и {e2_name}"})
        is_now_t = await get_term(session, guild_id, language, "terms.relationships.is_now", {"en":"is now {value_str}", "ru":"теперь {value_str}"})
        msg = f"{rel_between_t.format(e1_name=e1_name, e2_name=e2_name)} {is_now_t.format(value_str=value_str)}"
        if reason:
            due_to_t = await get_term(session, guild_id, language, "terms.relationships.due_to_reason", {"en":"due to: {change_reason}", "ru":"по причине: {change_reason}"})
            msg += f" ({due_to_t.format(change_reason=reason)})."
        else:
            msg += "."
        return msg

    elif event_type_str == EventType.STATUS_APPLIED.value.upper():
        target_id = _safe_get(log_entry_details_json, ["target_entity", "id"])
        target_type = _safe_get(log_entry_details_json, ["target_entity", "type"], "entity")
        status_id = _safe_get(log_entry_details_json, ["status_effect", "id"])
        duration = log_entry_details_json.get("duration_turns")
        source_info = log_entry_details_json.get("source_entity")
        target_name = get_name_from_cache(target_type, target_id, "Someone")
        status_name = get_name_from_cache("status_effect", status_id, "a status effect")
        affected_by_t = await get_term(session, guild_id, language, "terms.statuses.is_now_affected_by", {"en":"is now affected by", "ru":"теперь под действием"})
        msg_parts = [target_name, affected_by_t, f"'{status_name}'"]
        if duration is not None:
            duration_t = await get_term(session, guild_id, language, "terms.statuses.for_duration", {"en":"for {duration_turns} turns", "ru":"на {duration_turns} ходов"})
            msg_parts.append(duration_t.format(duration_turns=duration))
        if source_info and isinstance(source_info, dict):
            from_source_t = await get_term(session, guild_id, language, "terms.statuses.from_source", {"en":"from", "ru":"от"})
            msg_parts.append(from_source_t)
            s_id = source_info.get("id")
            s_type = source_info.get("type")
            s_name_direct = source_info.get("name")
            if s_id and s_type:
                s_display_name = get_name_from_cache(str(s_type).lower(), s_id, f"source ({s_type} ID {s_id})")
                msg_parts.append(f"'{s_display_name}'")
            elif s_name_direct:
                 msg_parts.append(f"'{s_name_direct}'")
            else:
                unknown_source_t = await get_term(session, guild_id, language, "terms.statuses.an_unknown_source", {"en":"an unknown source", "ru":"неизвестного источника"})
                msg_parts.append(unknown_source_t)
        msg_parts.append(".")
        return " ".join(filter(None, msg_parts)).strip()

    elif event_type_str == EventType.STATUS_REMOVED.value.upper():
        target_id = _safe_get(log_entry_details_json, ["target_entity", "id"])
        target_type = _safe_get(log_entry_details_json, ["target_entity", "type"], "entity")
        status_id = _safe_get(log_entry_details_json, ["status_effect", "id"])
        target_name = get_name_from_cache(target_type, target_id, "Someone")
        status_name = get_name_from_cache("status_effect", status_id, "a status effect")
        template = await get_term(session, guild_id, language, "terms.statuses.effect_ended_on", {"en": "'{status_name}' effect has ended on {target_name}.", "ru": "Эффект '{status_name}' закончился для {target_name}."})
        return template.format(status_name=status_name, target_name=target_name)

    event_type_readable = event_type_str.replace("_", " ").title()
    details_str_parts = []
    for k, v in log_entry_details_json.items():
        if k not in ["guild_id", "event_type", "timestamp"]:
            details_str_parts.append(f"{k}: {str(v)[:100]}" + ("..." if len(str(v)) > 100 else ""))
    details_summary = "; ".join(details_str_parts)
    if not details_summary:
        details_summary = await get_term(session, guild_id, language, "terms.general.no_further_details", {"en":"No further details.", "ru":"Нет дополнительных деталей."})

    if language == "ru":
        generic_event_template = await get_term(session, guild_id, language, "terms.general.generic_event_occurred_ru", {"ru": "[{event_type_readable}]: {details_summary}"})
        if f"generic_event_occurred_ru?]" not in generic_event_template:
             return generic_event_template.format(event_type_readable=event_type_readable, details_summary=details_summary)
    else:
        generic_event_template = await get_term(session, guild_id, language, "terms.general.generic_event_occurred_en", {"en": "[{event_type_readable}]: {details_summary}"})
        if f"generic_event_occurred_en?]" not in generic_event_template:
            return generic_event_template.format(event_type_readable=event_type_readable, details_summary=details_summary)

    logger.warning(f"Unhandled/Generic event_type '{event_type_str}' for guild {guild_id}. Using basic fallback. Details: {details_summary}")
    return fallback_message


def _collect_entity_refs_from_log_entry(log_entry_details: Dict[str, Any]) -> Set[Tuple[str, int]]:
    refs: Set[Tuple[str, int]] = set()
    raw_event_type = log_entry_details.get("event_type")
    event_type_str_val = str(raw_event_type) if raw_event_type else ""
    if event_type_str_val == EventType.PLAYER_ACTION.value:
        actor_id = _safe_get(log_entry_details, ["actor", "id"])
        actor_type = _safe_get(log_entry_details, ["actor", "type"])
        if actor_id and actor_type: refs.add((str(actor_type).lower(), actor_id))
    elif event_type_str_val == EventType.MOVEMENT.value:
        player_id = log_entry_details.get("player_id")
        if player_id: refs.add(("player", player_id))
        old_loc_id = log_entry_details.get("old_location_id")
        if old_loc_id: refs.add(("location", old_loc_id))
        new_loc_id = log_entry_details.get("new_location_id")
        if new_loc_id: refs.add(("location", new_loc_id))
    elif event_type_str_val in [EventType.ITEM_ACQUIRED.value, EventType.ITEM_LOST.value, EventType.ITEM_USED.value, EventType.ITEM_DROPPED.value]:
        player_id = log_entry_details.get("player_id")
        if player_id: refs.add(("player", player_id))
        item_id = log_entry_details.get("item_id")
        if item_id: refs.add(("item", item_id))
        if event_type_str_val == EventType.ITEM_USED.value:
            target_entity = _safe_get(log_entry_details, ["target"])
            if target_entity and isinstance(target_entity, dict):
                target_id = target_entity.get("id")
                target_type = target_entity.get("type")
                if target_id and target_type: refs.add((str(target_type).lower(), target_id))
    elif event_type_str_val == EventType.COMBAT_ACTION.value:
        actor_id = _safe_get(log_entry_details, ["actor", "id"])
        actor_type = _safe_get(log_entry_details, ["actor", "type"])
        if actor_id and actor_type: refs.add((str(actor_type).lower(), actor_id))
        target_id = _safe_get(log_entry_details, ["target", "id"])
        target_type = _safe_get(log_entry_details, ["target", "type"])
        if target_id and target_type: refs.add((str(target_type).lower(), target_id))
        ability_id = _safe_get(log_entry_details, ["ability_id"])
        if ability_id: refs.add(("ability", ability_id))
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
    elif event_type_str_val in [EventType.STATUS_APPLIED.value, EventType.STATUS_REMOVED.value]:
        target_id = _safe_get(log_entry_details, ["target_entity", "id"])
        target_type = _safe_get(log_entry_details, ["target_entity", "type"])
        if target_id and target_type: refs.add((str(target_type).lower(), target_id))
        status_id = _safe_get(log_entry_details, ["status_effect", "id"])
        if status_id: refs.add(("status_effect", status_id))
        source_entity = _safe_get(log_entry_details, ["source_entity"])
        if source_entity and isinstance(source_entity, dict):
            source_id = source_entity.get("id")
            source_type = source_entity.get("type")
            if source_id and source_type: refs.add((str(source_type).lower(), source_id))
    elif event_type_str_val in [EventType.LEVEL_UP.value, EventType.XP_GAINED.value]:
        player_id = log_entry_details.get("player_id")
        if player_id: refs.add(("player", player_id))
    elif event_type_str_val == EventType.RELATIONSHIP_CHANGE.value:
        e1_id = _safe_get(log_entry_details, ["entity1", "id"])
        e1_type = _safe_get(log_entry_details, ["entity1", "type"])
        if e1_id and e1_type: refs.add((str(e1_type).lower(), e1_id))
        e2_id = _safe_get(log_entry_details, ["entity2", "id"])
        e2_type = _safe_get(log_entry_details, ["entity2", "type"])
        if e2_id and e2_type: refs.add((str(e2_type).lower(), e2_id))
        faction_id = log_entry_details.get("faction_id")
        if faction_id: refs.add(("faction", faction_id))
    elif event_type_str_val in [EventType.COMBAT_START.value, EventType.COMBAT_END.value]:
        location_id = log_entry_details.get("location_id")
        if location_id: refs.add(("location", location_id))
        participant_ids = log_entry_details.get("participant_ids", [])
        for p_info in participant_ids:
            if isinstance(p_info, dict) and "id" in p_info and "type" in p_info:
                refs.add((str(p_info["type"]).lower(), p_info["id"]))
        survivors = log_entry_details.get("survivors", [])
        for s_info in survivors:
            if isinstance(s_info, dict) and "id" in s_info and "type" in s_info:
                refs.add((str(s_info["type"]).lower(), s_info["id"]))
    elif event_type_str_val in [EventType.QUEST_ACCEPTED.value, EventType.QUEST_STEP_COMPLETED.value, EventType.QUEST_COMPLETED.value, EventType.QUEST_FAILED.value]:
        player_id = log_entry_details.get("player_id")
        if player_id: refs.add(("player", player_id))
        quest_id = log_entry_details.get("quest_id")
        if quest_id: refs.add(("quest", quest_id))
        if event_type_str_val == EventType.QUEST_ACCEPTED.value:
            giver_id = _safe_get(log_entry_details, ["giver_entity", "id"])
            giver_type = _safe_get(log_entry_details, ["giver_entity", "type"])
            if giver_id and giver_type: refs.add((str(giver_type).lower(), giver_id))
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
        listener_id = _safe_get(log_entry_details, ["listener_entity", "id"])
        listener_type = _safe_get(log_entry_details, ["listener_entity", "type"])
        if listener_id and listener_type: refs.add((str(listener_type).lower(), listener_id))
    elif event_type_str_val == EventType.NPC_ACTION.value:
        actor_id = _safe_get(log_entry_details, ["actor", "id"])
        actor_type = _safe_get(log_entry_details, ["actor", "type"])
        if actor_id and actor_type: refs.add((str(actor_type).lower(), actor_id))
    elif event_type_str_val == EventType.FACTION_CHANGE.value:
        entity_id = _safe_get(log_entry_details, ["entity", "id"])
        entity_type = _safe_get(log_entry_details, ["entity", "type"])
        if entity_id and entity_type: refs.add((str(entity_type).lower(), entity_id))
        faction_id = log_entry_details.get("faction_id")
        if faction_id: refs.add(("faction", faction_id))
    elif event_type_str_val in [EventType.SYSTEM_EVENT.value, EventType.WORLD_STATE_CHANGE.value, EventType.MASTER_COMMAND.value, EventType.ERROR_EVENT.value, EventType.TRADE_INITIATED.value, EventType.GE_TRIGGERED_DIALOGUE_PLACEHOLDER.value]:
        if "player_id" in log_entry_details: refs.add(("player", log_entry_details["player_id"]))
        if "npc_id" in log_entry_details: refs.add(("npc", log_entry_details["npc_id"]))
        if "global_npc_id" in log_entry_details: refs.add(("global_npc", log_entry_details["global_npc_id"]))
        if "generated_npc_id" in log_entry_details: refs.add(("generated_npc", log_entry_details["generated_npc_id"]))
        if "location_id" in log_entry_details: refs.add(("location", log_entry_details["location_id"]))
        if "item_id" in log_entry_details: refs.add(("item", log_entry_details["item_id"]))
        if "quest_id" in log_entry_details: refs.add(("quest", log_entry_details["quest_id"]))
        if "faction_id" in log_entry_details: refs.add(("faction", log_entry_details["faction_id"]))
        if "party_id" in log_entry_details: refs.add(("party", log_entry_details["party_id"]))
        if event_type_str_val == EventType.GE_TRIGGERED_DIALOGUE_PLACEHOLDER.value:
            target_entity_id = log_entry_details.get("target_entity_id")
            target_entity_type = log_entry_details.get("target_entity_type")
            if target_entity_id and target_entity_type: refs.add((str(target_entity_type).lower(), target_entity_id))
    if not refs and event_type_str_val not in [EventType.AI_GENERATION_TRIGGERED.value, EventType.TURN_START.value, EventType.TURN_END.value]:
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
    if not log_entries:
        return await get_term(
            session=session, guild_id=guild_id, language=language,
            term_key_base="terms.turn_report.nothing_significant",
            default_text_map={"en": "Nothing significant happened this turn.", "ru": "Ничего существенного не произошло за этот ход."}
        )
    all_entity_refs: Set[Tuple[str, int]] = set()
    if player_id:
        all_entity_refs.add(("player", player_id))
    for entry_details in log_entries:
        all_entity_refs.update(_collect_entity_refs_from_log_entry(entry_details))
    names_cache: Dict[Tuple[str, int], str] = {}
    if all_entity_refs:
        entity_refs_for_batch: List[Dict[str, Any]] = [
            {"type": entity_type, "id": entity_id} for entity_type, entity_id in all_entity_refs
        ]
        names_cache = await get_batch_localized_entity_names(
            session, guild_id, entity_refs_for_batch, language, fallback_language
        )
    player_name_for_title = names_cache.get(("player", player_id), f"Player {player_id}")
    title_template = await get_term(
        session=session, guild_id=guild_id, language=language,
        term_key_base="terms.turn_report.report_for_player",
        default_text_map={"en": "Turn Report for {player_name}:", "ru": "Отчет по ходу для {player_name}:"}
    )
    report_parts = [title_template.format(player_name=player_name_for_title)]
    for entry_details in log_entries:
        if 'guild_id' not in entry_details and guild_id:
            entry_details_copy = entry_details.copy()
            entry_details_copy['guild_id'] = guild_id
            formatted_entry = await _format_log_entry_with_names_cache(session, entry_details_copy, language, names_cache)
        else:
            formatted_entry = await _format_log_entry_with_names_cache(session, entry_details, language, names_cache)
        report_parts.append(f"- {formatted_entry}")
    return "\n".join(report_parts)

async def format_story_log_entry_for_master_display(
    session: AsyncSession,
    log_entry: StoryLog,
    language: str,
    fallback_language: str = "en"
) -> str:
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
