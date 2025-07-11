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
    GeneratedNpc, # If local NPCs are involved in interactions, uncommented
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


# --- Tests for _determine_next_location_id and _handle_goal_reached ---

class TestDetermineNextLocationAndGoalReached(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_session = AsyncMock(spec=AsyncSession)
        self.guild_id = 1
        self.entity_id = 1
        self.location_id_current = 10
        self.location_id_goal = 11
        self.location_id_next_goal = 12

        self.mock_entity = MagicMock(spec=GlobalNpc) # Can be GlobalNpc or MobileGroup
        self.mock_entity.id = self.entity_id
        self.mock_entity.static_id = "test_entity"
        self.mock_entity.current_location_id = self.location_id_current
        self.mock_entity.properties_json = {}
        self.mock_entity.name_i18n = {"en": "Test Entity"}
        self.mock_entity.__class__.__name__ = "GlobalNpc" # For logging/rules

        self.mock_goal_location = MagicMock(spec=Location)
        self.mock_goal_location.id = self.location_id_goal
        self.mock_goal_location.static_id = "goal_loc_static"

        self.mock_next_goal_location = MagicMock(spec=Location)
        self.mock_next_goal_location.id = self.location_id_next_goal
        self.mock_next_goal_location.static_id = "next_goal_loc_static"

        # Patch location_crud used by _determine_next_location_id and _handle_goal_reached
        self.patcher_location_crud = patch.object(backend.core.global_entity_manager, "location_crud")
        self.mock_location_crud = self.patcher_location_crud.start()
        # Ensure methods expected to be async are AsyncMock
        self.mock_location_crud.get_by_static_id = AsyncMock(return_value=self.mock_goal_location) # Default
        self.mock_location_crud.get = AsyncMock() # Also ensure .get is AsyncMock if used by SUT

    async def asyncTearDown(self):
        self.patcher_location_crud.stop()

    async def test_goal_reached_behavior_idle(self):
        self.mock_entity.current_location_id = self.location_id_goal # Entity is at the goal
        self.mock_entity.properties_json = {
            "goal_location_static_id": "goal_loc_static",
            "on_goal_reached_behavior": "idle"
        }
        # _determine_next_location_id calls _handle_goal_reached internally
        next_loc_id = await backend.core.global_entity_manager._determine_next_location_id(
            self.mock_session, self.guild_id, self.mock_entity
        )
        self.assertIsNone(next_loc_id) # Should not move immediately
        self.assertNotIn("goal_location_static_id", self.mock_entity.properties_json)
        # on_goal_reached_behavior might be removed or kept depending on exact logic,
        # for "idle", it might be kept or removed. Current code removes it if it was set_new_goal and failed.
        # For "idle", it's not explicitly removed.

    async def test_goal_reached_behavior_set_new_goal(self):
        self.mock_entity.current_location_id = self.location_id_goal
        self.mock_entity.properties_json = {
            "goal_location_static_id": "goal_loc_static",
            "on_goal_reached_behavior": "set_new_goal",
            "next_goal_static_id": "next_goal_loc_static",
            "after_next_goal_behavior": "idle_after_next"
        }

        # Mock get_by_static_id to return the next goal when asked
        async def get_loc_side_effect(session, guild_id, static_id):
            if static_id == "goal_loc_static": return self.mock_goal_location
            if static_id == "next_goal_loc_static": return self.mock_next_goal_location
            return None
        self.mock_location_crud.get_by_static_id.side_effect = get_loc_side_effect

        next_loc_id = await backend.core.global_entity_manager._determine_next_location_id(
            self.mock_session, self.guild_id, self.mock_entity
        )
        self.assertIsNone(next_loc_id) # _determine_next_location_id returns None after goal reached logic
        self.assertEqual(self.mock_entity.properties_json.get("goal_location_static_id"), "next_goal_loc_static")
        self.assertEqual(self.mock_entity.properties_json.get("on_goal_reached_behavior"), "idle_after_next")
        self.assertNotIn("next_goal_static_id", self.mock_entity.properties_json) # Consumed
        self.assertNotIn("after_next_goal_behavior", self.mock_entity.properties_json) # Consumed indirectly


    async def test_goal_reached_behavior_start_new_route(self):
        self.mock_entity.current_location_id = self.location_id_goal
        new_route_json = {"location_static_ids": ["route_loc_1", "route_loc_2"], "type": "sequential"}
        self.mock_entity.properties_json = {
            "goal_location_static_id": "goal_loc_static",
            "on_goal_reached_behavior": "start_new_route",
            "next_route_json": new_route_json
        }
        self.mock_location_crud.get_by_static_id.return_value = self.mock_goal_location

        next_loc_id = await backend.core.global_entity_manager._determine_next_location_id(
            self.mock_session, self.guild_id, self.mock_entity
        )
        self.assertIsNone(next_loc_id)
        self.assertEqual(self.mock_entity.properties_json.get("route_json"), new_route_json)
        self.assertEqual(self.mock_entity.properties_json.get("current_route_index"), 0)
        self.assertNotIn("goal_location_static_id", self.mock_entity.properties_json)
        self.assertNotIn("next_route_json", self.mock_entity.properties_json) # Consumed


if __name__ == "__main__":
    unittest.main()


# --- Tests for MobileGroup expansion in combat ---

class TestMobileGroupCombatExpansion(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_session = AsyncMock(spec=AsyncSession)
        self.guild_id = 1
        self.location_id = 50

        # Patches for dependencies of _simulate_entity_interactions and its callees
        self.patchers = [
            patch.object(backend.core.global_entity_manager, "get_rule"),
            patch.object(backend.core.global_entity_manager, "resolve_check"),
            patch.object(backend.core.global_entity_manager, "start_combat"),
            patch.object(backend.core.global_entity_manager, "log_event"),
            patch.object(backend.core.global_entity_manager, "crud_relationship"),
            patch.object(backend.core.global_entity_manager, "generated_npc_crud"),
            patch.object(backend.core.global_entity_manager, "_get_entities_in_location"), # Mock this helper too
            patch.object(backend.core.global_entity_manager, "_choose_reaction_action")
        ]
        self.mocked_objects = {}
        for p in self.patchers:
            mock_obj = p.start()
            # Ensure async functions are AsyncMock
            if asyncio.iscoroutinefunction(p.temp_original):
                 # If p.start() didn't already make it AsyncMock, re-patch with AsyncMock
                 # This is tricky; usually patch handles it. Let's assume it does for now.
                 # If issues arise, we might need to ensure they are AsyncMock.
                 pass
            self.mocked_objects[p.attribute] = mock_obj

        # Default behaviors
        self.mocked_objects["get_rule"].return_value = {"enabled": True, "check_type": "perception", "base_dc": 0} # Auto-detect
        self.mock_resolve_check_result = MagicMock(spec=CheckResultModel)
        self.mock_resolve_check_result.outcome = MagicMock(spec=CheckOutcome, status="success")
        self.mocked_objects["resolve_check"].return_value = self.mock_resolve_check_result
        self.mocked_objects["_choose_reaction_action"].return_value = "initiate_combat"
        self.mocked_objects["crud_relationship"].get_relationship_between_entities.return_value = None


    async def asyncTearDown(self):
        for p in self.patchers:
            p.stop()

    async def test_mobile_group_actor_expands_members_into_combat(self):
        actor_group = MobileGroup(id=100, static_id="mg_attackers", name_i18n={"en":"Attackers"}, current_location_id=self.location_id, guild_id=self.guild_id)
        actor_group.member_npc_ids_json = [101, 102]
        actor_group.__class__.__name__ = "MobileGroup"


        member_npc1 = GeneratedNpc(
            id=101, name_i18n={"en":"Bandit1"}, guild_id=self.guild_id,
            properties_json={"stats": {"current_hp": 30, "hp": 30}}
        )
        member_npc2 = GeneratedNpc(
            id=102, name_i18n={"en":"Bandit2"}, guild_id=self.guild_id,
            properties_json={"stats": {"current_hp": 30, "hp": 30}}
        )

        target_player = Player(id=200, name="HeroPlayer", current_hp=100, guild_id=self.guild_id)
        target_player.__class__.__name__ = "Player" # For _get_entity_type_for_rules

        self.mocked_objects["_get_entities_in_location"].return_value = [target_player]

        async def get_npc_side_effect(session, id):
            if id == 101: return member_npc1
            if id == 102: return member_npc2
            return None
        self.mocked_objects["generated_npc_crud"].get = AsyncMock(side_effect=get_npc_side_effect)


        await backend.core.global_entity_manager._simulate_entity_interactions(
            self.mock_session, self.guild_id, actor_group
        )

        self.mocked_objects["start_combat"].assert_called_once()
        call_args = self.mocked_objects["start_combat"].call_args
        # args[3] is participant_entities list
        passed_combatants = call_args.args[3]

        self.assertIn(member_npc1, passed_combatants)
        self.assertIn(member_npc2, passed_combatants)
        self.assertIn(target_player, passed_combatants)
        self.assertEqual(len(passed_combatants), 3)


    async def test_mobile_group_target_expands_members_into_combat(self):
        actor_npc_global = GlobalNpc(id=300, static_id="gnpc_hero", name_i18n={"en":"Hero NPC"}, current_location_id=self.location_id, guild_id=self.guild_id)
        actor_npc_global.base_npc_id = 301 # Link to a GeneratedNpc
        actor_npc_global.__class__.__name__ = "GlobalNpc"

        base_actor_npc = GeneratedNpc(
            id=301, name_i18n={"en":"Base Hero"}, guild_id=self.guild_id,
            properties_json={"stats": {"current_hp": 100, "hp": 100}}
        )
        # Mock the session.get for GlobalNpc's base_npc if it's fetched via refresh
        # For this test, we can also mock the base_npc attribute directly if refresh is not easily mocked
        actor_npc_global.base_npc = base_actor_npc # Pre-set it

        target_group = MobileGroup(id=400, static_id="mg_targets", name_i18n={"en":"Target Group"}, current_location_id=self.location_id, guild_id=self.guild_id)
        target_group.member_npc_ids_json = [401, 402]
        target_group.__class__.__name__ = "MobileGroup"

        member_target_npc1 = GeneratedNpc(
            id=401, name_i18n={"en":"Target1"}, guild_id=self.guild_id,
            properties_json={"stats": {"current_hp": 20, "hp": 20}}
        )
        member_target_npc2 = GeneratedNpc(
            id=402, name_i18n={"en":"Target2"}, guild_id=self.guild_id,
            properties_json={"stats": {"current_hp": 20, "hp": 20}}
        )

        self.mocked_objects["_get_entities_in_location"].return_value = [target_group]

        async def get_npc_side_effect(session, id):
            if id == 401: return member_target_npc1
            if id == 402: return member_target_npc2
            if id == 301: return base_actor_npc # For base_npc of GlobalNpc if fetched
            return None
        self.mocked_objects["generated_npc_crud"].get = AsyncMock(side_effect=get_npc_side_effect)
        # If GlobalNpc.base_npc is accessed via relationship, ensure session.refresh is handled or attribute is pre-set
        self.mock_session.refresh = AsyncMock() # Ensure refresh doesn't break things

        await backend.core.global_entity_manager._simulate_entity_interactions(
            self.mock_session, self.guild_id, actor_npc_global
        )

        self.mocked_objects["start_combat"].assert_called_once()
        passed_combatants = self.mocked_objects["start_combat"].call_args.args[3]

        self.assertIn(base_actor_npc, passed_combatants)
        self.assertIn(member_target_npc1, passed_combatants)
        self.assertIn(member_target_npc2, passed_combatants)
        self.assertEqual(len(passed_combatants), 3)


if __name__ == "__main__":
    unittest.main()
