import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import discord
from discord.ext import commands
from backend.bot.commands.party_commands import PartyCog
from backend.models.player import Player, PlayerStatus
from backend.models.party import Party
from backend.models.location import Location, LocationType

class MockGuild:
    def __init__(self, id):
        self.id = id
        self.name = "Test Guild"

class MockUser(MagicMock):
    def __init__(self, id, name):
        super().__init__()
        self.id = id
        self.name = name
        self.mention = f"<@{id}>"

class MockInteraction:
    def __init__(self, user: MockUser, guild: Optional[MockGuild] = None):
        self.user = user
        self.guild = guild
        self.response = MagicMock(spec=discord.InteractionResponse)
        self.response.send_message = AsyncMock()
        self.response.is_done = MagicMock(return_value=False)

class TestPartyCommands(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.bot_mock = AsyncMock(spec=commands.Bot)
        self.cog = PartyCog(self.bot_mock)

        self.session_mock = AsyncMock(spec=AsyncSession)

        # Patch the transactional decorator to inject the session
        self.patcher_transactional = patch('backend.bot.commands.party_commands.transactional')
        self.mock_transactional = self.patcher_transactional.start()

        def transactional_side_effect(func):
            async def wrapper(cog_instance, interaction, *args, **kwargs):
                return await func(cog_instance, interaction, *args, **kwargs, session=self.session_mock)
            return wrapper
        self.mock_transactional.side_effect = transactional_side_effect

        self.patcher_player_crud = patch('backend.bot.commands.party_commands.player_crud', new_callable=AsyncMock)
        self.mock_player_crud = self.patcher_player_crud.start()

        self.patcher_party_crud = patch('backend.bot.commands.party_commands.party_crud', new_callable=AsyncMock)
        self.mock_party_crud = self.patcher_party_crud.start()

        self.patcher_location_crud = patch('backend.bot.commands.party_commands.location_crud', new_callable=AsyncMock)
        self.mock_location_crud = self.patcher_location_crud.start()

        self.patcher_get_rule = patch('backend.bot.commands.party_commands.get_rule', new_callable=AsyncMock)
        self.mock_get_rule = self.patcher_get_rule.start()

        self.guild = MockGuild(id=789)
        self.user = MockUser(id=321, name="TestPartyUser")
        self.interaction = MockInteraction(user=self.user, guild=self.guild)

        self.player = Player(id=1, guild_id=self.guild.id, discord_id=self.user.id, name=self.user.name, current_party_id=None)
        self.mock_player_crud.get_by_discord_id.return_value = self.player

    def tearDown(self):
        self.patcher_transactional.stop()
        self.patcher_player_crud.stop()
        self.patcher_party_crud.stop()
        self.patcher_location_crud.stop()
        self.patcher_get_rule.stop()

    async def test_party_create_success(self):
        self.mock_get_rule.side_effect = lambda s, g, key, default: default
        self.mock_party_crud.get_by_name.return_value = None

        created_party = Party(id=100, name="Cool Adventurers")
        self.mock_party_crud.create_with_leader.return_value = created_party

        await self.cog.party_create.callback(self.cog, self.interaction, "Cool Adventurers")

        self.mock_party_crud.create_with_leader.assert_called_once()
        self.assertEqual(self.player.current_party_id, created_party.id)
        self.session_mock.add.assert_called_with(self.player)
        self.interaction.response.send_message.assert_called_once_with(f"Группа 'Cool Adventurers' успешно создана! Вы ее лидер.")

    async def test_party_create_fails_already_in_party(self):
        self.player.current_party_id = 101
        self.mock_party_crud.get.return_value = Party(name="Old Crew")

        await self.cog.party_create.callback(self.cog, self.interaction, "New Party")

        self.interaction.response.send_message.assert_called_once_with(
            "Вы уже состоите в группе 'Old Crew'. Сначала покиньте ее.",
            ephemeral=True
        )

    async def test_party_leave_success_and_disband(self):
        party_to_leave = Party(id=102, guild_id=self.guild.id, name="Solo Group", player_ids_json=[self.player.id], leader_player_id=self.player.id)
        self.player.current_party_id = party_to_leave.id
        self.mock_party_crud.get.return_value = party_to_leave

        async def mock_remove_player(session, party, player_id):
            party.player_ids_json = []
            return party
        self.mock_party_crud.remove_player_from_party_json.side_effect = mock_remove_player
        self.mock_get_rule.return_value = "promote_oldest_member"

        await self.cog.party_leave.callback(self.cog, self.interaction)

        self.mock_party_crud.delete.assert_called_once_with(self.session_mock, id=party_to_leave.id, guild_id=self.guild.id)
        self.interaction.response.send_message.assert_called_once_with(f"Вы покинули группу 'Solo Group'. Группа была распущена.")
        self.assertIsNone(self.player.current_party_id)

    async def test_disband_success(self):
        party_to_disband = Party(id=103, guild_id=self.guild.id, name="The Crew", leader_player_id=self.player.id, player_ids_json=[self.player.id, 2])
        self.player.current_party_id = party_to_disband.id
        self.mock_party_crud.get.return_value = party_to_disband

        member2 = Player(id=2, current_party_id=103)
        self.mock_player_crud.get.return_value = member2

        await self.cog.party_disband.callback(self.cog, self.interaction)

        self.mock_party_crud.delete.assert_called_once_with(self.session_mock, id=party_to_disband.id, guild_id=self.guild.id)
        # Check that both players were updated
        self.assertEqual(self.session_mock.add.call_count, 2)
        self.interaction.response.send_message.assert_called_once_with("Группа 'The Crew' была успешно распущена.")

    async def test_disband_fails_not_leader(self):
        party_to_disband = Party(id=104, leader_player_id=999) # Leader is someone else
        self.player.current_party_id = 104
        self.mock_party_crud.get.return_value = party_to_disband

        await self.cog.party_disband.callback(self.cog, self.interaction)

        self.mock_party_crud.delete.assert_not_called()
        self.interaction.response.send_message.assert_called_once_with("Только лидер группы может ее распустить.", ephemeral=True)

    async def test_join_success(self):
        self.player.current_party_id = None
        target_party = Party(id=105, name="Open Party", player_ids_json=[])
        self.mock_party_crud.get_by_id_or_name.return_value = target_party
        self.mock_get_rule.return_value = 5 # max_size

        async def mock_add_player(session, party, player_id):
            party.player_ids_json.append(player_id)
            return party
        self.mock_party_crud.add_player_to_party_json.side_effect = mock_add_player

        await self.cog.party_join.callback(self.cog, self.interaction, "Open Party")

        self.mock_party_crud.add_player_to_party_json.assert_called_once()
        self.assertEqual(self.player.current_party_id, target_party.id)
        self.interaction.response.send_message.assert_called_once_with("Вы успешно присоединились к группе 'Open Party'.")

    async def test_join_fails_party_full(self):
        self.player.current_party_id = None
        target_party = Party(id=106, name="Full Party", player_ids_json=[1,2,3,4,5])
        self.mock_party_crud.get_by_id_or_name.return_value = target_party
        self.mock_get_rule.return_value = 5 # max_size

        await self.cog.party_join.callback(self.cog, self.interaction, "Full Party")

        self.mock_party_crud.add_player_to_party_json.assert_not_called()
        self.interaction.response.send_message.assert_called_once_with("Группа 'Full Party' уже заполнена.", ephemeral=True)

    async def test_kick_success(self):
        party = Party(id=107, leader_player_id=self.player.id, player_ids_json=[self.player.id, 99])
        self.player.current_party_id = party.id
        self.mock_party_crud.get.return_value = party

        target_user = MockUser(id=99, name="KickedUser")
        target_player_db = Player(id=99, discord_id=99, current_party_id=party.id)
        self.mock_player_crud.get_by_discord_id.side_effect = [self.player, target_player_db]

        async def mock_remove_player(session, party, player_id):
            party.player_ids_json.remove(player_id)
            return party
        self.mock_party_crud.remove_player_from_party_json.side_effect = mock_remove_player

        await self.cog.party_kick.callback(self.cog, self.interaction, target_player=target_user)

        self.mock_party_crud.remove_player_from_party_json.assert_called_once()
        self.assertIsNone(target_player_db.current_party_id)
        self.interaction.response.send_message.assert_called_once_with(f"Игрок {target_user.mention} был исключен из группы.")

    async def test_kick_fails_not_leader(self):
        party = Party(id=108, leader_player_id=999) # Not the leader
        self.player.current_party_id = party.id
        self.mock_party_crud.get.return_value = party
        target_user = MockUser(id=99, name="TargetUser")

        await self.cog.party_kick.callback(self.cog, self.interaction, target_player=target_user)

        self.interaction.response.send_message.assert_called_once_with("Только лидер может исключать игроков.", ephemeral=True)

if __name__ == '__main__':
    unittest.main()
