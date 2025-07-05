import sys
import os
import unittest
import json
from typing import Dict, Any, List, Union

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pydantic import ValidationError as PydanticNativeValidationError

from src.core.ai_response_parser import (
    ParsedFactionData,
    ParsedRelationshipData,
    parse_and_validate_ai_response,
    CustomValidationError,
    GeneratedEntity, # For constructing test data for parse_and_validate_ai_response
    ParsedAiData
)
# Mocking get_rule for semantic validation tests, as it's called by _perform_semantic_validation
# This will be used with unittest.mock.patch
# from src.core.rules import get_rule

# Helper data
VALID_FACTION_DATA_MINIMAL = {
    "entity_type": "faction",
    "static_id": "test_fac_01",
    "name_i18n": {"en": "Test Faction", "ru": "Тестовая Фракция"},
    "description_i18n": {"en": "A test faction.", "ru": "Тестовая фракция."},
}

VALID_FACTION_DATA_FULL = {
    **VALID_FACTION_DATA_MINIMAL,
    "ideology_i18n": {"en": "Testology", "ru": "Тестология"},
    "leader_npc_static_id": "npc_leader_01",
    "resources_json": {"gold": 100, "wood": 500},
    "ai_metadata_json": {"notes": "Generated for testing"},
}

VALID_RELATIONSHIP_DATA = {
    "entity_type": "relationship",
    "entity1_static_id": "test_fac_01",
    "entity1_type": "faction",
    "entity2_static_id": "test_fac_02",
    "entity2_type": "faction",
    "relationship_type": "rivalry",
    "value": -50,
}

class TestAIResponseParserPydanticModels(unittest.TestCase):
    # Synchronous tests for Pydantic model validation

    def test_parsed_faction_data_valid(self):
        # Test minimal valid data
        faction_min = ParsedFactionData(**VALID_FACTION_DATA_MINIMAL)
        self.assertEqual(faction_min.static_id, "test_fac_01")
        # name_i18n is not Optional, so direct access is fine if VALID_FACTION_DATA_MINIMAL is correct
        self.assertEqual(faction_min.name_i18n["en"], "Test Faction")

        # Test full valid data
        faction_full = ParsedFactionData(**VALID_FACTION_DATA_FULL)
        self.assertEqual(faction_full.leader_npc_static_id, "npc_leader_01")
        # resources_json is Optional, but VALID_FACTION_DATA_FULL provides it.
        # If VALID_FACTION_DATA_FULL guarantees resources_json, direct access is okay after validation.
        # However, to be safe with type hints if data could vary, a check is good.
        assert faction_full.resources_json is not None
        self.assertEqual(faction_full.resources_json["wood"], 500)

    def test_parsed_faction_data_invalid(self):
        # Missing static_id
        with self.assertRaises(PydanticNativeValidationError):
            data = VALID_FACTION_DATA_MINIMAL.copy()
            del data["static_id"]
            ParsedFactionData(**data)

        # Empty static_id
        with self.assertRaises(PydanticNativeValidationError):
            ParsedFactionData(**{**VALID_FACTION_DATA_MINIMAL, "static_id": ""})

        # Invalid name_i18n (not a dict)
        with self.assertRaises(PydanticNativeValidationError):
            ParsedFactionData(**{**VALID_FACTION_DATA_MINIMAL, "name_i18n": "not a dict"})

        # Invalid name_i18n (empty dict)
        with self.assertRaises(PydanticNativeValidationError):
            ParsedFactionData(**{**VALID_FACTION_DATA_MINIMAL, "name_i18n": {}})

        # Invalid name_i18n (wrong content type)
        with self.assertRaises(PydanticNativeValidationError):
            ParsedFactionData(**{**VALID_FACTION_DATA_MINIMAL, "name_i18n": {"en": 123}})

        # Invalid ideology_i18n (if present, must be valid)
        with self.assertRaises(PydanticNativeValidationError):
            ParsedFactionData(**{**VALID_FACTION_DATA_FULL, "ideology_i18n": {"en": 123}})

        # Entity type cannot be changed
        with self.assertRaises(PydanticNativeValidationError):
            faction = ParsedFactionData(**VALID_FACTION_DATA_MINIMAL)
            faction.entity_type = "new_type"


    def test_parsed_relationship_data_valid(self):
        rel = ParsedRelationshipData(**VALID_RELATIONSHIP_DATA)
        self.assertEqual(rel.entity1_static_id, "test_fac_01")
        self.assertEqual(rel.value, -50)

    def test_parsed_relationship_data_invalid(self):
        # Missing entity1_static_id
        with self.assertRaises(PydanticNativeValidationError):
            data = VALID_RELATIONSHIP_DATA.copy()
            del data["entity1_static_id"]
            ParsedRelationshipData(**data)

        # Empty entity1_type
        with self.assertRaises(PydanticNativeValidationError):
            ParsedRelationshipData(**{**VALID_RELATIONSHIP_DATA, "entity1_type": ""})

        # Non-numeric value (Pydantic should catch this based on type hint)
        with self.assertRaises(PydanticNativeValidationError):
            ParsedRelationshipData(**{**VALID_RELATIONSHIP_DATA, "value": "not a number"})

        # Entity type cannot be changed
        with self.assertRaises(PydanticNativeValidationError):
            rel = ParsedRelationshipData(**VALID_RELATIONSHIP_DATA)
            rel.entity_type = "new_type"

    # Tests for ParsedNpcData
    def test_parsed_npc_data_valid(self):
        from src.core.ai_response_parser import ParsedNpcData # Local import for clarity
        valid_npc_data = {
            "entity_type": "npc",
            "static_id": "npc_001",
            "name_i18n": {"en": "Guard", "ru": "Стражник"},
            "description_i18n": {"en": "A city guard.", "ru": "Городской стражник."},
            "stats": {"hp": 50}
        }
        npc = ParsedNpcData(**valid_npc_data)
        self.assertEqual(npc.static_id, "npc_001")
        if npc.name_i18n: # Guard for Pyright, though name_i18n is not Optional
            self.assertEqual(npc.name_i18n["en"], "Guard")
        if npc.stats: # Guard for Pyright as stats is Optional
            self.assertEqual(npc.stats["hp"], 50)

        # Test with optional static_id missing
        valid_npc_data_no_static_id = valid_npc_data.copy()
        del valid_npc_data_no_static_id["static_id"]
        npc_no_sid = ParsedNpcData(**valid_npc_data_no_static_id)
        self.assertIsNone(npc_no_sid.static_id)

    def test_parsed_npc_data_invalid_static_id(self):
        from src.core.ai_response_parser import ParsedNpcData
        invalid_npc_data_empty_static_id = {
            "entity_type": "npc", "static_id": " ", # Whitespace only
            "name_i18n": {"en": "Guard", "ru": "Стражник"},
            "description_i18n": {"en": "A city guard.", "ru": "Городской стражник."}
        }
        with self.assertRaises(PydanticNativeValidationError) as context:
            ParsedNpcData(**invalid_npc_data_empty_static_id)
        self.assertIn("static_id must be a non-empty string if provided", str(context.exception))

        invalid_npc_data_wrong_type_static_id = {
            "entity_type": "npc", "static_id": 123, # Not a string
            "name_i18n": {"en": "Guard", "ru": "Стражник"},
            "description_i18n": {"en": "A city guard.", "ru": "Городской стражник."}
        }
        with self.assertRaises(PydanticNativeValidationError) as context:
            ParsedNpcData(**invalid_npc_data_wrong_type_static_id)
        # Pydantic v2 might convert int to str if not strict, or error on type.
        # The validator `check_static_id` runs `mode='before'`, so it gets 123.
        # `isinstance(v, str)` will be false.
        # The error message comes from our validator.
        self.assertIn("static_id must be a non-empty string if provided", str(context.exception))

    def test_parsed_npc_data_missing_required_fields(self):
        from src.core.ai_response_parser import ParsedNpcData
        # Missing name_i18n
        with self.assertRaises(PydanticNativeValidationError):
            ParsedNpcData(entity_type="npc", description_i18n={"en": "Desc"}) # type: ignore[call-arg]
        # Missing description_i18n
        with self.assertRaises(PydanticNativeValidationError):
            ParsedNpcData(entity_type="npc", name_i18n={"en": "Name"}) # type: ignore[call-arg]


class TestAIResponseParserFunction(unittest.IsolatedAsyncioTestCase):
    # Asynchronous tests for parse_and_validate_ai_response function

    async def test_parse_valid_faction_and_relationship(self):
        # Test with a mix of valid faction and relationship data
        # The parser expects a flat list of entities as input string
        ai_response_list = [VALID_FACTION_DATA_FULL, VALID_RELATIONSHIP_DATA]
        ai_response_str = json.dumps(ai_response_list)

        # Mocking get_rule for semantic validation of language (e.g. 'en' required)
        # For this test, assume 'en' is always required by _perform_semantic_validation's current logic

        result = await parse_and_validate_ai_response(ai_response_str, guild_id=1)

        if isinstance(result, CustomValidationError):
            self.fail(f"Parsing failed: {result.message}")

        # Now result is ParsedAiData
        self.assertIsInstance(result, ParsedAiData) # Should already be true if no fail
        self.assertEqual(len(result.generated_entities), 2)

        entity1 = result.generated_entities[0]
        entity2 = result.generated_entities[1]

        self.assertIsInstance(entity1, ParsedFactionData)
        self.assertIsInstance(entity2, ParsedRelationshipData)

        if isinstance(entity1, ParsedFactionData): # Guard for Pyright
            self.assertEqual(entity1.static_id, VALID_FACTION_DATA_FULL["static_id"])
        if isinstance(entity2, ParsedRelationshipData): # Guard for Pyright
            self.assertEqual(entity2.value, VALID_RELATIONSHIP_DATA["value"])


    async def test_parse_invalid_json_string(self):
        invalid_json_str = '{"entity_type": "faction", "name_i18n": {"en": "Test"' # Missing closing brace and quote
        result = await parse_and_validate_ai_response(invalid_json_str, guild_id=1)
        self.assertIsInstance(result, CustomValidationError)
        if isinstance(result, CustomValidationError): # Guard for Pyright
            self.assertEqual(result.error_type, "JSONParsingError")

    async def test_parse_structural_validation_error_not_a_list(self):
        # AI response is expected to be a list of entities
        not_a_list_str = json.dumps({"some_key": "some_value"})
        result = await parse_and_validate_ai_response(not_a_list_str, guild_id=1)
        self.assertIsInstance(result, CustomValidationError)
        if isinstance(result, CustomValidationError): # Guard for Pyright
            self.assertEqual(result.error_type, "StructuralValidationError")
            self.assertIn("Expected a list of entities", result.message)

    async def test_parse_pydantic_validation_error_in_faction(self):
        invalid_faction_data = VALID_FACTION_DATA_MINIMAL.copy()
        del invalid_faction_data["name_i18n"] # Missing required field
        ai_response_list = [invalid_faction_data, VALID_RELATIONSHIP_DATA]
        ai_response_str = json.dumps(ai_response_list)

        result = await parse_and_validate_ai_response(ai_response_str, guild_id=1)
        self.assertIsInstance(result, CustomValidationError)
        if isinstance(result, CustomValidationError): # Guard for Pyright
            self.assertEqual(result.error_type, "StructuralValidationError") # Pydantic errors are caught as structural by _validate_overall_structure
            self.assertIn("Validation failed for entity at index 0", result.message)
            self.assertEqual(result.path, [0]) # Path should indicate the failing entity index

            # Check details for specific field error for 'name_i18n'
            # result.details is a list of dicts, each representing a Pydantic validation error for the entity at path [0]
            found_name_error = False
            if result.details: # Guard for Pyright, result.details can be None
                for error_detail in result.details:
                    # Example error_detail: {'type': 'missing', 'loc': ('name_i18n',), 'msg': 'Field required', 'input': {...}}
                    if "name_i18n" in error_detail.get("loc", tuple()) and error_detail.get("type") == "missing":
                        found_name_error = True
                        break
            self.assertTrue(found_name_error, "Expected a validation error for missing 'name_i18n' in the first entity's details.")


    async def test_parse_semantic_validation_error_faction_missing_lang(self):
        # Assumes _perform_semantic_validation checks for 'en' key.
        faction_missing_en = {
            "entity_type": "faction", "static_id": "fac_sem_err",
            "name_i18n": {"ru": "Только Ру"}, # Missing 'en'
            "description_i18n": {"en": "Desc", "ru": "Описание"}
        }
        ai_response_str = json.dumps([faction_missing_en])
        result = await parse_and_validate_ai_response(ai_response_str, guild_id=1)
        self.assertIsInstance(result, CustomValidationError)
        if isinstance(result, CustomValidationError): # Guard for Pyright
            self.assertEqual(result.error_type, "SemanticValidationError")
            self.assertIn("missing required languages {'en'} in 'name_i18n'", result.message)

    async def test_parse_semantic_validation_error_relationship_value_out_of_range(self):
        # Assumes _perform_semantic_validation checks relationship value range (-1000 to 1000)
        relationship_bad_value = {
            **VALID_RELATIONSHIP_DATA,
            "value": 2000 # Out of range
        }
        ai_response_str = json.dumps([VALID_FACTION_DATA_MINIMAL, relationship_bad_value]) # Add a valid faction to make the list pass initial struct validation for first item

        # Need to ensure the faction part is valid semantically too
        valid_faction_for_sem_test = VALID_FACTION_DATA_MINIMAL.copy()
        valid_faction_for_sem_test["name_i18n"] = {"en": "Test", "ru": "Тест"}
        valid_faction_for_sem_test["description_i18n"] = {"en": "Test", "ru": "Тест"}

        ai_response_str = json.dumps([valid_faction_for_sem_test, relationship_bad_value])

        result = await parse_and_validate_ai_response(ai_response_str, guild_id=1)
        self.assertIsInstance(result, CustomValidationError)
        if isinstance(result, CustomValidationError): # Guard for Pyright
            self.assertEqual(result.error_type, "SemanticValidationError")
            self.assertIn("has value 2000 outside expected range", result.message)
            self.assertEqual(result.path, [1, "value"]) # path should be [entity_index, field_name]

if __name__ == "__main__":
    unittest.main()
