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

async def get_localized_message_template(
    session: AsyncSession,
    guild_id: Optional[int],
    message_key: str,
    language_code: str,
    default_template: str,
    rule_prefix: str = "master_cmd_feedback:" # Можно сделать настраиваемым, если нужно
) -> str:
    """
    Retrieves a localized message template from RuleConfig.

    Args:
        session: The database session.
        guild_id: The ID of the guild. Can be None for global/DM contexts.
        message_key: The specific key for the message (e.g., "player_view:title").
        language_code: The preferred language code (e.g., "ru", "en-US").
        default_template: The default template string to return if not found.
        rule_prefix: The prefix for RuleConfig keys for these messages.

    Returns:
        The localized message template string.
    """
    from .rules import get_rule # Local import to avoid circular dependency at module load time

    if guild_id is None:
        logger.debug(f"guild_id is None for message_key '{message_key}'. Returning default template.")
        return default_template

    full_rule_key = f"{rule_prefix}{message_key}"

    # get_rule returns the value_json, which should be a dict of lang_code: template_string
    # e.g., {"en": "Player not found: {player_id}", "ru": "Игрок не найден: {player_id}"}
    i18n_templates: Optional[Dict[str, str]] = await get_rule(session, guild_id, full_rule_key, default=None)

    if i18n_templates is None or not isinstance(i18n_templates, dict):
        logger.debug(f"No RuleConfig found for '{full_rule_key}' or not a dict for guild {guild_id}. Using default template.")
        return default_template

    # Use existing get_localized_text to extract the specific language string from the dict
    # Assuming primary language of bot/system is 'en' as fallback if specific lang_code not in dict
    # This could be made more sophisticated (e.g. guild's primary language from GuildConfig)
    primary_fallback_lang = "en" # Or fetch from GuildConfig if available

    # Try exact language_code (e.g., "en-US", "ru")
    template = i18n_templates.get(language_code)
    if template:
        return template

    # Try base language_code (e.g., "en" from "en-US")
    base_language_code = language_code.split('-')[0]
    if base_language_code != language_code:
        template = i18n_templates.get(base_language_code)
        if template:
            logger.debug(f"Using base language '{base_language_code}' for rule '{full_rule_key}' as '{language_code}' was not found.")
            return template

    # Try primary fallback language
    template = i18n_templates.get(primary_fallback_lang)
    if template:
        logger.debug(f"Using primary fallback language '{primary_fallback_lang}' for rule '{full_rule_key}'.")
        return template

    # If still not found, try to return any available language from the rule
    # This part is similar to the old get_localized_text internal fallback
    if i18n_templates:
        for lang_code_available, lang_text_available in i18n_templates.items():
            if lang_text_available: # Ensure there's actually text
                logger.debug(f"Using first available language '{lang_code_available}' from rule '{full_rule_key}' as a last resort.")
                return lang_text_available

    logger.warning(f"RuleConfig '{full_rule_key}' found for guild {guild_id}, but no suitable language template found for '{language_code}' or fallbacks. Using default template.")
    return default_template


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
            entities = await crud_instance.get_many_by_ids(session=session, ids=ids, guild_id=guild_id)
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

async def get_localized_master_message(
    session: AsyncSession,
    guild_id: Optional[int], # Changed to Optional[int]
    message_key: str,
    default_template: str,
    locale: str, # This should be the target locale string e.g. "en-US", "ru"
    **kwargs: Any
) -> str:
    """
    Retrieves and formats a localized message template for master commands.
    Tries to get the template from RuleConfig first, then falls back to default_template.
    Formats the template with provided kwargs.

    Args:
        session: The database session.
        guild_id: The ID of the guild.
        message_key: The specific key for the message (e.g., "player_view:title").
        default_template: The default template string to use if not found in RuleConfig or if RuleConfig access fails.
        locale: The target locale string (e.g., "en-US", "ru").
        **kwargs: Keyword arguments to format the template string.

    Returns:
        The formatted localized message string.
    """
    from .rules import get_rule # Local import to avoid circular dependency

    # Construct the RuleConfig key
    # Example: master_cmd_messages:player_view:title or master_cmd_feedback:player_not_found
    # The plan used "master_cmd_messages:<message_key>:<locale>" but it's better to store
    # all locales under one key like "master_cmd_messages:<message_key>" -> {"en": "T_en", "ru": "T_ru"}
    # and then use get_localized_text logic.
    # For this iteration, let's assume the key for get_rule is just the base message_key,
    # and get_rule itself returns an i18n dict if the rule is structured that way.
    # Or, a simpler approach for now: the rule itself contains the direct template string for a default/main language,
    # and we don't try to fetch language-specific versions from RuleConfig yet, just the base template.
    # Let's refine this to match get_localized_message_template structure.

    rule_config_key_prefix = "master_cmd_feedback:" # As used in existing get_localized_message_template
    full_rule_key = f"{rule_config_key_prefix}{message_key}"

    template_to_format = default_template # Start with the ultimate fallback

    if guild_id is not None: # Only try to fetch from RuleConfig if guild_id is provided
        try:
            # Attempt to get i18n templates dictionary from RuleConfig
            i18n_templates: Optional[Dict[str, str]] = await get_rule(
                session, guild_id, full_rule_key, default=None
            )

            if i18n_templates and isinstance(i18n_templates, dict):
                # We have a dictionary of locales and templates from RuleConfig
                # Use get_localized_text to pick the best one based on current locale and fallback logic
                selected_template = get_localized_text(i18n_templates, locale) # primary_fallback_lang is "en" by default in get_localized_text
                if selected_template: # If get_localized_text found a suitable template
                    template_to_format = selected_template
                else:
                    logger.debug(f"RuleConfig '{full_rule_key}' found for guild {guild_id}, but no template for locale '{locale}' or fallbacks. Using default template for key '{message_key}'.")
            elif i18n_templates: # It's not a dict, maybe a direct string? (legacy or misconfiguration)
                 if isinstance(i18n_templates, str):
                    template_to_format = i18n_templates # Use it directly
                    logger.debug(f"RuleConfig '{full_rule_key}' for guild {guild_id} is a direct string. Using it as template.")
                 else:
                    logger.warning(f"RuleConfig '{full_rule_key}' for guild {guild_id} is not a dict or string. Using default template for key '{message_key}'.")
            # If i18n_templates is None, we stick with default_template initialized above

        except Exception as e:
            logger.error(f"Error accessing RuleConfig for key '{full_rule_key}' in guild {guild_id}: {e}. Using default template for key '{message_key}'.", exc_info=True)
            # template_to_format remains default_template
    else:
        logger.debug(f"guild_id is None for get_localized_master_message key '{message_key}'. Using default template.")


    # Format the chosen template
    try:
        return template_to_format.format(**kwargs)
    except KeyError as e:
        logger.error(f"Missing key '{e}' in kwargs when formatting template for message key '{message_key}'. Template: '{template_to_format}' Kwargs: {kwargs}", exc_info=True)
        # Fallback to a message indicating the formatting error, including the original key
        return f"[Formatting Error: Missing key {e} for '{message_key}']"
    except Exception as e:
        logger.error(f"Unexpected error formatting template for message key '{message_key}'. Template: '{template_to_format}' Error: {e}", exc_info=True)
        return f"[Unexpected Formatting Error for '{message_key}']"
