import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.quest_system import (
    handle_player_event_for_quest,
    _check_mechanic_match,
    _evaluate_abstract_goal,
    _advance_quest_progress,
    _apply_quest_consequences,
)
from src.models import StoryLog, PlayerQuestProgress, GeneratedQuest, QuestStep, Player, Party
from src.models.enums import EventType, QuestStatus, RelationshipEntityType


class TestQuestSystem(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_session = AsyncMock(spec=AsyncSession)
        self.guild_id = 1
        self.player_id = 10
        self.party_id = 100
        self.quest_id = 1000
        self.step_id_1 = 1001
        self.step_id_2 = 1002
        self.location_id = 5

        self.mock_event_log_entry = MagicMock(spec=StoryLog)
        self.mock_event_log_entry.id = 999
        self.mock_event_log_entry.event_type = EventType.COMBAT_END
        self.mock_event_log_entry.details_json = {"winning_team": "players"}
        self.mock_event_log_entry.location_id = self.location_id

        self.mock_player = MagicMock(spec=Player)
        self.mock_player.id = self.player_id
        self.mock_player.current_party_id = self.party_id
        self.mock_player.selected_language = "en"

        self.mock_party = MagicMock(spec=Party)
        self.mock_party.id = self.party_id
        self.mock_party.player_ids_json = [self.player_id, self.player_id + 1]
        self.mock_party.players = [self.mock_player]

        self.mock_quest_step_1 = MagicMock(spec=QuestStep)
        self.mock_quest_step_1.id = self.step_id_1
        self.mock_quest_step_1.step_order = 1
        self.mock_quest_step_1.title_i18n = {"en": "First Step"}
        self.mock_quest_step_1.required_mechanics_json = {
            "event_type": "COMBAT_END",
            "details_subset": {"winning_team": "players"}
        }
        self.mock_quest_step_1.abstract_goal_json = {"enabled": True, "description_i18n": {"en": "Test Goal"}, "evaluation_method": "rule_based"} # Changed to True and added example fields
        self.mock_quest_step_1.consequences_json = {"xp_award": {"amount": 100}}

        self.mock_quest_step_2 = MagicMock(spec=QuestStep)
        self.mock_quest_step_2.id = self.step_id_2
        self.mock_quest_step_2.step_order = 2
        self.mock_quest_step_2.title_i18n = {"en": "Second Step"}
        self.mock_quest_step_2.required_mechanics_json = {"event_type": "ITEM_USED"}
        self.mock_quest_step_2.abstract_goal_json = {"enabled": False}
        self.mock_quest_step_2.consequences_json = {"xp_award": {"amount": 200}}

        self.mock_quest = MagicMock(spec=GeneratedQuest)
        self.mock_quest.id = self.quest_id
        self.mock_quest.static_id = "test_quest_01"
        self.mock_quest.title_i18n = {"en": "Test Quest"}
        self.mock_quest.steps = [self.mock_quest_step_1, self.mock_quest_step_2]
        self.mock_quest.rewards_json = {"item_rewards": [{"item_static_id": "gold_coins", "quantity": 100}]}
        self.mock_quest.questline_id = None
        self.mock_quest.questline = None

        self.mock_progress_entry = MagicMock(spec=PlayerQuestProgress)
        self.mock_progress_entry.id = 2000
        self.mock_progress_entry.player_id = self.player_id
        self.mock_progress_entry.guild_id = self.guild_id
        self.mock_progress_entry.status = QuestStatus.IN_PROGRESS
        self.mock_progress_entry.quest = self.mock_quest
        self.mock_progress_entry.current_step = self.mock_quest_step_1
        self.mock_progress_entry.current_step_id = self.step_id_1

    @patch('src.core.crud.crud_party.party_crud', new_callable=AsyncMock)
    @patch('src.core.quest_system.select')
    @patch('src.core.quest_system._check_mechanic_match', new_callable=AsyncMock)
    @patch('src.core.quest_system._evaluate_abstract_goal', new_callable=AsyncMock)
    @patch('src.core.quest_system._apply_quest_consequences', new_callable=AsyncMock)
    @patch('src.core.quest_system._advance_quest_progress', new_callable=AsyncMock)
    @patch('src.core.quest_system.core_log_event', new_callable=AsyncMock)
    async def test_handle_player_event_successful_step_completion(
        self, mock_log_event_func, mock_advance_progress, mock_apply_consequences,
        mock_evaluate_goal, mock_check_mechanic, mock_sqlalchemy_select, mock_party_crud_instance
    ):
        mock_party_crud_instance.get.return_value = self.mock_party

        # Corrected mocking for session.execute().scalars().all()
        mock_result_object = MagicMock()
        mock_scalars_object = MagicMock()
        mock_scalars_object.all.return_value = [self.mock_progress_entry]
        mock_result_object.scalars.return_value = mock_scalars_object
        self.mock_session.execute = AsyncMock(return_value=mock_result_object)

        mock_sqlalchemy_select.return_value.where.return_value.options.return_value = MagicMock()

        mock_check_mechanic.return_value = True
        mock_evaluate_goal.return_value = True

        await handle_player_event_for_quest(
            self.mock_session, self.guild_id, self.mock_event_log_entry, player_id=self.player_id, party_id=self.party_id
        )

        if self.party_id:
            mock_party_crud_instance.get.assert_called_once_with(session=self.mock_session, id=self.party_id, guild_id=self.guild_id)

        self.mock_session.execute.assert_called() # This will be called for each player in target_player_ids

        # _check_mechanic_match will be called for each player with active quests.
        # In this setup, target_player_ids will have 2 players (self.player_id and self.player_id + 1)
        # and mock_scalars_obj.all.return_value returns [self.mock_progress_entry] for both.
        # So, _check_mechanic_match should be called twice with the same arguments.
        self.assertEqual(mock_check_mechanic.call_count, len(self.mock_party.player_ids_json))
        mock_check_mechanic.assert_any_call( # Use assert_any_call as it's called multiple times with same args
            self.mock_session, self.guild_id, self.mock_event_log_entry, self.mock_quest_step_1.required_mechanics_json
        )

        # Similarly, _evaluate_abstract_goal will be called twice.
        self.assertEqual(mock_evaluate_goal.call_count, len(self.mock_party.player_ids_json))
        # We need to check based on the player_id that was actually processed first by the loop in the main code
        # For simplicity, checking with self.player_id (the first one in mock_party.player_ids_json)
        mock_evaluate_goal.assert_any_call(
            self.mock_session, self.guild_id, self.player_id, self.party_id, self.mock_quest, self.mock_quest_step_1, self.mock_event_log_entry
        )

        # _apply_quest_consequences and _advance_quest_progress will be called for each player.
        # In this test setup, it's effectively for self.player_id first due to loop order and mock setup.
        self.assertEqual(mock_apply_consequences.call_count, len(self.mock_party.player_ids_json))
        mock_apply_consequences.assert_any_call(
            self.mock_session, self.guild_id, self.mock_quest_step_1.consequences_json,
            self.player_id, self.party_id, self.quest_id, self.step_id_1, self.mock_event_log_entry
            # Note: The second call would be for player_id = self.player_id + 1
        )

        self.assertEqual(mock_log_event_func.call_count, len(self.mock_party.player_ids_json)) # Once per player for QUEST_STEP_COMPLETED
        mock_log_event_func.assert_any_call(
            self.mock_session, self.guild_id, EventType.QUEST_STEP_COMPLETED.name,
            details_json={
                "player_id": self.player_id, "quest_id": self.quest_id, "quest_static_id": "test_quest_01",
                "step_id": self.step_id_1, "step_order": 1, "step_title": "First Step"
            },
            player_id=self.player_id, location_id=self.location_id
        )

        self.assertEqual(mock_advance_progress.call_count, len(self.mock_party.player_ids_json))
        mock_advance_progress.assert_any_call(
            self.mock_session, self.guild_id, self.mock_progress_entry, self.player_id, self.party_id, self.mock_event_log_entry
            # Note: The second call would be for player_id = self.player_id + 1
        )

    async def test_check_mechanic_match_event_type_mismatch(self):
        event = MagicMock(spec=StoryLog)
        event.event_type.name = "ITEM_PICKED_UP"
        required_mechanics = {"event_type": "COMBAT_END"}
        self.assertFalse(await _check_mechanic_match(self.mock_session, self.guild_id, event, required_mechanics))

    async def test_check_mechanic_match_details_subset_match(self):
        event = MagicMock(spec=StoryLog)
        event.event_type.name = "COMBAT_END"
        event.details_json = {"winning_team": "players", "enemy_type": "goblin"}
        required_mechanics = {
            "event_type": "COMBAT_END",
            "details_subset": {"winning_team": "players"}
        }
        self.assertTrue(await _check_mechanic_match(self.mock_session, self.guild_id, event, required_mechanics))

    async def test_check_mechanic_match_details_subset_mismatch(self):
        event = MagicMock(spec=StoryLog)
        event.event_type.name = "COMBAT_END"
        event.details_json = {"winning_team": "npcs"}
        required_mechanics = {
            "event_type": "COMBAT_END",
            "details_subset": {"winning_team": "players"}
        }
        self.assertFalse(await _check_mechanic_match(self.mock_session, self.guild_id, event, required_mechanics))

    @patch('src.core.quest_system.core_log_event', new_callable=AsyncMock)
    @patch('src.core.quest_system._apply_quest_consequences', new_callable=AsyncMock)
    async def test_advance_quest_progress_to_next_step(self, mock_apply_consequences, mock_log_event_func):
        await _advance_quest_progress(self.mock_session, self.guild_id, self.mock_progress_entry, self.player_id, self.party_id, self.mock_event_log_entry)

        self.assertEqual(self.mock_progress_entry.current_step_id, self.step_id_2)
        self.assertEqual(self.mock_progress_entry.status, QuestStatus.IN_PROGRESS)
        self.mock_session.add.assert_called_with(self.mock_progress_entry)

        expected_details_for_step_started = {
            "subtype": "QUEST_STEP_STARTED",
            "player_id": self.player_id, "quest_id": self.quest_id, "quest_static_id": "test_quest_01",
            "step_id": self.step_id_2, "step_order": 2, "step_title": "Second Step"
        }
        mock_log_event_func.assert_any_call(
            self.mock_session,
            self.guild_id,
            EventType.SYSTEM_EVENT.name,
            details_json=expected_details_for_step_started,
            player_id=self.player_id,
            location_id=self.location_id
        )

    @patch('src.core.quest_system.core_log_event', new_callable=AsyncMock)
    @patch('src.core.quest_system._apply_quest_consequences', new_callable=AsyncMock)
    async def test_advance_quest_progress_to_completion(self, mock_apply_consequences, mock_log_event_func):
        self.mock_progress_entry.current_step = self.mock_quest_step_2 # Set current step to the last step
        self.mock_progress_entry.current_step_id = self.step_id_2

        await _advance_quest_progress(self.mock_session, self.guild_id, self.mock_progress_entry, self.player_id, self.party_id, self.mock_event_log_entry)

        self.assertIsNone(self.mock_progress_entry.current_step_id)
        self.assertEqual(self.mock_progress_entry.status, QuestStatus.COMPLETED)
        self.mock_session.add.assert_called_with(self.mock_progress_entry)

        mock_log_event_func.assert_any_call(
            self.mock_session, self.guild_id, EventType.QUEST_COMPLETED.name,
            details_json={
                "player_id": self.player_id, "quest_id": self.quest_id, "quest_static_id": "test_quest_01",
                "quest_title": "Test Quest"
            },
            player_id=self.player_id, location_id=self.location_id
        )
        mock_apply_consequences.assert_called_once_with( # Ensure overall rewards are applied
            self.mock_session, self.guild_id, self.mock_quest.rewards_json,
            self.player_id, self.party_id, self.quest_id, None, self.mock_event_log_entry
        )

    @patch('src.core.experience_system.award_xp', new_callable=AsyncMock)
    @patch('src.core.relationship_system.update_relationship', new_callable=AsyncMock)
    @patch('src.core.quest_system.core_log_event', new_callable=AsyncMock)
    async def test_apply_quest_consequences_all_types(self, mock_internal_log, mock_update_rel, mock_award_xp):
        consequences = {
            "xp_award": {"amount": 150},
            "relationship_changes": [{
                "target_entity_id": 501, "target_entity_type": "GENERATED_NPC", "delta": 10 # Corrected NPC to GENERATED_NPC
            }],
            "item_rewards": [{"item_static_id": "magic_orb", "quantity": 1}],
            "world_state_changes": [{"flag_key": "portal_active", "value": True}]
        }
        await _apply_quest_consequences(
            self.mock_session, self.guild_id, consequences, self.player_id, None,
            self.quest_id, self.step_id_1, self.mock_event_log_entry
        )

        mock_award_xp.assert_called_once_with(
            self.mock_session, self.guild_id, self.player_id, RelationshipEntityType.PLAYER, 150,
            source_event_type=EventType.SYSTEM_EVENT,
            source_log_id=self.mock_event_log_entry.id
        )
        mock_update_rel.assert_called_once_with(
            self.mock_session, self.guild_id,
            entity_doing_id=self.player_id, entity_doing_type=RelationshipEntityType.PLAYER,
            target_entity_id=501, target_entity_type=RelationshipEntityType.GENERATED_NPC,
            event_type=EventType.SYSTEM_EVENT.name,
            event_details_log_id=self.mock_event_log_entry.id
        )

        # Check for ITEM_ACQUIRED log
        expected_item_details = {
            "player_id": self.player_id, "item_static_id": "magic_orb", "quantity": 1,
            "source": "quest_reward",
            "source_quest_id": self.quest_id, "source_step_id": self.step_id_1
        }
        mock_internal_log.assert_any_call(
            self.mock_session, self.guild_id, EventType.ITEM_ACQUIRED.name,
            details_json=expected_item_details,
            player_id=self.player_id, location_id=self.location_id
        )

        # Check for WORLD_STATE_CHANGE log
        expected_ws_details = {
            "flag_key": "portal_active", "new_value": True,
            "source": "quest_consequence",
            "source_quest_id": self.quest_id, "source_step_id": self.step_id_1,
            "triggered_by_player_id": self.player_id,
            "triggered_by_party_id": None,
        }
        mock_internal_log.assert_any_call(
            self.mock_session, self.guild_id, EventType.WORLD_STATE_CHANGE.name,
            details_json=expected_ws_details,
            location_id=self.location_id
        )

if __name__ == '__main__':
    unittest.main()
