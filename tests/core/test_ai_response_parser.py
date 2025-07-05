import sys
import os
import unittest
import json
import asyncio # Added for loop.run_until_complete
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
    GeneratedEntity,
    ParsedAiData,
    ParsedQuestData, # Added for quest tests
    ParsedQuestStepData # Added for quest tests
)

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
    def test_parsed_faction_data_valid(self):
        faction_min = ParsedFactionData(**VALID_FACTION_DATA_MINIMAL)
        self.assertEqual(faction_min.static_id, "test_fac_01")
        self.assertEqual(faction_min.name_i18n["en"], "Test Faction")
        faction_full = ParsedFactionData(**VALID_FACTION_DATA_FULL)
        self.assertEqual(faction_full.leader_npc_static_id, "npc_leader_01")
        assert faction_full.resources_json is not None
        self.assertEqual(faction_full.resources_json["wood"], 500)

    def test_parsed_faction_data_invalid(self):
        with self.assertRaises(PydanticNativeValidationError):
            data = VALID_FACTION_DATA_MINIMAL.copy(); del data["static_id"]
            ParsedFactionData(**data)
        with self.assertRaises(PydanticNativeValidationError):
            ParsedFactionData(**{**VALID_FACTION_DATA_MINIMAL, "static_id": ""})
        with self.assertRaises(PydanticNativeValidationError):
            ParsedFactionData(**{**VALID_FACTION_DATA_MINIMAL, "name_i18n": "not a dict"})
        with self.assertRaises(PydanticNativeValidationError):
            ParsedFactionData(**{**VALID_FACTION_DATA_MINIMAL, "name_i18n": {}})
        with self.assertRaises(PydanticNativeValidationError):
            ParsedFactionData(**{**VALID_FACTION_DATA_MINIMAL, "name_i18n": {"en": 123}})
        with self.assertRaises(PydanticNativeValidationError):
            ParsedFactionData(**{**VALID_FACTION_DATA_FULL, "ideology_i18n": {"en": 123}})
        with self.assertRaises(PydanticNativeValidationError):
            faction = ParsedFactionData(**VALID_FACTION_DATA_MINIMAL)
            faction.entity_type = "new_type"

    def test_parsed_relationship_data_valid(self):
        rel = ParsedRelationshipData(**VALID_RELATIONSHIP_DATA)
        self.assertEqual(rel.entity1_static_id, "test_fac_01")
        self.assertEqual(rel.value, -50)

    def test_parsed_relationship_data_invalid(self):
        with self.assertRaises(PydanticNativeValidationError):
            data = VALID_RELATIONSHIP_DATA.copy(); del data["entity1_static_id"]
            ParsedRelationshipData(**data)
        with self.assertRaises(PydanticNativeValidationError):
            ParsedRelationshipData(**{**VALID_RELATIONSHIP_DATA, "entity1_type": ""})
        with self.assertRaises(PydanticNativeValidationError):
            ParsedRelationshipData(**{**VALID_RELATIONSHIP_DATA, "value": "not a number"})
        with self.assertRaises(PydanticNativeValidationError):
            rel = ParsedRelationshipData(**VALID_RELATIONSHIP_DATA)
            rel.entity_type = "new_type"

    def test_parsed_npc_data_valid(self):
        from src.core.ai_response_parser import ParsedNpcData
        valid_npc_data = {
            "entity_type": "npc", "static_id": "npc_001",
            "name_i18n": {"en": "Guard", "ru": "Стражник"},
            "description_i18n": {"en": "A city guard.", "ru": "Городской стражник."},
            "stats": {"hp": 50}
        }
        npc = ParsedNpcData(**valid_npc_data)
        self.assertEqual(npc.static_id, "npc_001")
        if npc.name_i18n: self.assertEqual(npc.name_i18n["en"], "Guard")
        if npc.stats: self.assertEqual(npc.stats["hp"], 50)
        valid_npc_data_no_static_id = valid_npc_data.copy(); del valid_npc_data_no_static_id["static_id"]
        npc_no_sid = ParsedNpcData(**valid_npc_data_no_static_id)
        self.assertIsNone(npc_no_sid.static_id)

    def test_parsed_npc_data_invalid_static_id(self):
        from src.core.ai_response_parser import ParsedNpcData
        invalid_npc_data_empty_static_id = {
            "entity_type": "npc", "static_id": " ",
            "name_i18n": {"en": "Guard"}, "description_i18n": {"en": "A city guard."}
        }
        with self.assertRaises(PydanticNativeValidationError) as context:
            ParsedNpcData(**invalid_npc_data_empty_static_id)
        self.assertIn("static_id must be a non-empty string if provided", str(context.exception))
        invalid_npc_data_wrong_type_static_id = {
            "entity_type": "npc", "static_id": 123,
            "name_i18n": {"en": "Guard"}, "description_i18n": {"en": "A city guard."}
        }
        with self.assertRaises(PydanticNativeValidationError) as context:
            ParsedNpcData(**invalid_npc_data_wrong_type_static_id)
        self.assertIn("static_id must be a non-empty string if provided", str(context.exception))

    def test_parsed_npc_data_missing_required_fields(self):
        from src.core.ai_response_parser import ParsedNpcData
        with self.assertRaises(PydanticNativeValidationError):
            ParsedNpcData(entity_type="npc", description_i18n={"en": "Desc"})
        with self.assertRaises(PydanticNativeValidationError):
            ParsedNpcData(entity_type="npc", name_i18n={"en": "Name"})

class TestAIResponseParserFunction(unittest.IsolatedAsyncioTestCase):
    async def test_parse_valid_faction_and_relationship(self):
        ai_response_list = [VALID_FACTION_DATA_FULL, VALID_RELATIONSHIP_DATA]
        ai_response_str = json.dumps(ai_response_list)
        result = await parse_and_validate_ai_response(ai_response_str, guild_id=1)
        if isinstance(result, CustomValidationError):
            self.fail(f"Parsing failed: {result.message}")
        self.assertIsInstance(result, ParsedAiData)
        self.assertEqual(len(result.generated_entities), 2)
        entity1, entity2 = result.generated_entities[0], result.generated_entities[1]
        self.assertIsInstance(entity1, ParsedFactionData)
        self.assertIsInstance(entity2, ParsedRelationshipData)
        if isinstance(entity1, ParsedFactionData):
            self.assertEqual(entity1.static_id, VALID_FACTION_DATA_FULL["static_id"])
        if isinstance(entity2, ParsedRelationshipData):
            self.assertEqual(entity2.value, VALID_RELATIONSHIP_DATA["value"])

    async def test_parse_invalid_json_string(self):
        invalid_json_str = '{"entity_type": "faction", "name_i18n": {"en": "Test"'
        result = await parse_and_validate_ai_response(invalid_json_str, guild_id=1)
        self.assertIsInstance(result, CustomValidationError)
        if isinstance(result, CustomValidationError):
            self.assertEqual(result.error_type, "JSONParsingError")

    async def test_parse_structural_validation_error_not_a_list(self):
        not_a_list_str = json.dumps({"some_key": "some_value"})
        result = await parse_and_validate_ai_response(not_a_list_str, guild_id=1)
        self.assertIsInstance(result, CustomValidationError)
        if isinstance(result, CustomValidationError):
            self.assertEqual(result.error_type, "StructuralValidationError")
            # Corrected indentation for the assertion below
            self.assertIn("Expected a list of entities", result.message)

    def test_parse_valid_quest_data(self):
        valid_quest_json_str = """
        [
            {
                "entity_type": "quest", "static_id": "q_001",
                "title_i18n": {"en": "The Grand Hunt", "ru": "Великая Охота"},
                "summary_i18n": {"en": "Hunt the legendary beast.", "ru": "Выследить легендарного зверя."},
                "steps": [
                    {"title_i18n": {"en": "Prepare", "ru": "Подготовка"}, "description_i18n": {"en": "Gather supplies."}, "step_order": 0, "required_mechanics_json": {"type": "gather", "item_count": 3}},
                    {"title_i18n": {"en": "Hunt", "ru": "Охота"}, "description_i18n": {"en": "Track and defeat the beast."}, "step_order": 1, "required_mechanics_json": {"type": "combat", "target_static_id": "beast_xyz"}}
                ], "rewards_json": {"xp": 500}
            }
        ]"""
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(parse_and_validate_ai_response(valid_quest_json_str, guild_id=1))
        self.assertIsInstance(result, ParsedAiData)
        assert isinstance(result, ParsedAiData) # for type checker
        self.assertEqual(len(result.generated_entities), 1)
        parsed_quest = result.generated_entities[0]
        self.assertIsInstance(parsed_quest, ParsedQuestData)
        assert isinstance(parsed_quest, ParsedQuestData) # for type checker
        self.assertEqual(parsed_quest.static_id, "q_001")
        self.assertEqual(parsed_quest.title_i18n["en"], "The Grand Hunt")
        self.assertEqual(len(parsed_quest.steps), 2)
        self.assertEqual(parsed_quest.steps[0].title_i18n["en"], "Prepare")
        self.assertEqual(parsed_quest.steps[0].step_order, 0)
        assert parsed_quest.steps[1].required_mechanics_json is not None # for type checker
        self.assertEqual(parsed_quest.steps[1].required_mechanics_json["type"], "combat")

    def test_parse_quest_data_missing_static_id(self):
        invalid_quest_json_str = """
        [
            {"entity_type": "quest", "title_i18n": {"en": "Quest without ID"}, "summary_i18n": {"en": "Missing static_id."}, "steps": [{"title_i18n": {"en": "Step 1"}, "description_i18n": {"en": "Do something."}, "step_order": 0}]}
        ]"""
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(parse_and_validate_ai_response(invalid_quest_json_str, guild_id=1))
        self.assertIsInstance(result, CustomValidationError)
        assert isinstance(result, CustomValidationError) # for type checker
        self.assertEqual(result.error_type, "StructuralValidationError")
        assert result.details is not None # for type checker
        # Pydantic v2: loc is a tuple, type is 'missing' for required fields
        found_static_id_missing_error = any(
            isinstance(detail.get("loc"), tuple) and \
            "static_id" in detail.get("loc") and \
            detail.get("type") == "missing"
            for detail in result.details if isinstance(detail, dict)
        )
        self.assertTrue(found_static_id_missing_error, f"Expected 'missing' error for 'static_id' not found. Details: {result.details}")

    def test_parse_quest_data_empty_steps(self):
        invalid_quest_json_str = """
        [
            {"entity_type": "quest", "static_id": "q_empty_steps", "title_i18n": {"en": "Empty Quest"}, "summary_i18n": {"en": "No steps."}, "steps": []}
        ]"""
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(parse_and_validate_ai_response(invalid_quest_json_str, guild_id=1))
        self.assertIsInstance(result, CustomValidationError)
        assert isinstance(result, CustomValidationError) # for type checker
        self.assertEqual(result.error_type, "StructuralValidationError")
        assert result.details is not None # for type checker
        self.assertTrue(any("steps" in detail.get("loc", []) and "Quest must have at least one step." in detail.get("msg","") for detail in result.details if isinstance(detail, dict)))

    def test_parse_quest_step_data_invalid_i18n(self):
        invalid_step_json_str = """
        [
            {"entity_type": "quest", "static_id": "q_bad_step_i18n", "title_i18n": {"en": "Quest with Bad Step"}, "summary_i18n": {"en": "Bad i18n in step."}, "steps": [{"title_i18n": {"en": "Valid Step"}, "description_i18n": "not an i18n dict", "step_order": 0}]}
        ]"""
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(parse_and_validate_ai_response(invalid_step_json_str, guild_id=1))
        self.assertIsInstance(result, CustomValidationError)
        assert isinstance(result, CustomValidationError) # for type checker
        self.assertEqual(result.error_type, "StructuralValidationError")
        assert result.details is not None # for type checker
        self.assertTrue(any("steps" in detail.get("loc", []) and 0 in detail.get("loc", []) and "description_i18n" in detail.get("loc", []) for detail in result.details if isinstance(detail, dict)))

    async def test_parse_pydantic_validation_error_in_faction(self):
        invalid_faction_data = VALID_FACTION_DATA_MINIMAL.copy()
        del invalid_faction_data["name_i18n"]
        ai_response_list = [invalid_faction_data, VALID_RELATIONSHIP_DATA]
        ai_response_str = json.dumps(ai_response_list)
        result = await parse_and_validate_ai_response(ai_response_str, guild_id=1)
        self.assertIsInstance(result, CustomValidationError)
        if isinstance(result, CustomValidationError):
            self.assertEqual(result.error_type, "StructuralValidationError")
            self.assertIn("Validation failed for entity at index 0", result.message)
            self.assertEqual(result.path, [0])
            found_name_error = False
            if result.details:
                for error_detail in result.details:
                    if "name_i18n" in error_detail.get("loc", tuple()) and error_detail.get("type") == "missing":
                        found_name_error = True; break
            self.assertTrue(found_name_error)

    async def test_parse_semantic_validation_error_faction_missing_lang(self):
        faction_missing_en = {
            "entity_type": "faction", "static_id": "fac_sem_err",
            "name_i18n": {"ru": "Только Ру"}, "description_i18n": {"en": "Desc", "ru": "Описание"}
        }
        ai_response_str = json.dumps([faction_missing_en])
        result = await parse_and_validate_ai_response(ai_response_str, guild_id=1)
        self.assertIsInstance(result, CustomValidationError)
        if isinstance(result, CustomValidationError):
            self.assertEqual(result.error_type, "SemanticValidationError")
            self.assertIn("missing required languages {'en'} in 'name_i18n'", result.message)

    async def test_parse_semantic_validation_error_relationship_value_out_of_range(self):
        relationship_bad_value = {**VALID_RELATIONSHIP_DATA, "value": 2000}
        valid_faction_for_sem_test = VALID_FACTION_DATA_MINIMAL.copy()
        valid_faction_for_sem_test["name_i18n"] = {"en": "Test", "ru": "Тест"}
        valid_faction_for_sem_test["description_i18n"] = {"en": "Test", "ru": "Тест"}
        ai_response_str = json.dumps([valid_faction_for_sem_test, relationship_bad_value])
        result = await parse_and_validate_ai_response(ai_response_str, guild_id=1)
        self.assertIsInstance(result, CustomValidationError)
        if isinstance(result, CustomValidationError):
            self.assertEqual(result.error_type, "SemanticValidationError")
            self.assertIn("has value 2000 outside expected range", result.message)
            self.assertEqual(result.path, [1, "value"])

if __name__ == "__main__":
    unittest.main()
