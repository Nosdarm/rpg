import logging
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.crud.crud_player import player_crud
from src.core.crud.crud_location import location_crud
from src.core.rules import get_rule
from src.core.check_resolver import resolve_check, CheckResult
from src.core.game_events import log_event # Placeholder
from src.models import Player, Location
from src.models.actions import ActionEntity # For action_data structure if defined

logger = logging.getLogger(__name__)

# Placeholder for feedback formatting - eventually use Task 54
def _format_feedback(message_key: str, lang: str = "en", **kwargs) -> str:
    # In a real scenario, this would use a proper i18n library
    # For now, simple f-string or key return
    if message_key == "examine_success":
        return f"You examine {kwargs.get('target_name', 'it')}: {kwargs.get('description', 'You see nothing special.')}"
    if message_key == "examine_not_found":
        return f"You don't see any '{kwargs.get('target_name', 'that')}' here to examine."
    if message_key == "interact_not_found":
        return f"You don't see any '{kwargs.get('target_name', 'that')}' here to interact with."
    if message_key == "interact_no_rules":
        return f"You try to interact with {kwargs.get('target_name', 'it')}, but nothing interesting happens."
    if message_key == "interact_success_placeholder":
        return f"You interact with {kwargs.get('target_name', 'it')}. (Interaction effects TBD)"
    if message_key == "move_sublocation_success":
        return f"You move to {kwargs.get('target_name', 'the new area')}."
    if message_key == "move_sublocation_fail":
        return f"You can't move to '{kwargs.get('target_name', 'that area')}' from here."
    if message_key == "sublocation_not_found":
        return f"There is no sub-location called '{kwargs.get('target_name', 'that')}' here."
    if message_key == "player_not_found":
        return "Error: Player not found."
    if message_key == "location_not_found":
        return "Error: Current location not found."
    return message_key


def _find_target_in_location(location_data: Dict[str, Any], target_name: str) -> Optional[Dict[str, Any]]:
    """
    Helper to find an interactable/sublocation by name within a location's details.
    Assumes location_data might have a list under 'interactable_elements'.
    """
    if not location_data:
        return None
    interactables = location_data.get("interactable_elements", [])
    if not isinstance(interactables, list):
        logger.warning(f"Location.generated_details_json.interactable_elements is not a list.")
        return None

    for item in interactables:
        if isinstance(item, dict) and item.get("name", "").lower() == target_name.lower():
            return item
    return None


async def handle_intra_location_action(
    guild_id: int, session: AsyncSession, player_id: int, action_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handles player actions directed at objects or sub-locations WITHIN the current location.
    """
    feedback = {"message": "Unknown action or error.", "success": False}

    player = await player_crud.get(db=session, id=player_id, guild_id=guild_id)
    if not player:
        logger.error(f"Player {player_id} not found for guild {guild_id} in handle_intra_location_action.")
        return {"message": _format_feedback("player_not_found"), "success": False}

    if player.current_location_id is None:
        logger.error(f"Player {player_id} has no current_location_id.")
        return {"message": _format_feedback("location_not_found"), "success": False}

    location = await location_crud.get(db=session, id=player.current_location_id, guild_id=guild_id)
    if not location:
        logger.error(f"Location {player.current_location_id} not found for player {player_id}, guild {guild_id}.")
        return {"message": _format_feedback("location_not_found"), "success": False}

    intent = action_data.get("intent")
    # Assuming NLU provides entities like: [{"name": "target name", "type": "object/sublocation_target"}]
    target_entity_name = ""
    if action_data.get("entities") and isinstance(action_data["entities"], list) and action_data["entities"]:
        target_entity_name = action_data["entities"][0].get("name", "").strip()

    if not target_entity_name:
        logger.warning(f"No target entity name in action_data for player {player_id}, intent {intent}")
        # Generic feedback might be better handled by NLU/Action Processor if no target
        feedback = {"message": "What do you want to interact with?", "success": False}
        return feedback

    # Use generated_details_json for interactable elements for now
    location_details = location.generated_details_json or {}
    target_object_data = _find_target_in_location(location_details, target_entity_name)

    player_lang = player.selected_language or "en"

    # --- Handle EXAMINE intent ---
    if intent == "examine":
        if target_object_data and target_object_data.get("can_examine", True): # Default to examinable
            description = "You see nothing special."
            if target_object_data.get("description_i18n"):
                description = target_object_data["description_i18n"].get(player_lang, target_object_data["description_i18n"].get("en", description))

            feedback = {
                "message": _format_feedback("examine_success", player_lang, target_name=target_entity_name, description=description),
                "success": True
            }
            await log_event(
                session=session, guild_id=guild_id, event_type="player_examine",
                details_json={"player_id": player.id, "target": target_entity_name, "description": description, "location_id": location.id, "sublocation": player.current_sublocation_name},
                player_id=player.id, location_id=location.id
            )
        else:
            feedback = {"message": _format_feedback("examine_not_found", player_lang, target_name=target_entity_name), "success": False}

    # --- Handle INTERACT intent ---
    elif intent == "interact":
        if target_object_data and target_object_data.get("can_interact", True): # Default to interactable
            interaction_rules_key = target_object_data.get("interaction_rules_key")
            if interaction_rules_key:
                # TODO: Placeholder for RuleConfig based interaction
                # rule = await get_rule(session=session, guild_id=guild_id, key=f"interactions:{interaction_rules_key}")
                # if rule and rule.get("requires_check"):
                #     check_result: CheckResult = await resolve_check(...)
                #     if check_result.success:
                #         # Apply success consequences
                #     else:
                #         # Apply failure consequences
                logger.info(f"Placeholder for interaction with '{target_entity_name}' using rule key '{interaction_rules_key}'")
                feedback = {"message": _format_feedback("interact_success_placeholder", player_lang, target_name=target_entity_name), "success": True}
                await log_event(
                    session=session, guild_id=guild_id, event_type="player_interact",
                    details_json={"player_id": player.id, "target": target_entity_name, "outcome": "placeholder_success", "location_id": location.id, "sublocation": player.current_sublocation_name},
                    player_id=player.id, location_id=location.id
                )
            else:
                feedback = {"message": _format_feedback("interact_no_rules", player_lang, target_name=target_entity_name), "success": True} # Success is true, just nothing happens
        else:
            feedback = {"message": _format_feedback("interact_not_found", player_lang, target_name=target_entity_name), "success": False}

    # --- Handle MOVE_TO_SUBLOCATION intent ---
    # NLU should ideally differentiate "move <location_static_id>" (handled by movement_logic)
    # from "move to <sublocation_name>" or "enter <sublocation_name>" (handled here).
    # For now, we assume the intent 'move_to_sublocation' is correctly set by NLU for this case.
    elif intent == "move_to_sublocation":
        # Check if target_entity_name is a valid sublocation *within* the current location's details
        # This assumes sublocations are also defined in `location.generated_details_json.interactable_elements`
        # with type "sublocation"
        if target_object_data and target_object_data.get("type") == "sublocation":
            actual_sublocation_name = target_object_data.get("actual_sublocation_name", target_entity_name)
            player.current_sublocation_name = actual_sublocation_name
            await session.commit() # Persist change to player
            feedback = {"message": _format_feedback("move_sublocation_success", player_lang, target_name=actual_sublocation_name), "success": True}
            await log_event(
                session=session, guild_id=guild_id, event_type="player_move_sublocation",
                details_json={"player_id": player.id, "target_sublocation": actual_sublocation_name, "location_id": location.id},
                player_id=player.id, location_id=location.id
            )
        else:
            # Could also check against a predefined list of valid sublocations for the current location
            # if not using the `interactable_elements` structure for sublocations.
            feedback = {"message": _format_feedback("sublocation_not_found", player_lang, target_name=target_entity_name), "success": False}
            if target_object_data: # It was found, but wasn't a sublocation
                 feedback = {"message": f"'{target_entity_name}' is not a place you can move to within {location.name_i18n.get(player_lang, location.name_i18n.get('en')) if location.name_i18n else location.static_id}.", "success": False}


    else:
        logger.warning(f"Unknown intent '{intent}' in handle_intra_location_action for player {player_id}.")
        feedback = {"message": f"You are not sure how to '{intent}'.", "success": False}

    return feedback
