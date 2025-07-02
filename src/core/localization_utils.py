# src/core/localization_utils.py
import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

# Import necessary models and CRUD utilities
# These will be specific and need to be added as new entity types are supported
from ..models import Player, Location, GeneratedNpc, Item # Example models
# Assuming a generic way to get entities or specific CRUDs for each
from .crud_base_definitions import get_entity_by_id_gino_style # Assuming a generic getter like this exists or will be adapted
from .player_utils import get_player
from .locations_utils import get_location_by_id # Assuming this is the correct name
from .crud.crud_npc import get_npc # Placeholder for actual NPC getter
from .crud.crud_item import get_item # Placeholder for actual Item getter


logger = logging.getLogger(__name__)

# A map from simple entity type strings to their SQLAlchemy models
# This will need to be expanded as more entity types are supported for naming.
ENTITY_TYPE_MODEL_MAP: Dict[str, Any] = {
    "player": Player,
    "location": Location,
    "npc": GeneratedNpc, # Assuming GeneratedNpc is the model for NPCs
    "item": Item,
    # Add other entity types here, e.g., "faction", "quest"
}

# A map for specific getter functions if a generic one isn't suitable for all
# This provides more flexibility if some entities need special loading logic for their names.
ENTITY_TYPE_GETTER_MAP: Dict[str, callable] = {
    "player": lambda session, guild_id, entity_id: get_player(session, entity_id, guild_id=guild_id),
    "location": lambda session, guild_id, entity_id: get_location_by_id(session, location_id=entity_id, guild_id=guild_id),
    # For NPCs and Items, assuming direct CRUD access or specific utils like get_player/get_location
    # These might need to be adjusted based on actual CRUD implementations
    "npc": lambda session, guild_id, entity_id: get_npc(session, npc_id=entity_id, guild_id=guild_id), # Placeholder
    "item": lambda session, guild_id, entity_id: get_item(session, item_id=entity_id, guild_id=guild_id), # Placeholder
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
    if i18n_field:
        for lang_code, lang_text in i18n_field.items():
            if lang_text:
                logger.debug(f"Using first available language '{lang_code}' as fallback for i18n field.")
                return lang_text
    return ""


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

    model_class = ENTITY_TYPE_MODEL_MAP.get(entity_type_lower)
    getter_func = ENTITY_TYPE_GETTER_MAP.get(entity_type_lower)

    entity: Any = None

    try:
        if getter_func:
            # Some getters might not need guild_id if entity_id is globally unique and getter handles it,
            # but it's good practice to pass it if the getter supports it for guild-scoped entities.
            # The lambda functions in ENTITY_TYPE_GETTER_MAP are defined to accept guild_id.
            entity = await getter_func(session, guild_id, entity_id)
        elif model_class:
            # Fallback to a generic getter if no specific getter is mapped but model is.
            # This assumes get_entity_by_id_gino_style can fetch by PK and optionally filters by guild_id if the model has it.
            # Adjust this call based on your actual generic getter's signature.
            # If your generic getter requires guild_id, ensure it's passed.
            # entity = await get_entity_by_id_gino_style(session, model_class, entity_id)
            # For models that are always guild-scoped, you might need:
            entity = await get_entity_by_id_gino_style(session, model_class, entity_id, guild_id=guild_id) # Assuming generic takes guild_id
            logger.warning(f"Using generic getter for {entity_type_lower}. Ensure it's appropriate.")

        else:
            logger.warning(f"Unsupported entity type for name resolution: {entity_type}")
            return f"[{entity_type} ID: {entity_id}]"

        if not entity:
            logger.warning(f"{entity_type.capitalize()} with ID {entity_id} not found in guild {guild_id}.")
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
