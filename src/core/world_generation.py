# src/core/world_generation.py
import json
import logging
from typing import Optional, Any, Dict, Tuple, List

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.ai_orchestrator import trigger_ai_generation_flow, save_approved_generation, \
    _mock_openai_api_call # Используем мок для AI
from src.core.ai_prompt_builder import prepare_ai_prompt, prepare_faction_relationship_generation_prompt
from src.core.ai_response_parser import parse_and_validate_ai_response, ParsedAiData, ParsedLocationData, \
    CustomValidationError, ParsedFactionData, ParsedRelationshipData
from src.core.crud.crud_location import location_crud
from src.core.crud.crud_faction import crud_faction
from src.core.crud.crud_relationship import crud_relationship
from src.core.game_events import log_event
from src.models import Location, GeneratedFaction, Relationship
from src.models.enums import EventType, ModerationStatus, RelationshipEntityType
from src.models.pending_generation import PendingGeneration

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
        # Ensure the AI knows we want a location. This might be part of context or a specific instruction.
        prompt_context_params["generation_type"] = "location"
        if parent_location_id:
            prompt_context_params["parent_location_id"] = parent_location_id
            # Optionally add more context about the parent if needed for the prompt
            # parent_loc_for_prompt = await location_crud.get(session, id=parent_location_id, guild_id=guild_id)
            # if parent_loc_for_prompt:
            #     prompt_context_params["parent_location_name"] = parent_loc_for_prompt.name_i18n.get('en', 'Unknown')

        prompt = await prepare_ai_prompt(
            session=session,
            guild_id=guild_id,
            location_id=location_id_context, # This context is used by prepare_ai_prompt
            player_id=player_id_context,   # This context is used by prepare_ai_prompt
            party_id=party_id_context      # This context is used by prepare_ai_prompt
            # context_params is not an accepted parameter for prepare_ai_prompt.
            # Information like "generation_type" or "parent_location_id" (from prompt_context_params)
            # would need to be handled by prepare_ai_prompt itself or by adding new specific parameters to it.
        )
        logger.debug(f"Generated AI prompt for new location in guild {guild_id}:\n{prompt[:500]}...") # Log snippet

        # 2. Call AI (using mock for now)
        mock_ai_response_str = await _mock_openai_api_call(prompt)
        logger.debug(f"Mock AI response received: {mock_ai_response_str[:500]}...")

        # 3. Parse and validate AI response
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

        # 4. Create Location record in DB
        # AI-generated locations typically won't have a predefined static_id; it's for static/key locations.
        new_location_db = await location_crud.create(
            session,
            obj_in={
                "guild_id": guild_id,
                "static_id": None, # AI-generated locations usually don't have a static_id unless specifically designed
                "name_i18n": generated_location_data.name_i18n,
                "descriptions_i18n": generated_location_data.descriptions_i18n,
                "type": generated_location_data.location_type, # Ensure this is validated against LocationType enum values
                "coordinates_json": generated_location_data.coordinates_json or {},
                "neighbor_locations_json": [], # Will be populated after handling potential_neighbors
                "generated_details_json": generated_location_data.generated_details_json or {},
                "ai_metadata_json": {"prompt_hash": hash(prompt), "raw_response_snippet": mock_ai_response_str[:200]} # Example metadata
            }
        )
        await session.flush() # To get new_location_db.id for neighbor linking

        logger.info(f"New location '{generated_location_data.name_i18n.get('en', 'N/A')}' (ID: {new_location_db.id}) data created by AI for guild {guild_id}.")

        # 5. Update connections with neighbors
        # Initialize current_neighbor_links_for_new_loc robustly
        raw_initial_neighbors = new_location_db.neighbor_locations_json
        current_neighbor_links_for_new_loc: List[Dict[str, Any]] = []
        if isinstance(raw_initial_neighbors, list):
            for item in raw_initial_neighbors:
                if isinstance(item, dict):
                    current_neighbor_links_for_new_loc.append(item)
                else:
                    logger.warning(f"Malformed neighbor item in new_location_db {new_location_db.id} initial data: {item}. Skipping.")
        elif raw_initial_neighbors is not None: # It could be a Dict or other non-list type
            logger.warning(f"New location {new_location_db.id} had non-list neighbor_locations_json: {type(raw_initial_neighbors)}. Initializing links as empty list.")
        # If raw_initial_neighbors is None, current_neighbor_links_for_new_loc remains []


        # 5a. Explicit parent linking
        if parent_location_id:
            parent_loc = await location_crud.get(session, id=parent_location_id, guild_id=guild_id)
            if parent_loc:
                default_connection_desc = {"en": "a path", "ru": "тропа"}
                actual_connection_details = connection_details_i18n or default_connection_desc

                # Link new location to parent
                if not any(n.get("id") == parent_location_id for n in current_neighbor_links_for_new_loc):
                    current_neighbor_links_for_new_loc.append({"id": parent_location_id, "type_i18n": actual_connection_details})

                # Link parent to new location
                await update_location_neighbors(session, parent_loc, new_location_db.id, actual_connection_details, add_connection=True)
                logger.info(f"Explicitly linked new location {new_location_db.id} to parent {parent_loc.id}.")
            else:
                logger.warning(f"Parent location ID {parent_location_id} not found or not in guild {guild_id} when linking new AI location {new_location_db.id}.")

        # 5b. AI suggested potential_neighbors
        if generated_location_data.potential_neighbors:
            logger.info(f"Processing AI-suggested potential neighbors for location ID {new_location_db.id}: {generated_location_data.potential_neighbors}")
            for neighbor_info in generated_location_data.potential_neighbors:
                neighbor_identifier = neighbor_info.get("static_id_or_name")
                conn_desc_i18n = neighbor_info.get("connection_description_i18n", {"en": "a path", "ru": "тропа"})

                if not neighbor_identifier:
                    logger.warning(f"Skipping potential neighbor for new loc {new_location_db.id} due to missing 'static_id_or_name': {neighbor_info}")
                    continue

                # Try to find the existing neighbor by static_id first, then by name (more complex, requires i18n name search)
                # For MVP, let's assume 'static_id_or_name' is primarily a static_id for existing locations.
                # A full name search would require a more complex lookup.
                existing_neighbor_loc = await location_crud.get_by_static_id(session, guild_id=guild_id, static_id=neighbor_identifier)
                # TODO: Add name-based lookup if static_id fails, or make it a convention for AI to provide static_id.

                if existing_neighbor_loc:
                    # Add link from new location to existing neighbor
                    current_neighbor_links_for_new_loc.append({"id": existing_neighbor_loc.id, "type_i18n": conn_desc_i18n})
                    # Add link from existing neighbor to new location
                    await update_location_neighbors(session, existing_neighbor_loc, new_location_db.id, conn_desc_i18n, add_connection=True)
                    logger.info(f"Linked new location {new_location_db.id} with existing neighbor {existing_neighbor_loc.static_id} (ID: {existing_neighbor_loc.id}).")
                else:
                    logger.warning(f"Potential neighbor with identifier '{neighbor_identifier}' not found for guild {guild_id} when linking new location {new_location_db.id}.")
                    # TODO: Handle case where AI suggests creating *another* new location as a neighbor.
                    # This would involve a recursive call or queueing, which is complex for MVP.

        # Update the new location's neighbor list if it has changed
        # This check is to avoid unnecessary DB write if list is identical (though SQLAlchemy might optimize anyway)
        if new_location_db.neighbor_locations_json is None or list(new_location_db.neighbor_locations_json) != current_neighbor_links_for_new_loc:
             new_location_db.neighbor_locations_json = current_neighbor_links_for_new_loc
             await session.flush([new_location_db]) # Ensure this change is also flushed
             logger.info(f"Finalized neighbor links for new location {new_location_db.id}: {current_neighbor_links_for_new_loc}")


        # 6. Log event
        log_details = {
            "location_id": new_location_db.id,
            "name_i18n": new_location_db.name_i18n,
            "generated_by": "ai",
            "generation_context": context, # Log original context
        }
        if parent_location_id:
            log_details["parent_location_id"] = parent_location_id
            log_details["connection_details_i18n"] = connection_details_i18n

        await log_event(
            session=session,
            guild_id=guild_id,
            event_type=EventType.WORLD_EVENT_LOCATION_GENERATED.value,
            details_json=log_details,
            location_id=new_location_db.id # The new location itself
        )

        await session.commit()
        logger.info(f"Successfully generated and saved new AI location ID {new_location_db.id} (Name: {new_location_db.name_i18n.get('en', 'N/A')}) for guild {guild_id}.")
        return new_location_db, None

    except Exception as e:
        logger.exception(f"Error in generate_location for guild {guild_id}: {e}")
        await session.rollback()
        return None, f"An unexpected error occurred during AI location generation: {str(e)}"

# world_generation.py should be focused on AI-driven generation.
# Manual map management functions (add_location_master, etc.) belong in map_management.py.

async def update_location_neighbors(
    session: AsyncSession,
    location: Location,
    neighbor_id: int,
    connection_type_i18n: Dict[str, str],
    add_connection: bool = True
) -> None:
    """
    Вспомогательная функция для добавления/удаления соседа из neighbor_locations_json локации.
    """
    # Ensure current_neighbors is strictly List[Dict[str, Any]]
    raw_neighbors = location.neighbor_locations_json or []
    current_neighbors: List[Dict[str, Any]] = []
    for item in raw_neighbors:
        if isinstance(item, dict):
            current_neighbors.append(item)
        else:
            # Log or handle malformed item if necessary
            logger.warning(f"Location {location.id} contained a malformed (non-dict) neighbor entry: {item}")

    if add_connection:
        # Проверяем, нет ли уже такой связи
        if not any(n.get("id") == neighbor_id for n in current_neighbors):
            current_neighbors.append({"id": neighbor_id, "type_i18n": connection_type_i18n})
            location.neighbor_locations_json = current_neighbors
            logger.debug(f"Added neighbor {neighbor_id} to location {location.id}")
    else: # remove_connection
        initial_len = len(current_neighbors)
        current_neighbors = [n for n in current_neighbors if n.get("id") != neighbor_id]
        if len(current_neighbors) < initial_len:
            logger.debug(f"Removed neighbor {neighbor_id} from location {location.id}")
        location.neighbor_locations_json = current_neighbors

    # session.add(location) # SQLAlchemy 2.0+ отслеживает изменения автоматически
    await session.flush([location])


async def generate_factions_and_relationships(
    session: AsyncSession,
    guild_id: int,
    # context: Optional[Dict[str, Any]] = None, # If any specific context beyond guild_id is needed
    # trigger_event_id: Optional[int] = None # If this generation is tied to a specific event
) -> Tuple[Optional[List[Location]], Optional[List[Location]], Optional[str]]: # TODO: Correct return types to Faction, Relationship
    """
    Generates factions and their relationships for a guild using AI.
    Returns (created_factions_list, created_relationships_list, None) or (None, None, error_message).
    """
    # Moved imports to module level for easier patching in tests
    # from .ai_prompt_builder import prepare_faction_relationship_generation_prompt -> This is already at module level if used by other funcs or should be.
    # from .ai_response_parser import ParsedFactionData, ParsedRelationshipData
    # from .crud import crud_faction, crud_relationship
    # from ..models import GeneratedFaction, Relationship
    # from ..models.enums import RelationshipEntityType

    logger.info(f"Starting faction and relationship generation for guild_id: {guild_id}")
    try:
        # 1. Prepare prompt for AI
        prompt = await prepare_faction_relationship_generation_prompt(session, guild_id)
        if "Error generating" in prompt: # Basic error check from prompt builder
            logger.error(f"Failed to generate faction/relationship prompt for guild {guild_id}: {prompt}")
            return None, None, prompt

        logger.debug(f"Generated AI prompt for factions/relationships in guild {guild_id}:\n{prompt[:500]}...")

        # 2. Call AI (using mock for now)
        # For faction/relationship, the mock response needs to be different.
        # TODO: Create a more specific mock or adapt _mock_openai_api_call
        # For now, let's assume _mock_openai_api_call is generic enough or we'll adapt its output structure.
        # A more realistic mock would return a JSON with "generated_factions" and "generated_relationships" keys.
        # Example mock structure:
        # mock_ai_response_str = json.dumps({
        #     "generated_factions": [
        #         {"entity_type": "faction", "static_id": "f1", "name_i18n": {"en": "Faction One", "ru": "Фракция Один"}, ...},
        #         {"entity_type": "faction", "static_id": "f2", "name_i18n": {"en": "Faction Two", "ru": "Фракция Два"}, ...}
        #     ],
        #     "generated_relationships": [
        #         {"entity_type": "relationship", "entity1_static_id": "f1", "entity1_type": "faction", "entity2_static_id": "f2", "entity2_type": "faction", "relationship_type": "rivalry", "value": -50}
        #     ]
        # })
        # Using existing mock, but it might not fit the expected structure for factions/relationships perfectly.
        # This will likely fail parsing unless the mock is adapted.
        # Let's create a dedicated mock response string here for now.
        mock_ai_response_str = json.dumps({
            "generated_factions": [
                {
                    "entity_type": "faction", "static_id": "knights_of_dawn",
                    "name_i18n": {"en": "Knights of Dawn", "ru": "Рыцари Рассвета"},
                    "description_i18n": {"en": "A noble order defending the realm.", "ru": "Благородный орден, защищающий королевство."},
                    "ideology_i18n": {"en": "Justice and Order", "ru": "Справедливость и Порядок"}
                },
                {
                    "entity_type": "faction", "static_id": "shadow_syndicate",
                    "name_i18n": {"en": "Shadow Syndicate", "ru": "Теневой Синдикат"},
                    "description_i18n": {"en": "A secretive group operating in the underworld.", "ru": "Секретная группа, действующая в преступном мире."},
                    "ideology_i18n": {"en": "Power through Stealth", "ru": "Власть через Скрытность"}
                }
            ],
            "generated_relationships": [
                {
                    "entity_type": "relationship", "entity1_static_id": "knights_of_dawn", "entity1_type": "faction",
                    "entity2_static_id": "shadow_syndicate", "entity2_type": "faction",
                    "relationship_type": "faction_standing", "value": -75
                },
                { # Example relationship with a generic player placeholder
                    "entity_type": "relationship", "entity1_static_id": "knights_of_dawn", "entity1_type": "faction",
                    "entity2_static_id": "player_default", "entity2_type": "player", # Assuming AI might generate this
                    "relationship_type": "faction_reputation", "value": 10
                }
            ]
        })

        logger.debug(f"Mock AI response for factions/relationships: {mock_ai_response_str[:500]}...")

        # 3. Parse and validate AI response
        # parse_and_validate_ai_response expects a list of entities, not a dict with top-level keys.
        # The prompt asks for a dict. So, we need to adapt how we pass data to the parser.
        # The parser currently expects a list of entity objects directly.
        # Let's assume the AI returns a list of mixed entities (factions and relationships)
        # and the prompt builder will instruct it to do so, or we adjust the parser.
        # For now, let's adapt the MOCK to be a flat list as the parser expects.
        # This means the prompt builder's instruction for output format and the parser's expectation must align.
        # If prompt asks for {"generated_factions": [], "generated_relationships": []}, parser needs an update.
        # Current parser expects: [ {faction_obj1}, {faction_obj2}, {relationship_obj1} ]
        # Let's adjust the mock output to be a flat list for now to match current parser.
        # This is a design choice: either parser handles nested structure, or AI provides flat list.
        # For now, assume AI is instructed to provide a flat list of all generated entities.
        # This also implies that ParsedAiData.generated_entities is a flat list.

        # Re-mocking based on current parser expectation (flat list of entities)
        # And the prompt builder needs to instruct AI to output this flat list.
        # For now, I'll assume the prompt builder is updated to ask for a flat list.
        # If not, this part needs to change or the parser needs to change.
        # Let's assume the output is a JSON that directly is a list of entities.
        # The prompt builder will need to be updated to ask for this.
        # Or, the parser's _validate_overall_structure is updated to handle the dict.

        # Given the current plan, the prompt asks for a dict. So the parser needs to handle it.
        # Let's assume the parser is NOT changed yet. We will extract the lists.
        raw_parsed_json = json.loads(mock_ai_response_str)
        parsed_faction_list_json = raw_parsed_json.get("generated_factions", [])
        parsed_relationship_list_json = raw_parsed_json.get("generated_relationships", [])

        all_parsed_entities_json = parsed_faction_list_json + parsed_relationship_list_json

        # Now parse this combined list
        parsed_data_or_error = await parse_and_validate_ai_response(
            raw_ai_output_text=json.dumps(all_parsed_entities_json), # Pass the combined list as a JSON string
            guild_id=guild_id
        )

        if isinstance(parsed_data_or_error, CustomValidationError):
            error_msg = f"AI response validation failed for factions/relationships: {parsed_data_or_error.message} - Details: {parsed_data_or_error.details}"
            logger.error(error_msg)
            return None, None, error_msg

        parsed_ai_data: ParsedAiData = parsed_data_or_error

        created_factions: List[GeneratedFaction] = []
        created_relationships: List[Relationship] = []
        static_id_to_db_id_map: Dict[str, int] = {}

        # Save Factions first
        for entity_data in parsed_ai_data.generated_entities:
            if isinstance(entity_data, ParsedFactionData):
                faction_to_create = {
                    "guild_id": guild_id,
                    "static_id": entity_data.static_id,
                    "name_i18n": entity_data.name_i18n,
                    "description_i18n": entity_data.description_i18n,
                    "ideology_i18n": entity_data.ideology_i18n,
                    # leader_npc_id needs to be resolved if leader_npc_static_id is provided
                    # For now, assuming leader_npc_id is set later or AI provides existing NPC ID.
                    # "leader_npc_id": None, # Placeholder
                    "resources_json": entity_data.resources_json,
                    "ai_metadata_json": entity_data.ai_metadata_json,
                }
                # Check for unique static_id within the guild before creating
                existing_faction = await crud_faction.get_by_static_id(session, guild_id=guild_id, static_id=entity_data.static_id)
                if existing_faction:
                    logger.warning(f"Faction with static_id '{entity_data.static_id}' already exists for guild {guild_id}. Skipping.")
                    # Optionally, map this static_id to the existing DB ID for relationship creation
                    static_id_to_db_id_map[entity_data.static_id] = existing_faction.id
                    created_factions.append(existing_faction) # Add existing to list if needed for return
                    continue

                new_faction_db = await crud_faction.create(session, obj_in=faction_to_create)
                await session.flush() # Ensure ID is available
                if new_faction_db:
                    created_factions.append(new_faction_db)
                    static_id_to_db_id_map[new_faction_db.static_id] = new_faction_db.id # type: ignore
                    logger.info(f"Created faction '{new_faction_db.name_i18n.get('en')}' (ID: {new_faction_db.id}, StaticID: {new_faction_db.static_id}) for guild {guild_id}")
                else:
                    logger.error(f"Failed to create faction DB entry for static_id: {entity_data.static_id}")


        # Save Relationships
        for entity_data in parsed_ai_data.generated_entities:
            if isinstance(entity_data, ParsedRelationshipData):
                e1_id = static_id_to_db_id_map.get(entity_data.entity1_static_id)
                e2_id = static_id_to_db_id_map.get(entity_data.entity2_static_id)

                # Handle generic player_default for relationships
                # We don't create a DB record for 'player_default', so its ID is conceptual (e.g., 0 or a special marker)
                # For now, we'll only create relationships if both entities are actual factions found in the map.
                # If e.g. entity2_type is 'player' and static_id is 'player_default', we might skip DB creation here
                # or handle it by linking to a conceptual player entity (e.g. player_id=0).
                # Task 35 doesn't specify saving relationships to player_default, only that AI *may suggest* them.
                # For now, only create if both are resolved to actual faction IDs.

                if e1_id is None and entity_data.entity1_type.lower() != "player": # Allow player type without DB ID for now
                    logger.warning(f"Could not find DB ID for entity1_static_id '{entity_data.entity1_static_id}' for relationship. Skipping.")
                    continue
                if e2_id is None and entity_data.entity2_type.lower() != "player":
                    logger.warning(f"Could not find DB ID for entity2_static_id '{entity_data.entity2_static_id}' for relationship. Skipping.")
                    continue

                # Determine RelationshipEntityType from string
                try:
                    entity1_type_enum = RelationshipEntityType(entity_data.entity1_type.lower())
                    entity2_type_enum = RelationshipEntityType(entity_data.entity2_type.lower())
                except ValueError:
                    logger.error(f"Invalid entity type in relationship data: {entity_data.entity1_type} or {entity_data.entity2_type}. Skipping.")
                    continue

                # Handle player_default case: if type is player and static_id is player_default, use a placeholder ID (e.g. 0)
                # This is conceptual and depends on how relationships with "all players" or "new players" are handled.
                # For now, we require actual DB IDs for non-player entities.
                final_e1_id = e1_id
                final_e2_id = e2_id

                if entity_data.entity1_type.lower() == "player" and entity_data.entity1_static_id == "player_default":
                    final_e1_id = 0 # Placeholder ID for "default player"
                elif e1_id is None: # Non-player type but ID not found
                    logger.warning(f"Entity1 static_id '{entity_data.entity1_static_id}' (type: {entity_data.entity1_type}) not resolved to DB ID. Skipping relationship.")
                    continue

                if entity_data.entity2_type.lower() == "player" and entity_data.entity2_static_id == "player_default":
                    final_e2_id = 0 # Placeholder ID for "default player"
                elif e2_id is None: # Non-player type but ID not found
                    logger.warning(f"Entity2 static_id '{entity_data.entity2_static_id}' (type: {entity_data.entity2_type}) not resolved to DB ID. Skipping relationship.")
                    continue


                relationship_to_create = {
                    "guild_id": guild_id,
                    "entity1_id": final_e1_id,
                    "entity1_type": entity1_type_enum,
                    "entity2_id": final_e2_id,
                    "entity2_type": entity2_type_enum,
                    "relationship_type": entity_data.relationship_type,
                    "value": entity_data.value,
                    # "source_log_id": trigger_event_id, # If applicable
                }
                # Check for existing relationship before creating
                # Note: crud_relationship.get_relationship_between_entities handles order
                existing_rel = await crud_relationship.get_relationship_between_entities(
                    session,
                    guild_id=guild_id,
                    entity1_id=final_e1_id, # type: ignore
                    entity1_type=entity1_type_enum,
                    entity2_id=final_e2_id, # type: ignore
                    entity2_type=entity2_type_enum
                )
                if existing_rel:
                    logger.info(f"Relationship already exists between {entity_data.entity1_static_id} and {entity_data.entity2_static_id}. Updating value from {existing_rel.value} to {entity_data.value}.")
                    existing_rel.value = entity_data.value
                    existing_rel.relationship_type = entity_data.relationship_type # Also update type if AI suggests change
                    session.add(existing_rel)
                    created_relationships.append(existing_rel)
                else:
                    new_relationship_db = await crud_relationship.create(session, obj_in=relationship_to_create)
                    if new_relationship_db:
                        created_relationships.append(new_relationship_db)
                        logger.info(f"Created relationship between '{entity_data.entity1_static_id}' and '{entity_data.entity2_static_id}' (Value: {entity_data.value}) for guild {guild_id}")
                    else:
                        logger.error(f"Failed to create relationship DB entry for {entity_data.entity1_static_id} - {entity_data.entity2_static_id}")

        # 6. Log event
        await log_event(
            session=session,
            guild_id=guild_id,
            event_type=EventType.WORLD_EVENT_FACTIONS_GENERATED.value, # Define this event type
            details_json={
                "generated_factions_count": len(created_factions),
                "generated_relationships_count": len(created_relationships),
                "faction_ids": [f.id for f in created_factions],
                # "trigger_event_id": trigger_event_id # If applicable
            }
            # entity_ids_json could list all faction IDs involved.
        )

        await session.commit()
        logger.info(f"Successfully generated and saved {len(created_factions)} factions and {len(created_relationships)} relationships for guild {guild_id}.")
        # Corrected return type
        return created_factions, created_relationships, None

    except Exception as e:
        logger.exception(f"Error in generate_factions_and_relationships for guild {guild_id}: {e}")
        await session.rollback()
        return None, None, f"An unexpected error occurred during AI faction/relationship generation: {str(e)}"
