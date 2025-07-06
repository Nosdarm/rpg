# tests/core/test_world_generation.py
import sys
import os
import unittest # Changed from pytest
import json # Added
from typing import Optional, Dict, Any, List, cast # Added List and cast
from unittest.mock import patch, AsyncMock, MagicMock

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')) # Corrected path
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine # Added create_async_engine etc.
from sqlalchemy import event, select # Added select
from src.models.base import Base # Added
from src.models.guild import GuildConfig # Added
from src.models.rule_config import RuleConfig # Added
from src.models.location import Location, LocationType
from src.models.generated_faction import GeneratedFaction # Added
from src.models.relationship import Relationship # Added
from src.models.enums import EventType, RelationshipEntityType # Added RelationshipEntityType
from src.models.custom_types import JsonBForSQLite # Added

from src.core.crud.crud_location import location_crud # Added
from src.core.crud.crud_faction import crud_faction # Added
from src.core.crud.crud_relationship import crud_relationship # Added
from src.core.world_generation import generate_location, update_location_neighbors, generate_factions_and_relationships # Added new func
from src.core.ai_response_parser import ParsedLocationData, ParsedAiData, CustomValidationError, ParsedFactionData, ParsedRelationshipData # Added Faction/Rel data

# Event listeners for SQLite compatibility
@event.listens_for(Location.__table__, "column_reflect")
def _location_column_reflect_world_gen(inspector, table, column_info):
    json_fields = ['name_i18n', 'descriptions_i18n', 'coordinates_json', 'neighbor_locations_json', 'generated_details_json', 'ai_metadata_json']
    if column_info['name'] in json_fields:
        if not isinstance(column_info['type'], JsonBForSQLite):
            column_info['type'] = JsonBForSQLite()

@event.listens_for(GeneratedFaction.__table__, "column_reflect")
def _generated_faction_column_reflect_world_gen(inspector, table, column_info):
    json_fields = ['name_i18n', 'description_i18n', 'ideology_i18n', 'resources_json', 'ai_metadata_json']
    if column_info['name'] in json_fields:
        if not isinstance(column_info['type'], JsonBForSQLite):
            column_info['type'] = JsonBForSQLite()

@event.listens_for(RuleConfig.__table__, "column_reflect")
def _rule_config_column_reflect_world_gen(inspector, table, column_info):
    if column_info['name'] == 'value_json':
        if not isinstance(column_info['type'], JsonBForSQLite):
            column_info['type'] = JsonBForSQLite()

# Relationship model does not have JSON fields currently that need this handler.

class TestWorldGeneration(unittest.IsolatedAsyncioTestCase): # Changed to unittest.IsolatedAsyncioTestCase
    engine: Optional[AsyncEngine] = None
    SessionLocal: Optional[async_sessionmaker[AsyncSession]] = None

    test_guild_id = 301
    other_guild_id = 302 # For tests involving multiple guilds
    default_lang = "en"

    @classmethod
    def setUpClass(cls):
        cls.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        cls.SessionLocal = async_sessionmaker(
            bind=cls.engine, class_=AsyncSession, expire_on_commit=False
        )

    @classmethod
    def tearDownClass(cls):
        if cls.engine:
            import asyncio
            asyncio.run(cls.engine.dispose())

    async def asyncSetUp(self):
        assert self.SessionLocal is not None
        self.session: AsyncSession = self.SessionLocal() # type: ignore
        # Mock commit, rollback, flush for testing calls on the real session object
        # We are creating a real session, so we need to mock its methods if we want to assert calls on them
        # Assigning AsyncMock instances and then casting for Pyright's benefit
        self.session_commit_mock = AsyncMock()
        self.session_rollback_mock = AsyncMock()
        self.session_flush_mock = AsyncMock()
        self.session.commit = self.session_commit_mock # type: ignore
        self.session.rollback = self.session_rollback_mock # type: ignore
        self.session.flush = self.session_flush_mock # type: ignore


        assert self.engine is not None
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        # Setup GuildConfigs and basic RuleConfigs
        for gid in [self.test_guild_id, self.other_guild_id]:
            guild = await self.session.get(GuildConfig, gid)
            if not guild:
                self.session.add(GuildConfig(id=gid, main_language=self.default_lang, name=f"Guild {gid}"))

            # Basic rule for main language, used by some mocked functions or underlying logic
            rule_lang_key = "guild_main_language"
            # Query for existing rule by guild_id and key
            stmt = select(RuleConfig).where(RuleConfig.guild_id == gid, RuleConfig.key == rule_lang_key)
            result = await self.session.execute(stmt)
            existing_rule = result.scalar_one_or_none()

            if not existing_rule:
                 self.session.add(RuleConfig(guild_id=gid, key=rule_lang_key, value_json=self.default_lang))

        await self.session.commit()
        self.session_commit_mock.reset_mock() # Сбрасываем мок после коммита в asyncSetUp

        # Mock for location_crud and other cruds if needed by tests
        self.mock_location_crud = MagicMock()
        self.mock_location_crud.create = AsyncMock()
        self.mock_location_crud.get_by_static_id = AsyncMock()
        self.mock_location_crud.get = AsyncMock()

        self.mock_faction_crud = MagicMock(spec=crud_faction)
        self.mock_faction_crud.create = AsyncMock()
        self.mock_faction_crud.get_by_static_id = AsyncMock()

        self.mock_relationship_crud = MagicMock(spec=crud_relationship)
        self.mock_relationship_crud.create = AsyncMock()
        self.mock_relationship_crud.get_relationship_between_entities = AsyncMock(return_value=None)


    async def asyncTearDown(self):
        if hasattr(self, 'session') and self.session:
            await self.session.rollback() # Ensure rollback after each test
            await self.session.close()

    # Existing tests will be adapted below...
    # For example, test_generate_new_location_via_ai_success would become:
    async def test_generate_new_location_via_ai_success(self): # Removed pytest fixtures
        guild_id = self.test_guild_id # Use instance guild_id
        self.session_commit_mock.reset_mock() # type: ignore
        self.session_rollback_mock.reset_mock() # type: ignore
        context_location_id = 10

        mock_parsed_location_data = ParsedLocationData(
            entity_type="location",
            name_i18n={"en": "Generated Test Location", "ru": "Сген Тест Локация"},
            descriptions_i18n={"en": "A test description", "ru": "Тестовое описание"},
            location_type="FOREST",
            coordinates_json={"x": 1, "y": 1},
            generated_details_json={"detail": "some detail"},
            potential_neighbors=[
                {"static_id_or_name": "neighbor1_static", "connection_description_i18n": {"en": "a path", "ru": "тропа"}}
            ]
        )
        mock_parsed_ai_data = ParsedAiData(
            generated_entities=[mock_parsed_location_data],
            raw_ai_output="mock raw output",
            parsing_metadata={}
        )

        created_location_mock = Location(
            id=100, guild_id=guild_id, name_i18n=mock_parsed_location_data.name_i18n,
            descriptions_i18n=mock_parsed_location_data.descriptions_i18n, type=LocationType.FOREST,
            coordinates_json=mock_parsed_location_data.coordinates_json,
            generated_details_json=mock_parsed_location_data.generated_details_json,
            neighbor_locations_json=[]
        )
        self.mock_location_crud.create.return_value = created_location_mock

        existing_neighbor_mock = Location(id=200, guild_id=guild_id, static_id="neighbor1_static", name_i18n={"en":"Neighbor 1"}, neighbor_locations_json=[])
        self.mock_location_crud.get_by_static_id.return_value = existing_neighbor_mock
        self.mock_location_crud.get.return_value = existing_neighbor_mock

        with patch("src.core.world_generation.prepare_ai_prompt", new_callable=AsyncMock, return_value="Test Prompt") as mock_prepare_prompt, \
             patch("src.core.world_generation._mock_openai_api_call", new_callable=AsyncMock, return_value='[{"entity_type": "location", ...}]') as mock_ai_call, \
             patch("src.core.world_generation.parse_and_validate_ai_response", new_callable=AsyncMock, return_value=mock_parsed_ai_data) as mock_parse_validate, \
             patch("src.core.world_generation.log_event", new_callable=AsyncMock) as mock_log_event, \
             patch("src.core.world_generation.location_crud", new=self.mock_location_crud), \
             patch("src.core.world_generation.update_location_neighbors", new_callable=AsyncMock) as mock_update_neighbors:

            location, error = await generate_location(
                session=self.session, # Use self.session
                guild_id=guild_id,
                location_id_context=context_location_id
            )

            self.assertIsNone(error)
            self.assertIsNotNone(location)
            if location: # Guard for Pyright
                self.assertEqual(location.id, 100)
                self.assertEqual(location.name_i18n["en"], "Generated Test Location")

            mock_prepare_prompt.assert_called_once()
            mock_ai_call.assert_called_once()
            mock_parse_validate.assert_called_once()
            self.mock_location_crud.create.assert_called_once()
            # Assuming created_location_mock.id is safe if location_crud.create worked as expected.
            # And existing_neighbor_mock is also assumed to be valid for this test.
            if location: # Guard for mock_update_neighbors if it depends on location details not covered by created_location_mock
                 mock_update_neighbors.assert_called_once_with( # type: ignore
                     self.session, existing_neighbor_mock, created_location_mock.id, {"en": "a path", "ru": "тропа"}, add_connection=True
                 )

            mock_log_event.assert_called_once() # type: ignore
            # Assuming mock_log_event.call_args.kwargs is a dict after being called
            self.assertEqual(mock_log_event.call_args.kwargs["event_type"], EventType.WORLD_EVENT_LOCATION_GENERATED.value)
            self.assertEqual(mock_log_event.call_args.kwargs["details_json"]["location_id"], 100)

            self.session_commit_mock.assert_called_once() # type: ignore

    async def test_generate_new_location_ai_validation_error(self): # Removed pytest fixtures
        guild_id = self.test_guild_id
        self.session_commit_mock.reset_mock() # type: ignore
        self.session_rollback_mock.reset_mock() # type: ignore
        validation_error = CustomValidationError(error_type="TestError", message="AI validation failed")

        with patch("src.core.world_generation.prepare_ai_prompt", new_callable=AsyncMock, return_value="Test Prompt"), \
             patch("src.core.world_generation._mock_openai_api_call", new_callable=AsyncMock, return_value='invalid json'), \
             patch("src.core.world_generation.parse_and_validate_ai_response", new_callable=AsyncMock, return_value=validation_error):

            location, error = await generate_location(
                session=self.session, # Use self.session
                guild_id=guild_id
            )
            self.assertIsNone(location)
            self.assertIsNotNone(error)
            if error: # Type guard for Pyright
                self.assertIn("AI validation failed", error)
            # self.session.rollback.assert_called_once() # Rollback is not called if error is returned before exception block


    async def test_generate_new_location_no_location_data_in_response(self): # Removed pytest fixtures
        guild_id = self.test_guild_id
        self.session_commit_mock.reset_mock() # type: ignore
        self.session_rollback_mock.reset_mock() # type: ignore
        mock_parsed_ai_data_empty = ParsedAiData(generated_entities=[], raw_ai_output="mock raw output", parsing_metadata={})

        with patch("src.core.world_generation.prepare_ai_prompt", new_callable=AsyncMock, return_value="Test Prompt"), \
             patch("src.core.world_generation._mock_openai_api_call", new_callable=AsyncMock, return_value='[]'), \
             patch("src.core.world_generation.parse_and_validate_ai_response", new_callable=AsyncMock, return_value=mock_parsed_ai_data_empty):

            location, error = await generate_location(
                session=self.session, # Use self.session
                guild_id=guild_id
            )
            self.assertIsNone(location)
            self.assertIsNotNone(error)
            if error: # Type guard for Pyright
                self.assertIn("No valid location data found", error)
            # self.session.rollback.assert_called_once() # Rollback is not called if error is returned before exception block


    async def test_update_location_neighbors_add_connection(self): # Removed pytest fixtures
        loc1 = Location(id=1, guild_id=self.test_guild_id, name_i18n={"en":"Loc1"}, neighbor_locations_json=[])
        neighbor_id = 2
        conn_type = {"en": "a bridge", "ru": "мост"}

        await update_location_neighbors(self.session, loc1, neighbor_id, conn_type, add_connection=True)

        self.assertIsNotNone(loc1.neighbor_locations_json)
        if loc1.neighbor_locations_json: # Guard for Pyright
            self.assertEqual(len(loc1.neighbor_locations_json), 1)
            self.assertEqual(loc1.neighbor_locations_json[0]["id"], neighbor_id) # type: ignore
            self.assertEqual(loc1.neighbor_locations_json[0]["type_i18n"], conn_type) # type: ignore
        self.session_flush_mock.assert_called_once_with([loc1]) # type: ignore


    async def test_update_location_neighbors_remove_connection(self): # Removed pytest fixtures
        neighbor_id_to_remove = 2
        initial_neighbors = [
            {"id": neighbor_id_to_remove, "type_i18n": {"en": "a bridge"}},
            {"id": 3, "type_i18n": {"en": "a tunnel"}}
        ]
        loc1 = Location(id=1, guild_id=self.test_guild_id, name_i18n={"en":"Loc1"}, neighbor_locations_json=initial_neighbors)

        await update_location_neighbors(self.session, loc1, neighbor_id_to_remove, {}, add_connection=False)

        self.assertIsNotNone(loc1.neighbor_locations_json)
        if loc1.neighbor_locations_json: # Guard for Pyright
            self.assertEqual(len(loc1.neighbor_locations_json), 1)
            self.assertEqual(loc1.neighbor_locations_json[0]["id"], 3) # type: ignore
        self.session_flush_mock.assert_called_once_with([loc1]) # type: ignore


    async def test_update_location_neighbors_add_existing_does_not_duplicate(self): # Removed pytest fixtures
        existing_neighbor_id = 2
        conn_type = {"en": "a bridge", "ru": "мост"}
        initial_neighbors = [{"id": existing_neighbor_id, "type_i18n": conn_type}]
        loc1 = Location(id=1, guild_id=self.test_guild_id, name_i18n={"en":"Loc1"}, neighbor_locations_json=initial_neighbors)

        await update_location_neighbors(self.session, loc1, existing_neighbor_id, conn_type, add_connection=True)

        self.assertIsNotNone(loc1.neighbor_locations_json)
        if loc1.neighbor_locations_json: # Guard for Pyright
            self.assertEqual(len(loc1.neighbor_locations_json), 1)
            self.assertEqual(loc1.neighbor_locations_json[0]["id"], existing_neighbor_id) # type: ignore
        self.session_flush_mock.assert_called_once_with([loc1]) # type: ignore


    async def test_generate_new_location_potential_neighbor_not_found(self): # Removed pytest fixtures
        guild_id = self.test_guild_id
        self.session_commit_mock.reset_mock() # type: ignore
        self.session_rollback_mock.reset_mock() # type: ignore
        mock_parsed_location_data = ParsedLocationData(
            entity_type="location",
            name_i18n={"en": "Test Loc"}, descriptions_i18n={"en": "Desc"}, location_type="PLAINS",
            potential_neighbors=[{"static_id_or_name": "non_existent_neighbor", "connection_description_i18n": {"en": "a track"}}]
        )
        mock_parsed_ai_data = ParsedAiData(generated_entities=[mock_parsed_location_data], raw_ai_output="", parsing_metadata={})
        created_location_mock = Location(id=101, guild_id=guild_id, name_i18n=mock_parsed_location_data.name_i18n, neighbor_locations_json=[])

        self.mock_location_crud.create.return_value = created_location_mock
        self.mock_location_crud.get_by_static_id.return_value = None

        with patch("src.core.world_generation.prepare_ai_prompt", new_callable=AsyncMock, return_value="Prompt"), \
             patch("src.core.world_generation._mock_openai_api_call", new_callable=AsyncMock, return_value='[{}]'), \
             patch("src.core.world_generation.parse_and_validate_ai_response", new_callable=AsyncMock, return_value=mock_parsed_ai_data), \
             patch("src.core.world_generation.log_event", new_callable=AsyncMock) as mock_log_event, \
             patch("src.core.world_generation.location_crud", new=self.mock_location_crud), \
             patch("src.core.world_generation.update_location_neighbors", new_callable=AsyncMock) as mock_update_neighbors:

            location, error = await generate_location(self.session, guild_id)

            self.assertIsNone(error)
            self.assertIsNotNone(location)
            if location: # Guard for Pyright
                self.assertEqual(location.id, 101)
                self.assertFalse(location.neighbor_locations_json)

            mock_update_neighbors.assert_not_called() # type: ignore
            self.session_commit_mock.assert_called_once() # type: ignore

    async def test_generate_new_location_parent_not_found(self):
        guild_id = self.test_guild_id
        self.session_commit_mock.reset_mock()
        self.session_rollback_mock.reset_mock()
        mock_parsed_location_data = ParsedLocationData(
            entity_type="location", name_i18n={"en": "Child Loc"}, descriptions_i18n={"en": "Desc"}, location_type="CAVE"
        )
        mock_parsed_ai_data = ParsedAiData(generated_entities=[mock_parsed_location_data], raw_ai_output="", parsing_metadata={})
        created_location_mock = Location(id=102, guild_id=guild_id, name_i18n=mock_parsed_location_data.name_i18n, neighbor_locations_json=[])

        self.mock_location_crud.create.return_value = created_location_mock
        self.mock_location_crud.get.return_value = None # Parent location not found

        with patch("src.core.world_generation.prepare_ai_prompt", new_callable=AsyncMock, return_value="Prompt"), \
             patch("src.core.world_generation._mock_openai_api_call", new_callable=AsyncMock, return_value='[{}]'), \
             patch("src.core.world_generation.parse_and_validate_ai_response", new_callable=AsyncMock, return_value=mock_parsed_ai_data), \
             patch("src.core.world_generation.log_event", new_callable=AsyncMock) as mock_log_event, \
             patch("src.core.world_generation.location_crud", new=self.mock_location_crud), \
             patch("src.core.world_generation.update_location_neighbors", new_callable=AsyncMock) as mock_update_neighbors:

            location, error = await generate_location(self.session, guild_id, parent_location_id=999)

            self.assertIsNone(error)
            self.assertIsNotNone(location)
            if location:
                self.assertEqual(location.id, 102)
                # Parent not found, so no explicit link should be made via update_location_neighbors for parent
                # It might still be called for AI suggested neighbors if any.
                # For this test, assume no AI suggested neighbors for simplicity to check parent linking part.
                # If mock_parsed_location_data had potential_neighbors, mock_update_neighbors would be called for them.
                # Here, we check that update_location_neighbors was NOT called for the non-existent parent.
                # If there were other neighbors, it would be called for them.
                # The current mock_parsed_location_data has no potential_neighbors.
                mock_update_neighbors.assert_not_called()


            self.session_commit_mock.assert_called_once()
            mock_log_event.assert_called_once()
            log_details = mock_log_event.call_args.kwargs['details_json']
            self.assertEqual(log_details['parent_location_id'], 999) # Still logs the attempt

    async def test_generate_new_location_invalid_potential_neighbor_data(self):
        guild_id = self.test_guild_id
        self.session_commit_mock.reset_mock()
        mock_parsed_location_data = ParsedLocationData(
            entity_type="location", name_i18n={"en": "Test Loc Inv Neigh"}, descriptions_i18n={"en": "Desc"}, location_type="RUINS",
            potential_neighbors=[
                {"connection_description_i18n": {"en": "a faulty path"}}, # Missing static_id_or_name
                {"static_id_or_name": None, "connection_description_i18n": {"en": "another faulty path"}} # static_id_or_name is None
            ]
        )
        mock_parsed_ai_data = ParsedAiData(generated_entities=[mock_parsed_location_data], raw_ai_output="", parsing_metadata={})
        created_location_mock = Location(id=103, guild_id=guild_id, name_i18n=mock_parsed_location_data.name_i18n, neighbor_locations_json=[])
        self.mock_location_crud.create.return_value = created_location_mock

        with patch("src.core.world_generation.prepare_ai_prompt", new_callable=AsyncMock, return_value="Prompt"), \
             patch("src.core.world_generation._mock_openai_api_call", new_callable=AsyncMock, return_value='[{}]'), \
             patch("src.core.world_generation.parse_and_validate_ai_response", new_callable=AsyncMock, return_value=mock_parsed_ai_data), \
             patch("src.core.world_generation.log_event", new_callable=AsyncMock), \
             patch("src.core.world_generation.location_crud", new=self.mock_location_crud), \
             patch("src.core.world_generation.update_location_neighbors", new_callable=AsyncMock) as mock_update_neighbors:

            location, error = await generate_location(self.session, guild_id)

            self.assertIsNone(error)
            self.assertIsNotNone(location)
            mock_update_neighbors.assert_not_called() # No valid neighbors to link
            self.session_commit_mock.assert_called_once()

    async def test_generate_new_location_default_connection_description(self):
        guild_id = self.test_guild_id
        parent_loc_id = 500
        self.session_commit_mock.reset_mock()

        mock_parsed_location_data = ParsedLocationData(
            entity_type="location", name_i18n={"en": "Child Default Conn"}, descriptions_i18n={"en": "Desc"}, location_type="FOREST"
        )
        mock_parsed_ai_data = ParsedAiData(generated_entities=[mock_parsed_location_data], raw_ai_output="", parsing_metadata={})
        created_location_mock = Location(id=104, guild_id=guild_id, name_i18n=mock_parsed_location_data.name_i18n, neighbor_locations_json=[])
        parent_location_mock = Location(id=parent_loc_id, guild_id=guild_id, name_i18n={"en":"Parent"}, neighbor_locations_json=[])

        self.mock_location_crud.create.return_value = created_location_mock
        self.mock_location_crud.get.return_value = parent_location_mock # Parent found

        with patch("src.core.world_generation.prepare_ai_prompt", new_callable=AsyncMock, return_value="Prompt"), \
             patch("src.core.world_generation._mock_openai_api_call", new_callable=AsyncMock, return_value='[{}]'), \
             patch("src.core.world_generation.parse_and_validate_ai_response", new_callable=AsyncMock, return_value=mock_parsed_ai_data), \
             patch("src.core.world_generation.log_event", new_callable=AsyncMock) as mock_log_event, \
             patch("src.core.world_generation.location_crud", new=self.mock_location_crud), \
             patch("src.core.world_generation.update_location_neighbors", new_callable=AsyncMock) as mock_update_neighbors:

            # Call generate_location without connection_details_i18n
            location, error = await generate_location(self.session, guild_id, parent_location_id=parent_loc_id, connection_details_i18n=None)

            self.assertIsNone(error)
            self.assertIsNotNone(location)

            # Check that update_location_neighbors was called with default connection details
            expected_default_conn_desc = {"en": "a path", "ru": "тропа"}
            mock_update_neighbors.assert_called_once_with(
                self.session, parent_location_mock, created_location_mock.id, expected_default_conn_desc, add_connection=True
            )
            self.session_commit_mock.assert_called_once()
            log_details = mock_log_event.call_args.kwargs['details_json']
            self.assertEqual(log_details['connection_details_i18n'], None) # Logs original input which was None

    async def test_generate_new_location_malformed_initial_neighbors(self):
        guild_id = self.test_guild_id
        self.session_commit_mock.reset_mock()

        mock_parsed_location_data = ParsedLocationData(
            entity_type="location", name_i18n={"en": "Malformed Init"}, descriptions_i18n={"en": "Desc"}, location_type="SWAMP"
        )
        mock_parsed_ai_data = ParsedAiData(generated_entities=[mock_parsed_location_data], raw_ai_output="", parsing_metadata={})

        # Simulate that the created Location object somehow gets a malformed neighbor_locations_json
        # This tests the robustness of the neighbor processing logic.
        created_location_mock = Location(
            id=105, guild_id=guild_id, name_i18n=mock_parsed_location_data.name_i18n,
            neighbor_locations_json="this is not a list" # Malformed data
        )
        self.mock_location_crud.create.return_value = created_location_mock

        with patch("src.core.world_generation.prepare_ai_prompt", new_callable=AsyncMock, return_value="Prompt"), \
             patch("src.core.world_generation._mock_openai_api_call", new_callable=AsyncMock, return_value='[{}]'), \
             patch("src.core.world_generation.parse_and_validate_ai_response", new_callable=AsyncMock, return_value=mock_parsed_ai_data), \
             patch("src.core.world_generation.log_event", new_callable=AsyncMock), \
             patch("src.core.world_generation.location_crud", new=self.mock_location_crud), \
             patch("src.core.world_generation.update_location_neighbors", new_callable=AsyncMock) as mock_update_neighbors:

            location, error = await generate_location(self.session, guild_id)

            self.assertIsNone(error)
            self.assertIsNotNone(location)
            if location:
                # The important part is that it doesn't crash and current_neighbor_links_for_new_loc is empty.
                # If there were valid AI suggested neighbors, they would be added.
                # Here, we assume no AI neighbors to isolate the initial malformed data handling.
                self.assertEqual(location.neighbor_locations_json, []) # Should be reset to empty list and saved.

            self.session_commit_mock.assert_called_once()


    # --- Tests for generate_factions_and_relationships ---

    @patch('src.core.world_generation.prepare_faction_relationship_generation_prompt', new_callable=AsyncMock)
    @patch('src.core.world_generation._mock_openai_api_call', new_callable=AsyncMock)
    @patch('src.core.world_generation.parse_and_validate_ai_response', new_callable=AsyncMock)
    @patch('src.core.world_generation.log_event', new_callable=AsyncMock, return_value=MagicMock(id=12345))
    @patch('src.core.world_generation.crud_faction', new_callable=MagicMock)
    @patch('src.core.world_generation.crud_relationship', new_callable=MagicMock)
    async def test_generate_factions_and_relationships_success(
        self, mock_crud_relationship, mock_crud_faction, mock_log_event,
        mock_parse_validate, mock_ai_call, mock_prepare_prompt
    ):
        guild_id = self.test_guild_id
        self.session_commit_mock.reset_mock()
        self.session_rollback_mock.reset_mock()

        mock_prepare_prompt.return_value = "faction_rel_prompt"

        # Mocking the direct output of parse_and_validate_ai_response
        parsed_faction1_data = ParsedFactionData(
            entity_type="faction", static_id="fac1_sid", name_i18n={"en": "Faction One"}, description_i18n={"en":"Desc1"}
        )
        parsed_faction2_data = ParsedFactionData(
            entity_type="faction", static_id="fac2_sid", name_i18n={"en": "Faction Two"}, description_i18n={"en":"Desc2"}
        )
        parsed_relationship_data = ParsedRelationshipData(
            entity_type="relationship", entity1_static_id="fac1_sid", entity1_type="faction", # Corrected type
            entity2_static_id="fac2_sid", entity2_type="faction", # Corrected type
            relationship_type="alliance", value=75
        )
        mock_parsed_ai_data_success = ParsedAiData(
            generated_entities=[parsed_faction1_data, parsed_faction2_data, parsed_relationship_data],
            raw_ai_output="dummy_raw_output_for_factions",
            parsing_metadata={}
        )
        mock_parse_validate.return_value = mock_parsed_ai_data_success

        created_faction1_db = GeneratedFaction(id=1, guild_id=guild_id, static_id="fac1_sid", name_i18n={"en": "Faction One DB"}, description_i18n={})
        created_faction2_db = GeneratedFaction(id=2, guild_id=guild_id, static_id="fac2_sid", name_i18n={"en": "Faction Two DB"}, description_i18n={})

        mock_crud_faction.create = AsyncMock(side_effect=[created_faction1_db, created_faction2_db])
        mock_crud_faction.get_by_static_id = AsyncMock(return_value=None)

        created_relationship_db = Relationship(
            id=10, guild_id=guild_id, entity1_id=1, entity1_type=RelationshipEntityType.GENERATED_FACTION,
            entity2_id=2, entity2_type=RelationshipEntityType.GENERATED_FACTION,
            relationship_type="alliance", value=75
        )
        mock_crud_relationship.create = AsyncMock(return_value=created_relationship_db)
        mock_crud_relationship.get_relationship_between_entities = AsyncMock(return_value=None)

        factions, relationships, error = await generate_factions_and_relationships(self.session, guild_id)

        self.assertIsNone(error)
        self.assertIsNotNone(factions)
        self.assertIsNotNone(relationships)
        if factions: self.assertEqual(len(factions), 2)
        if relationships: self.assertEqual(len(relationships), 1)

        self.assertEqual(mock_crud_faction.create.call_count, 2)
        call_args_f1 = mock_crud_faction.create.call_args_list[0][1]['obj_in']
        self.assertEqual(call_args_f1['static_id'], "fac1_sid")

        mock_crud_relationship.create.assert_called_once()
        call_args_rel = mock_crud_relationship.create.call_args[1]['obj_in']
        self.assertEqual(call_args_rel['entity1_id'], created_faction1_db.id)
        self.assertEqual(call_args_rel['entity2_id'], created_faction2_db.id)

        mock_log_event.assert_called_once()
        log_args = mock_log_event.call_args.kwargs
        self.assertEqual(log_args['event_type'], EventType.WORLD_EVENT_FACTIONS_GENERATED.value)
        self.session_commit_mock.assert_called_once()

    @patch('src.core.world_generation.prepare_faction_relationship_generation_prompt', new_callable=AsyncMock)
    @patch('src.core.world_generation.parse_and_validate_ai_response', new_callable=AsyncMock) # No need to mock _mock_openai_api_call if this is mocked
    async def test_generate_factions_and_relationships_parsing_error(
        self, mock_parse_validate, mock_prepare_prompt
    ):
        guild_id = self.test_guild_id
        mock_prepare_prompt.return_value = "faction_rel_prompt_parse_error"
        validation_error = CustomValidationError(error_type="TestParsingError", message="Simulated parsing error")
        mock_parse_validate.return_value = validation_error

        factions, relationships, error_message = await generate_factions_and_relationships(self.session, guild_id)

        self.assertIsNone(factions)
        self.assertIsNone(relationships)
        self.assertIsNotNone(error_message)
        if error_message: self.assertIn("Simulated parsing error", error_message)
        self.session_rollback_mock.assert_not_called() # Error returned before DB ops

    @patch('src.core.world_generation.prepare_faction_relationship_generation_prompt', new_callable=AsyncMock)
    @patch('src.core.world_generation.parse_and_validate_ai_response', new_callable=AsyncMock)
    @patch('src.core.world_generation.crud_faction', new_callable=MagicMock)
    @patch('src.core.world_generation.crud_relationship', new_callable=MagicMock)
    @patch('src.core.world_generation.log_event', new_callable=AsyncMock, return_value=MagicMock(id=67890)) # Added mock for log_event
    async def test_generate_factions_and_relationships_existing_static_id(
        self, mock_log_event, mock_crud_relationship, mock_crud_faction, mock_parse_validate, mock_prepare_prompt # Corrected order & added mock_log_event
    ):
        guild_id = self.test_guild_id
        existing_static_id = "existing_fac_sid"
        existing_faction_db = GeneratedFaction(id=50, guild_id=guild_id, static_id=existing_static_id, name_i18n={"en": "Original Faction"}, description_i18n={})

        async def mock_get_by_static_id_side_effect(session, guild_id, static_id):
            return existing_faction_db if static_id == existing_static_id else None
        mock_crud_faction.get_by_static_id = AsyncMock(side_effect=mock_get_by_static_id_side_effect)

        new_faction_static_id = "new_fac_sid"
        new_faction_db = GeneratedFaction(id=51, guild_id=guild_id, static_id=new_faction_static_id, name_i18n={"en": "New Faction DB"}, description_i18n={})
        mock_crud_faction.create = AsyncMock(return_value=new_faction_db)

        mock_prepare_prompt.return_value = "faction_rel_prompt_existing_sid"

        parsed_faction_existing_data = ParsedFactionData(entity_type="faction", static_id=existing_static_id, name_i18n={"en": "Faction Existing (AI)"}, description_i18n={"en":"Desc Existing"})
        parsed_faction_new_data = ParsedFactionData(entity_type="faction", static_id=new_faction_static_id, name_i18n={"en": "New Faction (AI)"}, description_i18n={"en":"Desc New"})
        parsed_relationship_data = ParsedRelationshipData(entity_type="relationship", entity1_static_id=existing_static_id, entity1_type="faction", entity2_static_id=new_faction_static_id, entity2_type="faction", relationship_type="neutral_standing", value=0) # Corrected types

        mock_parse_validate.return_value = ParsedAiData(generated_entities=[parsed_faction_existing_data, parsed_faction_new_data, parsed_relationship_data], raw_ai_output="dummy")

        created_relationship_db = Relationship(id=20, guild_id=guild_id, entity1_id=existing_faction_db.id, entity1_type=RelationshipEntityType.GENERATED_FACTION, entity2_id=new_faction_db.id, entity2_type=RelationshipEntityType.GENERATED_FACTION, relationship_type="neutral_standing", value=0)
        mock_crud_relationship.create = AsyncMock(return_value=created_relationship_db)
        mock_crud_relationship.get_relationship_between_entities = AsyncMock(return_value=None)

        factions, relationships, error = await generate_factions_and_relationships(self.session, guild_id)

        self.assertIsNone(error)
        self.assertIsNotNone(factions)
        if factions: self.assertEqual(len(factions), 2)
        mock_crud_faction.create.assert_called_once() # Only for the new one

        if relationships: self.assertEqual(len(relationships), 1)
        mock_crud_relationship.create.assert_called_once()
        call_args_rel = mock_crud_relationship.create.call_args[1]['obj_in']
        self.assertEqual(call_args_rel['entity1_id'], existing_faction_db.id)
        self.assertEqual(call_args_rel['entity2_id'], new_faction_db.id)
        self.session_commit_mock.assert_called_once()

    # --- Tests for generate_quests_for_guild ---

    @patch('src.core.world_generation.prepare_quest_generation_prompt', new_callable=AsyncMock)
    @patch('src.core.world_generation._mock_openai_api_call', new_callable=AsyncMock)
    @patch('src.core.world_generation.parse_and_validate_ai_response', new_callable=AsyncMock)
    @patch('src.core.world_generation.generated_quest_crud', new_callable=MagicMock)
    @patch('src.core.world_generation.quest_step_crud', new_callable=MagicMock)
    @patch('src.core.world_generation.questline_crud', new_callable=MagicMock)
    @patch('src.core.world_generation.log_event', new_callable=AsyncMock)
    async def test_generate_quests_for_guild_success(
        self, mock_log_event, mock_ql_crud, mock_qs_crud, mock_gq_crud,
        mock_parse_validate, mock_ai_call, mock_prepare_prompt
    ):
        from src.core.world_generation import generate_quests_for_guild # SUT
        from src.models.quest import GeneratedQuest, QuestStep, Questline # DB Models
        from src.core.ai_response_parser import ParsedQuestData, ParsedQuestStepData # Pydantic Parsers

        guild_id_test = self.test_guild_id
        self.session_commit_mock.reset_mock()
        self.session_rollback_mock.reset_mock()

        mock_prepare_prompt.return_value = "Test quest prompt"
        ai_response_quests_json_str = json.dumps([
            {
                "entity_type": "quest", "static_id": "quest_alpha",
                "title_i18n": {"en": "Alpha Quest"}, "summary_i18n": {"en": "First one."},
                "steps": [
                    {"title_i18n": {"en": "Alpha Step 1"}, "description_i18n": {"en": "Do alpha."}, "step_order": 0, "required_mechanics_json": {"type":"explore"}}
                ], "questline_static_id": "main_plot"
            }
        ])
        mock_ai_call.return_value = ai_response_quests_json_str

        parsed_quest_alpha_step1 = ParsedQuestStepData(title_i18n={"en": "Alpha Step 1"}, description_i18n={"en": "Do alpha."}, step_order=0, required_mechanics_json={"type":"explore"})
        parsed_quest_alpha = ParsedQuestData(
            entity_type="quest", static_id="quest_alpha",
            title_i18n={"en": "Alpha Quest"}, summary_i18n={"en": "First one."},
            steps=[parsed_quest_alpha_step1], questline_static_id="main_plot"
        )
        mock_parse_validate.return_value = ParsedAiData(
            generated_entities=[parsed_quest_alpha], raw_ai_output=ai_response_quests_json_str
        )

        # Ensure mocked CRUD methods are AsyncMock if they are awaited
        mock_gq_crud.get_by_static_id = AsyncMock(return_value=None) # Quest does not exist

        # Mock Questline CRUD
        mock_existing_questline = Questline(id=5, guild_id=guild_id_test, static_id="main_plot", name_i18n={"en":"Main Plot"})
        mock_ql_crud.get_by_static_id = AsyncMock(return_value=mock_existing_questline) # Questline exists

        mock_db_quest_alpha = GeneratedQuest(id=301, guild_id=guild_id_test, static_id="quest_alpha", title_i18n={"en": "Alpha Quest"}, questline_id=5)
        # We need to mock the 'steps' attribute for the refresh call and logging
        mock_db_quest_alpha.steps = [QuestStep(id=401, quest_id=301, title_i18n={"en": "Alpha Step 1"}, step_order=0)]

        mock_gq_crud.create = AsyncMock(return_value=mock_db_quest_alpha)
        mock_qs_crud.create = AsyncMock(return_value=MagicMock(spec=QuestStep)) # Step creation mock

        # Mock session.refresh to avoid "not persistent" error with mock_db_quest_alpha
        self.session.refresh = AsyncMock()

        created_quests_list, error_msg = await generate_quests_for_guild(self.session, guild_id_test)

        self.assertIsNone(error_msg)
        self.assertIsNotNone(created_quests_list)
        self.assertEqual(len(created_quests_list), 1)
        if created_quests_list: # Guard for Pyright
            self.assertEqual(created_quests_list[0].static_id, "quest_alpha")
            self.assertEqual(created_quests_list[0].questline_id, 5) # Check linked to questline

        mock_gq_crud.create.assert_called_once()
        mock_qs_crud.create.assert_called_once() # One step
        mock_ql_crud.get_by_static_id.assert_called_once_with(self.session, guild_id=guild_id_test, static_id="main_plot")

        mock_log_event.assert_called_once()
        log_args = mock_log_event.call_args.kwargs
        self.assertEqual(log_args['event_type'], EventType.WORLD_EVENT_QUESTS_GENERATED.value)
        self.assertEqual(log_args['details_json']['generated_quests_count'], 1)
        self.session_commit_mock.assert_called_once()

    @patch('src.core.world_generation.prepare_quest_generation_prompt', new_callable=AsyncMock)
    @patch('src.core.world_generation._mock_openai_api_call', new_callable=AsyncMock)
    @patch('src.core.world_generation.parse_and_validate_ai_response', new_callable=AsyncMock)
    async def test_generate_quests_for_guild_parse_error(
        self, mock_parse_validate, mock_ai_call, mock_prepare_prompt
    ):
        from src.core.world_generation import generate_quests_for_guild # SUT
        guild_id_test = self.test_guild_id
        self.session_commit_mock.reset_mock()
        self.session_rollback_mock.reset_mock()

        mock_prepare_prompt.return_value = "Test quest prompt for parse error"
        mock_ai_call.return_value = "This is not valid JSON"

        validation_error = CustomValidationError(error_type="JSONParsingError", message="Bad JSON")
        mock_parse_validate.return_value = validation_error

        created_quests_list, error_msg = await generate_quests_for_guild(self.session, guild_id_test)

        self.assertIsNone(created_quests_list)
        self.assertIsNotNone(error_msg)
        self.assertIn("AI response validation failed for quests: Bad JSON", error_msg)
        self.session_rollback_mock.assert_not_called() # Rollback is not called for early returns

    @patch('src.core.world_generation.prepare_quest_generation_prompt', new_callable=AsyncMock)
    @patch('src.core.world_generation._mock_openai_api_call', new_callable=AsyncMock)
    @patch('src.core.world_generation.parse_and_validate_ai_response', new_callable=AsyncMock)
    @patch('src.core.world_generation.generated_quest_crud', new_callable=MagicMock)
    @patch('src.core.world_generation.log_event', new_callable=AsyncMock)
    async def test_generate_quests_for_guild_skips_duplicate_quest_static_id(
        self, mock_log_event, mock_gq_crud,
        mock_parse_validate, mock_ai_call, mock_prepare_prompt
    ):
        from src.core.world_generation import generate_quests_for_guild # SUT
        from src.models.quest import GeneratedQuest
        from src.core.ai_response_parser import ParsedQuestData, ParsedQuestStepData

        guild_id_test = self.test_guild_id
        self.session_commit_mock.reset_mock()

        mock_prepare_prompt.return_value = "Prompt for duplicate quest static_id test"
        ai_response_json_str = json.dumps([
            {
                "entity_type": "quest", "static_id": "existing_quest_007",
                "title_i18n": {"en": "Existing Quest"}, "summary_i18n": {"en": "This one exists."},
                "steps": [{"title_i18n": {"en": "Step Ex"}, "description_i18n": {"en": "Do Ex."}, "step_order": 0}]
            }
        ])
        mock_ai_call.return_value = ai_response_json_str

        parsed_quest_existing = ParsedQuestData(
            entity_type="quest", static_id="existing_quest_007",
            title_i18n={"en": "Existing Quest"}, summary_i18n={"en": "This one exists."},
            steps=[ParsedQuestStepData(title_i18n={"en": "Step Ex"}, description_i18n={"en": "Do Ex."}, step_order=0)]
        )
        mock_parse_validate.return_value = ParsedAiData(
            generated_entities=[parsed_quest_existing], raw_ai_output=ai_response_json_str
        )

        # Mock get_by_static_id to return an existing quest
        db_mock_existing_quest = GeneratedQuest(id=707, guild_id=guild_id_test, static_id="existing_quest_007", title_i18n={"en":"DB Version"})
        mock_gq_crud.get_by_static_id = AsyncMock(return_value=db_mock_existing_quest) # Make it AsyncMock
        mock_gq_crud.create = AsyncMock() # Ensure create is a mock

        created_quests_list, error_msg = await generate_quests_for_guild(self.session, guild_id_test)

        self.assertIsNone(error_msg)
        self.assertIsNotNone(created_quests_list)
        self.assertEqual(len(created_quests_list), 1)
        if created_quests_list: # Guard for Pyright
            self.assertEqual(created_quests_list[0].id, 707) # Should be the existing DB object

        mock_gq_crud.create.assert_not_called() # Create should not be called
        mock_log_event.assert_called_once() # Log event should still be called
        self.session_commit_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()


class TestWorldGenerationEconomicEntities(unittest.IsolatedAsyncioTestCase):
    engine: Optional[AsyncEngine] = None
    SessionLocal: Optional[async_sessionmaker[AsyncSession]] = None
    test_guild_id = 401
    default_lang = "en"

    @classmethod
    def setUpClass(cls):
        cls.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        cls.SessionLocal = async_sessionmaker(
            bind=cls.engine, class_=AsyncSession, expire_on_commit=False
        )

    @classmethod
    def tearDownClass(cls):
        if cls.engine:
            import asyncio
            asyncio.run(cls.engine.dispose())

    async def asyncSetUp(self):
        assert self.SessionLocal is not None
        self.session: AsyncSession = self.SessionLocal()
        self.session_commit_mock = AsyncMock()
        self.session_rollback_mock = AsyncMock()
        self.session.commit = self.session_commit_mock # type: ignore
        self.session.rollback = self.session_rollback_mock # type: ignore

        assert self.engine is not None
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        guild = await self.session.get(GuildConfig, self.test_guild_id)
        if not guild:
            self.session.add(GuildConfig(id=self.test_guild_id, main_language=self.default_lang, name=f"Guild {self.test_guild_id}"))
            await self.session.commit() # Commit this setup data
        self.session_commit_mock.reset_mock()


    async def asyncTearDown(self):
        if hasattr(self, 'session') and self.session:
            await self.session.rollback()
            await self.session.close()

    @patch('src.core.world_generation.prepare_economic_entity_generation_prompt', new_callable=AsyncMock)
    @patch('src.core.world_generation._mock_openai_api_call', new_callable=AsyncMock)
    @patch('src.core.world_generation.parse_and_validate_ai_response', new_callable=AsyncMock)
    @patch('src.core.world_generation.item_crud', new_callable=MagicMock)
    @patch('src.core.world_generation.npc_crud', new_callable=MagicMock)
    @patch('src.core.world_generation.inventory_item_crud', new_callable=MagicMock)
    @patch('src.core.world_generation.log_event', new_callable=AsyncMock)
    async def test_generate_economic_entities_success(
        self, mock_log_event, mock_inv_item_crud, mock_npc_crud, mock_item_crud,
        mock_parse_validate, mock_ai_call, mock_prepare_prompt
    ):
        from src.core.world_generation import generate_economic_entities # SUT
        from src.core.ai_response_parser import ParsedItemData, ParsedNpcTraderData, GeneratedInventoryItemEntry
        from src.models import Item, GeneratedNpc

        guild_id = self.test_guild_id
        mock_prepare_prompt.return_value = "economic_entities_prompt"

        # Mock AI response structure
        ai_response_json_str = json.dumps([
            {
                "entity_type": "item", "static_id": "test_sword",
                "name_i18n": {"en": "Test Sword"}, "description_i18n": {"en": "A sword for testing."},
                "item_type": "weapon", "base_value": 50
            },
            {
                "entity_type": "npc_trader", "static_id": "test_smith",
                "name_i18n": {"en": "Test Smith"}, "description_i18n": {"en": "A smith for testing."},
                "role_i18n": {"en": "Blacksmith"},
                "generated_inventory_items": [
                    {"item_static_id": "test_sword", "quantity_min": 1, "quantity_max": 1, "chance_to_appear": 1.0}
                ]
            }
        ])
        mock_ai_call.return_value = ai_response_json_str

        # Mock parsed data
        parsed_item = ParsedItemData(entity_type="item", static_id="test_sword", name_i18n={"en":"Test Sword"}, description_i18n={"en":"Desc"}, item_type="weapon", base_value=50)
        parsed_trader = ParsedNpcTraderData(
            entity_type="npc_trader", static_id="test_smith", name_i18n={"en":"Test Smith"}, description_i18n={"en":"Desc"}, role_i18n={"en":"Blacksmith"},
            generated_inventory_items=[GeneratedInventoryItemEntry(item_static_id="test_sword", quantity_min=1, quantity_max=1, chance_to_appear=1.0)]
        )
        mock_parse_validate.return_value = ParsedAiData(generated_entities=[parsed_item, parsed_trader], raw_ai_output=ai_response_json_str)

        # Mock CRUD operations
        mock_item_crud.get_by_static_id = AsyncMock(return_value=None)
        mock_item_db = Item(id=1, guild_id=guild_id, static_id="test_sword", name_i18n={"en":"Test Sword"})
        mock_item_crud.create = AsyncMock(return_value=mock_item_db)

        mock_npc_crud.get_by_static_id = AsyncMock(return_value=None)
        mock_npc_db = GeneratedNpc(id=10, guild_id=guild_id, static_id="test_smith", name_i18n={"en":"Test Smith"})
        mock_npc_crud.create = AsyncMock(return_value=mock_npc_db)

        mock_inv_item_crud.add_item_to_owner = AsyncMock()

        items, traders, error = await generate_economic_entities(self.session, guild_id)

        self.assertIsNone(error)
        self.assertIsNotNone(items)
        self.assertIsNotNone(traders)
        if items: self.assertEqual(len(items), 1)
        if traders: self.assertEqual(len(traders), 1)

        mock_item_crud.create.assert_called_once()
        mock_npc_crud.create.assert_called_once()
        mock_inv_item_crud.add_item_to_owner.assert_called_once()

        # Check inventory item call details
        call_args = mock_inv_item_crud.add_item_to_owner.call_args.kwargs
        self.assertEqual(call_args['guild_id'], guild_id)
        self.assertEqual(call_args['owner_entity_id'], mock_npc_db.id)
        self.assertEqual(call_args['item_id'], mock_item_db.id)
        self.assertEqual(call_args['quantity'], 1) # Since min=1, max=1

        mock_log_event.assert_called_once()
        log_details = mock_log_event.call_args.kwargs['details_json']
        self.assertEqual(log_details['generated_items_count'], 1)
        self.assertEqual(log_details['generated_traders_count'], 1)

        self.session_commit_mock.assert_called_once()

    @patch('src.core.world_generation.prepare_economic_entity_generation_prompt', new_callable=AsyncMock)
    @patch('src.core.world_generation.parse_and_validate_ai_response', new_callable=AsyncMock)
    async def test_generate_economic_entities_ai_parse_error(
        self, mock_parse_validate, mock_prepare_prompt
    ):
        from src.core.world_generation import generate_economic_entities # SUT
        guild_id = self.test_guild_id
        mock_prepare_prompt.return_value = "prompt_for_parse_error"

        validation_error = CustomValidationError(error_type="TestParseError", message="AI response parsing failed badly.")
        mock_parse_validate.return_value = validation_error

        items, traders, error_msg = await generate_economic_entities(self.session, guild_id)

        self.assertIsNone(items)
        self.assertIsNone(traders)
        self.assertIsNotNone(error_msg)
        if error_msg: self.assertIn("AI response parsing failed badly.", error_msg)
        self.session_rollback_mock.assert_not_called() # Error returned before DB ops
        self.session_commit_mock.assert_not_called()

    @patch('src.core.world_generation.prepare_economic_entity_generation_prompt', new_callable=AsyncMock)
    @patch('src.core.world_generation._mock_openai_api_call', new_callable=AsyncMock)
    @patch('src.core.world_generation.parse_and_validate_ai_response', new_callable=AsyncMock)
    @patch('src.core.world_generation.item_crud', new_callable=MagicMock)
    @patch('src.core.world_generation.npc_crud', new_callable=MagicMock)
    @patch('src.core.world_generation.inventory_item_crud', new_callable=MagicMock)
    @patch('src.core.world_generation.log_event', new_callable=AsyncMock)
    async def test_generate_economic_entities_handles_existing_item_and_npc(
        self, mock_log_event, mock_inv_item_crud, mock_npc_crud, mock_item_crud,
        mock_parse_validate, mock_ai_call, mock_prepare_prompt
    ):
        from src.core.world_generation import generate_economic_entities
        from src.core.ai_response_parser import ParsedItemData, ParsedNpcTraderData
        from src.models import Item, GeneratedNpc

        guild_id = self.test_guild_id
        mock_prepare_prompt.return_value = "prompt_existing"
        ai_response_json_str = json.dumps([
            {"entity_type": "item", "static_id": "existing_item", "name_i18n": {"en": "Existing Item"}, "description_i18n": {"en":"Desc"}, "item_type": "misc"},
            {"entity_type": "npc_trader", "static_id": "existing_trader", "name_i18n": {"en": "Existing Trader"}, "description_i18n": {"en":"Desc"}, "role_i18n": {"en": "Vendor"}}
        ])
        mock_ai_call.return_value = ai_response_json_str

        parsed_item_exist = ParsedItemData(entity_type="item", static_id="existing_item", name_i18n={"en":"Existing Item"}, description_i18n={"en":"Desc"}, item_type="misc")
        parsed_trader_exist = ParsedNpcTraderData(entity_type="npc_trader", static_id="existing_trader", name_i18n={"en":"Existing Trader"}, description_i18n={"en":"Desc"}, role_i18n={"en":"Vendor"})
        mock_parse_validate.return_value = ParsedAiData(generated_entities=[parsed_item_exist, parsed_trader_exist], raw_ai_output=ai_response_json_str)

        mock_existing_item_db = Item(id=2, guild_id=guild_id, static_id="existing_item", name_i18n={"en":"DB Item"})
        mock_item_crud.get_by_static_id.return_value = mock_existing_item_db
        mock_item_crud.create = AsyncMock() # Should not be called for this item

        mock_existing_npc_db = GeneratedNpc(id=20, guild_id=guild_id, static_id="existing_trader", name_i18n={"en":"DB Trader"})
        mock_npc_crud.get_by_static_id.return_value = mock_existing_npc_db
        mock_npc_crud.create = AsyncMock() # Should not be called for this NPC

        items, traders, error = await generate_economic_entities(self.session, guild_id)

        self.assertIsNone(error)
        self.assertIsNotNone(items)
        if items: self.assertEqual(len(items), 1); self.assertEqual(items[0].id, 2)
        self.assertIsNotNone(traders)
        if traders: self.assertEqual(len(traders), 1); self.assertEqual(traders[0].id, 20)

        mock_item_crud.create.assert_not_called()
        mock_npc_crud.create.assert_not_called()
        mock_inv_item_crud.add_item_to_owner.assert_not_called() # No inventory items specified for existing trader in this test
        self.session_commit_mock.assert_called_once()
