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
)
from .crud.crud_guild import guild_crud as guild_config_crud
from .crud.crud_npc import npc_crud as generated_npc_crud
from .crud.crud_relationship import crud_relationship
from .crud.crud_quest import player_quest_progress_crud, generated_quest_crud, quest_step_crud
from .crud.crud_ability import ability_crud
from .crud.crud_skill import skill_crud


from .rules import get_all_rules_for_guild, get_rule
from .locations_utils import get_localized_text
from ..models.enums import RelationshipEntityType, PlayerStatus


logger = logging.getLogger(__name__)

DEFAULT_QUEST_THEMES = {
    "en": ["artifact hunt", "monster hunt", "local mystery", "escort mission", "gathering resources"],
    "ru": ["поиск артефакта", "охота на монстра", "местная тайна", "миссия сопровождения", "сбор ресурсов"]
}
DEFAULT_WORLD_STATE_I18N = {
    "en": "Global Plot Status: The realm is currently stable, but whispers of ancient prophecies are stirring.",
    "ru": "Статус глобального сюжета: В королевстве сейчас спокойно, но шепот древних пророчеств уже начинает звучать."
}


async def _get_guild_main_language(session: AsyncSession, guild_id: int) -> str:
    guild_config = await guild_config_crud.get(session, id=guild_id)
    return guild_config.main_language if guild_config and guild_config.main_language else "en"

async def _get_location_context(session: AsyncSession, location_id: Optional[int], guild_id: int, lang: str) -> Dict[str, Any]:
    if location_id is None:
        return {"name": "N/A - Not specified.", "description": "No specific location context."}

    location_obj = await location_crud.get(session, id=location_id, guild_id=guild_id)
    if not location_obj:
        return {"name": "N/A - Location Not Found", "description": f"Location ID {location_id} not found."}

    loc_name = get_localized_text(location_obj.name_i18n, lang) or "Unknown Location"
    descriptions_i18n_dict = location_obj.descriptions_i18n if isinstance(location_obj.descriptions_i18n, dict) else {}
    loc_desc = get_localized_text(descriptions_i18n_dict, lang) or "No description available."

    gen_details_i18n_dict = location_obj.generated_details_json if isinstance(location_obj.generated_details_json, dict) else {}
    generated_details = get_localized_text(gen_details_i18n_dict, lang)

    context = {
        "id": location_obj.id,
        "static_id": getattr(location_obj, 'static_id', None),
        "name": loc_name,
        "description": loc_desc,
        "type": location_obj.type.value if hasattr(location_obj.type, 'value') else str(location_obj.type),
        "coordinates": location_obj.coordinates_json if isinstance(location_obj.coordinates_json, dict) else {},
        "generated_details": generated_details or "",
        "ai_metadata": location_obj.ai_metadata_json if isinstance(location_obj.ai_metadata_json, dict) else {},
        "neighbor_static_ids": []
    }

    neighbor_data = location_obj.neighbor_locations_json
    if isinstance(neighbor_data, (str, bytes)):
        try:
            neighbor_data = json.loads(neighbor_data)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in neighbor_locations_json for location {location_id}")
            neighbor_data = []

    if isinstance(neighbor_data, list):
         for neighbor_entry in neighbor_data:
            if isinstance(neighbor_entry, dict):
                for loc_id_int_str, _ in neighbor_entry.items():
                    try:
                        loc_id_int = int(loc_id_int_str)
                        neighbor_loc = await location_crud.get(session, id=loc_id_int, guild_id=guild_id)
                        if neighbor_loc and getattr(neighbor_loc, 'static_id', None):
                            context["neighbor_static_ids"].append(neighbor_loc.static_id)
                    except ValueError:
                        logger.warning(f"Invalid neighbor ID format '{loc_id_int_str}' in location {location_id}")
    return context

async def _get_player_context(session: AsyncSession, player_id: Optional[int], guild_id: int) -> Dict[str, Any]:
    if player_id is None: return {}
    player = await player_crud.get(session, id=player_id, guild_id=guild_id)
    if not player: return {}
    return {
        "id": player.id, "discord_id": player.discord_id, "name": player.name,
        "level": player.level, "xp": player.xp,
        "status": player.current_status.value if player.current_status else "unknown",
    }

async def _get_party_context(session: AsyncSession, party_id: Optional[int], guild_id: int) -> Dict[str, Any]:
    if party_id is None: return {}
    from .crud.crud_party import party_crud
    party = await party_crud.get(session, id=party_id, guild_id=guild_id)
    if not party: return {}
    party_members_details = []
    total_level, member_count = 0, 0
    if party.player_ids_json:
        member_ids = party.player_ids_json
        for member_id in member_ids:
            member = await player_crud.get(session, id=member_id, guild_id=guild_id)
            if member:
                party_members_details.append({"id": member.id, "name": member.name, "level": member.level, "status": member.current_status.value if member.current_status else "unknown"})
                total_level += member.level
                member_count += 1
    average_level = round(total_level / member_count, 2) if member_count > 0 else 0
    return {"id": party.id, "name": party.name, "turn_status": party.turn_status.value if party.turn_status else "unknown", "average_level": average_level, "members": party_members_details}

async def _get_nearby_entities_context(session: AsyncSession, guild_id: int, location_id: Optional[int], lang: str, player_id: Optional[int] = None, party_id: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
    if location_id is None: return {"npcs": []}
    # Corrected call: use `attribute` and provide `is_like`
    npcs_in_location = await generated_npc_crud.get_multi_by_attribute(
        session,
        guild_id=guild_id,
        attribute="current_location_id", # Changed from attribute_name
        value=location_id,
        is_like=False # Explicitly add is_like
    )
    npcs_context = []
    for npc in npcs_in_location:
        if player_id and hasattr(npc, 'player_id_if_controlled') and npc.player_id_if_controlled == player_id : continue
        name_i18n_dict = npc.name_i18n if isinstance(npc.name_i18n, dict) else {}
        desc_i18n_dict = npc.description_i18n if isinstance(npc.description_i18n, dict) else {}
        npcs_context.append({"id": npc.id, "name": get_localized_text(name_i18n_dict, lang), "description": get_localized_text(desc_i18n_dict, lang), "level": npc.level})
    return {"npcs": npcs_context}

async def _get_quests_context(session: AsyncSession, guild_id: int, lang: str, player_id: Optional[int] = None, party_id: Optional[int] = None) -> List[Dict[str, Any]]:
    if player_id is None: return []
    active_quests_context = []
    stmt = select(PlayerQuestProgress, GeneratedQuest, QuestStep).join(GeneratedQuest, PlayerQuestProgress.quest_id == GeneratedQuest.id).join(QuestStep, PlayerQuestProgress.current_step_id == QuestStep.id).where(PlayerQuestProgress.player_id == player_id, PlayerQuestProgress.guild_id == guild_id, PlayerQuestProgress.status.in_(['started', 'in_progress']))
    results = await session.execute(stmt)
    for pqp, quest, step in results.all():
        active_quests_context.append({
            "quest_id": quest.id, "quest_name": get_localized_text(quest.title_i18n if isinstance(quest.title_i18n, dict) else {}, lang),
            "quest_description": get_localized_text(quest.description_i18n if isinstance(quest.description_i18n, dict) else {}, lang),
            "current_step_id": step.id, "current_step_name": get_localized_text(step.title_i18n if isinstance(step.title_i18n, dict) else {}, lang),
            "current_step_description": get_localized_text(step.description_i18n if isinstance(step.description_i18n, dict) else {}, lang),
            "status": pqp.status.value if hasattr(pqp.status, 'value') else str(pqp.status),
        })
    return active_quests_context

async def _get_relationships_context(session: AsyncSession, guild_id: int, lang: str, player_id: Optional[int] = None, party_id: Optional[int] = None, entity_ids_in_location: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    if not player_id or not entity_ids_in_location: return []
    relationships_context = []
    for npc_id in entity_ids_in_location:
        rel_p_npc = await crud_relationship.get_relationship_between_entities(session, guild_id=guild_id, entity1_id=player_id, entity1_type=RelationshipEntityType.PLAYER, entity2_id=npc_id, entity2_type=RelationshipEntityType.GENERATED_NPC)
        if rel_p_npc:
            npc = await generated_npc_crud.get(session, id=npc_id, guild_id=guild_id)
            npc_name = get_localized_text(npc.name_i18n if isinstance(npc.name_i18n, dict) else {}, lang) if npc else f"NPC_{npc_id}"
            relationships_context.append({"entity1_name": "Player", "entity1_id": player_id, "entity1_type": "player", "entity2_name": npc_name, "entity2_id": npc_id, "entity2_type": "npc", "type": rel_p_npc.relationship_type, "value": rel_p_npc.value})
    return relationships_context

async def _get_world_state_context(session: AsyncSession, guild_id: int, lang: str) -> Dict[str, Any]:
    world_flags = {}
    key_flags_to_check = ["world_event_volcano_erupted", "global_quest_artifact_found", "city_under_siege_status"]
    for flag_key in key_flags_to_check:
        flag_value = await get_rule(session, guild_id, f"world_state:{flag_key}", default=None)
        if flag_value is not None: world_flags[flag_key.replace("world_state:", "")] = flag_value
    if not world_flags: return {"global_plot_status": get_localized_text(DEFAULT_WORLD_STATE_I18N, lang)}
    return world_flags

async def _get_game_rules_terms(session: AsyncSession, guild_id: int, lang: str) -> Dict[str, Any]:
    all_rules_dict = await get_all_rules_for_guild(session, guild_id)
    return {
        "main_language_code": all_rules_dict.get("guild_main_language", "en"),
        "generation_style": all_rules_dict.get("ai_generation_style", "classic_fantasy"),
        "allowed_npc_races": all_rules_dict.get("allowed_npc_races", ["human", "elf", "dwarf"]),
        "currency_name": get_localized_text(all_rules_dict.get("currency_name_i18n",{}), lang) or "gold pieces"
    }

async def _get_abilities_skills_terms(session: AsyncSession, guild_id: int, lang: str) -> Dict[str, List[Dict[str, Any]]]:
    # Ensure calls use `attribute` and `is_like` correctly.
    abilities = await ability_crud.get_multi_by_attribute(session, guild_id=guild_id, attribute="id", value=None, is_like=False)
    skills = await skill_crud.get_multi_by_attribute(session, guild_id=guild_id, attribute="id", value=None, is_like=False)
    return {
        "abilities": [{"static_id": ab.static_id, "name": get_localized_text(ab.name_i18n if isinstance(ab.name_i18n, dict) else {}, lang), "description": get_localized_text(ab.description_i18n if isinstance(ab.description_i18n, dict) else {}, lang)} for ab in abilities],
        "skills": [{"static_id": sk.static_id, "name": get_localized_text(sk.name_i18n if isinstance(sk.name_i18n, dict) else {}, lang), "description": get_localized_text(sk.description_i18n if isinstance(sk.description_i18n, dict) else {}, lang)} for sk in skills]
    }

def get_entity_schema_terms() -> Dict[str, Any]: # Renamed: removed leading underscore
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
            "example": { "static_id": "old_man_willow_01", "name_i18n": {"en": "Old Man Willow", "ru": "Старик Ива"}, "description_i18n": {"en": "A weathered old man who seems to know more than he lets on.", "ru": "Пожилой мужчина, который, кажется, знает больше, чем говорит."}, "level": 5, "key_characteristics_i18n": {"en": "Has a mischievous glint in his eyes.", "ru": "В глазах озорной блеск."}}
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
                "steps": {"type": "array", "description": "List of quest steps. Must contain at least one step.", "items": { "$ref": "#/components/schemas/quest_step_schema" }},
                "rewards_json": {"type": "object", "description": "Structured rewards, e.g., {'xp': 100, 'gold': 50, 'item_static_ids': ['item_id_1']}"},
                "ai_metadata_json": {"type": "object", "description": "Optional AI-specific metadata."}
            },
            "required": ["entity_type", "static_id", "title_i18n", "summary_i18n", "steps"]
        },
        "quest_step_schema": {
            "description": "Schema for individual Quest Steps.", "type": "object",
            "properties": {
                "title_i18n": {"type": "object", "description": "Localized step title."},
                "description_i18n": {"type": "object", "description": "Localized step description detailing the objective."},
                "step_order": {"type": "integer", "description": "Order of the step in the quest, starting from 0 or 1."},
                "required_mechanics_json": {"type": "object", "description": "Structured objective. Examples: {'type': 'fetch', ...}"},
                "abstract_goal_json": {"type": "object", "description": "Optional abstract goal..."},
                "consequences_json": {"type": "object", "description": "Optional consequences..."}
            },
            "required": ["title_i18n", "description_i18n", "step_order"]
        },
        "item_schema": {
             "description": "Schema for Items. Ensure 'static_id' is unique for each item generated in this batch.",
             "fields": {
                "entity_type": {"type": "string", "const": "item", "description": "Must be 'item'."},
                "static_id": {"type": "string", "description": "AI-generated unique static ID..."}, "name_i18n": {"type": "object", "description": "Localized item name."},
                "description_i18n": {"type": "object", "description": "Localized item description."},
                "item_type": {"type": "string", "enum": ["weapon", "armor", "consumable", "quest_item", "misc", "currency", "crafting_material"], "description": "Item type."},
                "properties_json": {"type": "object", "description": "Specific properties..."},
                "base_value": {"type": "integer", "description": "Optional: Base monetary value..."}
             }, "required": ["entity_type", "static_id", "name_i18n", "description_i18n", "item_type"]
        },
        "npc_trader_schema": {
            "description": "Schema for NPC Traders...", "allOf": [{"$ref": "#/components/schemas/npc_schema"}], "type": "object",
            "properties": {
                "entity_type": {"type": "string", "const": "npc_trader", "description": "Must be 'npc_trader'."},
                "role_i18n": {"type": "object", "description": "Localized role..."},
                "inventory_template_key": {"type": "string", "description": "Optional key..."},
                "generated_inventory_items": {"type": "array", "description": "Optional list...", "items": {"type": "object", "properties": {"item_static_id": {"type": "string"}, "quantity_min": {"type": "integer", "default": 1, "minimum": 1}, "quantity_max": {"type": "integer", "default": 1, "minimum": 1}, "chance_to_appear": {"type": "number", "format": "float", "minimum": 0.0, "maximum": 1.0, "default": 1.0}}, "required": ["item_static_id"]}}
            }, "required": ["entity_type", "role_i18n"]
        },
        "event_schema": {
            "description": "Schema for dynamic Events...", "fields": {
                "name_i18n": {"type": "object", "description": "Localized event name/title."},
                "description_i18n": {"type": "object", "description": "Detailed description..."},
                "type": {"type": "string", "enum": ["ambient", "encounter", "discovery", "hazard"], "description": "Type of event."},
                "duration_turns": {"type": "integer", "description": "How many game turns..."},
                "trigger_conditions_json": {"type": "object", "description": "Optional conditions..."},
                "outcomes_json": {"type": "object", "description": "Potential outcomes..."}
            }
        },
        "faction_schema": {
            "description": "Schema for Factions.", "fields": {
                "static_id": {"type": "string", "description": "Unique identifier..."}, "name_i18n": {"type": "object", "description": "Localized faction name."},
                "description_i18n": {"type": "object", "description": "Localized faction description."}, "ideology_i18n": {"type": "object", "description": "Localized faction ideology (optional)."},
                "leader_npc_static_id": {"type": "string", "description": "Static ID of an NPC..."}, "resources_json": {"type": "object", "description": "Faction resources..."},
                "ai_metadata_json": {"type": "object", "description": "AI-specific metadata..."}
            }, "example": {"static_id": "guardians_of_light", "name_i18n": {"en": "Guardians of Light", "ru": "Стражи Света"}, "description_i18n": {"en": "A noble order...", "ru": "Благородный орден..."}}
        },
        "relationship_schema": {
            "description": "Schema for Relationships...", "fields": {
                "entity1_static_id": {"type": "string", "description": "Static_id of the first entity..."}, "entity1_type": {"type": "string", "description": "Type of the first entity..."},
                "entity2_static_id": {"type": "string", "description": "Static_id of the second entity."}, "entity2_type": {"type": "string", "description": "Type of the second entity."},
                "relationship_type": {"type": "string", "description": "Type of relationship..."}, "value": {"type": "integer", "description": "Numerical value..."}
            }, "example": {"entity1_static_id": "guardians_of_light", "entity1_type": "faction", "entity2_static_id": "shadow_syndicate", "entity2_type": "faction", "relationship_type": "faction_standing", "value": -75}
        }
    }

@transactional
async def prepare_ai_prompt(session: AsyncSession, guild_id: int, location_id: Optional[int] = None, player_id: Optional[int] = None, party_id: Optional[int] = None) -> str:
    try:
        guild_main_lang = await _get_guild_main_language(session, guild_id)

        print(f"DEBUG: prepare_ai_prompt received location_id: {location_id}, player_id: {player_id}")
        loc_ctx = await _get_location_context(session, location_id, guild_id, guild_main_lang)
        print(f"DEBUG: loc_ctx from _get_location_context: {loc_ctx}")

        player_context_str = ""
        if player_id:
            p_ctx = await _get_player_context(session, player_id, guild_id)
            if p_ctx: player_context_str = f"Player: {p_ctx.get('name')} (Lvl {p_ctx.get('level')}, Status: {p_ctx.get('status')})"

        party_context_str = ""

        nearby_npcs_str_list: List[str] = [] # Explicitly type as List[str]
        if location_id is not None:
            nearby_ctx = await _get_nearby_entities_context(session, guild_id, location_id, guild_main_lang, player_id, party_id)
            if nearby_ctx.get("npcs"):
                for npc_data in nearby_ctx["npcs"][:3]:
                    name_str = str(npc_data.get('name', 'Unknown NPC'))
                    level_str = str(npc_data.get('level', '?'))
                    nearby_npcs_str_list.append(f"{name_str} (Lvl {level_str})")
        nearby_npcs_str = f"Nearby NPCs: {', '.join(nearby_npcs_str_list) if nearby_npcs_str_list else 'None notable'}"


        active_quests_str_list: List[str] = [] # Explicitly type as List[str]
        if player_id:
            quests_ctx = await _get_quests_context(session, guild_id, guild_main_lang, player_id, party_id)
            for q_data in quests_ctx[:2]:
                quest_name_str = str(q_data.get('quest_name', 'Unnamed Quest'))
                step_name_str = str(q_data.get('current_step_name', 'Unknown Step'))
                active_quests_str_list.append(f"'{quest_name_str}' (Step: {step_name_str})")
        active_quests_str = f"Active Quests: {', '.join(active_quests_str_list) if active_quests_str_list else 'None'}"


        ws_ctx = await _get_world_state_context(session, guild_id, guild_main_lang)
        world_state_str = f"World State: {ws_ctx.get('global_plot_status', 'Stable')}"

        all_rules = await get_all_rules_for_guild(session, guild_id)
        generation_style = all_rules.get("ai_generation_style", "classic_fantasy")

        prompt_parts = [
            f"## AI Content Generation Request (Guild: {guild_id}, Lang: {guild_main_lang})",
            f"Location: {loc_ctx.get('name', 'N/A')} - {loc_ctx.get('description', 'Not specified.')}",
            player_context_str, nearby_npcs_str, active_quests_str, world_state_str,
            f"Generation Style: {generation_style}",
            "\n### Generation Task:",
            f"Generate enriching content (NPCs, Quests, Items, Events, Relationships) for '{loc_ctx.get('name', 'this location')}'.",
            "Output: Single JSON with keys 'generated_npcs', 'generated_quests', etc., listing entities per schema.",
            "Ensure all text is i18n (_i18n objects with primary lang and 'en'). Use unique static_ids.",
            "\n### Entity Schemas:", "```json", json.dumps(get_entity_schema_terms(), indent=1), "```"
        ]
        final_prompt = "\n".join(filter(None, prompt_parts))
        logger.info(f"Generated AI prompt (L:{len(final_prompt)}) for guild {guild_id}, loc {location_id}: {final_prompt[:300]}...")
        return final_prompt
    except Exception as e:
        logger.exception(f"Error in prepare_ai_prompt (guild {guild_id}, loc {location_id}): {e}")
        return f"Error generating AI prompt: {str(e)}"

@transactional
async def prepare_faction_relationship_generation_prompt(session: AsyncSession, guild_id: int) -> str:
    try:
        guild_main_lang = await _get_guild_main_language(session, guild_id)
        all_rules = await get_all_rules_for_guild(session, guild_id)
        world_desc_i18n = all_rules.get("world_description_i18n", {"en": "A generic fantasy world."})
        faction_rules = {"target_faction_count": all_rules.get("faction_generation:target_count", 3), "faction_themes": get_localized_text(all_rules.get("faction_generation:themes_i18n",{}), guild_main_lang) or DEFAULT_QUEST_THEMES.get(guild_main_lang,[]), "allow_player_faction_interaction": all_rules.get("faction_generation:allow_player_interaction", True), "world_description": get_localized_text(world_desc_i18n, guild_main_lang)}
        relationship_rules = {"initial_relationship_complexity": all_rules.get("relationship_generation:complexity", "moderate"), "default_relationship_types": all_rules.get("relationship_generation:default_types", ["faction_standing"])}
        entity_schemas = get_entity_schema_terms()
        faction_themes_list = faction_rules['faction_themes']
        if not isinstance(faction_themes_list, list):
            faction_themes_list = [str(faction_themes_list)]
        # Ensure all elements in faction_themes_list are strings for join
        faction_themes_str_list = [str(theme) for theme in faction_themes_list if theme is not None]

        prompt_parts = [
            f"## AI Faction & Relationship Generation (Guild: {guild_id}, Lang: {guild_main_lang})",
            f"World: {faction_rules['world_description']}",
            f"Task: Generate {faction_rules['target_faction_count']} factions with themes like '{', '.join(faction_themes_str_list)}'.",
            f"Then, generate relationships between them (complexity: {relationship_rules['initial_relationship_complexity']}).",
            "If player interaction is allowed, may suggest relations to 'player_default' (type: player).",
            "Output: JSON with 'generated_factions' and 'generated_relationships' lists, per schemas.",
            "All text _i18n (primary lang and 'en'). Use unique static_ids.",
            "\n### Schemas:", "```json", json.dumps({"faction_schema": entity_schemas.get("faction_schema"), "relationship_schema": entity_schemas.get("relationship_schema")}, indent=1), "```"
        ]
        final_prompt = "\n".join(prompt_parts)
        logger.info(f"Generated Faction/Rel prompt (L:{len(final_prompt)}) for guild {guild_id}: {final_prompt[:300]}...")
        return final_prompt
    except Exception as e:
        logger.exception(f"Error in prepare_faction_relationship_generation_prompt for guild {guild_id}: {e}")
        return f"Error generating faction/relationship AI prompt: {str(e)}"

@transactional
async def prepare_quest_generation_prompt(session: AsyncSession, guild_id: int, player_id_context: Optional[int] = None, location_id_context: Optional[int] = None) -> str:
    try:
        guild_main_lang = await _get_guild_main_language(session, guild_id)
        all_rules = await get_all_rules_for_guild(session, guild_id)
        themes_i18n = all_rules.get("ai:quest_generation:themes_i18n", DEFAULT_QUEST_THEMES)
        world_desc_i18n = all_rules.get("world_description_i18n", {"en":"World context"})
        quest_gen_rules = {"target_quest_count": all_rules.get("ai:quest_generation:target_count", 1), "quest_themes": get_localized_text(themes_i18n, guild_main_lang) or DEFAULT_QUEST_THEMES.get(guild_main_lang,[]), "quest_complexity": all_rules.get("ai:quest_generation:complexity", "medium"), "world_description": get_localized_text(world_desc_i18n, guild_main_lang)}
        player_context_str = ""
        if player_id_context:
            p_ctx = await _get_player_context(session, player_id_context, guild_id)
            if p_ctx: player_context_str = f"Player: {p_ctx.get('name')} (Lvl {p_ctx.get('level')})"
        location_context_str = ""
        if location_id_context:
            loc_ctx = await _get_location_context(session, location_id_context, guild_id, guild_main_lang)
            if loc_ctx: location_context_str = f"Location: {loc_ctx.get('name')} ({loc_ctx.get('type')})"
        entity_schemas = get_entity_schema_terms()
        prompt_parts = [
            f"## AI Quest Generation (Guild: {guild_id}, Lang: {guild_main_lang})",
            f"Context: {quest_gen_rules['world_description']}. {player_context_str}. {location_context_str}",
            f"Task: Generate {quest_gen_rules['target_quest_count']} quest(s). Themes: '{json.dumps(quest_gen_rules['quest_themes'])}'. Complexity: {quest_gen_rules['quest_complexity']}.",
            "For each quest: use 'quest_schema'. Steps use 'quest_step_schema'. Define 'required_mechanics_json'.",
            "Output: JSON array of quest objects. All text _i18n (primary lang and 'en'). Unique static_ids.",
            "\n### Schemas:", "```json", json.dumps({"quest_schema": entity_schemas.get("quest_schema"), "quest_step_schema": entity_schemas.get("quest_step_schema")}, indent=1), "```"
        ]
        final_prompt = "\n".join(filter(None, prompt_parts))
        logger.info(f"Generated Quest prompt (L:{len(final_prompt)}) for guild {guild_id}: {final_prompt[:300]}...")
        return final_prompt
    except Exception as e:
        logger.exception(f"Error in prepare_quest_generation_prompt for guild {guild_id}: {e}")
        return f"Error generating quest AI prompt: {str(e)}"

@transactional
async def prepare_economic_entity_generation_prompt(session: AsyncSession, guild_id: int) -> str:
    try:
        guild_main_lang = await _get_guild_main_language(session, guild_id)
        all_rules = await get_all_rules_for_guild(session, guild_id)
        target_item_count = all_rules.get("ai:economic_generation:target_item_count", {}).get("count", 5)
        target_trader_count = all_rules.get("ai:economic_generation:target_trader_count", {}).get("count", 2)
        world_desc_i18n = all_rules.get("world_description_i18n", {"en":"World context"})
        world_desc = get_localized_text(world_desc_i18n, guild_main_lang)
        quality_instr_i18n = all_rules.get("ai:economic_generation:quality_instructions_i18n", {})
        quality_instr = get_localized_text(quality_instr_i18n, guild_main_lang)
        item_dist_str = json.dumps(all_rules.get("ai:economic_generation:item_type_distribution", {}).get("types", []))
        trader_dist_str = json.dumps(all_rules.get("ai:economic_generation:trader_role_distribution", {}).get("roles", []))
        entity_schemas = get_entity_schema_terms()
        prompt_parts = [
            f"## AI Economic Entity Generation (Guild: {guild_id}, Lang: {guild_main_lang})",
            f"Context: {world_desc}. {quality_instr}",
            f"Task: Generate {target_item_count} items and {target_trader_count} NPC traders.",
            f"Item types inspiration: {item_dist_str}. Trader roles inspiration: {trader_dist_str}.",
            "For Items: use 'item_schema'. For Traders: use 'npc_trader_schema'. Unique static_ids.",
            "Trader inventory: use 'inventory_template_key' (from RuleConfig context if provided) or 'generated_inventory_items'.",
            "Output: JSON array of item/trader objects. All text _i18n (primary lang and 'en').",
            "\n### Schemas:", "```json", json.dumps({"item_schema": entity_schemas.get("item_schema"), "npc_trader_schema": entity_schemas.get("npc_trader_schema"), "npc_schema": entity_schemas.get("npc_schema")}, indent=1), "```"
        ]
        final_prompt = "\n".join(filter(None, prompt_parts))
        logger.info(f"Generated Economic Entity prompt (L:{len(final_prompt)}) for guild {guild_id}: {final_prompt[:300]}...")
        return final_prompt
    except Exception as e:
        logger.exception(f"Error in prepare_economic_entity_generation_prompt for guild {guild_id}: {e}")
        return f"Error generating economic entity AI prompt: {str(e)}"

async def _get_hidden_relationships_context_for_dialogue(session: AsyncSession, guild_id: int, lang: str, npc_id: int, player_id: Optional[int] = None) -> List[Dict[str, Any]]:
    hidden_relationships_context = []
    if npc_id is None: # Added check for None npc_id
        logger.warning("_get_hidden_relationships_context_for_dialogue called with npc_id=None")
        return []
    npc_all_relationships = await crud_relationship.get_relationships_for_entity(session=session, guild_id=guild_id, entity_id=npc_id, entity_type=RelationshipEntityType.GENERATED_NPC)
    if not npc_all_relationships: return []
    hidden_prefixes = ("secret_", "internal_", "personal_debt", "hidden_fear", "betrayal_")
    relevant_hidden_rels: List[Relationship] = [rel for rel in npc_all_relationships if isinstance(rel.relationship_type, str) and rel.relationship_type.startswith(hidden_prefixes)]
    for rel in relevant_hidden_rels:
        other_entity_id = rel.entity1_id if rel.entity2_id == npc_id else rel.entity2_id
        other_entity_type_enum = rel.entity1_type if rel.entity2_id == npc_id else rel.entity2_type
        rel_ctx = {"relationship_type": rel.relationship_type, "value": rel.value, "target_entity_id": other_entity_id, "target_entity_type": other_entity_type_enum.value, "prompt_hints": "", "unlocks_tags": [], "options_availability_formula": None}
        rule_key = f"hidden_relationship_effects:dialogue:{rel.relationship_type.split(':')[0]}"
        rule_data = await get_rule(session, guild_id, rule_key, default=None)
        if rule_data and isinstance(rule_data, dict) and rule_data.get("enabled", False):
            hints_i18n = rule_data.get("prompt_modifier_hints_i18n", {})
            hint_template = get_localized_text(hints_i18n, lang)
            if hint_template: rel_ctx["prompt_hints"] = hint_template.replace("{value}", str(rel.value))
            rel_ctx["unlocks_tags"] = rule_data.get("unlocks_dialogue_options_tags", [])
            rel_ctx["options_availability_formula"] = rule_data.get("dialogue_option_availability_formula")
        hidden_relationships_context.append(rel_ctx)
    return hidden_relationships_context

async def _get_npc_memory_context_stub(session: AsyncSession, guild_id: int, npc_id: int, player_id: int, party_id: Optional[int]) -> List[str]:
    logger.debug(f"NPC Memory STUB: Called for NPC {npc_id}, Player {player_id}, Party {party_id} in Guild {guild_id}")
    memories = []
    if random.random() < 0.3: memories.append("NPC Memory STUB: Player once helped me with a small task.")
    if player_id % 3 == 0 : memories.append("NPC Memory STUB: Player seemed suspicious during our last encounter.")
    if not memories: memories.append("NPC Memory STUB: No particularly strong memories of the player recently.")
    return memories

async def prepare_dialogue_generation_prompt(session: AsyncSession, guild_id: int, context: Dict[str, Any]) -> str:
    try:
        npc_id_any = context.get("npc_id")
        player_id_any = context.get("player_id")
        player_input_text = context.get("player_input_text")
        party_id = context.get("party_id") # Optional
        dialogue_history = context.get("dialogue_history", []) # Optional
        location_id = context.get("location_id") # Optional

        # Validate required parameters and their types
        if not isinstance(npc_id_any, int):
            logger.error(f"Invalid or missing npc_id in context: {npc_id_any}")
            return "Error: Missing or invalid NPC ID for dialogue."
        if not isinstance(player_id_any, int):
            logger.error(f"Invalid or missing player_id in context: {player_id_any}")
            return "Error: Missing or invalid Player ID for dialogue."
        if not isinstance(player_input_text, str):
            logger.error(f"Invalid or missing player_input_text in context: {player_input_text}")
            return "Error: Missing or invalid player input text for dialogue."

        npc_id: int = npc_id_any
        player_id: int = player_id_any

        guild_main_lang = await _get_guild_main_language(session, guild_id)
        all_rules = await get_all_rules_for_guild(session, guild_id)
        prompt_parts = [f"## NPC Dialogue Generation Request", f"Target Guild ID: {guild_id}", f"Language for NPC's response: {guild_main_lang} (Also be aware of English for game terms if they appear in context).", "\n### Characters Involved:"]
        npc: Optional[GeneratedNpc] = await generated_npc_crud.get(session, id=npc_id, guild_id=guild_id)
        if not npc: return f"Error: NPC with ID {npc_id} not found in guild {guild_id}."
        npc_name = get_localized_text(npc.name_i18n if isinstance(npc.name_i18n, dict) else {}, guild_main_lang)
        npc_desc = get_localized_text(npc.description_i18n if isinstance(npc.description_i18n, dict) else {}, guild_main_lang)
        npc_properties = npc.properties_json if isinstance(npc.properties_json, dict) else {}
        role_i18n = npc_properties.get("role_i18n", {})
        npc_role = get_localized_text(role_i18n if isinstance(role_i18n, dict) else {}, guild_main_lang)
        personality_i18n = npc_properties.get("personality_i18n", {})
        npc_personality = get_localized_text(personality_i18n if isinstance(personality_i18n, dict) else {}, guild_main_lang) or "neutral"
        dialogue_style_hint_i18n = npc_properties.get("dialogue_style_hint_i18n", {})
        npc_dialogue_style_hint = get_localized_text(dialogue_style_hint_i18n if isinstance(dialogue_style_hint_i18n, dict) else {}, guild_main_lang)
        prompt_parts.append(f"**You are {npc_name}.**")
        prompt_parts.append(f"  - Your Description: {npc_desc}")
        if npc_role: prompt_parts.append(f"  - Your Role/Profession: {npc_role}")
        prompt_parts.append(f"  - Your General Personality Traits: {npc_personality}")
        if npc_dialogue_style_hint: prompt_parts.append(f"  - Your Dialogue Style Hint: {npc_dialogue_style_hint}")
        player: Optional[Player] = await player_crud.get(session, id=player_id, guild_id=guild_id)
        if not player: return f"Error: Player with ID {player_id} not found in guild {guild_id}."
        player_name = player.name
        prompt_parts.append(f"\n**You are speaking with {player_name} (the Player).**")
        prompt_parts.append(f"  - Player Level: {player.level}")
        if party_id:
            from .crud.crud_party import party_crud
            party_obj = await party_crud.get(session, id=party_id, guild_id=guild_id)
            if party_obj:
                party_members_details = []
                if party_obj.player_ids_json:
                    for member_id_in_party in party_obj.player_ids_json:
                        member_player = await player_crud.get(session, id=member_id_in_party, guild_id=guild_id)
                        if member_player: party_members_details.append(f"{member_player.name} (Lvl {member_player.level})")
                party_info_str = f"{party_obj.name}" + (f" with members: {', '.join(party_members_details)}" if party_members_details else " (currently no listed members)")
                prompt_parts.append(f"  - Player is part of Party: {party_info_str}")
        prompt_parts.append("\n### Current Situation:")
        if location_id:
            loc_ctx = await _get_location_context(session, location_id, guild_id, guild_main_lang)
            if loc_ctx and loc_ctx.get("name") != "N/A - Location Not Found":
                prompt_parts.append(f"  Location: {loc_ctx.get('name', 'Unknown')} ({loc_ctx.get('type', 'N/A')}) - {loc_ctx.get('description', '')}")
                if loc_ctx.get('generated_details'): prompt_parts.append(f"    Extra details: {loc_ctx.get('generated_details')}")
        nearby_entities_ctx = await _get_nearby_entities_context(session, guild_id, location_id, guild_main_lang, player_id, party_id)
        if nearby_entities_ctx.get("npcs"):
            other_npc_names = [n.get('name') for n in nearby_entities_ctx["npcs"] if n.get('id') != npc_id and n.get('name')]
            if other_npc_names: prompt_parts.append(f"  Other notable individuals nearby: {', '.join(other_npc_names[:3])}{' and possibly others.' if len(other_npc_names) > 3 else '.'}")
        world_state_ctx = await _get_world_state_context(session, guild_id, guild_main_lang)
        if world_state_ctx:
            prompt_parts.append("  Relevant World State Snippets:")
            for key, value in list(world_state_ctx.items())[:3]: prompt_parts.append(f"    - {key.replace('_', ' ').title()}: {value}")
        prompt_parts.append("\n### Relationship and Memory Context:")
        player_npc_rel = await crud_relationship.get_relationship_between_entities(session, guild_id, player_id, RelationshipEntityType.PLAYER, npc_id, RelationshipEntityType.GENERATED_NPC)
        if player_npc_rel: prompt_parts.append(f"  Your current relationship with {player_name}: Type: {player_npc_rel.relationship_type}, Value: {player_npc_rel.value} (e.g., -100 hostile to 100 allied).")
        else: prompt_parts.append(f"  You have no established specific relationship with {player_name} (assume neutral).")
        hidden_rels_ctx = await _get_hidden_relationships_context_for_dialogue(session, guild_id, guild_main_lang, npc_id, player_id)
        if hidden_rels_ctx:
            prompt_parts.append("  Some of your relevant hidden feelings or relationships:")
            for h_rel in hidden_rels_ctx[:2]:
                hint = h_rel.get("prompt_hints") or f"Towards entity ID {h_rel['target_entity_id']} ({h_rel['target_entity_type']}): Type '{h_rel['relationship_type']}', Value {h_rel['value']}."
                prompt_parts.append(f"    - {hint}")
        npc_memory_entries = await _get_npc_memory_context_stub(session, guild_id, npc_id, player_id, party_id)
        if npc_memory_entries:
            prompt_parts.append("  Recent notable memories involving the player:")
            for mem_entry in npc_memory_entries[:2]: prompt_parts.append(f"    - {mem_entry}")
        active_quests_ctx = await _get_quests_context(session, guild_id, guild_main_lang, player_id, party_id)
        if active_quests_ctx:
            relevant_quests = [f"'{q.get('quest_name')}' (step: '{q.get('current_step_name')}')" for q in active_quests_ctx[:2] if q.get('quest_name')]
            if relevant_quests:
                prompt_parts.append("\n### Relevant Active Quests for the Player:")
                for i_q, rq_str in enumerate(relevant_quests): prompt_parts.append(f"  {i_q+1}. {rq_str}")
        prompt_parts.append("\n### Dialogue So Far:")
        if not dialogue_history: prompt_parts.append("  (This is the beginning of the conversation).")
        else:
            for line in dialogue_history[-5:]:
                speaker_name = player_name if line.get("speaker") == "player" else npc_name
                prompt_parts.append(f"  {speaker_name}: {line.get('text')}")
        prompt_parts.append(f"\n{player_name} says to you: \"{player_input_text}\"")
        prompt_parts.append("\n### Your Task:")
        prompt_parts.append(f"You are {npc_name}. Based on ALL context (personality, relationship, situation, memory, quests, dialogue history), generate your next single, natural-sounding dialogue line. Be concise. Respond in **{guild_main_lang}**.")
        prompt_parts.append("Do NOT add prefixes like 'NPC:' or out-of-character remarks.")
        dialogue_rules_parts = []
        npc_static_id = npc.static_id or "default"
        guidelines_key = f"dialogue_rules:npc_general_guidelines:{npc_static_id}"
        guidelines = all_rules.get(guidelines_key) or all_rules.get("dialogue_rules:npc_general_guidelines:default")
        if guidelines and isinstance(guidelines, dict):
            guidelines_i18n = guidelines.get("guidelines_i18n",{})
            guideline_text = get_localized_text(guidelines_i18n, guild_main_lang)
            if guideline_text: dialogue_rules_parts.append(f"  - General Guideline: {guideline_text}")
        tone_rules_key = f"dialogue_rules:npc_tone_modifiers:{npc_static_id}"
        tone_rules = all_rules.get(tone_rules_key) or all_rules.get("dialogue_rules:npc_tone_modifiers:default")
        if tone_rules and isinstance(tone_rules, list):
            dialogue_rules_parts.append("  - Tone Guidance (consider relationship value):")
            for rule in tone_rules[:2]:
                if isinstance(rule, dict):
                    condition_i18n = rule.get('condition_description_i18n',{})
                    cond = get_localized_text(condition_i18n, guild_main_lang) or rule.get('condition','')
                    tone_hint_i18n = rule.get('tone_hint_i18n',{})
                    hint = get_localized_text(tone_hint_i18n, guild_main_lang)
                    if cond and hint: dialogue_rules_parts.append(f"    - If {cond}: lean towards '{hint}'.")
        # --- Начало интеграции влияния отношений на тон (Шаг 2 текущего плана) ---
        relationship_dialogue_rule_key = "relationship_influence:dialogue:availability_and_tone"
        relationship_dialogue_config = await get_rule(session, guild_id, relationship_dialogue_rule_key, default=None)

        derived_tone_hint = None
        if relationship_dialogue_config and isinstance(relationship_dialogue_config, dict) and "tone_modifiers" in relationship_dialogue_config:
            tone_modifiers = relationship_dialogue_config["tone_modifiers"]
            if isinstance(tone_modifiers, list) and player_npc_rel:
                current_relationship_value = player_npc_rel.value
                default_tone_hint_from_rule = None

                for modifier in sorted(tone_modifiers, key=lambda x: x.get("relationship_above", -float('inf')), reverse=True):
                    if modifier.get("relationship_default", False):
                        default_tone_hint_from_rule = modifier.get("tone_hint")
                        # Не выходим сразу, вдруг есть более специфичное правило, которое подойдет

                    if "relationship_above" in modifier and current_relationship_value > modifier["relationship_above"]:
                        derived_tone_hint = modifier.get("tone_hint")
                        break # Используем первое совпавшее правило (отсортированы по убыванию порога)

                if derived_tone_hint is None and default_tone_hint_from_rule is not None:
                    derived_tone_hint = default_tone_hint_from_rule

            if derived_tone_hint:
                 logger.info(f"Derived tone_hint '{derived_tone_hint}' from rule '{relationship_dialogue_rule_key}' for NPC {npc_id} and Player {player_id} (Relationship: {player_npc_rel.value if player_npc_rel else 'N/A'})")


        # --- Конец интеграции влияния отношений на тон ---

        if dialogue_rules_parts:
            prompt_parts.append("\n### Specific Dialogue Guidelines (from Game Rules for you):")
            prompt_parts.extend(dialogue_rules_parts)

        # Добавляем derived_tone_hint в промпт, если он был определен
        if derived_tone_hint:
            prompt_parts.append(f"  - Your current emotional tone towards {player_name} should reflect: **{derived_tone_hint}**.")

        final_prompt = "\n".join(prompt_parts)
        logger.info(f"Generated AI dialogue prompt (L:{len(final_prompt)}) for NPC {npc_id}, Player {player_id}, Guild {guild_id}. Start: {final_prompt[:350]}...")
        return final_prompt
    except Exception as e:
        logger.exception(f"Error in prepare_dialogue_generation_prompt for guild {guild_id}, context: {context}: {e}")
        return f"Error: Internal error generating dialogue prompt: {str(e)}"
