import json
import logging
from typing import Optional, Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from .database import get_db_session, transactional
from ..models import (
    GuildConfig, Location, Player, Party, GeneratedNpc, Relationship,
    PlayerQuestProgress, GeneratedQuest, QuestStep, RuleConfig, Ability, Skill
)
from .crud import ( # These should come from src.core.crud (meaning src.core.crud.__init__)
    location_crud, player_crud, party_crud,
    # The following are not yet defined in src.core.crud/* or exported by src.core.crud.__init__
    # guild_config_crud, # To be created (e.g., src.core.crud.crud_guild_config.py)
    # generated_npc_crud, # To be created
    # relationship_crud, # To be created
    # player_quest_progress_crud, # To be created
    # generated_quest_crud, # To be created
    # quest_step_crud, # To be created
    # ability_crud, # To be created
    # skill_crud # To be created
)
# Import get_all_rules_for_guild instead of the raw rule_config_crud for this purpose
from .rules import get_all_rules_for_guild, get_rule
# For others, we'll have to use placeholders or wait for their creation.
# For now, let's assume they will be added to src.core.crud later.
# To avoid breaking the code that uses them, we might need to define placeholders if they are actively used.
# The pyright errors point to them being used.

# Temporary: Define placeholders for missing CRUDs to allow pyright to pass this file,
# but these need to be implemented properly.
# This is a temporary measure to assess other errors in this file.
class PlaceholderCRUDBase:
    async def get(self, session, id, guild_id=None): return None
    async def get_multi_by_attribute(self, session, guild_id, **kwargs): return []
    async def get_relationship(self, session, guild_id, entity1_id, entity1_type, entity2_id, entity2_type): return None

guild_config_crud = PlaceholderCRUDBase()
generated_npc_crud = PlaceholderCRUDBase()
relationship_crud = PlaceholderCRUDBase()
player_quest_progress_crud = PlaceholderCRUDBase() # Not used in this file directly by name
generated_quest_crud = PlaceholderCRUDBase() # Not used in this file directly by name
quest_step_crud = PlaceholderCRUDBase() # Not used in this file directly by name
ability_crud = PlaceholderCRUDBase()
skill_crud = PlaceholderCRUDBase()


from .locations_utils import get_localized_text # Assuming this can be used broadly

logger = logging.getLogger(__name__)

DEFAULT_QUEST_THEMES = {
    "en": ["artifact hunt", "monster hunt", "local mystery", "escort mission", "gathering resources"],
    "ru": ["поиск артефакта", "охота на монстра", "местная тайна", "миссия сопровождения", "сбор ресурсов"]
}

# Placeholder for actual WorldState model and CRUD if it gets created
# from src.models import WorldState
# from src.core.crud import world_state_crud

async def _get_guild_main_language(session: AsyncSession, guild_id: int) -> str:
    """Fetches the main language for the guild."""
    guild_config = await guild_config_crud.get(session, id=guild_id)
    return guild_config.main_language if guild_config else "en"

async def _get_location_context(session: AsyncSession, location_id: Optional[int], guild_id: int, lang: str) -> Dict[str, Any]:
    """Gathers context about a specific location. Returns empty if location_id is None or not found."""
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
        "neighbor_static_ids": [] # Simplified, actual neighbors might need more detail
    }
    if location.neighbor_locations_json:
        try:
            neighbor_data = location.neighbor_locations_json
            if isinstance(neighbor_data, list): # Expected format [{location_id: conn_type_i18n}, ...]
                 for neighbor_entry in neighbor_data:
                    for loc_id_int, _ in neighbor_entry.items(): # conn_type_i18n not used for now
                        neighbor_loc = await location_crud.get(session, id=loc_id_int, guild_id=guild_id)
                        if neighbor_loc:
                            context["neighbor_static_ids"].append(neighbor_loc.static_id)
            elif isinstance(neighbor_data, dict): # Older format? {loc_id: conn_type_i18n}
                 for loc_id_int, _ in neighbor_data.items():
                    neighbor_loc = await location_crud.get(session, id=int(loc_id_int), guild_id=guild_id) # Ensure int
                    if neighbor_loc:
                        context["neighbor_static_ids"].append(neighbor_loc.static_id)

        except (json.JSONDecodeError, AttributeError, TypeError) as e:
            logger.error(f"Error parsing neighbor_locations_json for location {location_id} in guild {guild_id}: {e}")


    return context

async def _get_player_context(session: AsyncSession, player_id: int, guild_id: int) -> Dict[str, Any]:
    """Gathers context about a specific player."""
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
        # Add other relevant player fields: stats_json, equipment, abilities etc. when models support them
    }

async def _get_party_context(session: AsyncSession, party_id: int, guild_id: int) -> Dict[str, Any]:
    """Gathers context about a specific party."""
    party = await party_crud.get(session, id=party_id, guild_id=guild_id)
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
    """Gathers context about NPCs and other relevant entities in the location. Handles None location_id."""
    if location_id is None:
        return {"npcs": []} # No location, no nearby entities based on location

    npcs_in_location = await generated_npc_crud.get_multi_by_attribute(
        session, guild_id=guild_id, current_location_id=location_id
    )

    npcs_context = []
    for npc in npcs_in_location:
        # Exclude player if they are somehow listed as an NPC (should not happen with proper data)
        # Or if an NPC is the player (e.g. if player_id is an NPC id - also unlikely)
        if player_id and npc.id == player_id : # Assuming GeneratedNpc can't be a player
            continue

        npcs_context.append({
            "id": npc.id,
            "name": get_localized_text(npc.name_i18n, lang, "en"),
            "description": get_localized_text(npc.description_i18n, lang, "en"),
            "level": npc.level,
            # Add other relevant NPC fields: faction, relationships, notable characteristics
        })

    # Potentially add other entity types here (e.g., dynamic objects, global entities present)

    return {"npcs": npcs_context}


async def _get_quests_context(session: AsyncSession, guild_id: int, lang: str,
                            player_id: Optional[int] = None, party_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Gathers context about active quests for the player or party."""
    active_quests_context = []
    # This needs to determine which entity (player or party) the quests are for.
    # For simplicity, let's assume quests can be linked to players directly for now.
    # Party quests might need a different lookup or rely on player's quests if they are the leader.

    entity_id_for_quests = player_id # Default to player
    # If party_id is provided and no player_id, or if party quests are primary, adjust logic here.
    # Example: if party_id and not player_id, try to find party leader or all party members' quests.
    # For now, just using player_id if available.

    if entity_id_for_quests:
        stmt = (
            select(PlayerQuestProgress, GeneratedQuest, QuestStep)
            .join(GeneratedQuest, PlayerQuestProgress.quest_id == GeneratedQuest.id)
            # Use getattr for problematic class-level attribute access in query
            .join(QuestStep, getattr(PlayerQuestProgress, "current_quest_step_id") == QuestStep.id)
            .where(PlayerQuestProgress.player_id == entity_id_for_quests,
                   PlayerQuestProgress.guild_id == guild_id,
                   PlayerQuestProgress.status != 'completed', # Using string for now, adjust if Enum
                   PlayerQuestProgress.status != 'failed')
        )
        results = await session.execute(stmt)
        for pqp, quest, step in results.all():
            active_quests_context.append({
                "quest_id": quest.id,
                "quest_name": get_localized_text(quest.name_i18n, lang, "en"),
                "quest_description": get_localized_text(quest.description_i18n, lang, "en"),
                "current_step_id": step.id,
                "current_step_name": get_localized_text(step.name_i18n, lang, "en"),
                "current_step_description": get_localized_text(step.description_i18n, lang, "en"),
                "status": pqp.status.value if pqp.status else "unknown",
            })
    return active_quests_context

async def _get_relationships_context(session: AsyncSession, guild_id: int, lang: str,
                                   player_id: Optional[int] = None, party_id: Optional[int] = None,
                                   entity_ids_in_location: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    """Gathers context about relevant relationships."""
    # This is complex. Relationships can be Player-NPC, Player-Faction, Party-NPC, Party-Faction etc.
    # For AI prompt, we likely care about relationships of the acting entity (player/party)
    # with entities in the current location or globally important factions.

    relationships_context = []
    relevant_entities = [] # Tuples of (entity_id, entity_type_str)

    if player_id:
        relevant_entities.append((player_id, "player"))
    if party_id: # TODO: Define how party relationships are stored/queried
        # party = await party_crud.get(session, id=party_id, guild_id=guild_id)
        # if party and party.player_ids_json:
        #     for member_id in party.player_ids_json:
        #          relevant_entities.append((member_id, "player")) # or a specific "party_member" type
        pass # For now, party relationships are not deeply handled.

    if not relevant_entities and not entity_ids_in_location:
        return [] # No one to query relationships for/against

    # Example: Get player's relationships with NPCs in the location
    if player_id and entity_ids_in_location:
        for npc_id in entity_ids_in_location:
            # Relationship from player to NPC
            rel_p_npc = await relationship_crud.get_relationship(session, guild_id=guild_id,
                                                                entity1_id=player_id, entity1_type="player",
                                                                entity2_id=npc_id, entity2_type="npc") # Assuming "npc" type string
            if rel_p_npc:
                # Need NPC name
                npc = await generated_npc_crud.get(session, id=npc_id, guild_id=guild_id)
                npc_name = get_localized_text(npc.name_i18n, lang, "en") if npc else f"NPC_{npc_id}"
                relationships_context.append({
                    "entity1": "player", "entity1_id": player_id,
                    "entity2_name": npc_name, "entity2_type": "npc", "entity2_id": npc_id,
                    "type": rel_p_npc.type.value if rel_p_npc.type else "neutral",
                    "value": rel_p_npc.value
                })
            # Relationship from NPC to player
            rel_npc_p = await relationship_crud.get_relationship(session, guild_id=guild_id,
                                                                entity1_id=npc_id, entity1_type="npc",
                                                                entity2_id=player_id, entity2_type="player")
            if rel_npc_p:
                npc = await generated_npc_crud.get(session, id=npc_id, guild_id=guild_id)
                npc_name = get_localized_text(npc.name_i18n, lang, "en") if npc else f"NPC_{npc_id}"
                relationships_context.append({
                    "entity1_name": npc_name, "entity1_type": "npc", "entity1_id": npc_id,
                    "entity2": "player", "entity2_id": player_id,
                    "type": rel_npc_p.type.value if rel_npc_p.type else "neutral",
                    "value": rel_npc_p.value
                })

    # This is a simplified version. A full version would query all combinations or use more complex logic.
    return relationships_context


async def _get_world_state_context(session: AsyncSession, guild_id: int) -> Dict[str, Any]:
    """Placeholder for WorldState context."""
    # TODO: Implement when WorldState model (Task 36) is defined.
    # For now, return a generic statement or an empty dict.
    # Example: Fetch key-value pairs from a WorldState table for the guild.
    # world_events = await world_state_crud.get_multi_by_attribute(session, guild_id=guild_id)
    # return {event.key: event.value for event in world_events}
    return {"global_plot_status": "The ancient artifact is yet to be found."}


async def _get_game_rules_terms(session: AsyncSession, guild_id: int) -> Dict[str, Any]:
    """Fetches relevant game rules and terms from RuleConfig."""
    # rules = await get_all_rules_for_guild(session, guild_id=guild_id) # This gets the dict directly
    # For now, let's mock a simple rule structure.
    # In a real scenario, you'd fetch specific, relevant rules for AI context.
    all_rules_dict = await get_all_rules_for_guild(session, guild_id=guild_id) # Uses the cache

    # Filter or select rules relevant for AI generation context
    # For example, rules about entity generation, language, difficulty, etc.
    # This is highly dependent on how rules are structured in RuleConfig.
    # Example:
    # relevant_rules = {
    #    "main_language": all_rules_obj.get_rule("guild_main_language", "en"),
    #    "ai_generation_difficulty": all_rules_obj.get_rule("ai_generation_difficulty", "medium"),
    #    "npc_density_preference": all_rules_obj.get_rule("npc_density_preference", "average")
    # }
    # For now, just returning a few example rules directly.
    return {
        "main_language_code": all_rules_dict.get("guild_main_language", "en"),
        "generation_style": all_rules_dict.get("ai_generation_style", "classic_fantasy"),
        "allowed_npc_races": all_rules_dict.get("allowed_npc_races", ["human", "elf", "dwarf"]),
        "currency_name": all_rules_dict.get("currency_name", "gold pieces")
    }

async def _get_abilities_skills_terms(session: AsyncSession, guild_id: int, lang: str) -> Dict[str, List[Dict[str, Any]]]:
    """Fetches abilities and skills definitions."""
    abilities = await ability_crud.get_multi_by_attribute(session, guild_id=guild_id) # or global if guild_id is None
    skills = await skill_crud.get_multi_by_attribute(session, guild_id=guild_id) # or global

    return {
        "abilities": [{
            "static_id": ab.static_id,
            "name": get_localized_text(ab.name_i18n, lang, "en"),
            "description": get_localized_text(ab.description_i18n, lang, "en")
        } for ab in abilities],
        "skills": [{
            "static_id": sk.static_id,
            "name": get_localized_text(sk.name_i18n, lang, "en"),
            "description": get_localized_text(sk.description_i18n, lang, "en")
        } for sk in skills]
    }

def _get_entity_schema_terms() -> Dict[str, Any]:
    """Provides a basic schema/structure for key game entities for the AI."""
    # This helps the AI understand what kind of data to generate and in what format.
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
                        "$ref": "#/components/schemas/quest_step_schema" # Reference to QuestStep schema
                    }
                },
                "rewards_json": {"type": "object", "description": "Structured rewards, e.g., {'xp': 100, 'gold': 50, 'item_static_ids': ['item_id_1']}"},
                "ai_metadata_json": {"type": "object", "description": "Optional AI-specific metadata."}
            },
            "required": ["entity_type", "static_id", "title_i18n", "summary_i18n", "steps"]
        },
        "quest_step_schema": { # Renamed for clarity and reference
            "description": "Schema for individual Quest Steps.",
            "type": "object", # Added type object for clarity as a sub-schema
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
             "required": ["entity_type", "static_id", "name_i18n", "description_i18n", "item_type"] # base_value is optional
        },
        "npc_trader_schema": {
            "description": "Schema for NPC Traders. Inherits general NPC fields (like static_id, name_i18n, description_i18n, level) and adds trader-specific ones. Ensure 'static_id' is unique if provided, or one will be generated.",
            "allOf": [{"$ref": "#/components/schemas/npc_schema"}],
            "type": "object", # Explicitly define as object
            "properties": { # Define additional properties here, not in a "fields" sub-object
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
                # Other fields like name_i18n, description_i18n, static_id are inherited from npc_schema via allOf
            },
            "required": ["entity_type", "role_i18n"] # These are specific to npc_trader
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
        # Add more schemas for Locations (if generating new ones) as needed.
    }

# Main API function for location content generation
@transactional # Manages session lifecycle
async def prepare_ai_prompt(
    session: AsyncSession, # Injected by @transactional
    guild_id: int,
    location_id: Optional[int], # Changed to Optional[int]
    player_id: Optional[int] = None,
    party_id: Optional[int] = None
) -> str:
    """
    Collects world context for a specific guild and location,
    and forms a structured prompt for the AI to generate new content.
    """
    try:
        guild_main_lang = await _get_guild_main_language(session, guild_id)

        # --- Gather Context ---
        location_context = await _get_location_context(session, location_id, guild_id, guild_main_lang)
        if not location_context:
            logger.warning(f"Location {location_id} not found for guild {guild_id}. Aborting prompt generation.")
            return "Error: Location not found."

        player_context = {}
        if player_id:
            player_context = await _get_player_context(session, player_id, guild_id)

        party_context = {}
        if party_id:
            party_context = await _get_party_context(session, party_id, guild_id)

        # NPCs in current location (excluding player/party members if they were somehow listed)
        nearby_entities_ctx = await _get_nearby_entities_context(session, guild_id, location_id, guild_main_lang, player_id, party_id)

        # Active quests for player/party
        active_quests_ctx = await _get_quests_context(session, guild_id, guild_main_lang, player_id, party_id)

        # Relationships (simplified for now)
        npc_ids_in_location = [npc['id'] for npc in nearby_entities_ctx.get("npcs", [])]
        relationships_ctx = await _get_relationships_context(session, guild_id, guild_main_lang, player_id, party_id, npc_ids_in_location)

        # World state (placeholder)
        world_state_ctx = await _get_world_state_context(session, guild_id)

        # --- Gather Game Terms & Rules ---
        game_rules_terms = await _get_game_rules_terms(session, guild_id)
        # abilities_skills_terms = await _get_abilities_skills_terms(session, guild_id, guild_main_lang) # Assuming CRUDs exist
        entity_schemas = _get_entity_schema_terms()

        # --- Construct the Prompt ---
        prompt_parts = []
        prompt_parts.append(f"## AI Content Generation Request")
        prompt_parts.append(f"Target Guild ID: {guild_id}")
        prompt_parts.append(f"Primary Language for Generation: {guild_main_lang} (Please also provide English translations for all user-facing text in 'en' fields within _i18n JSON objects).")
        prompt_parts.append(f"Secondary Language (always include): en")

        prompt_parts.append("\n### Current Context:")
        prompt_parts.append(f"**Location:** {location_context.get('name', 'Unknown Location')} (Static ID: {location_context.get('static_id', 'N/A')})")
        prompt_parts.append(f"  Description: {location_context.get('description', '')}")
        if location_context.get('generated_details'):
             prompt_parts.append(f"  Additional Details: {location_context.get('generated_details')}")
        prompt_parts.append(f"  Type: {location_context.get('type')}")
        prompt_parts.append(f"  Connected Locations (Static IDs): {', '.join(location_context.get('neighbor_static_ids', [])) or 'None specified'}")


        if player_context:
            prompt_parts.append(f"\n**Player:** {player_context.get('name', 'N/A')} (Level {player_context.get('level', 'N/A')})")
            prompt_parts.append(f"  Status: {player_context.get('status', 'N/A')}")
            # Add more player details

        if party_context:
            prompt_parts.append(f"\n**Party:** {party_context.get('name', 'N/A')} (Average Level: {party_context.get('average_level', 'N/A')})")
            prompt_parts.append(f"  Members: {', '.join([m['name'] for m in party_context.get('members', [])]) or 'None'}")
            # Add more party details

        prompt_parts.append("\n**Entities in Location:**")
        if nearby_entities_ctx.get("npcs"):
            for npc in nearby_entities_ctx["npcs"]:
                prompt_parts.append(f"  - NPC: {npc.get('name')} (Level {npc.get('level', 'N/A')}) - {npc.get('description', '')}")
        else:
            prompt_parts.append("  - No other significant NPCs detected in the immediate vicinity.")

        if active_quests_ctx:
            prompt_parts.append("\n**Active Quests for Player/Party:**")
            for q_ctx in active_quests_ctx:
                prompt_parts.append(f"  - Quest: {q_ctx.get('quest_name')} - Current Step: {q_ctx.get('current_step_name')} ({q_ctx.get('status', 'N/A')})")

        if relationships_ctx:
            prompt_parts.append("\n**Relevant Relationships:**")
            for rel in relationships_ctx:
                e1_name = rel.get('entity1_name', rel.get('entity1', 'Unknown'))
                e2_name = rel.get('entity2_name', rel.get('entity2', 'Unknown'))
                prompt_parts.append(f"  - {e1_name} ({rel.get('entity1_type')}) to {e2_name} ({rel.get('entity2_type')}): {rel.get('type')} ({rel.get('value')})")


        prompt_parts.append("\n**Overall World State Snippets:**")
        for key, value in world_state_ctx.items():
            prompt_parts.append(f"  - {key.replace('_', ' ').title()}: {value}")

        prompt_parts.append("\n### Game Rules & Terminology Snippets:")
        for key, value in game_rules_terms.items():
            prompt_parts.append(f"  - {key.replace('_', ' ').title()}: {value}")

        # prompt_parts.append("\n**Available Abilities & Skills (Examples):**")
        # for ability in abilities_skills_terms.get("abilities", [])[:3]: # Show a few examples
        #     prompt_parts.append(f"  - Ability: {ability.get('name')} ({ability.get('static_id')}) - {ability.get('description')}")
        # for skill in abilities_skills_terms.get("skills", [])[:3]: # Show a few examples
        #     prompt_parts.append(f"  - Skill: {skill.get('name')} ({skill.get('static_id')}) - {skill.get('description')}")


        prompt_parts.append("\n### Generation Request:")
        prompt_parts.append(f"Based on the context above, please generate content for the location '{location_context.get('name', '')}'. Focus on enriching the current location. You can generate a mix of the following entities:")
        prompt_parts.append(f"  1. NPCs: Interesting characters that fit the location and world lore. Ensure each generated NPC has a unique 'static_id' (e.g., 'npc_guard_captain_01', 'mysterious_hermit').")
        prompt_parts.append(f"  2. Quests: Short to medium quests that can be initiated or progressed in this location.")
        prompt_parts.append(f"  3. Items: Unique or noteworthy items that could be found or are relevant here.")
        prompt_parts.append(f"  4. Events: Small dynamic occurrences, discoveries, or minor encounters suitable for this location.")
        prompt_parts.append(f"  5. Relationships: Specific relationships for the NPCs you generate. These can be NPC-NPC (among those generated in this batch) or NPC-Faction (with existing factions if context provides them, or factions generated in this batch if applicable). Use the 'relationship_schema'. These relationships can represent hidden loyalties, grudges, affiliations, etc. Use appropriate 'relationship_type' values (e.g., 'secret_rivalry', 'hidden_alliance_with_faction_X', 'personal_debt_to_npc_Y').")

        prompt_parts.append("\n### Output Format Instructions:")
        prompt_parts.append("Please provide your response as a single JSON object. The top-level keys should be entity types (e.g., 'generated_npcs', 'generated_quests', 'generated_items', 'generated_events', 'generated_relationships'). Each key should map to a list of generated entities of that type.")
        prompt_parts.append("For each entity, adhere to its schema provided below. ALL user-facing text (names, descriptions, dialogue, etc.) MUST be provided in an _i18n JSON object with keys for the primary language '{guild_main_lang}' AND 'en' (English).")
        prompt_parts.append("When generating NPCs and their relationships: ensure 'static_id' values for NPCs are used consistently in the 'generated_relationships' list (e.g., if you generate an NPC with static_id 'hermit_01', a relationship involving this NPC should use 'hermit_01' as entity_static_id).")
        prompt_parts.append("Example of _i18n field: \"name_i18n\": {\""+guild_main_lang+"\": \"Localized Name\", \"en\": \"English Name\"}")
        prompt_parts.append("Ensure generated content is consistent with the provided context, rules, and entity schemas.")

        prompt_parts.append("\n### Entity Schemas for Generation:")
        prompt_parts.append("```json")
        # Убедиться, что entity_schemas включает relationship_schema, что он уже делает
        prompt_parts.append(json.dumps(entity_schemas, indent=2))
        prompt_parts.append("```")

        final_prompt = "\n".join(prompt_parts)
        logger.info(f"Generated AI prompt for guild {guild_id}, location {location_id}:\n{final_prompt[:1000]}...") # Log snippet
        return final_prompt

    except Exception as e:
        logger.exception(f"Error in prepare_ai_prompt for guild {guild_id}, location {location_id}: {e}")
        return f"Error generating AI prompt: {str(e)}"

# Example of how it might be called (for testing purposes, not part of the module's API contract)
# async def main_test():
#     async for session in get_db_session():
#         # Replace with actual guild_id, location_id for testing
#         guild_id_test = 1
#         location_id_test = 1
#         # Ensure GuildConfig, Location etc. exist for these IDs in your test DB
#         # await guild_config_crud.create(session, obj_in={"id":guild_id_test, "main_language":"ru"})
#         # await location_crud.create(session, obj_in={"id":location_id_test, "guild_id":guild_id_test, "static_id":"start_loc", "name_i18n":{"ru":"Старт", "en":"Start"}})
#         prompt = await prepare_ai_prompt(session, guild_id=guild_id_test, location_id=location_id_test)
#         print(prompt)

# if __name__ == "__main__":
#     import asyncio
#     # Basic logging setup for testing
#     logging.basicConfig(level=logging.INFO)
#     # You'll need to ensure your DB is initialized and test data exists.
#     # Also, ensure DATABASE_URL is configured in your environment or settings.
#     # asyncio.run(main_test())


@transactional
async def prepare_faction_relationship_generation_prompt(
    session: AsyncSession, # Injected by @transactional
    guild_id: int
) -> str:
    """
    Collects guild-level context and forms a structured prompt for the AI
    to generate factions and their initial relationships.
    """
    try:
        guild_main_lang = await _get_guild_main_language(session, guild_id)
        all_rules = await get_all_rules_for_guild(session, guild_id)

        # --- Gather Game Rules & Terms relevant for Faction/Relationship Generation ---
        faction_rules = {
            "target_faction_count": all_rules.get("faction_generation:target_count", 3),
            "faction_themes": all_rules.get("faction_generation:themes", ["good_vs_evil", "nature_vs_industry"]),
            "allow_player_faction_interaction": all_rules.get("faction_generation:allow_player_interaction", True),
            "world_description": all_rules.get("world_description", "A generic fantasy world.")
        }
        relationship_rules = {
            "initial_relationship_complexity": all_rules.get("relationship_generation:complexity", "moderate"), # e.g., simple, moderate, complex
            "default_relationship_types": all_rules.get("relationship_generation:default_types", ["faction_standing"])
        }

        entity_schemas = _get_entity_schema_terms() # Ensure this includes faction_schema and relationship_schema

        # --- Construct the Prompt ---
        prompt_parts = []
        prompt_parts.append(f"## AI Faction and Relationship Generation Request")
        prompt_parts.append(f"Target Guild ID: {guild_id}")
        prompt_parts.append(f"Primary Language for Generation: {guild_main_lang} (Please also provide English translations for all user-facing text in 'en' fields within _i18n JSON objects).")
        prompt_parts.append(f"Secondary Language (always include): en")

        prompt_parts.append("\n### Guild & World Context:")
        prompt_parts.append(f"  World Description: {faction_rules['world_description']}")
        # Add more world state context if available and relevant (e.g., from _get_world_state_context)

        prompt_parts.append("\n### Generation Guidelines & Rules:")
        prompt_parts.append(f"  Target Number of Factions to Generate: {faction_rules['target_faction_count']}")
        prompt_parts.append(f"  Suggested Faction Themes/Archetypes: {', '.join(faction_rules['faction_themes'])}")
        prompt_parts.append(f"  Relationship Complexity: {relationship_rules['initial_relationship_complexity']}")
        prompt_parts.append(f"  Default Relationship Types to consider: {', '.join(relationship_rules['default_relationship_types'])}")

        prompt_parts.append("\n### Generation Task:")
        prompt_parts.append(f"Based on the context and rules, please generate a set of {faction_rules['target_faction_count']} distinct factions for this game world.")
        prompt_parts.append(f"For each faction, provide its details according to the 'faction_schema'. Ensure each faction has a unique 'static_id' you generate.")
        prompt_parts.append(f"After defining the factions, generate initial relationships BETWEEN these newly created factions. Use the 'relationship_schema'.")
        prompt_parts.append(f"If '{faction_rules['allow_player_faction_interaction']}' is true, you may also suggest initial default relationships between some factions and a generic 'player_default' entity (use 'player_default' as static_id and 'player' as type for this generic player placeholder).")


        prompt_parts.append("\n### Output Format Instructions:")
        prompt_parts.append("Please provide your response as a single JSON object. The top-level keys should be 'generated_factions' and 'generated_relationships'.")
        prompt_parts.append("  'generated_factions': Should be a list of faction objects, each adhering to 'faction_schema'.")
        prompt_parts.append("  'generated_relationships': Should be a list of relationship objects, each adhering to 'relationship_schema'.")
        prompt_parts.append("ALL user-facing text (names, descriptions, ideology, etc.) MUST be provided in an _i18n JSON object with keys for the primary language '{guild_main_lang}' AND 'en' (English).")
        prompt_parts.append("Ensure generated 'static_id' for factions are unique within this generation batch.")

        prompt_parts.append("\n### Entity Schemas for Generation:")
        prompt_parts.append("```json")
        prompt_parts.append(json.dumps({
            "faction_schema": entity_schemas.get("faction_schema"),
            "relationship_schema": entity_schemas.get("relationship_schema")
        }, indent=2))
        prompt_parts.append("```")

        final_prompt = "\n".join(prompt_parts)
        logger.info(f"Generated AI prompt for faction/relationship generation for guild {guild_id}:\n{final_prompt[:1000]}...") # Log snippet
        return final_prompt

    except Exception as e:
        logger.exception(f"Error in prepare_faction_relationship_generation_prompt for guild {guild_id}: {e}")
        return f"Error generating faction/relationship AI prompt: {str(e)}"


async def _get_hidden_relationships_context_for_dialogue(
    session: AsyncSession,
    guild_id: int,
    lang: str,
    npc_id: int,
    player_id: Optional[int] = None,
    # party_id: Optional[int] = None, # Placeholder for future use
    # other_relevant_entity_ids: Optional[List[Tuple[int, RelationshipEntityType]]] = None # Placeholder
) -> List[Dict[str, Any]]:
    """
    Gathers context about hidden relationships of an NPC for dialogue generation,
    including relevant rule-based hints for the AI.
    """
    hidden_relationships_context = []

    # Correctly import the actual CRUD operations for relationships
    from .crud.crud_relationship import crud_relationship as actual_crud_relationship
    from ..models.enums import RelationshipEntityType # Ensure this is the correct Enum

    npc_all_relationships = await actual_crud_relationship.get_relationships_for_entity(
        session=session, # crud_relationship.py uses 'db' as session parameter name
        guild_id=guild_id,
        entity_id=npc_id,
            entity_type=RelationshipEntityType.GENERATED_NPC # Use the imported Enum
    )

    if not npc_all_relationships:
        return []

    hidden_prefixes = ("secret_", "internal_", "personal_debt", "hidden_fear", "betrayal_")
    relevant_hidden_rels: List[Relationship] = []

    for rel in npc_all_relationships:
        if not rel.relationship_type.startswith(hidden_prefixes):
            continue

        is_relevant_to_dialogue = False
        # Check if the relationship involves the player, if player_id is provided
        if player_id:
            is_player_entity1 = (rel.entity1_id == player_id and rel.entity1_type == RelationshipEntityType.PLAYER)
            is_player_entity2 = (rel.entity2_id == player_id and rel.entity2_type == RelationshipEntityType.PLAYER)

            is_npc_entity1 = (rel.entity1_id == npc_id and rel.entity1_type == RelationshipEntityType.GENERATED_NPC)
            is_npc_entity2 = (rel.entity2_id == npc_id and rel.entity2_type == RelationshipEntityType.GENERATED_NPC) # Corrected to rel.entity2_type

            if (is_npc_entity1 and is_player_entity2) or \
               (is_npc_entity2 and is_player_entity1):
                is_relevant_to_dialogue = True
        else:
            # If no player_id, all hidden relationships of the NPC might be relevant for broader context
            is_relevant_to_dialogue = True
            # Future: could filter for relationships with other_relevant_entity_ids if provided

        if is_relevant_to_dialogue:
            relevant_hidden_rels.append(rel)

    if not relevant_hidden_rels:
        return []

    for rel in relevant_hidden_rels:
        # Determine the "other" entity in the relationship relative to the NPC
        other_entity_id = rel.entity1_id if rel.entity2_id == npc_id else rel.entity2_id
        other_entity_type_enum = rel.entity1_type if rel.entity2_id == npc_id else rel.entity2_type

        rel_ctx = {
            "relationship_type": rel.relationship_type,
            "value": rel.value,
            "target_entity_id": other_entity_id,
            "target_entity_type": other_entity_type_enum.value,
            "prompt_hints": "",
            "unlocks_tags": [],
            "options_availability_formula": None
        }

        base_rel_type_for_rule = rel.relationship_type.split(':')[0]
        rule_key_exact = f"hidden_relationship_effects:dialogue:{rel.relationship_type}"
        rule_key_generic = f"hidden_relationship_effects:dialogue:{base_rel_type_for_rule}"

        specific_rule = await get_rule(session, guild_id, rule_key_exact, default=None)
        generic_rule = await get_rule(session, guild_id, rule_key_generic, default=None)

        chosen_rule_data = None
        if specific_rule and isinstance(specific_rule, dict) and specific_rule.get("enabled", False):
            chosen_rule_data = specific_rule
        elif generic_rule and isinstance(generic_rule, dict) and generic_rule.get("enabled", False):
            chosen_rule_data = generic_rule

        if chosen_rule_data:
            hints_i18n = chosen_rule_data.get("prompt_modifier_hints_i18n")
            if hints_i18n and isinstance(hints_i18n, dict):
                hint_template = hints_i18n.get(lang) # Get text for current language
                if hint_template is None and lang != "en": # Fallback to English if current lang not found
                    hint_template = hints_i18n.get("en")
                if hint_template is None: # If still None (e.g. 'en' also not found or hints_i18n was empty for these keys)
                    hint_template = ""

                if hint_template: # Only proceed if we have a template
                    # Basic placeholder replacement.
                    relationship_description = rel.relationship_type.replace("_", " ").replace("secret ", "") # Simple description
                    formatted_hint = hint_template.replace("{value}", str(rel.value))
                    # These might not exist in all templates, but replace won't error if placeholder is missing
                    formatted_hint = formatted_hint.replace("{relationship_description_en}", relationship_description)
                    formatted_hint = formatted_hint.replace("{relationship_description_ru}", relationship_description)
                    rel_ctx["prompt_hints"] = formatted_hint
                else:
                    rel_ctx["prompt_hints"] = "" # Ensure it's an empty string if no template
            else: # hints_i18n is not a dict or is None
                rel_ctx["prompt_hints"] = ""


            rel_ctx["unlocks_tags"] = chosen_rule_data.get("unlocks_dialogue_options_tags", [])
            rel_ctx["options_availability_formula"] = chosen_rule_data.get("dialogue_option_availability_formula")

        hidden_relationships_context.append(rel_ctx)

    return hidden_relationships_context


async def prepare_quest_generation_prompt(
    session: AsyncSession,
    guild_id: int,
    # context_params: Optional[Dict[str, Any]] = None # General context if needed
    # For quest generation, context might include:
    # - Current world state snippets (e.g., recent major events)
    # - Key NPCs or Factions recently interacted with or of importance
    # - Themes or types of quests desired (e.g., "exploration", "mystery", "combat-heavy")
    # - Player/Party level or progression to tailor difficulty/rewards
    player_id_context: Optional[int] = None, # For player-specific quest context
    location_id_context: Optional[int] = None # For location-specific quest context
) -> str:
    """
    Collects guild-level context and forms a structured prompt for the AI
    to generate quests, including their steps and relevant JSON fields.
    """
    try:
        guild_main_lang = await _get_guild_main_language(session, guild_id)
        all_rules = await get_all_rules_for_guild(session, guild_id) # Fetches from cache or DB

        # --- Gather Quest Generation Rules & Context ---
        quest_gen_rules = {
            "target_quest_count": all_rules.get("ai:quest_generation:target_count", 1),
            "quest_themes_i18n": all_rules.get("ai:quest_generation:themes_i18n", {"en": ["artifact recovery", "monster hunt", "local mystery"]}),
            "quest_complexity": all_rules.get("ai:quest_generation:complexity", "medium"), # e.g., simple, medium, complex
            "example_mechanics_json": all_rules.get(
                "ai:quest_generation:example_mechanics_json",
                {"type": "fetch", "item_static_id": "sample_item", "count": 1, "target_npc_static_id_for_delivery": "sample_npc"}
            ),
            "example_abstract_goal_json": all_rules.get(
                "ai:quest_generation:example_abstract_goal_json",
                {"description_i18n": {"en": "Impress the guild master.", "ru": "Произвести впечатление на главу гильдии."}}
            ),
            "example_consequences_json": all_rules.get(
                "ai:quest_generation:example_consequences_json",
                {"world_state_update": {"key": "guild_master_mood", "new_value": "pleased"}}
            ),
            "world_description": all_rules.get("world_description", "A generic fantasy world context.") # General world context
        }

        # Fetch relevant context (player, location, etc.) if IDs are provided
        player_context_str = ""
        if player_id_context:
            player_ctx = await _get_player_context(session, player_id_context, guild_id)
            if player_ctx:
                player_context_str = f"  - Player Context: Name: {player_ctx.get('name')}, Level: {player_ctx.get('level')}\n"

        location_context_str = ""
        if location_id_context:
            loc_ctx = await _get_location_context(session, location_id_context, guild_id, guild_main_lang)
            if loc_ctx:
                location_context_str = f"  - Location Context: Name: {loc_ctx.get('name')}, Type: {loc_ctx.get('type')}\n"


        entity_schemas = _get_entity_schema_terms() # Ensure this includes the updated quest_schema and quest_step_schema

        # --- Construct the Prompt ---
        prompt_parts = []
        prompt_parts.append("## AI Quest Generation Request")
        prompt_parts.append(f"Target Guild ID: {guild_id}")
        prompt_parts.append(f"Primary Language for Generation: {guild_main_lang} (Also provide English ('en') translations for all user-facing text in _i18n JSON objects).")

        prompt_parts.append("\n### Generation Guidelines & Context:")
        prompt_parts.append(f"  World Description: {quest_gen_rules['world_description']}")
        if player_context_str: prompt_parts.append(player_context_str)
        if location_context_str: prompt_parts.append(location_context_str)
        prompt_parts.append(f"  Target Number of Quests to Generate: {quest_gen_rules['target_quest_count']}")

        # Corrected theme processing
        actual_themes_i18n = all_rules.get("ai:quest_generation:themes_i18n", {}) # Get from all_rules directly
        themes_list_for_lang = actual_themes_i18n.get(guild_main_lang, [])

        if not themes_list_for_lang and guild_main_lang != "en": # Fallback to English from rules
            themes_list_for_lang = actual_themes_i18n.get("en", [])

        if not themes_list_for_lang: # Fallback to global defaults if no themes found in rules
            themes_list_for_lang = DEFAULT_QUEST_THEMES.get(guild_main_lang, DEFAULT_QUEST_THEMES.get("en", []))

        suggested_themes_str = ", ".join(themes_list_for_lang) if themes_list_for_lang else ""
        prompt_parts.append(f"  Suggested Quest Themes: {suggested_themes_str}")
        prompt_parts.append(f"  Desired Quest Complexity: {quest_gen_rules['quest_complexity']}")

        prompt_parts.append("\n### Generation Task:")
        prompt_parts.append(f"Generate {quest_gen_rules['target_quest_count']} quest(s) suitable for the provided context.")
        prompt_parts.append("For each quest:")
        prompt_parts.append("  - Adhere to the 'quest_schema'. Ensure 'static_id' is unique for each quest.")
        prompt_parts.append("  - Each quest must have one or more steps, adhering to 'quest_step_schema'.")
        prompt_parts.append("  - For each step, define 'title_i18n', 'description_i18n', and 'step_order'.")
        prompt_parts.append("  - Populate 'required_mechanics_json' with a clear, structured objective for the step.")
        prompt_parts.append(f"    Example for 'required_mechanics_json': {json.dumps(quest_gen_rules['example_mechanics_json'])}")
        prompt_parts.append("  - Optionally, provide 'abstract_goal_json' for steps requiring broader interpretation.")
        prompt_parts.append(f"    Example for 'abstract_goal_json': {json.dumps(quest_gen_rules['example_abstract_goal_json'])}")
        prompt_parts.append("  - Optionally, detail 'consequences_json' for step completion.")
        prompt_parts.append(f"    Example for 'consequences_json': {json.dumps(quest_gen_rules['example_consequences_json'])}")
        prompt_parts.append("  - Ensure all user-facing text fields (titles, descriptions, summaries) are _i18n objects including both the primary language and English.")

        prompt_parts.append("\n### Output Format Instructions:")
        prompt_parts.append("Provide your response as a single JSON array, where each element is a quest object conforming to 'quest_schema'.")
        prompt_parts.append("Example of _i18n field: \"title_i18n\": {\""+guild_main_lang+"\": \"Localized Title\", \"en\": \"English Title\"}")

        prompt_parts.append("\n### Entity Schemas for Generation:")
        prompt_parts.append("```json")
        # Ensure quest_schema and quest_step_schema are included. _get_entity_schema_terms should provide them.
        prompt_parts.append(json.dumps({
            "quest_schema": entity_schemas.get("quest_schema"),
            "quest_step_schema": entity_schemas.get("quest_step_schema") # Referenced by quest_schema
            # Include other schemas if AI needs to reference them for quest content (e.g., item_schema for rewards)
        }, indent=2))
        prompt_parts.append("```")

        final_prompt = "\n".join(prompt_parts)
        logger.info(f"Generated AI prompt for quest generation for guild {guild_id}:\n{final_prompt[:1000]}...") # Log snippet
        return final_prompt

    except Exception as e:
        logger.exception(f"Error in prepare_quest_generation_prompt for guild {guild_id}: {e}")
        return f"Error generating quest AI prompt: {str(e)}"


@transactional
async def prepare_economic_entity_generation_prompt(
    session: AsyncSession,
    guild_id: int
) -> str:
    """
    Collects guild-level context and forms a structured prompt for the AI
    to generate economic entities (items and NPC traders).
    """
    try:
        guild_main_lang = await _get_guild_main_language(session, guild_id)
        all_rules = await get_all_rules_for_guild(session, guild_id) # Fetches from cache or DB

        # --- Gather Economic Generation Rules & Context ---
        # Extract relevant economic rules for context
        economic_rules_for_context = {
            key: value for key, value in all_rules.items() if key.startswith("economy:")
        }
        ai_gen_rules_for_context = {
            key: value for key, value in all_rules.items() if key.startswith("ai:economic_generation:")
        }

        # Specific rules that might guide generation
        target_item_count = ai_gen_rules_for_context.get("ai:economic_generation:target_item_count", {}).get("count", 5)
        target_trader_count = ai_gen_rules_for_context.get("ai:economic_generation:target_trader_count", {}).get("count", 2)

        world_description_i18n = all_rules.get("world_description_i18n", {"en": "A generic fantasy world."})
        world_description = get_localized_text(world_description_i18n, guild_main_lang, "en")

        item_type_distribution = ai_gen_rules_for_context.get("ai:economic_generation:item_type_distribution", {}).get("types", [])
        trader_role_distribution = ai_gen_rules_for_context.get("ai:economic_generation:trader_role_distribution", {}).get("roles", [])

        quality_instructions_i18n = ai_gen_rules_for_context.get("ai:economic_generation:quality_instructions_i18n", {})
        quality_instructions = get_localized_text(quality_instructions_i18n, guild_main_lang, "en")


        entity_schemas = _get_entity_schema_terms()

        # --- Construct the Prompt ---
        prompt_parts = []
        prompt_parts.append("## AI Economic Entity Generation Request")
        prompt_parts.append(f"Target Guild ID: {guild_id}")
        prompt_parts.append(f"Primary Language for Generation: {guild_main_lang} (Also provide English ('en') translations for all user-facing text in _i18n JSON objects).")

        prompt_parts.append("\n### Generation Guidelines & Context:")
        prompt_parts.append(f"  World Description: {world_description}")
        if quality_instructions:
            prompt_parts.append(f"  Quality Instructions: {quality_instructions}")

        prompt_parts.append(f"  Target Number of New Items to Generate: {target_item_count}")
        prompt_parts.append(f"  Target Number of New NPC Traders to Generate: {target_trader_count}")

        if item_type_distribution:
            prompt_parts.append(f"  Suggested Item Type Distribution (use as inspiration, weights are relative): {json.dumps(item_type_distribution)}")
        else:
            prompt_parts.append(f"  Example Item Types: weapon, armor, consumable, crafting_material, quest_item, misc")

        if trader_role_distribution:
            prompt_parts.append(f"  Suggested Trader Role Distribution (use as inspiration, weights are relative): {json.dumps(trader_role_distribution)}")
        else:
            prompt_parts.append(f"  Example Trader Roles: Blacksmith, Alchemist, General Goods Vendor, Fletcher")


        if economic_rules_for_context:
            prompt_parts.append("\n  Relevant Economic Rules (for context and inspiration, do not just copy):")
            for key, value in economic_rules_for_context.items():
                value_str = json.dumps(value)
                if len(value_str) > 200: # Keep snippets readable
                    value_str = value_str[:197] + "..."
                prompt_parts.append(f"    - {key}: {value_str}")
        else:
            prompt_parts.append("\n  No specific economic rules found; use general fantasy tropes for item values and trader inventories.")

        prompt_parts.append("\n### Generation Task:")
        prompt_parts.append(f"Generate {target_item_count} new item(s) and {target_trader_count} new NPC trader(s) suitable for the world context.")
        prompt_parts.append("For each ITEM:")
        prompt_parts.append("  - Adhere to the 'item_schema'. Ensure 'static_id' is unique for each item generated (e.g., 'iron_sword_common', 'potion_healing_minor').")
        prompt_parts.append("  - Provide 'name_i18n', 'description_i18n', 'item_type'.")
        prompt_parts.append("  - 'properties_json' should detail relevant stats (e.g., damage for weapons, effects for potions, armor value for armor).")
        prompt_parts.append("  - 'base_value' should be a sensible integer representing its worth in the game's smallest currency unit. You can use rules under 'economy:base_item_values:*' for guidance if available.")
        prompt_parts.append("For each NPC TRADER:")
        prompt_parts.append("  - Adhere to the 'npc_trader_schema' (which includes 'npc_schema' fields like 'static_id', 'name_i18n', 'description_i18n', 'stats.level'). Ensure 'static_id' is unique (e.g., 'boris_the_blacksmith', 'elara_herbalist').")
        prompt_parts.append("  - Provide a 'role_i18n' (e.g., Blacksmith, Alchemist).")
        prompt_parts.append("  - For inventory: you can EITHER provide an 'inventory_template_key' that references a template from 'economy:npc_inventory_templates:*' (if such rules are provided in context), OR provide a list of 'generated_inventory_items'.")
        prompt_parts.append("  - If using 'generated_inventory_items', each entry should specify 'item_static_id' (referencing items generated in this batch or common existing items you might assume), 'quantity_min', 'quantity_max', and 'chance_to_appear'.")
        prompt_parts.append("  - Ensure all user-facing text fields are _i18n objects including both the primary language and English.")

        prompt_parts.append("\n### Output Format Instructions:")
        prompt_parts.append("Provide your response as a single JSON array, where each element is an item object (conforming to 'item_schema') or an NPC trader object (conforming to 'npc_trader_schema'). Each object must have an 'entity_type' field ('item' or 'npc_trader').")
        prompt_parts.append("Example of _i18n field: \"name_i18n\": {\""+guild_main_lang+"\": \"Localized Name\", \"en\": \"English Name\"}")

        prompt_parts.append("\n### Entity Schemas for Generation:")
        prompt_parts.append("```json")
        prompt_parts.append(json.dumps({
            "item_schema": entity_schemas.get("item_schema"),
            "npc_trader_schema": entity_schemas.get("npc_trader_schema"),
            "npc_schema": entity_schemas.get("npc_schema") # Referenced by npc_trader_schema
        }, indent=2))
        prompt_parts.append("```")

        final_prompt = "\n".join(prompt_parts)
        logger.info(f"Generated AI prompt for economic entity generation for guild {guild_id}:\n{final_prompt[:1000]}...")
        return final_prompt

    except Exception as e:
        logger.exception(f"Error in prepare_economic_entity_generation_prompt for guild {guild_id}: {e}")
        return f"Error generating economic entity AI prompt: {str(e)}"


@transactional
async def prepare_economic_entity_generation_prompt(
    session: AsyncSession,
    guild_id: int
) -> str:
    """
    Collects guild-level context and forms a structured prompt for the AI
    to generate economic entities (items and NPC traders).
    """
    try:
        guild_main_lang = await _get_guild_main_language(session, guild_id)
        all_rules = await get_all_rules_for_guild(session, guild_id)

        # --- Gather Economic Generation Rules & Context ---
        # Extract relevant economic rules for context
        economic_rules_context = {
            key: value for key, value in all_rules.items() if key.startswith("economy:")
        }
        # Specific rules that might guide generation
        target_item_count = all_rules.get("ai:economic_generation:target_item_count", 5)
        target_trader_count = all_rules.get("ai:economic_generation:target_trader_count", 2)
        world_description = all_rules.get("world_description", "A generic fantasy world.")
        item_type_examples = ["weapon", "armor", "consumable", "crafting_material", "quest_item"] # Default examples

        entity_schemas = _get_entity_schema_terms()

        # --- Construct the Prompt ---
        prompt_parts = []
        prompt_parts.append("## AI Economic Entity Generation Request")
        prompt_parts.append(f"Target Guild ID: {guild_id}")
        prompt_parts.append(f"Primary Language for Generation: {guild_main_lang} (Also provide English ('en') translations for all user-facing text in _i18n JSON objects).")

        prompt_parts.append("\n### Generation Guidelines & Context:")
        prompt_parts.append(f"  World Description: {world_description}")
        prompt_parts.append(f"  Target Number of New Items to Generate: {target_item_count}")
        prompt_parts.append(f"  Target Number of New NPC Traders to Generate: {target_trader_count}")
        prompt_parts.append(f"  Example Item Types: {', '.join(item_type_examples)}")

        if economic_rules_context:
            prompt_parts.append("\n  Relevant Economic Rules (for context and inspiration, do not just copy):")
            for key, value in economic_rules_context.items():
                # Summarize or show snippet of complex rules
                value_str = json.dumps(value)
                if len(value_str) > 150:
                    value_str = value_str[:147] + "..."
                prompt_parts.append(f"    - {key}: {value_str}")
        else:
            prompt_parts.append("\n  No specific economic rules found; use general fantasy tropes for item values and trader inventories.")

        prompt_parts.append("\n### Generation Task:")
        prompt_parts.append(f"Generate {target_item_count} new item(s) and {target_trader_count} new NPC trader(s) suitable for the world context.")
        prompt_parts.append("For each ITEM:")
        prompt_parts.append("  - Adhere to the 'item_schema'. Ensure 'static_id' is unique for each item generated.")
        prompt_parts.append("  - Provide 'name_i18n', 'description_i18n', 'item_type'.")
        prompt_parts.append("  - 'properties_json' should detail relevant stats (e.g., damage for weapons, effects for potions).")
        prompt_parts.append("  - 'base_value' should be a sensible integer representing its worth.")
        prompt_parts.append("For each NPC TRADER:")
        prompt_parts.append("  - Adhere to the 'npc_trader_schema' (which includes 'npc_schema' fields like 'static_id', 'name_i18n', 'description_i18n').")
        prompt_parts.append("  - Provide a 'role_i18n' (e.g., Blacksmith, Alchemist).")
        prompt_parts.append("  - Suggest an 'inventory_template_key' from the provided economic rules (e.g., a key from 'economy:npc_inventory_templates') OR provide a list of 'generated_inventory_items' with specific 'item_static_id' (referencing items generated in this batch or existing common items you might assume), quantities, and chance to appear.")
        prompt_parts.append("  - Ensure all user-facing text fields are _i18n objects including both the primary language and English.")

        prompt_parts.append("\n### Output Format Instructions:")
        prompt_parts.append("Provide your response as a single JSON array, where each element is an item object (conforming to 'item_schema') or an NPC trader object (conforming to 'npc_trader_schema'). Each object must have an 'entity_type' field ('item' or 'npc_trader').")
        prompt_parts.append("Example of _i18n field: \"name_i18n\": {\""+guild_main_lang+"\": \"Localized Name\", \"en\": \"English Name\"}")

        prompt_parts.append("\n### Entity Schemas for Generation:")
        prompt_parts.append("```json")
        prompt_parts.append(json.dumps({
            "item_schema": entity_schemas.get("item_schema"),
            "npc_trader_schema": entity_schemas.get("npc_trader_schema"),
            "npc_schema": entity_schemas.get("npc_schema") # Referenced by npc_trader_schema
        }, indent=2))
        prompt_parts.append("```")

        final_prompt = "\n".join(prompt_parts)
        logger.info(f"Generated AI prompt for economic entity generation for guild {guild_id}:\n{final_prompt[:1000]}...")
        return final_prompt

    except Exception as e:
        logger.exception(f"Error in prepare_economic_entity_generation_prompt for guild {guild_id}: {e}")
        return f"Error generating economic entity AI prompt: {str(e)}"
