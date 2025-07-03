from typing import Union, Optional, Any, Dict
import logging

from src.models import Player, GeneratedNpc

logger = logging.getLogger(__name__)

# --- HP Utils ---

def get_entity_hp(entity: Union[Player, GeneratedNpc]) -> Optional[int]:
    """Gets the current HP of an entity."""
    if isinstance(entity, Player):
        return entity.current_hp
    elif isinstance(entity, GeneratedNpc):
        try:
            # Ensure properties_json and stats exist and hp is an int
            props = getattr(entity, 'properties_json', None)
            if props and 'stats' in props and 'hp' in props['stats']:
                return int(props["stats"]["hp"])
            else:
                logger.warning(f"HP not found or invalid in properties_json for NPC {entity.id}: {props}")
                return None
        except (ValueError, TypeError):
            logger.warning(f"Could not parse HP for NPC {entity.id} from properties_json: {getattr(entity, 'properties_json', None)}")
            return None
    return None

def set_entity_hp(entity: Union[Player, GeneratedNpc], new_hp: int) -> bool:
    """Sets the current HP of an entity."""
    if not isinstance(new_hp, int):
        logger.error(f"Invalid new_hp value '{new_hp}' for entity {entity.id}. Must be an integer.")
        return False

    if isinstance(entity, Player):
        entity.current_hp = new_hp
        return True
    elif isinstance(entity, GeneratedNpc):
        if not hasattr(entity, 'properties_json') or entity.properties_json is None:
            entity.properties_json = {"stats": {}}
        elif "stats" not in entity.properties_json or entity.properties_json["stats"] is None: # Check if 'stats' is None
            entity.properties_json["stats"] = {}

        # Ensure 'stats' is a dictionary
        if not isinstance(entity.properties_json.get("stats"), dict):
            entity.properties_json["stats"] = {}

        entity.properties_json["stats"]["hp"] = new_hp
        return True
    return False

def change_entity_hp(entity: Union[Player, GeneratedNpc], amount: int) -> bool:
    """Changes the current HP of an entity by a given amount (can be negative)."""
    if not isinstance(amount, int):
        logger.error(f"Invalid amount '{amount}' for HP change. Must be an integer.")
        return False

    current_hp = get_entity_hp(entity)
    if current_hp is None:
        logger.error(f"Cannot change HP for entity {entity.id if hasattr(entity, 'id') else 'Unknown Entity'}: current HP is None or could not be determined.")
        return False

    return set_entity_hp(entity, current_hp + amount)

# --- Generic Stat/Resource Utils ---

def get_entity_stat(entity: Union[Player, GeneratedNpc], stat_name: str) -> Optional[Any]:
    """
    Gets a specific stat/resource value for an entity.
    For Player, current_hp is handled. Other stats are placeholders.
    For NPC, expects it in properties_json['stats'].
    """
    if not isinstance(stat_name, str) or not stat_name:
        logger.error("stat_name must be a non-empty string.")
        return None

    if isinstance(entity, Player):
        if stat_name.lower() in ["hp", "current_hp"]:
             return entity.current_hp
        # Placeholder for other player stats (e.g., mana, strength)
        # Example: if hasattr(entity, 'stats_json') and entity.stats_json and stat_name in entity.stats_json:
        # return entity.stats_json[stat_name]
        logger.debug(f"Stat '{stat_name}' lookup for Player {entity.id} is a placeholder or needs specific handling.")
        return None
    elif isinstance(entity, GeneratedNpc):
        try:
            props = getattr(entity, 'properties_json', None)
            if props and 'stats' in props and isinstance(props['stats'], dict) and stat_name in props['stats']:
                return props["stats"][stat_name]
            else:
                logger.debug(f"Stat '{stat_name}' not found in properties_json for NPC {entity.id}: {props}")
                return None
        except AttributeError: # Should be caught by getattr
            logger.warning(f"NPC {entity.id} properties_json is missing, cannot get stat '{stat_name}'.")
            return None
    return None

def set_entity_stat(entity: Union[Player, GeneratedNpc], stat_name: str, value: Any) -> bool:
    """
    Sets a specific stat/resource value for an entity.
    For Player, current_hp is handled. Other stats are placeholders.
    For NPC, sets it in properties_json['stats'].
    """
    if not isinstance(stat_name, str) or not stat_name:
        logger.error("stat_name must be a non-empty string.")
        return False

    if isinstance(entity, Player):
        if stat_name.lower() in ["hp", "current_hp"]:
            if not isinstance(value, int):
                logger.error(f"Invalid value '{value}' for Player {entity.id} HP. Must be an integer.")
                return False
            entity.current_hp = value
            return True
        # Placeholder for other player stats
        # Example: if hasattr(entity, 'stats_json') and entity.stats_json is not None:
        # entity.stats_json[stat_name] = value; return True
        logger.warning(f"Cannot set stat '{stat_name}' for Player {entity.id}. Player model might need a dedicated stats field or specific handling.")
        return False
    elif isinstance(entity, GeneratedNpc):
        if not hasattr(entity, 'properties_json') or entity.properties_json is None:
            entity.properties_json = {"stats": {}}
        elif "stats" not in entity.properties_json or entity.properties_json["stats"] is None: # Check if 'stats' is None
            entity.properties_json["stats"] = {}

        # Ensure 'stats' is a dictionary
        if not isinstance(entity.properties_json.get("stats"), dict):
            entity.properties_json["stats"] = {}

        entity.properties_json["stats"][stat_name] = value
        return True
    return False

def change_entity_stat(entity: Union[Player, GeneratedNpc], stat_name: str, amount: Union[int, float]) -> bool:
    """
    Changes a numerical stat/resource for an entity by a given amount.
    Returns False if the stat is not found, not numerical, or amount is not numerical.
    """
    if not isinstance(stat_name, str) or not stat_name:
        logger.error("stat_name must be a non-empty string.")
        return False
    if not isinstance(amount, (int, float)):
        logger.error(f"Invalid amount '{amount}' for stat change. Must be numerical.")
        return False

    current_value = get_entity_stat(entity, stat_name)
    if not isinstance(current_value, (int, float)):
        logger.error(f"Cannot change stat '{stat_name}' for entity {entity.id if hasattr(entity, 'id') else 'Unknown Entity'}: current value '{current_value}' is not numerical or not found.")
        return False

    return set_entity_stat(entity, stat_name, current_value + amount)

# Ensure __all__ is defined for explicit exports if this becomes a larger module
# __all__ = ["get_entity_hp", "set_entity_hp", "change_entity_hp", "get_entity_stat", "set_entity_stat", "change_entity_stat"]
