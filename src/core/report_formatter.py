# src/core/report_formatter.py
import logging
from typing import List, Dict, Any, Union, Tuple, Set, Optional # Added Optional
from sqlalchemy.ext.asyncio import AsyncSession

# Removed direct import of get_localized_entity_name
# from .localization_utils import get_localized_entity_name
from .localization_utils import get_batch_localized_entity_names # Import the new batch function
from .rules import get_rule # Added import for get_rule
from ..models.story_log import StoryLog
from ..models.enums import EventType # Import EventType

logger = logging.getLogger(__name__)

# Module-level helper for localization terms
async def get_term(
    session: AsyncSession,
    guild_id: Optional[int],  # guild_id can be None for global terms or if guild context is not applicable
    language: str,
    term_key_base: str,
    default_text_map: Dict[str, str]
) -> str:
    full_term_key = f"{term_key_base}_{language}"
    primary_fallback_language = "en"

    rule_value_obj = None
    if guild_id is not None: # Only query RuleConfig if guild_id is provided
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
    return f"[{term_key_base}_{language}?]" # Return a more informative placeholder

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

  # All calls to get_term now directly use the module-level get_term function
  # The call_get_term wrapper is no longer needed.

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
            actor_name = get_name_from_cache(str(actor_type).lower(), actor_id, str(actor_type).capitalize())

        entities = _safe_get(log_entry_details_json, ["action", "entities"], [])
        target_name_str = await get_term(session, guild_id, language, "terms.general.something_somewhere", {"en": "something/somewhere", "ru": "что-то/где-то"})

        if entities and isinstance(entities, list) and len(entities) > 0:
            first_entity = entities[0]
            if isinstance(first_entity, dict):
                 # Prioritize 'name', then 'static_id', then 'value'
                target_name_str = first_entity.get("name", first_entity.get("value", str(first_entity)))
                # If it's an entity with type and id, try to get its cached name
                entity_type_in_action = first_entity.get("type")
                entity_id_in_action = first_entity.get("id") # This might be static_id or pk depending on NLU
                if entity_type_in_action and entity_id_in_action: # This is a heuristic
                    # Try to resolve if it's a known entity type that uses integer PKs in cache
                    # This part is tricky as "id" in action entities might not be PK
                    pass # For now, use name/value from entity dict

        if action_intent == "examine":
            verb_defaults = {"en": "examines", "ru": "осматривает"}
            sees_defaults = {"en": "Observations", "ru": "Вы видите"}
        else:
            verb_defaults = {"en": action_intent, "ru": action_intent} # Default to intent name if no term
            sees_defaults = {} # Not used for other actions in this block

        preposition_defaults = {"en": "on", "ru": "на"}
        result_label_defaults = {"en": "Result", "ru": "Результат"}

        verb = await get_term(session, guild_id, language, f"terms.actions.{action_intent}.verb", verb_defaults)

        formatted_str = f"{actor_name} {verb}"

        if action_intent == "examine":
            sees_term = await get_term(session, guild_id, language, f"terms.actions.examine.sees", sees_defaults)
            formatted_str += f" '{target_name_str}'. {sees_term}:"
        elif action_intent not in ["look", "think"]:
            preposition = await get_term(session, guild_id, language, f"terms.actions.{action_intent}.preposition", preposition_defaults)
            formatted_str += f" {preposition} '{target_name_str}'."
        else:
            formatted_str += "."

        result_desc = _safe_get(log_entry_details_json, ["result", "description"])
        if result_desc:
            if action_intent == "examine":
                 formatted_str += f" {result_desc}"
            else:
                result_label = await get_term(session, guild_id, language, "terms.general.result_label", result_label_defaults)
                formatted_str += f" {result_label}: {result_desc}"

        return formatted_str.strip()

    elif event_type_str == EventType.MOVEMENT.value.upper():
        player_id = _safe_get(log_entry_details_json, ["player_id"])
        old_loc_id = _safe_get(log_entry_details_json, ["old_location_id"])
        new_loc_id = _safe_get(log_entry_details_json, ["new_location_id"])

        actor_name = get_name_from_cache("player", player_id, "Player") if player_id else await get_term(session, guild_id, language, "terms.general.someone", {"en": "Someone", "ru": "Некто"})
        old_loc_name = get_name_from_cache("location", old_loc_id, await get_term(session, guild_id, language, "terms.general.unknown_location", {"en":"an old place", "ru":"старое место"})) if old_loc_id else await get_term(session, guild_id, language, "terms.general.somewhere", {"en": "somewhere", "ru": "где-то"})
        new_loc_name = get_name_from_cache("location", new_loc_id, await get_term(session, guild_id, language, "terms.general.unknown_location", {"en":"a new place", "ru":"новое место"})) if new_loc_id else await get_term(session, guild_id, language, "terms.general.somewhere_new", {"en": "somewhere new", "ru": "куда-то еще"})

        template_str = await get_term(session, guild_id, language, "terms.movement.player_moves_from_to", {"en": "{actor_name} moves from '{old_loc_name}' to '{new_loc_name}'.", "ru": "{actor_name} перемещается из '{old_loc_name}' в '{new_loc_name}'."})
        return template_str.format(actor_name=actor_name, old_loc_name=old_loc_name, new_loc_name=new_loc_name)

    elif event_type_str == EventType.ITEM_ACQUIRED.value.upper():
        player_id = _safe_get(log_entry_details_json, ["player_id"])
        item_id = _safe_get(log_entry_details_json, ["item_id"])
        quantity = _safe_get(log_entry_details_json, ["quantity"], 1)
        source = _safe_get(log_entry_details_json, ["source"])

        actor_name = get_name_from_cache("player", player_id, "Player") if player_id else await get_term(session, guild_id, language, "terms.general.someone", {"en": "Someone", "ru": "Некто"})
        item_name = get_name_from_cache("item", item_id, await get_term(session, guild_id, language, "terms.general.an_item", {"en": "an item", "ru": "предмет"})) if item_id else await get_term(session, guild_id, language, "terms.general.an_item", {"en": "an item", "ru": "предмет"})

        if source:
            template_str = await get_term(session, guild_id, language, "terms.items.acquired_from_source", {"en": "{actor_name} acquired '{item_name}' (x{quantity}) from {source}.", "ru": "{actor_name} получил(а) '{item_name}' (x{quantity}) из {source}."})
            return template_str.format(actor_name=actor_name, item_name=item_name, quantity=quantity, source=source)
        else:
            template_str = await get_term(session, guild_id, language, "terms.items.acquired", {"en": "{actor_name} acquired '{item_name}' (x{quantity}).", "ru": "{actor_name} получил(а) '{item_name}' (x{quantity})."})
            return template_str.format(actor_name=actor_name, item_name=item_name, quantity=quantity)

    elif event_type_str == EventType.COMBAT_START.value.upper():
        location_id = _safe_get(log_entry_details_json, ["location_id"])
        participant_ids_json = _safe_get(log_entry_details_json, ["participant_ids"], [])

        location_name = get_name_from_cache("location", location_id, await get_term(session, guild_id, language, "terms.general.unknown_location", {"en": "an unknown location", "ru": "неизвестной локации"})) if location_id else await get_term(session, guild_id, language, "terms.general.unknown_location", {"en": "an unknown location", "ru": "неизвестной локации"})

        participant_names_list = []
        for p_info in participant_ids_json:
            if isinstance(p_info, dict) and "id" in p_info and "type" in p_info:
                p_name = get_name_from_cache(str(p_info["type"]).lower(), p_info["id"], str(p_info["type"]).capitalize())
                participant_names_list.append(p_name)

        participants_str = ", ".join(participant_names_list) if participant_names_list else await get_term(session, guild_id, language, "terms.general.unknown_participants", {"en": "unknown participants", "ru": "неизвестные участники"})

        template_str = await get_term(session, guild_id, language, "terms.combat.starts_involving", {"en": "Combat starts at '{location_name}' involving: {participants_str}.", "ru": "Начинается бой в '{location_name}' с участием: {participants_str}."})
        return template_str.format(location_name=location_name, participants_str=participants_str)

    elif event_type_str == EventType.COMBAT_END.value.upper():
        location_id = _safe_get(log_entry_details_json, ["location_id"])
        outcome = _safe_get(log_entry_details_json, ["outcome"], "unknown")
        survivors_json = _safe_get(log_entry_details_json, ["survivors"], [])

        location_name = get_name_from_cache("location", location_id, await get_term(session, guild_id, language, "terms.general.unknown_location", {"en": "an unknown location", "ru": "неизвестной локации"})) if location_id else await get_term(session, guild_id, language, "terms.general.unknown_location", {"en": "an unknown location", "ru": "неизвестной локации"})

        outcome_readable_key = f"terms.combat.outcomes.{outcome}" # e.g. terms.combat.outcomes.victory_players
        outcome_readable_default = outcome.replace("_", " ").capitalize()
        outcome_readable = await get_term(session, guild_id, language, outcome_readable_key, {"en": outcome_readable_default, "ru": outcome_readable_default})

        base_template = await get_term(session, guild_id, language, "terms.combat.ended", {"en": "Combat at '{location_name}' has ended. Outcome: {outcome_readable}.", "ru": "Схватка в '{location_name}' окончена. Результат: {outcome_readable}."})
        formatted_msg = base_template.format(location_name=location_name, outcome_readable=outcome_readable)

        survivor_names_list = []
        for s_info in survivors_json:
            if isinstance(s_info, dict) and "id" in s_info and "type" in s_info:
                s_name = get_name_from_cache(str(s_info["type"]).lower(), s_info["id"], str(s_info["type"]).capitalize())
                survivor_names_list.append(s_name)

        if survivor_names_list:
            survivors_str = ", ".join(survivor_names_list)
            survivors_template = await get_term(session, guild_id, language, "terms.combat.survivors", {"en": " Survivors: {survivors_str}.", "ru": " Уцелевшие: {survivors_str}."})
            formatted_msg += survivors_template.format(survivors_str=survivors_str)
        return formatted_msg

    elif event_type_str == EventType.ABILITY_USED.value.upper():
        actor_entity_json = _safe_get(log_entry_details_json, ["actor_entity"], {})
        actor_id = _safe_get(actor_entity_json, ["id"])
        actor_type = _safe_get(actor_entity_json, ["type"], "entity")
        ability_json = _safe_get(log_entry_details_json, ["ability"], {})
        ability_id = _safe_get(ability_json, ["id"]) # This is Ability.id (PK)
        targets_json = _safe_get(log_entry_details_json, ["targets"], [])
        outcome_desc = _safe_get(log_entry_details_json, ["outcome", "description"], "")

        actor_name = get_name_from_cache(str(actor_type).lower(), actor_id, str(actor_type).capitalize()) if actor_id and actor_type else await get_term(session, guild_id, language, "terms.general.someone", {"en": "Someone", "ru": "Некто"})
        ability_name = get_name_from_cache("ability", ability_id, await get_term(session, guild_id, language, "terms.abilities.an_ability", {"en": "an ability", "ru": "способность"})) if ability_id else await get_term(session, guild_id, language, "terms.abilities.an_ability", {"en": "an ability", "ru": "способность"})

        verb_uses = await get_term(session, guild_id, language, "terms.abilities.verb_uses", {"en": "uses ability", "ru": "использует способность"})
        particle_on = await get_term(session, guild_id, language, "terms.abilities.particle_on", {"en": "on", "ru": "на"})

        target_names_list = []
        if targets_json:
            for target_entry in targets_json:
                target_info = _safe_get(target_entry, ["entity"], {})
                t_id = _safe_get(target_info, ["id"])
                t_type = _safe_get(target_info, ["type"])
                if t_id and t_type:
                    target_names_list.append(get_name_from_cache(str(t_type).lower(), t_id, str(t_type).capitalize()))

        targets_display_str = ", ".join(target_names_list) if target_names_list else await get_term(session, guild_id, language, "terms.general.nobody", {"en": "nobody", "ru": "никого"})

        formatted_str = f"{actor_name} {verb_uses} '{ability_name}' {particle_on} {targets_display_str}."
        if outcome_desc:
            formatted_str += f" {outcome_desc}"
        return formatted_str.strip()

    elif event_type_str == EventType.NPC_ACTION.value.upper():
        actor_json = _safe_get(log_entry_details_json, ["actor"], {})
        actor_id = _safe_get(actor_json, ["id"])
        actor_type = _safe_get(actor_json, ["type"], "npc") # Default to npc

        action_json = _safe_get(log_entry_details_json, ["action"], {})
        action_intent = _safe_get(action_json, ["intent"], "unknown_action").lower()
        action_entities = _safe_get(action_json, ["entities"], [])

        result_message = _safe_get(log_entry_details_json, ["result", "message"], "")

        actor_name = get_name_from_cache(str(actor_type).lower(), actor_id, await get_term(session, guild_id, language, "terms.general.an_npc", {"en": "An NPC", "ru": "НИП"})) if actor_id and actor_type else await get_term(session, guild_id, language, "terms.general.an_npc", {"en": "An NPC", "ru": "НИП"})

        # Determine target name from action_entities (simplified)
        target_name_str = ""
        if action_entities and isinstance(action_entities, list) and len(action_entities) > 0:
            first_entity = action_entities[0]
            if isinstance(first_entity, dict):
                target_name_str = first_entity.get("name", first_entity.get("value", ""))

        verb_key_suffix = ".verb_npc" # Specific for NPC actions if needed, or use generic
        verb_defaults = {"en": f"performs '{action_intent}'", "ru": f"совершает '{action_intent}'"}
        verb = await get_term(session, guild_id, language, f"terms.actions.{action_intent}{verb_key_suffix}", verb_defaults)

        formatted_str = f"{actor_name} {verb}"
        if target_name_str:
             # The preposition should ideally be part of the verb term if it's verb-specific,
             # or a general "on target" term could be used.
             # For "performs 'attack' on 'target'", "on" is good.
             # For "casts 'fireball' at 'target'", "at" might be better.
             # Using a generic preposition for now, fetched via action_intent.
             preposition_defaults_npc = {"en": "on", "ru": "на"}
             on_particle = await get_term(session, guild_id, language, f"terms.actions.{action_intent}.preposition_npc", preposition_defaults_npc) # allow specific npc preposition
             if not on_particle and action_intent not in ["look", "think"]: # fallback to general if specific not found
                 on_particle = await get_term(session, guild_id, language, f"terms.actions.{action_intent}.preposition", {"en": "on", "ru": "на"})

             if on_particle: # Only add preposition if one is found/defined
                formatted_str += f" {on_particle} '{target_name_str}'"

        formatted_str += "."
        if result_message:
            formatted_str += f" {result_message}"
        return formatted_str.strip()

    elif event_type_str == EventType.COMBAT_ACTION.value.upper():
        actor_json = _safe_get(log_entry_details_json, ["actor"], {})
        actor_id = _safe_get(actor_json, ["id"])
        actor_type = _safe_get(actor_json, ["type"], "entity")
        target_json = _safe_get(log_entry_details_json, ["target"], {})
        target_id = _safe_get(target_json, ["id"])
        target_type = _safe_get(target_json, ["type"], "entity")
        action_name_str = _safe_get(log_entry_details_json, ["action_name"], "action")
        damage_val = _safe_get(log_entry_details_json, ["damage"])
        check_result_json = _safe_get(log_entry_details_json, ["check_result"], {})

        actor_name = get_name_from_cache(str(actor_type).lower(), actor_id, str(actor_type).capitalize()) if actor_id and actor_type else "Actor"
        target_name = get_name_from_cache(str(target_type).lower(), target_id, str(target_type).capitalize()) if target_id and target_type else "Target"

        uses_term = await get_term(session, guild_id, language, "terms.combat.uses", {"en": "uses", "ru": "использует"})
        on_term = await get_term(session, guild_id, language, "terms.combat.on", {"en": "on", "ru": "на"})

        base_msg = f"{actor_name} {uses_term} '{action_name_str}' {on_term} {target_name}"
        if damage_val is not None and damage_val > 0:
            dealing_term = await get_term(session, guild_id, language, "terms.combat.dealing_damage", {"en": "dealing", "ru": "нанося"})
            damage_term = await get_term(session, guild_id, language, "terms.general.damage", {"en": "damage", "ru": "урона"})
            base_msg += f", {dealing_term} {damage_val} {damage_term}."
        else:
            base_msg += "."

        check_str_parts = []
        if check_result_json:
            roll = _safe_get(check_result_json, ["roll_used"])
            total_mod = _safe_get(check_result_json, ["total_modifier"])
            final_val = _safe_get(check_result_json, ["final_value"])
            dc = _safe_get(check_result_json, ["difficulty_class"])
            if all(v is not None for v in [roll, total_mod, final_val, dc]):
                term_roll_val = await get_term(session, guild_id, language, "terms.checks.roll", {"en": "Roll", "ru": "Бросок"})
                term_mod_val = await get_term(session, guild_id, language, "terms.checks.modifier", {"en": "Mod", "ru": "Мод."})
                term_total_val = await get_term(session, guild_id, language, "terms.checks.total", {"en": "Total", "ru": "Итог"})
                term_vs_dc_val = await get_term(session, guild_id, language, "terms.checks.vs_dc", {"en": "vs DC", "ru": "против СЛ"})
                check_str_parts.append(f"({term_roll_val}: {roll}, {term_mod_val}: {total_mod}, {term_total_val}: {final_val} {term_vs_dc_val}: {dc})")

            modifier_details_list = _safe_get(check_result_json, ["modifier_details"], [])
            mod_descs = []
            for md in modifier_details_list:
                desc = _safe_get(md, ["description"], "Unknown Modifier")
                val = _safe_get(md, ["value"], 0)
                mod_descs.append(f"{desc} ({'+' if val >=0 else ''}{val})")
            if mod_descs:
                term_bonuses_penalties_val = await get_term(session, guild_id, language, "terms.checks.bonuses_penalties", {"en": "Bonuses/Penalties", "ru": "Бонусы/Штрафы"})
                check_str_parts.append(f"[{term_bonuses_penalties_val}: {'; '.join(mod_descs)}]")

        return f"{base_msg} {' '.join(check_str_parts)}".strip()

    elif event_type_str == EventType.ITEM_USED.value.upper():
        player_id = _safe_get(log_entry_details_json, ["player_id"])
        item_id = _safe_get(log_entry_details_json, ["item_id"])
        outcome_desc = _safe_get(log_entry_details_json, ["outcome_description"], "")
        target_info = _safe_get(log_entry_details_json, ["target"])

        actor_name = get_name_from_cache("player", player_id, "Player") if player_id else await get_term(session, guild_id, language, "terms.general.someone", {"en": "Someone", "ru": "Некто"})
        item_name = get_name_from_cache("item", item_id, await get_term(session, guild_id, language, "terms.general.an_item", {"en": "an item", "ru": "предмет"})) if item_id else await get_term(session, guild_id, language, "terms.general.an_item", {"en": "an item", "ru": "предмет"})

        uses_term = await get_term(session, guild_id, language, "terms.items.uses", {"en": "uses", "ru": "использует"})
        formatted_str = f"{actor_name} {uses_term} '{item_name}'"

        if target_info and isinstance(target_info, dict):
            target_id = _safe_get(target_info, ["id"])
            target_type = _safe_get(target_info, ["type"])
            if target_id and target_type:
                target_name_rendered = get_name_from_cache(str(target_type).lower(), target_id, str(target_type).capitalize())
                on_term = await get_term(session, guild_id, language, "terms.items.on", {"en": "on", "ru": "на"})
                formatted_str += f" {on_term} '{target_name_rendered}'"

        formatted_str += "."
        if outcome_desc:
            formatted_str += f" {outcome_desc}"
        return formatted_str.strip()

    elif event_type_str == EventType.ITEM_DROPPED.value.upper():
        player_id = _safe_get(log_entry_details_json, ["player_id"])
        item_id = _safe_get(log_entry_details_json, ["item_id"])
        quantity = _safe_get(log_entry_details_json, ["quantity"], 1)

        actor_name = get_name_from_cache("player", player_id, "Player") if player_id else await get_term(session, guild_id, language, "terms.general.someone", {"en": "Someone", "ru": "Некто"})
        item_name = get_name_from_cache("item", item_id, await get_term(session, guild_id, language, "terms.general.an_item", {"en": "an item", "ru": "предмет"})) if item_id else await get_term(session, guild_id, language, "terms.general.an_item", {"en": "an item", "ru": "предмет"})

        drops_term = await get_term(session, guild_id, language, "terms.items.drops", {"en": "drops", "ru": "выбрасывает"})
        return f"{actor_name} {drops_term} '{item_name}' (x{quantity})."

    elif event_type_str == EventType.DIALOGUE_START.value.upper():
        player_entity_json = _safe_get(log_entry_details_json, ["player_entity"], {})
        player_id = _safe_get(player_entity_json, ["id"])
        npc_entity_json = _safe_get(log_entry_details_json, ["npc_entity"], {})
        npc_id = _safe_get(npc_entity_json, ["id"])

        player_name = get_name_from_cache("player", player_id, "Player") if player_id else await get_term(session, guild_id, language, "terms.general.someone", {"en": "Someone", "ru": "Некто"})
        # Use "npc" for cache lookup, consistent with mock_names_cache_fixture and likely other areas.
        npc_name = get_name_from_cache("npc", npc_id, await get_term(session, guild_id, language, "terms.general.an_npc", {"en": "An NPC", "ru": "НИП"})) if npc_id else await get_term(session, guild_id, language, "terms.general.an_npc", {"en": "An NPC", "ru": "НИП"})

        template_str = await get_term(session, guild_id, language, "terms.dialogue.starts_conversation_with", {"en": "{player_name} starts a conversation with {npc_name}.", "ru": "{player_name} начинает разговор с {npc_name}."})
        return template_str.format(player_name=player_name, npc_name=npc_name)

    elif event_type_str == EventType.DIALOGUE_END.value.upper():
        player_entity_json = _safe_get(log_entry_details_json, ["player_entity"], {})
        player_id = _safe_get(player_entity_json, ["id"])
        npc_entity_json = _safe_get(log_entry_details_json, ["npc_entity"], {})
        npc_id = _safe_get(npc_entity_json, ["id"])

        player_name = get_name_from_cache("player", player_id, "Player") if player_id else await get_term(session, guild_id, language, "terms.general.someone", {"en": "Someone", "ru": "Некто"})
        # Use "npc" for cache lookup.
        npc_name = get_name_from_cache("npc", npc_id, await get_term(session, guild_id, language, "terms.general.an_npc", {"en": "An NPC", "ru": "НИП"})) if npc_id else await get_term(session, guild_id, language, "terms.general.an_npc", {"en": "An NPC", "ru": "НИП"})

        template_str = await get_term(session, guild_id, language, "terms.dialogue.ends_conversation_with", {"en": "{player_name} ends the conversation with {npc_name}.", "ru": "{player_name} заканчивает разговор с {npc_name}."})
        return template_str.format(player_name=player_name, npc_name=npc_name)

    elif event_type_str == EventType.DIALOGUE_LINE.value.upper():
        speaker_entity_json = _safe_get(log_entry_details_json, ["speaker_entity"], {})
        speaker_id = _safe_get(speaker_entity_json, ["id"])
        speaker_type = _safe_get(speaker_entity_json, ["type"], "entity") # Should be 'player' or 'generated_npc'
        line_text = _safe_get(log_entry_details_json, ["line_text"], "...")

        # Ensure speaker_type is lowercased for cache lookup, and provide a sensible default if type is generic
        default_speaker_name_prefix = str(speaker_type).capitalize() if speaker_type and speaker_type != "entity" else "Speaker"
        speaker_name = get_name_from_cache(str(speaker_type).lower(), speaker_id, default_speaker_name_prefix) if speaker_id and speaker_type else await get_term(session, guild_id, language, "terms.general.someone", {"en": "Someone", "ru": "Некто"})
        return f'{speaker_name}: "{line_text}"'

    elif event_type_str == EventType.FACTION_CHANGE.value.upper():
        entity_json = _safe_get(log_entry_details_json, ["entity"], {})
        entity_id = _safe_get(entity_json, ["id"])
        entity_type = _safe_get(entity_json, ["type"], "entity")
        faction_id = _safe_get(log_entry_details_json, ["faction_id"])
        old_standing = _safe_get(log_entry_details_json, ["old_standing"], "unknown")
        new_standing = _safe_get(log_entry_details_json, ["new_standing"], "unknown")
        reason = _safe_get(log_entry_details_json, ["reason"])

        entity_name = get_name_from_cache(str(entity_type).lower(), entity_id, str(entity_type).capitalize()) if entity_id and entity_type else await get_term(session, guild_id, language, "terms.general.an_entity", {"en": "An entity", "ru": "Сущность"})
        faction_name = get_name_from_cache("faction", faction_id, await get_term(session, guild_id, language, "terms.factions.a_faction", {"en": "a faction", "ru": "фракцией"})) if faction_id else await get_term(session, guild_id, language, "terms.factions.a_faction", {"en": "a faction", "ru": "фракцией"})

        rep_of = await get_term(session, guild_id, language, "terms.factions.reputation_of", {"en": "Reputation of", "ru": "Репутация"})
        with_faction = await get_term(session, guild_id, language, "terms.factions.with_faction", {"en": "with", "ru": "с"})
        changed_from = await get_term(session, guild_id, language, "terms.factions.changed_from", {"en": "changed from", "ru": "изменилась с"})
        to_standing = await get_term(session, guild_id, language, "terms.factions.to_standing", {"en": "to", "ru": "на"})

        msg = f"{rep_of} {entity_name} {with_faction} {faction_name} {changed_from} {old_standing} {to_standing} {new_standing}."
        if reason:
            reason_term = await get_term(session, guild_id, language, "terms.general.reason", {"en": "Reason", "ru": "Причина"})
            msg += f" ({reason_term}: {reason})"
        return msg

    elif event_type_str == EventType.STATUS_APPLIED.value.upper():
        target_entity_json = _safe_get(log_entry_details_json, ["target_entity"], {})
        target_id = _safe_get(target_entity_json, ["id"])
        target_type = _safe_get(target_entity_json, ["type"], "entity")
        status_effect_json = _safe_get(log_entry_details_json, ["status_effect"], {})
        status_id = _safe_get(status_effect_json, ["id"]) # This is StatusEffect.id (PK)
        duration_turns = _safe_get(log_entry_details_json, ["duration_turns"])
        source_entity_json = _safe_get(log_entry_details_json, ["source_entity"]) # Optional

        target_name = get_name_from_cache(str(target_type).lower(), target_id, str(target_type).capitalize()) if target_id and target_type else await get_term(session, guild_id, language, "terms.general.someone", {"en": "Someone", "ru": "Некто"})
        status_name = get_name_from_cache("status_effect", status_id, await get_term(session, guild_id, language, "terms.statuses.a_status_effect", {"en": "a status effect", "ru": "эффект состояния"})) if status_id else await get_term(session, guild_id, language, "terms.statuses.a_status_effect", {"en": "a status effect", "ru": "эффект состояния"})

        is_now_affected_by = await get_term(session, guild_id, language, "terms.statuses.is_now_affected_by", {"en": "is now affected by", "ru": "теперь под действием"})
        msg_parts = [target_name, is_now_affected_by, f"'{status_name}'"]

        if duration_turns is not None:
            for_duration_fmt = await get_term(session, guild_id, language, "terms.statuses.for_duration", {"en": "for {duration_turns} turns", "ru": "на {duration_turns} ходов"})
            msg_parts.append(for_duration_fmt.format(duration_turns=duration_turns))

        if source_entity_json and isinstance(source_entity_json, dict):
            from_source_term = await get_term(session, guild_id, language, "terms.statuses.from_source", {"en": "from", "ru": "от"})
            msg_parts.append(from_source_term)
            source_id = _safe_get(source_entity_json, ["id"])
            source_type = _safe_get(source_entity_json, ["type"])
            source_name_direct = _safe_get(source_entity_json, ["name"]) # If source is just a name string

            if source_id and source_type:
                source_display_name = get_name_from_cache(str(source_type).lower(), source_id, str(source_type).capitalize())
                msg_parts.append(f"'{source_display_name}'")
            elif source_name_direct:
                 msg_parts.append(f"'{source_name_direct}'")
            else:
                msg_parts.append(await get_term(session, guild_id, language, "terms.statuses.an_unknown_source", {"en": "an unknown source", "ru": "неизвестного источника"}))

        msg_parts.append(".")
        return " ".join(msg_parts)

    elif event_type_str == EventType.STATUS_REMOVED.value.upper():
        target_entity_json = _safe_get(log_entry_details_json, ["target_entity"], {})
        target_id = _safe_get(target_entity_json, ["id"])
        target_type = _safe_get(target_entity_json, ["type"], "entity")
        status_effect_json = _safe_get(log_entry_details_json, ["status_effect"], {})
        status_id = _safe_get(status_effect_json, ["id"])

        target_name = get_name_from_cache(str(target_type).lower(), target_id, str(target_type).capitalize()) if target_id and target_type else await get_term(session, guild_id, language, "terms.general.someone", {"en": "Someone", "ru": "Некто"})
        status_name = get_name_from_cache("status_effect", status_id, await get_term(session, guild_id, language, "terms.statuses.a_status_effect", {"en": "a status effect", "ru": "эффект состояния"})) if status_id else await get_term(session, guild_id, language, "terms.statuses.a_status_effect", {"en": "a status effect", "ru": "эффект состояния"})

        template_str = await get_term(session, guild_id, language, "terms.statuses.effect_ended_on", {"en": "'{status_name}' effect has ended on {target_name}.", "ru": "Эффект '{status_name}' закончился для {target_name}."})
        return template_str.format(status_name=status_name, target_name=target_name)

    elif event_type_str == EventType.QUEST_ACCEPTED.value.upper():
        player_id = _safe_get(log_entry_details_json, ["player_id"])
        quest_id = _safe_get(log_entry_details_json, ["quest_id"]) # GeneratedQuest.id

        player_name = get_name_from_cache("player", player_id, "Player") if player_id else await get_term(session, guild_id, language, "terms.general.someone", {"en": "Someone", "ru": "Некто"})
        quest_name = get_name_from_cache("quest", quest_id, await get_term(session, guild_id, language, "terms.quests.a_quest", {"en": "a quest", "ru": "задание"})) if quest_id else await get_term(session, guild_id, language, "terms.quests.a_quest", {"en": "a quest", "ru": "задание"})

        template_str = await get_term(session, guild_id, language, "terms.quests.accepted", {"en": "{player_name} has accepted the quest: '{quest_name}'.", "ru": "{player_name} принял(а) задание: '{quest_name}'."})
        return template_str.format(player_name=player_name, quest_name=quest_name)

    elif event_type_str == EventType.QUEST_STEP_COMPLETED.value.upper():
        player_id = _safe_get(log_entry_details_json, ["player_id"])
        quest_id = _safe_get(log_entry_details_json, ["quest_id"])
        step_details_str = _safe_get(log_entry_details_json, ["step_details"]) # This is often the title of the step

        player_name = get_name_from_cache("player", player_id, "Player") if player_id else await get_term(session, guild_id, language, "terms.general.someone", {"en": "Someone", "ru": "Некто"})
        quest_name = get_name_from_cache("quest", quest_id, await get_term(session, guild_id, language, "terms.quests.a_quest", {"en": "a quest", "ru": "задание"})) if quest_id else await get_term(session, guild_id, language, "terms.quests.a_quest", {"en": "a quest", "ru": "задание"})

        if step_details_str:
            template_str = await get_term(session, guild_id, language, "terms.quests.step_completed_detailed", {"en": "{player_name} completed a step in '{quest_name}': {step_details}.", "ru": "{player_name} выполнил(а) этап в задании '{quest_name}': {step_details}."})
            return template_str.format(player_name=player_name, quest_name=quest_name, step_details=step_details_str)
        else:
            template_str = await get_term(session, guild_id, language, "terms.quests.step_completed_simple", {"en": "{player_name} completed a step in the quest '{quest_name}'.", "ru": "{player_name} выполнил(а) этап в задании '{quest_name}'."})
            return template_str.format(player_name=player_name, quest_name=quest_name)

    elif event_type_str == EventType.QUEST_COMPLETED.value.upper():
        player_id = _safe_get(log_entry_details_json, ["player_id"])
        quest_id = _safe_get(log_entry_details_json, ["quest_id"])

        player_name = get_name_from_cache("player", player_id, "Player") if player_id else await get_term(session, guild_id, language, "terms.general.someone", {"en": "Someone", "ru": "Некто"})
        quest_name = get_name_from_cache("quest", quest_id, await get_term(session, guild_id, language, "terms.quests.a_quest", {"en": "a quest", "ru": "задание"})) if quest_id else await get_term(session, guild_id, language, "terms.quests.a_quest", {"en": "a quest", "ru": "задание"})

        template_str = await get_term(session, guild_id, language, "terms.quests.completed", {"en": "{player_name} has completed the quest: '{quest_name}'!", "ru": "{player_name} завершил(а) задание: '{quest_name}'!"})
        return template_str.format(player_name=player_name, quest_name=quest_name)

    elif event_type_str == EventType.QUEST_FAILED.value.upper():
        player_id = _safe_get(log_entry_details_json, ["player_id"])
        quest_id = _safe_get(log_entry_details_json, ["quest_id"])
        reason = _safe_get(log_entry_details_json, ["reason"])

        player_name = get_name_from_cache("player", player_id, "Player") if player_id else await get_term(session, guild_id, language, "terms.general.someone", {"en": "Someone", "ru": "Некто"})
        quest_name = get_name_from_cache("quest", quest_id, await get_term(session, guild_id, language, "terms.quests.a_quest", {"en": "a quest", "ru": "задание"})) if quest_id else await get_term(session, guild_id, language, "terms.quests.a_quest", {"en": "a quest", "ru": "задание"})

        if reason:
            template_str = await get_term(session, guild_id, language, "terms.quests.failed_with_reason", {"en": "{player_name} has failed the quest '{quest_name}' due to: {reason}.", "ru": "{player_name} провалил(а) задание '{quest_name}' по причине: {reason}."})
            return template_str.format(player_name=player_name, quest_name=quest_name, reason=reason)
        else:
            template_str = await get_term(session, guild_id, language, "terms.quests.failed_simple", {"en": "{player_name} has failed the quest '{quest_name}'.", "ru": "{player_name} провалил(а) задание '{quest_name}'."})
            return template_str.format(player_name=player_name, quest_name=quest_name)

    elif event_type_str == EventType.LEVEL_UP.value.upper():
        player_id = _safe_get(log_entry_details_json, ["player_id"])
        new_level = _safe_get(log_entry_details_json, ["new_level"])

        player_name = get_name_from_cache("player", player_id, "Player") if player_id else await get_term(session, guild_id, language, "terms.general.someone", {"en": "Someone", "ru": "Некто"})
        level_str = str(new_level) if new_level is not None else await get_term(session, guild_id, language, "terms.character.unknown_level", {"en": "a new level", "ru": "новый уровень"})

        template_str = await get_term(session, guild_id, language, "terms.character.level_up", {"en": "{player_name} has reached level {level_str}!", "ru": "{player_name} достиг(ла) уровня {level_str}!"})
        return template_str.format(player_name=player_name, level_str=level_str)

    elif event_type_str == EventType.XP_GAINED.value.upper():
        player_id = _safe_get(log_entry_details_json, ["player_id"])
        amount = _safe_get(log_entry_details_json, ["amount"])
        source = _safe_get(log_entry_details_json, ["source"]) # Optional

        player_name = get_name_from_cache("player", player_id, "Player") if player_id else await get_term(session, guild_id, language, "terms.general.someone", {"en": "Someone", "ru": "Некто"})
        amount_str = str(amount) if amount is not None else await get_term(session, guild_id, language, "terms.character.some_xp", {"en": "some", "ru": "немного"})
        xp_term = await get_term(session, guild_id, language, "terms.character.xp", {"en": "XP", "ru": "опыта"})

        if source:
            from_source_template = await get_term(session, guild_id, language, "terms.character.from_source", {"en": "from {source}", "ru": "из {source}"})
            source_str_rendered = from_source_template.format(source=source)
            template_str = await get_term(session, guild_id, language, "terms.character.xp_gained_with_source", {"en": "{player_name} gained {amount_str} {xp_term} {source_str}.", "ru": "{player_name} получил(а) {amount_str} {xp_term} {source_str}."})
            return template_str.format(player_name=player_name, amount_str=amount_str, xp_term=xp_term, source_str=source_str_rendered)
        else:
            template_str = await get_term(session, guild_id, language, "terms.character.xp_gained_simple", {"en": "{player_name} gained {amount_str} {xp_term}.", "ru": "{player_name} получил(а) {amount_str} {xp_term}."})
            return template_str.format(player_name=player_name, amount_str=amount_str, xp_term=xp_term)

    elif event_type_str == EventType.RELATIONSHIP_CHANGE.value.upper():
        entity1_json = _safe_get(log_entry_details_json, ["entity1"], {})
        e1_id = _safe_get(entity1_json, ["id"])
        e1_type = _safe_get(entity1_json, ["type"], "entity")
        entity2_json = _safe_get(log_entry_details_json, ["entity2"], {})
        e2_id = _safe_get(entity2_json, ["id"])
        e2_type = _safe_get(entity2_json, ["type"], "entity")
        new_value = _safe_get(log_entry_details_json, ["new_value"])
        reason = _safe_get(log_entry_details_json, ["change_reason"]) # Note: key is "change_reason" in log

        e1_name = get_name_from_cache(str(e1_type).lower(), e1_id, str(e1_type).capitalize()) if e1_id and e1_type else await get_term(session, guild_id, language, "terms.general.one_entity", {"en": "One entity", "ru": "Одна сущность"})
        e2_name = get_name_from_cache(str(e2_type).lower(), e2_id, str(e2_type).capitalize()) if e2_id and e2_type else await get_term(session, guild_id, language, "terms.general.another_entity", {"en": "another entity", "ru": "другой сущностью"})
        value_str = str(new_value) if new_value is not None else await get_term(session, guild_id, language, "terms.relationships.an_unknown_level", {"en": "an unknown level", "ru": "неизвестного уровня"})

        relation_between_fmt = await get_term(session, guild_id, language, "terms.relationships.relation_between", {"en": "Relationship between {e1_name} and {e2_name}", "ru": "Отношения между {e1_name} и {e2_name}"})
        is_now_fmt = await get_term(session, guild_id, language, "terms.relationships.is_now", {"en": "is now {value_str}", "ru": "теперь {value_str}"})

        msg = f"{relation_between_fmt.format(e1_name=e1_name, e2_name=e2_name)} {is_now_fmt.format(value_str=value_str)}"
        if reason:
            due_to_reason_fmt = await get_term(session, guild_id, language, "terms.relationships.due_to_reason", {"en": "due to: {change_reason}", "ru": "по причине: {change_reason}"})
            msg += f" ({due_to_reason_fmt.format(change_reason=reason)})."
        else:
            msg += "."
        return msg.strip()

    # --- Handling for generic/system events ---
    elif event_type_str in [
        EventType.SYSTEM_EVENT.value.upper(),
        EventType.WORLD_STATE_CHANGE.value.upper(),
        EventType.MASTER_COMMAND.value.upper(),
        EventType.ERROR_EVENT.value.upper(),
        EventType.AI_GENERATION_TRIGGERED.value.upper(),
        EventType.TRADE_INITIATED.value.upper(),
        EventType.GE_TRIGGERED_DIALOGUE_PLACEHOLDER.value.upper(),
        EventType.TURN_START.value.upper(),
        EventType.TURN_END.value.upper(),
        # Add other less player-facing or generic events here
    ]:
        event_type_readable = event_type_str.replace("_", " ").title() # Use .title() for "System Event" like casing

        event_type_term_key = f"terms.event_types.{event_type_str.lower()}"
        # Default for get_term should be the readable version if no specific term is found
        event_type_display = await get_term(session, guild_id, language, event_type_term_key, {language: event_type_readable, "en": event_type_readable.replace("Ru", "En")}) # crude fallback for ru->en default

        details_to_show = {}
        for k, v in log_entry_details_json.items():
            if k not in ["guild_id", "event_type", "timestamp", "log_id", "player_id_acting_for_turn", "turn_number_for_player", "session_id"]:
                details_to_show[k] = v

        # Format details more like "key: value" rather than all in one line for readability in tests
        details_str_parts = []
        for key, value in details_to_show.items():
            if value is not None:
                 details_str_parts.append(f"{key}: {value}")
        details_str = "; ".join(details_str_parts)

        if details_str:
            # Ensure the default template matches the test expectations more closely
            template_str = await get_term(session, guild_id, language, "terms.general.generic_event_with_details", {"en": "[{event_type_display}]: {details_str}", "ru": "[{event_type_display}]: {details_str}"})
            return template_str.format(event_type_display=event_type_display, details_str=details_str)
        else:
            template_str = await get_term(session, guild_id, language, "terms.general.generic_event_no_details", {"en": "[{event_type_display}] event occurred.", "ru": "Произошло событие [{event_type_display}]."})
            return template_str.format(event_type_display=event_type_display)

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
    # if not log_entries: return "Nothing significant happened."
    # return "Turn report formatted (simplified for overwrite example)."

    # --- Restored logic for format_turn_report ---
    if not log_entries:
        # Get localized "nothing happened" message
        return await get_term( # Re-use get_term from _format_log_entry_with_names_cache context
            session=session, guild_id=guild_id, language=language, # Pass session and guild_id
            term_key_base="terms.turn_report.nothing_significant",
            default_text_map={"en": "Nothing significant happened this turn.", "ru": "Ничего существенного не произошло за этот ход."}
        )


    all_entity_refs: Set[Tuple[str, int]] = set()
    if player_id: # Ensure player_id is added for the report title
        all_entity_refs.add(("player", player_id))

    for entry_details in log_entries:
        all_entity_refs.update(_collect_entity_refs_from_log_entry(entry_details))

    names_cache: Dict[Tuple[str, int], str] = {}
    if all_entity_refs:
        entity_refs_for_batch: List[Dict[str, Any]] = [
            {"type": entity_type, "id": entity_id} for entity_type, entity_id in all_entity_refs
        ]
        # Ensure get_batch_localized_entity_names is available and correctly called
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
        # Ensure guild_id is in entry_details for _format_log_entry_with_names_cache if not already
        if 'guild_id' not in entry_details and guild_id:
            entry_details_copy = entry_details.copy()
            entry_details_copy['guild_id'] = guild_id
            formatted_entry = await _format_log_entry_with_names_cache(session, entry_details_copy, language, names_cache)
        else:
            formatted_entry = await _format_log_entry_with_names_cache(session, entry_details, language, names_cache)
        report_parts.append(f"- {formatted_entry}")

    return "\n".join(report_parts)
    # --- End of restored logic ---


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
