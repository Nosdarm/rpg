from typing import Optional, Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.location import Location
from .crud.crud_location import location_crud # Specific CRUD for Location

async def get_location(db: AsyncSession, guild_id: int, location_id: int) -> Optional[Location]:
    """
    Retrieves a specific location by its primary ID, ensuring it belongs to the specified guild.

    :param db: The database session.
    :param guild_id: The ID of the guild.
    :param location_id: The primary key ID of the location.
    :return: The Location object or None if not found or not matching guild_id.
    """
    # CRUDBase.get() already handles filtering by primary key and optionally by guild_id
    return await location_crud.get(db, id=location_id, guild_id=guild_id)

async def get_location_by_static_id(db: AsyncSession, guild_id: int, static_id: str) -> Optional[Location]:
    """
    Retrieves a specific location by its static_id, ensuring it belongs to the specified guild.

    :param db: The database session.
    :param guild_id: The ID of the guild.
    :param static_id: The static_id of the location.
    :return: The Location object or None if not found.
    """
    return await location_crud.get_by_static_id(db, guild_id=guild_id, static_id=static_id)


# Placeholder for the i18n utility function, to be implemented in the next step.
# This utility will be more generic for any model with _i18n fields.
def get_localized_text(
    entity_with_i18n_fields: Any,
    field_name_base: str,
    language: str,
    fallback_language: str = 'en'
) -> str:
    """
    Retrieves localized text from an entity's i18n JSON field.
    Example: field_name_base='name', language='fr' -> accesses entity.name_i18n['fr']

    :param entity_with_i18n_fields: The ORM entity instance.
    :param field_name_base: The base name of the field (e.g., "name", "description").
                            The function will look for attributes like "name_i18n".
    :param language: The desired language code (e.g., "en", "ru", "fr").
    :param fallback_language: The language code to use if the desired language is not found.
    :return: The localized text, or fallback text, or an empty string if neither is found.
    """
    i18n_field_name = f"{field_name_base}_i18n"
    logger_instance = logging.getLogger(__name__) # Get logger instance

    if not hasattr(entity_with_i18n_fields, i18n_field_name):
        logger_instance.debug(
            f"Entity {type(entity_with_i18n_fields).__name__} (ID: {getattr(entity_with_i18n_fields, 'id', 'N/A')}) "
            f"has no attribute {i18n_field_name} for language '{language}', fallback '{fallback_language}'."
        )
        return ""

    i18n_dict: Optional[Dict[str, str]] = getattr(entity_with_i18n_fields, i18n_field_name)

    if not isinstance(i18n_dict, dict):
        logger_instance.warning(
            f"Attribute {i18n_field_name} on {type(entity_with_i18n_fields).__name__} "
            f"(ID: {getattr(entity_with_i18n_fields, 'id', 'N/A')}) is not a dict (type: {type(i18n_dict)}). "
            f"Language: '{language}', fallback: '{fallback_language}'."
        )
        return ""

    text = i18n_dict.get(language)
    if text is not None:
        return text

    # If desired language and fallback language are the same, no need to check again
    if language != fallback_language:
        text = i18n_dict.get(fallback_language)
        if text is not None:
            logger_instance.debug(
                f"Using fallback language '{fallback_language}' for {i18n_field_name} on "
                f"{type(entity_with_i18n_fields).__name__} (ID: {getattr(entity_with_i18n_fields, 'id', 'N/A')}). "
                f"Original language '{language}' not found."
            )
            return text

    # Fallback to the first available language if specific and fallback are missing
    if i18n_dict:
        first_available_value = next(iter(i18n_dict.values()), None)
        if first_available_value is not None:
            logger_instance.debug(
                f"Using first available language text for {i18n_field_name} on "
                f"{type(entity_with_i18n_fields).__name__} (ID: {getattr(entity_with_i18n_fields, 'id', 'N/A')}). "
                f"Neither '{language}' nor '{fallback_language}' found."
            )
            return first_available_value

    logger_instance.debug(
        f"No translation found for {i18n_field_name} on {type(entity_with_i18n_fields).__name__} "
        f"(ID: {getattr(entity_with_i18n_fields, 'id', 'N/A')}) for language '{language}' or fallback '{fallback_language}'. "
        f"Available keys: {list(i18n_dict.keys()) if i18n_dict else 'none'}."
    )
    return "" # Default if no text found at all

# Example Usage (conceptual, assuming 'location' is a fetched Location object):
# L = await get_location(db, guild_id=123, location_id=1)
# if L:
#   location_name_fr = get_localized_text(L, "name", "fr", "en")
#   location_desc_en = get_localized_text(L, "descriptions", "en", "de") # 'descriptions_i18n'
#
#   # If L.name_i18n = {"en": "Hello", "ru": "Привет"}
#   get_localized_text(L, "name", "ru") -> "Привет"
#   get_localized_text(L, "name", "fr", "en") -> "Hello"
#   get_localized_text(L, "name", "de", "es") -> "Hello" (if 'en' is the first in dict) or ""
#   get_localized_text(L, "name", "de") -> "Hello" (if 'en' is the first in dict) or "" (if fallback not specified/found)
#
#   # If L.descriptions_i18n = {}
#   get_localized_text(L, "descriptions", "en") -> ""

# This file can be expanded with more location-specific logic or utilities later.
# For example, functions to find neighbors, check connectivity, etc.
# For now, it primarily hosts the requested getter functions.
import logging
logger = logging.getLogger(__name__)
logger.info("Location utilities (get_location, get_location_by_static_id, get_localized_text) defined.")
