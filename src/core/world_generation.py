# src/core/world_generation.py
import logging
from typing import Optional, Any, Dict, Tuple, List

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.ai_orchestrator import trigger_ai_generation_flow, save_approved_generation, \
    _mock_openai_api_call # Используем мок для AI
from src.core.ai_prompt_builder import prepare_ai_prompt
from src.core.ai_response_parser import parse_and_validate_ai_response, ParsedAiData, ParsedLocationData, \
    CustomValidationError
from src.core.crud.crud_location import location_crud
from src.core.game_events import log_event
from src.models import Location
from src.models.enums import EventType, ModerationStatus
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
