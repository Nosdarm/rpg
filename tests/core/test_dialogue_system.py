import asyncio
import unittest
from unittest.mock import patch, AsyncMock, MagicMock, call # Added call

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.dialogue_system import (
    start_dialogue,
    handle_dialogue_input,
    end_dialogue,
    active_dialogues,
    generate_npc_dialogue # To mock its behavior
)
from backend.models import Player, GeneratedNpc
from backend.models.enums import PlayerStatus, EventType
from backend.core.crud.crud_player import CRUDPlayer
from backend.core.crud.crud_npc import CRUDNpc
# Импортируем CRUD напрямую, так как player_crud и npc_crud - это экземпляры
# from backend.core.crud import player_crud, npc_crud # This might cause issues if CRUDBase is complex to init for mocks

# Mocking CRUD instances directly if they are simple objects
# If they are complex, we might need to mock their methods on the imported instances.
# For now, let's try to mock the classes if that's cleaner.

class TestDialogueSystem(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Очищаем active_dialogues перед каждым тестом
        active_dialogues.clear()
        self.mock_session = AsyncMock(spec=AsyncSession)
        self.guild_id = 1
        self.player_id = 10
        self.npc_id = 20
        self.other_npc_id = 21

        self.player = Player(
            id=self.player_id,
            guild_id=self.guild_id,
            name="TestPlayer",
            discord_id=12345,
            current_status=PlayerStatus.EXPLORING,
            selected_language="en",
            current_location_id=100,
            current_party_id=None # Explicitly None for clarity in tests
        )
        self.npc = GeneratedNpc(
            id=self.npc_id,
            guild_id=self.guild_id,
            name_i18n={"en": "TestNPC", "ru": "ТестНИП"},
            static_id="test_npc_01"
        )
        self.other_npc = GeneratedNpc(
            id=self.other_npc_id,
            guild_id=self.guild_id,
            name_i18n={"en": "OtherNPC", "ru": "ДругойНИП"},
            static_id="other_npc_01"
        )

    @patch('backend.core.dialogue_system.player_crud', spec=CRUDPlayer)
    @patch('backend.core.dialogue_system.npc_crud', spec=CRUDNpc)
    @patch('backend.core.dialogue_system.log_event', new_callable=AsyncMock)
    async def test_start_dialogue_success(self, mock_log_event, mock_npc_crud, mock_player_crud):
        mock_player_crud.get_by_id_and_guild.return_value = self.player
        mock_npc_crud.get_by_id_and_guild.return_value = self.npc

        success, msg_key, context = await start_dialogue(
            self.mock_session, self.guild_id, self.player_id, self.npc_id
        )

        self.assertTrue(success)
        self.assertEqual(msg_key, "dialogue_started_success")
        self.assertEqual(context["npc_name"], "TestNPC")
        self.assertEqual(self.player.current_status, PlayerStatus.DIALOGUE)
        self.assertIn((self.guild_id, self.player_id), active_dialogues)
        self.assertEqual(active_dialogues[(self.guild_id, self.player_id)]["npc_id"], self.npc_id)
        self.assertEqual(active_dialogues[(self.guild_id, self.player_id)]["npc_name"], "TestNPC")
        mock_log_event.assert_called_once_with(
            session=self.mock_session,
            guild_id=self.guild_id,
            event_type=EventType.DIALOGUE_START.name,
            details_json={
                "player_id": self.player_id,
                "npc_id": self.npc_id,
                "npc_name": "TestNPC"
            },
            player_id=self.player_id,
            location_id=self.player.current_location_id,
            entity_ids_json={"players": [self.player_id], "npcs": [self.npc_id]}
        )
        self.mock_session.add.assert_called_with(self.player)

    @patch('backend.core.dialogue_system.player_crud', spec=CRUDPlayer)
    async def test_start_dialogue_player_not_found(self, mock_player_crud):
        mock_player_crud.get_by_id_and_guild.return_value = None
        success, msg_key, context = await start_dialogue(
            self.mock_session, self.guild_id, self.player_id, self.npc_id
        )
        self.assertFalse(success)
        self.assertEqual(msg_key, "dialogue_error_player_not_found")
        self.assertNotIn((self.guild_id, self.player_id), active_dialogues)

    @patch('backend.core.dialogue_system.player_crud', spec=CRUDPlayer)
    @patch('backend.core.dialogue_system.npc_crud', spec=CRUDNpc)
    async def test_start_dialogue_npc_not_found(self, mock_npc_crud, mock_player_crud):
        mock_player_crud.get_by_id_and_guild.return_value = self.player
        mock_npc_crud.get_by_id_and_guild.return_value = None
        success, msg_key, context = await start_dialogue(
            self.mock_session, self.guild_id, self.player_id, self.npc_id
        )
        self.assertFalse(success)
        self.assertEqual(msg_key, "dialogue_error_npc_not_found")

    @patch('backend.core.dialogue_system.player_crud', spec=CRUDPlayer)
    @patch('backend.core.dialogue_system.npc_crud', spec=CRUDNpc)
    async def test_start_dialogue_player_in_combat(self, mock_npc_crud, mock_player_crud):
        self.player.current_status = PlayerStatus.COMBAT
        mock_player_crud.get_by_id_and_guild.return_value = self.player
        mock_npc_crud.get_by_id_and_guild.return_value = self.npc
        success, msg_key, context = await start_dialogue(
            self.mock_session, self.guild_id, self.player_id, self.npc_id
        )
        self.assertFalse(success)
        self.assertEqual(msg_key, "dialogue_error_player_in_combat")
        self.assertNotIn((self.guild_id, self.player_id), active_dialogues)

    @patch('backend.core.dialogue_system.player_crud', spec=CRUDPlayer)
    @patch('backend.core.dialogue_system.npc_crud', spec=CRUDNpc)
    async def test_start_dialogue_already_with_same_npc(self, mock_npc_crud, mock_player_crud):
        mock_player_crud.get_by_id_and_guild.return_value = self.player
        mock_npc_crud.get_by_id_and_guild.return_value = self.npc
        active_dialogues[(self.guild_id, self.player_id)] = {"npc_id": self.npc_id, "npc_name": "TestNPC", "dialogue_history": []}

        success, msg_key, context = await start_dialogue(
            self.mock_session, self.guild_id, self.player_id, self.npc_id
        )
        self.assertTrue(success)
        self.assertEqual(msg_key, "dialogue_already_started_with_npc")

    @patch('backend.core.dialogue_system.player_crud', spec=CRUDPlayer)
    @patch('backend.core.dialogue_system.npc_crud', spec=CRUDNpc)
    async def test_start_dialogue_already_with_other_npc(self, mock_npc_crud, mock_player_crud):
        mock_player_crud.get_by_id_and_guild.return_value = self.player
        # self.npc is the new target, self.other_npc is the one player is currently talking to
        mock_npc_crud.get_by_id_and_guild.return_value = self.npc # For the new attempt
        active_dialogues[(self.guild_id, self.player_id)] = {"npc_id": self.other_npc_id, "npc_name": "OtherNPC", "dialogue_history": []}

        success, msg_key, context = await start_dialogue(
            self.mock_session, self.guild_id, self.player_id, self.npc_id # Attempt to talk to self.npc
        )
        self.assertFalse(success)
        self.assertEqual(msg_key, "dialogue_error_player_busy_other_npc")
        self.assertEqual(context["npc_name"], "OtherNPC")


    @patch('backend.core.dialogue_system.player_crud', spec=CRUDPlayer)
    @patch('backend.core.dialogue_system.generate_npc_dialogue', new_callable=AsyncMock) # Patched here
    @patch('backend.core.dialogue_system.log_event', new_callable=AsyncMock)
    async def test_handle_dialogue_input_success_with_nlu_data(self, mock_log_event, mock_generate_dialogue, mock_player_crud):
        mock_player_crud.get_by_id_and_guild.return_value = self.player
        active_dialogues[(self.guild_id, self.player_id)] = {
            "npc_id": self.npc_id,
            "npc_name": "TestNPC",
            "dialogue_history": []
        }
        mock_generate_dialogue.return_value = "NPC Response based on NLU"
        player_message = "Tell me about the artifact"
        test_intent = "query_artifact"
        test_entities = [{"type": "item_name", "value": "artifact"}]

        success, response, context = await handle_dialogue_input(
            self.mock_session, self.guild_id, self.player_id, player_message,
            parsed_intent=test_intent,
            parsed_entities=test_entities
        )

        self.assertTrue(success)
        self.assertEqual(response, "NPC Response based on NLU")
        self.assertEqual(context["npc_name"], "TestNPC")

        history = active_dialogues[(self.guild_id, self.player_id)]["dialogue_history"]
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0], {"speaker": "player", "line": player_message})
        self.assertEqual(history[1], {"speaker": "npc", "line": "NPC Response based on NLU"})

        expected_context_for_llm = {
            "guild_id": self.guild_id,
            "player_id": self.player_id,
            "player_name": self.player.name,
            "npc_id": self.npc_id,
            "player_input_text": player_message,
            "dialogue_history": [{"speaker": "player", "line": player_message}], # History before NPC response
            "selected_language": self.player.selected_language,
            "location_id": self.player.current_location_id,
            "party_id": self.player.current_party_id,
            "parsed_intent": test_intent, # Check for NLU data
            "parsed_entities": test_entities # Check for NLU data
        }
        mock_generate_dialogue.assert_called_once_with(
            self.mock_session, self.guild_id, expected_context_for_llm
        )

        self.assertEqual(mock_log_event.call_count, 2)
        log_calls = mock_log_event.call_args_list

        player_log_call = call(
            session=self.mock_session, guild_id=self.guild_id, event_type=EventType.DIALOGUE_LINE.name,
            details_json={'player_id': self.player_id, 'npc_id': self.npc_id, 'speaker': 'player', 'line': player_message, 'npc_name': 'TestNPC', 'player_name': 'TestPlayer'},
            player_id=self.player_id, location_id=self.player.current_location_id, entity_ids_json={'players': [self.player_id], 'npcs': [self.npc_id]}
        )
        npc_log_call = call(
            session=self.mock_session, guild_id=self.guild_id, event_type=EventType.DIALOGUE_LINE.name,
            details_json={'player_id': self.player_id, 'npc_id': self.npc_id, 'speaker': 'npc', 'line': "NPC Response based on NLU", 'npc_name': 'TestNPC', 'player_name': 'TestPlayer'},
            player_id=self.player_id, location_id=self.player.current_location_id, entity_ids_json={'players': [self.player_id], 'npcs': [self.npc_id]}
        )
        self.assertIn(player_log_call, log_calls)
        self.assertIn(npc_log_call, log_calls)

    async def test_handle_dialogue_input_not_in_dialogue(self):
        # Test without NLU data as it's not relevant if not in dialogue
        success, response, context = await handle_dialogue_input(
            self.mock_session, self.guild_id, self.player_id, "Hi"
        )
        self.assertFalse(success)
        self.assertEqual(response, "dialogue_error_not_in_dialogue")

    @patch('backend.core.dialogue_system.player_crud', spec=CRUDPlayer)
    @patch('backend.core.dialogue_system.log_event', new_callable=AsyncMock)
    async def test_end_dialogue_success(self, mock_log_event, mock_player_crud):
        mock_player_crud.get_by_id_and_guild.return_value = self.player
        self.player.current_status = PlayerStatus.DIALOGUE
        active_dialogues[(self.guild_id, self.player_id)] = {
            "npc_id": self.npc_id,
            "npc_name": "TestNPC",
            "dialogue_history": [{"speaker": "player", "line": "Hello"}, {"speaker": "npc", "line": "Hi"}]
        }

        success, msg_key, context = await end_dialogue(
            self.mock_session, self.guild_id, self.player_id
        )

        self.assertTrue(success)
        self.assertEqual(msg_key, "dialogue_ended_success")
        self.assertEqual(context["npc_name"], "TestNPC")
        self.assertEqual(self.player.current_status, PlayerStatus.EXPLORING)
        self.assertNotIn((self.guild_id, self.player_id), active_dialogues)

        mock_log_event.assert_called_once_with(
            session=self.mock_session,
            guild_id=self.guild_id,
            event_type=EventType.DIALOGUE_END.name,
            details_json={
                "player_id": self.player_id,
                "npc_id": self.npc_id,
                "npc_name": "TestNPC",
                "player_name": self.player.name,
                "dialogue_history_length": 2
            },
            player_id=self.player_id,
            location_id=self.player.current_location_id,
            entity_ids_json={"players": [self.player_id], "npcs": [self.npc_id]}
        )
        self.mock_session.add.assert_called_with(self.player)

    @patch('backend.core.dialogue_system.player_crud', spec=CRUDPlayer)
    async def test_end_dialogue_not_in_dialogue_status_not_dialogue(self, mock_player_crud):
        self.player.current_status = PlayerStatus.EXPLORING
        mock_player_crud.get_by_id_and_guild.return_value = self.player

        success, msg_key, context = await end_dialogue(
            self.mock_session, self.guild_id, self.player_id
        )
        self.assertTrue(success)
        self.assertEqual(msg_key, "dialogue_not_active_already_ended")

    @patch('backend.core.dialogue_system.player_crud', spec=CRUDPlayer)
    async def test_end_dialogue_not_in_dialogue_status_is_dialogue(self, mock_player_crud):
        self.player.current_status = PlayerStatus.DIALOGUE
        mock_player_crud.get_by_id_and_guild.return_value = self.player

        success, msg_key, context = await end_dialogue(
            self.mock_session, self.guild_id, self.player_id
        )
        self.assertFalse(success)
        self.assertEqual(msg_key, "dialogue_error_not_in_dialogue_to_end")
        self.assertEqual(self.player.current_status, PlayerStatus.DIALOGUE)


if __name__ == '__main__':
    unittest.main()
