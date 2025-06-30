import json
import logging
from typing import Optional, Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.core.database import get_db_session, transactional
from src.models import (
    GuildConfig, Location, Player, Party, GeneratedNpc, Relationship,
    PlayerQuestProgress, GeneratedQuest, QuestStep, RuleConfig, Ability, Skill
)
from src.core.crud import (
    guild_config_crud, location_crud, player_crud, party_crud,
    generated_npc_crud, relationship_crud, player_quest_progress_crud,
    generated_quest_crud, quest_step_crud, rule_config_crud, ability_crud, skill_crud
) # Assuming rule_config_crud, ability_crud, skill_crud will be created
from src.core.locations_utils import get_localized_text # Assuming this can be used broadly

logger = logging.getLogger(__name__)

# Placeholder for actual WorldState model and CRUD if it gets created
# from src.models import WorldState
# from src.core.crud import world_state_crud

async def _get_guild_main_language(session: AsyncSession, guild_id: int) -> str:
    """Fetches the main language for the guild."""
    guild_config = await guild_config_crud.get(session, id=guild_id)
    return guild_config.main_language if guild_config else "en"

async def _get_location_context(session: AsyncSession, location_id: int, guild_id: int, lang: str) -> Dict[str, Any]:
    """Gathers context about a specific location."""
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

async def _get_nearby_entities_context(session: AsyncSession, guild_id: int, location_id: int, lang: str,
                                     player_id: Optional[int] = None, party_id: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Gathers context about NPCs and other relevant entities in the location."""
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
            .join(QuestStep, PlayerQuestProgress.current_quest_step_id == QuestStep.id)
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
    # rules = await rule_config_crud.get_all_for_guild(session, guild_id=guild_id) # Assuming this method exists
    # For now, let's mock a simple rule structure.
    # In a real scenario, you'd fetch specific, relevant rules for AI context.
    all_rules_obj = await rule_config_crud.get_rules_object_for_guild(session, guild_id=guild_id) # Uses the cache

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
        "main_language_code": all_rules_obj.get_rule("guild_main_language", "en"),
        "generation_style": all_rules_obj.get_rule("ai_generation_style", "classic_fantasy"),
        "allowed_npc_races": all_rules_obj.get_rule("allowed_npc_races", ["human", "elf", "dwarf"]),
        "currency_name": all_rules_obj.get_rule("currency_name", "gold pieces")
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
                "name_i18n": {"en": "Old Man Willow", "ru": "Старик Ива"},
                "description_i18n": {"en": "A weathered old man who seems to know more than he lets on.", "ru": "Пожилой мужчина, который, кажется, знает больше, чем говорит."},
                "level": 5,
                "key_characteristics_i18n": {"en": "Has a mischievous glint in his eyes.", "ru": "В глазах озорной блеск."},
            }
        },
        "quest_schema": {
            "description": "Schema for Quests.",
            "fields": {
                "name_i18n": {"type": "object", "description": "Localized quest name."},
                "description_i18n": {"type": "object", "description": "Overall quest description."},
                "type": {"type": "string", "enum": ["main", "side", "faction", "personal"], "description": "Quest type."},
                "suggested_level": {"type": "integer", "description": "Suggested player level for this quest."},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name_i18n": {"type": "object", "description": "Localized step name."},
                            "description_i18n": {"type": "object", "description": "Localized step description/goal."},
                            "required_mechanics_json": {"type": "object", "description": "Structured goal, e.g., {'type': 'fetch', 'item_static_id': '...', 'count': 1} or {'type': 'kill', 'target_npc_static_id': '...'}"},
                        }
                    }
                },
                "rewards_json": {"type": "object", "description": "Structured rewards, e.g., {'xp': 100, 'gold': 50, 'item_static_ids': ['...']}"}
            }
        },
        "item_schema": {
             "description": "Schema for Items.",
             "fields": {
                "name_i18n": {"type": "object", "description": "Localized item name."},
                "description_i18n": {"type": "object", "description": "Localized item description."},
                "type": {"type": "string", "enum": ["weapon", "armor", "consumable", "quest_item", "misc"], "description": "Item type."},
                "properties_json": {"type": "object", "description": "Specific properties, e.g., {'damage': '1d6', 'armor_value': 5, 'effect': 'heal_2d4'}"},
                "value": {"type": "integer", "description": "Base monetary value."}
             }
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
        }
        # Add more schemas for Factions, Locations (if generating new ones) as needed.
    }

# Main API function
@transactional() # Manages session lifecycle
async def prepare_ai_prompt(
    session: AsyncSession, # Injected by @transactional
    guild_id: int,
    location_id: int,
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
        prompt_parts.append(f"  1. NPCs: Interesting characters that fit the location and world lore.")
        prompt_parts.append(f"  2. Quests: Short to medium quests that can be initiated or progressed in this location.")
        prompt_parts.append(f"  3. Items: Unique or noteworthy items that could be found or are relevant here.")
        prompt_parts.append(f"  4. Events: Small dynamic occurrences, discoveries, or minor encounters suitable for this location.")
        # prompt_parts.append(f"  5. Sub-Locations: If appropriate, minor points of interest within '{location_context.get('name', '')}'.") # If generating new locations/sub-locations

        prompt_parts.append("\n### Output Format Instructions:")
        prompt_parts.append("Please provide your response as a single JSON object. The top-level keys should be entity types (e.g., 'generated_npcs', 'generated_quests', 'generated_items', 'generated_events'). Each key should map to a list of generated entities of that type.")
        prompt_parts.append("For each entity, adhere to its schema provided below. ALL user-facing text (names, descriptions, dialogue, etc.) MUST be provided in an _i18n JSON object with keys for the primary language '{guild_main_lang}' AND 'en' (English).")
        prompt_parts.append("Example of _i18n field: \"name_i18n\": {\""+guild_main_lang+"\": \"Localized Name\", \"en\": \"English Name\"}")
        prompt_parts.append("Ensure generated content is consistent with the provided context, rules, and entity schemas.")

        prompt_parts.append("\n### Entity Schemas for Generation:")
        prompt_parts.append("```json")
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
