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


if __name__ == "__main__":
    unittest.main()
