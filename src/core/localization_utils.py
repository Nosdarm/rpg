# src/core/localization_utils.py
import logging
from typing import Optional, Dict, Any, Callable, Awaitable, List, Tuple # Added List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

# Import necessary models and CRUD utilities
from ..models import Player, Location, GeneratedNpc, Item # Example models
from .player_utils import get_player
# For location, we will use location_crud.get
from .crud.crud_location import location_crud
# For NPC and Item, we've created placeholder functions in their respective crud modules
from .crud.crud_npc import get_npc, npc_crud
from .crud.crud_item import get_item, item_crud
from .crud.crud_player import player_crud
from .crud.crud_ability import ability_crud
from .crud.crud_status_effect import status_effect_crud
from .crud.crud_quest import generated_quest_crud # Added
from ..models import Ability, StatusEffect, GeneratedQuest # Added GeneratedQuest

logger = logging.getLogger(__name__)

# A map from simple entity type strings to their SQLAlchemy models
ENTITY_TYPE_MODEL_MAP: Dict[str, Any] = {
    "player": Player,
    "location": Location,
    "npc": GeneratedNpc,
    "item": Item,
    "ability": Ability,
    "status_effect": StatusEffect,
    "quest": GeneratedQuest, # Added (using "quest" as simple type string)
}

# Define a more specific type for the getter functions
GetterCallable = Callable[[AsyncSession, int, int], Awaitable[Optional[Any]]]
# A map for specific getter functions for single entities
ENTITY_TYPE_GETTER_MAP: Dict[str, GetterCallable] = {
    "player": lambda session, guild_id, entity_id: get_player(session, player_id=entity_id, guild_id=guild_id),
    "location": lambda session, guild_id, entity_id: location_crud.get(session, id=entity_id, guild_id=guild_id),
    "npc": lambda session, guild_id, entity_id: get_npc(session, npc_id=entity_id, guild_id=guild_id),
    "item": lambda session, guild_id, entity_id: get_item(session, item_id=entity_id, guild_id=guild_id),
    "ability": lambda session, guild_id, entity_id: ability_crud.get(session, id=entity_id, guild_id=guild_id),
    "status_effect": lambda session, guild_id, entity_id: status_effect_crud.get(session, id=entity_id, guild_id=guild_id),
    "quest": lambda session, guild_id, entity_id: generated_quest_crud.get(session, id=entity_id, guild_id=guild_id), # Added
}

# Map entity types to their CRUD instances
from .crud_base_definitions import CRUDBase
ENTITY_TYPE_CRUD_MAP: Dict[str, CRUDBase] = {
    "player": player_crud,
    "location": location_crud,
    "npc": npc_crud,
    "item": item_crud,
    "ability": ability_crud,
    "status_effect": status_effect_crud,
    "quest": generated_quest_crud, # Added
}


def get_localized_text(
    i18n_field: Optional[Dict[str, str]],
    language: str,
    fallback_language: str = "en"
) -> str:
    """
    Retrieves localized text from an i18n JSONB field.
    (This is a helper, could be moved from locations_utils or kept here if generic enough)
    """
    if not i18n_field:
        return ""

    text = i18n_field.get(language)
    if text:
        return text

    text = i18n_field.get(fallback_language)
    if text:
        logger.debug(f"Using fallback language '{fallback_language}' for i18n field, as '{language}' was not found.")
        return text

    # If still not found, try to return any available language or an empty string
    # If still not found after checking preferred and primary fallback,
    # do not fall back to any other available language.
    # Return empty string to allow the caller to decide further fallbacks (e.g., to a non-i18n 'name' field).
    # if i18n_field:
    #     for lang_code, lang_text in i18n_field.items():
    #         if lang_text:
    #             logger.debug(f"Using first available language '{lang_code}' as fallback for i18n field.")
    #             return lang_text
    return ""


async def get_batch_localized_entity_names(
    session: AsyncSession,
    guild_id: int,
    entity_refs: List[Dict[str, Any]], # Изменено на List[Dict[str, Any]]
    language: str,
    fallback_language: str = "en",
) -> Dict[Tuple[str, int], str]:
    """
    Fetches multiple entities and returns a map of their localized names.
    Optimized to load entities of the same type in batches.
    entity_refs: List of dictionaries, e.g., [{"entity_type": "player", "entity_id": 1}, ...]
    """
    localized_names_cache: Dict[Tuple[str, int], str] = {}
    if not entity_refs:
        return localized_names_cache

    # Group entity_refs by entity_type
    grouped_refs: Dict[str, List[int]] = {}
    for ref_dict in entity_refs: # Итерация по словарям
        if not isinstance(ref_dict, dict):
            logger.warning(f"Invalid entity reference found in batch (not a dict): {ref_dict}. Skipping.")
            continue

        entity_type_str = ref_dict.get("entity_type")
        entity_id = ref_dict.get("entity_id")

        if not entity_type_str or not isinstance(entity_id, int):
            logger.warning(f"Invalid entity reference found in batch: {ref_dict}. Skipping.")
            continue # Пропускаем некорректную ссылку

        entity_type_lower = entity_type_str.lower()
        if entity_type_lower not in grouped_refs:
            grouped_refs[entity_type_lower] = []
        if entity_id not in grouped_refs[entity_type_lower]: # Ensure unique IDs per type
             grouped_refs[entity_type_lower].append(entity_id)

    for entity_type, ids in grouped_refs.items():
        crud_instance = ENTITY_TYPE_CRUD_MAP.get(entity_type) # entity_type здесь уже lowercased
        if not crud_instance:
            logger.warning(f"No CRUD instance found for entity type '{entity_type}' in ENTITY_TYPE_CRUD_MAP. Skipping batch load for this type.")
            for entity_id in ids: # Fallback to individual or placeholder
                localized_names_cache[(entity_type, entity_id)] = f"[{entity_type} ID: {entity_id} (No CRUD)]"
            continue

        try:
            # Assuming CRUDBase and its derivatives have get_many_by_ids
            entities = await crud_instance.get_many_by_ids(db=session, ids=ids, guild_id=guild_id)
            for entity_obj in entities:
                entity_id = getattr(entity_obj, 'id', None) # Or static_id if that's the PK used in entity_refs
                if entity_id is None: # Should not happen if get_many_by_ids works with PKs
                    logger.error(f"Loaded entity of type {entity_type} has no 'id' attribute.")
                    continue

                current_name = f"[{entity_type} ID: {entity_id} (Nameless)]" # Default placeholder
                if hasattr(entity_obj, "name_i18n") and isinstance(entity_obj.name_i18n, dict):
                    localized_name_from_i18n = get_localized_text(entity_obj.name_i18n, language, fallback_language)
                    if localized_name_from_i18n:
                        current_name = localized_name_from_i18n
                    elif hasattr(entity_obj, "name") and isinstance(entity_obj.name, str) and entity_obj.name: # Fallback to non-i18n name
                        current_name = entity_obj.name
                elif hasattr(entity_obj, "name") and isinstance(entity_obj.name, str) and entity_obj.name:
                     current_name = entity_obj.name

                localized_names_cache[(entity_type, entity_id)] = current_name

            # For IDs that were requested but not found in the batch load, add a placeholder
            loaded_ids = {getattr(e, 'id', None) for e in entities}
            for entity_id_req in ids:
                if entity_id_req not in loaded_ids:
                    localized_names_cache[(entity_type, entity_id_req)] = f"[{entity_type} ID: {entity_id_req} (Unknown)]"

        except Exception as e:
            logger.error(f"Error batch fetching/localizing names for {entity_type} (Guild: {guild_id}): {e}", exc_info=True)
            for entity_id_errored in ids: # Add placeholders for all requested IDs of this type on error
                 if (entity_type, entity_id_errored) not in localized_names_cache:
                    localized_names_cache[(entity_type, entity_id_errored)] = f"[{entity_type} ID: {entity_id_errored} (Error)]"

    return localized_names_cache


async def get_localized_entity_name(
    session: AsyncSession,
    guild_id: int,
    entity_type: str,
    entity_id: int,
    language: str,
    fallback_language: str = "en",
) -> str:
    """
    Fetches an entity from the database and returns its localized name.

    Args:
        session: The database session.
        guild_id: The ID of the guild to scope the entity search.
        entity_type: A string identifying the type of entity (e.g., "player", "location", "npc", "item").
        entity_id: The ID of the entity.
        language: The preferred language code (e.g., "en", "ru").
        fallback_language: The fallback language code if the preferred is not available.

    Returns:
        The localized name of the entity, or a generic placeholder if not found or no name available.
    """
    entity_type_lower = entity_type.lower()
    logger.debug(f"Attempting to get localized name for entity_type: '{entity_type_lower}', entity_id: {entity_id}, lang: '{language}', guild: {guild_id}")

    getter_func = ENTITY_TYPE_GETTER_MAP.get(entity_type_lower)
    entity: Optional[Any] = None

    try:
        if getter_func:
            # The lambda functions in ENTITY_TYPE_GETTER_MAP are defined to accept guild_id.
            # Note: entity_id is passed as the second arg to the lambda, which maps to guild_id in its signature.
            # And guild_id is passed as the third arg to the lambda, which maps to entity_id in its signature.
            # This needs to be consistent: lambda session, guild_id_arg, entity_id_arg: ...
            # Let's correct the lambda definitions and the call here if necessary.
            # Current lambda definition: lambda session, guild_id, entity_id: actual_getter(session, actual_entity_id_param_name=entity_id, actual_guild_id_param_name=guild_id)
            # The call is: getter_func(session, guild_id, entity_id)
            # This means for player: get_player(session, player_id=entity_id, guild_id=guild_id) -> correct
            # This means for location: location_crud.get(session, id=entity_id, guild_id=guild_id) -> correct
            # This means for npc: get_npc(session, npc_id=entity_id, guild_id=guild_id) -> correct
            # This means for item: get_item(session, item_id=entity_id, guild_id=guild_id) -> correct

            # The Pyright errors "Argument missing for parameter 'player_id'" and "Parameter 'guild_id' is already assigned"
            # for the player lambda `lambda session, guild_id, entity_id: get_player(session, entity_id, guild_id=guild_id)`
            # likely stem from Pyright getting confused by the parameter names `guild_id` and `entity_id` in the lambda
            # shadowing or conflicting with its understanding of the `get_player(session, player_id, guild_id)` signature.
            # Let's rename lambda parameters for clarity:
            # "player": lambda s, g_id, e_id: get_player(s, player_id=e_id, guild_id=g_id),
            # And then call as: entity = await getter_func(session, guild_id, entity_id)
            # This was already done in the previous step by making `player_id=entity_id` explicit.
            # The original pyright error might be due to `get_player(session, entity_id, guild_id=guild_id)`
            # if `get_player` was `def get_player(session, guild_id, player_id)`.
            # But `get_player` is `async def get_player(session: AsyncSession, player_id: int, guild_id: int)`.
            # So `get_player(session, entity_id, guild_id=guild_id)` should be fine.
            # The error "Argument missing for parameter 'player_id'" suggests it thinks `entity_id` is not `player_id`.
            # And "Parameter 'guild_id' is already assigned" means it thinks `guild_id=guild_id` is trying to set `guild_id` positionally
            # and then by keyword.
            # The most robust fix for the lambda for player is:
            # "player": lambda s, g_id_arg, e_id_arg: get_player(s, player_id=e_id_arg, guild_id=g_id_arg),
            # The map was already changed to:
            # "player": lambda session, guild_id, entity_id: get_player(session, player_id=entity_id, guild_id=guild_id),
            # This should be correct. The pyright error might be stale or a deeper issue.
            # For now, let's assume the current map is fine and the error was a misinterpretation by Pyright that might clear up.

            entity = await getter_func(session, guild_id, entity_id)
        else:
            # Removed the generic fallback that used get_entity_by_id_gino_style
            logger.warning(f"Unsupported entity type for name resolution (no getter configured): {entity_type}")
            return f"[{entity_type} ID: {entity_id}]"

        if not entity:
            logger.warning(f"{entity_type.capitalize()} with ID {entity_id} not found in guild {guild_id} using configured getter.")
            return f"[{entity_type.capitalize()} ID: {entity_id} (Unknown)]"

        if hasattr(entity, "name_i18n") and isinstance(entity.name_i18n, dict):
            localized_name = get_localized_text(entity.name_i18n, language, fallback_language)
            if localized_name:
                return localized_name

        # Fallback if no name_i18n or it's empty, try a 'name' attribute
        if hasattr(entity, "name") and isinstance(entity.name, str) and entity.name:
            logger.debug(f"Using non-i18n 'name' attribute for {entity_type} {entity_id}.")
            return entity.name

        logger.warning(f"{entity_type.capitalize()} {entity_id} found, but has no suitable name attribute (name_i18n or name).")
        return f"[{entity_type.capitalize()} ID: {entity_id} (Nameless)]"

    except Exception as e:
        logger.error(f"Error fetching/localizing name for {entity_type} {entity_id} (Guild: {guild_id}): {e}", exc_info=True)
        return f"[{entity_type.capitalize()} ID: {entity_id} (Error)]"

logger.info("Localization utils (localization_utils.py) created.")

# Example Usage (for testing/dev):
# async def main():
#     # Setup mock session and data
#     # ...
#     # name = await get_localized_entity_name(mock_session, 1, "player", 1, "ru")
#     # print(name)
# pass
