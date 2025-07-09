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

async def load_rules_config_for_guild(session: AsyncSession, guild_id: int) -> Dict[str, Any]:
    """
    Loads all RuleConfig entries for a specific guild from the DB and updates the cache.
    This function is intended to be called when a guild's rules need to be refreshed in the cache.
    """
    logger.debug(f"Loading rules from DB for guild_id: {guild_id}")
    statement = select(RuleConfig).where(RuleConfig.guild_id == guild_id)
    result = await session.execute(statement) # Execute the statement
    # For SQLAlchemy 2.x with async, result.scalars() is typically synchronous
    # and returns an object with a synchronous .all() method.
    rules_from_db = result.scalars().all()

    guild_rules: Dict[str, Any] = {}
    for rule_model_instance in rules_from_db: # Renamed to avoid confusion if rule is a var name
        guild_rules[rule_model_instance.key] = rule_model_instance.value_json

    _rules_cache[guild_id] = guild_rules
    logger.info(f"Loaded and cached {len(guild_rules)} rules for guild_id: {guild_id}")
    return guild_rules

async def get_rule(session: AsyncSession, guild_id: int, key: str, default: Optional[Any] = None) -> Any:
    """
    Retrieves a specific rule value for a guild from the cache.
    If the guild is not in the cache, it loads all rules for that guild first.
    If the key is not found after loading, returns the provided default value.
    """
    if guild_id not in _rules_cache:
        logger.info(f"Guild {guild_id} not in rule cache. Loading from DB for key '{key}'.")
        await load_rules_config_for_guild(session, guild_id)

    guild_cache = _rules_cache.get(guild_id, {})
    rule_value = guild_cache.get(key)

    if rule_value is None:
        logger.warning(f"Rule key '{key}' not found for guild_id {guild_id} in cache. Returning default: {default}")
        return default

    return rule_value

@transactional
async def update_rule_config(session: AsyncSession, guild_id: int, key: str, value: Any) -> RuleConfig:
    """
    Updates or creates a rule in the DB for the specified guild.
    After successful saving, it refreshes the cache for this guild.
    """
    logger.info(f"Attempting to update rule for guild_id: {guild_id}, key: '{key}'")

    statement = select(RuleConfig).where(RuleConfig.guild_id == guild_id, RuleConfig.key == key)
    result = await session.execute(statement)
    existing_rule = result.scalar_one_or_none()

    if existing_rule:
        logger.debug(f"Found existing rule ID {existing_rule.id}. Updating.")
        updated_rule = await update_entity(session, entity=existing_rule, data={"value_json": value})
    else:
        logger.debug(f"No existing rule found for key '{key}'. Creating new rule.")
        updated_rule = await create_entity(session, RuleConfig, {"key": key, "value_json": value}, guild_id=guild_id)

    await load_rules_config_for_guild(session, guild_id)
    logger.info(f"Rule for guild_id: {guild_id}, key: '{key}' updated successfully. Cache refreshed.")

    return updated_rule

async def get_all_rules_for_guild(session: AsyncSession, guild_id: int) -> Dict[str, Any]:
    """
    Retrieves all rules for a guild, utilizing the cache.
    If not in cache, loads from DB.
    """
    if guild_id not in _rules_cache:
        logger.info(f"Guild {guild_id} rules not in cache. Loading for 'get_all_rules_for_guild'.")
        await load_rules_config_for_guild(session, guild_id)
    return _rules_cache.get(guild_id, {})

logger.info("RuleConfig specific utilities (load, get, update, cache) defined in core.rules.")
