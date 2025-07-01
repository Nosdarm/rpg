import re
import datetime
import logging
from typing import Optional, List, Dict, Any, Tuple, Union # Added Union

from ..models.actions import ParsedAction, ActionEntity

logger = logging.getLogger(__name__)

# Simple pattern matching for MVP
# More sophisticated patterns or a proper NLU library would be needed for robust parsing.
# Patterns: (regex_pattern, intent_name, entity_groups_mapping)
# entity_groups_mapping: dict where key is entity_type and value is group name or index in regex match

# Order matters: more specific patterns should come before general ones.
ACTION_PATTERNS: List[Tuple[re.Pattern, str, Dict[str, Union[str, int]]]] = [
    # Movement: "go north", "move west", "n", "s", "e", "w"
    (re.compile(r"^(?:go|move|walk)\s+(north|south|east|west|up|down)$", re.IGNORECASE), "move", {"direction": 1}),
    (re.compile(r"^(n|north|s|south|e|east|w|west|u|up|d|down)$", re.IGNORECASE), "move", {"direction": 1}),

    # Look: "look", "look around", "examine"
    (re.compile(r"^(look|l|examine|exa)$", re.IGNORECASE), "look_around", {}),
    # Look at target: "look at goblin", "examine the sword" -> now "examine" intent for intra-location
    (re.compile(r"^(?:look|l|examine|exa)\s+(?:at|on)?\s*(?:the\s+)?(.+)$", re.IGNORECASE), "examine", {"name": 1}),

    # Interact with target: "interact with lever", "use the terminal"
    (re.compile(r"^(?:interact|use|activate|touch|press|pull)\s+(?:with\s+)?(?:the\s+)?(.+)$", re.IGNORECASE), "interact", {"name": 1}),

    # Go to sublocation: "go to the kitchen", "enter the library" (distinct from inter-location move)
    (re.compile(r"^(?:go\s+to|enter|move\s+to)\s+(?:the\s+)?(.+)$", re.IGNORECASE), "go_to", {"name": 1}),

    # Get/Take item: "get sword", "take the potion"
    (re.compile(r"^(?:get|take)\s+(?:the\s+)?(.+)$", re.IGNORECASE), "get_item", {"item_name": 1}),

    # Drop item: "drop shield", "drop the key"
    (re.compile(r"^(?:drop|discard)\s+(?:the\s+)?(.+)$", re.IGNORECASE), "drop_item", {"item_name": 1}),

    # Attack target: "attack goblin", "hit the orc"
    (re.compile(r"^(?:attack|hit|fight)\s+(?:the\s+)?(.+)$", re.IGNORECASE), "attack_target", {"target_name": 1}),

    # Talk to NPC: "talk to elara", "speak with the guard"
    (re.compile(r"^(?:talk|speak)(?:\s+to|\s+with)?\s+(?:the\s+)?(.+)$", re.IGNORECASE), "talk_to_npc", {"npc_name": 1}),

    # Inventory: "inventory", "inv", "i"
    (re.compile(r"^(inventory|inv|i)$", re.IGNORECASE), "view_inventory", {}),

    # Help: "help", "?"
    (re.compile(r"^(help|\?)$", re.IGNORECASE), "get_help", {}),

    # Say: "say hello world", "' hello world"
    (re.compile(r"^(?:say|shout|whisper|')\s*(.+)$", re.IGNORECASE), "say_text", {"text_to_say": 1}),
]

# Placeholder for guild-specific entity dictionaries or rule-based entity extraction
# For now, this service doesn't use guild_id for dynamic entity loading.
# async def load_guild_entities(guild_id: int) -> Dict[str, List[str]]:
#     # In future, this could load known NPCs, items, locations for this guild
#     # from RuleConfig or dedicated tables to aid NLU.
#     return {"npcs": ["elara", "goblin"], "items": ["sword", "potion"]}


async def parse_player_input(
    raw_text: str,
    guild_id: int,
    player_id: int # Discord ID of the player
) -> Optional[ParsedAction]:
    """
    Parses raw player input text into a structured ParsedAction using simple regex patterns.
    Returns None if no known pattern is matched.
    """
    cleaned_text = raw_text.strip()
    # if not cleaned_text: # Removed this block to allow unknown_intent for empty strings
    #     return None

    # guild_entities = await load_guild_entities(guild_id) # For future use

    # Only attempt to match patterns if cleaned_text is not empty
    if cleaned_text:
        for pattern, intent, entity_mapping in ACTION_PATTERNS:
            match = pattern.match(cleaned_text)
            if match:
                entities_extracted: List[ActionEntity] = []
                for entity_type, group_ref in entity_mapping.items():
                    try:
                        value = match.group(group_ref)
                        if value: # Ensure the group captured something
                            entities_extracted.append(ActionEntity(type=entity_type, value=value.strip()))
                    except IndexError:
                        logger.warning(f"Regex pattern group '{group_ref}' not found for intent '{intent}' with pattern '{pattern.pattern}'. Check pattern definition.")
                    except Exception as e:
                        logger.error(f"Error extracting entity '{entity_type}' with group '{group_ref}' for intent '{intent}': {e}")

                action = ParsedAction(
                    raw_text=raw_text,
                    intent=intent,
                    entities=entities_extracted,
                    parser_confidence=1.0, # Simple regex match = full confidence for this MVP
                    guild_id=guild_id,
                    player_id=player_id,
                    timestamp=datetime.datetime.now(datetime.timezone.utc) # Use timezone-aware UTC
                )
                logger.info(f"Parsed action for guild {guild_id}, player {player_id}: Intent='{intent}', Entities='{entities_extracted}' from text='{raw_text}'")
                return action

    # If no pattern matched or cleaned_text was empty
    logger.info(f"No specific intent matched for input: '{raw_text}' for guild {guild_id}, player {player_id}. Defaulting to 'unknown_intent'.")
    # Optionally, return a default "unknown" action instead of None if all inputs should be logged as actions.
    unknown_action = ParsedAction(
        raw_text=raw_text,
        intent="unknown_intent",
        entities=[],
        parser_confidence=0.0,
        guild_id=guild_id,
        player_id=player_id,
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    return unknown_action

# Example of how this might be tested (can be run locally)
# async def main():
#     test_inputs = [
#         "go north", "n", "look", "l", "look at the king", "examine goblin",
#         "get sword", "take potion", "drop the shield",
#         "attack orc", "hit dragon", "talk to elara", "speak with merchant",
#         "inventory", "inv", "i", "help", "?",
#         "say Hello there!", "'General Kenobi!",
#         "do something completely random"
#     ]
#     for text_input in test_inputs:
#         parsed = await parse_player_input(text_input, guild_id=123, player_id=456)
#         if parsed:
#             print(f"Input: '{text_input}' -> Intent: '{parsed.intent}', Entities: {parsed.entities}")
#         else:
#             print(f"Input: '{text_input}' -> No action parsed (or returned None)")

# if __name__ == "__main__":
#     import asyncio
#     asyncio.run(main())
logger.info("NLU Service (simple regex parser) defined in src/core/nlu_service.py")
