import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import json
from pydantic import ValidationError
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.ai_analysis_system import analyze_generated_content, AIAnalysisResult
from src.core.ai_response_parser import BaseGeneratedEntity
from src.models import RuleConfig

# Enhanced Mock Pydantic models
class MockParsedNPC(BaseGeneratedEntity):
    entity_type: str = "npc"
    static_id: str = "mock_npc_default"
    name_i18n: Dict[str, str] = {"en": "Mock NPC", "ru": "Тестовый NPC"}
    description_i18n: Dict[str, str] = {"en": "A brave mock warrior.", "ru": "Храбрый тестовый воин."}
    level: int = 5
    properties_json: Dict[str, Any] = {"role": "warrior", "stats": {"health": 100}}

class MockParsedItem(BaseGeneratedEntity):
    entity_type: str = "item"
    static_id: str = "mock_item_default"
    name_i18n: Dict[str, str] = {"en": "Mock Item", "ru": "Тестовый Предмет"}
    description_i18n: Dict[str, str] = {"en": "A shiny mock trinket.", "ru": "Блестящая тестовая безделушка."}
    item_type: str = "trinket"
    base_value: int = 50
    properties_json: Dict[str, Any] = {"rarity": "common"}

class MockParsedQuest(BaseGeneratedEntity):
    entity_type: str = "quest"
    static_id: str = "mock_quest_default"
    title_i18n: Dict[str, str] = {"en": "Mock Quest", "ru": "Тестовый Квест"}
    summary_i18n: Dict[str, str] = {"en": "Retrieve the mock artifact.", "ru": "Добудьте макетный артефакт."}
    steps: List[Dict[str, Any]] = [
        {"step_order": 1, "title_i18n": {"en": "Step 1", "ru": "Шаг 1"}, "description_i18n": {"en": "Desc1", "ru": "Опис1"}}
    ]
    min_level: int = 1

class MockParsedFaction(BaseGeneratedEntity):
    entity_type: str = "faction"
    static_id: str = "mock_faction_default"
    name_i18n: Dict[str, str] = {"en": "Mock Faction", "ru": "Тестовая Фракция"}
    description_i18n: Dict[str, str] = {"en": "A faction for testing.", "ru": "Фракция для тестов."}
    ideology_i18n: Dict[str, str] = {"en": "Testology", "ru": "Тестология"}

class MockParsedLocation(BaseGeneratedEntity):
    entity_type: str = "location"
    static_id: str = "mock_location_default"
    name_i18n: Dict[str, str] = {"en": "Mock Location", "ru": "Тестовая Локация"}
    descriptions_i18n: Dict[str, str] = {"en": "A place of wonders.", "ru": "Место чудес."} # Note: plural "descriptions"
    type: str = "generic"


class TestAIAnalysisSystem(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_session = AsyncMock(spec=AsyncSession)
        self.guild_id = 1

        self.patch_prepare_quest = patch('src.core.ai_analysis_system.prepare_quest_generation_prompt', new_callable=AsyncMock)
        self.patch_prepare_economic = patch('src.core.ai_analysis_system.prepare_economic_entity_generation_prompt', new_callable=AsyncMock)
        self.patch_prepare_general_loc = patch('src.core.ai_analysis_system.prepare_general_location_content_prompt', new_callable=AsyncMock)
        self.patch_prepare_faction = patch('src.core.ai_analysis_system.prepare_faction_relationship_generation_prompt', new_callable=AsyncMock)
        self.patch_get_entity_schemas = patch('src.core.ai_analysis_system._get_entity_schema_terms', new_callable=MagicMock)
        self.patch_parse_validate = patch('src.core.ai_analysis_system.parse_and_validate_ai_response', new_callable=AsyncMock)
        self.patch_get_rule = patch('src.core.ai_analysis_system.get_rule', new_callable=AsyncMock)

        self.mock_prepare_quest_prompt = self.patch_prepare_quest.start()
        self.mock_prepare_economic_prompt = self.patch_prepare_economic.start()
        self.mock_prepare_general_loc_prompt = self.patch_prepare_general_loc.start()
        self.mock_prepare_faction_prompt = self.patch_prepare_faction.start()
        self.mock_get_entity_schemas = self.patch_get_entity_schemas.start()
        self.mock_parse_and_validate = self.patch_parse_validate.start()
        self.mock_get_rule = self.patch_get_rule.start()

        self.addCleanup(patch.stopall)

        self.mock_prepare_quest_prompt.return_value = "Prompt for Quest"
        self.mock_prepare_economic_prompt.return_value = "Prompt for Economic Entities"
        self.mock_prepare_general_loc_prompt.return_value = "Prompt for General Location Content"
        self.mock_prepare_faction_prompt.return_value = "Prompt for Faction Generation"
        self.mock_get_entity_schemas.return_value = {
            "npc_schema": {"description": "NPC schema"}, "item_schema": {"description": "Item schema"},
            "quest_schema": {"description": "Quest schema"}, "faction_schema": {"description": "Faction schema"},
            "location_schema": {"description": "Location schema"},
        }
        self.mock_get_rule.side_effect = lambda session, guild_id, key, default: default

    async def _run_analysis(self, entity_type: str, mock_parsed_entity: Optional[BaseGeneratedEntity], context_json: Optional[str] = None):
        from src.core.ai_response_parser import ParsedAiData # Import for wrapping
        entities_for_payload = []
        if mock_parsed_entity:
            # Pass as dict for Pydantic to validate against the Union
            entities_for_payload.append(mock_parsed_entity.model_dump(mode='json'))

        self.mock_parse_and_validate.return_value = ParsedAiData(
            raw_ai_output="mock raw output for test", # Added required field
            generated_entities=entities_for_payload
            # errors=[] # Removed, ParsedAiData does not have an 'errors' field
        )

        return await analyze_generated_content(
            session=self.mock_session, guild_id=self.guild_id, entity_type=entity_type,
            generation_context_json=context_json, use_real_ai=False, target_count=1
        )

    # --- Tests for Prompt Builder Calls ---
    async def test_calls_prepare_quest_generation_prompt_for_quest(self):
        await self._run_analysis("quest", MockParsedQuest())
        self.mock_prepare_quest_prompt.assert_called_once_with(self.mock_session, self.guild_id, player_id_context=None, location_id_context=None)

    async def test_calls_prepare_economic_prompt_for_item(self):
        await self._run_analysis("item", MockParsedItem())
        self.mock_prepare_economic_prompt.assert_called_once_with(self.mock_session, self.guild_id)

    async def test_calls_general_loc_prompt_for_npc_with_location_context(self):
        context = {"location_id": 101, "player_id": 201, "party_id": 301}
        await self._run_analysis("npc", MockParsedNPC(), context_json=json.dumps(context))
        self.mock_prepare_general_loc_prompt.assert_called_once_with(self.mock_session, self.guild_id, location_id=101, player_id=201, party_id=301)

    async def test_calls_simplified_prompt_for_npc_without_location_context(self):
        await self._run_analysis("npc", MockParsedNPC())
        self.mock_prepare_general_loc_prompt.assert_not_called()
        # Check that _get_entity_schema_terms was involved for the simplified prompt
        self.mock_get_entity_schemas.assert_called()


    async def test_calls_prepare_faction_prompt_for_faction(self):
        await self._run_analysis("faction", MockParsedFaction())
        self.mock_prepare_faction_prompt.assert_called_once_with(self.mock_session, self.guild_id)

    # --- Tests for Analysis Logic ---
    async def test_i18n_completeness_fail(self):
        npc_missing_ru_name = MockParsedNPC(name_i18n={"en": "Only English Name"})
        self.mock_get_rule.side_effect = lambda s,gid,key,d: {"required_languages":["en","ru"]} if key=="analysis:common:i18n_completeness" else d
        result = await self._run_analysis("npc", npc_missing_ru_name)
        self.assertIn("Missing or empty i18n field 'name_i18n' for language 'ru'.", result.analysis_reports[0].issues_found)

    async def test_description_length_too_short(self):
        item_short_desc = MockParsedItem(description_i18n={"en": "Short."})
        self.mock_get_rule.side_effect = lambda s,gid,key,d: {"min":20,"max":100} if key=="analysis:common:description_length:item" else d
        result = await self._run_analysis("item", item_short_desc)
        self.assertIn("Desc/Summary (en) length (6) outside range [20-100].", result.analysis_reports[0].issues_found)

    async def test_key_field_missing_for_item(self):
        # Pydantic model will raise error if static_id or item_type is missing.
        # This test checks if our *additional* logic catches something if Pydantic model was more lenient or data is dict
        item_dict_missing_type = {"entity_type":"item", "name_i18n":{"en":"Item"}, "static_id":"item1"} # Missing item_type
        # We bypass Pydantic model creation for this specific test of the internal check
        self.mock_parse_and_validate.return_value = [BaseGeneratedEntity(**item_dict_missing_type)]
        result = await self._run_analysis("item", None) # Pass None to use the mocked parsed value
        self.assertIn("Item missing key field: 'item_type'.", result.analysis_reports[0].issues_found)


    async def test_npc_level_out_of_range(self):
        npc_high_level = MockParsedNPC(level=150)
        self.mock_get_rule.side_effect = lambda s,gid,key,d: {"min":1,"max":100} if key=="analysis:npc:field_range:level" else d
        result = await self._run_analysis("npc", npc_high_level)
        self.assertIn("NPC level (150) outside range [1-100].", result.analysis_reports[0].issues_found)

    async def test_quest_missing_steps(self):
        quest_no_steps = MockParsedQuest(steps=[])
        result = await self._run_analysis("quest", quest_no_steps)
        self.assertIn("Quest 'steps' field is missing, not a list, or empty.", result.analysis_reports[0].issues_found)

    async def test_quest_malformed_step(self):
        quest_bad_step = MockParsedQuest(steps=[{"title_i18n":{"en":"Good"}, "description_i18n":{"en":"Good"}}]) # Missing step_order
        result = await self._run_analysis("quest", quest_bad_step)
        self.assertIn("Quest Step 1 is malformed or missing key fields (step_order, title_i18n, description_i18n).", result.analysis_reports[0].issues_found)

    async def test_pydantic_validation_error_captured(self):
        from src.core.ai_response_parser import CustomValidationError # Import for test

        # Simulate parse_and_validate_ai_response returning a CustomValidationError
        custom_error_details_dicts = [{"loc": ("name_i18n",), "msg": "field required", "type": "value_error.missing", "input": {}}]
        # Convert details to list of strings as SUT stores them
        custom_error_details_json_strings = [json.dumps(detail) for detail in custom_error_details_dicts]

        self.mock_parse_and_validate.return_value = CustomValidationError(
            error_type="TestPydanticValidationError", # Added required field
            message="Mocked Pydantic Error From Test",
            details=custom_error_details_dicts # parse_and_validate_ai_response returns dicts here
        )

        result = await self._run_analysis("npc", None) # Entity type doesn't matter as parsing will "fail" via CustomValidationError

        self.assertEqual(len(result.analysis_reports), 1)
        report = result.analysis_reports[0]

        # Check that the SUT correctly identifies the CustomValidationError
        self.assertTrue(any("AI Response Validation Error: Mocked Pydantic Error From Test" in issue for issue in report.issues_found))

        self.assertIsNotNone(report.validation_errors)
        self.assertEqual(len(report.validation_errors), 1) # type: ignore[arg-type]
        # The SUT stores details as JSON strings in the report
        self.assertEqual(report.validation_errors[0], custom_error_details_json_strings[0]) # type: ignore[index]
        self.assertIn("'loc': ('name_i18n',)", report.validation_errors[0]) # type: ignore[index]
        self.assertIn("'msg': 'field required'", report.validation_errors[0]) # type: ignore[index]


    async def test_filtering_of_parsed_entities_item_from_economic_prompt(self):
        # Economic prompt generates items and npc_traders
        # We request "item", so only item should be analyzed
        mock_item = MockParsedItem(static_id="item_to_find")
        mock_trader = MockParsedNPC(entity_type="npc_trader", static_id="trader_to_ignore")
        self.mock_parse_and_validate.return_value = [mock_item, mock_trader]

        result = await self._run_analysis("item", None) # Let the mock_parse_and_validate provide the entities

        self.assertEqual(len(result.analysis_reports), 1) # Should only be one report for the item
        report = result.analysis_reports[0]
        self.assertEqual(report.entity_data_preview.get("static_id"), "item_to_find")
        self.assertNotIn("trader_to_ignore", report.entity_data_preview.get("static_id", ""))


    async def test_filtering_of_parsed_entities_npc_from_location_prompt(self):
        # Location prompt might generate NPCs, items, etc.
        # We request "npc", so only npc/npc_trader should be analyzed
        mock_npc = MockParsedNPC(static_id="npc_to_find")
        mock_item_in_loc = MockParsedItem(static_id="item_to_ignore")
        mock_npc_trader = MockParsedNPC(entity_type="npc_trader", static_id="npc_trader_to_find")
        self.mock_parse_and_validate.return_value = [mock_item_in_loc, mock_npc, mock_npc_trader]

        # We expect to analyze the first NPC or NPC_Trader found
        result = await self._run_analysis("npc", None)

        self.assertEqual(len(result.analysis_reports), 1)
        report = result.analysis_reports[0]
        # The current logic takes the *first* match. If npc comes before npc_trader in the list:
        self.assertEqual(report.entity_data_preview.get("static_id"), "npc_to_find")


if __name__ == '__main__':
    unittest.main()
