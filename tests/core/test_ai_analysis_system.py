import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import json
from pydantic import ValidationError, parse_obj_as
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.engine.result import Result, ScalarResult

from src.core.ai_analysis_system import analyze_generated_content, AIAnalysisResult
from src.core.ai_response_parser import BaseGeneratedEntity, ParsedAiData, GeneratedEntity, PydanticNativeValidationError, CustomValidationError
from src.models import GuildConfig, RuleConfig

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
    descriptions_i18n: Dict[str, str] = {"en": "A place of wonders.", "ru": "Место чудес."}
    type: str = "generic"


class TestAIAnalysisSystem(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_session = AsyncMock(spec=AsyncSession)
        self.guild_id = 1

        self.patch_prepare_quest = patch('src.core.ai_analysis_system.prepare_quest_generation_prompt', new_callable=AsyncMock)
        self.patch_prepare_economic = patch('src.core.ai_analysis_system.prepare_economic_entity_generation_prompt', new_callable=AsyncMock)
        self.patch_prepare_general_loc = patch('src.core.ai_analysis_system.prepare_general_location_content_prompt', new_callable=AsyncMock)
        self.patch_prepare_faction = patch('src.core.ai_analysis_system.prepare_faction_relationship_generation_prompt', new_callable=AsyncMock)
        self.patch_get_entity_schemas = patch('src.core.ai_analysis_system.get_entity_schema_terms', new_callable=MagicMock) # Corrected patch target
        self.patch_parse_validate = patch('src.core.ai_analysis_system.parse_and_validate_ai_response', new_callable=AsyncMock)
        self.patch_get_rule = patch('src.core.ai_analysis_system.get_rule', new_callable=AsyncMock)

        self.patch_guild_config_get_for_class = patch('src.core.crud.guild_crud.get', new_callable=AsyncMock)

        self.mock_prepare_quest_prompt = self.patch_prepare_quest.start()
        self.mock_prepare_economic_prompt = self.patch_prepare_economic.start()
        self.mock_prepare_general_loc_prompt = self.patch_prepare_general_loc.start()
        self.mock_prepare_faction_prompt = self.patch_prepare_faction.start()
        self.mock_get_entity_schemas = self.patch_get_entity_schemas.start()
        self.mock_parse_and_validate = self.patch_parse_validate.start()
        self.mock_get_rule = self.patch_get_rule.start()
        self.mock_guild_config_get_for_class = self.patch_guild_config_get_for_class.start()

        self.addCleanup(patch.stopall)

        mock_gc_instance = GuildConfig(id=self.guild_id, main_language="en")
        # For test purposes, we are dynamically adding this attribute.
        # Pyright will complain if not handled with setattr or cast.
        # setattr(mock_gc_instance, 'supported_languages_json', ["en", "ru"])
        # Or, if GuildConfig is a Pydantic model and this is a real field, ensure it's in the model definition.
        # For now, assuming it's a dynamic test attribute and we'll handle type checking issues if they persist.
        # Let's assume it's a dynamic attribute for the mock. We can tell pyright to ignore if needed for a specific line.
        mock_gc_instance.supported_languages_json = ["en", "ru"] # type: ignore[attr-defined]
        self.mock_guild_config_get_for_class.return_value = mock_gc_instance

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

    async def _run_analysis(self, entity_type: str, mock_test_data_entity: Optional[BaseGeneratedEntity], context_json: Optional[str] = None):
        if mock_test_data_entity:
            try:
                # parse_obj_as needs a concrete type, not the Union GeneratedEntity directly as the first argument.
                # We need to determine the correct type from mock_test_data_entity.
                # This is a simplification; a more robust solution might involve a mapping or isinstance checks.
                # For this test, we know the type of mock_test_data_entity.
                entity_model_type = type(mock_test_data_entity) # This is the mock type, e.g. MockParsedItem
                actual_entity_type_str = getattr(mock_test_data_entity, 'entity_type', None)

                if actual_entity_type_str:
                    from src.core.ai_response_parser import (
                        ParsedNpcData, ParsedItemData, ParsedQuestData, ParsedFactionData,
                        ParsedLocationData, ParsedRelationshipData, ParsedNpcTraderData, BaseGeneratedEntity
                    )
                    from typing import Type # For Type[BaseGeneratedEntity]

                    model_map: Dict[str, Type[BaseGeneratedEntity]] = {
                        "npc": ParsedNpcData,
                        "item": ParsedItemData,
                        "quest": ParsedQuestData,
                        "faction": ParsedFactionData,
                        "location": ParsedLocationData,
                        "relationship": ParsedRelationshipData,
                        "npc_trader": ParsedNpcTraderData,
                    }
                    pydantic_model_for_parsing = model_map.get(actual_entity_type_str)

                    if not pydantic_model_for_parsing:
                        raise AssertionError(f"Test setup error: No Pydantic model in test's model_map for entity_type '{actual_entity_type_str}'")

                    # Ensure the mock data is dumped before parsing into the target Pydantic model
                    actual_parser_model_instance = parse_obj_as(pydantic_model_for_parsing, mock_test_data_entity.model_dump(mode='json'))
                else:
                    raise AssertionError(f"Cannot determine entity_type for mock entity: {type(mock_test_data_entity)}")

                entities_for_parsed_ai_data = [actual_parser_model_instance]
            except PydanticNativeValidationError as e:
                raise AssertionError(
                    f"Failed to convert mock entity {type(mock_test_data_entity)} "
                    f"to actual parser model: {e}"
                )
            self.mock_parse_and_validate.return_value = ParsedAiData(
                raw_ai_output="mock raw output for this single entity test",
                generated_entities=entities_for_parsed_ai_data # type: ignore
            )
        return await analyze_generated_content(
            session=self.mock_session, guild_id=self.guild_id, entity_type=entity_type,
            generation_context_json=context_json, use_real_ai=False, target_count=1
        )

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
        self.mock_get_entity_schemas.assert_called()

    async def test_calls_prepare_faction_prompt_for_faction(self):
        await self._run_analysis("faction", MockParsedFaction())
        self.mock_prepare_faction_prompt.assert_called_once_with(self.mock_session, self.guild_id)

    async def test_i18n_completeness_fail(self):
        npc_missing_ru_name = MockParsedNPC(name_i18n={"en": "Only English Name"})
        self.mock_get_rule.side_effect = lambda s,gid,key,d: {"required_languages":["en","ru"]} if key=="analysis:common:i18n_completeness" else d
        result = await self._run_analysis("npc", npc_missing_ru_name)
        self.assertIn("Missing or empty i18n field 'name_i18n' for required lang 'ru'.", result.analysis_reports[0].issues_found)

    async def test_description_length_too_short(self):
        item_short_desc = MockParsedItem(description_i18n={"en": "Short."})
        self.mock_get_rule.side_effect = lambda s,gid,key,d: {"min":20,"max":100} if key=="analysis:common:description_length:item" else d
        result = await self._run_analysis("item", item_short_desc)
        self.assertIn("Desc/Summary (en) length (6) outside range [20-100].", result.analysis_reports[0].issues_found)

    async def test_key_field_missing_for_item(self):
        item_dict_missing_required_fields = {"entity_type": "item", "static_id": "item1", "name_i18n": {"en": "Item With Missing Fields"}}
        with self.assertRaises(ValidationError) as context:
            # The generated_entities expects List[GeneratedEntity], not List[dict]
            # We need to wrap this dict in a way that parse_and_validate_ai_response would, or test parse_and_validate_ai_response itself.
            # For this specific test, we are testing Pydantic validation at the ParsedAiData level.
            # So, we need to simulate that the dict *would have been* parsed into a model instance.
            # This test might be more about the behavior of `parse_obj_as(ParsedItemData, ...)`
            # Let's assume the intention is to check if Pydantic validation catches this for ParsedItemData
            # when used within ParsedAiData. The error is that item_dict_missing_required_fields is a dict.
            # ParsedAiData expects a list of model instances.
            # This test is slightly misdirected if it's trying to test ParsedItemData validation *through* ParsedAiData with raw dicts.
            # However, Pydantic v2 can do implicit parsing here if the type hint is List[ParsedItemData] etc.
            # Given GeneratedEntity is a Union, this becomes complex.
            # The error `Argument of type "list[dict[str, Unknown]]" cannot be assigned...` indicates this is the issue.
            # To fix the type error for Pyright, we can cast, but the runtime error from Pydantic will still occur if not actual models.
            # For the purpose of this test, if it's about testing Pydantic's behavior with dicts,
            # the test should be structured to call `parse_obj_as(ParsedItemData, item_dict_missing_required_fields)` directly.
            # If it's about `ParsedAiData` specifically, then `item_dict_missing_required_fields` needs to be a model instance.
            # Let's assume the test *intends* to pass a dict and expects Pydantic to validate.
            # We can use `Any` to bypass Pyright here if the runtime behavior is what's being tested.
            from typing import Any as TypingAny
            ParsedAiData(raw_ai_output="mock raw output", generated_entities=[item_dict_missing_required_fields]) # type: ignore
        errors = context.exception.errors()
        self.assertTrue(any(err['type'] == 'missing' and isinstance(err['loc'], tuple) and 'ParsedItemData' in err['loc'] and 'item_type' in err['loc'] for err in errors))
        self.assertTrue(any(err['type'] == 'missing' and isinstance(err['loc'], tuple) and 'ParsedItemData' in err['loc'] and 'description_i18n' in err['loc'] for err in errors))

    async def test_npc_level_out_of_range(self):
        npc_high_level = MockParsedNPC(level=150)
        self.mock_get_rule.side_effect = lambda s,gid,key,d: {"min":1,"max":100} if key=="analysis:npc:field_range:level" else d
        result = await self._run_analysis("npc", npc_high_level)
        self.assertIn("NPC level (150) outside range [1-100].", result.analysis_reports[0].issues_found)

    async def test_quest_missing_steps(self):
        with self.assertRaises(AssertionError) as context:
            await self._run_analysis("quest", MockParsedQuest(steps=[]))
        self.assertIn("Quest must have at least one step", str(context.exception))

    async def test_quest_malformed_step(self):
        quest_valid_step = MockParsedQuest(steps=[{"step_order": 1, "title_i18n": {"en": "Valid Step Title", "ru": "Валидный Заголовок Шага"}, "description_i18n": {"en": "Valid Step Description Long Enough", "ru": "Валидное Описание Шага Достаточной Длины"}}])
        original_get_rule_side_effect = self.mock_get_rule.side_effect
        def specific_get_rule_side_effect(session, guild_id, key, default):
            if key == "analysis:common:i18n_completeness":
                 return {"required_languages": ["en", "ru"], "enabled_for_types": ["none"]}
            if key.startswith("analysis:common:description_length:") or \
               key.startswith("analysis:common:summary_length:") or \
               key.startswith("analysis:quest:field_value:title_i18n") or \
               key.startswith("analysis:quest:field_value:summary_i18n"):
                 return {"min_len": 1, "max_len": 5000, "enabled_for_types": ["none"]}
            return original_get_rule_side_effect(session, guild_id, key, default)
        self.mock_get_rule.side_effect = specific_get_rule_side_effect
        result = await self._run_analysis("quest", quest_valid_step)
        self.mock_get_rule.side_effect = original_get_rule_side_effect
        if result.analysis_reports:
            self.assertEqual(len(result.analysis_reports[0].issues_found), 0, f"Found: {result.analysis_reports[0].issues_found}")
        else:
            self.fail("No analysis report generated.")

    async def test_pydantic_validation_error_captured(self):
        custom_error_details_dicts = [{"loc": ("name_i18n",), "msg": "field required", "type": "value_error.missing", "input": {}}]
        self.mock_parse_and_validate.return_value = CustomValidationError(error_type="TestPydanticError", message="Mocked Pydantic Error", details=custom_error_details_dicts)
        result = await self._run_analysis("npc", None)
        self.assertEqual(len(result.analysis_reports), 1)
        report = result.analysis_reports[0]
        self.assertTrue(any("AI Response Validation Error: Mocked Pydantic Error" in issue for issue in report.issues_found))
        self.assertEqual(report.validation_errors, [json.dumps(d) for d in custom_error_details_dicts])

    async def test_filtering_of_parsed_entities_item_from_economic_prompt(self):
        mock_item = MockParsedItem(static_id="item_to_find")
        mock_trader_dict = MockParsedNPC(entity_type="npc_trader", static_id="trader_to_ignore").model_dump(mode='json')
        # Determine the correct Pydantic model types for parsing
        from src.core.ai_response_parser import MAPPING_ENTITY_TYPE_TO_PYDANTIC_MODEL, ParsedItemData, ParsedNpcTraderData
        actual_item_model_type = MAPPING_ENTITY_TYPE_TO_PYDANTIC_MODEL.get("item")
        actual_trader_model_type = MAPPING_ENTITY_TYPE_TO_PYDANTIC_MODEL.get("npc_trader")
        if not actual_item_model_type or not actual_trader_model_type:
            raise AssertionError("Could not find Pydantic models for item or npc_trader in mapping.")

        actual_item = parse_obj_as(actual_item_model_type, mock_item.model_dump(mode='json')) # type: ignore
        actual_trader = parse_obj_as(actual_trader_model_type, mock_trader_dict) # type: ignore
        self.mock_parse_and_validate.return_value = ParsedAiData(raw_ai_output="mock", generated_entities=[actual_item, actual_trader]) # type: ignore
        result = await self._run_analysis("item", None)
        self.assertEqual(len(result.analysis_reports), 1)
        self.assertEqual(result.analysis_reports[0].entity_data_preview.get("static_id"), "item_to_find")

    async def test_filtering_of_parsed_entities_npc_from_location_prompt(self):
        mock_npc = MockParsedNPC(static_id="npc_to_find")
        mock_item_in_loc = MockParsedItem(static_id="item_to_ignore")
        mock_npc_trader_dict = MockParsedNPC(entity_type="npc_trader", static_id="npc_trader_to_find").model_dump(mode='json')

        from src.core.ai_response_parser import MAPPING_ENTITY_TYPE_TO_PYDANTIC_MODEL
        item_model_type = MAPPING_ENTITY_TYPE_TO_PYDANTIC_MODEL.get("item")
        npc_model_type = MAPPING_ENTITY_TYPE_TO_PYDANTIC_MODEL.get("npc")
        npc_trader_model_type = MAPPING_ENTITY_TYPE_TO_PYDANTIC_MODEL.get("npc_trader")
        if not item_model_type or not npc_model_type or not npc_trader_model_type:
            raise AssertionError("Could not find Pydantic models for item, npc or npc_trader in mapping.")

        actual_item = parse_obj_as(item_model_type, mock_item_in_loc.model_dump(mode='json')) # type: ignore
        actual_npc = parse_obj_as(npc_model_type, mock_npc.model_dump(mode='json')) # type: ignore
        actual_npc_trader = parse_obj_as(npc_trader_model_type, mock_npc_trader_dict) # type: ignore

        self.mock_parse_and_validate.return_value = ParsedAiData(raw_ai_output="mock", generated_entities=[actual_item, actual_npc, actual_npc_trader]) # type: ignore
        result = await self._run_analysis("npc", None)
        self.assertEqual(len(result.analysis_reports), 1)
        self.assertEqual(result.analysis_reports[0].entity_data_preview.get("static_id"), "npc_to_find")


class TestAIAnalysisSystemMainFunction(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_session = AsyncMock(spec=AsyncSession)
        self.guild_id = 1

        self.patch_prepare_quest = patch('src.core.ai_analysis_system.prepare_quest_generation_prompt', new_callable=AsyncMock)
        self.patch_prepare_economic = patch('src.core.ai_analysis_system.prepare_economic_entity_generation_prompt', new_callable=AsyncMock)
        self.patch_prepare_general_loc = patch('src.core.ai_analysis_system.prepare_general_location_content_prompt', new_callable=AsyncMock)
        self.patch_prepare_faction = patch('src.core.ai_analysis_system.prepare_faction_relationship_generation_prompt', new_callable=AsyncMock)
        self.patch_get_entity_schemas = patch('src.core.ai_analysis_system.get_entity_schema_terms', new_callable=MagicMock) # Corrected patch target

        self.patch_parse_validate = patch('src.core.ai_analysis_system.parse_and_validate_ai_response', new_callable=AsyncMock)
        self.patch_get_rule = patch('src.core.ai_analysis_system.get_rule', new_callable=AsyncMock)
        self.patch_make_real_ai_call = patch('src.core.ai_analysis_system.make_real_ai_call', new_callable=AsyncMock)

        self.patch_analyze_item_balance = patch('src.core.ai_analysis_system._m_analyze_item_balance', new_callable=AsyncMock)
        self.patch_analyze_npc_balance = patch('src.core.ai_analysis_system._m_analyze_npc_balance', new_callable=AsyncMock)
        self.patch_analyze_quest_balance = patch('src.core.ai_analysis_system._m_analyze_quest_balance', new_callable=AsyncMock)
        self.patch_analyze_text_lore = patch('src.core.ai_analysis_system._m_analyze_text_content_lore', new_callable=AsyncMock)
        self.patch_analyze_props_structure = patch('src.core.ai_analysis_system._m_analyze_properties_json_structure', new_callable=AsyncMock)

        self.patch_guild_config_get_main = patch('src.core.crud.guild_crud.get', new_callable=AsyncMock)
        self.mock_guild_config_get_main = self.patch_guild_config_get_main.start()

        async def async_guild_config_mock_main(*args, **kwargs):
            gc = GuildConfig(id=self.guild_id, main_language="en")
            # Dynamically setting attributes for a mock. Use type: ignore for Pyright.
            setattr(gc, 'supported_languages_json', ["en", "ru"])
            setattr(gc, 'game_rules_json', {})
            setattr(gc, 'ai_generation_configs_json', {})
            setattr(gc, 'command_configs_json', {})
            setattr(gc, 'properties_json', {})
            return gc
        self.mock_guild_config_get_main.side_effect = async_guild_config_mock_main

        self.mock_prepare_quest_prompt = self.patch_prepare_quest.start()
        self.mock_prepare_economic_prompt = self.patch_prepare_economic.start()
        self.mock_prepare_general_loc_prompt = self.patch_prepare_general_loc.start()
        self.mock_prepare_faction_prompt = self.patch_prepare_faction.start()
        self.mock_get_entity_schemas = self.patch_get_entity_schemas.start()
        self.mock_parse_and_validate = self.patch_parse_validate.start()
        self.mock_get_rule = self.patch_get_rule.start()
        self.mock_make_real_ai_call = self.patch_make_real_ai_call.start()

        self.mock_analyze_item_balance = self.patch_analyze_item_balance.start()
        self.mock_analyze_npc_balance = self.patch_analyze_npc_balance.start()
        self.mock_analyze_quest_balance = self.patch_analyze_quest_balance.start()
        self.mock_analyze_text_lore = self.patch_analyze_text_lore.start()
        self.mock_analyze_props_structure = self.patch_analyze_props_structure.start()

        self.addCleanup(patch.stopall)

        self.mock_prepare_economic_prompt.return_value = "Economic Prompt"
        self.mock_get_entity_schemas.return_value = {}
        self.mock_get_rule.side_effect = lambda s, gid, key, default: default
        self.mock_make_real_ai_call.return_value = json.dumps([MockParsedItem().model_dump(mode='json')])

    async def test_analyze_generated_content_calls_item_specific_analyzers(self):
        mock_item_data = MockParsedItem(static_id="test_item1")
        from src.core.ai_response_parser import ParsedItemData # Import the actual Pydantic model
        # Convert MockParsedItem to ParsedItemData
        parsed_item_instance = parse_obj_as(ParsedItemData, mock_item_data.model_dump(mode='json'))
        self.mock_parse_and_validate.return_value = ParsedAiData(
            raw_ai_output="...", generated_entities=[parsed_item_instance]
        )
        await analyze_generated_content(self.mock_session, self.guild_id, "item", target_count=1)
        self.mock_analyze_item_balance.assert_called_once()
        self.mock_analyze_text_lore.assert_called()
        self.mock_analyze_props_structure.assert_called_once()
        self.mock_analyze_npc_balance.assert_not_called()
        self.mock_analyze_quest_balance.assert_not_called()

    async def test_analyze_generated_content_calls_npc_specific_analyzers(self):
        mock_npc_data = MockParsedNPC(static_id="test_npc1")
        from src.core.ai_response_parser import ParsedNpcData # Import the actual Pydantic model
        # Convert MockParsedNPC to ParsedNpcData
        parsed_npc_instance = parse_obj_as(ParsedNpcData, mock_npc_data.model_dump(mode='json'))
        self.mock_parse_and_validate.return_value = ParsedAiData(
            raw_ai_output="...", generated_entities=[parsed_npc_instance]
        )
        await analyze_generated_content(self.mock_session, self.guild_id, "npc", target_count=1)
        self.mock_analyze_npc_balance.assert_called_once()
        self.mock_analyze_text_lore.assert_called()
        self.mock_analyze_props_structure.assert_called_once()
        self.mock_analyze_item_balance.assert_not_called()

    async def test_i18n_completeness_uses_guild_config_languages(self):
        original_side_effect = self.mock_guild_config_get_main.side_effect
        async def specific_guild_config_side_effect(*args, **kwargs):
            gc = GuildConfig(id=self.guild_id, main_language="en")
            setattr(gc, 'supported_languages_json', ["en", "de"]) # Use setattr for dynamic attributes in mocks
            return gc
        self.mock_guild_config_get_main.side_effect = specific_guild_config_side_effect

        item_missing_de_mock = MockParsedItem(name_i18n={"en": "Test Item"})
        from src.core.ai_response_parser import ParsedItemData
        parsed_item_instance = parse_obj_as(ParsedItemData, item_missing_de_mock.model_dump(mode='json'))
        self.mock_parse_and_validate.return_value = ParsedAiData(
            raw_ai_output="...", generated_entities=[parsed_item_instance]
        )
        result = await analyze_generated_content(self.mock_session, self.guild_id, "item", target_count=1)

        self.mock_guild_config_get_main.assert_called_once_with(self.mock_session, id=self.guild_id)
        report = result.analysis_reports[0]
        self.assertIn("Missing or empty i18n field 'name_i18n' for required lang 'de'.", report.issues_found)
        self.assertNotIn("Missing or empty i18n field 'name_i18n' for required lang 'ru'.", report.issues_found)

        self.mock_guild_config_get_main.side_effect = original_side_effect

    async def test_uniqueness_check_duplicate_static_id(self):
        item1_mock = MockParsedItem(static_id="dup_id", name_i18n={"en":"Item One"})
        item2_mock = MockParsedItem(static_id="dup_id", name_i18n={"en":"Item Two"})
        from src.core.ai_response_parser import ParsedItemData
        parsed_item1 = parse_obj_as(ParsedItemData, item1_mock.model_dump(mode='json'))
        parsed_item2 = parse_obj_as(ParsedItemData, item2_mock.model_dump(mode='json'))
        self.mock_parse_and_validate.return_value = ParsedAiData(
            raw_ai_output="...", generated_entities=[parsed_item1, parsed_item2]
        )
        result = await analyze_generated_content(self.mock_session, self.guild_id, "item", target_count=2)
        self.assertIn("Duplicate static_id 'dup_id' found across generated entities (indices 0 and 1).", result.analysis_reports[0].issues_found)
        self.assertIn("Duplicate static_id 'dup_id' found across generated entities (indices 0 and 1).", result.analysis_reports[1].issues_found)
        self.assertEqual(result.analysis_reports[0].quality_score_details["batch_static_id_uniqueness"], 0.1)
        self.assertEqual(result.analysis_reports[1].quality_score_details["batch_static_id_uniqueness"], 0.1)

    async def test_uniqueness_check_duplicate_name_i18n(self):
        item1_mock = MockParsedItem(static_id="item1", name_i18n={"en":"Duplicate Name", "ru": "Уникальное Имя1"})
        item2_mock = MockParsedItem(static_id="item2", name_i18n={"en":"Duplicate Name", "ru": "Уникальное Имя2"})
        from src.core.ai_response_parser import ParsedItemData
        parsed_item1 = parse_obj_as(ParsedItemData, item1_mock.model_dump(mode='json'))
        parsed_item2 = parse_obj_as(ParsedItemData, item2_mock.model_dump(mode='json'))
        self.mock_parse_and_validate.return_value = ParsedAiData(
            raw_ai_output="...", generated_entities=[parsed_item1, parsed_item2]
        )
        result = await analyze_generated_content(self.mock_session, self.guild_id, "item", target_count=2)
        self.assertIn("Duplicate name/title 'Duplicate Name' (lang: en) found across generated entities (indices 0 and 1).", result.analysis_reports[0].issues_found)
        self.assertIn("Duplicate name/title 'Duplicate Name' (lang: en) found across generated entities (indices 0 and 1).", result.analysis_reports[1].issues_found)
        self.assertEqual(result.analysis_reports[0].quality_score_details["batch_name_uniqueness_en"], 0.1)
        self.assertEqual(result.analysis_reports[1].quality_score_details["batch_name_uniqueness_en"], 0.1)
        self.assertEqual(result.analysis_reports[0].quality_score_details.get("batch_name_uniqueness_ru"), 1.0)
        self.assertEqual(result.analysis_reports[1].quality_score_details.get("batch_name_uniqueness_ru"), 1.0)

    async def test_score_aggregation(self):
        mock_item_data_mock = MockParsedItem()
        from src.core.ai_response_parser import ParsedItemData
        parsed_item_instance = parse_obj_as(ParsedItemData, mock_item_data_mock.model_dump(mode='json'))
        self.mock_parse_and_validate.return_value = ParsedAiData(
            raw_ai_output="...", generated_entities=[parsed_item_instance]
        )
        async def mock_item_balance_side_effect(data, report, session, guild_id):
            report.balance_score_details["value_vs_prop"] = 0.8
            report.balance_score_details["damage_cap"] = 0.9
        self.mock_analyze_item_balance.side_effect = mock_item_balance_side_effect
        async def mock_text_lore_side_effect(text, field, report, session, guild_id, entity_type):
            if field == "name_i18n": report.lore_score_details["name_i18n.en_restricted"] = 0.9
            if field == "description_i18n": report.lore_score_details["description_i18n.en_restricted"] = 0.7
        self.mock_analyze_text_lore.side_effect = mock_text_lore_side_effect
        async def mock_props_structure_side_effect(data, report, session, guild_id, entity_type):
            report.quality_score_details["properties_json_structure_required"] = 0.95
        self.mock_analyze_props_structure.side_effect = mock_props_structure_side_effect

        result = await analyze_generated_content(self.mock_session, self.guild_id, "item", target_count=1)
        report = result.analysis_reports[0]

        self.assertAlmostEqual(report.balance_score if report.balance_score is not None else -1.0, (0.8 + 0.9) / 2)
        self.assertAlmostEqual(report.lore_score_details.get("overall_lore_avg", -1.0), (0.9 + 0.7) / 2)

        expected_quality_avg = (
            0.95 +
            1.0 +
            1.0 +
            1.0 +
            1.0 +
            1.0 +
            1.0 +
            1.0
        ) / 8
        self.assertAlmostEqual(report.quality_score_details.get("overall_quality_avg", -1.0), expected_quality_avg, places=5)


if __name__ == '__main__':
    unittest.main()
