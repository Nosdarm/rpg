import json
import logging
from typing import Union, List, Optional, Dict, Any, TypeVar, Type

# Explicitly import Pydantic's ValidationError to avoid confusion
from pydantic import BaseModel, field_validator, model_validator, Field, parse_obj_as, ValidationInfo
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
    static_id: Optional[str] = None # Remains optional for base NPC
    name_i18n: Dict[str, str]
    description_i18n: Dict[str, str]
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
    def check_i18n_content(cls, v, info: ValidationInfo): # Added info
        if not v:
            raise ValueError(f"{info.field_name} cannot be empty")
        if not all(isinstance(lang, str) and isinstance(text, str) for lang, text in v.items()):
            raise ValueError(f"{info.field_name} must be a dict of str:str")
        return v


class ParsedQuestData(BaseGeneratedEntity):
    entity_type: str = Field("quest", frozen=True)
    title_i18n: Dict[str, str]
    summary_i18n: Dict[str, str]
    rewards_json: Optional[Dict[str, Any]] = None
    static_id: str
    questline_static_id: Optional[str] = None
    giver_entity_type: Optional[str] = None
    giver_entity_static_id: Optional[str] = None
    min_level: Optional[int] = None
    steps: List["ParsedQuestStepData"]
    ai_metadata_json: Optional[Dict[str, Any]] = None

    @field_validator('title_i18n', 'summary_i18n')
    @classmethod
    def check_quest_i18n_content(cls, v, info: ValidationInfo): # Added info
        if not v:
            raise ValueError(f"{info.field_name} cannot be empty")
        if not all(isinstance(lang, str) and isinstance(text, str) for lang, text in v.items()):
            raise ValueError(f"{info.field_name} must be a dict of str:str")
        return v

    @field_validator('static_id', mode="before")
    @classmethod
    def check_quest_static_id(cls, v): # Renamed for clarity
        if not isinstance(v, str) or not v.strip():
            raise ValueError("static_id must be a non-empty string for ParsedQuestData.")
        return v

    @field_validator('steps')
    @classmethod
    def check_steps_not_empty(cls, v):
        if not v:
            raise ValueError("Quest must have at least one step.")
        return v

class ParsedQuestStepData(BaseModel):
    title_i18n: Dict[str, str]
    description_i18n: Dict[str, str]
    step_order: int
    required_mechanics_json: Optional[Dict[str, Any]] = None
    abstract_goal_json: Optional[Dict[str, Any]] = None
    consequences_json: Optional[Dict[str, Any]] = None

    @field_validator('title_i18n', 'description_i18n')
    @classmethod
    def check_step_i18n_content(cls, v, info: ValidationInfo): # Added info
        if not v:
            raise ValueError(f"{info.field_name} cannot be empty")
        if not all(isinstance(lang, str) and isinstance(text, str) for lang, text in v.items()):
            raise ValueError(f"{info.field_name} must be a dict of str:str")
        return v

    @field_validator('step_order')
    @classmethod
    def check_step_order_positive(cls, v):
        if not isinstance(v, int) or v < 0:
            raise ValueError("step_order must be a non-negative integer.")
        return v

class ParsedItemData(BaseGeneratedEntity):
    entity_type: str = Field("item", frozen=True)
    static_id: str # Made mandatory
    name_i18n: Dict[str, str]
    description_i18n: Dict[str, str]
    item_type: str
    properties_json: Optional[Dict[str, Any]] = None
    base_value: Optional[int] = None

    @field_validator('static_id', mode="before")
    @classmethod
    def check_item_static_id(cls, v): # Specific validator for item's static_id
        if not isinstance(v, str) or not v.strip():
            raise ValueError("static_id must be a non-empty string for ParsedItemData.")
        return v

    @field_validator('name_i18n', 'description_i18n')
    @classmethod
    def check_item_i18n_content(cls, v, info: ValidationInfo): # Added info, specific name
        if not isinstance(v, dict) or not v:
            raise ValueError(f"{info.field_name} must be a non-empty dictionary.")
        if not all(isinstance(lang, str) and isinstance(text, str) for lang, text in v.items()):
            raise ValueError(f"{info.field_name} must be a dict of str:str.")
        return v

    @field_validator('item_type', mode="before")
    @classmethod
    def check_item_type(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("item_type must be a non-empty string.")
        return v.lower() # Keep .lower()

    @field_validator('base_value')
    @classmethod
    def check_base_value(cls, v):
        if v is not None and (not isinstance(v, int) or v < 0):
            raise ValueError("base_value must be a non-negative integer if provided.")
        return v

# New model for generated inventory items
class GeneratedInventoryItemEntry(BaseModel):
    item_static_id: str
    quantity_min: int = Field(default=1, ge=1)
    quantity_max: int = Field(default=1, ge=1)
    chance_to_appear: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator('item_static_id', mode="before")
    @classmethod
    def check_item_static_id_non_empty(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("item_static_id must be a non-empty string.")
        return v

    @model_validator(mode='after') # Use model_validator for cross-field validation
    def check_min_max_quantity(self):
        if self.quantity_max < self.quantity_min:
            raise ValueError("quantity_max cannot be less than quantity_min.")
        return self

# New model for NPC Traders
class ParsedNpcTraderData(ParsedNpcData): # Inherits from ParsedNpcData
    entity_type: str = Field("npc_trader", frozen=True) # Override entity_type
    role_i18n: Optional[Dict[str, str]] = None
    inventory_template_key: Optional[str] = None
    generated_inventory_items: Optional[List[GeneratedInventoryItemEntry]] = None

    @field_validator('role_i18n', mode="before")
    @classmethod
    def check_role_i18n(cls, v, info: ValidationInfo):
        if v is None:
            return v
        if not isinstance(v, dict) or not v: # Check if dict and not empty
            raise ValueError(f"{info.field_name} must be a non-empty dictionary if provided.")
        if not all(isinstance(lang, str) and isinstance(text, str) for lang, text in v.items()):
            raise ValueError(f"{info.field_name} must be a dict of str:str if provided.")
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
        if v is not None:
            if not isinstance(v, list):
                 raise ValueError("generated_inventory_items must be a list if provided.")
            # Pydantic will validate individual GeneratedInventoryItemEntry objects
        return v


class ParsedFactionData(BaseGeneratedEntity):
    entity_type: str = Field("faction", frozen=True)
    static_id: str
    name_i18n: Dict[str, str]
    description_i18n: Dict[str, str]
    ideology_i18n: Optional[Dict[str, str]] = None
    leader_npc_static_id: Optional[str] = None
    resources_json: Optional[Dict[str, Any]] = None
    ai_metadata_json: Optional[Dict[str, Any]] = None

    @field_validator('name_i18n', 'description_i18n', 'ideology_i18n', mode="before")
    @classmethod
    def check_faction_i18n_fields(cls, v, info: ValidationInfo): # Added info, specific name
        if v is None and info.field_name == 'ideology_i18n':
            return v
        if not isinstance(v, dict) or not v:
            raise ValueError(f"{info.field_name} must be a non-empty dictionary.")
        if not all(isinstance(lang, str) and isinstance(text, str) for lang, text in v.items()):
            raise ValueError(f"{info.field_name} must be a dict of str:str.")
        return v

    @field_validator('static_id', mode="before")
    @classmethod
    def check_faction_static_id(cls, v): # Specific validator
        if not isinstance(v, str) or not v.strip():
            raise ValueError("static_id must be a non-empty string for ParsedFactionData.")
        return v

class ParsedRelationshipData(BaseGeneratedEntity):
    entity_type: str = Field("relationship", frozen=True)
    entity1_static_id: str
    entity1_type: str
    entity2_static_id: str
    entity2_type: str
    relationship_type: str
    value: int

    @field_validator('entity1_static_id', 'entity1_type', 'entity2_static_id', 'entity2_type', 'relationship_type', mode="before")
    @classmethod
    def check_rel_non_empty_strings(cls, v, info: ValidationInfo): # Added info, specific name
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string.")
        return v

    @field_validator('entity1_type', 'entity2_type', mode="before")
    @classmethod
    def check_rel_entity_types(cls, v, info: ValidationInfo): # Added info, specific name
        # Basic check, can be expanded with known RelationshipEntityType values
        return v.lower()


class ParsedLocationData(BaseGeneratedEntity):
    entity_type: str = Field("location", frozen=True)
    name_i18n: Dict[str, str]
    descriptions_i18n: Dict[str, str]
    location_type: str
    coordinates_json: Optional[Dict[str, Any]] = None
    generated_details_json: Optional[Dict[str, Any]] = None
    potential_neighbors: Optional[List[Dict[str, Any]]] = None

    @field_validator("name_i18n", "descriptions_i18n", mode="before")
    @classmethod
    def check_loc_i18n_languages(cls, value, info: ValidationInfo): # Added info, specific name
        if not isinstance(value, dict):
            raise ValueError(f"{info.field_name} must be a dictionary.")
        if not value:
             raise ValueError(f"{info.field_name} dictionary cannot be empty.")
        if "en" not in value:
            logger.warning(f"i18n field {info.field_name} is missing 'en' key: {value}")
        return value

    @field_validator("location_type", mode="before")
    @classmethod
    def validate_loc_location_type(cls, value, info: ValidationInfo): # Added info, specific name
        if not isinstance(value, str) or not value.strip():
            raise ValueError("location_type must be a non-empty string.")
        return value.upper()


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
    generated_entities: List[GeneratedEntity]
    raw_ai_output: str
    parsing_metadata: Optional[Dict[str, Any]] = None


# --- Helper Functions ---

T = TypeVar('T')

def _parse_json_from_text(raw_text: str) -> Union[Any, CustomValidationError]:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error(f"JSONParsingError: {e}", exc_info=True)
        return CustomValidationError(error_type="JSONParsingError", message=str(e))


def _validate_overall_structure(
    json_data: Any,
    guild_id: int
) -> Union[List[GeneratedEntity], CustomValidationError]:
    try:
        if not isinstance(json_data, list):
             return CustomValidationError(
                error_type="StructuralValidationError",
                message="Expected a list of entities from AI.",
                details=[{"received_type": str(type(json_data))}]
            )

        validated_entities: List[GeneratedEntity] = []
        potential_errors = []
        for i, entity_data in enumerate(json_data):
            if not isinstance(entity_data, dict):
                potential_errors.append(CustomValidationError(
                    error_type="StructuralValidationError",
                    message=f"Entity at index {i} is not a dictionary.",
                    path=[i]
                ))
                continue
            try:
                validated_entity = parse_obj_as(GeneratedEntity, entity_data) # type: ignore[arg-type]
                validated_entities.append(validated_entity)
            except PydanticNativeValidationError as e:
                potential_errors.append(CustomValidationError(
                    error_type="StructuralValidationError",
                    message=f"Validation failed for entity at index {i}.",
                    details=[dict(err) for err in e.errors()],
                    path=[i]
                ))

        if potential_errors:
            return potential_errors[0]
        return validated_entities

    except PydanticNativeValidationError as e:
        logger.error(f"StructuralValidationError: {e}", exc_info=True)
        return CustomValidationError(
            error_type="StructuralValidationError",
            message="Overall Pydantic validation failed for AI response structure.",
            details=[dict(err) for err in e.errors()]
        )
    except Exception as e:
        logger.error(f"Unexpected error during structural validation: {e}", exc_info=True)
        return CustomValidationError(error_type="InternalParserError", message=f"Unexpected validation error: {str(e)}")


def _perform_semantic_validation(
    validated_entities: List[GeneratedEntity],
    guild_id: int
) -> List[CustomValidationError]:
    semantic_errors: List[CustomValidationError] = []
    try:
        required_langs_for_entity = {"en"} # Placeholder

        def check_i18n_dict(i18n_dict: Optional[Dict[str, str]], field_name: str, entity_idx: int, entity_type_str: str):
            if i18n_dict is None: return
            present_langs = set(i18n_dict.keys())
            missing = required_langs_for_entity - present_langs
            if missing:
                semantic_errors.append(CustomValidationError(
                    error_type="SemanticValidationError",
                    message=f"Entity {entity_idx} ('{entity_type_str}') missing required languages {missing} in '{field_name}'.",
                    path=[entity_idx, field_name]
                ))

        for i, entity in enumerate(validated_entities):
            entity_type_str = getattr(entity, 'entity_type', 'unknown')
            if isinstance(entity, (ParsedNpcData, ParsedItemData, ParsedFactionData)): # Base check for common models
                check_i18n_dict(entity.name_i18n, "name_i18n", i, entity_type_str)
                check_i18n_dict(entity.description_i18n, "description_i18n", i, entity_type_str)
                if isinstance(entity, ParsedFactionData):
                    check_i18n_dict(entity.ideology_i18n, "ideology_i18n", i, entity_type_str)

            if isinstance(entity, ParsedNpcTraderData): # Specific check for ParsedNpcTraderData
                # name_i18n and description_i18n are covered by ParsedNpcData check above
                check_i18n_dict(entity.role_i18n, "role_i18n", i, entity_type_str)
            elif isinstance(entity, ParsedLocationData):
                check_i18n_dict(entity.name_i18n, "name_i18n", i, entity_type_str)
                check_i18n_dict(entity.descriptions_i18n, "descriptions_i18n", i, entity_type_str)
            elif isinstance(entity, ParsedQuestData):
                check_i18n_dict(entity.title_i18n, "title_i18n", i, entity_type_str)
                check_i18n_dict(entity.summary_i18n, "summary_i18n", i, entity_type_str)
                if entity.steps:
                    for step_idx, step_data in enumerate(entity.steps):
                        check_i18n_dict(step_data.title_i18n, f"steps[{step_idx}].title_i18n", i, entity_type_str)
                        check_i18n_dict(step_data.description_i18n, f"steps[{step_idx}].description_i18n", i, entity_type_str)
            elif isinstance(entity, ParsedRelationshipData):
                if not (-1000 <= entity.value <= 1000):
                    semantic_errors.append(CustomValidationError(
                        error_type="SemanticValidationError",
                        message=f"Entity {i} ('relationship') has value {entity.value} outside expected range.",
                        path=[i, "value"]
                    ))
    except Exception as e:
        logger.error(f"Error during semantic validation: {e}", exc_info=True)
        semantic_errors.append(CustomValidationError(
            error_type="InternalParserError",
            message=f"Unexpected error during semantic validation: {str(e)}"
        ))
    return semantic_errors


# --- Main API Function ---

async def parse_and_validate_ai_response(
    raw_ai_output_text: str,
    guild_id: int
) -> Union[ParsedAiData, CustomValidationError]:
    parsed_json = _parse_json_from_text(raw_ai_output_text)
    if isinstance(parsed_json, CustomValidationError):
        return parsed_json

    validated_entities_or_error = _validate_overall_structure(parsed_json, guild_id)
    if isinstance(validated_entities_or_error, CustomValidationError):
        return validated_entities_or_error

    validated_entities: List[GeneratedEntity] = validated_entities_or_error

    if not (isinstance(validated_entities, list) and \
            all(isinstance(e, BaseGeneratedEntity) for e in validated_entities)):
        logger.error(f"Structural validation returned unexpected type: {type(validated_entities)}")
        return CustomValidationError(
            error_type="InternalParserError",
            message="Structural validation did not return the expected list of entities."
        )

    semantic_errors = _perform_semantic_validation(validated_entities, guild_id)
    if semantic_errors:
        return semantic_errors[0]

    successful_data = ParsedAiData(
        generated_entities=validated_entities,
        raw_ai_output=raw_ai_output_text,
        parsing_metadata={"guild_id": guild_id}
    )
    return successful_data
