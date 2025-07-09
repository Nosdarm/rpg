import json
import logging
from typing import Optional, Dict, Any, List
import random

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from .database import get_db_session, transactional
from ..models import (
    GuildConfig, Location, Player, Party, GeneratedNpc, Relationship,
    PlayerQuestProgress, GeneratedQuest, QuestStep, RuleConfig, Ability, Skill
)
from .crud import (
    location_crud, player_crud,
    # party_crud, # party_crud импортируется ниже как actual_party_crud
    # generated_npc_crud, # npc_crud импортируется ниже как actual_npc_crud
    # relationship_crud, # relationship_crud импортируется ниже как actual_crud_relationship
)
# CRUD инстансы, которые могут быть еще заглушками, но код должен их использовать
# По мере реализации реальных CRUD, эти импорты будут заменены или подтверждены
from .crud.crud_guild import guild_crud as guild_config_crud # Используем реальный CRUD с alias
from .crud.crud_npc import npc_crud as generated_npc_crud # Используем реальный CRUD, alias соответствует старому использованию
from .crud.crud_relationship import crud_relationship # Используем реальный CRUD
from .crud.crud_quest import player_quest_progress_crud, generated_quest_crud, quest_step_crud # Используем реальные CRUD для квестов
from .crud.crud_ability import ability_crud # Используем реальный CRUD
from .crud.crud_skill import skill_crud # Используем реальный CRUD


from .rules import get_all_rules_for_guild, get_rule
from .locations_utils import get_localized_text
from ..models.enums import RelationshipEntityType


logger = logging.getLogger(__name__)

DEFAULT_QUEST_THEMES = {
    "en": ["artifact hunt", "monster hunt", "local mystery", "escort mission", "gathering resources"],
    "ru": ["поиск артефакта", "охота на монстра", "местная тайна", "миссия сопровождения", "сбор ресурсов"]
}

async def _get_guild_main_language(session: AsyncSession, guild_id: int) -> str:
    guild_config = await guild_config_crud.get(session, id=guild_id, guild_id=guild_id) # Передаем guild_id как id и как guild_id для совместимости
    return guild_config.main_language if guild_config else "en"

async def _get_location_context(session: AsyncSession, location_id: Optional[int], guild_id: int, lang: str) -> Dict[str, Any]:
    if location_id is None:
        return {}
    location = await location_crud.get(session, id=location_id, guild_id=guild_id)
    if not location:
        return {}

    context = {
        "id": location.id,
        "static_id": location.static_id,
        "name": get_localized_text(location.name_i18n, lang, "en"),
        "description": get_localized_text(location.descriptions_i18n, lang, "en"),
        "type": location.type.value if location.type else "unknown",
        "coordinates": location.coordinates_json,
        "generated_details": get_localized_text(location.generated_details_json, lang, "en") if location.generated_details_json else "",
        "ai_metadata": location.ai_metadata_json,
        "neighbor_static_ids": []
    }
    if location.neighbor_locations_json:
        try:
            neighbor_data = location.neighbor_locations_json
            if isinstance(neighbor_data, list):
                 for neighbor_entry in neighbor_data:
                    if isinstance(neighbor_entry, dict): # Добавлена проверка
                        for loc_id_int_str, _ in neighbor_entry.items():
                            try:
                                loc_id_int = int(loc_id_int_str)
                                neighbor_loc = await location_crud.get(session, id=loc_id_int, guild_id=guild_id)
                                if neighbor_loc and neighbor_loc.static_id: # Проверка на static_id
                                    context["neighbor_static_ids"].append(neighbor_loc.static_id)
                            except ValueError:
                                logger.warning(f"Invalid neighbor ID format '{loc_id_int_str}' in location {location_id}")
            elif isinstance(neighbor_data, dict):
                 for loc_id_int_str, _ in neighbor_data.items():
                    try:
                        loc_id_int = int(loc_id_int_str)
                        neighbor_loc = await location_crud.get(session, id=loc_id_int, guild_id=guild_id)
                        if neighbor_loc and neighbor_loc.static_id: # Проверка на static_id
                            context["neighbor_static_ids"].append(neighbor_loc.static_id)
                    except ValueError:
                        logger.warning(f"Invalid neighbor ID format '{loc_id_int_str}' in location {location_id}")
        except Exception as e: # Более общий Exception
            logger.error(f"Error parsing neighbor_locations_json for location {location_id} in guild {guild_id}: {e}")
    return context

async def _get_player_context(session: AsyncSession, player_id: int, guild_id: int) -> Dict[str, Any]:
    player = await player_crud.get(session, id=player_id, guild_id=guild_id)
    if not player:
        return {}
    return {
        "id": player.id,
        "discord_id": player.discord_id,
        "name": player.name,
        "level": player.level,
        "xp": player.xp,
        "status": player.current_status.value if player.current_status else "unknown",
    }

async def _get_party_context(session: AsyncSession, party_id: int, guild_id: int) -> Dict[str, Any]:
    from .crud.crud_party import party_crud as actual_party_crud # Используем реальный CRUD
    party = await actual_party_crud.get(session, id=party_id, guild_id=guild_id)
    if not party:
        return {}

    party_members_details = []
    total_level = 0
    member_count = 0

    if party.player_ids_json:
        member_ids = party.player_ids_json
        for member_id in member_ids:
            member = await player_crud.get(session, id=member_id, guild_id=guild_id)
            if member:
                party_members_details.append({
                    "id": member.id, "name": member.name, "level": member.level,
                    "status": member.current_status.value if member.current_status else "unknown"
                })
                total_level += member.level
                member_count += 1
    average_level = total_level / member_count if member_count > 0 else 0
    return {
        "id": party.id,
        "name": party.name,
        "turn_status": party.turn_status.value if party.turn_status else "unknown",
        "average_level": round(average_level, 2),
        "members": party_members_details,
    }

async def _get_nearby_entities_context(session: AsyncSession, guild_id: int, location_id: Optional[int], lang: str,
                                     player_id: Optional[int] = None, party_id: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
    if location_id is None:
        return {"npcs": []}
    # Используем generated_npc_crud, который теперь должен быть реальным или замененным на реальный
    npcs_in_location = await generated_npc_crud.get_multi_by_attribute(
        session, guild_id=guild_id, current_location_id=location_id
    )
    npcs_context = []
    for npc in npcs_in_location:
        if player_id and hasattr(npc, 'player_id_if_controlled') and npc.player_id_if_controlled == player_id :
            continue
        npcs_context.append({
            "id": npc.id,
            "name": get_localized_text(npc.name_i18n, lang, "en"),
            "description": get_localized_text(npc.description_i18n, lang, "en"),
            "level": npc.level,
        })
    return {"npcs": npcs_context}

async def _get_quests_context(session: AsyncSession, guild_id: int, lang: str,
                            player_id: Optional[int] = None, party_id: Optional[int] = None) -> List[Dict[str, Any]]:
    active_quests_context = []
    entity_id_for_quests = player_id
    if not entity_id_for_quests: return []

    # Используем реальные CRUD для квестов
    stmt = (
        select(PlayerQuestProgress, GeneratedQuest, QuestStep)
        .join(GeneratedQuest, PlayerQuestProgress.quest_id == GeneratedQuest.id)
        .join(QuestStep, PlayerQuestProgress.current_quest_step_id == QuestStep.id)
        .where(PlayerQuestProgress.player_id == entity_id_for_quests,
               PlayerQuestProgress.guild_id == guild_id,
               PlayerQuestProgress.status.in_(['started', 'in_progress'])) # Используем строки для QuestStatus
    )
    results = await session.execute(stmt)
    for pqp, quest, step in results.all():
        active_quests_context.append({
            "quest_id": quest.id,
            "quest_name": get_localized_text(quest.title_i18n, lang, "en"), # title_i18n вместо name_i18n
            "quest_description": get_localized_text(quest.description_i18n, lang, "en"), # description_i18n вместо summary_i18n
            "current_step_id": step.id,
            "current_step_name": get_localized_text(step.title_i18n, lang, "en"), # title_i18n вместо name_i18n
            "current_step_description": get_localized_text(step.description_i18n, lang, "en"),
            "status": pqp.status.value if hasattr(pqp.status, 'value') else str(pqp.status),
        })
    return active_quests_context

async def _get_relationships_context(session: AsyncSession, guild_id: int, lang: str,
                                   player_id: Optional[int] = None, party_id: Optional[int] = None,
                                   entity_ids_in_location: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    relationships_context = []
    if not player_id or not entity_ids_in_location:
        return []

    # Используем реальный crud_relationship
    for npc_id in entity_ids_in_location:
        rel_p_npc = await crud_relationship.get_relationship_between_entities(session, guild_id=guild_id,
                                                            entity1_id=player_id, entity1_type=RelationshipEntityType.PLAYER,
                                                            entity2_id=npc_id, entity2_type=RelationshipEntityType.GENERATED_NPC)
        if rel_p_npc:
            npc = await generated_npc_crud.get(session, id=npc_id, guild_id=guild_id)
            npc_name = get_localized_text(npc.name_i18n, lang, "en") if npc else f"NPC_{npc_id}"
            relationships_context.append({
                "entity1_name": "Player", "entity1_id": player_id, "entity1_type": "player",
                "entity2_name": npc_name, "entity2_id": npc_id, "entity2_type": "npc",
                "type": rel_p_npc.relationship_type, "value": rel_p_npc.value
            })
    return relationships_context

async def _get_world_state_context(session: AsyncSession, guild_id: int) -> Dict[str, Any]:
    # Загрузка нескольких ключевых флагов из RuleConfig как пример
    world_flags = {}
    key_flags_to_check = ["world_event_volcano_erupted", "global_quest_artifact_found", "city_under_siege_status"]
    for flag_key in key_flags_to_check:
        flag_value = await get_rule(session, guild_id, f"world_state:{flag_key}", default=None)
        if flag_value is not None:
            world_flags[flag_key.replace("world_state:", "")] = flag_value

    if not world_flags: # Если ничего не найдено, возвращаем заглушку
        return {"global_plot_status": "The realm is currently stable, but whispers of ancient prophecies are stirring."}
    return world_flags


async def _get_game_rules_terms(session: AsyncSession, guild_id: int) -> Dict[str, Any]:
    all_rules_dict = await get_all_rules_for_guild(session, guild_id)
    return {
        "main_language_code": all_rules_dict.get("guild_main_language", "en"),
        "generation_style": all_rules_dict.get("ai_generation_style", "classic_fantasy"),
        "allowed_npc_races": all_rules_dict.get("allowed_npc_races", ["human", "elf", "dwarf"]),
        "currency_name": all_rules_dict.get("currency_name_i18n",{}).get(all_rules_dict.get("guild_main_language", "en"), "gold pieces")
    }

async def _get_abilities_skills_terms(session: AsyncSession, guild_id: int, lang: str) -> Dict[str, List[Dict[str, Any]]]:
    abilities = await ability_crud.get_multi_by_attribute(session, guild_id=guild_id)
    skills = await skill_crud.get_multi_by_attribute(session, guild_id=guild_id)
    return {
        "abilities": [{
            "static_id": ab.static_id, "name": get_localized_text(ab.name_i18n, lang, "en"),
            "description": get_localized_text(ab.description_i18n, lang, "en")
        } for ab in abilities],
        "skills": [{
            "static_id": sk.static_id, "name": get_localized_text(sk.name_i18n, lang, "en"),
            "description": get_localized_text(sk.description_i18n, lang, "en")
        } for sk in skills]
    }

def _get_entity_schema_terms() -> Dict[str, Any]:
    # Существующая функция _get_entity_schema_terms остается без изменений
    return {
        "npc_schema": {
            "description": "Schema for Non-Player Characters (NPCs).",
            "fields": {
                "static_id": {"type": "string", "description": "Unique static identifier for this NPC, e.g., 'guard_captain_reynold'. Should be unique at least within the current generation batch for relationship linking."},
                "name_i18n": {"type": "object", "description": "Localized names (e.g., {'en': 'Name', 'ru': 'Имя'})"},
                "description_i18n": {"type": "object", "description": "Localized descriptions."},
                "level": {"type": "integer", "description": "NPC's level."},
                "faction_static_id": {"type": "string", "description": "Static ID of the faction they belong to (optional)."},
                "key_characteristics_i18n": {"type": "object", "description": "Notable features or personality traits."},
                "initial_dialogue_i18n": {"type": "object", "description": "A starting dialogue line or greeting."},
                "inventory_items_static_ids": {"type": "array", "items": "string", "description": "List of static_ids of items NPC carries."},
                "abilities_static_ids": {"type": "array", "items": "string", "description": "List of static_ids of abilities NPC has."}
            },
            "example": {
                "static_id": "old_man_willow_01",
                "name_i18n": {"en": "Old Man Willow", "ru": "Старик Ива"},
                "description_i18n": {"en": "A weathered old man who seems to know more than he lets on.", "ru": "Пожилой мужчина, который, кажется, знает больше, чем говорит."},
                "level": 5,
                "key_characteristics_i18n": {"en": "Has a mischievous glint in his eyes.", "ru": "В глазах озорной блеск."},
            }
        },
        "quest_schema": {
            "description": "Schema for Generated Quests. Ensure 'static_id' is unique for each quest generated in this batch.",
            "fields": {
                "entity_type": {"type": "string", "const": "quest", "description": "Must be 'quest'."},
                "static_id": {"type": "string", "description": "AI-generated unique static ID for this quest (e.g., 'forest_ruins_artifact')."},
                "title_i18n": {"type": "object", "description": "Localized quest title (e.g., {'en': 'Title', 'ru': 'Заголовок'})."},
                "summary_i18n": {"type": "object", "description": "Localized overall quest summary/description."},
                "questline_static_id": {"type": "string", "description": "Optional static_id of a questline this quest belongs to."},
                "giver_entity_type": {"type": "string", "description": "Optional type of entity giving the quest (e.g., 'npc', 'item')."},
                "giver_entity_static_id": {"type": "string", "description": "Optional static_id of the NPC or item giving the quest."},
                "min_level": {"type": "integer", "description": "Optional minimum player level suggested for this quest."},
                "steps": {
                    "type": "array",
                    "description": "List of quest steps. Must contain at least one step.",
                    "items": {
                        "$ref": "#/components/schemas/quest_step_schema"
                    }
                },
                "rewards_json": {"type": "object", "description": "Structured rewards, e.g., {'xp': 100, 'gold': 50, 'item_static_ids': ['item_id_1']}"},
                "ai_metadata_json": {"type": "object", "description": "Optional AI-specific metadata."}
            },
            "required": ["entity_type", "static_id", "title_i18n", "summary_i18n", "steps"]
        },
        "quest_step_schema": {
            "description": "Schema for individual Quest Steps.",
            "type": "object",
            "properties": {
                "title_i18n": {"type": "object", "description": "Localized step title."},
                "description_i18n": {"type": "object", "description": "Localized step description detailing the objective."},
                "step_order": {"type": "integer", "description": "Order of the step in the quest, starting from 0 or 1."},
                "required_mechanics_json": {
                    "type": "object",
                    "description": "Structured objective. Examples: {'type': 'fetch', 'item_static_id': 'ancient_scroll', 'count': 1, 'target_npc_static_id_for_delivery': 'hermit_joe'}, {'type': 'kill', 'target_npc_static_id': 'goblin_leader', 'count': 1}, {'type': 'explore', 'location_static_id': 'hidden_cave'}, {'type': 'dialogue', 'target_npc_static_id': 'village_elder', 'required_dialogue_outcome_tag': 'information_revealed'}"
                },
                "abstract_goal_json": {
                    "type": "object",
                    "description": "Optional abstract goal for more complex steps, e.g., {'description_i18n': {'en': 'Gain the trust of the village elder.', 'ru': 'Завоевать доверие старейшины деревни.'}, 'evaluation_criteria_tags': ['trust_earned', 'elder_friendly']}"
                },
                "consequences_json": {
                    "type": "object",
                    "description": "Optional consequences of completing this step, e.g., {'relationship_change': {'target_faction_static_id': 'village_guard', 'delta': 10}, 'world_state_update': {'state_key': 'bridge_repaired', 'new_value': True}}"
                }
            },
            "required": ["title_i18n", "description_i18n", "step_order"]
        },
        "item_schema": {
             "description": "Schema for Items. Ensure 'static_id' is unique for each item generated in this batch.",
             "fields": {
                "entity_type": {"type": "string", "const": "item", "description": "Must be 'item'."},
                "static_id": {"type": "string", "description": "AI-generated unique static ID for this item (e.g., 'healing_potion_minor', 'steel_sword_common')."},
                "name_i18n": {"type": "object", "description": "Localized item name."},
                "description_i18n": {"type": "object", "description": "Localized item description."},
                "item_type": {"type": "string", "enum": ["weapon", "armor", "consumable", "quest_item", "misc", "currency", "crafting_material"], "description": "Item type."},
                "properties_json": {"type": "object", "description": "Specific properties, e.g., {'damage': '1d6', 'armor_value': 5, 'effect': 'heal_2d4', 'slot_type': 'weapon'}"},
                "base_value": {"type": "integer", "description": "Optional: Base monetary value in the smallest currency unit (e.g., copper pieces)."}
             },
             "required": ["entity_type", "static_id", "name_i18n", "description_i18n", "item_type"]
        },
        "npc_trader_schema": {
            "description": "Schema for NPC Traders. Inherits general NPC fields (like static_id, name_i18n, description_i18n, level) and adds trader-specific ones. Ensure 'static_id' is unique if provided, or one will be generated.",
            "allOf": [{"$ref": "#/components/schemas/npc_schema"}],
            "type": "object",
            "properties": {
                "entity_type": {"type": "string", "const": "npc_trader", "description": "Must be 'npc_trader'."},
                "role_i18n": {"type": "object", "description": "Localized role of the trader (e.g., {'en': 'Blacksmith', 'ru': 'Кузнец'})."},
                "inventory_template_key": {"type": "string", "description": "Optional key for a RuleConfig entry defining their inventory template (e.g., 'general_store_owner_template')."},
                "generated_inventory_items": {
                    "type": "array",
                    "description": "Optional list of specific items the trader has if not using a template. Each item should specify 'item_static_id', 'quantity_min', 'quantity_max', 'chance_to_appear'.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item_static_id": {"type": "string"},
                            "quantity_min": {"type": "integer", "default": 1, "minimum": 1},
                            "quantity_max": {"type": "integer", "default": 1, "minimum": 1},
                            "chance_to_appear": {"type": "number", "format": "float", "minimum": 0.0, "maximum": 1.0, "default": 1.0}
                        },
                        "required": ["item_static_id"]
                    }
                }
            },
            "required": ["entity_type", "role_i18n"]
        },
        "event_schema": {
            "description": "Schema for dynamic Events that can occur in a location.",
            "fields": {
                "name_i18n": {"type": "object", "description": "Localized event name/title."},
                "description_i18n": {"type": "object", "description": "Detailed description of the event unfolding."},
                "type": {"type": "string", "enum": ["ambient", "encounter", "discovery", "hazard"], "description": "Type of event."},
                "duration_turns": {"type": "integer", "description": "How many game turns this event might last (approx)."},
                "trigger_conditions_json": {"type": "object", "description": "Optional conditions for this event to trigger, e.g., {'time_of_day': 'night', 'player_has_item_static_id': '...'}"},
                "outcomes_json": {"type": "object", "description": "Potential outcomes or choices and their consequences."}
            }
        },
        "faction_schema": {
            "description": "Schema for Factions.",
            "fields": {
                "static_id": {"type": "string", "description": "Unique identifier for the faction, generated by AI (e.g., 'red_brigade', 'merchant_guild')."},
                "name_i18n": {"type": "object", "description": "Localized faction name."},
                "description_i18n": {"type": "object", "description": "Localized faction description."},
                "ideology_i18n": {"type": "object", "description": "Localized faction ideology (optional)."},
                "leader_npc_static_id": {"type": "string", "description": "Static ID of an NPC intended to be the leader (optional, can be linked later)."},
                "resources_json": {"type": "object", "description": "Faction resources, e.g., {'wealth': 1000, 'influence': 50} (optional)."},
                "ai_metadata_json": {"type": "object", "description": "AI-specific metadata, e.g., {'archetype': 'warlike', 'initial_goals': ['...']} (optional)."}
            },
            "example": {
                "static_id": "guardians_of_light",
                "name_i18n": {"en": "Guardians of Light", "ru": "Стражи Света"},
                "description_i18n": {"en": "A noble order dedicated to protecting the innocent.", "ru": "Благородный орден, посвященный защите невинных."}
            }
        },
        "relationship_schema": {
            "description": "Schema for Relationships between entities (primarily factions here).",
            "fields": {
                "entity1_static_id": {"type": "string", "description": "Static_id of the first entity (e.g., a faction's static_id)."},
                "entity1_type": {"type": "string", "description": "Type of the first entity (e.g., 'faction')."},
                "entity2_static_id": {"type": "string", "description": "Static_id of the second entity."},
                "entity2_type": {"type": "string", "description": "Type of the second entity."},
                "relationship_type": {"type": "string", "description": "Type of relationship, e.g., 'faction_standing', 'alliance_status', 'rivalry_level'."},
                "value": {"type": "integer", "description": "Numerical value of the relationship (e.g., -100 to 100)."}
            },
            "example": {
                "entity1_static_id": "guardians_of_light",
                "entity1_type": "faction",
                "entity2_static_id": "shadow_syndicate",
                "entity2_type": "faction",
                "relationship_type": "faction_standing",
                "value": -75
            }
        }
    }

@transactional
async def prepare_ai_prompt(
    session: AsyncSession,
    guild_id: int,
    location_id: Optional[int],
    player_id: Optional[int] = None,
    party_id: Optional[int] = None
) -> str:
    try:
        guild_main_lang = await _get_guild_main_language(session, guild_id)
        location_context = await _get_location_context(session, location_id, guild_id, guild_main_lang)
        if not location_context and location_id is not None: # location_id был предоставлен, но контекст не найден
            logger.warning(f"Location {location_id} not found for guild {guild_id} during prompt generation.")
            # Можно вернуть ошибку или продолжить с ограниченным контекстом
            # return "Error: Location not found for prompt context."

        player_context_str = ""
        if player_id:
            p_ctx = await _get_player_context(session, player_id, guild_id)
            if p_ctx: player_context_str = f"Player: {p_ctx.get('name')} (Lvl {p_ctx.get('level')}, Status: {p_ctx.get('status')})"

        party_context_str = ""
        if party_id:
            pa_ctx = await _get_party_context(session, party_id, guild_id)
            if pa_ctx: party_context_str = f"Party: {pa_ctx.get('name')} (AvgLvl {pa_ctx.get('average_level')}, Members: {len(pa_ctx.get('members',[]))})"

        nearby_npcs_str_list = []
        if location_id is not None: # Только если есть локация
            nearby_ctx = await _get_nearby_entities_context(session, guild_id, location_id, guild_main_lang, player_id, party_id)
            if nearby_ctx.get("npcs"):
                for npc_data in nearby_ctx["npcs"][:3]: # Первые 3 для краткости
                    nearby_npcs_str_list.append(f"{npc_data.get('name')} (Lvl {npc_data.get('level')})")
        nearby_npcs_str = f"Nearby NPCs: {', '.join(nearby_npcs_str_list) or 'None notable'}"

        active_quests_str_list = []
        if player_id: # Квесты обычно привязаны к игроку
            quests_ctx = await _get_quests_context(session, guild_id, guild_main_lang, player_id, party_id)
            for q_data in quests_ctx[:2]: # Первые 2 для краткости
                active_quests_str_list.append(f"'{q_data.get('quest_name')}' (Step: {q_data.get('current_step_name')})")
        active_quests_str = f"Active Quests: {', '.join(active_quests_str_list) or 'None'}"

        world_state_snippets = []
        ws_ctx = await _get_world_state_context(session, guild_id)
        for k,v in list(ws_ctx.items())[:3]: world_state_snippets.append(f"{k.replace('_',' ').title()}: {v}")
        world_state_str = f"World State: {'; '.join(world_state_snippets) or 'Stable'}"


        prompt_parts = [
            f"## AI Content Generation Request (Guild: {guild_id}, Lang: {guild_main_lang})",
            f"Location: {location_context.get('name', 'N/A')} - {location_context.get('description', 'Not specified.')}",
            player_context_str, party_context_str, nearby_npcs_str, active_quests_str, world_state_str,
            "\n### Generation Task:",
            f"Generate enriching content (NPCs, Quests, Items, Events, Relationships) for '{location_context.get('name', 'this location')}'.",
            "Output: Single JSON with keys 'generated_npcs', 'generated_quests', etc., listing entities per schema.",
            "Ensure all text is i18n (_i18n objects with primary lang and 'en'). Use unique static_ids.",
            "\n### Entity Schemas:",
            "```json",
            json.dumps(_get_entity_schema_terms(), indent=1), # Компактный JSON
            "```"
        ]

        final_prompt = "\n".join(filter(None, prompt_parts)) # Убираем пустые строки из контекста
        logger.info(f"Generated AI prompt (L:{len(final_prompt)}) for guild {guild_id}, loc {location_id}: {final_prompt[:300]}...")
        return final_prompt
    except Exception as e:
        logger.exception(f"Error in prepare_ai_prompt (guild {guild_id}, loc {location_id}): {e}")
        return f"Error generating AI prompt: {str(e)}"

@transactional
async def prepare_faction_relationship_generation_prompt(
    session: AsyncSession,
    guild_id: int
) -> str:
    try:
        guild_main_lang = await _get_guild_main_language(session, guild_id)
        all_rules = await get_all_rules_for_guild(session, guild_id)

        faction_rules = {
            "target_faction_count": all_rules.get("faction_generation:target_count", 3),
            "faction_themes": all_rules.get("faction_generation:themes_i18n",{}).get(guild_main_lang, DEFAULT_QUEST_THEMES.get(guild_main_lang, [])),
            "allow_player_faction_interaction": all_rules.get("faction_generation:allow_player_interaction", True),
            "world_description": get_localized_text(all_rules.get("world_description_i18n", {"en": "A generic fantasy world."}), guild_main_lang)
        }
        relationship_rules = {
            "initial_relationship_complexity": all_rules.get("relationship_generation:complexity", "moderate"),
            "default_relationship_types": all_rules.get("relationship_generation:default_types", ["faction_standing"])
        }
        entity_schemas = _get_entity_schema_terms()

        prompt_parts = [
            f"## AI Faction & Relationship Generation (Guild: {guild_id}, Lang: {guild_main_lang})",
            f"World: {faction_rules['world_description']}",
            f"Task: Generate {faction_rules['target_faction_count']} factions with themes like '{', '.join(faction_rules['faction_themes'])}'.",
            f"Then, generate relationships between them (complexity: {relationship_rules['initial_relationship_complexity']}).",
            "If player interaction is allowed, may suggest relations to 'player_default' (type: player).",
            "Output: JSON with 'generated_factions' and 'generated_relationships' lists, per schemas.",
            "All text _i18n (primary lang and 'en'). Use unique static_ids.",
            "\n### Schemas:",
            "```json",
            json.dumps({"faction_schema": entity_schemas.get("faction_schema"), "relationship_schema": entity_schemas.get("relationship_schema")}, indent=1),
            "```"
        ]
        final_prompt = "\n".join(prompt_parts)
        logger.info(f"Generated Faction/Rel prompt (L:{len(final_prompt)}) for guild {guild_id}: {final_prompt[:300]}...")
        return final_prompt
    except Exception as e:
        logger.exception(f"Error in prepare_faction_relationship_generation_prompt for guild {guild_id}: {e}")
        return f"Error generating faction/relationship AI prompt: {str(e)}"


@transactional
async def prepare_quest_generation_prompt(
    session: AsyncSession,
    guild_id: int,
    player_id_context: Optional[int] = None,
    location_id_context: Optional[int] = None
) -> str:
    try:
        guild_main_lang = await _get_guild_main_language(session, guild_id)
        all_rules = await get_all_rules_for_guild(session, guild_id)

        quest_gen_rules = {
            "target_quest_count": all_rules.get("ai:quest_generation:target_count", 1),
            "quest_themes": get_localized_text(all_rules.get("ai:quest_generation:themes_i18n", DEFAULT_QUEST_THEMES), guild_main_lang),
            "quest_complexity": all_rules.get("ai:quest_generation:complexity", "medium"),
            "world_description": get_localized_text(all_rules.get("world_description_i18n", {"en":"World context"}), guild_main_lang)
        }

        player_context_str = ""
        if player_id_context:
            p_ctx = await _get_player_context(session, player_id_context, guild_id)
            if p_ctx: player_context_str = f"Player: {p_ctx.get('name')} (Lvl {p_ctx.get('level')})"

        location_context_str = ""
        if location_id_context:
            loc_ctx = await _get_location_context(session, location_id_context, guild_id, guild_main_lang)
            if loc_ctx: location_context_str = f"Location: {loc_ctx.get('name')} ({loc_ctx.get('type')})"

        entity_schemas = _get_entity_schema_terms()

        prompt_parts = [
            f"## AI Quest Generation (Guild: {guild_id}, Lang: {guild_main_lang})",
            f"Context: {quest_gen_rules['world_description']}. {player_context_str}. {location_context_str}",
            f"Task: Generate {quest_gen_rules['target_quest_count']} quest(s). Themes: '{quest_gen_rules['quest_themes']}'. Complexity: {quest_gen_rules['quest_complexity']}.",
            "For each quest: use 'quest_schema'. Steps use 'quest_step_schema'. Define 'required_mechanics_json'.",
            "Output: JSON array of quest objects. All text _i18n (primary lang and 'en'). Unique static_ids.",
            "\n### Schemas:",
            "```json",
            json.dumps({"quest_schema": entity_schemas.get("quest_schema"), "quest_step_schema": entity_schemas.get("quest_step_schema")}, indent=1),
            "```"
        ]
        final_prompt = "\n".join(filter(None, prompt_parts))
        logger.info(f"Generated Quest prompt (L:{len(final_prompt)}) for guild {guild_id}: {final_prompt[:300]}...")
        return final_prompt
    except Exception as e:
        logger.exception(f"Error in prepare_quest_generation_prompt for guild {guild_id}: {e}")
        return f"Error generating quest AI prompt: {str(e)}"

@transactional
async def prepare_economic_entity_generation_prompt(
    session: AsyncSession,
    guild_id: int
) -> str:
    try:
        guild_main_lang = await _get_guild_main_language(session, guild_id)
        all_rules = await get_all_rules_for_guild(session, guild_id)

        target_item_count = all_rules.get("ai:economic_generation:target_item_count", {}).get("count", 5)
        target_trader_count = all_rules.get("ai:economic_generation:target_trader_count", {}).get("count", 2)
        world_desc = get_localized_text(all_rules.get("world_description_i18n", {"en":"World context"}), guild_main_lang)
        quality_instr = get_localized_text(all_rules.get("ai:economic_generation:quality_instructions_i18n", {}), guild_main_lang)

        item_dist_str = json.dumps(all_rules.get("ai:economic_generation:item_type_distribution", {}).get("types", []))
        trader_dist_str = json.dumps(all_rules.get("ai:economic_generation:trader_role_distribution", {}).get("roles", []))

        entity_schemas = _get_entity_schema_terms()
        prompt_parts = [
            f"## AI Economic Entity Generation (Guild: {guild_id}, Lang: {guild_main_lang})",
            f"Context: {world_desc}. {quality_instr}",
            f"Task: Generate {target_item_count} items and {target_trader_count} NPC traders.",
            f"Item types inspiration: {item_dist_str}. Trader roles inspiration: {trader_dist_str}.",
            "For Items: use 'item_schema'. For Traders: use 'npc_trader_schema'. Unique static_ids.",
            "Trader inventory: use 'inventory_template_key' (from RuleConfig context if provided) or 'generated_inventory_items'.",
            "Output: JSON array of item/trader objects. All text _i18n (primary lang and 'en').",
            "\n### Schemas:",
            "```json",
            json.dumps({"item_schema": entity_schemas.get("item_schema"),
                         "npc_trader_schema": entity_schemas.get("npc_trader_schema"),
                         "npc_schema": entity_schemas.get("npc_schema")}, indent=1),
            "```"
        ]
        final_prompt = "\n".join(filter(None, prompt_parts))
        logger.info(f"Generated Economic Entity prompt (L:{len(final_prompt)}) for guild {guild_id}: {final_prompt[:300]}...")
        return final_prompt
    except Exception as e:
        logger.exception(f"Error in prepare_economic_entity_generation_prompt for guild {guild_id}: {e}")
        return f"Error generating economic entity AI prompt: {str(e)}"


async def _get_hidden_relationships_context_for_dialogue(
    session: AsyncSession,
    guild_id: int,
    lang: str,
    npc_id: int,
    player_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    hidden_relationships_context = []
    from .crud.crud_relationship import crud_relationship as actual_crud_relationship

    npc_all_relationships = await actual_crud_relationship.get_relationships_for_entity(
        session=session,
        guild_id=guild_id,
        entity_id=npc_id,
        entity_type=RelationshipEntityType.GENERATED_NPC
    )
    if not npc_all_relationships: return []

    hidden_prefixes = ("secret_", "internal_", "personal_debt", "hidden_fear", "betrayal_")
    relevant_hidden_rels: List[Relationship] = [
        rel for rel in npc_all_relationships if rel.relationship_type.startswith(hidden_prefixes)
    ]

    for rel in relevant_hidden_rels:
        other_entity_id = rel.entity1_id if rel.entity2_id == npc_id else rel.entity2_id
        other_entity_type_enum = rel.entity1_type if rel.entity2_id == npc_id else rel.entity2_type
        rel_ctx = {
            "relationship_type": rel.relationship_type, "value": rel.value,
            "target_entity_id": other_entity_id, "target_entity_type": other_entity_type_enum.value,
            "prompt_hints": "", "unlocks_tags": [], "options_availability_formula": None
        }
        rule_key = f"hidden_relationship_effects:dialogue:{rel.relationship_type.split(':')[0]}"
        rule_data = await get_rule(session, guild_id, rule_key, default=None)
        if rule_data and isinstance(rule_data, dict) and rule_data.get("enabled", False):
            hints_i18n = rule_data.get("prompt_modifier_hints_i18n", {})
            hint_template = get_localized_text(hints_i18n, lang)
            if hint_template:
                rel_ctx["prompt_hints"] = hint_template.replace("{value}", str(rel.value))
            rel_ctx["unlocks_tags"] = rule_data.get("unlocks_dialogue_options_tags", [])
            rel_ctx["options_availability_formula"] = rule_data.get("dialogue_option_availability_formula")
        hidden_relationships_context.append(rel_ctx)
    return hidden_relationships_context


async def _get_npc_memory_context_stub(
    session: AsyncSession, guild_id: int, npc_id: int, player_id: int, party_id: Optional[int]
) -> List[str]:
    logger.debug(f"NPC Memory STUB: Called for NPC {npc_id}, Player {player_id}, Party {party_id} in Guild {guild_id}")
    memories = []
    # from .crud.crud_player_npc_memory import player_npc_memory_crud # hypothetical
    # raw_memories = await player_npc_memory_crud.get_memories_for_npc_player(session, guild_id, npc_id, player_id)
    # for mem in raw_memories:
    # memories.append(f"Memory: Event type {mem.event_type}, Details: {get_localized_text(mem.memory_details_i18n, lang)}")
    if random.random() < 0.3: memories.append("NPC Memory STUB: Player once helped me with a small task.")
    if player_id % 3 == 0 : memories.append("NPC Memory STUB: Player seemed suspicious during our last encounter.")
    if not memories: memories.append("NPC Memory STUB: No particularly strong memories of the player recently.")
    return memories


async def prepare_dialogue_generation_prompt(
    session: AsyncSession,
    guild_id: int,
    context: Dict[str, Any]
) -> str:
    try:
        npc_id = context.get("npc_id")
        player_id = context.get("player_id")
        player_input_text = context.get("player_input_text")
        party_id = context.get("party_id")
        dialogue_history = context.get("dialogue_history", [])
        location_id = context.get("location_id")

        if not all([isinstance(npc_id, int), isinstance(player_id, int), isinstance(player_input_text, str)]):
            missing_params = [
                p for p, v in [("npc_id", npc_id), ("player_id", player_id), ("player_input_text", player_input_text)]
                if not isinstance(v, (int if "id" in p else str))
            ]
            err_msg = f"Missing or invalid required parameters in context for dialogue prompt: {missing_params}"
            logger.error(err_msg)
            return f"Error: {err_msg}"

        guild_main_lang = await _get_guild_main_language(session, guild_id)
        all_rules = await get_all_rules_for_guild(session, guild_id)

        prompt_parts = []
        prompt_parts.append("## NPC Dialogue Generation Request")
        prompt_parts.append(f"Target Guild ID: {guild_id}")
        prompt_parts.append(f"Language for NPC's response: {guild_main_lang} (Also be aware of English for game terms if they appear in context).")

        prompt_parts.append("\n### Characters Involved:")

        from .crud.crud_npc import npc_crud as actual_npc_crud
        npc: Optional[GeneratedNpc] = await actual_npc_crud.get(session, id=npc_id, guild_id=guild_id)
        if not npc:
            return f"Error: NPC with ID {npc_id} not found in guild {guild_id}."

        npc_name = get_localized_text(npc.name_i18n, guild_main_lang)
        npc_desc = get_localized_text(npc.description_i18n, guild_main_lang)
        npc_properties = npc.properties_json if isinstance(npc.properties_json, dict) else {}
        npc_role = get_localized_text(npc_properties.get("role_i18n", {}), guild_main_lang)
        npc_personality = get_localized_text(npc_properties.get("personality_i18n", {}), guild_main_lang) or "neutral"
        npc_dialogue_style_hint = get_localized_text(npc_properties.get("dialogue_style_hint_i18n", {}), guild_main_lang, "") # Fallback to empty string

        prompt_parts.append(f"**You are {npc_name}.**")
        prompt_parts.append(f"  - Your Description: {npc_desc}")
        if npc_role: prompt_parts.append(f"  - Your Role/Profession: {npc_role}")
        prompt_parts.append(f"  - Your General Personality Traits: {npc_personality}")
        if npc_dialogue_style_hint: prompt_parts.append(f"  - Your Dialogue Style Hint: {npc_dialogue_style_hint}")

        player: Optional[Player] = await player_crud.get(session, id=player_id, guild_id=guild_id)
        if not player:
            return f"Error: Player with ID {player_id} not found in guild {guild_id}."
        player_name = player.name

        prompt_parts.append(f"\n**You are speaking with {player_name} (the Player).**")
        prompt_parts.append(f"  - Player Level: {player.level}")

        if party_id:
            from .crud.crud_party import party_crud as actual_party_crud
            party_obj = await actual_party_crud.get(session, id=party_id, guild_id=guild_id)
            if party_obj:
                party_members_details = []
                if party_obj.player_ids_json:
                    for member_id_in_party in party_obj.player_ids_json:
                        member_player = await player_crud.get(session, id=member_id_in_party, guild_id=guild_id)
                        if member_player:
                            party_members_details.append(f"{member_player.name} (Lvl {member_player.level})")
                party_info_str = f"{party_obj.name}" + (f" with members: {', '.join(party_members_details)}" if party_members_details else " (currently no listed members)")
                prompt_parts.append(f"  - Player is part of Party: {party_info_str}")

        prompt_parts.append("\n### Current Situation:")
        if location_id:
            loc_ctx = await _get_location_context(session, location_id, guild_id, guild_main_lang)
            if loc_ctx:
                prompt_parts.append(f"  Location: {loc_ctx.get('name', 'Unknown')} ({loc_ctx.get('type', 'N/A')}) - {loc_ctx.get('description', '')}")
                if loc_ctx.get('generated_details'): prompt_parts.append(f"    Extra details: {loc_ctx.get('generated_details')}")

        nearby_entities_ctx = await _get_nearby_entities_context(session, guild_id, location_id, guild_main_lang, player_id, party_id)
        if nearby_entities_ctx.get("npcs"):
            other_npc_names = [n.get('name') for n in nearby_entities_ctx["npcs"] if n.get('id') != npc_id]
            if other_npc_names:
                prompt_parts.append(f"  Other notable individuals nearby: {', '.join(other_npc_names[:3])}{' and possibly others.' if len(other_npc_names) > 3 else '.'}")

        world_state_ctx = await _get_world_state_context(session, guild_id)
        if world_state_ctx:
            prompt_parts.append("  Relevant World State Snippets:")
            for key, value in list(world_state_ctx.items())[:3]:
                prompt_parts.append(f"    - {key.replace('_', ' ').title()}: {value}")

        prompt_parts.append("\n### Relationship and Memory Context:")
        from .crud.crud_relationship import crud_relationship as actual_crud_relationship

        player_npc_rel = await actual_crud_relationship.get_relationship_between_entities(
            session, guild_id, player_id, RelationshipEntityType.PLAYER, npc_id, RelationshipEntityType.GENERATED_NPC
        )
        if player_npc_rel:
            prompt_parts.append(f"  Your current relationship with {player_name}: Type: {player_npc_rel.relationship_type}, Value: {player_npc_rel.value} (e.g., -100 hostile to 100 allied).")
        else:
            prompt_parts.append(f"  You have no established specific relationship with {player_name} (assume neutral).")

        hidden_rels_ctx = await _get_hidden_relationships_context_for_dialogue(session, guild_id, guild_main_lang, npc_id, player_id)
        if hidden_rels_ctx:
            prompt_parts.append("  Some of your relevant hidden feelings or relationships:")
            for h_rel in hidden_rels_ctx[:2]: # Max 2 for brevity
                hint = h_rel.get("prompt_hints") or f"Towards entity ID {h_rel['target_entity_id']} ({h_rel['target_entity_type']}): Type '{h_rel['relationship_type']}', Value {h_rel['value']}."
                prompt_parts.append(f"    - {hint}")

        npc_memory_entries = await _get_npc_memory_context_stub(session, guild_id, npc_id, player_id, party_id)
        if npc_memory_entries:
            prompt_parts.append("  Recent notable memories involving the player:")
            for mem_entry in npc_memory_entries[:2]: # Max 2 for brevity
                prompt_parts.append(f"    - {mem_entry}")

        active_quests_ctx = await _get_quests_context(session, guild_id, guild_main_lang, player_id, party_id)
        if active_quests_ctx:
            relevant_quests = [f"'{q.get('quest_name')}' (step: '{q.get('current_step_name')}')" for q in active_quests_ctx[:2]]
            if relevant_quests:
                prompt_parts.append("\n### Relevant Active Quests for the Player:")
                for i, rq_str in enumerate(relevant_quests): prompt_parts.append(f"  {i+1}. {rq_str}")

        prompt_parts.append("\n### Dialogue So Far:")
        if not dialogue_history:
            prompt_parts.append("  (This is the beginning of the conversation).")
        else:
            for line in dialogue_history[-5:]:
                speaker_name = player_name if line.get("speaker") == "player" else npc_name
                prompt_parts.append(f"  {speaker_name}: {line.get('text')}")
        prompt_parts.append(f"\n**{player_name} says to you**: \"{player_input_text}\"")

        prompt_parts.append("\n### Your Task:")
        prompt_parts.append(f"You are {npc_name}. Based on ALL context (personality, relationship, situation, memory, quests, dialogue history), generate your next single, natural-sounding dialogue line. Be concise. Respond in **{guild_main_lang}**.")
        prompt_parts.append("Do NOT add prefixes like 'NPC:' or out-of-character remarks.")

        dialogue_rules_parts = []
        npc_static_id = npc.static_id or "default"
        guidelines_key = f"dialogue_rules:npc_general_guidelines:{npc_static_id}"
        guidelines = all_rules.get(guidelines_key) or all_rules.get("dialogue_rules:npc_general_guidelines:default")
        if guidelines and isinstance(guidelines, dict):
            guideline_text = get_localized_text(guidelines.get("guidelines_i18n",{}), guild_main_lang)
            if guideline_text: dialogue_rules_parts.append(f"  - General Guideline: {guideline_text}")

        tone_rules_key = f"dialogue_rules:npc_tone_modifiers:{npc_static_id}"
        tone_rules = all_rules.get(tone_rules_key) or all_rules.get("dialogue_rules:npc_tone_modifiers:default")
        if tone_rules and isinstance(tone_rules, list):
            dialogue_rules_parts.append("  - Tone Guidance (consider relationship value):")
            for rule in tone_rules[:2]: # Max 2 rules for brevity
                if isinstance(rule, dict):
                    cond = get_localized_text(rule.get('condition_description_i18n',{}),guild_main_lang, rule.get('condition',''))
                    hint = get_localized_text(rule.get('tone_hint_i18n',{}),guild_main_lang)
                    if cond and hint: dialogue_rules_parts.append(f"    - If {cond}: lean towards '{hint}'.")

        if dialogue_rules_parts:
            prompt_parts.append("\n### Specific Dialogue Guidelines (from Game Rules for you):")
            prompt_parts.extend(dialogue_rules_parts)

        final_prompt = "\n".join(prompt_parts)
        logger.info(f"Generated AI dialogue prompt (L:{len(final_prompt)}) for NPC {npc_id}, Player {player_id}, Guild {guild_id}. Start: {final_prompt[:350]}...")
        return final_prompt
    except Exception as e:
        logger.exception(f"Error in prepare_dialogue_generation_prompt for guild {guild_id}, context: {context}: {e}")
        return f"Error: Internal error generating dialogue prompt: {str(e)}"

# Остальные функции файла (prepare_ai_prompt, prepare_faction_relationship_generation_prompt, etc.) остаются без изменений.
# Убедитесь, что этот код заменяет ТОЛЬКО существующую prepare_dialogue_generation_prompt и добавляет _get_npc_memory_context_stub,
# не затрагивая другие `prepare_..._prompt` функции.
# Однако, для полноты и избежания ошибок слияния, я предоставляю ВЕСЬ файл ai_prompt_builder.py с изменениями.
# Если это нежелательно, сообщите, и я предоставлю только измененные функции.
# Для данного вызова я закомментирую остальные функции, чтобы применился только нужный блок.

"""
@transactional
async def prepare_ai_prompt(
    session: AsyncSession,
    guild_id: int,
    location_id: Optional[int],
    player_id: Optional[int] = None,
    party_id: Optional[int] = None
) -> str:
    # ... (существующий код этой функции) ...
    pass

@transactional
async def prepare_faction_relationship_generation_prompt(
    session: AsyncSession,
    guild_id: int
) -> str:
    # ... (существующий код этой функции) ...
    pass

@transactional
async def prepare_quest_generation_prompt(
    session: AsyncSession,
    guild_id: int,
    player_id_context: Optional[int] = None,
    location_id_context: Optional[int] = None
) -> str:
    # ... (существующий код этой функции) ...
    pass

@transactional
async def prepare_economic_entity_generation_prompt(
    session: AsyncSession,
    guild_id: int
) -> str:
    # ... (существующий код этой функции) ...
    pass
"""
