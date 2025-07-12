import json
import logging
from typing import Union, Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

# Assuming models and enums will be imported correctly
from ..models import (
    PendingGeneration, Player, GuildConfig, GeneratedNpc, GeneratedQuest, Item,
    Relationship as RelationshipModel, Location, GeneratedFaction # Added Location and GeneratedFaction
)
from ..models.enums import ModerationStatus, PlayerStatus, RelationshipEntityType
import os # Moved to top
import openai # Moved to top
from .database import transactional
# Corrected import path for generic CRUD functions
from .crud_base_definitions import create_entity, get_entity_by_id, update_entity
from .ai_response_parser import parse_and_validate_ai_response, ParsedAiData, CustomValidationError, ParsedNpcData, ParsedQuestData, ParsedItemData, ParsedRelationshipData, ParsedNpcTraderData # Ensure ParsedNpcTraderData is here
from discord.ext import commands # For bot instance type hint
from ..bot.utils import notify_master # Import the new utility
from .rules import get_rule

# CRUD imports moved to module level for easier patching in tests
from .crud.crud_faction import crud_faction
from .crud.crud_npc import npc_crud as actual_npc_crud
from .crud.crud_relationship import crud_relationship
from ..models import Base # For MAPPING_ENTITY_TYPE_TO_SQLALCHEMY_MODEL
from typing import Type # For MAPPING_ENTITY_TYPE_TO_SQLALCHEMY_MODEL

# Placeholder for game events
# from .game_events import on_enter_location


logger = logging.getLogger(__name__)

# Mapping from entity type string to SQLAlchemy model
MAPPING_ENTITY_TYPE_TO_SQLALCHEMY_MODEL: Dict[str, Type[Base]] = {
    "npc": GeneratedNpc,
    "item": Item,
    "quest": GeneratedQuest,
    "location": Location, # type: ignore[name-defined] # Assuming Location is correctly imported but Pyright struggles
    "faction": GeneratedFaction, # type: ignore[name-defined] # Assuming GeneratedFaction is correctly imported
    "relationship": RelationshipModel,
    "npc_trader": GeneratedNpc,
}


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
        # Corrected call to get_player based on pyright errors (missing player_id, guild_id already assigned)
        # This assumes get_player signature is (session, *, player_id: int, guild_id: int) or similar with named args.
        player = await get_player(session, player_id=p_id, guild_id=guild_id)
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
async def handle_dynamic_event(
    session: AsyncSession,
    guild_id: int,
    context: Dict[str, Any],
    bot: Optional[commands.Bot] = None
) -> Union[PendingGeneration, CustomValidationError, str, None]:
    """
    A more generic function to trigger AI generation for various events.
    Checks rules to see if generation should even occur.
    """
    # 1. Check RuleConfig to see if this trigger type should generate content
    trigger_type = context.get("trigger_type", "unknown")
    rule_key = f"ai:generation:triggers:{trigger_type}"
    should_generate_rule = await get_rule(session, guild_id, rule_key, default={"enabled": False, "chance": 0.0})

    # Ensure rule is a dict and has expected keys
    if not isinstance(should_generate_rule, dict):
        should_generate_rule = {"enabled": False, "chance": 0.0}

    if not should_generate_rule.get("enabled", False):
        logger.debug(f"AI generation for trigger '{trigger_type}' is disabled by RuleConfig for guild {guild_id}.")
        return None

    # 2. Check chance
    import random
    chance = should_generate_rule.get("chance", 0.0)
    if random.random() > chance:
        logger.debug(f"AI generation for trigger '{trigger_type}' did not meet chance {chance} for guild {guild_id}.")
        return None

    logger.info(f"Triggering AI generation for guild {guild_id} due to '{trigger_type}' event.")

    # 3. Prepare Prompt
    # This assumes a more generic prompt builder that takes a context dict
    prompt = f"Generate a dynamic event for a text RPG. Context: {json.dumps(context)}"
    # In a real scenario, this would call a more sophisticated prompt builder
    # prompt = await prepare_dynamic_event_prompt(session, guild_id, context)

    # 4. Call AI, Parse, and Save
    # The rest of the logic is similar to the original trigger_ai_generation_flow
    raw_ai_response = await _mock_openai_api_call(prompt)
    parsed_or_error = await parse_and_validate_ai_response(raw_ai_response, guild_id, session)

    pending_gen_data = {
        "guild_id": guild_id,
        "triggered_by_user_id": context.get("player_id"),
        "trigger_context_json": context,
        "ai_prompt_text": prompt,
        "raw_ai_response_text": raw_ai_response,
    }

    if isinstance(parsed_or_error, ParsedAiData):
        pending_gen_data["parsed_validated_data_json"] = parsed_or_error.model_dump()
        pending_gen_data["status"] = ModerationStatus.PENDING_MODERATION
    elif isinstance(parsed_or_error, CustomValidationError):
        pending_gen_data["validation_issues_json"] = parsed_or_error.model_dump()
        pending_gen_data["status"] = ModerationStatus.VALIDATION_FAILED
    else:
        return "Unknown parsing error."

    new_pending_generation = await create_entity(session, PendingGeneration, pending_gen_data)

    if new_pending_generation and bot:
        message = (
            f"New AI content (ID: {new_pending_generation.id}) requires moderation."
            if new_pending_generation.status == ModerationStatus.PENDING_MODERATION
            else f"AI content (ID: {new_pending_generation.id}) failed validation."
        )
        await notify_master(bot, session, guild_id, message)

    if new_pending_generation.triggered_by_user_id:
        player = await get_entity_by_id(session, Player, entity_id=new_pending_generation.triggered_by_user_id, guild_id=guild_id)
        if player:
            await update_entity(session, player, {"current_status": PlayerStatus.AWAITING_MODERATION})


    return new_pending_generation

async def make_real_ai_call(prompt: str, api_key: Optional[str] = None) -> str:
    """
    Makes a real call to the OpenAI API (ChatCompletion endpoint).
    """
    # Imports moved to module level
    resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not resolved_api_key:
        logger.error("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
        return "Error: OpenAI API key not configured."

    client = openai.AsyncOpenAI(api_key=resolved_api_key)

    logger.info(f"Making real OpenAI API call (prompt starts with: {prompt[:100]}...)")
    try:
        chat_completion = await client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant for a text-based RPG, generating game content according to specific schemas and instructions.",
                },
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="gpt-3.5-turbo", # Or consider gpt-4-turbo if available/needed
            # Add other parameters like temperature, max_tokens if needed
        )
        response_content = chat_completion.choices[0].message.content
        if response_content is None:
            logger.warning("OpenAI API returned None content.")
            return "Error: AI returned empty content."
        logger.info(f"OpenAI API call successful. Response length: {len(response_content)}")
        return response_content
    except openai.APIConnectionError as e:
        logger.error(f"OpenAI API request failed to connect: {e}", exc_info=True)
        return f"Error: Failed to connect to OpenAI API. {e}"
    except openai.RateLimitError as e:
        logger.error(f"OpenAI API request exceeded rate limit: {e}", exc_info=True)
        return f"Error: OpenAI API rate limit exceeded. {e}"
    except openai.APIStatusError as e:
        logger.error(f"OpenAI API returned an API Error: {e.status_code} - {e.response}", exc_info=True)
        return f"Error: OpenAI API error ({e.status_code}). {e.message}"
    except Exception as e:
        logger.error(f"An unexpected error occurred during OpenAI API call: {e}", exc_info=True)
        return f"Error: An unexpected error occurred with the AI call. {e}"


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
        saved_entity_ids: Dict[str, List[Any]] = {"npc": [], "quest": [], "item": [], "location": [], "relationship": []}
        static_id_to_db_id_map: Dict[str, Dict[str, Any]] = {} # Stores {"static_id": {"db_id": id, "type": type_enum}}

        # Pass 1: Create NPCs (and Factions, if they were part of this flow) to get their DB IDs for relationships
        for entity_data in ai_data_model.generated_entities:
            db_model_for_entity = MAPPING_ENTITY_TYPE_TO_SQLALCHEMY_MODEL.get(entity_data.entity_type.lower())
            if not db_model_for_entity:
                logger.warning(f"No SQLAlchemy model mapping found for entity type: {entity_data.entity_type}. Skipping entity in Pass 1.")
                continue

            if isinstance(entity_data, ParsedNpcData): # Handles NPC and potentially NPC_Trader if ParsedNpcTraderData inherits ParsedNpcData
                npc_data_for_db = {
                    "guild_id": guild_id,
                    "name_i18n": entity_data.name_i18n,
                    "description_i18n": entity_data.description_i18n,
                    "properties_json": {"stats": entity_data.stats} if entity_data.stats else {},
                    "static_id": entity_data.static_id,
                    # Default npc_type_i18n, can be overridden by trader specific logic
                    "npc_type_i18n": {"en": "NPC", "ru": "НПС"}
                }
                # Ensure 'level' from ParsedNpcData is saved into properties_json
                if entity_data.level is not None:
                    if not isinstance(npc_data_for_db["properties_json"], dict): # Should always be a dict due to above line
                        npc_data_for_db["properties_json"] = {}
                    npc_data_for_db["properties_json"]["level"] = entity_data.level


                if isinstance(entity_data, ParsedNpcTraderData):
                    if entity_data.role_i18n: # This is valid for ParsedNpcTraderData
                        npc_data_for_db["npc_type_i18n"] = entity_data.role_i18n

                    current_props = npc_data_for_db.get("properties_json", {})
                    if not isinstance(current_props, dict): current_props = {} # Ensure it's a dict

                    if entity_data.inventory_template_key: # Valid for ParsedNpcTraderData
                        current_props["inventory_template_key"] = entity_data.inventory_template_key
                    # If generated_inventory_items needs to be stored in properties_json for the NPC model:
                    # if entity_data.generated_inventory_items:
                    #    current_props["generated_inventory_items_meta"] = [item.model_dump() for item in entity_data.generated_inventory_items]
                    npc_data_for_db["properties_json"] = current_props

                new_npc_db_any = await create_entity(session, db_model_for_entity, npc_data_for_db)

                # Cast to GeneratedNpc to access id and static_id safely
                if new_npc_db_any and isinstance(new_npc_db_any, GeneratedNpc):
                    new_npc_db: GeneratedNpc = new_npc_db_any
                    saved_entity_ids["npc"].append(new_npc_db.id)
                    if new_npc_db.static_id:
                        static_id_to_db_id_map[new_npc_db.static_id] = {"db_id": new_npc_db.id, "type": RelationshipEntityType.GENERATED_NPC}
                    logger.info(f"Saved {entity_data.entity_type} (Pass 1): {entity_data.name_i18n.get('en', 'Unknown NPC')} with ID {new_npc_db.id}, StaticID: {new_npc_db.static_id}")
                else:
                    logger.error(f"Failed to save {entity_data.entity_type} with static_id {entity_data.static_id} or it was of unexpected type.")

            # elif isinstance(entity_data, ParsedFactionData): # Example if factions were created here
            #     # ... save faction and add to static_id_to_db_id_map ...
            #     pass

        await session.flush() # Ensure DB IDs are available for the next pass

        # Pass 2: Create other primary entities (Quests, Items) and then Relationships
        for entity_data in ai_data_model.generated_entities:
            entity_type_lower = entity_data.entity_type.lower()
            db_model_for_entity = MAPPING_ENTITY_TYPE_TO_SQLALCHEMY_MODEL.get(entity_type_lower)

            if not db_model_for_entity:
                logger.warning(f"No SQLAlchemy model mapping for entity type: {entity_data.entity_type}. Skipping entity in Pass 2.")
                continue

            new_db_entity_any: Optional[Base] = None # Use Base type from create_entity

            if isinstance(entity_data, (ParsedNpcData)): # Already handled in Pass 1
                continue

            data_to_create: Dict[str, Any] = {"guild_id": guild_id} # Common field

            if entity_type_lower == "quest" and isinstance(entity_data, ParsedQuestData):
                data_to_create.update({
                    "title_i18n": entity_data.title_i18n,
                    "description_i18n": entity_data.summary_i18n,
                    "rewards_json": entity_data.rewards_json,
                    "ai_metadata_json": {"raw_steps": [step.model_dump(mode='json') for step in entity_data.steps]},
                    "static_id": entity_data.static_id,
                    "min_level": entity_data.min_level,
                })
                new_db_entity_any = await create_entity(session, db_model_for_entity, data_to_create)
                if new_db_entity_any and isinstance(new_db_entity_any, GeneratedQuest):
                    current_quest_db: GeneratedQuest = new_db_entity_any # Safe cast after check
                    saved_entity_ids["quest"].append(current_quest_db.id)
                    logger.info(f"Saved Quest (Pass 2): {entity_data.title_i18n.get('en', 'Unknown Quest')} with ID {current_quest_db.id}")
                elif not new_db_entity_any:
                    logger.error(f"Failed to create Quest DB entry for static_id: {entity_data.static_id}")


            elif entity_type_lower == "item" and isinstance(entity_data, ParsedItemData):
                data_to_create.update({
                    "name_i18n": entity_data.name_i18n,
                    "description_i18n": entity_data.description_i18n,
                    "item_type_i18n": {"en": entity_data.item_type, "ru": entity_data.item_type},
                    "properties_json": entity_data.properties_json,
                    "static_id": entity_data.static_id,
                    "base_value": entity_data.base_value,
                })
                new_db_entity_any = await create_entity(session, db_model_for_entity, data_to_create)
                if new_db_entity_any and isinstance(new_db_entity_any, Item):
                    current_item_db: Item = new_db_entity_any # Safe cast
                    saved_entity_ids["item"].append(current_item_db.id)
                    logger.info(f"Saved Item (Pass 2): {entity_data.name_i18n.get('en', 'Unknown Item')} with ID {current_item_db.id}")
                elif not new_db_entity_any:
                     logger.error(f"Failed to create Item DB entry for static_id: {entity_data.static_id}")

            elif entity_type_lower == "relationship" and isinstance(entity_data, ParsedRelationshipData):
                    # Relationship logic remains largely the same, just uses db_model_for_entity if needed for create_entity
                    e1_info = static_id_to_db_id_map.get(entity_data.entity1_static_id)
                    e2_info = static_id_to_db_id_map.get(entity_data.entity2_static_id)

                    final_e1_id: Optional[int] = None
                    final_e1_type: Optional[RelationshipEntityType] = None
                    final_e2_id: Optional[int] = None
                    final_e2_type: Optional[RelationshipEntityType] = None

                    # Resolve Entity 1
                    if e1_info:
                        final_e1_id = e1_info["db_id"]
                        final_e1_type = e1_info["type"]
                    elif entity_data.entity1_type.lower() == "faction":
                        existing_faction = await crud_faction.get_by_static_id(session, guild_id=guild_id, static_id=entity_data.entity1_static_id)
                        if existing_faction:
                            final_e1_id = existing_faction.id
                            final_e1_type = RelationshipEntityType.GENERATED_FACTION
                    elif entity_data.entity1_type.lower() == "npc": # Existing NPC not in this batch
                        existing_npc = await actual_npc_crud.get_by_static_id(session=session, guild_id=guild_id, static_id=entity_data.entity1_static_id)
                        if existing_npc:
                            final_e1_id = existing_npc.id
                            final_e1_type = RelationshipEntityType.GENERATED_NPC

                    # Resolve Entity 2
                    if e2_info:
                        final_e2_id = e2_info["db_id"]
                        final_e2_type = e2_info["type"]
                    elif entity_data.entity2_type.lower() == "faction":
                        existing_faction = await crud_faction.get_by_static_id(session, guild_id=guild_id, static_id=entity_data.entity2_static_id)
                        if existing_faction:
                            final_e2_id = existing_faction.id
                            final_e2_type = RelationshipEntityType.GENERATED_FACTION
                    elif entity_data.entity2_type.lower() == "npc": # Existing NPC not in this batch
                        existing_npc = await actual_npc_crud.get_by_static_id(session=session, guild_id=guild_id, static_id=entity_data.entity2_static_id)
                        if existing_npc:
                            final_e2_id = existing_npc.id
                            final_e2_type = RelationshipEntityType.GENERATED_NPC

                    if final_e1_id is not None and final_e1_type and final_e2_id is not None and final_e2_type:
                        rel_obj_in = {
                            "guild_id": guild_id,
                            "entity1_id": final_e1_id, "entity1_type": final_e1_type,
                            "entity2_id": final_e2_id, "entity2_type": final_e2_type,
                            "relationship_type": entity_data.relationship_type,
                            "value": entity_data.value
                        }
                        existing_rel = await crud_relationship.get_relationship_between_entities(
                            session, guild_id=guild_id,
                            entity1_id=final_e1_id, entity1_type=final_e1_type,
                            entity2_id=final_e2_id, entity2_type=final_e2_type
                        )
                        if existing_rel:
                             logger.info(f"Relationship exists between {final_e1_type.value}:{final_e1_id} and {final_e2_type.value}:{final_e2_id}. Updating type to '{entity_data.relationship_type}' and value from {existing_rel.value} to {entity_data.value}.")
                             existing_rel.value = entity_data.value
                             existing_rel.relationship_type = entity_data.relationship_type
                             session.add(existing_rel)
                        else:
                             await crud_relationship.create(session, obj_in=rel_obj_in)
                             logger.info(f"Saved Relationship: {entity_data.relationship_type} between {final_e1_type.value}:{final_e1_id} and {final_e2_type.value}:{final_e2_id}, value {entity_data.value}")
                    else:
                        logger.warning(f"Could not resolve one or both entities for relationship: {entity_data.entity1_static_id} ({entity_data.entity1_type}) <-> {entity_data.entity2_static_id} ({entity_data.entity2_type}). Skipping.")
            else: # This else corresponds to the if/elif chain for quest, item, relationship
                logger.warning(f"Unsupported entity_type '{entity_type_lower}' encountered during saving of PendingGeneration ID {pending_generation_id}") # Fixed typo entity_type_val -> entity_type_lower

        master_notes_message = (
            f"Successfully saved entities: "
            f"NPC IDs: {saved_entity_ids.get('npc', [])}, "
            f"Quest IDs: {saved_entity_ids.get('quest', [])}, "
            f"Item IDs: {saved_entity_ids.get('item', [])}. "
            # Add relationship count if tracked
            f"Relationships processed (see logs for details)."
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
                from .crud.crud_pending_generation import pending_generation_crud # Local import

                other_pending_count = await pending_generation_crud.count_other_active_pending_for_user(
                    session=session,
                    guild_id=guild_id,
                    user_id=player.id,
                    exclude_pending_generation_id=pending_generation_id,
                    statuses=[ModerationStatus.PENDING_MODERATION, ModerationStatus.VALIDATION_FAILED] # Statuses that keep player waiting
                )

                if other_pending_count == 0:
                    await update_entity(session, player, {"current_status": PlayerStatus.EXPLORING})
                    logger.info(f"Player {player.id} status updated from {PlayerStatus.AWAITING_MODERATION.name} to {PlayerStatus.EXPLORING.name} after generation ID {pending_generation_id} saved, as no other active pending generations were found.")
                else:
                    logger.info(f"Player {player.id} (status: {PlayerStatus.AWAITING_MODERATION.name}) still has {other_pending_count} other active pending generations. Status not changed after saving generation ID {pending_generation_id}.")
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
