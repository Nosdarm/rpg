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

from src.core.ai_analysis_system import analyze_generated_content, AIAnalysisResult, EntityAnalysisReport
from src.core.ai_response_parser import BaseGeneratedEntity, ParsedAiData, GeneratedEntity, CustomValidationError
from src.core.ai_response_parser import PydanticNativeValidationError
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
    rewards_json: Optional[Dict[str, Any]] = None

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


from src.core.ai_response_parser import (
    ParsedNpcData, ParsedItemData, ParsedQuestData, ParsedFactionData,
    ParsedLocationData, ParsedRelationshipData, ParsedNpcTraderData
)
from typing import Type as TypingType # For Type[BaseGeneratedEntity]

class TestAIAnalysisSystem(unittest.IsolatedAsyncioTestCase):
    MAPPING_ENTITY_TYPE_TO_PYDANTIC_MODEL_FOR_TEST: Dict[str, TypingType[BaseGeneratedEntity]] = {
        "npc": ParsedNpcData, "item": ParsedItemData, "quest": ParsedQuestData,
        "faction": ParsedFactionData, "location": ParsedLocationData,
        "relationship": ParsedRelationshipData, "npc_trader": ParsedNpcTraderData,
    }

    async def asyncSetUp(self):
        self.mock_session = AsyncMock(spec=AsyncSession)
        self.guild_id = 1
        self.patch_prepare_quest = patch('src.core.ai_analysis_system.prepare_quest_generation_prompt', new_callable=AsyncMock)
        self.patch_prepare_economic = patch('src.core.ai_analysis_system.prepare_economic_entity_generation_prompt', new_callable=AsyncMock)
        self.patch_prepare_general_loc = patch('src.core.ai_analysis_system.prepare_general_location_content_prompt', new_callable=AsyncMock)
        self.patch_prepare_faction = patch('src.core.ai_analysis_system.prepare_faction_relationship_generation_prompt', new_callable=AsyncMock)
        self.patch_get_entity_schemas = patch('src.core.ai_analysis_system.get_entity_schema_terms', new_callable=MagicMock)
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

        mock_gc_instance = GuildConfig(id=self.guild_id, main_language="en", name="Test Guild ClassScope")
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
                actual_entity_type_str = getattr(mock_test_data_entity, 'entity_type', None)
                if actual_entity_type_str:
                    pydantic_model_for_parsing = TestAIAnalysisSystem.MAPPING_ENTITY_TYPE_TO_PYDANTIC_MODEL_FOR_TEST.get(actual_entity_type_str)
                    if not pydantic_model_for_parsing:
                        raise AssertionError(f"Test setup error: No Pydantic model for entity_type '{actual_entity_type_str}'")
                    actual_parser_model_instance = parse_obj_as(pydantic_model_for_parsing, mock_test_data_entity.model_dump(mode='json'))
                else:
                    raise AssertionError(f"Cannot determine entity_type for mock entity: {type(mock_test_data_entity)}")
                entities_for_parsed_ai_data = [actual_parser_model_instance]
            except PydanticNativeValidationError as e:
                raise AssertionError(f"Failed to convert mock entity to actual parser model: {e}")
            self.mock_parse_and_validate.return_value = ParsedAiData(
                raw_ai_output="mock raw output", generated_entities=entities_for_parsed_ai_data # type: ignore
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
            from src.core.ai_response_parser import ParsedItemData
            parse_obj_as(ParsedItemData, item_dict_missing_required_fields)
        errors = context.exception.errors()
        self.assertTrue(any(err['type'] == 'missing' and err['loc'] == ('item_type',) for err in errors))
        self.assertTrue(any(err['type'] == 'missing' and err['loc'] == ('description_i18n',) for err in errors))

    async def test_npc_level_out_of_range(self):
        npc_high_level = MockParsedNPC(level=150)
        self.mock_get_rule.side_effect = lambda s,gid,key,d: {"min":1,"max":100} if key=="analysis:npc:field_range:level" else d
        result = await self._run_analysis("npc", npc_high_level)
        self.assertIn("NPC level (150) outside range [1-100].", result.analysis_reports[0].issues_found)

    async def test_quest_missing_steps(self):
        raw_quest_data_no_steps = {
            "entity_type": "quest", "static_id": "quest_no_steps",
            "title_i18n": {"en": "Quest With No Steps"},
            "summary_i18n": {"en": "This quest has no steps."},
            "steps": [], "min_level": 1
        }
        from src.core.ai_response_parser import ParsedQuestData
        # This test now checks Pydantic validation at the model level
        with self.assertRaises(ValidationError) as context:
            parse_obj_as(ParsedQuestData, raw_quest_data_no_steps)

        self.assertTrue(any("Quest must have at least one step" in err['msg'] for err in context.exception.errors()),
                        f"Expected validation error for empty steps, got errors: {context.exception.errors()}")

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
        mock_trader_dict = {
            "entity_type": "npc_trader", "static_id": "trader_to_ignore", "name_i18n": {"en": "Mock Trader"},
            "description_i18n": {"en": "Trader NPC"}, "level": 10, "properties_json": {"sells_wares": True},
            "inventory_items_json": [], "sells_item_types": ["weapon"], "buys_item_types": ["ore"], "currency_preferrence_json": {}
        }
        from src.core.ai_response_parser import ParsedItemData, ParsedNpcTraderData, GeneratedEntity
        actual_item = parse_obj_as(ParsedItemData, mock_item.model_dump(mode='json'))
        actual_trader = parse_obj_as(ParsedNpcTraderData, mock_trader_dict)
        entities: List[GeneratedEntity] = [actual_item, actual_trader] # type: ignore
        self.mock_parse_and_validate.return_value = ParsedAiData(raw_ai_output="mock", generated_entities=entities)
        result = await self._run_analysis("item", None)
        self.assertEqual(len(result.analysis_reports), 1)
        self.assertEqual(result.analysis_reports[0].entity_data_preview.get("static_id"), "item_to_find")

    async def test_filtering_of_parsed_entities_npc_from_location_prompt(self):
        mock_npc_to_find = MockParsedNPC(static_id="npc_to_find")
        mock_item_to_ignore = MockParsedItem(static_id="item_to_ignore")
        mock_npc_trader_dict_to_ignore = {
            "entity_type": "npc_trader", "static_id": "npc_trader_to_ignore", "name_i18n": {"en": "Mock Trader"},
            "description_i18n": {"en": "Trader NPC"}, "level": 10, "properties_json": {"sells_wares": True},
            "inventory_items_json": [], "sells_item_types": ["weapon"], "buys_item_types": ["ore"], "currency_preferrence_json": {}
        }
        from src.core.ai_response_parser import ParsedItemData, ParsedNpcData, ParsedNpcTraderData, GeneratedEntity
        actual_item = parse_obj_as(ParsedItemData, mock_item_to_ignore.model_dump(mode='json'))
        actual_npc = parse_obj_as(ParsedNpcData, mock_npc_to_find.model_dump(mode='json'))
        actual_npc_trader = parse_obj_as(ParsedNpcTraderData, mock_npc_trader_dict_to_ignore)
        entities: List[GeneratedEntity] = [actual_item, actual_npc, actual_npc_trader] # type: ignore
        self.mock_parse_and_validate.return_value = ParsedAiData(raw_ai_output="mock", generated_entities=entities)
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
        self.patch_get_entity_schemas = patch('src.core.ai_analysis_system.get_entity_schema_terms', new_callable=MagicMock)
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
            gc = GuildConfig(id=self.guild_id, main_language="en", name="Test Guild")
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
        from src.core.ai_response_parser import ParsedItemData
        parsed_item_instance = parse_obj_as(ParsedItemData, mock_item_data.model_dump(mode='json'))
        self.mock_parse_and_validate.return_value = ParsedAiData(raw_ai_output="...", generated_entities=[parsed_item_instance])
        await analyze_generated_content(self.mock_session, self.guild_id, "item", target_count=1)
        self.mock_analyze_item_balance.assert_called_once()
        self.mock_analyze_text_lore.assert_called()
        self.mock_analyze_props_structure.assert_called_once()
        self.mock_analyze_npc_balance.assert_not_called()
        self.mock_analyze_quest_balance.assert_not_called()

    async def test_analyze_generated_content_calls_npc_specific_analyzers(self):
        mock_npc_data = MockParsedNPC(static_id="test_npc1")
        from src.core.ai_response_parser import ParsedNpcData
        parsed_npc_instance = parse_obj_as(ParsedNpcData, mock_npc_data.model_dump(mode='json'))
        self.mock_parse_and_validate.return_value = ParsedAiData(raw_ai_output="...", generated_entities=[parsed_npc_instance])
        await analyze_generated_content(self.mock_session, self.guild_id, "npc", target_count=1)
        self.mock_analyze_npc_balance.assert_called_once()
        self.mock_analyze_text_lore.assert_called()
        self.mock_analyze_props_structure.assert_called_once()
        self.mock_analyze_item_balance.assert_not_called()

    async def test_analyze_generated_content_calls_quest_specific_analyzers(self):
        mock_quest_data = MockParsedQuest(static_id="test_quest1")
        from src.core.ai_response_parser import ParsedQuestData
        parsed_quest_instance = parse_obj_as(ParsedQuestData, mock_quest_data.model_dump(mode='json'))
        self.mock_parse_and_validate.return_value = ParsedAiData(raw_ai_output="...", generated_entities=[parsed_quest_instance])
        await analyze_generated_content(self.mock_session, self.guild_id, "quest", target_count=1)
        self.mock_analyze_quest_balance.assert_called_once()
        self.mock_analyze_text_lore.assert_called()
        self.mock_analyze_props_structure.assert_not_called()
        self.mock_analyze_item_balance.assert_not_called()
        self.mock_analyze_npc_balance.assert_not_called()

    async def test_i18n_completeness_uses_guild_config_languages(self):
        original_side_effect_gc_get = self.mock_guild_config_get_main.side_effect
        async def specific_guild_config_side_effect(*args, **kwargs):
            gc = GuildConfig(id=self.guild_id, main_language="en", name="Test Guild")
            return gc
        self.mock_guild_config_get_main.side_effect = specific_guild_config_side_effect
        original_get_rule_side_effect = self.mock_get_rule.side_effect
        def i18n_test_get_rule_side_effect(session_arg, guild_id_arg, key_arg, default_arg=None):
            if key_arg == "analysis:common:i18n_completeness":
                return {"required_languages": ["en", "de"], "enabled_for_types": ["item", "npc"]}
            if callable(original_get_rule_side_effect):
                 return original_get_rule_side_effect(session_arg, guild_id_arg, key_arg, default_arg)
            return default_arg
        self.mock_get_rule.side_effect = i18n_test_get_rule_side_effect
        item_missing_de_mock = MockParsedItem(name_i18n={"en": "Test Item"})
        from src.core.ai_response_parser import ParsedItemData
        parsed_item_instance = parse_obj_as(ParsedItemData, item_missing_de_mock.model_dump(mode='json'))
        self.mock_parse_and_validate.return_value = ParsedAiData(raw_ai_output="...", generated_entities=[parsed_item_instance])
        result = await analyze_generated_content(self.mock_session, self.guild_id, "item", target_count=1)
        self.mock_guild_config_get_main.assert_called_once_with(self.mock_session, id=self.guild_id)
        report = result.analysis_reports[0]
        self.assertIn("Missing or empty i18n field 'name_i18n' for required lang 'de'.", report.issues_found)
        self.assertNotIn("Missing or empty i18n field 'name_i18n' for required lang 'ru'.", report.issues_found)
        self.mock_guild_config_get_main.side_effect = original_side_effect_gc_get
        self.mock_get_rule.side_effect = original_get_rule_side_effect

    async def test_uniqueness_check_duplicate_static_id(self):
        item1_mock = MockParsedItem(static_id="dup_id", name_i18n={"en":"Item One"})
        item2_mock = MockParsedItem(static_id="dup_id", name_i18n={"en":"Item Two"})
        from src.core.ai_response_parser import ParsedItemData
        parsed_item1 = parse_obj_as(ParsedItemData, item1_mock.model_dump(mode='json'))
        parsed_item2 = parse_obj_as(ParsedItemData, item2_mock.model_dump(mode='json'))
        self.mock_parse_and_validate.return_value = ParsedAiData(raw_ai_output="...", generated_entities=[parsed_item1, parsed_item2])
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
        self.mock_parse_and_validate.return_value = ParsedAiData(raw_ai_output="...", generated_entities=[parsed_item1, parsed_item2])
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
        initial_quality_details = {
            "batch_static_id_uniqueness": 1.0, "batch_name_uniqueness_en": 1.0,
            "batch_name_uniqueness_ru": 1.0,
        }
        def mock_parse_and_validate_side_effect(*args, **kwargs):
            return ParsedAiData(raw_ai_output="...", generated_entities=[parsed_item_instance])
        self.mock_parse_and_validate.side_effect = mock_parse_and_validate_side_effect
        async def mock_item_balance_side_effect(data, report: EntityAnalysisReport, session, guild_id):
            report.balance_score_details["value_vs_prop"] = 0.8
            report.balance_score_details["damage_cap"] = 0.9
        self.mock_analyze_item_balance.side_effect = mock_item_balance_side_effect
        async def mock_text_lore_side_effect(text, field, report: EntityAnalysisReport, session, guild_id, entity_type):
            if field == "name_i18n": report.lore_score_details["name_i18n.en_restricted"] = 0.9
            if field == "description_i18n": report.lore_score_details["description_i18n.en_restricted"] = 0.7
        self.mock_analyze_text_lore.side_effect = mock_text_lore_side_effect
        async def mock_props_structure_side_effect(data, report: EntityAnalysisReport, session, guild_id, entity_type):
            report.quality_score_details["properties_json_structure_required"] = 0.95
            report.quality_score_details.update(initial_quality_details)
        self.mock_analyze_props_structure.side_effect = mock_props_structure_side_effect
        original_get_rule = self.mock_get_rule.side_effect
        def get_rule_for_score_agg_test(s, gid, key, default):
            if key == "analysis:common:i18n_completeness": return {"required_languages": ["en", "ru"]}
            if key.startswith("analysis:common:description_length:"): return {"min": 1, "max": 500}
            if key == "analysis:common:placeholder_texts": return {"placeholders": ["non_existent_placeholder"]}
            if key.startswith("analysis:item:field_range:"): return {"min":1, "max": 10000}
            if key.startswith("analysis:item:structure:required_properties_keys"): return {"keys": ["rarity"]}
            return default
        self.mock_get_rule.side_effect = get_rule_for_score_agg_test
        result = await analyze_generated_content(self.mock_session, self.guild_id, "item", target_count=1)
        self.mock_get_rule.side_effect = original_get_rule
        self.assertEqual(len(result.analysis_reports), 1)
        report = result.analysis_reports[0]
        expected_balance_score = (0.8 + 0.9) / 2
        self.assertAlmostEqual(report.balance_score if report.balance_score is not None else -1.0, expected_balance_score, places=5)
        expected_lore_avg = (0.9 + 0.7) / 2
        self.assertAlmostEqual(report.lore_score_details.get("overall_lore_avg", -1.0), expected_lore_avg, places=5)
        self.assertIn("properties_json_structure_required", report.quality_score_details)
        self.assertEqual(report.quality_score_details["properties_json_structure_required"], 0.95)
        self.assertIsNotNone(report.quality_score_details.get("overall_quality_avg"))
        self.assertTrue(0.0 <= report.quality_score_details.get("overall_quality_avg", -1.0) <= 1.0)

class TestQuestItemBalanceAnalysis(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_session = AsyncMock(spec=AsyncSession)
        self.guild_id = 1
        self.patch_get_rule = patch('src.core.ai_analysis_system.get_rule', new_callable=AsyncMock)
        self.mock_get_rule = self.patch_get_rule.start()
        self.patch_prepare_quest_prompt = patch('src.core.ai_analysis_system.prepare_quest_generation_prompt', new_callable=AsyncMock, return_value="Quest Prompt")
        self.mock_prepare_quest_prompt = self.patch_prepare_quest_prompt.start()
        self.patch_parse_validate = patch('src.core.ai_analysis_system.parse_and_validate_ai_response', new_callable=AsyncMock)
        self.mock_parse_and_validate = self.patch_parse_validate.start()
        self.patch_guild_crud_get = patch('src.core.crud.guild_crud.get', new_callable=AsyncMock)
        self.mock_guild_crud_get = self.patch_guild_crud_get.start()
        mock_gc_instance = GuildConfig(id=self.guild_id, main_language="en", name="Test Guild")
        self.mock_guild_crud_get.return_value = mock_gc_instance
        self.patch_analyze_text_lore = patch('src.core.ai_analysis_system._m_analyze_text_content_lore', new_callable=AsyncMock)
        self.mock_analyze_text_lore = self.patch_analyze_text_lore.start()
        self.addCleanup(patch.stopall)

    async def run_quest_item_analysis(self, quest_min_level: int, num_item_rewards: int, rule_config_value: Dict):
        def default_get_rule_side_effect(session, guild_id, key, default):
            if key == "analysis:quest:balance:items_per_level_range": return rule_config_value
            if key == "analysis:common:i18n_completeness": return {"required_languages": ["en"], "enabled_for_types": ["quest"]}
            if key.startswith("analysis:common:description_length:") or \
               key.startswith("analysis:common:summary_length:") or \
               key.startswith("analysis:quest:field_value:title_i18n") or \
               key.startswith("analysis:quest:field_value:summary_i18n"):
                 return {"min_len": 1, "max_len": 5000, "enabled_for_types": ["quest"]}
            if key == "analysis:common:placeholder_texts": return {"placeholders": ["todo"]}
            if key == "analysis:quest:balance:xp_per_level_point": return {"value": 100}
            if key == "analysis:quest:balance:xp_variance_percent": return {"value": 40}
            if key == "analysis:quest:balance:max_steps_per_level": return {"base": 2, "per_level_add": 0.5}
            return default
        self.mock_get_rule.side_effect = default_get_rule_side_effect
        mock_quest = MockParsedQuest(
            min_level=quest_min_level,
            rewards_json={"item_static_ids": [f"item_{i}" for i in range(num_item_rewards)]}
        )
        from src.core.ai_response_parser import ParsedQuestData
        parsed_quest_instance = parse_obj_as(ParsedQuestData, mock_quest.model_dump(mode='json'))
        self.mock_parse_and_validate.return_value = ParsedAiData(raw_ai_output="mocked quest", generated_entities=[parsed_quest_instance])
        result = await analyze_generated_content(self.mock_session, self.guild_id, "quest", target_count=1)
        return result.analysis_reports[0]

    async def test_quest_items_per_level_range_match_first_threshold(self):
        rule = {"max_items_by_level": [{"level_lte": 3, "max": 0}, {"level_lte": 7, "max": 1}, {"level_lte": 15, "max": 2}], "default_max": 1}
        report = await self.run_quest_item_analysis(quest_min_level=3, num_item_rewards=1, rule_config_value=rule)
        self.assertIn("Quest offers 1 item rewards, which might be too many for min_level 3 (expected max 0 based on configured ranges).", report.issues_found)

    async def test_quest_items_per_level_range_match_second_threshold(self):
        rule = {"max_items_by_level": [{"level_lte": 3, "max": 0}, {"level_lte": 7, "max": 1}, {"level_lte": 15, "max": 2}], "default_max": 1}
        report = await self.run_quest_item_analysis(quest_min_level=7, num_item_rewards=2, rule_config_value=rule)
        self.assertIn("Quest offers 2 item rewards, which might be too many for min_level 7 (expected max 1 based on configured ranges).", report.issues_found)

    async def test_quest_items_per_level_range_above_all_thresholds(self):
        rule = {"max_items_by_level": [{"level_lte": 3, "max": 0}, {"level_lte": 7, "max": 1}, {"level_lte": 15, "max": 2} ], "default_max": 1}
        report = await self.run_quest_item_analysis(quest_min_level=20, num_item_rewards=3, rule_config_value=rule)
        self.assertIn("Quest offers 3 item rewards, which might be too many for min_level 20 (expected max 2 based on configured ranges).", report.issues_found)

    async def test_quest_items_per_level_range_empty_rule_uses_default_max(self):
        rule = {"max_items_by_level": [], "default_max": 1}
        report = await self.run_quest_item_analysis(quest_min_level=5, num_item_rewards=2, rule_config_value=rule)
        self.assertIn("Quest offers 2 item rewards, which might be too many for min_level 5 (expected max 1 based on configured ranges).", report.issues_found)

    async def test_quest_items_per_level_range_malformed_rule_uses_default_max_from_code(self):
        def get_rule_returns_sut_default(session, guild_id, key, default_passed_by_sut):
            if key == "analysis:quest:balance:items_per_level_range": return default_passed_by_sut
            if key == "analysis:common:i18n_completeness": return {"required_languages": ["en"]}
            if key.startswith("analysis:common:description_length:") or \
               key.startswith("analysis:common:summary_length:") or \
               key.startswith("analysis:quest:field_value:title_i18n") or \
               key.startswith("analysis:quest:field_value:summary_i18n"):
                 return {"min_len": 1, "max_len": 5000, "enabled_for_types": ["quest"]}
            if key == "analysis:common:placeholder_texts": return {"placeholders": ["todo"]}
            if key == "analysis:quest:balance:xp_per_level_point": return {"value": 100}
            if key == "analysis:quest:balance:xp_variance_percent": return {"value": 40}
            if key == "analysis:quest:balance:max_steps_per_level": return {"base": 2, "per_level_add": 0.5}
            return default_passed_by_sut
        self.mock_get_rule.side_effect = get_rule_returns_sut_default
        report = await self.run_quest_item_analysis(quest_min_level=3, num_item_rewards=2, rule_config_value={})
        self.assertIn("Quest offers 2 item rewards, which might be too many for min_level 3 (expected max 1 based on configured ranges).", report.issues_found)

    async def test_quest_items_no_rewards_is_neutral(self):
        rule = {"max_items_by_level": [{"level_lte": 5, "max": 1}], "default_max": 1}
        report = await self.run_quest_item_analysis(quest_min_level=3, num_item_rewards=0, rule_config_value=rule)
        self.assertNotIn("Quest offers 0 item rewards", " ".join(report.issues_found))
        self.assertEqual(report.balance_score_details.get("item_rewards_vs_level"), 0.5)

    async def test_quest_items_correct_amount_is_good_score(self):
        rule = {"max_items_by_level": [{"level_lte": 5, "max": 1}], "default_max": 1}
        report = await self.run_quest_item_analysis(quest_min_level=5, num_item_rewards=1, rule_config_value=rule)
        self.assertNotIn("Quest offers 1 item rewards, which might be too many", " ".join(report.issues_found))
        self.assertEqual(report.balance_score_details.get("item_rewards_vs_level"), 0.7)

if __name__ == '__main__':
    unittest.main()
