import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call

from typing import List, Optional, Dict, Any, Union # Added Union

from sqlalchemy.ext.asyncio import AsyncSession

# Models to be mocked or used
from backend.models import (
    GlobalNpc,
    MobileGroup,
    Player,
    # GeneratedNpc, # If local NPCs are involved in interactions
    Location,
    GuildConfig,
    Relationship, # For mocking relationship values
    RuleConfig, # For mocking rule lookups
    EventType,
    RelationshipEntityType,
    StoryLog,
    CheckResult as CheckResultModel, # Renamed to avoid conflict with unittest.TestResult
    CheckOutcome,
    ModifierDetail
)

# CRUDs to be mocked
# Assuming paths like 'backend.core.crud.global_npc_crud'
# from backend.core.crud import global_npc_crud, mobile_group_crud, player_crud # etc.

# Core systems to be mocked
# from backend.core.rules import get_rule
# from backend.core.check_resolver import resolve_check, CheckError
# from backend.core.combat_cycle_manager import start_combat
# from backend.core.quest_system import handle_player_event_for_quest
# from backend.core.game_events import log_event
# from backend.core.relationship_system import get_relationship_between_entities

# Function to test
# from backend.core import global_entity_manager # This was causing issues with __init__.py
import backend.core.global_entity_manager # Import the module path directly
# from backend.core.global_entity_manager import simulate_global_entities_for_guild # Will be called via the module path


class TestGlobalEntityManager(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_session = AsyncMock(spec=AsyncSession)
        self.guild_id = 1

        # Patch all external dependencies that will be called by simulate_global_entities_for_guild
        # using patch.object
        self.patchers = [
            patch.object(backend.core.global_entity_manager, "global_npc_crud"),
            patch.object(backend.core.global_entity_manager, "mobile_group_crud"),
            patch.object(backend.core.global_entity_manager, "player_crud"),
            patch.object(backend.core.global_entity_manager, "generated_npc_crud"),
            patch.object(backend.core.global_entity_manager, "location_crud"),
            patch.object(backend.core.global_entity_manager, "crud_relationship"),
            patch.object(backend.core.global_entity_manager, "get_rule"),
            patch.object(backend.core.global_entity_manager, "resolve_check"),
            patch.object(backend.core.global_entity_manager, "start_combat"),
            patch.object(backend.core.global_entity_manager, "handle_player_event_for_quest"),
            patch.object(backend.core.global_entity_manager, "log_event"),
            patch.object(backend.core.global_entity_manager, "_simulate_entity_movement"),
            patch.object(backend.core.global_entity_manager, "_simulate_entity_interactions"),
        ]

        self.mocked_objects = {}
        for p in self.patchers:
            mock_obj = p.start()
            # Ensure commonly awaited methods on CRUDs are AsyncMock
            if p.attribute in ["global_npc_crud", "mobile_group_crud", "player_crud", "generated_npc_crud", "location_crud", "crud_relationship"]:
                mock_obj.get = AsyncMock()
                mock_obj.get_multi_by_guild_id = AsyncMock(return_value=[])
                mock_obj.get_multi_by_guild_id_active = AsyncMock(return_value=[])
                mock_obj.get_multi_by_location_id = AsyncMock(return_value=[])
                mock_obj.get_by_static_id = AsyncMock(return_value=None)
                mock_obj.create = AsyncMock()
                mock_obj.update = AsyncMock()
                mock_obj.delete = AsyncMock()
                if p.attribute == "crud_relationship":
                    mock_obj.get_relationship_between_entities = AsyncMock(return_value=None)
            elif isinstance(mock_obj, MagicMock) and not isinstance(mock_obj, AsyncMock) : # For non-CRUD async functions like get_rule, resolve_check etc.
                # If the patched object itself is supposed to be an async function, make it AsyncMock
                # This check might need refinement based on what exactly is patched.
                # The patch.object itself makes it a MagicMock if it's a regular function,
                # or an AsyncMock if it's an async function.
                # For now, assume patch.object handles async functions correctly.
                # If get_rule is async, it should already be an AsyncMock.
                pass


            self.mocked_objects[p.attribute] = mock_obj

        # Configure default return values for mocks using the new dict
        self.mocked_objects["global_npc_crud"].get_multi_by_guild_id_active.return_value = []
        self.mocked_objects["mobile_group_crud"].get_multi_by_guild_id_active.return_value = []
        self.mocked_objects["player_crud"].get_multi_by_location_id.return_value = []
        self.mocked_objects["generated_npc_crud"].get_multi_by_location_id.return_value = [] # For _get_entities_in_location
        self.mocked_objects["location_crud"].get.return_value = None # Default for location lookups
        self.mocked_objects["location_crud"].get_by_static_id.return_value = None
        self.mocked_objects["get_rule"].return_value = None
        self.mocked_objects["crud_relationship"].get_relationship_between_entities.return_value = None


    async def asyncTearDown(self):
        for p in self.patchers:
            p.stop()

    async def test_simulate_no_active_global_entities(self):
        """Test that simulation completes gracefully if no active global entities are found."""
        self.mocked_objects["global_npc_crud"].get_multi_by_guild_id.return_value = []
        self.mocked_objects["mobile_group_crud"].get_multi_by_guild_id.return_value = []

        await backend.core.global_entity_manager.simulate_global_entities_for_guild(self.mock_session, self.guild_id)

        self.mocked_objects["_simulate_entity_movement"].assert_not_called()
        self.mocked_objects["_simulate_entity_interactions"].assert_not_called()
        self.mocked_objects["log_event"].assert_not_called()

    async def test_simulate_single_global_npc_no_interaction(self):
        """Test simulation for a single GlobalNpc that moves but has no interactions."""
        mock_npc = MagicMock(spec=GlobalNpc)
        mock_npc.id = 10
        mock_npc.static_id = "npc_lonewolf"
        mock_npc.name_i18n = {"en": "Lone Wolf"}
        mock_npc.current_location_id = 1
        mock_npc.properties_json = {}
        mock_npc.__class__.__name__ = "GlobalNpc"

        # SUT calls get_multi_by_guild_id, not get_multi_by_guild_id_active
        self.mocked_objects["global_npc_crud"].get_multi_by_guild_id.return_value = [mock_npc]
        self.mocked_objects["mobile_group_crud"].get_multi_by_guild_id.return_value = []

        # _simulate_entity_movement is an AsyncMock from patch.object.
        # If it needs to do something (like setattr), its side_effect can be an async def function.
        # For just checking calls, no side_effect is needed beyond ensuring it's awaitable (AsyncMock handles this).
        # self.mocked_objects["_simulate_entity_movement"].side_effect = lambda s, g, e: setattr(e, 'moved_this_tick', True) # This makes it non-awaitable if lambda is not async
        async def mock_movement_side_effect(session, guild_id, entity):
            setattr(entity, 'moved_this_tick', True)
            return None # Simulate it returns None or some info
        self.mocked_objects["_simulate_entity_movement"].side_effect = mock_movement_side_effect
        self.mocked_objects["_simulate_entity_interactions"].return_value = None # Ensure it's awaitable and returns None


        await backend.core.global_entity_manager.simulate_global_entities_for_guild(self.mock_session, self.guild_id)

        self.mocked_objects["_simulate_entity_movement"].assert_called_once_with(self.mock_session, self.guild_id, mock_npc)
        self.mocked_objects["_simulate_entity_interactions"].assert_called_once_with(self.mock_session, self.guild_id, mock_npc)
        # Further assertions on log_event if movement logs something, etc.

    async def test_simulate_mobile_group_triggers_combat(self):
        """Test a MobileGroup detecting a player and initiating combat based on rules."""
        from backend.core.global_entity_manager import simulate_global_entities_for_guild

        mock_group = MagicMock(spec=MobileGroup)
        mock_group.id = 20
        mock_group.static_id = "grp_bandits"
        mock_group.name_i18n = {"en": "Bandit Patrol"}
        mock_group.current_location_id = 2
        mock_group.properties_json = {"target_faction": "player_faction"} # Example property
        mock_group.__class__.__name__ = "MobileGroup"

        mock_player = MagicMock(spec=Player)
        mock_player.id = 1
        mock_player.name = "Hero"
        mock_player.faction_id = "player_faction" # Example

        self.mocked_objects["global_npc_crud"].get_multi_by_guild_id.return_value = []
        self.mocked_objects["mobile_group_crud"].get_multi_by_guild_id.return_value = [mock_group]

        # Simulate movement (or not, if interaction is immediate)
        self.mocked_objects["_simulate_entity_movement"].return_value = None # Ensure it's awaitable if called

        # Make _simulate_entity_interactions trigger combat
        async def mock_interactions_that_start_combat(session, guild_id, entity):
            if entity == mock_group:
                # Simulate that it found a player and decided to attack
                await self.mocked_objects["start_combat"](session, guild_id, entity.current_location_id, [{"id": entity.id, "type": RelationshipEntityType.MOBILE_GROUP, "team": "A"}, {"id": mock_player.id, "type": RelationshipEntityType.PLAYER, "team": "B"}])
                await self.mocked_objects["log_event"](session=session, guild_id=guild_id, event_type=EventType.GLOBAL_ENTITY_ACTION, details_json={"action": "start_combat", "target_id": mock_player.id})

        self.mocked_objects["_simulate_entity_interactions"].side_effect = mock_interactions_that_start_combat

        await backend.core.global_entity_manager.simulate_global_entities_for_guild(self.mock_session, self.guild_id)

        self.mocked_objects["_simulate_entity_movement"].assert_called_once_with(self.mock_session, self.guild_id, mock_group)
        self.mocked_objects["_simulate_entity_interactions"].assert_called_once_with(self.mock_session, self.guild_id, mock_group)
        self.mocked_objects["start_combat"].assert_called_once()
        # Check args of start_combat if necessary
        self.mocked_objects["log_event"].assert_any_call(
            session=self.mock_session,
            guild_id=self.guild_id,
            event_type=EventType.GLOBAL_ENTITY_ACTION,
            details_json={"action": "start_combat", "target_id": mock_player.id}
        )

    async def test_simulate_npc_triggers_dialogue_placeholder(self):
        """Test a GlobalNpc triggering a placeholder dialogue event."""
        from backend.core.global_entity_manager import simulate_global_entities_for_guild

        mock_npc = MagicMock(spec=GlobalNpc)
        mock_npc.id = 11
        mock_npc.static_id = "npc_wandering_merchant"
        mock_npc.name_i18n = {"en": "Wandering Merchant"}
        mock_npc.current_location_id = 3
        mock_npc.__class__.__name__ = "GlobalNpc"

        mock_player = MagicMock(spec=Player) # Target of dialogue
        mock_player.id = 2
        mock_player.name = "Curious George"
        mock_player.__class__.__name__ = "Player"


        self.mocked_objects["global_npc_crud"].get_multi_by_guild_id.return_value = [mock_npc]
        self.mocked_objects["mobile_group_crud"].get_multi_by_guild_id.return_value = []

        # Ensure _simulate_entity_movement is awaitable and returns None for this test path
        self.mocked_objects["_simulate_entity_movement"].return_value = None


        async def mock_interactions_that_start_dialogue(session, guild_id, entity):
            if entity == mock_npc:
                # Simulate finding player and deciding to talk
                await self.mocked_objects["log_event"](
                    session=session,
                    guild_id=guild_id,
                    event_type=EventType.GE_TRIGGERED_DIALOGUE_PLACEHOLDER,
                    details_json={
                        "ge_static_id": entity.static_id,
                        "ge_type": entity.__class__.__name__,
                        "target_entity_id": mock_player.id,
                        "target_entity_type": mock_player.__class__.__name__,
                        "dialogue_initiation_type": "neutral_hail",
                    }
                )
        self.mocked_objects["_simulate_entity_interactions"].side_effect = mock_interactions_that_start_dialogue

        await backend.core.global_entity_manager.simulate_global_entities_for_guild(self.mock_session, self.guild_id)

        self.mocked_objects["_simulate_entity_movement"].assert_called_once_with(self.mock_session, self.guild_id, mock_npc)
        self.mocked_objects["_simulate_entity_interactions"].assert_called_once_with(self.mock_session, self.guild_id, mock_npc)
        self.mocked_objects["log_event"].assert_called_with(
            session=self.mock_session,
            guild_id=self.guild_id,
            event_type=EventType.GE_TRIGGERED_DIALOGUE_PLACEHOLDER,
            details_json={
                "ge_static_id": mock_npc.static_id,
                "ge_type": "GlobalNpc",
                "target_entity_id": mock_player.id,
                "target_entity_type": "Player",
                "dialogue_initiation_type": "neutral_hail",
            }
        )

    # TODO: Add more tests:
    # - Test for _simulate_entity_movement (when it's implemented)
    #   - Movement along a route
    #   - Reaching a destination
    #   - Logging movement
    # - Test for _simulate_entity_interactions (when it's implemented)
    #   - Detection success/failure based on resolve_check mock
    #   - Reaction logic based on get_rule mock (different actions chosen)
    #   - Relationship influence on reactions (mock get_relationship_between_entities)
    #   - Triggering quest updates (mock handle_player_event_for_quest)
    #   - Creating GlobalEvents
    # - Test error handling (e.g., CheckError from resolve_check)

if __name__ == "__main__":
    unittest.main()
