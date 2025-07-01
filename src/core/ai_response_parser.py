import json
import logging
from typing import Union, List, Optional, Dict, Any, TypeVar, Type
from pydantic import BaseModel, ValidationError as PydanticValidationError, field_validator, Field

from src.core.rules import get_rule, get_all_rules_for_guild
# from src.config.settings import SUPPORTED_LANGUAGES # Assuming this will be available

logger = logging.getLogger(__name__)

# --- Data Structures ---

class ValidationError(BaseModel):
    error_type: str  # e.g., "JSONParsingError", "StructuralValidationError", "SemanticValidationError"
    message: str
    details: Optional[Dict[str, Any]] = None
    path: Optional[List[Union[str, int]]] = None


# Base for AI generated entities to allow discriminated union
class BaseGeneratedEntity(BaseModel):
    entity_type: str


class ParsedNpcData(BaseGeneratedEntity):
    entity_type: str = Field("npc", frozen=True)
    name_i18n: Dict[str, str]
    description_i18n: Dict[str, str]
    # Example: stats might be a simple dict for now
    stats: Optional[Dict[str, Any]] = None
    # Add other NPC specific fields as expected from AI

    @field_validator('name_i18n', 'description_i18n')
    @classmethod
    def check_i18n_content(cls, v):
        if not v:
            raise ValueError("i18n field cannot be empty")
        if not all(isinstance(lang, str) and isinstance(text, str) for lang, text in v.items()):
            raise ValueError("i18n field must be a dict of str:str")
        return v


class ParsedQuestData(BaseGeneratedEntity):
    entity_type: str = Field("quest", frozen=True)
    title_i18n: Dict[str, str]
    summary_i18n: Dict[str, str]
    steps_description_i18n: List[Dict[str, str]] # Each step is a dict of lang:text
    rewards_json: Optional[Dict[str, Any]] = None # e.g. {"xp": 100, "gold": 50, "items": ["item_static_id_1"]}
    # Add other Quest specific fields

    @field_validator('title_i18n', 'summary_i18n')
    @classmethod
    def check_i18n_content(cls, v):
        if not v:
            raise ValueError("i18n field cannot be empty")
        if not all(isinstance(lang, str) and isinstance(text, str) for lang, text in v.items()):
            raise ValueError("i18n field must be a dict of str:str")
        return v

    @field_validator('steps_description_i18n')
    @classmethod
    def check_steps_i18n_content(cls, v):
        if not v: # Steps can be empty for a simple quest
            return v
        for step_desc in v:
            if not isinstance(step_desc, dict) or not all(isinstance(lang, str) and isinstance(text, str) for lang, text in step_desc.items()):
                raise ValueError("Each step description must be a dict of str:str")
        return v


class ParsedItemData(BaseGeneratedEntity):
    entity_type: str = Field("item", frozen=True)
    name_i18n: Dict[str, str]
    description_i18n: Dict[str, str]
    item_type: str # e.g., "weapon", "armor", "consumable"
    properties_json: Optional[Dict[str, Any]] = None
    # Add other Item specific fields

    @field_validator('name_i18n', 'description_i18n')
    @classmethod
    def check_i18n_content(cls, v):
        if not v:
            raise ValueError("i18n field cannot be empty")
        if not all(isinstance(lang, str) and isinstance(text, str) for lang, text in v.items()):
            raise ValueError("i18n field must be a dict of str:str")
        return v

# Union of all possible generated entity types for Pydantic to discriminate
GeneratedEntity = Union[ParsedNpcData, ParsedQuestData, ParsedItemData]


class ParsedAiData(BaseModel):
    # Using a list of discriminated union types
    generated_entities: List[GeneratedEntity]
    raw_ai_output: str
    parsing_metadata: Optional[Dict[str, Any]] = None


# --- Helper Functions ---

T = TypeVar('T')

def _parse_json_from_text(raw_text: str) -> Union[Any, ValidationError]:
    """Parses JSON from text, returning data or ValidationError."""
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error(f"JSONParsingError: {e}", exc_info=True)
        return ValidationError(error_type="JSONParsingError", message=str(e))


def _validate_overall_structure(
    json_data: Any,
    guild_id: int # Added for context, though not directly used in this Pydantic validation
) -> Union[ParsedAiData, ValidationError]:
    """Validates the JSON data against the ParsedAiData Pydantic model."""
    try:
        # We expect the AI to return a structure that matches ParsedAiData,
        # typically a dictionary like:
        # {
        #   "generated_entities": [
        #     {"entity_type": "npc", "name_i18n": ...},
        #     {"entity_type": "quest", "title_i18n": ...}
        #   ],
        #   "raw_ai_output": "...", // This will be added by our parser function
        #   "parsing_metadata": {...} // Also added by our parser
        # }
        # So, the actual AI output is expected to be the content for "generated_entities".
        # The `parse_and_validate_ai_response` function will construct the full ParsedAiData object.
        # This helper should validate the part that AI directly provides, i.e., the list of entities.

        # Let's assume `json_data` is the list of entities here.
        if not isinstance(json_data, list):
             return ValidationError(
                error_type="StructuralValidationError",
                message="Expected a list of entities from AI.",
                details={"received_type": str(type(json_data))}
            )

        # This will attempt to parse each item in the list as one of the GeneratedEntity types
        # Pydantic's discriminated union will use the 'entity_type' field.
        validated_entities: List[GeneratedEntity] = []
        potential_errors = []
        for i, entity_data in enumerate(json_data):
            if not isinstance(entity_data, dict):
                potential_errors.append(ValidationError(
                    error_type="StructuralValidationError",
                    message=f"Entity at index {i} is not a dictionary.",
                    path=[i]
                ))
                continue
            try:
                # Pydantic will use `entity_type` to pick the correct model from the Union
                validated_entity = GeneratedEntity(**entity_data)
                validated_entities.append(validated_entity)
            except PydanticValidationError as e:
                potential_errors.append(ValidationError(
                    error_type="StructuralValidationError",
                    message=f"Validation failed for entity at index {i}.",
                    details=e.errors(),
                    path=[i]
                ))

        if potential_errors:
            # For now, returning the first structural error found within entities
            # A more sophisticated approach might bundle these.
            return potential_errors[0]

        # If all entities validated, return them. The main function will wrap this in ParsedAiData.
        return validated_entities # Returning List[GeneratedEntity]

    except PydanticValidationError as e: # Catch errors from validating ParsedAiData itself if we change the input
        logger.error(f"StructuralValidationError: {e}", exc_info=True)
        return ValidationError(
            error_type="StructuralValidationError",
            message="Overall Pydantic validation failed for AI response structure.",
            details=e.errors()
        )
    except Exception as e: # Catch any other unexpected errors during validation
        logger.error(f"Unexpected error during structural validation: {e}", exc_info=True)
        return ValidationError(error_type="InternalParserError", message=f"Unexpected validation error: {str(e)}")


def _perform_semantic_validation(
    validated_entities: List[GeneratedEntity],
    guild_id: int
) -> List[ValidationError]:
    """Performs semantic validation based on guild rules and game logic."""
    semantic_errors: List[ValidationError] = []

    try:
        # guild_rules = get_all_rules_for_guild(guild_id) # This is sync
        # main_guild_language = get_rule(guild_id, "guild_main_language", default_value="en") # This is sync

        # TODO: Fetch SUPPORTED_LANGUAGES from config settings. For now, assume:
        supported_languages_config = ["en", "ru"]
        # Effective required languages could be main_guild_language + 'en' (if different)
        # required_languages = set([main_guild_language, "en"]) & set(supported_languages_config)
        # For now, let's assume a simpler check against a fixed list or just the main lang
        # This needs to be refined based on actual settings structure.
        # For MVP, let's assume we need at least the guild's main language if specified, else 'en'.

        # Example rule:
        # default_max_hp = get_rule(guild_id, "npc_default_max_hp", default_value=100)

        for i, entity in enumerate(validated_entities):
            # --- I18n Field Language Presence Validation ---
            # This should be more robust, checking against actual guild language settings
            # For now, a simple check for 'en' might be a placeholder
            required_langs_for_entity = {"en"} # Placeholder: should use guild's main language

            # Helper to check i18n dicts
            def check_i18n_dict(i18n_dict: Optional[Dict[str, str]], field_name: str, entity_idx: int):
                if i18n_dict is None: return # Optional fields might be None
                present_langs = set(i18n_dict.keys())
                missing = required_langs_for_entity - present_langs
                if missing:
                    semantic_errors.append(ValidationError(
                        error_type="SemanticValidationError",
                        message=f"Entity {entity_idx} ('{getattr(entity, 'entity_type', 'unknown')}') missing required languages {missing} in '{field_name}'.",
                        path=[entity_idx, field_name]
                    ))

            if isinstance(entity, (ParsedNpcData, ParsedItemData)):
                check_i18n_dict(entity.name_i18n, "name_i18n", i)
                check_i18n_dict(entity.description_i18n, "description_i18n", i)
            elif isinstance(entity, ParsedQuestData):
                check_i18n_dict(entity.title_i18n, "title_i18n", i)
                check_i18n_dict(entity.summary_i18n, "summary_i18n", i)
                if entity.steps_description_i18n:
                    for step_idx, step_desc_i18n in enumerate(entity.steps_description_i18n):
                        check_i18n_dict(step_desc_i18n, f"steps_description_i18n[{step_idx}]", i)

            # --- Other Semantic Validations ---
            # Example: Check NPC stats against RuleConfig (conceptual)
            # if isinstance(entity, ParsedNpcData) and entity.stats:
            #     if entity.stats.get("hp", 0) > default_max_hp:
            #         semantic_errors.append(ValidationError(
            #             error_type="SemanticValidationError",
            #             message=f"NPC HP {entity.stats.get('hp')} exceeds default max {default_max_hp}.",
            #             path=[i, "stats", "hp"]
            #         ))
            # Add more complex semantic checks here based on RuleConfig and entity type.
            # E.g., quest structure, item properties vs item type, etc.

    except Exception as e:
        logger.error(f"Error during semantic validation: {e}", exc_info=True)
        semantic_errors.append(ValidationError(
            error_type="InternalParserError",
            message=f"Unexpected error during semantic validation: {str(e)}"
        ))
    return semantic_errors


# --- Main API Function ---

async def parse_and_validate_ai_response(
    raw_ai_output_text: str,
    guild_id: int
) -> Union[ParsedAiData, ValidationError]:
    """
    Parses and validates AI-generated text output.
    Returns ParsedAiData on success, or ValidationError on failure.
    """
    # 1. Parse JSON from raw text
    parsed_json = _parse_json_from_text(raw_ai_output_text)
    if isinstance(parsed_json, ValidationError):
        return parsed_json

    # 2. Validate overall structure and individual entity structures using Pydantic
    # _validate_overall_structure expects the list of entities, not the full ParsedAiData structure yet.
    # Let's assume the AI output (parsed_json) IS the list of entities.
    validated_entities = _validate_overall_structure(parsed_json, guild_id)
    if isinstance(validated_entities, ValidationError):
        return validated_entities

    # Ensure validated_entities is List[GeneratedEntity] for type safety
    if not (isinstance(validated_entities, list) and \
            all(isinstance(e, BaseGeneratedEntity) for e in validated_entities)):
        logger.error(f"Structural validation returned unexpected type: {type(validated_entities)}")
        return ValidationError(
            error_type="InternalParserError",
            message="Structural validation did not return the expected list of entities."
        )

    # 3. Perform semantic validation on the structurally valid entities
    # Note: get_rule and get_all_rules_for_guild are synchronous based on current AGENTS.md log.
    # If they become async, this part (and the function signature) needs `await`.
    semantic_errors = _perform_semantic_validation(validated_entities, guild_id)
    if semantic_errors:
        # For now, return the first semantic error.
        # Future improvement: bundle multiple errors if necessary.
        return semantic_errors[0]

    # 4. If all validations pass, construct and return ParsedAiData
    # The raw_ai_output_text is added here.
    successful_data = ParsedAiData(
        generated_entities=validated_entities,
        raw_ai_output=raw_ai_output_text,
        parsing_metadata={"guild_id": guild_id} # Example metadata
    )

    return successful_data

# Example Usage (for testing purposes, not part of the module's API)
# async def main_test():
#     sample_npc_output_ok = """
#     [
#         {
#             "entity_type": "npc",
#             "name_i18n": {"en": "Old Man Willow", "ru": "Старик Ива"},
#             "description_i18n": {"en": "A wise old tree.", "ru": "Мудрое старое дерево."},
#             "stats": {"hp": 50, "mana": 0}
#         }
#     ]
#     """
#     sample_quest_output_bad_i18n = """
#     [
#         {
#             "entity_type": "quest",
#             "title_i18n": {"en": "The Lost Artifact"},
#             "summary_i18n": {"en": "Find the hidden artifact."},
#             "steps_description_i18n": [{"en": "Go to the cave."}],
#             "rewards_json": {"xp": 100}
#         }
#     ]
#     """ # Missing 'ru' for example if required by semantic check

#     print("--- Test OK NPC ---")
#     result_ok = await parse_and_validate_ai_response(sample_npc_output_ok, guild_id=1)
#     if isinstance(result_ok, ParsedAiData):
#         print("OK NPC Parsed successfully:", result_ok.model_dump_json(indent=2))
#     else:
#         print("OK NPC Error:", result_ok.model_dump_json(indent=2))

#     print("\n--- Test Bad I18N Quest ---")
#     # This test's success depends on how _perform_semantic_validation implements language checks
#     # For now, with placeholder {"en"} as required, it might pass if 'en' is present.
#     # To make it fail, _perform_semantic_validation needs to require 'ru' for guild_id=1 (example)
#     result_bad_i18n = await parse_and_validate_ai_response(sample_quest_output_bad_i18n, guild_id=1)
#     if isinstance(result_bad_i18n, ParsedAiData):
#         print("Bad I18N Quest Parsed successfully (unexpected for strict check):", result_bad_i18n.model_dump_json(indent=2))
#     else:
#         print("Bad I18N Quest Error:", result_bad_i18n.model_dump_json(indent=2))

# if __name__ == "__main__":
#     import asyncio
#     asyncio.run(main_test())
