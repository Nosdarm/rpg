import logging
from typing import Any, Dict, Optional, Tuple, List # Added List

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.crud.crud_player import player_crud
from backend.core.crud.crud_location import location_crud
from backend.core.rules import get_rule
from backend.core.check_resolver import resolve_check, CheckResult
from backend.core.game_events import log_event # Placeholder
from backend.models import Player, Location
from backend.models.actions import ActionEntity # For action_data structure if defined
from backend.models.enums import EventType # Added EventType import

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


def _find_target_in_location(location_data: Optional[Dict[str, Any]], target_name: str) -> Optional[Dict[str, Any]]:
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

    player = await player_crud.get(session=session, id=player_id, guild_id=guild_id)
    if not player:
        logger.error(f"Player {player_id} not found for guild {guild_id} in handle_intra_location_action.")
        return {"message": _format_feedback("player_not_found"), "success": False}

    if player.current_location_id is None:
        logger.error(f"Player {player_id} has no current_location_id.")
        return {"message": _format_feedback("location_not_found"), "success": False}

    location = await location_crud.get(session=session, id=player.current_location_id, guild_id=guild_id)
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
                interaction_rule = await get_rule(session=session, guild_id=guild_id, key=rule_config_key) # FIX: db to session

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
                            # Prepare check_context
                            current_check_context = {
                                "actor_attributes": actor_attributes, # Pass original actor_attributes here
                                "bonus_roll_modifier": contextual_bonus - contextual_penalty # Pass modifier here
                                # resolve_check can look for "bonus_roll_modifier" or similar from context
                                # or specific rules for this check_type can define how to use actor_attributes
                            }
                            if target_object_data and target_object_data.get("id"):
                                current_check_context["target_object_id_for_interaction"] = target_object_data.get("id")
                            if target_object_data and target_object_data.get("type"):
                                current_check_context["target_object_type_for_interaction"] = target_object_data.get("type")

                            from backend.models.enums import RelationshipEntityType # Ensure enum is available for type hint consistency
                            check_result = await resolve_check(
                                session=session,
                                guild_id=guild_id,
                                check_type=check_type,
                                actor_entity_id=player.id,
                                actor_entity_type=RelationshipEntityType.PLAYER, # Use Enum member
                                difficulty_dc=dc,
                                # target_entity_id and target_entity_type are for actual game entities,
                                # not necessarily the 'target_object_data' from location details.
                                # If the interaction target IS an entity, pass its ID/type here.
                                # For now, assuming interaction target is not a separate Player/NPC entity unless specified.
                                check_context=current_check_context
                            )
                        except Exception as e_resolve:
                            logger.error(f"Error during resolve_check for interaction: {e_resolve}", exc_info=True)
                            log_details["check_error"] = str(e_resolve)
                            feedback = {"message": f"An error occurred while trying to interact with {target_entity_name}.", "success": False}


                        if check_result:
                            log_details["check_result"] = check_result.model_dump(mode='json')
                            consequences_key = ""
                            # Accessing status from CheckOutcome object
                            if check_result.outcome.status in ["success", "critical_success"]: # status is already a string
                                consequences_key = interaction_rule.get("success_consequences_key", "generic_interaction_success")
                                feedback_msg_key = interaction_rule.get("feedback_success", "interact_check_success")
                                feedback = {
                                    "message": _format_feedback(feedback_msg_key, player_lang, target_name=target_entity_name, outcome=check_result.outcome.status.lower()), # status is str
                                    "success": True
                                }
                            else: # FAILURE, CRITICAL_FAILURE
                                consequences_key = interaction_rule.get("failure_consequences_key", "generic_interaction_failure")
                                feedback_msg_key = interaction_rule.get("feedback_failure", "interact_check_failure")
                                feedback = {
                                    "message": _format_feedback(feedback_msg_key, player_lang, target_name=target_entity_name, outcome=check_result.outcome.status.lower()), # status is str
                                    "success": False # Interaction failed duef to check
                                }
                            log_details["applied_consequences_key"] = consequences_key
                            logger.info(f"Interaction check outcome: {check_result.outcome.status}. Consequences key: {consequences_key}")
                            if consequences_key:
                                consequence_feedback_msgs = await _apply_consequences(session, guild_id, player, location, target_object_data, consequences_key)
                                if consequence_feedback_msgs:
                                    feedback["message"] += "\n" + "\n".join(consequence_feedback_msgs)
                            # TODO: Implement actual application of consequences based on consequences_key (This line is now addressed by calling _apply_consequences)
                        else: # check_result was None due to error in resolve_check
                             feedback = {"message": f"Something went wrong trying to interact with {target_entity_name}.", "success": False}


                    else: # No check required
                        log_details["check_required"] = False
                        direct_consequences_key = interaction_rule.get("direct_consequences_key", "generic_direct_interaction")
                        feedback_msg_key = interaction_rule.get("feedback_direct", "interact_direct_success")
                        log_details["applied_consequences_key"] = direct_consequences_key
                        logger.info(f"Interaction with '{target_entity_name}' - no check required. Consequences key: {direct_consequences_key}")
                        feedback = {
                            "message": _format_feedback(feedback_msg_key, player_lang, target_name=target_entity_name),
                            "success": True
                        }
                        if direct_consequences_key:
                            consequence_feedback_msgs = await _apply_consequences(session, guild_id, player, location, target_object_data, direct_consequences_key)
                            if consequence_feedback_msgs:
                                feedback["message"] += "\n" + "\n".join(consequence_feedback_msgs)
                        # TODO: Implement actual application of direct consequences (This line is now addressed by calling _apply_consequences)

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


async def _apply_consequences(
    session: AsyncSession,
    guild_id: int,
    player: Player,
    location: Location, # Current location model
    target_object_data: Optional[Dict[str, Any]], # The specific interactable from location_details
    consequences_key: str
) -> List[str]: # Returns a list of feedback messages from applied consequences
    """
    Applies a list of consequences based on a key fetched from RuleConfig.
    """
    from backend.core.entity_stats_utils import change_entity_stat # Local import
    from backend.core.ability_system import apply_status as apply_status_effect # Local import to avoid name clash

    feedback_messages: List[str] = []
    if not consequences_key:
        logger.warning(f"Player {player.id} interaction: _apply_consequences called with empty consequences_key.")
        return feedback_messages

    rule_config_full_key = f"consequences:{consequences_key}"
    consequence_rules = await get_rule(session, guild_id, rule_config_full_key)

    if not consequence_rules or not isinstance(consequence_rules, list):
        logger.warning(f"Player {player.id} interaction: No consequence rules found or not a list for key '{rule_config_full_key}'.")
        return feedback_messages

    logger.info(f"Player {player.id} applying consequences for key '{consequences_key}': {consequence_rules}")
    player_lang = player.selected_language or "en"

    # additional_log_details_for_effects is passed from handle_intra_location_action
    # and might contain player_id, location_id etc. that were part of the main action log.
    # We'll merge them into details_json for consequence effect logs.
    base_effect_log_details = {
        "player_id": player.id, # Ensure player_id is present
        "location_id": location.id, # Ensure location_id is present
        # **additional_log_details_for_effects # This was passed to _apply_consequences, but we might not need it if player/location are explicit
    }


    for idx, effect_rule in enumerate(consequence_rules):
        effect_type = effect_rule.get("type")

        # Prepare details for logging this specific effect
        current_effect_log_details = {
            **base_effect_log_details,
            "rule_key": rule_config_full_key,
            "effect_index": idx,
            "effect_rule_content": effect_rule, # Log the rule itself
        }

        try:
            effect_processed_or_known_error = False # Flag to control generic "applied" log

            if effect_type == "update_location_state":
                target_name = effect_rule.get("target_object_name")
                property_to_update = effect_rule.get("property_name")
                new_value = effect_rule.get("new_value")
                if location.generated_details_json and target_name and property_to_update is not None:
                    interactables = location.generated_details_json.get("interactable_elements", [])
                    obj_found = False
                    for item in interactables:
                        if isinstance(item, dict) and item.get("name", "").lower() == target_name.lower():
                            item[property_to_update] = new_value
                            obj_found = True
                            logger.info(f"Updated location state: '{target_name}.{property_to_update}' to '{new_value}' in loc {location.id}.")
                            location.generated_details_json = dict(location.generated_details_json)
                            session.add(location)
                            break
                    if not obj_found: logger.warning(f"update_location_state: Target '{target_name}' not found in loc {location.id}.")
                    current_effect_log_details["outcome_details"] = {"updated_object": target_name, "property": property_to_update, "new_value": new_value}
                else:
                    logger.warning(f"update_location_state: Missing params for loc {location.id}.")
                effect_processed_or_known_error = True

            elif effect_type == "change_player_stat":
                stat_name = effect_rule.get("stat_name")
                change_amount = effect_rule.get("change_amount")
                if stat_name and isinstance(change_amount, int):
                    change_entity_stat(player, stat_name, change_amount)
                    logger.info(f"Changed player {player.id} stat '{stat_name}' by {change_amount}.")
                    # feedback_messages.append(f"You feel your {stat_name} change.") # This type of feedback is often better handled by the stat change util itself or a global feedback system
                    current_effect_log_details["outcome_details"] = {"stat": stat_name, "change": change_amount}
                effect_processed_or_known_error = True

            elif effect_type == "teleport_player":
                target_loc_static_id = effect_rule.get("target_location_static_id")
                target_subloc_name = effect_rule.get("target_sublocation_name")
                if target_loc_static_id:
                    new_location = await location_crud.get_by_static_id(session, guild_id=guild_id, static_id=target_loc_static_id)
                    if new_location:
                        old_location_id = player.current_location_id
                        player.current_location_id = new_location.id
                        player.current_sublocation_name = target_subloc_name
                        session.add(player)
                        logger.info(f"Teleported player {player.id} to loc {new_location.static_id}, subloc: {target_subloc_name}.")
                        feedback_messages.append(f"You suddenly find yourself in {new_location.name_i18n.get(player_lang, new_location.static_id)}.")
                        await log_event(EventType.PLAYER_MOVED, session, guild_id=guild_id, # Corrected: Use Enum member
                                        details_json={"old_location_id": old_location_id, "new_location_id": new_location.id, "method": "teleport"},
                                        player_id=player.id # Pass player_id if log_event needs it explicitly
                                       )
                        current_effect_log_details["outcome_details"] = {"teleported_to_static_id": new_location.static_id, "teleported_to_location_id": new_location.id}
                    else:
                        logger.warning(f"Teleport failed: target loc_static_id '{target_loc_static_id}' not found.")
                effect_processed_or_known_error = True

            elif effect_type == "give_item":
                item_static_id = effect_rule.get("item_static_id")
                amount = effect_rule.get("amount", 1)
                logger.info(f"Placeholder: Give player {player.id} item '{item_static_id}' x{amount}.")
                feedback_messages.append(f"You receive {amount}x {item_static_id}.")
                current_effect_log_details["outcome_details"] = {"item_id": item_static_id, "amount": amount}
                effect_processed_or_known_error = True

            elif effect_type == "start_quest":
                quest_static_id = effect_rule.get("quest_static_id")
                logger.info(f"Placeholder: Start quest '{quest_static_id}' for player {player.id}.")
                feedback_messages.append(f"A new quest has begun: {quest_static_id}!")
                current_effect_log_details["outcome_details"] = {"quest_id": quest_static_id}
                effect_processed_or_known_error = True

            elif effect_type == "apply_status_effect_to_player":
                status_static_id = effect_rule.get("status_static_id")
                duration_turns = effect_rule.get("duration_turns") # Optional, could be indefinite
                # custom_properties = effect_rule.get("custom_properties_json") # For stackable effects
                if status_static_id:
                    logger.info(f"Placeholder: Apply status '{status_static_id}' to player {player.id} for {duration_turns} turns.")
                    # await apply_status_effect(session, guild_id=guild_id, target_id=player.id, target_type_str="player", status_effect_static_id=status_static_id, duration_turns=duration_turns, custom_properties_json=custom_properties, caster_id=None) # Example call
                    feedback_messages.append(f"You feel {status_static_id}.")
                    current_effect_log_details["outcome_details"] = {"status_id": status_static_id, "duration": duration_turns}
                effect_processed_or_known_error = True
            else: # Unknown effect type
                logger.warning(f"Unknown consequence effect_type: '{effect_type}' for key '{rule_config_full_key}'. Details: {effect_rule}")
                current_effect_log_details["error"] = f"Unknown consequence effect_type: '{effect_type}'."
                await log_event(
                    EventType.CONSEQUENCE_EFFECT_ERROR,
                    session,
                    guild_id=guild_id,
                    details_json=current_effect_log_details
                )
                # Temporarily simplified to avoid NameError for target_object_name_for_feedback
                feedback_messages.append("An unexpected error occurred with a consequence.")
                continue # Skip generic "applied" log for this error case

            if effect_processed_or_known_error:
                 # Update details_json for CONSEQUENCE_EFFECT_APPLIED with any specific outcomes from handlers
                current_effect_log_details.pop("error", None) # Remove error field if it was an unknown type that got handled by a plugin later (future)
                await log_event(
                    EventType.CONSEQUENCE_EFFECT_APPLIED,
                    session,
                    guild_id=guild_id,
                    details_json=current_effect_log_details
                )

            feedback_key_from_rule = effect_rule.get("feedback_message_key")
            if feedback_key_from_rule:
                # Allow target_object_name to be overridden by the effect rule if needed
                feedback_target_name = effect_rule.get("feedback_target_name", target_object_name_for_feedback)
                feedback_params = effect_rule.get("feedback_params", {})
                feedback_messages.append(_format_feedback(feedback_key_from_rule, player_lang, target_name=feedback_target_name, **feedback_params))

        except Exception as e_effect:
            logger.error(f"Error applying consequence effect {effect_rule} for key {rule_config_full_key}: {e_effect}", exc_info=True)
            feedback_messages.append("Something unexpected happened due to your action.")
            exception_log_details = {
                **base_effect_log_details,
                "rule_key": rule_config_full_key,
                "effect_index": idx,
                "failed_effect_rule": effect_rule,
                "error": str(e_effect)
            }
            await log_event(
                EventType.CONSEQUENCE_EFFECT_ERROR,
                session,
                guild_id=guild_id,
                details_json=exception_log_details
            )

    await session.flush()
    return feedback_messages
