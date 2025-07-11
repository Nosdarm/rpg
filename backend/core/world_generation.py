# src/core/world_generation.py
import json
import logging
from typing import Optional, Any, Dict, Tuple, List
import random # For quantity generation

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.ai_orchestrator import trigger_ai_generation_flow, save_approved_generation, \
    _mock_openai_api_call # Используем мок для AI
from backend.core.ai_prompt_builder import (
    prepare_ai_prompt,
    prepare_faction_relationship_generation_prompt,
    prepare_quest_generation_prompt,
    prepare_economic_entity_generation_prompt # Added for Task 43
)
from backend.core.ai_response_parser import (
    parse_and_validate_ai_response, ParsedAiData, ParsedLocationData,
    CustomValidationError, ParsedFactionData, ParsedRelationshipData, ParsedQuestData,
    ParsedItemData, ParsedNpcTraderData # Added for Task 43
)
from backend.core.crud.crud_location import location_crud
from backend.core.crud.crud_faction import crud_faction
from backend.core.crud.crud_relationship import crud_relationship
from backend.core.crud.crud_quest import generated_quest_crud, quest_step_crud, questline_crud
from backend.core.crud.crud_item import item_crud # Added for Task 43
from backend.core.crud.crud_npc import npc_crud # Added for Task 43
from backend.core.crud.crud_inventory_item import inventory_item_crud # Added for Task 43
from backend.core.game_events import log_event
from backend.models import ( # Grouped imports
    Location, GeneratedFaction, Relationship, Item, GeneratedNpc, InventoryItem
)
from backend.models.quest import GeneratedQuest
from backend.models.enums import EventType, ModerationStatus, RelationshipEntityType, OwnerEntityType # Added OwnerEntityType
from backend.models.pending_generation import PendingGeneration

logger = logging.getLogger(__name__)

async def generate_location(
    session: AsyncSession,
    guild_id: int,
    context: Optional[Dict[str, Any]] = None, # Renamed from generation_params
    parent_location_id: Optional[int] = None,
    connection_details_i18n: Optional[Dict[str, str]] = None,
    location_id_context: Optional[int] = None, # This can still be used for broader AI context
    player_id_context: Optional[int] = None,
    party_id_context: Optional[int] = None
) -> Tuple[Optional[Location], Optional[str]]:
    """
    Generates a new location using AI, saves it to the DB, and updates connections.
    Can explicitly link to a parent_location_id.
    This is the primary API function for AI-driven location generation.
    Returns (created location, None) or (None, error message).
    """
    try:
        # 1. Prepare prompt for AI
        prompt_context_params = context or {}
        prompt_context_params["generation_type"] = "location"
        if parent_location_id:
            prompt_context_params["parent_location_id"] = parent_location_id

        prompt = await prepare_ai_prompt(
            session=session,
            guild_id=guild_id,
            location_id=location_id_context,
            player_id=player_id_context,
            party_id=party_id_context
        )
        logger.debug(f"Generated AI prompt for new location in guild {guild_id}:\n{prompt[:500]}...")

        mock_ai_response_str = await _mock_openai_api_call(prompt)
        logger.debug(f"Mock AI response received: {mock_ai_response_str[:500]}...")

        parsed_data_or_error = await parse_and_validate_ai_response(
            raw_ai_output_text=mock_ai_response_str,
            guild_id=guild_id
        )

        if isinstance(parsed_data_or_error, CustomValidationError):
            error_msg = f"AI response validation failed: {parsed_data_or_error.message} - Details: {parsed_data_or_error.details}"
            logger.error(error_msg)
            return None, error_msg

        parsed_ai_data: ParsedAiData = parsed_data_or_error

        generated_location_data: Optional[ParsedLocationData] = None
        if parsed_ai_data.generated_entities:
            for entity in parsed_ai_data.generated_entities:
                if isinstance(entity, ParsedLocationData):
                    generated_location_data = entity
                    break

        if not generated_location_data:
            error_msg = "No valid location data found in AI response."
            logger.error(error_msg)
            return None, error_msg

        new_location_db = await location_crud.create(
            session,
            obj_in={
                "guild_id": guild_id,
                "static_id": None,
                "name_i18n": generated_location_data.name_i18n,
                "descriptions_i18n": generated_location_data.descriptions_i18n,
                "type": generated_location_data.location_type,
                "coordinates_json": generated_location_data.coordinates_json or {},
                "neighbor_locations_json": [],
                "generated_details_json": generated_location_data.generated_details_json or {},
                "ai_metadata_json": {"prompt_hash": hash(prompt), "raw_response_snippet": mock_ai_response_str[:200]}
            }
        )
        await session.flush()

        logger.info(f"New location '{generated_location_data.name_i18n.get('en', 'N/A')}' (ID: {new_location_db.id}) data created by AI for guild {guild_id}.")

        raw_initial_neighbors = new_location_db.neighbor_locations_json
        current_neighbor_links_for_new_loc: List[Dict[str, Any]] = []
        if isinstance(raw_initial_neighbors, list):
            for item in raw_initial_neighbors:
                if isinstance(item, dict):
                    current_neighbor_links_for_new_loc.append(item)
                else:
                    logger.warning(f"Malformed neighbor item in new_location_db {new_location_db.id} initial data: {item}. Skipping.")
        elif raw_initial_neighbors is not None:
            logger.warning(f"New location {new_location_db.id} had non-list neighbor_locations_json: {type(raw_initial_neighbors)}. Initializing links as empty list.")

        if parent_location_id:
            parent_loc = await location_crud.get(session, id=parent_location_id, guild_id=guild_id)
            if parent_loc:
                default_connection_desc = {"en": "a path", "ru": "тропа"}
                actual_connection_details = connection_details_i18n or default_connection_desc
                if not any(n.get("id") == parent_location_id for n in current_neighbor_links_for_new_loc):
                    current_neighbor_links_for_new_loc.append({"id": parent_location_id, "type_i18n": actual_connection_details})
                await update_location_neighbors(session, parent_loc, new_location_db.id, actual_connection_details, add_connection=True)
                logger.info(f"Explicitly linked new location {new_location_db.id} to parent {parent_loc.id}.")
            else:
                logger.warning(f"Parent location ID {parent_location_id} not found or not in guild {guild_id} when linking new AI location {new_location_db.id}.")

        if generated_location_data.potential_neighbors:
            logger.info(f"Processing AI-suggested potential neighbors for location ID {new_location_db.id}: {generated_location_data.potential_neighbors}")
            for neighbor_info in generated_location_data.potential_neighbors:
                neighbor_identifier = neighbor_info.get("static_id_or_name")
                conn_desc_i18n = neighbor_info.get("connection_description_i18n", {"en": "a path", "ru": "тропа"})
                if not isinstance(neighbor_identifier, str) or not neighbor_identifier:
                    logger.warning(f"Skipping potential neighbor for new loc {new_location_db.id} due to invalid or missing 'static_id_or_name': {neighbor_identifier} in {neighbor_info}")
                    continue
                existing_neighbor_loc = await location_crud.get_by_static_id(session, guild_id=guild_id, static_id=neighbor_identifier)
                if existing_neighbor_loc:
                    current_neighbor_links_for_new_loc.append({"id": existing_neighbor_loc.id, "type_i18n": conn_desc_i18n})
                    await update_location_neighbors(session, existing_neighbor_loc, new_location_db.id, conn_desc_i18n, add_connection=True)
                    logger.info(f"Linked new location {new_location_db.id} with existing neighbor {existing_neighbor_loc.static_id} (ID: {existing_neighbor_loc.id}).")
                else:
                    logger.warning(f"Potential neighbor with identifier '{neighbor_identifier}' not found for guild {guild_id} when linking new location {new_location_db.id}.")

        if new_location_db.neighbor_locations_json is None or list(new_location_db.neighbor_locations_json) != current_neighbor_links_for_new_loc:
             new_location_db.neighbor_locations_json = current_neighbor_links_for_new_loc
             await session.flush([new_location_db])
             logger.info(f"Finalized neighbor links for new location {new_location_db.id}: {current_neighbor_links_for_new_loc}")

        log_details = {
            "location_id": new_location_db.id, "name_i18n": new_location_db.name_i18n,
            "generated_by": "ai", "generation_context": context,
        }
        if parent_location_id:
            log_details["parent_location_id"] = parent_location_id
            log_details["connection_details_i18n"] = connection_details_i18n

        await log_event(
            session=session, guild_id=guild_id,
            event_type=EventType.WORLD_EVENT_LOCATION_GENERATED.value,
            details_json=log_details, location_id=new_location_db.id
        )
        await session.commit()
        logger.info(f"Successfully generated and saved new AI location ID {new_location_db.id} (Name: {new_location_db.name_i18n.get('en', 'N/A')}) for guild {guild_id}.")
        return new_location_db, None
    except Exception as e:
        logger.exception(f"Error in generate_location for guild {guild_id}: {e}")
        await session.rollback()
        return None, f"An unexpected error occurred during AI location generation: {str(e)}"

async def update_location_neighbors(
    session: AsyncSession, location: Location, neighbor_id: int,
    connection_type_i18n: Dict[str, str], add_connection: bool = True
) -> None:
    raw_neighbors = location.neighbor_locations_json or []
    current_neighbors: List[Dict[str, Any]] = []
    for item in raw_neighbors:
        if isinstance(item, dict): current_neighbors.append(item)
        else: logger.warning(f"Location {location.id} contained a malformed (non-dict) neighbor entry: {item}")

    if add_connection:
        if not any(n.get("id") == neighbor_id for n in current_neighbors):
            current_neighbors.append({"id": neighbor_id, "type_i18n": connection_type_i18n})
            location.neighbor_locations_json = current_neighbors
            logger.debug(f"Added neighbor {neighbor_id} to location {location.id}")
    else:
        initial_len = len(current_neighbors)
        current_neighbors = [n for n in current_neighbors if n.get("id") != neighbor_id]
        if len(current_neighbors) < initial_len:
            logger.debug(f"Removed neighbor {neighbor_id} from location {location.id}")
        location.neighbor_locations_json = current_neighbors
    await session.flush([location])

async def generate_factions_and_relationships(
    session: AsyncSession, guild_id: int,
) -> Tuple[Optional[List[GeneratedFaction]], Optional[List[Relationship]], Optional[str]]:
    logger.info(f"Starting faction and relationship generation for guild_id: {guild_id}")
    try:
        prompt = await prepare_faction_relationship_generation_prompt(session, guild_id)
        if "Error generating" in prompt:
            logger.error(f"Failed to generate faction/relationship prompt for guild {guild_id}: {prompt}")
            return None, None, prompt
        logger.debug(f"Generated AI prompt for factions/relationships in guild {guild_id}:\n{prompt[:500]}...")

        mock_ai_response_str = json.dumps({
            "generated_factions": [
                {"entity_type": "faction", "static_id": "knights_of_dawn", "name_i18n": {"en": "Knights of Dawn", "ru": "Рыцари Рассвета"}, "description_i18n": {"en": "A noble order defending the realm.", "ru": "Благородный орден, защищающий королевство."}, "ideology_i18n": {"en": "Justice and Order", "ru": "Справедливость и Порядок"}},
                {"entity_type": "faction", "static_id": "shadow_syndicate", "name_i18n": {"en": "Shadow Syndicate", "ru": "Теневой Синдикат"}, "description_i18n": {"en": "A secretive group operating in the underworld.", "ru": "Секретная группа, действующая в преступном мире."}, "ideology_i18n": {"en": "Power through Stealth", "ru": "Власть через Скрытность"}}
            ],
            "generated_relationships": [
                {"entity_type": "relationship", "entity1_static_id": "knights_of_dawn", "entity1_type": "faction", "entity2_static_id": "shadow_syndicate", "entity2_type": "faction", "relationship_type": "faction_standing", "value": -75},
                {"entity_type": "relationship", "entity1_static_id": "knights_of_dawn", "entity1_type": "faction", "entity2_static_id": "player_default", "entity2_type": "player", "relationship_type": "faction_reputation", "value": 10}
            ]
        })
        logger.debug(f"Mock AI response for factions/relationships: {mock_ai_response_str[:500]}...")

        raw_parsed_json = json.loads(mock_ai_response_str)
        parsed_faction_list_json = raw_parsed_json.get("generated_factions", [])
        parsed_relationship_list_json = raw_parsed_json.get("generated_relationships", [])
        all_parsed_entities_json = parsed_faction_list_json + parsed_relationship_list_json
        parsed_data_or_error = await parse_and_validate_ai_response(raw_ai_output_text=json.dumps(all_parsed_entities_json), guild_id=guild_id)

        if isinstance(parsed_data_or_error, CustomValidationError):
            error_msg = f"AI response validation failed for factions/relationships: {parsed_data_or_error.message} - Details: {parsed_data_or_error.details}"
            logger.error(error_msg)
            return None, None, error_msg
        parsed_ai_data: ParsedAiData = parsed_data_or_error
        created_factions: List[GeneratedFaction] = []
        created_relationships: List[Relationship] = []
        static_id_to_db_id_map: Dict[str, int] = {}

        for entity_data in parsed_ai_data.generated_entities:
            if isinstance(entity_data, ParsedFactionData):
                faction_to_create = {"guild_id": guild_id, "static_id": entity_data.static_id, "name_i18n": entity_data.name_i18n, "description_i18n": entity_data.description_i18n, "ideology_i18n": entity_data.ideology_i18n, "resources_json": entity_data.resources_json, "ai_metadata_json": entity_data.ai_metadata_json}
                assert entity_data.static_id is not None, "ParsedFactionData.static_id should not be None here"
                existing_faction = await crud_faction.get_by_static_id(session, guild_id=guild_id, static_id=entity_data.static_id) # type: ignore[reportArgumentType]
                if existing_faction:
                    logger.warning(f"Faction with static_id '{entity_data.static_id}' already exists for guild {guild_id}. Skipping.")
                    static_id_to_db_id_map[entity_data.static_id] = existing_faction.id # type: ignore
                    created_factions.append(existing_faction)
                    continue
                new_faction_db = await crud_faction.create(session, obj_in=faction_to_create)
                await session.flush()
                if new_faction_db:
                    created_factions.append(new_faction_db)
                    static_id_to_db_id_map[new_faction_db.static_id] = new_faction_db.id # type: ignore
                    logger.info(f"Created faction '{new_faction_db.name_i18n.get('en')}' (ID: {new_faction_db.id}, StaticID: {new_faction_db.static_id}) for guild {guild_id}")
                else: logger.error(f"Failed to create faction DB entry for static_id: {entity_data.static_id}")

        for entity_data in parsed_ai_data.generated_entities:
            if isinstance(entity_data, ParsedRelationshipData):
                e1_id = static_id_to_db_id_map.get(entity_data.entity1_static_id)
                e2_id = static_id_to_db_id_map.get(entity_data.entity2_static_id)
                if e1_id is None and entity_data.entity1_type.lower() != "player":
                    logger.warning(f"Could not find DB ID for entity1_static_id '{entity_data.entity1_static_id}' for relationship. Skipping.")
                    continue
                if e2_id is None and entity_data.entity2_type.lower() != "player":
                    logger.warning(f"Could not find DB ID for entity2_static_id '{entity_data.entity2_static_id}' for relationship. Skipping.")
                    continue
                TYPE_STRING_TO_ENUM_MAP = {"faction": RelationshipEntityType.GENERATED_FACTION, "generated_faction": RelationshipEntityType.GENERATED_FACTION, "npc": RelationshipEntityType.GENERATED_NPC, "generated_npc": RelationshipEntityType.GENERATED_NPC, "player": RelationshipEntityType.PLAYER, "party": RelationshipEntityType.PARTY}
                try:
                    entity1_type_enum = TYPE_STRING_TO_ENUM_MAP[entity_data.entity1_type.lower()]
                    entity2_type_enum = TYPE_STRING_TO_ENUM_MAP[entity_data.entity2_type.lower()]
                except KeyError:
                    logger.error(f"Invalid or unmapped entity type in relationship data: '{entity_data.entity1_type}' or '{entity_data.entity2_type}'. Skipping relationship.")
                    continue
                final_e1_id = e1_id
                final_e2_id = e2_id
                if entity_data.entity1_type.lower() == "player" and entity_data.entity1_static_id == "player_default": final_e1_id = 0
                elif e1_id is None:
                    logger.warning(f"Entity1 static_id '{entity_data.entity1_static_id}' (type: {entity_data.entity1_type}) not resolved to DB ID. Skipping relationship.")
                    continue
                if entity_data.entity2_type.lower() == "player" and entity_data.entity2_static_id == "player_default": final_e2_id = 0
                elif e2_id is None:
                    logger.warning(f"Entity2 static_id '{entity_data.entity2_static_id}' (type: {entity_data.entity2_type}) not resolved to DB ID. Skipping relationship.")
                    continue
                relationship_to_create = {"guild_id": guild_id, "entity1_id": final_e1_id, "entity1_type": entity1_type_enum, "entity2_id": final_e2_id, "entity2_type": entity2_type_enum, "relationship_type": entity_data.relationship_type, "value": entity_data.value}
                existing_rel = await crud_relationship.get_relationship_between_entities(session, guild_id=guild_id, entity1_id=final_e1_id, entity1_type=entity1_type_enum, entity2_id=final_e2_id, entity2_type=entity2_type_enum) # type: ignore
                if existing_rel:
                    logger.info(f"Relationship already exists between {entity_data.entity1_static_id} and {entity_data.entity2_static_id}. Updating value from {existing_rel.value} to {entity_data.value}.")
                    existing_rel.value = entity_data.value
                    existing_rel.relationship_type = entity_data.relationship_type
                    session.add(existing_rel)
                    created_relationships.append(existing_rel)
                else:
                    new_relationship_db = await crud_relationship.create(session, obj_in=relationship_to_create)
                    if new_relationship_db:
                        created_relationships.append(new_relationship_db)
                        logger.info(f"Created relationship between '{entity_data.entity1_static_id}' and '{entity_data.entity2_static_id}' (Value: {entity_data.value}) for guild {guild_id}")
                    else: logger.error(f"Failed to create relationship DB entry for {entity_data.entity1_static_id} - {entity_data.entity2_static_id}")

        await log_event(session=session, guild_id=guild_id, event_type=EventType.WORLD_EVENT_FACTIONS_GENERATED.value, details_json={"generated_factions_count": len(created_factions), "generated_relationships_count": len(created_relationships), "faction_ids": [f.id for f in created_factions]})
        await session.commit()
        logger.info(f"Successfully generated and saved {len(created_factions)} factions and {len(created_relationships)} relationships for guild {guild_id}.")
        return created_factions, created_relationships, None
    except Exception as e:
        logger.exception(f"Error in generate_factions_and_relationships for guild {guild_id}: {e}")
        await session.rollback()
        return None, None, f"An unexpected error occurred during AI faction/relationship generation: {str(e)}"

async def generate_quests_for_guild(
    session: AsyncSession, guild_id: int, player_id_context: Optional[int] = None, location_id_context: Optional[int] = None,
) -> Tuple[Optional[List[GeneratedQuest]], Optional[str]]:
    from backend.models.quest import Questline, QuestStep
    logger.info(f"Starting quest generation for guild_id: {guild_id}")
    try:
        prompt = await prepare_quest_generation_prompt(session, guild_id, player_id_context=player_id_context, location_id_context=location_id_context)
        if "Error generating" in prompt:
            logger.error(f"Failed to generate quest prompt for guild {guild_id}: {prompt}")
            return None, prompt
        logger.debug(f"Generated AI prompt for quests in guild {guild_id}:\n{prompt[:500]}...")
        mock_ai_response_str = json.dumps([{"entity_type": "quest", "static_id": "first_sample_quest_01", "title_i18n": {"en": "The Missing Scroll", "ru": "Пропавший Свиток"}, "summary_i18n": {"en": "A valuable scroll has been stolen from the library.", "ru": "Ценный свиток был украден из библиотеки."}, "min_level": 1, "steps": [{"title_i18n": {"en": "Ask the Librarian", "ru": "Спросить Библиотекаря"}, "description_i18n": {"en": "Speak to Librarian Elara about the theft.", "ru": "Поговорить с Библиотекарем Эларой о краже."}, "step_order": 0, "required_mechanics_json": {"type": "dialogue", "target_npc_static_id": "librarian_elara", "required_dialogue_outcome_tag": "clue_obtained"}}, {"title_i18n": {"en": "Find the Scroll", "ru": "Найти Свиток"}, "description_i18n": {"en": "Based on the clue, find the stolen scroll.", "ru": "Основываясь на подсказке, найти украденный свиток."}, "step_order": 1, "required_mechanics_json": {"type": "explore_and_fetch", "target_item_static_id": "stolen_scroll_xyz", "location_hint_key": "thief_hideout_location"}}], "rewards_json": {"xp": 150, "gold": 25}}])
        logger.debug(f"Mock AI response for quests: {mock_ai_response_str[:500]}...")
        parsed_data_or_error = await parse_and_validate_ai_response(raw_ai_output_text=mock_ai_response_str, guild_id=guild_id)
        if isinstance(parsed_data_or_error, CustomValidationError):
            error_msg = f"AI response validation failed for quests: {parsed_data_or_error.message} - Details: {parsed_data_or_error.details}"
            logger.error(error_msg)
            return None, error_msg
        parsed_ai_data: ParsedAiData = parsed_data_or_error
        created_quests_db: List[GeneratedQuest] = []
        for entity_data in parsed_ai_data.generated_entities:
            if isinstance(entity_data, ParsedQuestData):
                parsed_quest: ParsedQuestData = entity_data
                questline_db_id: Optional[int] = None
                if parsed_quest.questline_static_id:
                    existing_questline = await questline_crud.get_by_static_id(session, guild_id=guild_id, static_id=parsed_quest.questline_static_id)
                    if existing_questline: questline_db_id = existing_questline.id
                    else: logger.warning(f"Questline with static_id '{parsed_quest.questline_static_id}' not found for quest '{parsed_quest.static_id}'. Quest will be standalone.")
                quest_to_create_data = {"guild_id": guild_id, "static_id": parsed_quest.static_id, "title_i18n": parsed_quest.title_i18n, "description_i18n": parsed_quest.summary_i18n, "questline_id": questline_db_id, "min_level": parsed_quest.min_level, "rewards_json": parsed_quest.rewards_json, "ai_metadata_json": parsed_quest.ai_metadata_json}
                existing_db_quest = await generated_quest_crud.get_by_static_id(session, guild_id=guild_id, static_id=parsed_quest.static_id)
                if existing_db_quest:
                    logger.warning(f"Quest with static_id '{parsed_quest.static_id}' already exists for guild {guild_id}. Skipping creation.")
                    created_quests_db.append(existing_db_quest)
                    continue
                new_quest_db = await generated_quest_crud.create(session, obj_in=quest_to_create_data)
                await session.flush()
                if new_quest_db:
                    for step_data in parsed_quest.steps:
                        step_to_create_data = {"quest_id": new_quest_db.id, "step_order": step_data.step_order, "title_i18n": step_data.title_i18n, "description_i18n": step_data.description_i18n, "required_mechanics_json": step_data.required_mechanics_json, "abstract_goal_json": step_data.abstract_goal_json, "consequences_json": step_data.consequences_json}
                        await quest_step_crud.create(session, obj_in=step_to_create_data)
                    await session.refresh(new_quest_db, attribute_names=['steps'])
                    created_quests_db.append(new_quest_db)
                    logger.info(f"Created quest '{new_quest_db.title_i18n.get('en')}' (ID: {new_quest_db.id}, StaticID: {new_quest_db.static_id}) with {len(new_quest_db.steps)} steps for guild {guild_id}")
                else: logger.error(f"Failed to create GeneratedQuest DB entry for static_id: {parsed_quest.static_id}")
        await log_event(session=session, guild_id=guild_id, event_type=EventType.WORLD_EVENT_QUESTS_GENERATED.value, details_json={"generated_quests_count": len(created_quests_db), "quest_ids": [q.id for q in created_quests_db], "context": {"player_id_context": player_id_context, "location_id_context": location_id_context}})
        await session.commit()
        logger.info(f"Successfully generated and saved {len(created_quests_db)} quests for guild {guild_id}.")
        return created_quests_db, None
    except Exception as e:
        logger.exception(f"Error in generate_quests_for_guild for guild {guild_id}: {e}")
        await session.rollback()
        return None, f"An unexpected error occurred during AI quest generation: {str(e)}"

async def generate_economic_entities(
    session: AsyncSession, guild_id: int,
) -> Tuple[Optional[List[Item]], Optional[List[GeneratedNpc]], Optional[str]]:
    logger.info(f"Starting economic entity generation for guild_id: {guild_id}")
    try:
        prompt = await prepare_economic_entity_generation_prompt(session, guild_id)
        if "Error generating" in prompt:
            logger.error(f"Failed to generate economic entity prompt for guild {guild_id}: {prompt}")
            return None, None, prompt
        logger.debug(f"Generated AI prompt for economic entities in guild {guild_id}:\n{prompt[:500]}...")
        mock_ai_response_str = json.dumps([{"entity_type": "item", "static_id": "iron_sword_01", "name_i18n": {"en": "Iron Sword", "ru": "Железный Меч"}, "description_i18n": {"en": "A basic but reliable iron sword.", "ru": "Простой, но надежный железный меч."}, "item_type": "weapon", "properties_json": {"damage": "1d6", "type": "slashing"}, "base_value": 50}, {"entity_type": "item", "static_id": "healing_potion_minor_01", "name_i18n": {"en": "Minor Healing Potion", "ru": "Малое Зелье Лечения"}, "description_i18n": {"en": "Restores a small amount of health.", "ru": "Восстанавливает небольшое количество здоровья."}, "item_type": "consumable", "properties_json": {"effect": "heal", "amount": "2d4+2"}, "base_value": 25}, {"entity_type": "npc_trader", "static_id": "trader_boris_01", "name_i18n": {"en": "Boris the Blacksmith", "ru": "Борис Кузнец"}, "description_i18n": {"en": "A sturdy blacksmith selling common weapons and armor.", "ru": "Крепкий кузнец, торгующий обычным оружием и броней."}, "role_i18n": {"en": "Blacksmith", "ru": "Кузнец"}, "inventory_template_key": "blacksmith_common_template", "stats": {"level": 5}}, {"entity_type": "npc_trader", "static_id": "trader_elara_01", "name_i18n": {"en": "Elara the Herbalist", "ru": "Элара Травница"}, "description_i18n": {"en": "An old woman selling various herbs and potions.", "ru": "Старушка, продающая различные травы и зелья."}, "role_i18n": {"en": "Herbalist", "ru": "Травница"}, "generated_inventory_items": [{"item_static_id": "healing_potion_minor_01", "quantity_min": 3, "quantity_max": 5, "chance_to_appear": 0.9}, {"item_static_id": "mana_potion_minor_01", "quantity_min": 1, "quantity_max": 3, "chance_to_appear": 0.7}], "stats": {"level": 3}}])
        logger.debug(f"Mock AI response for economic entities: {mock_ai_response_str[:500]}...")
        parsed_data_or_error = await parse_and_validate_ai_response(raw_ai_output_text=mock_ai_response_str, guild_id=guild_id)
        if isinstance(parsed_data_or_error, CustomValidationError):
            error_msg = f"AI response validation failed for economic entities: {parsed_data_or_error.message} - Details: {parsed_data_or_error.details}"
            logger.error(error_msg)
            return None, None, error_msg
        parsed_ai_data: ParsedAiData = parsed_data_or_error
        created_items_db: List[Item] = []
        created_traders_db: List[GeneratedNpc] = []
        item_static_to_db_id_map: Dict[str, int] = {}

        for entity_data in parsed_ai_data.generated_entities:
            if isinstance(entity_data, ParsedItemData):
                assert entity_data.static_id is not None, "static_id from ParsedItemData should be a string"
                existing_item = await item_crud.get_by_static_id(session, guild_id=guild_id, static_id=entity_data.static_id)
                if existing_item:
                    logger.warning(f"Item with static_id '{entity_data.static_id}' already exists for guild {guild_id}. Skipping creation. DB ID: {existing_item.id}")
                    item_static_to_db_id_map[existing_item.static_id] = existing_item.id # type: ignore
                    created_items_db.append(existing_item)
                    continue
                item_to_create_data = {"guild_id": guild_id, "static_id": entity_data.static_id, "name_i18n": entity_data.name_i18n, "description_i18n": entity_data.description_i18n, "item_type_i18n": {"en": entity_data.item_type, "ru": entity_data.item_type}, "properties_json": entity_data.properties_json, "base_value": entity_data.base_value}
                new_item_db = await item_crud.create(session, obj_in=item_to_create_data)
                await session.flush()
                if new_item_db:
                    created_items_db.append(new_item_db)
                    item_static_to_db_id_map[new_item_db.static_id] = new_item_db.id # type: ignore
                    logger.info(f"Created item '{new_item_db.name_i18n.get('en')}' (ID: {new_item_db.id}, StaticID: {new_item_db.static_id}) for guild {guild_id}")
                else: logger.error(f"Failed to create Item DB entry for static_id: {entity_data.static_id}")

        for entity_data in parsed_ai_data.generated_entities:
            if isinstance(entity_data, ParsedNpcTraderData):
                existing_npc = await npc_crud.get_by_static_id(session, guild_id=guild_id, static_id=entity_data.static_id)
                if existing_npc:
                    logger.warning(f"NPC Trader with static_id '{entity_data.static_id}' already exists for guild {guild_id}. Skipping creation.")
                    created_traders_db.append(existing_npc)
                    continue
                npc_properties = entity_data.stats or {}
                if entity_data.role_i18n: npc_properties["role_i18n"] = entity_data.role_i18n
                if entity_data.inventory_template_key: npc_properties["inventory_template_key"] = entity_data.inventory_template_key
                npc_to_create_data = {"guild_id": guild_id, "static_id": entity_data.static_id, "name_i18n": entity_data.name_i18n, "description_i18n": entity_data.description_i18n, "npc_type_i18n": entity_data.role_i18n, "properties_json": npc_properties}
                new_npc_db = await npc_crud.create(session, obj_in=npc_to_create_data)
                await session.flush()
                if new_npc_db:
                    created_traders_db.append(new_npc_db)
                    logger.info(f"Created NPC Trader '{new_npc_db.name_i18n.get('en')}' (ID: {new_npc_db.id}, StaticID: {new_npc_db.static_id}) for guild {guild_id}")
                    if entity_data.generated_inventory_items:
                        for inv_item_data in entity_data.generated_inventory_items:
                            item_db_id: Optional[int] = item_static_to_db_id_map.get(inv_item_data.item_static_id)
                            actual_item_static_id_for_logging = inv_item_data.item_static_id

                            if not item_db_id:
                                item_static_id_to_lookup = inv_item_data.item_static_id
                                # assert item_static_id_to_lookup is not None # This didn't help pyright, Pydantic model should ensure str
                                if not item_static_id_to_lookup:
                                    logger.warning(f"Empty item_static_id in inventory data for NPC {new_npc_db.static_id}. Skipping item.")
                                    continue

                                existing_item_for_inv = await item_crud.get_by_static_id(session, guild_id=guild_id, static_id=item_static_id_to_lookup) # type: ignore[reportArgumentType]
                                if existing_item_for_inv:
                                    item_db_id = existing_item_for_inv.id
                                    item_static_to_db_id_map[item_static_id_to_lookup] = item_db_id
                                else:
                                    logger.warning(f"Item with static_id '{item_static_id_to_lookup}' not found for NPC {new_npc_db.static_id}'s inventory. Skipping item.")
                                    continue

                            if item_db_id is None:
                                logger.error(f"Critical internal error: item_db_id is None for item '{actual_item_static_id_for_logging}' for NPC {new_npc_db.static_id} despite checks. Skipping.")
                                continue

                            quantity = inv_item_data.quantity_min
                            if inv_item_data.quantity_max > inv_item_data.quantity_min:
                                quantity = random.randint(inv_item_data.quantity_min, inv_item_data.quantity_max)

                            if inv_item_data.chance_to_appear < 1.0:
                                if random.random() > inv_item_data.chance_to_appear:
                                     logger.debug(f"Item {actual_item_static_id_for_logging} did not appear due to chance ({inv_item_data.chance_to_appear}) for NPC {new_npc_db.static_id}")
                                     continue

                            await inventory_item_crud.add_item_to_owner(
                                session=session, guild_id=guild_id, owner_entity_id=new_npc_db.id,
                                owner_entity_type=OwnerEntityType.GENERATED_NPC, item_id=item_db_id,
                                quantity=quantity
                            )
                            logger.info(f"Added item '{actual_item_static_id_for_logging}' (Qty: {quantity}) to NPC {new_npc_db.static_id}'s inventory.")
                else: logger.error(f"Failed to create NPC Trader DB entry for static_id: {entity_data.static_id}")

        event_type_value = getattr(EventType, "WORLD_EVENT_ECONOMIC_ENTITIES_GENERATED", EventType.SYSTEM_EVENT).value
        await log_event(
            session=session, guild_id=guild_id, event_type=event_type_value,
            details_json={"generated_items_count": len(created_items_db), "generated_traders_count": len(created_traders_db), "item_ids": [item.id for item in created_items_db if item.id is not None], "trader_ids": [npc.id for npc in created_traders_db if npc.id is not None]}
        )
        await session.commit()
        logger.info(f"Successfully generated and saved {len(created_items_db)} items and {len(created_traders_db)} NPC traders for guild {guild_id}.")
        return created_items_db, created_traders_db, None
    except Exception as e:
        logger.exception(f"Error in generate_economic_entities for guild {guild_id}: {e}")
        await session.rollback()
        return None, None, f"An unexpected error occurred during AI economic entity generation: {str(e)}"
