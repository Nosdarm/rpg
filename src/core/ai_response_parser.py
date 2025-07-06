import json
import logging
from typing import Union, List, Optional, Dict, Any, TypeVar, Type

# Explicitly import Pydantic's ValidationError to avoid confusion
from pydantic import BaseModel, field_validator, Field, parse_obj_as, ValidationInfo
from pydantic import ValidationError as PydanticNativeValidationError # For catching Pydantic errors

from .rules import get_rule, get_all_rules_for_guild
# from ..config.settings import SUPPORTED_LANGUAGES # Assuming this will be available

logger = logging.getLogger(__name__)

# --- Data Structures ---

class CustomValidationError(BaseModel): # Renamed from ValidationError
    error_type: str  # e.g., "JSONParsingError", "StructuralValidationError", "SemanticValidationError"
    message: str
    details: Optional[List[Dict[str, Any]]] = None # Changed to List[Dict] to match Pydantic's e.errors()
    path: Optional[List[Union[str, int]]] = None


# Base for AI generated entities to allow discriminated union
class BaseGeneratedEntity(BaseModel):
    entity_type: str


class ParsedNpcData(BaseGeneratedEntity):
    entity_type: str = Field("npc", frozen=True)
    static_id: Optional[str] = None # Added for linking relationships
    name_i18n: Dict[str, str]
    description_i18n: Dict[str, str]
    # Example: stats might be a simple dict for now
    stats: Optional[Dict[str, Any]] = None
    # Add other NPC specific fields as expected from AI

    @field_validator('static_id', mode='before')
    @classmethod
    def check_static_id(cls, v):
        if v is not None and (not isinstance(v, str) or not v.strip()):
            raise ValueError("static_id must be a non-empty string if provided.")
        return v

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
    # steps_description_i18n: List[Dict[str, str]] # REMOVED THIS OLD FIELD
    rewards_json: Optional[Dict[str, Any]] = None # e.g. {"xp": 100, "gold": 50, "items": ["item_static_id_1"]}
    # Add other Quest specific fields
    static_id: str # AI should generate this, unique within the response at least
    questline_static_id: Optional[str] = None # Optional: if part of a new questline also being generated
    giver_entity_type: Optional[str] = None # e.g., "npc", "item", "location_interaction"
    giver_entity_static_id: Optional[str] = None # static_id of the NPC/item giving the quest
    min_level: Optional[int] = None
    steps: List["ParsedQuestStepData"] # Changed from steps_description_i18n
    # rewards_json is already present and fine
    ai_metadata_json: Optional[Dict[str, Any]] = None


    @field_validator('title_i18n', 'summary_i18n')
    @classmethod
    def check_i18n_content(cls, v):
        if not v:
            raise ValueError("i18n field cannot be empty")
        if not all(isinstance(lang, str) and isinstance(text, str) for lang, text in v.items()):
            raise ValueError("i18n field must be a dict of str:str")
        return v

    # REMOVED VALIDATOR FOR steps_description_i18n
    # @field_validator('steps_description_i18n')
    # @classmethod
    # def check_steps_i18n_content(cls, v):
    #     if not v: # Steps can be empty for a simple quest
    #         return v
    #     for step_desc in v:
    #         if not isinstance(step_desc, dict) or not all(isinstance(lang, str) and isinstance(text, str) for lang, text in step_desc.items()):
    #             raise ValueError("Each step description must be a dict of str:str")
    #     return v

    @field_validator('static_id', mode="before")
    @classmethod
    def check_static_id(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("static_id must be a non-empty string for ParsedQuestData.")
        return v

    @field_validator('steps')
    @classmethod
    def check_steps_not_empty(cls, v):
        if not v:
            raise ValueError("Quest must have at least one step.")
        return v

class ParsedQuestStepData(BaseModel): # Not inheriting BaseGeneratedEntity as it's part of ParsedQuestData
    # No entity_type needed here as it's nested.
    # If steps could be generated independently, then it would need entity_type.
    title_i18n: Dict[str, str]
    description_i18n: Dict[str, str]
    step_order: int # Added to ensure order is defined by AI
    required_mechanics_json: Optional[Dict[str, Any]] = None
    abstract_goal_json: Optional[Dict[str, Any]] = None
    consequences_json: Optional[Dict[str, Any]] = None

    @field_validator('title_i18n', 'description_i18n')
    @classmethod
    def check_step_i18n_content(cls, v):
        if not v:
            raise ValueError("Step i18n field cannot be empty")
        if not all(isinstance(lang, str) and isinstance(text, str) for lang, text in v.items()):
            raise ValueError("Step i18n field must be a dict of str:str")
        return v

    @field_validator('step_order')
    @classmethod
    def check_step_order_positive(cls, v):
        if not isinstance(v, int) or v < 0: # Allow 0 for first step if desired, or change to v < 1
            raise ValueError("step_order must be a non-negative integer.")
        return v

class ParsedItemData(BaseGeneratedEntity):
    entity_type: str = Field("item", frozen=True)
    static_id: str # AI should generate this, unique within the response at least
    name_i18n: Dict[str, str]
    description_i18n: Dict[str, str]
    item_type: str # e.g., "weapon", "armor", "consumable", "quest_item", "misc"
    properties_json: Optional[Dict[str, Any]] = None
    base_value: Optional[int] = None # Base monetary value

    @field_validator('static_id', mode="before")
    @classmethod
    def check_item_static_id(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("static_id must be a non-empty string for ParsedItemData.")
        return v

    @field_validator('name_i18n', 'description_i18n')
    @classmethod
    def check_i18n_content(cls, v, info: ValidationInfo): # Added ValidationInfo
        if not isinstance(v, dict) or not v: # Check if dict and not empty
            raise ValueError(f"{info.field_name} must be a non-empty dictionary.")
        if not all(isinstance(lang, str) and isinstance(text, str) for lang, text in v.items()):
            raise ValueError(f"{info.field_name} must be a dict of str:str.")
        # TODO: Add check for required languages (e.g., 'en' and guild's main lang)
        return v

    @field_validator('item_type', mode="before")
    @classmethod
    def check_item_type(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("item_type must be a non-empty string.")
        # TODO: Validate against a predefined list of item types if necessary
        return v.lower()

    @field_validator('base_value')
    @classmethod
    def check_base_value(cls, v):
        if v is not None and (not isinstance(v, int) or v < 0):
            raise ValueError("base_value must be a non-negative integer if provided.")
        return v

# Structure for generated inventory items if AI provides them directly for a trader
class GeneratedInventoryItemEntry(BaseModel):
    item_static_id: str
    quantity_min: int = 1
    quantity_max: int = 1
    chance_to_appear: float = 1.0

    @field_validator('item_static_id', mode="before")
    @classmethod
    def check_item_static_id_non_empty(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("item_static_id must be a non-empty string.")
        return v

    @field_validator('quantity_min', 'quantity_max')
    @classmethod
    def check_positive_quantity(cls, v):
        if not isinstance(v, int) or v < 1:
            raise ValueError("Quantity must be a positive integer.")
        return v

    @field_validator('chance_to_appear')
    @classmethod
    def check_chance(cls, v):
        if not isinstance(v, float) or not (0.0 <= v <= 1.0):
            raise ValueError("Chance to appear must be a float between 0.0 and 1.0.")
        return v

class ParsedNpcTraderData(ParsedNpcData): # Inherits from ParsedNpcData
    entity_type: str = Field("npc_trader", frozen=True)
    role_i18n: Optional[Dict[str, str]] = None # e.g. {"en": "Blacksmith", "ru": "Кузнец"}
    inventory_template_key: Optional[str] = None # Key for RuleConfig: economy:npc_inventory_templates:<key>
    # If AI generates specific items instead of using a template:
    generated_inventory_items: Optional[List[GeneratedInventoryItemEntry]] = None

    @field_validator('role_i18n', mode="before")
    @classmethod
    def check_role_i18n(cls, v, info: ValidationInfo):
        if v is None: # Optional field
            return v
        if not isinstance(v, dict) or not v:
            raise ValueError(f"{info.field_name} must be a non-empty dictionary if provided.")
        if not all(isinstance(lang, str) and isinstance(text, str) for lang, text in v.items()):
            raise ValueError(f"{info.field_name} must be a dict of str:str.")
        return v

    @field_validator('inventory_template_key', mode="before")
    @classmethod
    def check_inventory_template_key(cls, v):
        if v is not None and (not isinstance(v, str) or not v.strip()):
            raise ValueError("inventory_template_key must be a non-empty string if provided.")
        return v

    @field_validator('generated_inventory_items', mode="before")
    @classmethod
    def check_generated_inventory(cls, v):
        if v is not None and (not isinstance(v, list) or not all(isinstance(i, dict) for i in v)):
            raise ValueError("generated_inventory_items must be a list of item entry objects if provided.")
        # Pydantic will validate individual GeneratedInventoryItemEntry objects
        return v

# ... (other imports remain the same)

# --- Data Structures ---

# ... (CustomValidationError and BaseGeneratedEntity remain the same)

# ... (ParsedNpcData, ParsedQuestData, ParsedItemData remain largely the same,
#      but ensure their field_validators are compatible with Pydantic V2 if not already,
#      e.g. using ValidationInfo for context if needed, though current ones seem simple enough)

class ParsedFactionData(BaseGeneratedEntity):
    entity_type: str = Field("faction", frozen=True)
    static_id: str # AI should generate this, unique within the response at least
    name_i18n: Dict[str, str]
    description_i18n: Dict[str, str]
    ideology_i18n: Optional[Dict[str, str]] = None
    leader_npc_static_id: Optional[str] = None # Static ID of an NPC (could be generated in same batch)
    resources_json: Optional[Dict[str, Any]] = None
    ai_metadata_json: Optional[Dict[str, Any]] = None

    @field_validator('name_i18n', 'description_i18n', 'ideology_i18n', mode="before")
    @classmethod
    def check_i18n_fields(cls, v, info: ValidationInfo):
        if v is None and info.field_name == 'ideology_i18n': # Ideology can be optional
            return v
        if not isinstance(v, dict) or not v:
            raise ValueError(f"{info.field_name} must be a non-empty dictionary.")
        if not all(isinstance(lang, str) and isinstance(text, str) for lang, text in v.items()):
            raise ValueError(f"{info.field_name} must be a dict of str:str.")
        # TODO: Add check for required languages (e.g., 'en' and guild's main lang)
        return v

    @field_validator('static_id', mode="before")
    @classmethod
    def check_static_id(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("static_id must be a non-empty string.")
        # Consider adding regex for static_id format if needed
        return v

class ParsedRelationshipData(BaseGeneratedEntity):
    entity_type: str = Field("relationship", frozen=True)
    # Using static_ids for entities as DB IDs are not known at generation time
    entity1_static_id: str
    entity1_type: str # e.g., "faction", "npc", "player_default"
    entity2_static_id: str
    entity2_type: str
    relationship_type: str # e.g., "faction_standing", "personal_feeling_npc_faction"
    value: int # Numerical value of the relationship

    @field_validator('entity1_static_id', 'entity1_type', 'entity2_static_id', 'entity2_type', 'relationship_type', mode="before")
    @classmethod
    def check_non_empty_strings(cls, v, info: ValidationInfo):
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string.")
        return v

    @field_validator('entity1_type', 'entity2_type', mode="before")
    @classmethod
    def check_entity_types(cls, v, info: ValidationInfo):
        # Basic check, can be expanded with known RelationshipEntityType values
        # from src.models.enums import RelationshipEntityType
        # known_types = [ret.value for ret in RelationshipEntityType]
        # if v not in known_types:
        #     raise ValueError(f"Invalid {info.field_name}: '{v}'. Must be one of {known_types}")
        return v.lower()


class ParsedLocationData(BaseGeneratedEntity):
    entity_type: str = Field("location", frozen=True)
    name_i18n: Dict[str, str]
    descriptions_i18n: Dict[str, str]
    location_type: str # Должен соответствовать LocationType enum
    coordinates_json: Optional[Dict[str, Any]] = None
    generated_details_json: Optional[Dict[str, Any]] = None
    # Поле для описания связей с соседями, которое AI может вернуть
    # Пример: [{"static_id_or_name": "village_square", "connection_description_i18n": {"en": "a dusty road", "ru": "пыльная дорога"}}]
    potential_neighbors: Optional[List[Dict[str, Any]]] = None

    @field_validator("name_i18n", "descriptions_i18n", mode="before") # mode="before" is fine for simple checks
    @classmethod
    def check_i18n_languages(cls, value, info: ValidationInfo): # Added ValidationInfo for Pydantic 2.x style
        # This is a simplified check. Real check should use guild's languages from RuleConfig
        # or a global list of supported languages.
        # For now, ensure it's a dict and has at least 'en'.
        if not isinstance(value, dict):
            raise ValueError("i18n field must be a dictionary.")
        if not value: # Cannot be empty
             raise ValueError("i18n field dictionary cannot be empty.")
        if "en" not in value: # Example: ensure English is always present
            logger.warning(f"i18n field {info.field_name} is missing 'en' key: {value}")
            # Depending on strictness, this could be an error:
            # raise ValueError(f"i18n field {info.field_name} must contain 'en' translation.")
        return value

    @field_validator("location_type", mode="before")
    @classmethod
    def validate_location_type(cls, value, info: ValidationInfo):
        # TODO: Validate against actual LocationType enum members from src.models.location
        # from src.models.location import LocationType
        # if value not in [lt.value for lt in LocationType]:
        #     raise ValueError(f"Invalid location_type: {value}. Must be one of {[lt.value for lt in LocationType]}")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("location_type must be a non-empty string.")
        return value.upper() # Example: Store as uppercase


# Union of all possible generated entity types for Pydantic to discriminate
GeneratedEntity = Union[
    ParsedNpcData,
    ParsedNpcTraderData, # Added new trader type
    ParsedQuestData,
    ParsedItemData,
    ParsedLocationData,
    ParsedFactionData,
    ParsedRelationshipData
]


class ParsedAiData(BaseModel):
    # Using a list of discriminated union types
    generated_entities: List[GeneratedEntity]
    raw_ai_output: str
    parsing_metadata: Optional[Dict[str, Any]] = None


# --- Helper Functions ---

T = TypeVar('T')

def _parse_json_from_text(raw_text: str) -> Union[Any, CustomValidationError]:
    """Parses JSON from text, returning data or CustomValidationError."""
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error(f"JSONParsingError: {e}", exc_info=True)
        return CustomValidationError(error_type="JSONParsingError", message=str(e))


def _validate_overall_structure(
    json_data: Any,
    guild_id: int # Added for context, though not directly used in this Pydantic validation
) -> Union[List[GeneratedEntity], CustomValidationError]: # Corrected return type
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
             return CustomValidationError( # Renamed
                error_type="StructuralValidationError",
                message="Expected a list of entities from AI.",
                details=[{"received_type": str(type(json_data))}] # Corrected to List[Dict]
            )

        # This will attempt to parse each item in the list as one of the GeneratedEntity types
        # Pydantic's discriminated union will use the 'entity_type' field.
        validated_entities: List[GeneratedEntity] = []
        potential_errors = []
        for i, entity_data in enumerate(json_data):
            if not isinstance(entity_data, dict):
                potential_errors.append(CustomValidationError( # Renamed
                    error_type="StructuralValidationError",
                    message=f"Entity at index {i} is not a dictionary.",
                    path=[i]
                ))
                continue
            try:
                # Pydantic will use `entity_type` to pick the correct model from the Union
                validated_entity = parse_obj_as(GeneratedEntity, entity_data) # type: ignore[arg-type] # Pyright struggles with Union here
                validated_entities.append(validated_entity)
            except PydanticNativeValidationError as e: # Use aliased Pydantic error
                potential_errors.append(CustomValidationError( # Renamed
                    error_type="StructuralValidationError",
                    message=f"Validation failed for entity at index {i}.",
                    details=[dict(err) for err in e.errors()], # Explicitly convert ErrorDetails to dict
                    path=[i]
                ))

        if potential_errors:
            # For now, returning the first structural error found within entities
            # A more sophisticated approach might bundle these.
            return potential_errors[0]

        # If all entities validated, return them. The main function will wrap this in ParsedAiData.
        return validated_entities # Returning List[GeneratedEntity]

    except PydanticNativeValidationError as e: # Use aliased Pydantic error
        logger.error(f"StructuralValidationError: {e}", exc_info=True)
        return CustomValidationError( # Renamed
            error_type="StructuralValidationError",
            message="Overall Pydantic validation failed for AI response structure.",
            details=[dict(err) for err in e.errors()] # Explicitly convert ErrorDetails to dict
        )
    except Exception as e: # Catch any other unexpected errors during validation
        logger.error(f"Unexpected error during structural validation: {e}", exc_info=True)
        return CustomValidationError(error_type="InternalParserError", message=f"Unexpected validation error: {str(e)}") # Renamed


def _perform_semantic_validation(
    validated_entities: List[GeneratedEntity],
    guild_id: int
) -> List[CustomValidationError]: # Renamed return type
    """Performs semantic validation based on guild rules and game logic."""
    semantic_errors: List[CustomValidationError] = [] # Renamed

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
                    semantic_errors.append(CustomValidationError( # Renamed
                        error_type="SemanticValidationError",
                        message=f"Entity {entity_idx} ('{getattr(entity, 'entity_type', 'unknown')}') missing required languages {missing} in '{field_name}'.",
                        path=[entity_idx, field_name]
                    ))

            if isinstance(entity, (ParsedNpcData, ParsedItemData, ParsedFactionData, ParsedNpcTraderData)): # Added ParsedNpcTraderData
                check_i18n_dict(entity.name_i18n, "name_i18n", i)
                check_i18n_dict(entity.description_i18n, "description_i18n", i)
                if isinstance(entity, ParsedFactionData):
                    check_i18n_dict(entity.ideology_i18n, "ideology_i18n", i)
                if isinstance(entity, ParsedNpcTraderData):
                    check_i18n_dict(entity.role_i18n, "role_i18n", i)
            elif isinstance(entity, ParsedLocationData):
                check_i18n_dict(entity.name_i18n, "name_i18n", i)
                check_i18n_dict(entity.descriptions_i18n, "descriptions_i18n", i)
            elif isinstance(entity, ParsedQuestData):
                check_i18n_dict(entity.title_i18n, "title_i18n", i)
                check_i18n_dict(entity.summary_i18n, "summary_i18n", i)
                if entity.steps: # Changed from steps_description_i18n
                    for step_idx, step_data in enumerate(entity.steps):
                        check_i18n_dict(step_data.title_i18n, f"steps[{step_idx}].title_i18n", i)
                        check_i18n_dict(step_data.description_i18n, f"steps[{step_idx}].description_i18n", i)
            elif isinstance(entity, ParsedRelationshipData):
                # Relationships typically don't have direct i18n fields in ParsedRelationshipData
                # Their meaning is derived from types and values, descriptions come from related entities.
                # Basic validation for relationship values if needed:
                if not (-1000 <= entity.value <= 1000): # Example range
                    semantic_errors.append(CustomValidationError(
                        error_type="SemanticValidationError",
                        message=f"Entity {i} ('relationship') has value {entity.value} outside expected range.",
                        path=[i, "value"]
                    ))
                # Check if entity types are known/valid (could use RelationshipEntityType enum)
                # For now, type checked in Pydantic model validator for non-empty string.

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
        semantic_errors.append(CustomValidationError( # Renamed
            error_type="InternalParserError",
            message=f"Unexpected error during semantic validation: {str(e)}"
        ))
    return semantic_errors


# --- Main API Function ---

async def parse_and_validate_ai_response(
    raw_ai_output_text: str,
    guild_id: int
) -> Union[ParsedAiData, CustomValidationError]: # Renamed return type
    """
    Parses and validates AI-generated text output.
    Returns ParsedAiData on success, or CustomValidationError on failure.
    """
    # 1. Parse JSON from raw text
    parsed_json = _parse_json_from_text(raw_ai_output_text)
    if isinstance(parsed_json, CustomValidationError): # Corrected to CustomValidationError
        return parsed_json

    # 2. Validate overall structure and individual entity structures using Pydantic
    # _validate_overall_structure expects the list of entities, not the full ParsedAiData structure yet.
    # Let's assume the AI output (parsed_json) IS the list of entities.
    validated_entities_or_error = _validate_overall_structure(parsed_json, guild_id) # Renamed var
    if isinstance(validated_entities_or_error, CustomValidationError): # Renamed class
        return validated_entities_or_error

    # Ensure validated_entities_or_error is List[GeneratedEntity] for type safety
    # This assignment is safe due to the check above.
    validated_entities: List[GeneratedEntity] = validated_entities_or_error

    if not (isinstance(validated_entities, list) and \
            all(isinstance(e, BaseGeneratedEntity) for e in validated_entities)):
        logger.error(f"Structural validation returned unexpected type: {type(validated_entities)}")
        return CustomValidationError( # Renamed
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
