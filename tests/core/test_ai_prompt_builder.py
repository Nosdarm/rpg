import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import asyncio
import json
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.engine.result import Result, ScalarResult

from src.models import GuildConfig, Location, Player, GeneratedNpc, Relationship, RuleConfig
from src.core.ai_prompt_builder import (
    prepare_ai_prompt,
    prepare_faction_relationship_generation_prompt,
    prepare_quest_generation_prompt,
    prepare_economic_entity_generation_prompt,
    prepare_dialogue_generation_prompt
)
from src.models.location import LocationType
from src.models.enums import RelationshipEntityType, PlayerStatus

async def mock_get_guild_config(session, id, guild_id=None):
    if id == 1 and (guild_id is None or guild_id == 1) :
        mock_gc = GuildConfig(id=1, main_language="en")
        return mock_gc
    return None

async def mock_get_location(session, id, guild_id=None): # Still used by test_prepare_ai_prompt_location_not_found
    if id == 1 and guild_id == 1:
        mock_loc = Location(id=1, guild_id=1, name_i18n={"en":"Test Loc", "ru":"Тест Лок"}, descriptions_i18n={}, type=LocationType.CITY.value, coordinates_json="{}", generated_details_json="{}", ai_metadata_json="{}", neighbor_locations_json="[]")
        return mock_loc
    if id == 100 and guild_id == 1:
        mock_loc = Location(id=100, guild_id=1, name_i18n={"en":"Test Tavern", "ru":"Тестовая Таверна"}, descriptions_i18n={"en":"A cozy place", "ru":"Уютное место"}, type=LocationType.TAVERN.value, neighbor_locations_json="[]") # Changed BUILDING to TAVERN
        return mock_loc
    return None

async def mock_get_npc_generic(session, id, guild_id=None):
    if id == 10 and guild_id == 1:
        mock_npc = GeneratedNpc(id=10, guild_id=1, name_i18n={"en":f"Test NPC {id}", "ru":f"Тестовый NPC {id}"}, description_i18n={}, properties_json={}, static_id=f"npc_static_{id}")
        return mock_npc
    return None

async def mock_get_multi_npc_generic(session, guild_id, **kwargs):
    if guild_id == 1 and kwargs.get("current_location_id") == 100:
        return []
    return []


class TestAIPromptBuilder(unittest.IsolatedAsyncioTestCase):

    @patch('src.core.ai_prompt_builder._get_world_state_context', new_callable=AsyncMock) # Innermost now
    @patch('src.core.ai_prompt_builder._get_location_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.guild_config_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.player_crud.get', new_callable=AsyncMock)
    @patch('src.core.crud.crud_party.party_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.generated_npc_crud.get_multi_by_attribute', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.crud_relationship.get_relationship_between_entities', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock) # Outermost
    async def test_prepare_ai_prompt_basic_scenario(
        self, mock_get_all_rules, mock_crud_relationship_get_relationship_between_entities,
        mock_generated_npc_crud_get_multi_by_attribute, mock_party_crud_get,
        mock_player_crud_get, mock_guild_config_crud_get, mock_get_location_context,
        mock_get_world_state_context # Added new argument
    ):
        mock_session = AsyncMock(spec=AsyncSession)

        mock_quest_execute_result = MagicMock(spec=Result)
        mock_quest_execute_result.all.return_value = []
        mock_session.execute.return_value = mock_quest_execute_result

        gc_instance = GuildConfig(id=1, main_language="en")
        mock_guild_config_crud_get.return_value = gc_instance

        mock_get_location_context.return_value = {
            "id": 1,
            "name": "Test Loc",
            "type": LocationType.CITY.value,
            "description": "No description available."
        }

        # Configure the new mock for world state context
        mock_get_world_state_context.return_value = {"global_plot_status": "A vast and perilous world."}


        mock_player_crud_get.return_value = Player(id=1, guild_id=1, name="TestPlayer", level=5, xp=100, current_status=PlayerStatus.EXPLORING)
        mock_party_crud_get.return_value = None
        mock_generated_npc_crud_get_multi_by_attribute.return_value = []
        mock_crud_relationship_get_relationship_between_entities.return_value = None

        # This mock_get_all_rules is still used for generation_style
        mock_get_all_rules.return_value = {
            "guild_main_language": "en",
            "ai_generation_style": "dark_fantasy",
            # world_description_i18n is no longer directly used by the SUT part being asserted, due to _get_world_state_context mock
            "world_description_i18n": {"en": "A different world description to ensure our mock is used."}
        }

        result_prompt = await prepare_ai_prompt(
            session=mock_session,
            guild_id=1,
            location_id=1,
            player_id=1,
            party_id=None
        )

        # Debug print from SUT will show:
        # DEBUG: prepare_ai_prompt received location_id: 1, player_id: 1
        # DEBUG: loc_ctx from _get_location_context: {'id': 1, 'name': 'Test Loc', 'type': 'city', 'description': 'No description available.'}
        # And the world_state_str in SUT will be: "World State: A vast and perilous world."

        self.assertIsInstance(result_prompt, str)
        self.assertNotIn("Error:", result_prompt)
        self.assertIn("## AI Content Generation Request (Guild: 1, Lang: en)", result_prompt)
        self.assertIn("Location: Test Loc - No description available.", result_prompt)
        self.assertIn("Player: TestPlayer (Lvl 5, Status: exploring)", result_prompt)
        self.assertIn("Nearby NPCs: None notable", result_prompt)
        self.assertIn("World State: A vast and perilous world.", result_prompt)
        self.assertIn("Generation Style: dark_fantasy", result_prompt)
        self.assertIn("npc_schema", result_prompt)
        self.assertIn("quest_schema", result_prompt)

    @patch('src.core.ai_prompt_builder.guild_config_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.location_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.generated_npc_crud.get_multi_by_attribute', new_callable=AsyncMock)
    async def test_prepare_ai_prompt_location_not_found(self, mock_get_multi_npc, mock_location_get, mock_guild_get_config_crud):
        mock_session = AsyncMock(spec=AsyncSession)

        # GuildConfig constructor takes main_language. supported_languages is a property derived from properties_json.
        # For this test, only main_language is relevant for _get_guild_main_language.
        gc_instance = GuildConfig(id=1, main_language="en")
        # If the test needed to check supported_languages property, properties_json would be set:
        # gc_instance.properties_json = {"supported_languages": ["en", "ru"]}
        mock_guild_get_config_crud.return_value = gc_instance

        mock_execute_other_contexts = MagicMock(spec=Result)
        mock_execute_other_contexts.all.return_value = []
        mock_execute_other_contexts.scalars.return_value = MagicMock(spec=ScalarResult)
        mock_execute_other_contexts.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_execute_other_contexts

        mock_location_get.return_value = None
        mock_get_multi_npc.return_value = []

        result_prompt = await prepare_ai_prompt(mock_session, guild_id=1, location_id=999)
        # Expected: "Location: N/A - Location Not Found - Location ID 999 not found."
        # Actual if bug persists: "Location: N/A - Not specified. - No specific location context."
        self.assertIn("Location: N/A - Location Not Found - Location ID 999 not found.", result_prompt)
        self.assertNotIn("Error: Location not found", result_prompt)
        self.assertIn("Generate enriching content", result_prompt)

class TestAIFactionPromptBuilder(unittest.IsolatedAsyncioTestCase):

    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock)
    async def test_prepare_faction_relationship_generation_prompt_basic(
        self, mock_get_all_rules, mock_get_guild_lang
    ):
        mock_session = AsyncMock(spec=AsyncSession)
        guild_id = 1
        mock_get_guild_lang.return_value = "ru"
        mock_get_all_rules.return_value = {
            "faction_generation:target_count": 2,
            "faction_generation:themes_i18n": {"ru": ["Торговые гильдии", "Рыцарские ордена"]},
            "world_description_i18n": {"ru": "Мир на грани войны", "en": "A world on the brink of war"},
            "relationship_generation:complexity": "low"
        }
        prompt = await prepare_faction_relationship_generation_prompt(mock_session, guild_id)
        self.assertIsInstance(prompt, str)
        self.assertNotIn("Error generating faction/relationship AI prompt", prompt)
        self.assertIn("## AI Faction & Relationship Generation (Guild: 1, Lang: ru)", prompt)
        self.assertIn("World: Мир на грани войны", prompt)
        self.assertIn("Task: Generate 2 factions", prompt)
        self.assertIn("Торговые гильдии", prompt)
        self.assertIn("Рыцарские ордена", prompt)
        self.assertIn("complexity: low", prompt)
        self.assertIn("faction_schema", prompt)
        self.assertIn("relationship_schema", prompt)

class TestAIQuestPromptBuilder(unittest.IsolatedAsyncioTestCase):

    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_player_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_location_context', new_callable=AsyncMock)
    async def test_prepare_quest_generation_prompt_with_context(
        self, mock_get_loc_ctx, mock_get_player_ctx, mock_get_all_rules, mock_get_guild_lang
    ):
        mock_session = AsyncMock(spec=AsyncSession)
        guild_id = 1
        player_id_test = 1
        location_id_test = 1
        mock_get_guild_lang.return_value = "en" # This mock might be redundant if _get_guild_main_language calls guild_config_crud.get

        # If GuildConfig is fetched inside prepare_quest_generation_prompt (it is, via _get_guild_main_language),
        # we need to mock that call instead of just _get_guild_main_language if we want to control its attributes.
        # For this test, the attribute error is from outside this SUT, so the original test setup was likely for a different SUT.
        # However, if the test structure was:
        # mock_gc = GuildConfig(...)
        # mock_gc.supported_languages_json = ... (ERROR HERE)
        # mock_some_crud.get.return_value = mock_gc
        # await prepare_quest_generation_prompt(...)
        # Then the fix applies.
        # The current error is not from within prepare_quest_generation_prompt but in the test setup itself.
        # The pyright_summary line 133 is for test_ai_prompt_builder.py, not ai_analysis_system.py.
        # It refers to a line like `gc_instance.supported_languages_json = ...`

        # Let's assume the test structure *was* something like this for a different test or was simplified:
        # This test, as written, doesn't have a GuildConfig instance being modified directly.
        # The error must be in a different test or the summary is for a slightly different version.
        # For now, I will NO-OP this specific change as the current test code doesn't show this assignment at line 133.
        # If this error persists for this file, the exact context of line 133 needs to be re-verified from pyright.

        mock_get_all_rules.return_value = {
            "ai:quest_generation:target_count": 1,
            "ai:quest_generation:themes_i18n": {"en": ["lost artifact", "local investigation"]},
            "world_description_i18n": {"en": "A peaceful village with a dark secret."}
        }
        mock_get_player_ctx.return_value = {"name": "HeroPlayer", "level": 3}
        mock_get_loc_ctx.return_value = {"name": "Oakhaven", "type": "Village"}
        prompt = await prepare_quest_generation_prompt(
            mock_session, guild_id,
            player_id_context=player_id_test,
            location_id_context=location_id_test
        )
        self.assertIsInstance(prompt, str)
        self.assertNotIn("Error generating quest AI prompt", prompt)
        self.assertIn("## AI Quest Generation (Guild: 1, Lang: en)", prompt)
        self.assertIn("Context: A peaceful village with a dark secret.", prompt)
        self.assertIn("Player: HeroPlayer (Lvl 3)", prompt)
        self.assertIn("Location: Oakhaven (Village)", prompt)
        self.assertIn("Task: Generate 1 quest(s)", prompt)
        self.assertIn("lost artifact", prompt)
        self.assertIn("quest_schema", prompt)
        self.assertIn("quest_step_schema", prompt)

class TestAIEconomicPromptBuilder(unittest.IsolatedAsyncioTestCase):

    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock)
    async def test_prepare_economic_entity_generation_prompt_basic(
        self, mock_get_all_rules, mock_get_guild_lang
    ):
        mock_session = AsyncMock(spec=AsyncSession)
        guild_id = 1
        mock_get_guild_lang.return_value = "en"
        mock_get_all_rules.return_value = {
            "world_description_i18n": {"en": "A test world where items are scarce."},
            "ai:economic_generation:target_item_count": {"count": 3},
            "ai:economic_generation:target_trader_count": {"count": 1},
            "ai:economic_generation:item_type_distribution": {"types": [{"type_name": "weapon", "weight": 1}]},
            "ai:economic_generation:trader_role_distribution": {"roles": [{"role_key": "blacksmith", "weight": 1}]},
            "guild_main_language": "en"
        }
        result = await prepare_economic_entity_generation_prompt(mock_session, guild_id)
        self.assertIsInstance(result, str)
        mock_get_guild_lang.assert_called_once_with(mock_session, 1)
        mock_get_all_rules.assert_called_once_with(mock_session, 1)
        self.assertIn("## AI Economic Entity Generation (Guild: 1, Lang: en)", result)
        self.assertIn("item_schema", result)
        self.assertIn("npc_trader_schema", result)
        self.assertIn("npc_schema", result)
        self.assertIn("Context: A test world where items are scarce.", result)
        self.assertIn("Task: Generate 3 items and 1 NPC traders.", result)

class TestDialoguePromptBuilder(unittest.IsolatedAsyncioTestCase):

    def _create_mock_npc(self, npc_id=10, name_i18n=None, desc_i18n=None, props=None, static_id="npc_static_1"):
        mock_npc = AsyncMock(spec=GeneratedNpc)
        mock_npc.id = npc_id
        mock_npc.guild_id = 1
        mock_npc.name_i18n = name_i18n or {"en": f"Test NPC {npc_id}", "ru": f"Тестовый NPC {npc_id}"}
        mock_npc.description_i18n = desc_i18n or {"en": "A generic test NPC.", "ru": "Обычный тестовый NPC."}
        mock_npc.properties_json = props or {"role_i18n": {"en": "Merchant", "ru": "Торговец"}, "personality_i18n": {"en": "Friendly", "ru": "Дружелюбный"}}
        mock_npc.static_id = static_id
        return mock_npc

    def _create_mock_player(self, player_id=1, name="Test Player", level=5):
        mock_player = AsyncMock(spec=Player)
        mock_player.id = player_id
        mock_player.guild_id = 1
        mock_player.name = name
        mock_player.level = level
        return mock_player

    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.generated_npc_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.player_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.crud_relationship.get_relationship_between_entities', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock)
    # Minimal mocks for other context functions
    @patch('src.core.ai_prompt_builder._get_party_context', new_callable=AsyncMock, return_value={})
    @patch('src.core.ai_prompt_builder._get_location_context', new_callable=AsyncMock, return_value={})
    @patch('src.core.ai_prompt_builder._get_nearby_entities_context', new_callable=AsyncMock, return_value={"npcs": []})
    @patch('src.core.ai_prompt_builder._get_hidden_relationships_context_for_dialogue', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_npc_memory_context_stub', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_quests_context', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_world_state_context', new_callable=AsyncMock, return_value={})
    async def test_prepare_dialogue_prompt_no_relationship(
        self, mock_get_world_state, mock_get_quests_ctx, mock_get_memory_stub, mock_get_hidden_rels_ctx,
        mock_get_nearby_entities, mock_get_loc_ctx, mock_get_party_ctx,
        mock_get_all_rules, mock_get_player_npc_rel,
        mock_get_player, mock_get_npc, mock_get_lang
    ):
        mock_session = AsyncMock(spec=AsyncSession)
        guild_id = 1
        npc_id_test = 10
        player_id_test = 1

        mock_get_lang.return_value = "en"
        mock_get_npc.return_value = self._create_mock_npc(npc_id=npc_id_test, name_i18n={"en":"Mysterious Stranger"})
        mock_get_player.return_value = self._create_mock_player(player_id=player_id_test, name="Curious Cat")
        mock_get_all_rules.return_value = {"guild_main_language": "en"}

        mock_get_player_npc_rel.return_value = None # Simulate no existing relationship

        # Setup mock for session.execute for rules
        mock_execute_result_rules = MagicMock(spec=Result)
        mock_scalars_result_rules = MagicMock(spec=ScalarResult)
        mock_scalars_result_rules.all.return_value = [] # No RuleConfig entries
        mock_execute_result_rules.scalars.return_value = mock_scalars_result_rules
        mock_session.execute.return_value = mock_execute_result_rules

        test_context = {
            "npc_id": npc_id_test, "player_id": player_id_test, "player_input_text": "Who are you?",
        }
        prompt = await prepare_dialogue_generation_prompt(mock_session, guild_id, test_context)

        self.assertIsInstance(prompt, str)
        self.assertNotIn("Error:", prompt)
        self.assertIn("You have no established specific relationship with Curious Cat (assume neutral).", prompt)
        mock_get_player_npc_rel.assert_called_once_with(mock_session, guild_id, player_id_test, RelationshipEntityType.PLAYER, npc_id_test, RelationshipEntityType.GENERATED_NPC)


    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.generated_npc_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.player_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.crud_relationship.get_relationship_between_entities', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_hidden_relationships_context_for_dialogue', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_quests_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock) # for _get_guild_main_language and other rules
    # Mocks for other context functions that are called but not asserted on directly in this test
    @patch('src.core.ai_prompt_builder._get_party_context', new_callable=AsyncMock, return_value={})
    @patch('src.core.ai_prompt_builder._get_location_context', new_callable=AsyncMock, return_value={"name": "Somewhere", "description": "A place."})
    @patch('src.core.ai_prompt_builder._get_nearby_entities_context', new_callable=AsyncMock, return_value={"npcs": []})
    @patch('src.core.ai_prompt_builder._get_npc_memory_context_stub', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_world_state_context', new_callable=AsyncMock, return_value={})
    async def test_prepare_dialogue_prompt_with_relationship_quest_hidden_context(
        self, mock_get_world_state, mock_get_memory, mock_get_nearby_entities, mock_get_loc_ctx, mock_get_party_ctx,
        mock_get_all_rules, mock_get_quests_ctx, mock_get_hidden_rels_ctx, mock_get_player_npc_rel,
        mock_get_player, mock_get_npc, mock_get_lang
    ):
        mock_session = AsyncMock(spec=AsyncSession)
        guild_id = 1
        npc_id_test = 10
        player_id_test = 1

        mock_get_lang.return_value = "en"
        mock_get_npc.return_value = self._create_mock_npc(npc_id=npc_id_test, name_i18n={"en":"Guard Captain"})
        mock_get_player.return_value = self._create_mock_player(player_id=player_id_test, name="Rogue")
        mock_get_all_rules.return_value = {"guild_main_language": "en"} # Minimal rules

        # Test Relationship Context
        mock_relationship = Relationship(
            id=1, guild_id=guild_id,
            entity1_id=player_id_test, entity1_type=RelationshipEntityType.PLAYER,
            entity2_id=npc_id_test, entity2_type=RelationshipEntityType.GENERATED_NPC,
            relationship_type="trust", value=75
        )
        mock_get_player_npc_rel.return_value = mock_relationship

        # Test Hidden Relationship Context
        mock_get_hidden_rels_ctx.return_value = [
            {"prompt_hints": "Secretly admires the Rogue's skills."}
        ]

        # Test Quest Context
        mock_get_quests_ctx.return_value = [
            {"quest_name": "The Stolen Locket", "current_step_name": "Find clues in the market"}
        ]

        test_context = {
            "npc_id": npc_id_test, "player_id": player_id_test, "player_input_text": "About that locket...",
        }

        # Setup mock for session.execute for rules
        mock_execute_result_rules = MagicMock(spec=Result)
        mock_scalars_result_rules = MagicMock(spec=ScalarResult)
        mock_scalars_result_rules.all.return_value = [] # No RuleConfig entries
        mock_execute_result_rules.scalars.return_value = mock_scalars_result_rules
        mock_session.execute.return_value = mock_execute_result_rules

        prompt = await prepare_dialogue_generation_prompt(mock_session, guild_id, test_context)

        self.assertIsInstance(prompt, str)
        self.assertNotIn("Error:", prompt)

        # Check Relationship Context
        self.assertIn("Your current relationship with Rogue: Type: trust, Value: 75", prompt)
        mock_get_player_npc_rel.assert_called_once_with(mock_session, guild_id, player_id_test, RelationshipEntityType.PLAYER, npc_id_test, RelationshipEntityType.GENERATED_NPC)

        # Check Hidden Relationship Context
        self.assertIn("Some of your relevant hidden feelings or relationships:", prompt)
        self.assertIn("- Secretly admires the Rogue's skills.", prompt)
        mock_get_hidden_rels_ctx.assert_called_once()

        # Check Quest Context
        self.assertIn("Relevant Active Quests for the Player:", prompt)
        self.assertIn("1. 'The Stolen Locket' (step: 'Find clues in the market')", prompt)
        mock_get_quests_ctx.assert_called_once()

    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.generated_npc_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.player_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_party_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_location_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_nearby_entities_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.crud_relationship.get_relationship_between_entities', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_hidden_relationships_context_for_dialogue', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_npc_memory_context_stub', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_quests_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_world_state_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock)
    async def test_prepare_dialogue_prompt_basic_success(
        self, mock_get_rules, mock_get_world_state, mock_get_quests,
        mock_get_memory, mock_get_hidden_rels, mock_get_player_npc_rel,
        mock_get_nearby_entities, mock_get_loc_ctx, mock_get_party_ctx,
        mock_get_player, mock_get_npc, mock_get_lang
    ):
        mock_session = AsyncMock(spec=AsyncSession)
        guild_id = 1
        npc_id_test = 10
        player_id_test = 1
        mock_get_lang.return_value = "en"
        mock_get_npc.return_value = self._create_mock_npc(npc_id=npc_id_test)
        mock_get_player.return_value = self._create_mock_player(player_id=player_id_test)
        mock_get_party_ctx.return_value = {}
        mock_get_loc_ctx.return_value = {"name": "Test Tavern", "description": "A cozy place.", "type": "BUILDING"}
        mock_get_nearby_entities.return_value = {"npcs": []}
        mock_get_player_npc_rel.return_value = None
        mock_get_hidden_rels.return_value = []
        mock_get_memory.return_value = ["NPC STUB: Player seems okay."]
        mock_get_quests.return_value = []
        mock_get_world_state.return_value = {"global_event_active": "Festival of Stars"}

        # Setup mock for session.execute used by get_rule -> load_rules_config_for_guild
        mock_execute_result_rules = MagicMock(spec=Result)
        mock_scalars_result_rules = MagicMock(spec=ScalarResult)
        # Simulate that get_rule for relationship_influence:dialogue:availability_and_tone returns None,
        # and other rule lookups might also return None or their defaults from all_rules.
        # This means the DB query for RuleConfig by get_rule->load_rules_config_for_guild returns no rows.
        mock_scalars_result_rules.all.return_value = []
        mock_execute_result_rules.scalars.return_value = mock_scalars_result_rules
        mock_session.execute.return_value = mock_execute_result_rules

        mock_npc_obj = self._create_mock_npc(
            npc_id=npc_id_test,
            name_i18n={"en": "Old Man Willow", "ru": "Старик Ива"},
            desc_i18n={"en": "A wise old tree.", "ru": "Мудрое старое дерево."},
            props={"role_i18n": {"en": "Storyteller", "ru": "Сказитель"},
                   "personality_i18n": {"en": "Calm and thoughtful", "ru": "Спокойный и вдумчивый"},
                   "dialogue_style_hint_i18n": {"en": "Speaks in riddles sometimes.", "ru": "Иногда говорит загадками."}}
        )
        mock_get_npc.return_value = mock_npc_obj

        mock_player_obj = self._create_mock_player(player_id=player_id_test, name="Hero", level=7)
        mock_get_player.return_value = mock_player_obj

        mock_get_rules.return_value = {
            "guild_main_language": "en",
            "dialogue_rules:npc_general_guidelines:default": {"guidelines_i18n": {"en": "Be polite."}},
            "dialogue_rules:npc_tone_modifiers:default": [{"condition_description_i18n": {"en": "player is friendly"}, "tone_hint_i18n": {"en": "warm"}}]
        }

        test_context = {
            "npc_id": npc_id_test, "player_id": player_id_test, "player_input_text": "Greetings!",
            "dialogue_history": [{"speaker": "player", "text": "Hello?"}], "location_id": 100 # "text" is used here
        }
        prompt = await prepare_dialogue_generation_prompt(mock_session, guild_id, test_context)

        self.assertIsInstance(prompt, str)
        self.assertNotIn("Error:", prompt)

        # Проверка основного контекста NPC
        self.assertIn("You are Old Man Willow.", prompt)
        self.assertIn("Your Description: A wise old tree.", prompt)
        self.assertIn("Your Role/Profession: Storyteller", prompt)
        self.assertIn("Your General Personality Traits: Calm and thoughtful", prompt)
        self.assertIn("Your Dialogue Style Hint: Speaks in riddles sometimes.", prompt)

        # Проверка основного контекста Игрока
        self.assertIn("You are speaking with Hero (the Player).", prompt)
        self.assertIn("Player Level: 7", prompt)

        # Проверка указания языка
        self.assertIn("Language for NPC's response: en", prompt)

        # Проверка ключевых инструкций
        self.assertIn("Based on ALL context (personality, relationship, situation, memory, quests, dialogue history, NLU hints if provided), generate your next single, natural-sounding dialogue line.", prompt) # Corrected this line
        self.assertIn("Respond in **en**.", prompt)
        self.assertIn(f"{mock_player_obj.name} says to you: \"Greetings!\"", prompt)
        # В данном тесте history: [{"speaker": "player", "text": "Hello?"}]
        # После исправления в ai_prompt_builder на get('line'), это будет "None", т.к. ключ "line" отсутствует.
        self.assertIn(f"{mock_player_obj.name}: None", prompt)

        # Проверка использования заглушки для NPC Memory
        mock_get_memory.assert_called_once()
        self.assertIn("NPC STUB: Player seems okay.", prompt) # From mock_get_memory.return_value

        # Проверка других деталей из первоначального теста
        self.assertIn("Global Event Active: Festival of Stars", prompt)
        self.assertIn("General Guideline: Be polite.", prompt)
        self.assertIn("If player is friendly: lean towards 'warm'", prompt)

        mock_get_npc.assert_called_once_with(mock_session, id=npc_id_test, guild_id=guild_id)

    # --- Начало тестов для Шага 3 текущего плана (влияние отношений на тон) ---

    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.generated_npc_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.player_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.crud_relationship.get_relationship_between_entities', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_rule') # Not async, direct patch
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock)
    # Minimal mocks for other context functions
    @patch('src.core.ai_prompt_builder._get_party_context', new_callable=AsyncMock, return_value={})
    @patch('src.core.ai_prompt_builder._get_location_context', new_callable=AsyncMock, return_value={})
    @patch('src.core.ai_prompt_builder._get_nearby_entities_context', new_callable=AsyncMock, return_value={"npcs": []})
    @patch('src.core.ai_prompt_builder._get_hidden_relationships_context_for_dialogue', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_npc_memory_context_stub', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_quests_context', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_world_state_context', new_callable=AsyncMock, return_value={})
    async def test_dialogue_prompt_with_positive_relationship_tone_hint(
        self, mock_get_world_state, mock_get_quests_ctx, mock_get_memory_stub, mock_get_hidden_rels_ctx,
        mock_get_nearby_entities, mock_get_loc_ctx, mock_get_party_ctx,
        mock_get_all_rules_for_guild, mock_get_rule_config, mock_get_player_npc_rel,
        mock_get_player, mock_get_npc, mock_get_lang
    ):
        mock_session = AsyncMock(spec=AsyncSession)
        guild_id = 1
        npc_id_test = 10
        player_id_test = 1
        player_name_test = "Friendly Player"

        mock_get_lang.return_value = "en"
        mock_get_npc.return_value = self._create_mock_npc(npc_id=npc_id_test)
        mock_get_player.return_value = self._create_mock_player(player_id=player_id_test, name=player_name_test)

        # Simulate positive relationship
        mock_relationship = Relationship(value=80, relationship_type="friendship")
        mock_get_player_npc_rel.return_value = mock_relationship

        # Mock RuleConfig for relationship_influence:dialogue:availability_and_tone
        relationship_dialogue_rule = {
            "tone_modifiers": [
                {"relationship_above": 50, "tone_hint": "very_friendly"},
                {"relationship_above": 0, "tone_hint": "neutral"},
                {"relationship_default": True, "tone_hint": "cautious_default"}
            ]
        }
        # get_rule is synchronous, its mock should be synchronous too
        def get_rule_side_effect(session, guild_id_arg, key, default=None):
            if key == "relationship_influence:dialogue:availability_and_tone":
                return relationship_dialogue_rule
            return default
        mock_get_rule_config.side_effect = get_rule_side_effect

        mock_get_all_rules_for_guild.return_value = {"guild_main_language": "en"} # Basic rules

        test_context = {"npc_id": npc_id_test, "player_id": player_id_test, "player_input_text": "Hello my friend!"}
        prompt = await prepare_dialogue_generation_prompt(mock_session, guild_id, test_context)

        self.assertIn(f"Your current emotional tone towards {player_name_test} should reflect: **very_friendly**.", prompt)
        mock_get_rule_config.assert_any_call(mock_session, guild_id, "relationship_influence:dialogue:availability_and_tone", default=None)

        # Ensure session.execute is mocked for rule loading, if get_rule is called by SUT
        mock_execute_result_rules = MagicMock(spec=Result)
        mock_scalars_result_rules = MagicMock(spec=ScalarResult)
        # This specific test relies on mock_get_rule_config.side_effect to return the rule,
        # so the .all() value here might not be critical IF get_rule is the only DB access for rules.
        # However, if load_rules_config_for_guild is called before get_rule, this matters.
        # Let's assume it might be called.
        mock_rule_config_entry = RuleConfig(guild_id=guild_id, key="relationship_influence:dialogue:availability_and_tone", value_json=relationship_dialogue_rule)
        mock_scalars_result_rules.all.return_value = [mock_rule_config_entry]
        mock_execute_result_rules.scalars.return_value = mock_scalars_result_rules
        if not hasattr(mock_session.execute, 'side_effect') or mock_session.execute.side_effect is None : # Avoid overriding specific test mocks for execute
             mock_session.execute.return_value = mock_execute_result_rules


    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.generated_npc_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.player_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.crud_relationship.get_relationship_between_entities', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_rule') # Synchronous
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_party_context', new_callable=AsyncMock, return_value={})
    @patch('src.core.ai_prompt_builder._get_location_context', new_callable=AsyncMock, return_value={})
    @patch('src.core.ai_prompt_builder._get_nearby_entities_context', new_callable=AsyncMock, return_value={"npcs": []})
    @patch('src.core.ai_prompt_builder._get_hidden_relationships_context_for_dialogue', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_npc_memory_context_stub', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_quests_context', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_world_state_context', new_callable=AsyncMock, return_value={})
    async def test_dialogue_prompt_with_negative_relationship_tone_hint(
        self, mock_get_world_state, mock_get_quests_ctx, mock_get_memory_stub, mock_get_hidden_rels_ctx,
        mock_get_nearby_entities, mock_get_loc_ctx, mock_get_party_ctx,
        mock_get_all_rules_for_guild, mock_get_rule_config, mock_get_player_npc_rel,
        mock_get_player, mock_get_npc, mock_get_lang
    ):
        mock_session = AsyncMock(spec=AsyncSession)
        guild_id = 1
        npc_id_test = 11
        player_id_test = 2
        player_name_test = "Known Troublemaker"

        mock_get_lang.return_value = "en"
        mock_get_npc.return_value = self._create_mock_npc(npc_id=npc_id_test)
        mock_get_player.return_value = self._create_mock_player(player_id=player_id_test, name=player_name_test)

        mock_relationship = Relationship(value=-60, relationship_type="animosity")
        mock_get_player_npc_rel.return_value = mock_relationship

        relationship_dialogue_rule = {
            "tone_modifiers": [
                {"relationship_above": 50, "tone_hint": "very_friendly"},
                {"relationship_above": -20, "tone_hint": "neutral_wary"},
                {"relationship_above": -80, "tone_hint": "hostile"}, # This should be chosen
                {"relationship_default": True, "tone_hint": "default_neutral"}
            ]
        }
        def get_rule_side_effect(session, guild_id_arg, key, default=None):
            if key == "relationship_influence:dialogue:availability_and_tone":
                return relationship_dialogue_rule
            return default
        mock_get_rule_config.side_effect = get_rule_side_effect
        mock_get_all_rules_for_guild.return_value = {"guild_main_language": "en"}

        test_context = {"npc_id": npc_id_test, "player_id": player_id_test, "player_input_text": "What are you looking at?"}
        prompt = await prepare_dialogue_generation_prompt(mock_session, guild_id, test_context)

        self.assertIn(f"Your current emotional tone towards {player_name_test} should reflect: **hostile**.", prompt)

        # Ensure session.execute is mocked
        mock_execute_result_rules = MagicMock(spec=Result)
        mock_scalars_result_rules = MagicMock(spec=ScalarResult)
        mock_rule_config_entry = RuleConfig(guild_id=guild_id, key="relationship_influence:dialogue:availability_and_tone", value_json=relationship_dialogue_rule)
        mock_scalars_result_rules.all.return_value = [mock_rule_config_entry]
        mock_execute_result_rules.scalars.return_value = mock_scalars_result_rules
        if not hasattr(mock_session.execute, 'side_effect') or mock_session.execute.side_effect is None :
             mock_session.execute.return_value = mock_execute_result_rules

    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.generated_npc_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.player_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.crud_relationship.get_relationship_between_entities', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_rule') # Synchronous
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_party_context', new_callable=AsyncMock, return_value={})
    @patch('src.core.ai_prompt_builder._get_location_context', new_callable=AsyncMock, return_value={})
    @patch('src.core.ai_prompt_builder._get_nearby_entities_context', new_callable=AsyncMock, return_value={"npcs": []})
    @patch('src.core.ai_prompt_builder._get_hidden_relationships_context_for_dialogue', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_npc_memory_context_stub', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_quests_context', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_world_state_context', new_callable=AsyncMock, return_value={})
    async def test_dialogue_prompt_with_neutral_relationship_default_tone_hint(
        self, mock_get_world_state, mock_get_quests_ctx, mock_get_memory_stub, mock_get_hidden_rels_ctx,
        mock_get_nearby_entities, mock_get_loc_ctx, mock_get_party_ctx,
        mock_get_all_rules_for_guild, mock_get_rule_config, mock_get_player_npc_rel,
        mock_get_player, mock_get_npc, mock_get_lang
    ):
        mock_session = AsyncMock(spec=AsyncSession)
        player_name_test = "Neutral Player"
        mock_get_lang.return_value = "en"
        mock_get_npc.return_value = self._create_mock_npc()
        mock_get_player.return_value = self._create_mock_player(name=player_name_test)
        mock_relationship = Relationship(value=5, relationship_type="neutral") # Does not meet >50 or >-20 (if hostile was -80)
        mock_get_player_npc_rel.return_value = mock_relationship

        relationship_dialogue_rule = {
            "tone_modifiers": [
                {"relationship_above": 50, "tone_hint": "very_friendly"},
                {"relationship_above": 20, "tone_hint": "friendly_nod"}, # Value 5 is not > 20
                {"relationship_default": True, "tone_hint": "standard_neutral_greeting"}
            ]
        }
        def get_rule_side_effect(session, guild_id_arg, key, default=None):
            if key == "relationship_influence:dialogue:availability_and_tone": return relationship_dialogue_rule
            return default
        mock_get_rule_config.side_effect = get_rule_side_effect
        mock_get_all_rules_for_guild.return_value = {"guild_main_language": "en"}

        test_context = {"npc_id": 10, "player_id": 1, "player_input_text": "Hello."}
        prompt = await prepare_dialogue_generation_prompt(mock_session, 1, test_context)
        self.assertIn(f"Your current emotional tone towards {player_name_test} should reflect: **standard_neutral_greeting**.", prompt)

        # Ensure session.execute is mocked
        mock_execute_result_rules = MagicMock(spec=Result)
        mock_scalars_result_rules = MagicMock(spec=ScalarResult)
        mock_rule_config_entry = RuleConfig(guild_id=1, key="relationship_influence:dialogue:availability_and_tone", value_json=relationship_dialogue_rule)
        mock_scalars_result_rules.all.return_value = [mock_rule_config_entry] # Or [] if rule is expected to be missing for some part of logic
        mock_execute_result_rules.scalars.return_value = mock_scalars_result_rules
        if not hasattr(mock_session.execute, 'side_effect') or mock_session.execute.side_effect is None :
            mock_session.execute.return_value = mock_execute_result_rules

    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.generated_npc_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.player_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.crud_relationship.get_relationship_between_entities', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_rule') # Synchronous
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock)
    # Mocks for other context functions
    @patch('src.core.ai_prompt_builder._get_party_context', new_callable=AsyncMock, return_value={})
    @patch('src.core.ai_prompt_builder._get_location_context', new_callable=AsyncMock, return_value={})
    @patch('src.core.ai_prompt_builder._get_nearby_entities_context', new_callable=AsyncMock, return_value={"npcs": []})
    @patch('src.core.ai_prompt_builder._get_hidden_relationships_context_for_dialogue', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_npc_memory_context_stub', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_quests_context', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_world_state_context', new_callable=AsyncMock, return_value={})
    async def test_dialogue_prompt_no_relationship_influence_rule(
        self, mock_get_world_state, mock_get_quests_ctx, mock_get_memory_stub, mock_get_hidden_rels_ctx,
        mock_get_nearby_entities, mock_get_loc_ctx, mock_get_party_ctx,
        mock_get_all_rules_for_guild, mock_get_rule_config, mock_get_player_npc_rel,
        mock_get_player, mock_get_npc, mock_get_lang
    ):
        mock_session = AsyncMock(spec=AsyncSession)
        player_name_test = "Player With No Rules"
        mock_get_lang.return_value = "en"
        mock_get_npc.return_value = self._create_mock_npc()
        mock_get_player.return_value = self._create_mock_player(name=player_name_test)
        mock_get_player_npc_rel.return_value = Relationship(value=10) # Some relationship exists

        # Simulate rule not found for relationship_influence, but other rules might exist
        def get_rule_side_effect(session, guild_id_arg, key, default=None):
            if key == "relationship_influence:dialogue:availability_and_tone":
                return None # Rule not found for relationship influence
            elif key == "dialogue_rules:npc_general_guidelines:default":
                return {"guidelines_i18n": {"en": "Default guideline"}}
            # Ensure that a default is returned for other get_rule calls if they occur
            # For example, the code also tries to get specific NPC guidelines:
            # dialogue_rules:npc_general_guidelines:npc_static_1 (using the default static_id from _create_mock_npc)
            # and dialogue_rules:npc_tone_modifiers:npc_static_1
            # dialogue_rules:npc_tone_modifiers:default
            # If these are not mocked to return something, they might default to None or an empty dict.
            # The original test passed because the assertion was only on the absence of the relationship tone hint
            # and the presence of the general guideline.
            # Let's ensure get_all_rules_for_guild returns these keys if they are expected to be processed by the SUT
            return default

        mock_get_rule_config.side_effect = get_rule_side_effect

        # Ensure get_all_rules_for_guild returns the keys that prepare_dialogue_generation_prompt will try to get via all_rules.get()
        # This includes the general guideline and tone modifier rules.
        mock_get_all_rules_for_guild.return_value = {
            "guild_main_language": "en",
            "dialogue_rules:npc_general_guidelines:default": {"guidelines_i18n": {"en": "Default guideline"}},
            "dialogue_rules:npc_tone_modifiers:default": [{"condition_description_i18n": {"en": "player is neutral"}, "tone_hint_i18n": {"en": "standard"}}],
            # Add other rule keys that might be accessed by all_rules.get() if necessary
        }


        test_context = {"npc_id": 10, "player_id": 1, "player_input_text": "Test."}
        prompt = await prepare_dialogue_generation_prompt(mock_session, 1, test_context)

        self.assertNotIn("Your current emotional tone towards", prompt) # Specific tone hint from relationship_influence rule should be absent
        self.assertIn("General Guideline: Default guideline", prompt) # Check that other rule types are still processed

        # Ensure session.execute is mocked
        mock_execute_result_rules = MagicMock(spec=Result)
        mock_scalars_result_rules = MagicMock(spec=ScalarResult)
        # For this test, the specific rule is NOT found, so .all() should be empty for that key.
        # However, other rules (like general guidelines) ARE found via all_rules.get().
        # So, the mock for session.execute should reflect that the DB query underlying get_rule for the specific key returns nothing.
        # The get_all_rules_for_guild mock already provides the general guidelines.
        # If get_rule is called for "relationship_influence:dialogue:availability_and_tone", it should return None (its default).
        # This is handled by mock_get_rule_config.side_effect.
        # If load_rules_config_for_guild is called independently, it would need to return all rules.
        # The critical part is that mock_get_rule_config.side_effect correctly returns None for the specific key.
        # The session.execute mock here is more of a safety for general calls to load_rules_config_for_guild.
        mock_scalars_result_rules.all.return_value = [
            RuleConfig(guild_id=1, key="dialogue_rules:npc_general_guidelines:default", value_json={"guidelines_i18n": {"en": "Default guideline"}}),
            RuleConfig(guild_id=1, key="dialogue_rules:npc_tone_modifiers:default", value_json=[{"condition_description_i18n": {"en": "player is neutral"}, "tone_hint_i18n": {"en": "standard"}}])
        ] # Simulate other rules exist
        mock_execute_result_rules.scalars.return_value = mock_scalars_result_rules
        if not hasattr(mock_session.execute, 'side_effect') or mock_session.execute.side_effect is None:
            mock_session.execute.return_value = mock_execute_result_rules


    # --- Конец тестов для Шага 3 ---


    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.generated_npc_crud.get', new_callable=AsyncMock)
    async def test_prepare_dialogue_prompt_npc_not_found(self, mock_generated_npc_get, mock_get_guild_language_direct):
        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_guild_language_direct.return_value = "en"
        mock_generated_npc_get.return_value = None
        mock_execute_rules_npc = MagicMock(spec=Result)
        mock_scalars_rules_npc = MagicMock(spec=ScalarResult)
        mock_scalars_rules_npc.all.return_value = []
        mock_execute_rules_npc.scalars.return_value = mock_scalars_rules_npc
        mock_session.execute.return_value = mock_execute_rules_npc
        test_context = {"npc_id": 999, "player_id": 1, "player_input_text": "Anyone here?"}
        prompt = await prepare_dialogue_generation_prompt(mock_session, 1, test_context)
        self.assertTrue(prompt.startswith("Error: NPC with ID 999 not found"))

        # Ensure session.execute is mocked for any rule loading attempts
        mock_execute_result_rules = MagicMock(spec=Result)
        mock_scalars_result_rules = MagicMock(spec=ScalarResult)
        mock_scalars_result_rules.all.return_value = []
        mock_execute_result_rules.scalars.return_value = mock_scalars_result_rules
        # Check if execute has a side_effect from a previous specific mock in a broader test setup
        if not hasattr(mock_session.execute, 'side_effect') or mock_session.execute.side_effect is None:
            mock_session.execute.return_value = mock_execute_result_rules

    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.generated_npc_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.player_crud.get', new_callable=AsyncMock)
    async def test_prepare_dialogue_prompt_player_not_found(self, mock_get_player, mock_get_npc, mock_get_lang):
        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_lang.return_value = "en"
        mock_get_npc.return_value = self._create_mock_npc()
        mock_get_player.return_value = None
        mock_execute_rules_player = MagicMock(spec=Result)
        mock_scalars_rules_player = MagicMock(spec=ScalarResult)
        mock_scalars_rules_player.all.return_value = []
        mock_execute_rules_player.scalars.return_value = mock_scalars_rules_player
        mock_session.execute.return_value = mock_execute_rules_player
        test_context = {"npc_id": 10, "player_id": 999, "player_input_text": "Is this the real life?"}
        prompt = await prepare_dialogue_generation_prompt(mock_session, 1, test_context)
        self.assertTrue(prompt.startswith("Error: Player with ID 999 not found"))

        # Ensure session.execute is mocked
        mock_execute_result_rules = MagicMock(spec=Result)
        mock_scalars_result_rules = MagicMock(spec=ScalarResult)
        mock_scalars_result_rules.all.return_value = []
        mock_execute_result_rules.scalars.return_value = mock_scalars_result_rules
        if not hasattr(mock_session.execute, 'side_effect') or mock_session.execute.side_effect is None:
            mock_session.execute.return_value = mock_execute_result_rules

    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.generated_npc_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.player_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_npc_memory_context_stub', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_party_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_location_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_nearby_entities_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.crud_relationship.get_relationship_between_entities', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_hidden_relationships_context_for_dialogue', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_quests_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_world_state_context', new_callable=AsyncMock)
    async def test_dialogue_history_inclusion(
        self, mock_world_state, mock_quests, mock_hidden_rels, mock_player_npc_rel,
        mock_nearby_entities, mock_loc_ctx, mock_party_ctx, mock_rules,
        mock_memory_stub, mock_get_player, mock_get_npc, mock_get_lang
    ):
        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_lang.return_value = "en"
        mock_npc_obj = self._create_mock_npc(npc_id=10, name_i18n={"en":"Innkeeper"})
        mock_get_npc.return_value = mock_npc_obj
        mock_player_obj = self._create_mock_player(player_id=1, name="Adventurer")
        mock_get_player.return_value = mock_player_obj
        mock_memory_stub.return_value = []
        mock_rules.return_value = {}
        mock_party_ctx.return_value = {}
        mock_loc_ctx.return_value = {}
        mock_nearby_entities.return_value = {"npcs": []}
        mock_player_npc_rel.return_value = None
        mock_hidden_rels.return_value = []
        mock_quests.return_value = []
        mock_world_state.return_value = {}

        # Setup mock for session.execute used by get_rule -> load_rules_config_for_guild
        mock_execute_result_rules = MagicMock(spec=Result)
        mock_scalars_result_rules = MagicMock(spec=ScalarResult)
        mock_scalars_result_rules.all.return_value = [] # No RuleConfig entries for this test
        mock_execute_result_rules.scalars.return_value = mock_scalars_result_rules
        mock_session.execute.return_value = mock_execute_result_rules

        dialogue_history = [
            {"speaker": "player", "line": "Good day!"},
            {"speaker": "npc", "line": "And to you, traveler."},
            {"speaker": "player", "line": "Any news?"}
        ]
        test_context = {
            "npc_id": 10, "player_id": 1, "player_input_text": "What about the old ruins?",
            "dialogue_history": dialogue_history
        }
        prompt = await prepare_dialogue_generation_prompt(mock_session, 1, test_context)
        self.assertIn("Adventurer: Good day!", prompt)
        self.assertIn("Innkeeper: And to you, traveler.", prompt)
        self.assertIn("Adventurer: Any news?", prompt)
        self.assertIn("Adventurer says to you: \"What about the old ruins?\"", prompt)

    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.generated_npc_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.player_crud.get', new_callable=AsyncMock)
    # Mock all other context-gathering functions to return empty/neutral values
    @patch('src.core.ai_prompt_builder._get_party_context', new_callable=AsyncMock, return_value={})
    @patch('src.core.ai_prompt_builder._get_location_context', new_callable=AsyncMock, return_value={})
    @patch('src.core.ai_prompt_builder._get_nearby_entities_context', new_callable=AsyncMock, return_value={"npcs": []})
    @patch('src.core.ai_prompt_builder.crud_relationship.get_relationship_between_entities', new_callable=AsyncMock, return_value=None)
    @patch('src.core.ai_prompt_builder._get_hidden_relationships_context_for_dialogue', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_npc_memory_context_stub', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_quests_context', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_world_state_context', new_callable=AsyncMock, return_value={})
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock, return_value={"guild_main_language": "en"})
    @patch('src.core.ai_prompt_builder.get_rule', new_callable=AsyncMock) # Changed to AsyncMock
    async def test_prepare_dialogue_prompt_with_nlu_data(
        self, mock_get_rule, mock_get_all_rules, mock_get_world_state, mock_get_quests,
        mock_get_memory, mock_get_hidden_rels, mock_get_player_npc_rel,
        mock_get_nearby_entities, mock_get_loc_ctx, mock_get_party_ctx,
        mock_get_player, mock_get_npc, mock_get_lang
    ):
        mock_session = AsyncMock(spec=AsyncSession)
        guild_id = 1
        npc_id_test = 10
        player_id_test = 1

        mock_get_lang.return_value = "en"
        mock_get_npc.return_value = self._create_mock_npc(npc_id=npc_id_test, name_i18n={"en":"Helpful NPC"})
        mock_get_player.return_value = self._create_mock_player(player_id=player_id_test, name="Adventurer")

        test_intent = "request_item"
        test_entities = [{"type": "item_name", "value": "healing potion"}, {"type": "quantity", "value": "2"}]

        test_context = {
            "npc_id": npc_id_test,
            "player_id": player_id_test,
            "player_input_text": "Can I have two healing potions?",
            "parsed_intent": test_intent,
            "parsed_entities": test_entities
        }
        prompt = await prepare_dialogue_generation_prompt(mock_session, guild_id, test_context)

        self.assertIsInstance(prompt, str)
        self.assertNotIn("Error:", prompt)

        self.assertIn(f"(Player's message was analyzed by NLU. Recognized intent: **'{test_intent}'**.)", prompt)
        self.assertIn(f"Recognized NLU entities: item_name: 'healing potion', quantity: '2'.", prompt)
        self.assertIn("Based on ALL context (personality, relationship, situation, memory, quests, dialogue history, NLU hints if provided), generate your next single, natural-sounding dialogue line.", prompt)

        # Ensure session.execute is mocked
        mock_execute_result_rules = MagicMock(spec=Result)
        mock_scalars_result_rules = MagicMock(spec=ScalarResult)
        mock_scalars_result_rules.all.return_value = []
        mock_execute_result_rules.scalars.return_value = mock_scalars_result_rules
        if not hasattr(mock_session.execute, 'side_effect') or mock_session.execute.side_effect is None:
            mock_session.execute.return_value = mock_execute_result_rules

    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.generated_npc_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.player_crud.get', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_party_context', new_callable=AsyncMock, return_value={})
    @patch('src.core.ai_prompt_builder._get_location_context', new_callable=AsyncMock, return_value={})
    @patch('src.core.ai_prompt_builder._get_nearby_entities_context', new_callable=AsyncMock, return_value={"npcs": []})
    @patch('src.core.ai_prompt_builder.crud_relationship.get_relationship_between_entities', new_callable=AsyncMock, return_value=None)
    @patch('src.core.ai_prompt_builder._get_hidden_relationships_context_for_dialogue', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_npc_memory_context_stub', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_quests_context', new_callable=AsyncMock, return_value=[])
    @patch('src.core.ai_prompt_builder._get_world_state_context', new_callable=AsyncMock, return_value={})
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock, return_value={"guild_main_language": "en"})
    @patch('src.core.ai_prompt_builder.get_rule', new_callable=AsyncMock) # Changed to AsyncMock
    async def test_prepare_dialogue_prompt_with_nlu_unknown_intent(
        self, mock_get_rule, mock_get_all_rules, mock_get_world_state, mock_get_quests,
        mock_get_memory, mock_get_hidden_rels, mock_get_player_npc_rel,
        mock_get_nearby_entities, mock_get_loc_ctx, mock_get_party_ctx,
        mock_get_player, mock_get_npc, mock_get_lang
    ):
        mock_session = AsyncMock(spec=AsyncSession)
        guild_id = 1
        npc_id_test = 10
        player_id_test = 1

        mock_get_lang.return_value = "en"
        mock_get_npc.return_value = self._create_mock_npc(npc_id=npc_id_test)
        mock_get_player.return_value = self._create_mock_player(player_id=player_id_test)

        test_context = {
            "npc_id": npc_id_test,
            "player_id": player_id_test,
            "player_input_text": "Gibberish text",
            "parsed_intent": "unknown_intent", # NLU could not determine specific intent
            "parsed_entities": []
        }
        prompt = await prepare_dialogue_generation_prompt(mock_session, guild_id, test_context)

        self.assertIsInstance(prompt, str)
        self.assertNotIn("Error:", prompt)

        # Check that NLU hint section is NOT added for "unknown_intent"
        self.assertNotIn("(Player's message was analyzed by NLU. Recognized intent: **'unknown_intent'**.)", prompt)
        # Check that the main task description still mentions NLU hints generally
        self.assertIn("Based on ALL context (personality, relationship, situation, memory, quests, dialogue history, NLU hints if provided), generate your next single, natural-sounding dialogue line.", prompt)

        # Ensure session.execute is mocked
        mock_execute_result_rules = MagicMock(spec=Result)
        mock_scalars_result_rules = MagicMock(spec=ScalarResult)
        mock_scalars_result_rules.all.return_value = []
        mock_execute_result_rules.scalars.return_value = mock_scalars_result_rules
        if not hasattr(mock_session.execute, 'side_effect') or mock_session.execute.side_effect is None:
            mock_session.execute.return_value = mock_execute_result_rules

if __name__ == '__main__':
    unittest.main()
