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
    # Removed "interact_success_placeholder"
    if message_key == "interact_check_success":
        return f"You attempt to interact with {kwargs.get('target_name', 'it')}... Success! ({kwargs.get('outcome', 'success')})"
    if message_key == "interact_check_failure":
        return f"You attempt to interact with {kwargs.get('target_name', 'it')}... Failure. ({kwargs.get('outcome', 'failure')})"
    if message_key == "interact_direct_success":
        return f"You interact with {kwargs.get('target_name', 'it')}. It seems to have worked."
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
            interaction_rules_key_short = target_object_data.get("interaction_rules_key")
            log_details: Dict[str, Any] = {
                "player_id": player.id,
                "target": target_entity_name,
                "location_id": location.id,
                "sublocation": player.current_sublocation_name,
                "interaction_rules_key": interaction_rules_key_short
            }

            if interaction_rules_key_short:
                rule_config_key = f"interactions:{interaction_rules_key_short}"
                interaction_rule = await get_rule(session=session, guild_id=guild_id, key=rule_config_key)

                if interaction_rule:
                    log_details["rule_found"] = True
                    log_details["rule_content"] = interaction_rule

                    if interaction_rule.get("requires_check", False):
                        log_details["check_required"] = True
                        check_type = interaction_rule.get("check_type", "ability") # Default check type
                        # For MVP, player's primary attribute for the check. Real system might be more complex.
                        actor_attribute_key = interaction_rule.get("actor_attribute_key", "strength")
                        # Simplified: get a base stat. Real system needs effective stats.
                        actor_attribute_value = getattr(player, actor_attribute_key, 10) # Default to 10 if no attr

                        actor_attributes = {
                            actor_attribute_key: {
                                "value": actor_attribute_value,
                                "modifiers": [] # Placeholder for detailed modifiers
                            }
                        }
                        # DC could be fixed in rule, or derived from target, or base + target mod
                        dc = interaction_rule.get("base_dc", 12)

                        # Modifiers from context (e.g. from target_object_data or rule itself)
                        # Example: rule might specify bonus/penalty based on conditions
                        contextual_bonus = interaction_rule.get("contextual_bonus", 0)
                        contextual_penalty = interaction_rule.get("contextual_penalty", 0)

                        # For resolve_check, we'd pass these as part of actor_attributes or bonus_roll_dice_modifier
                        # Simplified for now: directly adjust dc or roll for MVP
                        # Let's assume bonus_roll_dice_modifier in resolve_check can take this simple form
                        # For now, let's use a generic bonus/penalty on the roll.
                        # bonus_roll_dice_modifier = contextual_bonus - contextual_penalty

                        logger.info(f"Player {player.id} interacting with {target_entity_name}, requires check. Type: {check_type}, Attr: {actor_attribute_key}={actor_attribute_value}, DC: {dc}")

                        check_result: Optional[CheckResult] = None
                        try:
                             check_result = await resolve_check(
                                db=session, # Added db param
                                guild_id=guild_id,
                                check_type=check_type,
                                dc=dc,
                                actor_id=player.id,
                                actor_type="player",
                                actor_attributes=actor_attributes,
                                # target_id and target_type could be relevant if DC depends on target
                                # target_id=target_object_data.get("id"), # If target has an ID
                                # target_type=target_object_data.get("type"),
                                bonus_roll_dice_modifier= contextual_bonus - contextual_penalty
                            )
                        except Exception as e_resolve:
                            logger.error(f"Error during resolve_check for interaction: {e_resolve}", exc_info=True)
                            log_details["check_error"] = str(e_resolve)
                            feedback = {"message": f"An error occurred while trying to interact with {target_entity_name}.", "success": False}


                        if check_result:
                            log_details["check_result"] = check_result.model_dump(mode='json')
                            consequences_key = ""
                            if check_result.outcome in ["SUCCESS", "CRITICAL_SUCCESS"]:
                                consequences_key = interaction_rule.get("success_consequences_key", "generic_interaction_success")
                                feedback_msg_key = interaction_rule.get("feedback_success", "interact_check_success")
                                feedback = {
                                    "message": _format_feedback(feedback_msg_key, player_lang, target_name=target_entity_name, outcome=check_result.outcome.lower()),
                                    "success": True
                                }
                            else: # FAILURE, CRITICAL_FAILURE
                                consequences_key = interaction_rule.get("failure_consequences_key", "generic_interaction_failure")
                                feedback_msg_key = interaction_rule.get("feedback_failure", "interact_check_failure")
                                feedback = {
                                    "message": _format_feedback(feedback_msg_key, player_lang, target_name=target_entity_name, outcome=check_result.outcome.lower()),
                                    "success": False # Interaction failed duef to check
                                }
                            log_details["applied_consequences_key"] = consequences_key
                            logger.info(f"Interaction check outcome: {check_result.outcome}. Consequences to apply (placeholder): {consequences_key}")
                            # TODO: Implement actual application of consequences based on consequences_key
                        else: # check_result was None due to error in resolve_check
                             feedback = {"message": f"Something went wrong trying to interact with {target_entity_name}.", "success": False}


                    else: # No check required
                        log_details["check_required"] = False
                        direct_consequences_key = interaction_rule.get("direct_consequences_key", "generic_direct_interaction")
                        feedback_msg_key = interaction_rule.get("feedback_direct", "interact_direct_success")
                        log_details["applied_consequences_key"] = direct_consequences_key
                        logger.info(f"Interaction with '{target_entity_name}' - no check required. Consequences (placeholder): {direct_consequences_key}")
                        feedback = {
                            "message": _format_feedback(feedback_msg_key, player_lang, target_name=target_entity_name),
                            "success": True
                        }
                        # TODO: Implement actual application of direct consequences

                    await log_event(session=session, guild_id=guild_id, event_type="player_interact", details_json=log_details, player_id=player.id, location_id=location.id)

                else: # Rule not found in RuleConfig
                    log_details["rule_found"] = False
                    feedback = {"message": _format_feedback("interact_no_rules", player_lang, target_name=target_entity_name), "success": True}
                    # Log that rule was not found, but interaction still "occurred" (harmlessly)
                    await log_event(session=session, guild_id=guild_id, event_type="player_interact", details_json=log_details, player_id=player.id, location_id=location.id)

            else: # No interaction_rules_key defined for the object
                log_details["interaction_rules_key"] = None
                feedback = {"message": _format_feedback("interact_no_rules", player_lang, target_name=target_entity_name), "success": True}
                await log_event(session=session, guild_id=guild_id, event_type="player_interact", details_json=log_details, player_id=player.id, location_id=location.id)
        else: # Target object not found or not interactable
            feedback = {"message": _format_feedback("interact_not_found", player_lang, target_name=target_entity_name), "success": False}
            # No log_event here as the interaction didn't meaningfully occur with a target

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
