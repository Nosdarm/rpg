import logging
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update as sqlalchemy_update, delete as sqlalchemy_delete

from ..models.rule_config import RuleConfig
# Corrected import path for CRUDBase and generic CRUD functions
from .crud_base_definitions import CRUDBase, create_entity, get_entity_by_id, update_entity
from .database import transactional # For transactional operations

logger = logging.getLogger(__name__)

# In-memory cache for rules, structured as {guild_id: {key: value_json}}
_rules_cache: Dict[int, Dict[str, Any]] = {}

# CRUD instance for RuleConfig
rule_config_crud = CRUDBase(RuleConfig)

async def load_rules_config_for_guild(session: AsyncSession, guild_id: int) -> Dict[str, Any]: # Renamed db to session
    """
    Loads all RuleConfig entries for a specific guild from the DB and updates the cache.
    This function is intended to be called when a guild's rules need to be refreshed in the cache.
    """
    logger.debug(f"Loading rules from DB for guild_id: {guild_id}")
    statement = select(RuleConfig).where(RuleConfig.guild_id == guild_id)
    result = await session.execute(statement) # Renamed db to session
    rules_from_db = result.scalars().all() # Fixed: .all() is not async here for scalars

    guild_rules: Dict[str, Any] = {}
    for rule in rules_from_db:
        guild_rules[rule.key] = rule.value_json

    _rules_cache[guild_id] = guild_rules
    logger.info(f"Loaded and cached {len(guild_rules)} rules for guild_id: {guild_id}")
    return guild_rules

async def get_rule(session: AsyncSession, guild_id: int, key: str, default: Optional[Any] = None) -> Any: # Renamed db to session
    """
    Retrieves a specific rule value for a guild from the cache.
    If the guild is not in the cache, it loads all rules for that guild first.
    If the key is not found after loading, returns the provided default value.

    :param db: AsyncSession for database operations if cache needs loading.
    :param guild_id: The ID of the guild.
    :param key: The key of the rule to retrieve.
    :param default: The default value to return if the key is not found.
    :return: The rule value or the default.
    """
    if guild_id not in _rules_cache:
        logger.info(f"Guild {guild_id} not in rule cache. Loading from DB.")
        await load_rules_config_for_guild(session, guild_id) # Renamed db to session

    guild_cache = _rules_cache.get(guild_id, {})
    rule_value = guild_cache.get(key)

    if rule_value is None:
        logger.warning(f"Rule key '{key}' not found for guild_id {guild_id}. Returning default: {default}")
        return default

    return rule_value

@transactional
async def update_rule_config(session: AsyncSession, guild_id: int, key: str, value: Any) -> RuleConfig: # Renamed db to session
    """
    Updates or creates a rule in the DB for the specified guild.
    After successful saving, it refreshes the cache for this guild.

    :param db: The database session (provided by @transactional).
    :param guild_id: The ID of the guild.
    :param key: The key of the rule to update/create.
    :param value: The new value for the rule (should be JSON serializable).
    :return: The updated or created RuleConfig object.
    """
    logger.info(f"Attempting to update rule for guild_id: {guild_id}, key: '{key}'")

    # Check if rule exists
    statement = select(RuleConfig).where(RuleConfig.guild_id == guild_id, RuleConfig.key == key)
    result = await session.execute(statement) # Renamed db to session
    existing_rule = result.scalar_one_or_none() # Removed await

    if existing_rule:
        logger.debug(f"Found existing rule ID {existing_rule.id}. Updating.")
        updated_rule = await update_entity(session, entity=existing_rule, data={"value_json": value}) # Renamed db to session
        # update_entity already does flush and refresh
    else:
        logger.debug(f"No existing rule found for key '{key}'. Creating new rule.")
        updated_rule = await create_entity(session, RuleConfig, {"key": key, "value_json": value}, guild_id=guild_id) # Renamed db to session
        # create_entity already does flush and refresh

    # Refresh cache for the guild
    await load_rules_config_for_guild(session, guild_id) # Renamed db to session
    logger.info(f"Rule for guild_id: {guild_id}, key: '{key}' updated successfully. Cache refreshed.")

    return updated_rule

async def get_all_rules_for_guild(session: AsyncSession, guild_id: int) -> Dict[str, Any]: # Renamed db to session
    """
    Retrieves all rules for a guild, utilizing the cache.
    If not in cache, loads from DB. This is an alias for ensuring cache is populated
    and then returning the cached dict.
    """
    if guild_id not in _rules_cache:
        logger.info(f"Guild {guild_id} rules not in cache. Loading for 'get_all_rules_for_guild'.")
        await load_rules_config_for_guild(session, guild_id) # Renamed db to session
    return _rules_cache.get(guild_id, {})

# Example of how this might be used in bot command or event handler:
# async def some_bot_function(guild_id: int):
#     # db_session would be obtained via dependency injection or similar
#     async for db_session in get_db_session(): # Assuming get_db_session is available
#         # Set a rule
#         await update_rule_config(db_session, guild_id, "max_players", 5)
#
#         # Get a rule
#         max_players = await get_rule(db_session, guild_id, "max_players", default=10)
#         print(f"Max players for guild {guild_id}: {max_players}")
#
#         # Get all rules for the guild
#         all_guild_rules = await get_all_rules_for_guild(db_session, guild_id)
#         print(f"All rules for guild {guild_id}: {all_guild_rules}")

logger.info("RuleConfig specific utilities (load, get, update, cache) defined in core.rules.")
