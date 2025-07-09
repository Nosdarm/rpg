from typing import Optional, Any, Dict, List
import logging # Added import

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.location import Location
from .crud.crud_location import location_crud # Specific CRUD for Location

# Define logger at module level
logger = logging.getLogger(__name__)

async def get_location(db: AsyncSession, guild_id: int, location_id: int) -> Optional[Location]:
    """
    Retrieves a specific location by its primary ID, ensuring it belongs to the specified guild.
    """
    return await location_crud.get(db, id=location_id, guild_id=guild_id)

async def get_location_by_static_id(db: AsyncSession, guild_id: int, static_id: str) -> Optional[Location]:
    """
    Retrieves a specific location by its static_id, ensuring it belongs to the specified guild.
    """
    return await location_crud.get_by_static_id(db, guild_id=guild_id, static_id=static_id)

def get_localized_text(
    i18n_dict: Optional[Dict[str, str]],
    language: str,
    default_lang: str = "en"
) -> Optional[str]:
    """
    Retrieves localized text from an i18n dictionary.

    :param i18n_dict: The dictionary containing language codes as keys and text as values.
    :param language: The desired language code (e.g., "en", "ru", "fr").
    :param default_lang: The language code to use if the desired language is not found.
    :return: The localized text, or fallback text, or None if neither is found.
    """
    if not isinstance(i18n_dict, dict):
        # logger.warning(f"Provided i18n_field is not a dict (type: {type(i18n_dict)}). Lang: {language}")
        return None

    text = i18n_dict.get(language)
    if text is not None: # Handles empty string correctly, returns it if present
        return text

    if language != default_lang: # Avoid re-checking if lang is already default_lang
        text = i18n_dict.get(default_lang)
        if text is not None:
            # logger.debug(f"Using fallback language '{default_lang}' for i18n_dict. Original lang '{language}' not found.")
            return text

    # Fallback to the very first available language if specific and default_lang are missing and dict is not empty
    # This behavior might be desirable or not depending on requirements.
    # For now, let's keep it simple: if requested lang and default_lang fail, return None.
    # if i18n_dict:
    #     first_available_value = next(iter(i18n_dict.values()), None)
    #     if first_available_value is not None:
    #         # logger.debug(f"Using first available language for i18n_dict. Lang '{language}' and fallback '{default_lang}' not found.")
    #         return first_available_value

    # logger.debug(f"No translation found in i18n_dict for lang '{language}' or fallback '{default_lang}'. Keys: {list(i18n_dict.keys()) if i18n_dict else 'none'}.")
    return None

logger.info("Location utilities (get_location, get_location_by_static_id, get_localized_text) defined.")
