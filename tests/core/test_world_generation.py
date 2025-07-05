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

    # New tests for generate_factions_and_relationships will be added here...

    @patch('src.core.world_generation.prepare_faction_relationship_generation_prompt', new_callable=AsyncMock)
    @patch('src.core.world_generation._mock_openai_api_call', new_callable=AsyncMock) # Assuming this is still the AI call mechanism used
    @patch('src.core.world_generation.parse_and_validate_ai_response', new_callable=AsyncMock)
    @patch('src.core.world_generation.log_event', new_callable=AsyncMock)
    @patch('src.core.world_generation.crud_faction', new_callable=MagicMock) # Patching the imported crud object
    @patch('src.core.world_generation.crud_relationship', new_callable=MagicMock)
    async def test_generate_factions_and_relationships_success(
        self, mock_crud_relationship, mock_crud_faction, mock_log_event,
        mock_parse_validate, mock_ai_call, mock_prepare_prompt
    ):
        guild_id = self.test_guild_id
        self.session_commit_mock.reset_mock() # type: ignore
        self.session_rollback_mock.reset_mock() # type: ignore

        # 1. Setup Mocks
        mock_prepare_prompt.return_value = "faction_rel_prompt"

        # AI response mock - this needs to be a string that parse_and_validate_ai_response can handle
        # The actual function generate_factions_and_relationships constructs a flat list
        # from a structured dict before calling parse_and_validate_ai_response.
        # So, _mock_openai_api_call should return the structured dict.
        # generate_factions_and_relationships then processes this into a flat list string for parse_and_validate.

        # This is what _mock_openai_api_call should return (the structured dict as a string)
        # However, generate_factions_and_relationships internally calls json.loads on this,
        # then extracts lists and re-dumps. So the mock for _mock_openai_api_call should return
        # the string representation of the structured dict.
        # Let's simplify: the important mock is parse_and_validate_ai_response.
        # The _mock_openai_api_call in generate_factions_and_relationships is currently:
        # raw_parsed_json = json.loads(mock_ai_response_str)
        # parsed_faction_list_json = raw_parsed_json.get("generated_factions", [])
        # ...
        # all_parsed_entities_json = parsed_faction_list_json + parsed_relationship_list_json
        # parsed_data_or_error = await parse_and_validate_ai_response(json.dumps(all_parsed_entities_json), ...)
        # So, we need to ensure that mock_parse_validate receives the flat list.
        # The direct output of _mock_openai_api_call is less critical if parse_and_validate is properly mocked.

        # For simplicity, we'll mock the output of parse_and_validate_ai_response directly.
        parsed_faction1_data = ParsedFactionData(
            entity_type="faction", static_id="fac1_sid", name_i18n={"en": "Faction One"}, description_i18n={"en":"Desc1"}
        )
        parsed_faction2_data = ParsedFactionData(
            entity_type="faction", static_id="fac2_sid", name_i18n={"en": "Faction Two"}, description_i18n={"en":"Desc2"}
        )
        parsed_relationship_data = ParsedRelationshipData(
            entity_type="relationship", entity1_static_id="fac1_sid", entity1_type="generated_faction",
            entity2_static_id="fac2_sid", entity2_type="generated_faction",
            relationship_type="alliance", value=75
        )
        mock_parsed_ai_data_success = ParsedAiData(
            generated_entities=[parsed_faction1_data, parsed_faction2_data, parsed_relationship_data],
            raw_ai_output="dummy_raw_output_for_factions", # This is raw_ai_output_text for parse_and_validate
            parsing_metadata={}
        )
        mock_parse_validate.return_value = mock_parsed_ai_data_success

        # Mock CRUD operations
        created_faction1_db = GeneratedFaction(id=1, guild_id=guild_id, static_id="fac1_sid", name_i18n={"en": "Faction One DB"}, description_i18n={})
        created_faction2_db = GeneratedFaction(id=2, guild_id=guild_id, static_id="fac2_sid", name_i18n={"en": "Faction Two DB"}, description_i18n={})

        # crud_faction.create will be called. Need to set side_effect if called multiple times.
        mock_crud_faction_instance = mock_crud_faction # This is the MagicMock object for the module
        mock_crud_faction_instance.create = AsyncMock(side_effect=[created_faction1_db, created_faction2_db])
        mock_crud_faction_instance.get_by_static_id = AsyncMock(return_value=None) # No existing factions by these static_ids

        created_relationship_db = Relationship(
            id=10, guild_id=guild_id, entity1_id=1, entity1_type=RelationshipEntityType.GENERATED_FACTION,
            entity2_id=2, entity2_type=RelationshipEntityType.GENERATED_FACTION,
            relationship_type="alliance", value=75
        )
        mock_crud_relationship_instance = mock_crud_relationship
        mock_crud_relationship_instance.create = AsyncMock(return_value=created_relationship_db)
        mock_crud_relationship_instance.get_relationship_between_entities = AsyncMock(return_value=None) # No existing relationship

        # 2. Call the function
        factions, relationships, error = await generate_factions_and_relationships(self.session, guild_id)

        # 3. Assertions
        self.assertIsNone(error)
        self.assertIsNotNone(factions)
        self.assertIsNotNone(relationships)
        if factions: # Guard for Pyright
            self.assertEqual(len(factions), 2)
        if relationships: # Guard for Pyright
            self.assertEqual(len(relationships), 1)

        # Check faction creation calls and data
        self.assertEqual(mock_crud_faction_instance.create.call_count, 2)

        # Call 1 for faction 1
        call_args_f1 = mock_crud_faction_instance.create.call_args_list[0][1]['obj_in'] # obj_in is a kwarg
        self.assertEqual(call_args_f1['static_id'], "fac1_sid")
        self.assertEqual(call_args_f1['name_i18n']['en'], "Faction One")
        self.assertEqual(call_args_f1['guild_id'], guild_id)

        # Call 2 for faction 2
        call_args_f2 = mock_crud_faction_instance.create.call_args_list[1][1]['obj_in']
        self.assertEqual(call_args_f2['static_id'], "fac2_sid")
        self.assertEqual(call_args_f2['name_i18n']['en'], "Faction Two")

        # Check relationship creation
        mock_crud_relationship_instance.create.assert_called_once() # type: ignore
        call_args_rel = mock_crud_relationship_instance.create.call_args[1]['obj_in']
        self.assertEqual(call_args_rel['guild_id'], guild_id)
        self.assertEqual(call_args_rel['entity1_id'], created_faction1_db.id) # Check correct DB ID mapping
        self.assertEqual(call_args_rel['entity1_type'], RelationshipEntityType.GENERATED_FACTION)
        self.assertEqual(call_args_rel['entity2_id'], created_faction2_db.id) # Check correct DB ID mapping
        self.assertEqual(call_args_rel['entity2_type'], RelationshipEntityType.GENERATED_FACTION)
        self.assertEqual(call_args_rel['relationship_type'], "alliance")
        self.assertEqual(call_args_rel['value'], 75)

        # Check log_event call
        mock_log_event.assert_called_once() # type: ignore
        log_args = mock_log_event.call_args.kwargs
        self.assertEqual(log_args['guild_id'], guild_id)
        self.assertEqual(log_args['event_type'], EventType.WORLD_EVENT_FACTIONS_GENERATED.value)
        self.assertEqual(log_args['details_json']['generated_factions_count'], 2)
        self.assertEqual(log_args['details_json']['generated_relationships_count'], 1)
        self.assertIn(created_faction1_db.id, log_args['details_json']['faction_ids']) # This should be fine if faction_ids is a list
        self.assertIn(created_faction2_db.id, log_args['details_json']['faction_ids']) # And this too

        self.session_commit_mock.assert_called_once() # type: ignore

    @patch('src.core.world_generation.prepare_faction_relationship_generation_prompt', new_callable=AsyncMock)
    @patch('src.core.world_generation._mock_openai_api_call', new_callable=AsyncMock)
    @patch('src.core.world_generation.parse_and_validate_ai_response', new_callable=AsyncMock)
    @patch('src.core.world_generation.log_event', new_callable=AsyncMock)
    @patch('src.core.world_generation.crud_faction', new_callable=MagicMock)
    @patch('src.core.world_generation.crud_relationship', new_callable=MagicMock)
    async def test_generate_factions_and_relationships_parsing_error(
        self, mock_crud_relationship, mock_crud_faction, mock_log_event,
        mock_parse_validate, mock_ai_call, mock_prepare_prompt
    ):
        guild_id = self.test_guild_id
        self.session_commit_mock.reset_mock() # type: ignore
        self.session_rollback_mock.reset_mock() # type: ignore

        # 1. Setup Mocks
        mock_prepare_prompt.return_value = "faction_rel_prompt"
        # _mock_openai_api_call returns a string which is then processed.
        # The actual error will occur in parse_and_validate_ai_response.
        # We make parse_and_validate_ai_response return a CustomValidationError.
        mock_ai_call.return_value = json.dumps({ # This content doesn't really matter as parse_and_validate is mocked next
            "generated_factions": [{"entity_type": "faction", "static_id": "bad_data"}],
            "generated_relationships": []
        })

        validation_error = CustomValidationError(
            error_type="JSONParsingError", # Or any other error type like StructuralValidationError
            message="Simulated parsing error"
        )
        mock_parse_validate.return_value = validation_error

        # 2. Call the function
        factions, relationships, error_message = await generate_factions_and_relationships(self.session, guild_id)

        # 3. Assertions
        self.assertIsNone(factions)
        self.assertIsNone(relationships)
        self.assertIsNotNone(error_message)
        if error_message: # Type guard for Pyright
            self.assertIn("Simulated parsing error", error_message)

        # Ensure no CRUD operations were attempted
        mock_crud_faction.create.assert_not_called()
        mock_crud_relationship.create.assert_not_called()

        # Ensure log_event for success was not called
        mock_log_event.assert_not_called()

        # Rollback is not called if error is returned before exception block in generate_factions_and_relationships
        # self.session.rollback.assert_called_once()

    @patch('src.core.world_generation.prepare_faction_relationship_generation_prompt', new_callable=AsyncMock)
    @patch('src.core.world_generation._mock_openai_api_call', new_callable=AsyncMock)
    @patch('src.core.world_generation.parse_and_validate_ai_response', new_callable=AsyncMock)
    @patch('src.core.world_generation.log_event', new_callable=AsyncMock)
    @patch('src.core.world_generation.crud_faction', new_callable=MagicMock)
    @patch('src.core.world_generation.crud_relationship', new_callable=MagicMock)
    async def test_generate_factions_and_relationships_existing_static_id(
        self, mock_crud_relationship, mock_crud_faction, mock_log_event,
        mock_parse_validate, mock_ai_call, mock_prepare_prompt
    ):
        guild_id = self.test_guild_id
        self.session_commit_mock.reset_mock() # type: ignore
        self.session_rollback_mock.reset_mock() # type: ignore
        existing_static_id = "existing_fac_sid"

        # 1. Setup: Mock an existing faction in DB
        existing_faction_db = GeneratedFaction(id=50, guild_id=guild_id, static_id=existing_static_id, name_i18n={"en": "Original Faction"}, description_i18n={})

        mock_crud_faction_instance = mock_crud_faction
        # When get_by_static_id is called for existing_static_id, return the existing_faction_db
        # For any other static_id, return None (new faction)
        async def mock_get_by_static_id_side_effect(session, guild_id, static_id):
            if static_id == existing_static_id:
                return existing_faction_db
            return None
        mock_crud_faction_instance.get_by_static_id = AsyncMock(side_effect=mock_get_by_static_id_side_effect)

        # New faction to be created by AI
        new_faction_static_id = "new_fac_sid"
        new_faction_db = GeneratedFaction(id=51, guild_id=guild_id, static_id=new_faction_static_id, name_i18n={"en": "New Faction DB"}, description_i18n={})

        # crud_faction.create will only be called for the new faction
        mock_crud_faction_instance.create = AsyncMock(return_value=new_faction_db)

        # 2. Setup Mocks for AI response
        mock_prepare_prompt.return_value = "faction_rel_prompt_existing_sid"

        # AI response tries to create the existing faction again, and a new one
        parsed_faction_existing_data = ParsedFactionData(
            entity_type="faction", static_id=existing_static_id, name_i18n={"en": "Faction Existing (AI)"}, description_i18n={"en":"Desc Existing"}
        )
        parsed_faction_new_data = ParsedFactionData(
            entity_type="faction", static_id=new_faction_static_id, name_i18n={"en": "New Faction (AI)"}, description_i18n={"en":"Desc New"}
        )
        # Relationship between the "existing" (from AI's perspective) and the new one
        parsed_relationship_data = ParsedRelationshipData(
            entity_type="relationship", entity1_static_id=existing_static_id, entity1_type="generated_faction",
            entity2_static_id=new_faction_static_id, entity2_type="generated_faction",
            relationship_type="neutral_standing", value=0
        )
        mock_parsed_ai_data = ParsedAiData(
            generated_entities=[parsed_faction_existing_data, parsed_faction_new_data, parsed_relationship_data],
            raw_ai_output="dummy_raw_for_existing_sid",
            parsing_metadata={}
        )
        mock_parse_validate.return_value = mock_parsed_ai_data

        # Mock relationship CRUD
        created_relationship_db = Relationship(
            id=20, guild_id=guild_id, entity1_id=existing_faction_db.id, entity1_type=RelationshipEntityType.GENERATED_FACTION, # Should use existing ID
            entity2_id=new_faction_db.id, entity2_type=RelationshipEntityType.GENERATED_FACTION, # Should use new ID
            relationship_type="neutral_standing", value=0
        )
        mock_crud_relationship_instance = mock_crud_relationship
        mock_crud_relationship_instance.create = AsyncMock(return_value=created_relationship_db)
        mock_crud_relationship_instance.get_relationship_between_entities = AsyncMock(return_value=None)

        # 3. Call the function
        factions, relationships, error = await generate_factions_and_relationships(self.session, guild_id)

        # 4. Assertions
        self.assertIsNone(error)
        self.assertIsNotNone(factions)
        self.assertIsNotNone(relationships)

        # Should include the existing faction (returned by get_by_static_id) and the new one
        if factions: # Guard for Pyright
            self.assertEqual(len(factions), 2)
            faction_ids_returned = {f.id for f in factions} # f should be GeneratedFaction here
            self.assertIn(existing_faction_db.id, faction_ids_returned)
            self.assertIn(new_faction_db.id, faction_ids_returned)

        if relationships: # Guard for Pyright
            self.assertEqual(len(relationships), 1)

        # crud_faction.create should only be called ONCE (for the new faction)
        mock_crud_faction_instance.create.assert_called_once()
        call_args_new_fac = mock_crud_faction_instance.create.call_args[1]['obj_in']
        self.assertEqual(call_args_new_fac['static_id'], new_faction_static_id)
        self.assertEqual(call_args_new_fac['name_i18n']['en'], "New Faction (AI)")

        # Check relationship creation - should use correct DB IDs
        mock_crud_relationship_instance.create.assert_called_once()
        call_args_rel = mock_crud_relationship_instance.create.call_args[1]['obj_in']
        self.assertEqual(call_args_rel['entity1_id'], existing_faction_db.id) # Points to the original DB faction
        self.assertEqual(call_args_rel['entity2_id'], new_faction_db.id)
        self.assertEqual(call_args_rel['relationship_type'], "neutral_standing")

        mock_log_event.assert_called_once() # type: ignore
        self.session_commit_mock.assert_called_once() # type: ignore


if __name__ == "__main__":
    unittest.main() # Changed from pytest execution
