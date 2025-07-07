import sys
import os
import unittest
import json
from unittest.mock import patch, MagicMock, AsyncMock

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession

# Assuming GuildConfig is needed for _get_guild_main_language if not fully mocked
from src.models.guild import GuildConfig
from src.models.rule_config import RuleConfig
from src.core.ai_prompt_builder import prepare_faction_relationship_generation_prompt, _get_entity_schema_terms
# For testing, we'll need an AsyncSession. We can mock it or use a real in-memory DB session.
# For prompt builder, mocking dependencies might be easier than setting up full DB state.

# Dummy AsyncSession for type hinting and basic mock
class MockAsyncSession(AsyncMock, AsyncSession): # Inherit from AsyncSession for type compatibility
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add any methods that might be called on the session if not fully mocked out
        # For example, if any CRUD methods are called directly on session instead of through a CRUD object.
        # self.execute = AsyncMock()
        # self.scalars = AsyncMock(return_value=self) # if session.scalars().all() is used
        # self.all = AsyncMock(return_value=[])


class TestAIProompBuilderFactionRel(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Schemas are constant, load them once
        self.entity_schemas = _get_entity_schema_terms()
        self.faction_schema_json = json.dumps(self.entity_schemas.get("faction_schema"), indent=2)
        self.relationship_schema_json = json.dumps(self.entity_schemas.get("relationship_schema"), indent=2)

    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock)
    async def test_prepare_faction_relationship_generation_prompt_structure(
        self, mock_get_all_rules, mock_get_guild_main_language
    ):
        mock_get_guild_main_language.return_value = "en"
        mock_get_all_rules.return_value = {
            "faction_generation:target_count": 3,
            "faction_generation:themes": ["fantasy", "sci-fi"],
            "world_description": "A test world",
            "relationship_generation:complexity": "simple",
            "relationship_generation:default_types": ["allied", "neutral"]
        }

        mock_session = MockAsyncSession()
        guild_id = 1

        prompt = await prepare_faction_relationship_generation_prompt(mock_session, guild_id)

        self.assertIsInstance(prompt, str)
        self.assertIn("## AI Faction and Relationship Generation Request", prompt)
        self.assertIn(f"Target Guild ID: {guild_id}", prompt)
        self.assertIn("### Guild & World Context:", prompt)
        self.assertIn("### Generation Guidelines & Rules:", prompt)
        self.assertIn("### Generation Task:", prompt)
        self.assertIn("### Output Format Instructions:", prompt)
        self.assertIn("### Entity Schemas for Generation:", prompt)

        # Check for schema inclusion
        # The prompt builder wraps the faction and relationship schemas in another dict before dumping
        expected_schemas_in_prompt = json.dumps({
            "faction_schema": self.entity_schemas.get("faction_schema"),
            "relationship_schema": self.entity_schemas.get("relationship_schema")
        }, indent=2)
        self.assertIn(expected_schemas_in_prompt, prompt)


    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock)
    async def test_prompt_includes_guild_language_and_rules(
        self, mock_get_all_rules, mock_get_guild_main_language
    ):
        test_lang = "fr"
        test_target_count = 5
        test_themes = ["steampunk", "magic"]
        test_world_desc = "Un monde francophone de test."
        test_complexity = "high"
        test_rel_types = ["trade_pact", "warring"]

        mock_get_guild_main_language.return_value = test_lang
        mock_get_all_rules.return_value = {
            "faction_generation:target_count": test_target_count,
            "faction_generation:themes": test_themes,
            "world_description": test_world_desc,
            "relationship_generation:complexity": test_complexity,
            "relationship_generation:default_types": test_rel_types,
            # Add a rule that might be missing to test default fallback later if needed
        }

        mock_session = MockAsyncSession()
        guild_id = 2

        prompt = await prepare_faction_relationship_generation_prompt(mock_session, guild_id)

        self.assertIn(f"Primary Language for Generation: {test_lang}", prompt)
        self.assertIn(f"World Description: {test_world_desc}", prompt)
        self.assertIn(f"Target Number of Factions to Generate: {test_target_count}", prompt)
        self.assertIn(f"Suggested Faction Themes/Archetypes: {', '.join(test_themes)}", prompt)
        self.assertIn(f"Relationship Complexity: {test_complexity}", prompt)
        self.assertIn(f"Default Relationship Types to consider: {', '.join(test_rel_types)}", prompt)


    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock)
    async def test_prompt_handles_missing_rules_gracefully(
        self, mock_get_all_rules, mock_get_guild_main_language
    ):
        mock_get_guild_main_language.return_value = "de"
        # Return empty dict for rules, forcing defaults in the function
        mock_get_all_rules.return_value = {}

        mock_session = MockAsyncSession()
        guild_id = 3

        prompt = await prepare_faction_relationship_generation_prompt(mock_session, guild_id)

        # Check for default values as defined in prepare_faction_relationship_generation_prompt
        # Example defaults from the function:
        # "faction_generation:target_count", 3
        # "faction_generation:themes", ["good_vs_evil", "nature_vs_industry"]
        # "world_description", "A generic fantasy world."
        # "relationship_generation:complexity", "moderate"
        # "relationship_generation:default_types", ["faction_standing"]

        self.assertIn(f"Primary Language for Generation: de", prompt)
        self.assertIn(f"World Description: A generic fantasy world.", prompt) # Default
        self.assertIn(f"Target Number of Factions to Generate: 3", prompt) # Default
        self.assertIn(f"Suggested Faction Themes/Archetypes: {', '.join(['good_vs_evil', 'nature_vs_industry'])}", prompt) # Default
        self.assertIn(f"Relationship Complexity: moderate", prompt) # Default
        self.assertIn(f"Default Relationship Types to consider: {', '.join(['faction_standing'])}", prompt) # Default
        self.assertNotIn("Error generating", prompt) # Ensure no error message in prompt


class TestAIEconomicPromptBuilder(unittest.IsolatedAsyncioTestCase): # Renamed class for clarity
    def setUp(self):
        self.entity_schemas = _get_entity_schema_terms()
        self.item_schema_json = json.dumps(self.entity_schemas.get("item_schema"), indent=2)
        self.npc_trader_schema_json = json.dumps(self.entity_schemas.get("npc_trader_schema"), indent=2)
        self.npc_schema_json = json.dumps(self.entity_schemas.get("npc_schema"), indent=2) # For npc_trader schema reference

    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock)
    async def test_prepare_economic_entity_generation_prompt_basic_structure(
        self, mock_get_all_rules, mock_get_guild_main_language
    ):
        from src.core.ai_prompt_builder import prepare_economic_entity_generation_prompt # SUT

        mock_get_guild_main_language.return_value = "en"
        # Provide sample rules that the prompt builder expects
        mock_get_all_rules.return_value = {
            "ai:economic_generation:target_item_count": {"count": 7}, # Use dict structure
            "ai:economic_generation:target_trader_count": {"count": 2}, # Use dict structure
            "world_description_i18n": {"en": "A bustling trade city.", "ru": "Шумный торговый город."},
            "economy:base_item_values:weapon_sword_common": {"value": 100, "currency": "gold"},
            "economy:npc_inventory_templates:general_store_owner": {"description": "General store template items"},
            "ai:economic_generation:item_type_distribution": {
                "types": [{"type_name": "weapon", "weight": 5}]
            },
            "ai:economic_generation:trader_role_distribution": {
                "roles": [{"role_key": "blacksmith", "weight": 3, "name_i18n": {"en": "Smith"}}]
            },
            "ai:economic_generation:quality_instructions_i18n": {"en": "Make them good."}
        }
        mock_session = MockAsyncSession()
        guild_id = 1

        prompt = await prepare_economic_entity_generation_prompt(mock_session, guild_id)

        self.assertIsInstance(prompt, str)
        self.assertIn("## AI Economic Entity Generation Request", prompt)
        self.assertIn(f"Target Guild ID: {guild_id}", prompt)
        self.assertIn("Primary Language for Generation: en", prompt)
        self.assertIn("### Generation Guidelines & Context:", prompt)
        self.assertIn("World Description: A bustling trade city.", prompt)
        self.assertIn("Quality Instructions: Make them good.", prompt)
        self.assertIn("Target Number of New Items to Generate: 7", prompt) # Adjusted to reflect rule
        self.assertIn("Target Number of New NPC Traders to Generate: 2", prompt) # Adjusted to reflect rule

        self.assertIn("Suggested Item Type Distribution", prompt)
        self.assertIn("Suggested Trader Role Distribution", prompt)

        self.assertIn("Relevant Economic Rules", prompt)
        self.assertIn("economy:base_item_values:weapon_sword_common", prompt)
        self.assertIn("economy:npc_inventory_templates:general_store_owner", prompt)

        self.assertIn("### Generation Task:", prompt)
        self.assertIn("Generate 7 new item(s) and 2 new NPC trader(s)", prompt) # Adjusted
        self.assertIn("Adhere to the 'item_schema'", prompt)
        self.assertIn("Adhere to the 'npc_trader_schema'", prompt)
        self.assertIn("### Output Format Instructions:", prompt)
        self.assertIn("Provide your response as a single JSON array", prompt)
        self.assertIn("entity_type' field ('item' or 'npc_trader')", prompt)
        self.assertIn("### Entity Schemas for Generation:", prompt)

        expected_schemas_dump = json.dumps({
            "item_schema": self.entity_schemas.get("item_schema"),
            "npc_trader_schema": self.entity_schemas.get("npc_trader_schema"),
            "npc_schema": self.entity_schemas.get("npc_schema")
        }, indent=2)
        self.assertIn(expected_schemas_dump, prompt)
        self.assertNotIn("Error generating economic entity AI prompt", prompt)


    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock)
    async def test_prepare_economic_entity_generation_prompt_handles_missing_rules(
        self, mock_get_all_rules, mock_get_guild_main_language
    ):
        from src.core.ai_prompt_builder import prepare_economic_entity_generation_prompt # SUT
        mock_get_guild_main_language.return_value = "de"
        mock_get_all_rules.return_value = {} # No rules defined, expect defaults

        mock_session = MockAsyncSession()
        guild_id = 2

        prompt = await prepare_economic_entity_generation_prompt(mock_session, guild_id)

        self.assertIn("Primary Language for Generation: de", prompt)
        # Check for default counts (as defined in the SUT)
        self.assertIn("Target Number of New Items to Generate: 5", prompt) # Default
        self.assertIn("Target Number of New NPC Traders to Generate: 2", prompt) # Default
        self.assertIn("No specific economic rules found", prompt)
        self.assertIn("Example Item Types: weapon, armor, consumable, crafting_material, quest_item, misc", prompt) # Default example
        self.assertIn("Example Trader Roles: Blacksmith, Alchemist, General Goods Vendor, Fletcher", prompt) # Default example
        self.assertNotIn("Error generating economic entity AI prompt", prompt)


class TestAIProompBuilderLocationContent(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.entity_schemas = _get_entity_schema_terms()
        # Extract specific schemas needed for location content generation
        self.npc_schema_json = json.dumps(self.entity_schemas.get("npc_schema"), indent=2)
        self.quest_schema_json = json.dumps(self.entity_schemas.get("quest_schema"), indent=2)
        self.item_schema_json = json.dumps(self.entity_schemas.get("item_schema"), indent=2)
        self.event_schema_json = json.dumps(self.entity_schemas.get("event_schema"), indent=2)
        self.relationship_schema_json = json.dumps(self.entity_schemas.get("relationship_schema"), indent=2)

    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_location_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_player_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_party_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_nearby_entities_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_quests_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_relationships_context', new_callable=AsyncMock) # Standard relationships
    @patch('src.core.ai_prompt_builder._get_world_state_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_game_rules_terms', new_callable=AsyncMock)
    async def test_prepare_ai_prompt_requests_npc_static_id_and_relationships(
        self, mock_get_game_rules, mock_get_world_state, mock_get_relationships,
        mock_get_quests, mock_get_nearby_entities, mock_get_party, mock_get_player,
        mock_get_location_context, mock_get_guild_main_language
    ):
        # Setup mocks for all dependencies of prepare_ai_prompt
        mock_get_guild_main_language.return_value = "en"
        mock_get_location_context.return_value = {"name": "Test Location", "static_id": "test_loc_01", "description": "A place."}
        # Parameters to test_prepare_ai_prompt_requests_npc_static_id_and_relationships are:
        # mock_get_game_rules, mock_get_world_state, mock_get_relationships,
        # mock_get_quests, mock_get_nearby_entities, mock_get_party, mock_get_player,
        # mock_get_location_context, mock_get_guild_main_language
        # So, the ones to set are mock_get_player and mock_get_party.
        mock_get_player.return_value = {}
        mock_get_party.return_value = {}
        mock_get_nearby_entities.return_value = {"npcs": []}
        mock_get_quests.return_value = []
        mock_get_relationships.return_value = []
        mock_get_world_state.return_value = {"global_plot": "pending"}
        mock_get_game_rules.return_value = {"main_language_code": "en"}

        mock_session = MockAsyncSession()
        guild_id = 1
        location_id_for_context = 10

        from src.core.ai_prompt_builder import prepare_ai_prompt # Import here to use patches

        prompt = await prepare_ai_prompt(mock_session, guild_id, location_id_for_context)

        self.assertIsInstance(prompt, str)
        self.assertNotIn("Error: Location not found.", prompt)

        # Check for NPC static_id request in Generation Request
        self.assertIn("Ensure each generated NPC has a unique 'static_id'", prompt)

        # Check for Relationship generation request
        self.assertIn("5. Relationships: Specific relationships for the NPCs you generate.", prompt)
        self.assertIn("Use the 'relationship_schema'.", prompt)

        # Check Output Format Instructions for relationships
        self.assertIn("'generated_relationships'", prompt) # In the list of top-level keys
        self.assertIn("When generating NPCs and their relationships: ensure 'static_id' values for NPCs are used consistently", prompt)

        # Check that npc_schema in the prompt includes static_id
        # The full entity_schemas are dumped, so we need to check the content of npc_schema within it.
        # This is harder to check directly in the final string due to JSON formatting.
        # We rely on the setUp ensuring self.entity_schemas is correct and that it's dumped.
        # A more direct check would be to inspect the call to json.dumps if that was possible,
        # or to parse the JSON from the prompt and check the schema there.
        # For now, let's assume if "static_id" is in the description of npc_schema (as added in previous step), it's fine.
        self.assertIn("\"description\": \"Unique static identifier for this NPC, e.g., 'guard_captain_reynold'. Should be unique at least within the current generation batch for relationship linking.\"", prompt) # Corrected assertIn
        self.assertIn("\"relationship_schema\"", prompt) # Ensure relationship_schema is also there

# Placeholder for TestHiddenRelationshipsContext - to be added next
class TestHiddenRelationshipsContext(unittest.IsolatedAsyncioTestCase):

    @patch('src.core.crud.crud_relationship.crud_relationship', new_callable=AsyncMock) # Corrected patch target
    @patch('src.core.ai_prompt_builder.get_rule', new_callable=AsyncMock) # Keep this for get_rule in SUT
    async def test_get_hidden_relationships_context_basic(
        self, mock_get_rule, mock_crud_relationship_obj # Renamed mock arg
    ):
        from src.core.ai_prompt_builder import _get_hidden_relationships_context_for_dialogue
        from src.models import Relationship # Import real Relationship for mock return
        from src.models.enums import RelationshipEntityType # Import real Enum

        mock_session = MockAsyncSession()
        guild_id = 1
        lang = "en"
        npc_id = 100
        player_id = 1

        # Mock relationships returned for the NPC
        mock_npc_relationships = [
            Relationship(id=1, guild_id=guild_id, entity1_id=npc_id, entity1_type=RelationshipEntityType.GENERATED_NPC,
                         entity2_id=player_id, entity2_type=RelationshipEntityType.PLAYER,
                         relationship_type="secret_positive_to_entity", value=70),
            Relationship(id=2, guild_id=guild_id, entity1_id=npc_id, entity1_type=RelationshipEntityType.GENERATED_NPC,
                         entity2_id=5, entity2_type=RelationshipEntityType.GENERATED_FACTION,
                         relationship_type="secret_negative_to_faction:faction_evil", value=90),
            Relationship(id=3, guild_id=guild_id, entity1_id=npc_id, entity1_type=RelationshipEntityType.GENERATED_NPC,
                         entity2_id=101, entity2_type=RelationshipEntityType.GENERATED_NPC,
                         relationship_type="personal_debt_to_entity", value=50),
            Relationship(id=4, guild_id=guild_id, entity1_id=npc_id, entity1_type=RelationshipEntityType.GENERATED_NPC,
                         entity2_id=player_id, entity2_type=RelationshipEntityType.PLAYER,
                         relationship_type="normal_interaction_log", value=10), # Not a hidden one
        ]
        mock_crud_relationship_obj.get_relationships_for_entity.return_value = mock_npc_relationships

        # Mock RuleConfig responses
        # Rule for "secret_positive_to_entity" with player
        rule_for_secret_positive = {
            "enabled": True, "priority": 10,
            "prompt_modifier_hints_i18n": {"en": "This NPC secretly likes you (value: {value}).", "ru": "Вы тайно нравитесь этому NPC (значение: {value})."},
            "unlocks_dialogue_options_tags": ["secret_help"],
            "dialogue_option_availability_formula": "value > 50"
        }
        # Rule for "secret_negative_to_faction" (generic part of "secret_negative_to_faction:faction_evil")
        rule_for_secret_negative_generic = {
            "enabled": True, "priority": 5,
            "prompt_modifier_hints_i18n": {"en": "This NPC secretly despises the {relationship_description_en} (value: {value}).", "ru": "Этот NPC тайно презирает {relationship_description_ru} (значение: {value})."}
        }

        # Rule for "personal_debt_to_entity" (specific to NPC 101)
        # No specific rule, so generic should not be found either if we only mock this for specific type.
        # Let's assume no rule for personal_debt_to_entity.

        def get_rule_side_effect(session_arg, g_id_arg, key_arg, default=None):
            if key_arg == "hidden_relationship_effects:dialogue:secret_positive_to_entity":
                return rule_for_secret_positive
            # For "secret_negative_to_faction:faction_evil", first exact match, then generic
            if key_arg == "hidden_relationship_effects:dialogue:secret_negative_to_faction:faction_evil":
                return None # No exact rule
            if key_arg == "hidden_relationship_effects:dialogue:secret_negative_to_faction":
                return rule_for_secret_negative_generic
            return default

        mock_get_rule.side_effect = get_rule_side_effect

        context_list = await _get_hidden_relationships_context_for_dialogue(
            mock_session, guild_id, lang, npc_id, player_id
        )

        self.assertEqual(len(context_list), 1) # Only "secret_positive_to_entity" with player is processed due to player_id filter

        # Check the content of the processed "secret_positive_to_entity"
        rel1_ctx = context_list[0]
        self.assertEqual(rel1_ctx["relationship_type"], "secret_positive_to_entity")
        self.assertEqual(rel1_ctx["value"], 70)
        self.assertEqual(rel1_ctx["target_entity_id"], player_id)
        self.assertEqual(rel1_ctx["target_entity_type"], RelationshipEntityType.PLAYER.value)
        self.assertEqual(rel1_ctx["prompt_hints"], "This NPC secretly likes you (value: 70).") # Changed to assertEqual
        self.assertIn("secret_help", rel1_ctx["unlocks_tags"])
        self.assertEqual(rel1_ctx["options_availability_formula"], "value > 50")

        # Test without player_id (should include all hidden relationships of NPC)
        mock_crud_relationship_obj.get_relationships_for_entity.return_value = mock_npc_relationships # Reset mock for new call
        mock_get_rule.side_effect = get_rule_side_effect # Reset side effect for new call

        context_list_no_player = await _get_hidden_relationships_context_for_dialogue(
            mock_session, guild_id, lang, npc_id, player_id=None # No player_id
        )

        self.assertEqual(len(context_list_no_player), 3) # secret_positive, secret_negative, personal_debt

        # Find and check "secret_negative_to_faction:faction_evil"
        neg_rel_ctx = next((r for r in context_list_no_player if r["relationship_type"] == "secret_negative_to_faction:faction_evil"), None)
        self.assertIsNotNone(neg_rel_ctx)
        if neg_rel_ctx is not None: # Guard for Pyright
            self.assertEqual(neg_rel_ctx["value"], 90)
            self.assertEqual(neg_rel_ctx["target_entity_id"], 5) # Faction ID
            self.assertEqual(neg_rel_ctx["target_entity_type"], RelationshipEntityType.GENERATED_FACTION.value)
            # Description for "secret_negative_to_faction:faction_evil" becomes "negative to faction:faction evil"
            self.assertIn("This NPC secretly despises the negative to faction:faction evil (value: 90).", neg_rel_ctx["prompt_hints"])

        # Check "personal_debt_to_entity" - should have no hints as no rule was mocked for it
        debt_rel_ctx = next((r for r in context_list_no_player if r["relationship_type"] == "personal_debt_to_entity"), None)
        self.assertIsNotNone(debt_rel_ctx)
        if debt_rel_ctx is not None: # Guard for Pyright
            self.assertEqual(debt_rel_ctx["value"], 50)
            self.assertEqual(debt_rel_ctx["target_entity_id"], 101) # NPC ID
            self.assertEqual(debt_rel_ctx["target_entity_type"], RelationshipEntityType.GENERATED_NPC.value)
            self.assertEqual(debt_rel_ctx["prompt_hints"], "") # No rule, so no hints
            self.assertEqual(debt_rel_ctx["unlocks_tags"], [])


class TestAIQuestPromptBuilder(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.entity_schemas = _get_entity_schema_terms()
        # Schemas relevant for quest generation
        self.quest_schema_json = json.dumps(self.entity_schemas.get("quest_schema"), indent=2)
        self.quest_step_schema_json = json.dumps(self.entity_schemas.get("quest_step_schema"), indent=2)

    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_player_context', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder._get_location_context', new_callable=AsyncMock)
    async def test_prepare_quest_generation_prompt_basic_structure_and_content(
        self, mock_get_loc_ctx, mock_get_player_ctx, mock_get_all_rules, mock_get_lang
    ):
        """Test basic structure and content of prepare_quest_generation_prompt."""
        from src.core.ai_prompt_builder import prepare_quest_generation_prompt # Import SUT

        mock_get_lang.return_value = "en"
        mock_get_all_rules.return_value = {
            "ai:quest_generation:target_count": 2,
            "ai:quest_generation:themes_i18n": {"en": ["exploration", "mystery"], "ru": ["исследование", "тайна"]},
            "ai:quest_generation:complexity": "simple",
            "world_description": "A peaceful testing kingdom.",
            "ai:quest_generation:example_mechanics_json": {"type": "test_mech"},
            "ai:quest_generation:example_abstract_goal_json": {"desc_i18n": {"en": "Test Goal"}},
            "ai:quest_generation:example_consequences_json": {"effect": "test_consequence"}
        }
        mock_get_player_ctx.return_value = {"name": "Sir TestALot", "level": 7}
        mock_get_loc_ctx.return_value = {"name": "Testington Village", "type": "village"}

        session_mock = MockAsyncSession() # Using the defined mock session
        guild_id_test = 101

        result_prompt = await prepare_quest_generation_prompt(
            session_mock, guild_id_test, player_id_context=1, location_id_context=1
        )

        self.assertIsInstance(result_prompt, str)
        self.assertNotIn("Error generating quest AI prompt", result_prompt)

        self.assertIn("## AI Quest Generation Request", result_prompt)
        self.assertIn(f"Target Guild ID: {guild_id_test}", result_prompt)
        self.assertIn("Primary Language for Generation: en", result_prompt)

        # Check context inclusion
        self.assertIn("World Description: A peaceful testing kingdom.", result_prompt)
        self.assertIn("Player Context: Name: Sir TestALot, Level: 7", result_prompt)
        self.assertIn("Location Context: Name: Testington Village, Type: village", result_prompt)

        # Check rule-based instructions
        self.assertIn("Target Number of Quests to Generate: 2", result_prompt)
        self.assertIn("Suggested Quest Themes: exploration, mystery", result_prompt) # Checks English version
        self.assertIn("Desired Quest Complexity: simple", result_prompt)

        # Check schema inclusion (by checking for key parts of the schema descriptions)
        self.assertIn("Schema for Generated Quests.", result_prompt)
        self.assertIn("Schema for individual Quest Steps.", result_prompt)

        expected_schema_dump = json.dumps({
            "quest_schema": self.entity_schemas.get("quest_schema"),
            "quest_step_schema": self.entity_schemas.get("quest_step_schema")
        }, indent=2)
        self.assertIn(expected_schema_dump, result_prompt)

        # Check for example JSON field guidance
        self.assertIn("Example for 'required_mechanics_json': {\"type\": \"test_mech\"}", result_prompt)
        self.assertIn("Example for 'abstract_goal_json': {\"desc_i18n\": {\"en\": \"Test Goal\"}}", result_prompt)
        self.assertIn("Example for 'consequences_json': {\"effect\": \"test_consequence\"}", result_prompt)

        # Check output format instructions
        self.assertIn("Provide your response as a single JSON array", result_prompt)
        self.assertIn("where each element is a quest object conforming to 'quest_schema'", result_prompt)

    @patch('src.core.ai_prompt_builder._get_guild_main_language', new_callable=AsyncMock)
    @patch('src.core.ai_prompt_builder.get_all_rules_for_guild', new_callable=AsyncMock)
    async def test_prepare_quest_generation_prompt_uses_defaults_for_missing_rules(
        self, mock_get_all_rules, mock_get_lang
    ):
        """Test that the prompt builder uses default values if RuleConfig entries are missing."""
        from src.core.ai_prompt_builder import prepare_quest_generation_prompt # Import SUT

        mock_get_lang.return_value = "ru" # Test with a different primary language
        mock_get_all_rules.return_value = {
            # Missing: target_count, themes, complexity, examples, world_description
        }

        session_mock = MockAsyncSession()
        guild_id_test = 102

        result_prompt = await prepare_quest_generation_prompt(session_mock, guild_id_test) # No player/location context

        self.assertIsInstance(result_prompt, str)
        self.assertNotIn("Error generating quest AI prompt", result_prompt)
        self.assertIn("Primary Language for Generation: ru", result_prompt)

        # Check for default values (as defined in prepare_quest_generation_prompt)
        self.assertIn("Target Number of Quests to Generate: 1", result_prompt) # Default
        self.assertIn("Suggested Quest Themes: поиск артефакта, охота на монстра, местная тайна", result_prompt) # Default, Russian
        self.assertIn("Desired Quest Complexity: medium", result_prompt) # Default
        self.assertIn("World Description: A generic fantasy world context.", result_prompt) # Default

        # Ensure examples are still present (using their defaults from the function)
        default_example_mechanics = {"type": "fetch", "item_static_id": "sample_item", "count": 1, "target_npc_static_id_for_delivery": "sample_npc"}
        self.assertIn(f"Example for 'required_mechanics_json': {json.dumps(default_example_mechanics)}", result_prompt)

        self.assertNotIn("Player Context:", result_prompt)
        self.assertNotIn("Location Context:", result_prompt)

if __name__ == "__main__":
    unittest.main()
