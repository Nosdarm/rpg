import logging
from typing import Union, Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

# Assuming models and enums will be imported correctly
from ..models import PendingGeneration, Player, GuildConfig, GeneratedNpc, GeneratedQuest, Item # Add other generated entity models
from ..models.enums import ModerationStatus, PlayerStatus
from .database import transactional
# Corrected import path for generic CRUD functions
from .crud_base_definitions import create_entity, get_entity_by_id, update_entity
from .ai_prompt_builder import prepare_ai_prompt
from .ai_response_parser import parse_and_validate_ai_response, ParsedAiData, CustomValidationError, ParsedNpcData, ParsedQuestData, ParsedItemData # Import specific parsed types, and CustomValidationError
from discord.ext import commands # For bot instance type hint
from ..bot.utils import notify_master # Import the new utility
# Placeholder for game events
# from .game_events import on_enter_location


logger = logging.getLogger(__name__)

async def _mock_openai_api_call(prompt: str) -> str:
    """
    Mocks a call to an OpenAI API or similar LLM.
    Returns a sample JSON string representing AI output.
    """
    logger.info(f"Mocking OpenAI API call for prompt (first 200 chars): {prompt[:200]}...")

    # Check if the prompt is for location generation
    if "generation_type\": \"location\"" in prompt:
        mock_response_obj = [{
            "entity_type": "location",
            "name_i18n": {"en": "Mocked Mystic Grove", "ru": "Моковая Мистическая Роща"},
            "descriptions_i18n": {
                "en": "A serene grove, sunlight dappling through ancient trees. AI generated.",
                "ru": "Безмятежная роща, солнечный свет играет на древних деревьях. Сгенерировано ИИ."
            },
            "location_type": "FOREST",
            "coordinates_json": {"x": 15, "y": 25, "plane": "AstralPlane"},
            "generated_details_json": {
                "flora_i18n": {"en": "Lush magical plants.", "ru": "Пышные магические растения."},
                "fauna_i18n": {"en": "Rare mystical creatures.", "ru": "Редкие мистические существа."}
            },
            "potential_neighbors": [
                {"static_id_or_name": "town_square", "connection_description_i18n": {"en": "a shimmering portal", "ru": "мерцающий портал"}},
                {"static_id_or_name": "dark_cave_entrance", "connection_description_i18n": {"en": "a narrow, overgrown path", "ru": "узкая, заросшая тропа"}}
            ]
        }]
        return json.dumps(mock_response_obj)
    else:
        # Default mock (e.g., for NPC or other types if not specified)
        return """
        [
            {
                "entity_type": "npc",
                "name_i18n": {"en": "Sir Reginald the Bold", "ru": "Сэр Реджинальд Смелый"},
                "description_i18n": {"en": "A knight of stern gaze and noble heart.", "ru": "Рыцарь сурового взгляда и благородного сердца."},
                "stats": {"hp": 100, "attack": 10}
            }
        ]
        """

async def _mock_narrative_openai_api_call(prompt: str, language: str) -> str:
    """
    Mocks a call to an OpenAI API for narrative generation.
    Returns a sample narrative string.
    """
    logger.info(f"Mocking OpenAI API call for NARRATIVE prompt (first 200 chars): {prompt[:200]}...")
    if language == "ru":
        return f"Это пример повествования на русском языке, основанный на контексте: {prompt[:100]}..."
    else:
        return f"This is a sample narrative in English, based on the context: {prompt[:100]}..."


@transactional
async def generate_narrative(
    session: AsyncSession,
    guild_id: int,
    context: Dict[str, Any],
    # Optional: Explicitly pass player_id if player-specific language is needed
    # player_id: Optional[int] = None
) -> str:
    """
    Generates freeform narrative text using an LLM.

    Args:
        session: The database session.
        guild_id: The ID of the guild for which to generate narrative.
        context: A dictionary containing contextual information for the narrative
                 (e.g., event_type, involved_entities, location_data, world_state_summary).
        # player_id: Optional ID of the player to determine language preference.

    Returns:
        A string containing the generated narrative.
    """
    from .player_utils import get_player  # Local import to avoid circular dependency issues at module level
    from .rules import get_rule

    logger.debug(f"Generating narrative for guild_id: {guild_id} with context: {context}")

    target_language = "en"  # Default language

    # Determine target language
    # Priority: 1. Player's language (if player_id is in context and resolvable)
    #           2. Guild's main language
    player_id_from_context = context.get("player_id")
    if isinstance(player_id_from_context, int):
        # Ensure player_id_from_context is treated as int for the call
        p_id: int = player_id_from_context
        player = await get_player(session, p_id, guild_id=guild_id)
        if player and player.selected_language:
            target_language = player.selected_language
            logger.debug(f"Using player's selected language: {target_language}")
        else:
            # Fallback to guild language if player not found or has no language set
            guild_main_lang_rule = await get_rule(session, guild_id, "guild_main_language")
            if guild_main_lang_rule and isinstance(guild_main_lang_rule.value_json, str):
                target_language = guild_main_lang_rule.value_json
                logger.debug(f"Using guild's main language (player context provided but no player lang): {target_language}")
            else:
                logger.debug(f"Player language not found, guild main language not set or invalid. Defaulting to '{target_language}'.")
    else:
        guild_main_lang_rule = await get_rule(session, guild_id, "guild_main_language")
        if guild_main_lang_rule and isinstance(guild_main_lang_rule.value_json, str):
            target_language = guild_main_lang_rule.value_json
            logger.debug(f"Using guild's main language: {target_language}")
        else:
            logger.debug(f"Guild main language not set or invalid. Defaulting to '{target_language}'.")

    # Construct the prompt
    # This is a simplified prompt construction. A more sophisticated version
    # would use ai_prompt_builder or a similar utility.
    prompt_parts = [
        f"Generate a short, engaging narrative piece in {target_language.upper()}.",
        "The context for this narrative is as follows:",
    ]
    if "event_type" in context:
        prompt_parts.append(f"- Event Type: {context['event_type']}")
    if "involved_entities" in context: # e.g., {"player_name": "Hero", "npc_name": "Goblin"}
        actors = ", ".join(f"{k}: {v}" for k, v in context["involved_entities"].items())
        prompt_parts.append(f"- Key Entities Involved: {actors}")
    if "location_data" in context: # e.g., {"name": "Dark Forest", "description": "A spooky forest"}
        loc_info = ", ".join(f"{k}: {v}" for k, v in context["location_data"].items())
        prompt_parts.append(f"- Location: {loc_info}")
    if "world_state_summary" in context:
        prompt_parts.append(f"- World State Summary: {context['world_state_summary']}")
    if "custom_instruction" in context: # Allow for specific instructions
        prompt_parts.append(f"- Specific Instruction: {context['custom_instruction']}")

    prompt_parts.append("The narrative should be atmospheric and relevant to these details.")
    prompt = "\n".join(prompt_parts)

    logger.debug(f"Constructed narrative prompt (first 300 chars): {prompt[:300]}")

    # Call the (mocked) LLM
    try:
        # Using a new mock function for narrative to avoid conflicts with existing mock
        narrative_text = await _mock_narrative_openai_api_call(prompt, target_language)
        logger.info(f"Generated narrative for guild_id {guild_id} in {target_language}: {narrative_text[:100]}...")
        return narrative_text
    except Exception as e:
        logger.error(f"Error calling LLM for narrative generation (guild {guild_id}): {e}", exc_info=True)
        if target_language == "ru":
            return "Произошла ошибка при генерации повествования."
        return "An error occurred while generating the narrative."


@transactional
async def trigger_ai_generation_flow(
    session: AsyncSession, # Injected by @transactional
    bot: commands.Bot, # Added bot instance for notifications
    guild_id: int,
    location_id: Optional[int] = None,
    player_id: Optional[int] = None,
    # Potentially other context like event_type that triggered this, etc.
) -> Union[PendingGeneration, CustomValidationError, str]: # Changed to CustomValidationError
    """
    Orchestrates the AI content generation flow:
    1. Prepares a prompt.
    2. Calls the AI (mocked).
    3. Parses and validates the AI response.
    4. Creates a PendingGeneration record.
    5. Updates player status (if applicable).
    6. Notifies Master (placeholder).
    """
    try:
        prompt_context = {
            "location_id": location_id,
            "player_id": player_id,
            # Add more context as needed for prepare_ai_prompt
        }
        # prepare_ai_prompt might need a session if it directly queries DB outside of its own @transactional
        # Assuming prepare_ai_prompt is designed to be callable here.
        # If prepare_ai_prompt is also @transactional, nested transactions are usually fine with SQLAlchemy.
        prompt = await prepare_ai_prompt(session, guild_id, location_id, player_id)

        if not prompt:
            logger.error(f"Guild {guild_id}: Failed to generate AI prompt for context {prompt_context}")
            return "Failed to generate AI prompt."

        raw_ai_response = await _mock_openai_api_call(prompt)

        # This function is async
        parsed_or_error = await parse_and_validate_ai_response(raw_ai_response, guild_id)

        pending_gen_data: Dict[str, Any] = {
            "guild_id": guild_id,
            "triggered_by_user_id": player_id,
            "trigger_context_json": prompt_context,
            "ai_prompt_text": prompt,
            "raw_ai_response_text": raw_ai_response,
        }

        new_pending_generation: Optional[PendingGeneration] = None

        if isinstance(parsed_or_error, ParsedAiData):
            pending_gen_data["parsed_validated_data_json"] = parsed_or_error.model_dump()
            pending_gen_data["status"] = ModerationStatus.PENDING_MODERATION

            new_pending_generation = await create_entity(session, PendingGeneration, pending_gen_data)

            if player_id and new_pending_generation: # Update player only if pending_gen created
                player_to_update = await get_entity_by_id(session, Player, player_id, guild_id=guild_id)
                if player_to_update:
                    await update_entity(session, player_to_update, {"current_status": PlayerStatus.AWAITING_MODERATION})

        elif isinstance(parsed_or_error, CustomValidationError): # Changed to CustomValidationError
            pending_gen_data["validation_issues_json"] = parsed_or_error.model_dump()
            pending_gen_data["status"] = ModerationStatus.VALIDATION_FAILED
            new_pending_generation = await create_entity(session, PendingGeneration, pending_gen_data)
            # Return the validation error to the caller if it's critical, or just log and let Master review
            # For now, we save it and return the PendingGeneration record
            if new_pending_generation:
                 logger.warning(f"Guild {guild_id}: AI response validation failed for PendingGeneration ID {new_pending_generation.id}. Issues: {parsed_or_error.message}")
            else:
                 logger.error(f"Guild {guild_id}: AI response validation failed AND PendingGeneration record creation failed.")
                 return parsed_or_error # Or a generic error string

        else:
            logger.error(f"Guild {guild_id}: Unknown state after AI response parsing. Type: {type(parsed_or_error)}")
            return "Unknown error after AI response parsing."

        if new_pending_generation:
            if new_pending_generation.status == ModerationStatus.PENDING_MODERATION:
                await notify_master(
                    bot,
                    session, # The session from @transactional is valid here
                    guild_id,
                    f"New AI-generated content (Pending ID: {new_pending_generation.id}) requires moderation."
                )
                logger.info(f"Guild {guild_id}: New content (PendingGeneration ID: {new_pending_generation.id}) awaits moderation. Master notified.")
            elif new_pending_generation.status == ModerationStatus.VALIDATION_FAILED:
                 await notify_master(
                    bot,
                    session,
                    guild_id,
                    f"AI content generation attempt (Pending ID: {new_pending_generation.id}) resulted in validation errors. Please review."
                )
            return new_pending_generation
        else:
            logger.error(f"Guild {guild_id}: Failed to create PendingGeneration record.")
            return "Failed to save pending generation record."

    except Exception as e:
        logger.error(f"Guild {guild_id}: Exception in trigger_ai_generation_flow: {e}", exc_info=True)
        return f"Internal server error during AI generation flow: {str(e)}"


@transactional
async def save_approved_generation(
    session: AsyncSession,
    pending_generation_id: int,
    guild_id: int # Added for explicit guild context check, though get_entity_by_id also uses it
) -> bool:
    """
    Saves entities from an approved PendingGeneration record to the database.
    """
    logger.info(f"Attempting to save approved generation for PendingID: {pending_generation_id}, GuildID: {guild_id}")
    pending_gen = await get_entity_by_id(session, PendingGeneration, pending_generation_id, guild_id=guild_id)

    if not pending_gen:
        logger.warning(f"PendingGeneration ID {pending_generation_id} not found for guild {guild_id}.")
        return False

    if pending_gen.guild_id != guild_id: # Should be redundant if get_entity_by_id is correct
        logger.error(f"CRITICAL: Guild ID mismatch for PendingGeneration ID {pending_generation_id}. Expected {guild_id}, found {pending_gen.guild_id}.")
        return False

    if pending_gen.status not in [ModerationStatus.APPROVED, ModerationStatus.EDITED_PENDING_APPROVAL]: # Assuming EDITED_PENDING_APPROVAL is also ready to be saved after an edit.
        logger.warning(f"Attempt to save PendingGeneration ID {pending_generation_id} with status {pending_gen.status} (not APPROVED/EDITED_PENDING_APPROVAL).")
        return False

    if not pending_gen.parsed_validated_data_json:
        logger.error(f"No parsed_validated_data_json in approved PendingGeneration ID {pending_generation_id}")
        await update_entity(session, pending_gen, {"status": ModerationStatus.ERROR_ON_SAVE, "master_notes": "Critical: Missing parsed_validated_data_json on approval."})
        return False

    try:
        ai_data_model = ParsedAiData(**pending_gen.parsed_validated_data_json)
        saved_entity_ids: Dict[str, List[Any]] = {"npc": [], "quest": [], "item": [], "location": []} # Added location

        for entity_data in ai_data_model.generated_entities:
            # entity_dict = entity_data.model_dump() -> This is not needed as create_entity takes dict.
            # We will construct the dict for each entity type specifically.

            entity_type_val = entity_data.entity_type # Directly from the discriminated union model
            new_db_entity = None

            if entity_type_val == "npc" and isinstance(entity_data, ParsedNpcData):
                npc_data_for_db = {
                    "guild_id": guild_id, # Ensure guild_id is always passed
                    "name_i18n": entity_data.name_i18n,
                    "description_i18n": entity_data.description_i18n,
                    # Assuming GeneratedNpc model has 'properties_json' for stats and other dynamic attributes
                    # And 'ai_metadata_json' for generation related info.
                    # The ParsedNpcData might need fields like 'static_id', 'npc_type_i18n' if AI is to provide them.
                    # For now, we map what's available and matches GeneratedNpc structure.
                    "properties_json": {"stats": entity_data.stats} if entity_data.stats else {},
                    # "static_id": entity_data.static_id, # If AI provides static_id
                    # "npc_type_i18n": entity_data.npc_type_i18n, # If AI provides this
                }
                new_db_entity = await create_entity(session, GeneratedNpc, npc_data_for_db)
                if new_db_entity: saved_entity_ids["npc"].append(new_db_entity.id)
                logger.info(f"Saved NPC: {entity_data.name_i18n.get('en', 'Unknown NPC')} with ID {new_db_entity.id if new_db_entity else 'Error'}")

            elif entity_type_val == "quest" and isinstance(entity_data, ParsedQuestData):
                quest_data_for_db = {
                    "guild_id": guild_id,
                    "title_i18n": entity_data.title_i18n,
                    "description_i18n": entity_data.summary_i18n, # ParsedQuestData.summary_i18n maps to GeneratedQuest.description_i18n
                    # Assuming GeneratedQuest has 'steps_json' or similar for steps descriptions
                    # For GeneratedQuest model:
                    # description_i18n (from summary_i18n)
                    # rewards_json
                    # Needs fields like static_id from AI, or it has to be generated.
                    # For simplicity, let's assume static_id is not AI-generated for now or is part of ParsedQuestData.
                    # "static_id": entity_data.static_id, # If AI provides static_id
                    "rewards_json": entity_data.rewards_json,
                    # Placeholder for steps - GeneratedQuest might have a direct JSONB field for simple steps
                    # or require separate QuestStep entries. For now, let's assume a JSONB field.
                    # "steps_data_json": entity_data.steps_description_i18n # If GeneratedQuest has such a field
                }
                # If GeneratedQuest has steps as a list of JSON, and ParsedQuestData provides steps_description_i18n
                # This mapping needs to be aligned with the actual GeneratedQuest model structure for steps.
                # For example, if GeneratedQuest expects a field like `ai_metadata_json` to store raw step descriptions:
                quest_data_for_db["ai_metadata_json"] = {"raw_steps": entity_data.steps_description_i18n}

                new_db_entity = await create_entity(session, GeneratedQuest, quest_data_for_db)
                if new_db_entity: saved_entity_ids["quest"].append(new_db_entity.id)
                logger.info(f"Saved Quest: {entity_data.title_i18n.get('en', 'Unknown Quest')} with ID {new_db_entity.id if new_db_entity else 'Error'}")

            elif entity_type_val == "item" and isinstance(entity_data, ParsedItemData):
                item_data_for_db = {
                    "guild_id": guild_id,
                    "name_i18n": entity_data.name_i18n,
                    "description_i18n": entity_data.description_i18n,
                    # Assuming Item model has 'item_type_i18n' or a key field for item_type
                    # Item model has item_type_i18n and item_category_i18n
                    # ParsedItemData has item_type (string). We might need a mapping or store it directly.
                    # Let's assume item_type from AI can be stored in a generic 'properties_json' or a specific field.
                    # For now, let's use 'item_type_i18n' as a placeholder if AI gives localized type.
                    # If AI gives a key like "weapon", we might map it to a localized dict.
                    "item_type_i18n": {"en": entity_data.item_type, "ru": entity_data.item_type}, # Simple mapping
                    "properties_json": entity_data.properties_json,
                    # "static_id": entity_data.static_id, # If AI provides static_id
                }
                new_db_entity = await create_entity(session, Item, item_data_for_db)
                if new_db_entity: saved_entity_ids["item"].append(new_db_entity.id)
                logger.info(f"Saved Item: {entity_data.name_i18n.get('en', 'Unknown Item')} with ID {new_db_entity.id if new_db_entity else 'Error'}")

            # Add Location saving if ParsedLocationData is defined and used
            # elif entity_type_val == "location" and isinstance(entity_data, ParsedLocationData):
            #    location_data_for_db = { ... } # map fields
            #    new_db_entity = await create_entity(session, Location, location_data_for_db)
            #    if new_db_entity: saved_entity_ids["location"].append(new_db_entity.id)

            else:
                logger.warning(f"Unsupported entity_type '{entity_type_val}' encountered during saving of PendingGeneration ID {pending_generation_id}")

        master_notes_message = (
            f"Successfully saved entities: "
            f"NPC IDs: {saved_entity_ids['npc']}, "
            f"Quest IDs: {saved_entity_ids['quest']}, "
            f"Item IDs: {saved_entity_ids['item']}"
            # f"Location IDs: {saved_entity_ids['location']}" # If locations are saved
        )
        await update_entity(session, pending_gen, {
            "status": ModerationStatus.SAVED,
            "master_notes": master_notes_message
        })

        # Placeholder for post-save hooks like on_enter_location
        # trigger_context = pending_gen.trigger_context_json or {}
        # if "location_id" in trigger_context:
        #     player_id_context = trigger_context.get("player_id")
        #     # await on_enter_location(session, guild_id, location_id=trigger_context["location_id"], player_id=player_id_context, new_entities=saved_entity_ids)
        #     logger.info(f"Placeholder: Called on_enter_location for location {trigger_context['location_id']}")

        if pending_gen.triggered_by_user_id:
            player = await get_entity_by_id(session, Player, entity_id=pending_gen.triggered_by_user_id, guild_id=guild_id)
            if player and player.current_status == PlayerStatus.AWAITING_MODERATION:
                # TODO: More robust logic: check if there are OTHER pending_generations for this player.
                # For now, assume this resolves the await for this specific player action.
                # This might require linking player action ID to pending_generation ID.
                await update_entity(session, player, {"current_status": PlayerStatus.EXPLORING}) # Or IDLE, or previous status
                logger.info(f"Player {player.id} status updated from {PlayerStatus.AWAITING_MODERATION.name} to {PlayerStatus.EXPLORING.name} after generation ID {pending_generation_id} saved.")
            elif player:
                logger.info(f"Player {player.id} was trigger for generation ID {pending_generation_id}, but status was {player.current_status.name} (not AWAITING_MODERATION). No status change.")


        logger.info(f"Successfully processed and saved entities from PendingGeneration ID {pending_generation_id} for guild {guild_id}")
        return True

    except Exception as e:
        logger.error(f"Error saving entities from PendingGeneration ID {pending_generation_id} for guild {guild_id}: {e}", exc_info=True)
        # Ensure pending_gen is loaded before trying to update it in exception handler
        loaded_pending_gen = await get_entity_by_id(session, PendingGeneration, pending_generation_id, guild_id=guild_id)
        if loaded_pending_gen:
            try:
                await update_entity(session, loaded_pending_gen, {"status": ModerationStatus.ERROR_ON_SAVE, "master_notes": f"Saving error: {str(e)}"})
            except Exception as update_err:
                logger.error(f"Failed to update PendingGeneration status to ERROR_ON_SAVE for ID {pending_generation_id}: {update_err}", exc_info=True)
        else:
            logger.error(f"Could not load PendingGeneration ID {pending_generation_id} to mark as ERROR_ON_SAVE.")
        return False

logger.info("AI Orchestrator module initialized with trigger_ai_generation_flow and save_approved_generation.")

# Add to src/core/__init__.py:
# from .ai_orchestrator import trigger_ai_generation_flow, save_approved_generation
# __all__.extend(["trigger_ai_generation_flow", "save_approved_generation"])
