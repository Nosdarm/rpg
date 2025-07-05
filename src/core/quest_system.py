import logging
from typing import Optional, List, Any, Dict # Added List, Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload

from src.models import StoryLog
from src.models.quest import PlayerQuestProgress, QuestStatus, GeneratedQuest, QuestStep
from src.models.enums import EventType, RelationshipEntityType # Added RelationshipEntityType
from src.core.rules import get_rule
from src.core.game_events import log_event as core_log_event

# For LLM call (conceptual)
# from src.core.ai_prompt_builder import prepare_quest_goal_evaluation_prompt
# from src.core.ai_orchestrator import get_llm_evaluation_for_goal

logger = logging.getLogger(__name__)

async def handle_player_event_for_quest(
    session: AsyncSession,
    guild_id: int,
    event_log_entry: StoryLog,
    player_id: Optional[int] = None,
    party_id: Optional[int] = None,
) -> None:
    """
    Handles a player/party event (via its StoryLog entry) and checks if it triggers
    any progress in active quests for the involved player(s).
    """
    if not player_id and not party_id:
        logger.warning(f"Quest system: handle_player_event_for_quest for guild {guild_id} without player_id or party_id.")
        return

    logger.info(
        f"Quest system: Handling event (log_id: {event_log_entry.id}, type: {event_log_entry.event_type.value}) "
        f"for guild {guild_id}. Player: {player_id}, Party: {party_id}."
    )

    target_player_ids: list[int] = []
    if player_id and player_id not in target_player_ids:
        target_player_ids.append(player_id)

    if party_id:
        from src.core.crud.crud_party import party_crud
        party_obj = await party_crud.get(session=session, id=party_id, guild_id=guild_id)
        if party_obj and party_obj.player_ids_json:
            party_member_ids = [pid for pid in party_obj.player_ids_json if isinstance(pid, int)]
            for member_id in party_member_ids:
                if member_id not in target_player_ids:
                    target_player_ids.append(member_id)
        elif party_obj:
             logger.info(f"Quest system: Party {party_id} found but has no player_ids_json.")
        else:
            logger.info(f"Quest system: Party {party_id} not found for event {event_log_entry.id}.")


    if not target_player_ids:
        logger.info(f"Quest system: No target player IDs for guild {guild_id}, event {event_log_entry.id}.")
        return

    logger.debug(f"Quest system: Target player IDs for event processing: {target_player_ids}")

    for p_id in target_player_ids:
        # Re-fetch active progress entries inside the loop for each player to ensure fresh state if previous PQP for another player committed.
        # Although, typically this whole handle_player_event_for_quest would be one transaction.
        stmt = (
            select(PlayerQuestProgress)
            .where(
                PlayerQuestProgress.player_id == p_id,
                PlayerQuestProgress.guild_id == guild_id,
                PlayerQuestProgress.status.in_([QuestStatus.STARTED, QuestStatus.IN_PROGRESS])
            )
            .options(
                joinedload(PlayerQuestProgress.quest).options(
                    selectinload(GeneratedQuest.steps), # Use selectinload for lists
                    joinedload(GeneratedQuest.questline) # Can be joinedload if one-to-one/many-to-one
                ),
                joinedload(PlayerQuestProgress.current_step) # Can be joinedload
            )
        )
        result = await session.execute(stmt)
        active_progress_entries = result.scalars().all() # Removed .unique()

        if not active_progress_entries:
            logger.debug(f"Player {p_id} has no active quests matching STARTED or IN_PROGRESS for this event cycle.")
            continue

        logger.info(f"Player {p_id} has {len(active_progress_entries)} active quest progress entries to check.")

        for progress_entry in active_progress_entries:
            if not progress_entry.quest or not progress_entry.current_step:
                logger.warning(f"PQP_ID {progress_entry.id} for player {p_id} is missing fully loaded quest or current_step. Skipping.")
                continue

            current_step = progress_entry.current_step
            logger.info(f"Player {p_id}: Checking quest '{progress_entry.quest.static_id}' (PQP_ID: {progress_entry.id}), step {current_step.step_order} ('{current_step.title_i18n.get('en', 'N/A')}')")

            mechanic_match = await _check_mechanic_match(session, guild_id, event_log_entry, current_step.required_mechanics_json)

            if mechanic_match:
                logger.info(f"Player {p_id}: Mechanic match for PQP_ID {progress_entry.id}, step {current_step.step_order}.")

                goal_achieved = True # Assume true if no abstract goal
                if current_step.abstract_goal_json and current_step.abstract_goal_json.get("enabled", False):
                    goal_achieved = await _evaluate_abstract_goal(session, guild_id, p_id, party_id, progress_entry.quest, current_step, event_log_entry)

                if goal_achieved:
                    logger.info(f"Player {p_id}: Goal achieved for PQP_ID {progress_entry.id}, step {current_step.step_order}. Applying consequences.")

                    # Pass event_log_entry to _apply_quest_consequences for context (e.g., source_log_id for XP)
                    await _apply_quest_consequences(
                        session, guild_id,
                        current_step.consequences_json,
                        p_id, party_id,
                        progress_entry.quest.id, current_step.id,
                        event_log_entry
                    )

                    await core_log_event(
                        session, guild_id, EventType.QUEST_STEP_COMPLETED.name, # Use EventType directly
                        details_json={
                            "player_id": p_id, "quest_id": progress_entry.quest.id, "quest_static_id": progress_entry.quest.static_id,
                            "step_id": current_step.id, "step_order": current_step.step_order,
                            "step_title": current_step.title_i18n.get("en", "N/A")
                        },
                        player_id=p_id,
                        location_id=event_log_entry.location_id
                    )

                    await _advance_quest_progress(session, guild_id, progress_entry, p_id, party_id, event_log_entry)
                else:
                    logger.info(f"Player {p_id}: Abstract goal not met for PQP_ID {progress_entry.id}, step {current_step.step_order}.")
            # else: # No mechanic match, already logged in _check_mechanic_match if needed
            #     logger.debug(f"No mechanic match for PQP_ID {progress_entry.id}, step {current_step.step_order} from event {event_log_entry.event_type.value}.")


async def _check_mechanic_match(
    session: AsyncSession, guild_id: int, event: StoryLog, required_mechanics: Optional[Dict[str, Any]]
) -> bool:
    if not required_mechanics: # If a step is purely narrative or advances automatically, it might have no required_mechanics.
        logger.debug("No specific required mechanics for this step. This step might advance through other means (e.g. dialogue choice).")
        return False # For an event to trigger progress, mechanics must be defined.

    required_event_type_str = required_mechanics.get("event_type")
    if not isinstance(required_event_type_str, str):
        logger.debug(f"Required event_type is missing or not a string in mechanics: {required_mechanics}")
        return False

    if event.event_type.name != required_event_type_str.upper():
        # logger.debug(f"Event type mismatch: Event is {event.event_type.name}, required is {required_event_type_str.upper()}")
        return False

    # At this point, event_type matches. Now check details based on RuleConfig.
    rule_key = f"quest_rules:mechanic_matching:{event.event_type.name}"
    matching_rules = await get_rule(session, guild_id, rule_key, default={})
    # Example matching_rules: {"required_fields": ["target_id", "item_id"], "value_checks": {"action_type": "use_on_self"}}

    required_details_from_mechanics = required_mechanics.get("details_subset", {}) # Details specified in the quest step itself

    # Combine specific checks from RuleConfig and from quest step's "details_subset"
    # For now, prioritize "details_subset" from the quest step itself for simplicity.
    # A more complex system could merge or layer these.

    if not required_details_from_mechanics: # If only event_type is specified in required_mechanics, it's a match.
        logger.debug(f"Event type '{event.event_type.name}' matched. No further details required by step mechanics.")
        return True

    event_details = event.details_json or {}
    for key, req_value in required_details_from_mechanics.items():
        # Support for nested keys like "target.static_id" could be added here
        # current_event_val = event_details
        # for k_part in key.split('.'):
        #     if isinstance(current_event_val, dict):
        #         current_event_val = current_event_val.get(k_part)
        #     else:
        #         current_event_val = None
        #         break
        # if current_event_val != req_value: ...

        if event_details.get(key) != req_value:
            logger.debug(f"Detail mismatch for key '{key}': event has '{event_details.get(key)}', required is '{req_value}'.")
            return False

    logger.debug(f"All required details from 'details_subset' matched for event type '{event.event_type.name}'.")
    return True

async def _evaluate_abstract_goal(
    session: AsyncSession, guild_id: int, player_id: int, party_id: Optional[int],
    quest: GeneratedQuest, step: QuestStep, event_context: StoryLog
) -> bool:
    if not step.abstract_goal_json or not step.abstract_goal_json.get("enabled", False):
        return True

    goal_config = step.abstract_goal_json
    goal_description_i18n = goal_config.get("description_i18n", {})
    # Attempt to get localized description, fallback to 'en' or a generic message
    player_lang = "en" # Placeholder: In a real scenario, get player's selected language
    goal_description = goal_description_i18n.get(player_lang, goal_description_i18n.get("en", "No specific goal description provided."))

    evaluation_method = goal_config.get("evaluation_method", "rule_based")

    logger.info(f"Player {player_id}: Evaluating abstract goal for quest '{quest.static_id}', step {step.step_order}. Method: {evaluation_method}. Goal: '{goal_description}'")

    if evaluation_method == "llm_based":
        # from src.core.ai_prompt_builder import prepare_quest_goal_evaluation_prompt
        # from src.core.ai_orchestrator import get_llm_evaluation # Assuming a generic orchestrator function
        # # 1. Collect context logs (e.g., last N events for the player/party)
        # context_logs_stmt = select(StoryLog).where(StoryLog.guild_id == guild_id, # ... filter by player/party, time period ...
        #                                           ).order_by(StoryLog.timestamp.desc()).limit(goal_config.get("llm_context_log_count", 5))
        # context_logs_result = await session.execute(context_logs_stmt)
        # context_logs = context_logs_result.scalars().all()
        # prompt = await prepare_quest_goal_evaluation_prompt(session, guild_id, player_id, party_id, quest, step, context_logs, event_context)
        # try:
        #     llm_response_str = await get_llm_evaluation(guild_id=guild_id, prompt=prompt, expected_format="boolean_string") # "true" or "false"
        #     is_achieved = llm_response_str.strip().lower() == "true"
        #     logger.info(f"LLM evaluation for goal '{goal_description}': {is_achieved} (Raw: '{llm_response_str}')")
        #     return is_achieved
        # except Exception as e:
        #     logger.error(f"Error during LLM-based goal evaluation: {e}. Defaulting to False.")
        #     return False
        logger.warning("LLM-based abstract goal evaluation is not yet implemented. Defaulting to True for this step.")
        return True

    elif evaluation_method == "rule_based":
        rule_key = goal_config.get("rule_config_key")
        if not rule_key:
            logger.warning(f"Rule-based evaluation chosen for goal, but 'rule_config_key' is missing in abstract_goal_json. Defaulting to True.")
            return True

        goal_rules = await get_rule(session, guild_id, rule_key, default=None)
        if goal_rules is None:
            logger.warning(f"Rules for goal (key: {rule_key}) not found in RuleConfig. Defaulting to True.")
            return True

        # Example rule structure for goal_rules:
        # { "type": "check_player_stat", "stat_name": "reputation_with_faction_X", "operator": ">=", "value": 50 }
        # { "type": "check_world_flag", "flag_name": "ancient_gate_opened", "expected_value": True }
        # This part requires a mini rule-engine or specific handlers per rule type.
        logger.warning(f"Rule-based abstract goal evaluation for key '{rule_key}' is not yet implemented. Defaulting to True for this step.")
        return True # Placeholder for actual rule processing

    logger.warning(f"Unknown evaluation_method '{evaluation_method}' for abstract goal. Defaulting to True.")
    return True

async def _advance_quest_progress(
    session: AsyncSession, guild_id: int, progress_entry: PlayerQuestProgress,
    player_id: int, party_id: Optional[int], triggering_event: StoryLog
):
    quest = progress_entry.quest
    current_step = progress_entry.current_step # Should be loaded

    if not quest or not current_step: # Should not happen if checks above are done
        logger.error(f"Cannot advance quest progress for PQP_ID {progress_entry.id}: quest or current_step is None.")
        return

    next_step_order = current_step.step_order + 1
    next_step: Optional[QuestStep] = None
    # Ensure steps are loaded and sorted if not already guaranteed by relationship options
    # sorted_steps = sorted(quest.steps, key=lambda s: s.step_order) # Already done via selectinload options

    for step_in_quest in quest.steps: # quest.steps should be ordered by step_order due to relationship
        if step_in_quest.step_order == next_step_order:
            next_step = step_in_quest
            break

    if next_step:
        progress_entry.current_step_id = next_step.id
        # progress_entry.current_step = next_step # ORM should handle this if current_step_id is updated
        progress_entry.status = QuestStatus.IN_PROGRESS # Ensure status reflects ongoing nature
        session.add(progress_entry)
        # await session.flush() # Flush to make changes visible before logging/feedback if needed
        logger.info(f"Player {player_id} advanced on quest '{quest.static_id}' (PQP_ID: {progress_entry.id}) to step {next_step.step_order} ('{next_step.title_i18n.get('en', 'N/A')}').")

        # Log event for starting the new step
        await core_log_event(
            session, guild_id, EventType.SYSTEM_EVENT.name,
            details_json={
                "subtype": "QUEST_STEP_STARTED",
                "player_id": player_id, "quest_id": quest.id, "quest_static_id": quest.static_id,
                "step_id": next_step.id, "step_order": next_step.step_order, "step_title": next_step.title_i18n.get("en", "N/A")
            },
            player_id=player_id, location_id=triggering_event.location_id
        )
        # TODO: Provide feedback to player about new step
    else:
        # This was the last step, complete the quest
        progress_entry.status = QuestStatus.COMPLETED
        progress_entry.current_step_id = None
        session.add(progress_entry)
        # await session.flush()
        logger.info(f"Player {player_id} completed quest '{quest.static_id}' (PQP_ID: {progress_entry.id}).")

        await core_log_event(
            session, guild_id, EventType.QUEST_COMPLETED.name,
            details_json={
                "player_id": player_id, "quest_id": quest.id, "quest_static_id": quest.static_id,
                "quest_title": quest.title_i18n.get("en", "N/A")
            },
            player_id=player_id, location_id=triggering_event.location_id
        )

        if quest.rewards_json:
            logger.info(f"Applying overall rewards for completed quest '{quest.static_id}'.")
            await _apply_quest_consequences(session, guild_id, quest.rewards_json, player_id, party_id, quest.id, None, triggering_event)

        # TODO: Check for next quest in questline if quest.questline_id is set and quest.questline relationship is loaded.
        # If quest.questline and quest.questline.quests are loaded, can find next quest by order/dependency.


async def _apply_quest_consequences(
    session: AsyncSession,
    guild_id: int,
    consequences_json: Optional[Dict[str, Any]],
    player_id_context: Optional[int] = None,
    party_id_context: Optional[int] = None,
    quest_id_for_log: Optional[int] = None,
    step_id_for_log: Optional[int] = None,
    triggering_event: Optional[StoryLog] = None
) -> None:
    if not consequences_json:
        logger.debug("No consequences to apply.")
        return

    if not player_id_context and not party_id_context:
        logger.warning("Cannot apply consequences: no player_id or party_id specified for context.")
        return

    logger.info(f"Applying quest consequences for guild {guild_id}: {consequences_json}. Context Player: {player_id_context}, Party: {party_id_context}")

    target_player_ids_for_consequences: list[int] = []
    if party_id_context:
        from src.core.crud.crud_party import party_crud
        party_obj = await party_crud.get(session=session, id=party_id_context, guild_id=guild_id)
        if party_obj and party_obj.player_ids_json:
            party_member_ids = [pid for pid in party_obj.player_ids_json if isinstance(pid, int)]
            for member_id in party_member_ids:
                if member_id not in target_player_ids_for_consequences:
                     target_player_ids_for_consequences.append(member_id)
        else:
            if player_id_context and player_id_context not in target_player_ids_for_consequences:
                target_player_ids_for_consequences.append(player_id_context)
    elif player_id_context:
        if player_id_context not in target_player_ids_for_consequences:
            target_player_ids_for_consequences.append(player_id_context)

    if not target_player_ids_for_consequences:
        logger.info("No target players determined for consequences.")
        return

    logger.debug(f"Target player IDs for consequences: {target_player_ids_for_consequences}")

    source_log_id_for_consequences = triggering_event.id if triggering_event else None


    if "xp_award" in consequences_json:
        xp_data = consequences_json["xp_award"]
        xp_amount = xp_data.get("amount", 0)
        if isinstance(xp_amount, int) and xp_amount > 0:
            from src.core.experience_system import award_xp
            # RelationshipEntityType is already imported at the top of the file

            source_event_type_for_xp = EventType.SYSTEM_EVENT
            # Details for this SYSTEM_EVENT will indicate it's a quest reward
            # This avoids needing specific QUEST_REWARD / QUEST_STEP_REWARD in EventType enum for now

            if party_id_context:
                await award_xp(session, guild_id, party_id_context, RelationshipEntityType.PARTY, xp_amount,
                               source_event_type=source_event_type_for_xp, # Pass the Enum member
                               source_log_id=source_log_id_for_consequences)
                logger.info(f"Awarded {xp_amount} XP to party {party_id_context} (players: {target_player_ids_for_consequences}) for quest/step.")
            elif target_player_ids_for_consequences:
                for p_id_target in target_player_ids_for_consequences:
                    await award_xp(session, guild_id, p_id_target, RelationshipEntityType.PLAYER, xp_amount,
                                   source_event_type=source_event_type_for_xp, # Pass the Enum member
                                   source_log_id=source_log_id_for_consequences)
                    logger.info(f"Awarded {xp_amount} XP to player {p_id_target} for quest/step.")

    if "relationship_changes" in consequences_json and isinstance(consequences_json["relationship_changes"], list):
        from src.core.relationship_system import update_relationship
        # RelationshipEntityType is already imported

        for change_info in consequences_json["relationship_changes"]:
            target_ent_id = change_info.get("target_entity_id")
            target_ent_type_str = change_info.get("target_entity_type")
            delta = change_info.get("delta", change_info.get("change_value", 0))

            if not all([isinstance(target_ent_id, int), isinstance(target_ent_type_str, str), isinstance(delta, int)]):
                logger.warning(f"Skipping invalid relationship change data: {change_info}")
                continue
            try:
                target_ent_type_enum = RelationshipEntityType[target_ent_type_str.upper()]
            except KeyError:
                logger.warning(f"Invalid target_entity_type '{target_ent_type_str}' in relationship change.")
                continue

            for p_id_actor in target_player_ids_for_consequences:
                await update_relationship(
                    session, guild_id,
                    entity_doing_id=p_id_actor, entity_doing_type=RelationshipEntityType.PLAYER,
                    target_entity_id=target_ent_id, target_entity_type=target_ent_type_enum,
                    event_type=EventType.SYSTEM_EVENT.name,
                    event_details_log_id=source_log_id_for_consequences if source_log_id_for_consequences else 0
                )
                logger.info(f"Applied relationship change (rule-driven from SYSTEM_EVENT/quest context) for player {p_id_actor} towards {target_ent_type_str}:{target_ent_id}.")


    if "item_rewards" in consequences_json and isinstance(consequences_json["item_rewards"], list):
        for item_reward_info in consequences_json["item_rewards"]:
            item_static_id = item_reward_info.get("item_static_id")
            quantity = item_reward_info.get("quantity", 1)
            if isinstance(item_static_id, str) and isinstance(quantity, int) and quantity > 0:
                for p_id_target in target_player_ids_for_consequences:
                    logger.info(f"Placeholder: Awarded item '{item_static_id}' (qty: {quantity}) to player {p_id_target}.")
                    await core_log_event(
                        session, guild_id, EventType.ITEM_ACQUIRED.name,
                        details_json={
                            "player_id": p_id_target, "item_static_id": item_static_id, "quantity": quantity,
                            "source": "quest_reward",
                            "source_quest_id": quest_id_for_log, "source_step_id": step_id_for_log
                        },
                        player_id=p_id_target, location_id=triggering_event.location_id if triggering_event else None
                    )

    if "world_state_changes" in consequences_json and isinstance(consequences_json["world_state_changes"], list):
        for ws_change_info in consequences_json["world_state_changes"]:
            flag_key = ws_change_info.get("flag_key")
            new_value = ws_change_info.get("value")
            if isinstance(flag_key, str) and new_value is not None:
                logger.info(f"Placeholder: World state flag '{flag_key}' set to '{new_value}'.")
                await core_log_event(
                    session, guild_id, EventType.WORLD_STATE_CHANGE.name,
                    details_json={
                        "flag_key": flag_key, "new_value": new_value,
                        "source": "quest_consequence",
                        "source_quest_id": quest_id_for_log, "source_step_id": step_id_for_log,
                        "triggered_by_player_id": player_id_context,
                        "triggered_by_party_id": party_id_context,
                    },
                    location_id=triggering_event.location_id if triggering_event else None
                )

    # await session.flush()

logger.info("Quest system module (handle_player_event_for_quest, _apply_quest_consequences, etc.) structure defined.")
