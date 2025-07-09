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
        mock_loc = Location(id=1, guild_id=1, name_i18n={"en":"Test Loc", "ru":"Тест Лок"}, descriptions_i18n={}, type=LocationType.CITY, coordinates_json="{}", generated_details_json="{}", ai_metadata_json="{}", neighbor_locations_json="[]")
        return mock_loc
    if id == 100 and guild_id == 1:
        mock_loc = Location(id=100, guild_id=1, name_i18n={"en":"Test Tavern", "ru":"Тестовая Таверна"}, descriptions_i18n={"en":"A cozy place", "ru":"Уютное место"}, type=LocationType.BUILDING, neighbor_locations_json="[]")
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

        gc_instance = GuildConfig(id=1, main_language="en")
        gc_instance.supported_languages_json = ["en", "ru"]
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
        mock_get_guild_lang.return_value = "en"
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
        mock_get_rules.return_value = {
            "guild_main_language": "en",
            "dialogue_rules:npc_general_guidelines:default": {"guidelines_i18n": {"en": "Be polite."}},
            "dialogue_rules:npc_tone_modifiers:default": [{"condition_description_i18n": {"en": "player is friendly"}, "tone_hint_i18n": {"en": "warm"}}]
            }
        test_context = {
            "npc_id": npc_id_test, "player_id": player_id_test, "player_input_text": "Greetings!",
            "dialogue_history": [{"speaker": "player", "text": "Hello?"}], "location_id": 100
        }
        prompt = await prepare_dialogue_generation_prompt(mock_session, guild_id, test_context)
        self.assertIsInstance(prompt, str)
        self.assertNotIn("Error:", prompt)
        self.assertIn(f"You are Test NPC {npc_id_test}", prompt)
        self.assertIn("You are speaking with Test Player", prompt)
        self.assertIn("Player says to you: \"Greetings!\"", prompt)
        self.assertIn("Player: Hello?", prompt)
        self.assertIn("NPC STUB: Player seems okay.", prompt)
        self.assertIn("Global Event Active: Festival of Stars", prompt)
        self.assertIn("General Guideline: Be polite.", prompt)
        self.assertIn("If player is friendly: lean towards 'warm'", prompt)
        mock_get_npc.assert_called_once_with(mock_session, id=npc_id_test, guild_id=guild_id)
        mock_get_memory.assert_called_once()

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
        dialogue_history = [
            {"speaker": "player", "text": "Good day!"},
            {"speaker": "npc", "text": "And to you, traveler."},
            {"speaker": "player", "text": "Any news?"}
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

if __name__ == '__main__':
    unittest.main()
