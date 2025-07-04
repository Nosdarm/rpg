import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call # Added call
from sqlalchemy.ext.asyncio import AsyncSession # Added AsyncSession

import discord # type: ignore
from discord.ext import commands # type: ignore
from typing import Optional # Added Optional

from src.bot.commands.party_commands import PartyCog
from src.models.player import Player, PlayerStatus
from src.models.party import Party, PartyTurnStatus
from src.models.location import Location, LocationType

# Моки для discord.py объектов
class MockGuild:
    def __init__(self, id):
        self.id = id

class MockAuthor(discord.User): # Наследуемся от discord.User для type hints
    def __init__(self, id, name, display_name=None):
        user_data = {'id': str(id), 'username': name, 'discriminator': '0000', 'avatar': None}
        if display_name:
            user_data['global_name'] = display_name
        super().__init__(state=MagicMock(), data=user_data)
        # self.display_name is a property and should work correctly now based on global_name or name
        # self.mention is also a property, no need to set it manually.

class MockContext:
    def __init__(self, author: MockAuthor, guild: Optional[MockGuild] = None):
        self.author = author
        self.guild = guild
        self.invoked_subcommand = True # По умолчанию считаем, что подкоманда вызвана
        self.send = AsyncMock()


class TestPartyCommands(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.bot_mock = AsyncMock(spec=commands.Bot)
        self.cog = PartyCog(self.bot_mock)

        self.session_mock = AsyncMock(spec=AsyncSession)
        self.patcher_get_db_session = patch('src.bot.commands.party_commands.get_db_session')
        self.mock_get_db_session = self.patcher_get_db_session.start()
        self.mock_get_db_session.return_value.__aenter__.return_value = self.session_mock

        self.patcher_player_crud = patch('src.bot.commands.party_commands.player_crud', new_callable=AsyncMock)
        self.mock_player_crud = self.patcher_player_crud.start()

        self.patcher_party_crud = patch('src.bot.commands.party_commands.party_crud', new_callable=AsyncMock)
        self.mock_party_crud = self.patcher_party_crud.start()

        self.patcher_location_crud = patch('src.bot.commands.party_commands.location_crud', new_callable=AsyncMock)
        self.mock_location_crud = self.patcher_location_crud.start()

        self.patcher_get_localized_text = patch('src.bot.commands.party_commands.get_localized_text')
        self.mock_get_localized_text = self.patcher_get_localized_text.start()
        self.mock_get_localized_text.side_effect = lambda entity, field, lang, fallback="en": entity.name_i18n.get(lang, entity.name_i18n.get(fallback, "Unknown Location"))


        self.guild = MockGuild(id=789)
        self.author = MockAuthor(id=321, name="TestPartyUser") # Reverted user to author

        # Reverted to MockContext or a MagicMock for commands.Context
        self.ctx = AsyncMock(spec=commands.Context) # Use AsyncMock for context as commands can be async
        self.ctx.author = self.author
        self.ctx.guild = self.guild
        self.ctx.invoked_subcommand = True # Default assumption
        self.ctx.send = AsyncMock() # ctx.send is an async method
        # self.ctx.locale can be set if needed, commands.Context might not have it directly like Interaction.
        # For prefixed commands, locale is usually handled differently or via bot.
        # If SUT uses ctx.locale, ensure it's mocked:
        # self.ctx.locale = discord.Locale("en-US") # Example, if PartyCog used ctx.locale

        self.player_location = Location(id=10, guild_id=self.guild.id, name_i18n={"en": "Player's Spot"}, descriptions_i18n={}, type=LocationType.GENERIC)


    def tearDown(self):
        self.patcher_get_db_session.stop()
        self.patcher_player_crud.stop()
        self.patcher_party_crud.stop()
        self.patcher_location_crud.stop()
        self.patcher_get_localized_text.stop()

    async def test_party_create_success(self):
        player_in_db = Player(id=1, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=None, current_location_id=self.player_location.id)
        self.mock_player_crud.get_by_discord_id.return_value = player_in_db

        created_party = Party(id=100, guild_id=self.guild.id, name="Cool Adventurers", player_ids_json=[player_in_db.id], current_location_id=player_in_db.current_location_id)
        self.mock_party_crud.create.return_value = created_party

        await self.cog.party_create.callback(self.cog, self.ctx, party_name="Cool Adventurers")

        self.mock_party_crud.create.assert_called_once()
        created_data = self.mock_party_crud.create.call_args[1]['obj_in']
        self.assertEqual(created_data['name'], "Cool Adventurers")
        self.assertEqual(created_data['player_ids_json'], [player_in_db.id])

        self.session_mock.merge.assert_called_once() # For player update
        self.assertEqual(player_in_db.current_party_id, created_party.id)

        self.session_mock.commit.assert_called_once()
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, группа 'Cool Adventurers' успешно создана! Ты ее первый участник.")

    async def test_party_create_player_already_in_party(self):
        existing_party = Party(id=101, name="Old Party")
        player_in_db = Player(id=2, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=existing_party.id)
        self.mock_player_crud.get_by_discord_id.return_value = player_in_db
        self.mock_party_crud.get.return_value = existing_party # For fetching existing party name

        await self.cog.party_create.callback(self.cog, self.ctx, party_name="New Party")

        self.mock_party_crud.create.assert_not_called()
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, ты уже состоишь в группе 'Old Party'. Сначала покинь ее.")

    async def test_party_leave_success_and_disband(self):
        party_to_leave = Party(id=102, guild_id=self.guild.id, name="Solo Group", player_ids_json=[1]) # Initially one member
        player_in_db = Player(id=1, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=party_to_leave.id)

        self.mock_player_crud.get_by_discord_id.return_value = player_in_db
        self.mock_party_crud.get.return_value = party_to_leave

        # Mock remove_player_from_party_json to simulate party becoming empty
        async def mock_remove_player(session, party, player_id):
            party.player_ids_json = [] # Simulate player removal making it empty
            return party
        self.mock_party_crud.remove_player_from_party_json.side_effect = mock_remove_player

        await self.cog.party_leave.callback(self.cog, self.ctx)

        self.mock_party_crud.remove_player_from_party_json.assert_called_once_with(self.session_mock, party=party_to_leave, player_id=player_in_db.id)
        self.assertIsNone(player_in_db.current_party_id)
        self.mock_party_crud.delete.assert_called_once_with(self.session_mock, id=party_to_leave.id, guild_id=self.guild.id)
        self.session_mock.commit.assert_called_once()
        self.ctx.send.assert_called_once_with(f"{self.author.mention} покинул группу 'Solo Group'. Группа была распущена, так как стала пустой.")

    async def test_party_disband_success(self):
        party_to_disband = Party(id=103, guild_id=self.guild.id, name="To Be Disbanded", player_ids_json=[1, 2])
        player_in_db = Player(id=1, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=party_to_disband.id)
        member2 = Player(id=2, discord_id=999, guild_id=self.guild.id, name="Member2", current_party_id=party_to_disband.id)

        self.mock_player_crud.get_by_discord_id.return_value = player_in_db
        self.mock_party_crud.get.return_value = party_to_disband
        # Mock player_crud.get to return members when updating their current_party_id
        self.mock_player_crud.get.side_effect = lambda db, id, guild_id: player_in_db if id == 1 else member2 if id == 2 else None

        await self.cog.party_disband.callback(self.cog, self.ctx)

        self.mock_party_crud.delete.assert_called_once_with(self.session_mock, id=party_to_disband.id, guild_id=self.guild.id)

        # Check player updates
        self.assertEqual(self.session_mock.merge.call_count, 2) # For player_in_db and member2
        self.assertIsNone(player_in_db.current_party_id)
        self.assertIsNone(member2.current_party_id)

        self.session_mock.commit.assert_called_once()
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, группа 'To Be Disbanded' была успешно распущена. Все участники покинули группу.")

    async def test_party_join_success_by_name(self):
        player_in_db = Player(id=3, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=None, current_location_id=self.player_location.id, selected_language="en")
        self.mock_player_crud.get_by_discord_id.return_value = player_in_db

        target_party = Party(id=104, guild_id=self.guild.id, name="Joinable Party", player_ids_json=[], current_location_id=self.player_location.id)
        self.mock_party_crud.get.return_value = None # Not found by ID initially
        self.mock_party_crud.get_by_name.return_value = target_party

        # Mock add_player_to_party_json
        async def mock_add_player_json(session, party, player_id):
            party.player_ids_json = [player_id]
            return party
        self.mock_party_crud.add_player_to_party_json.side_effect = mock_add_player_json

        self.mock_location_crud.get.return_value = self.player_location # For fetching location name

        await self.cog.party_join.callback(self.cog, self.ctx, party_identifier="Joinable Party")

        self.mock_party_crud.get_by_name.assert_called_once_with(self.session_mock, guild_id=self.guild.id, name="Joinable Party")
        self.mock_party_crud.add_player_to_party_json.assert_called_once_with(self.session_mock, party=target_party, player_id=player_in_db.id)
        self.assertEqual(player_in_db.current_party_id, target_party.id)
        self.session_mock.merge.assert_called_once_with(player_in_db)
        self.session_mock.commit.assert_called_once()
        self.ctx.send.assert_called_once_with(f"{self.author.mention} успешно присоединился к группе 'Joinable Party'! Текущая локация группы: Player's Spot.")

    async def test_party_join_moves_player_location(self):
        different_loc = Location(id=11, guild_id=self.guild.id, name_i18n={"en": "Party's Hideout"}, descriptions_i18n={}, type=LocationType.CAVE)
        player_in_db = Player(id=4, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=None, current_location_id=self.player_location.id, selected_language="en")
        self.mock_player_crud.get_by_discord_id.return_value = player_in_db

        target_party = Party(id=105, guild_id=self.guild.id, name="FarAwayParty", player_ids_json=[], current_location_id=different_loc.id)
        self.mock_party_crud.get_by_name.return_value = target_party

        # Corrected side_effect for add_player_to_party_json
        async def mock_add_player_side_effect(session, party, player_id):
            if party.player_ids_json is None:
                party.player_ids_json = []
            if player_id not in party.player_ids_json:
                party.player_ids_json.append(player_id)
            # Simulate refresh or ensure the test uses the modified party object correctly
            return party
        self.mock_party_crud.add_player_to_party_json.side_effect = mock_add_player_side_effect

        self.mock_location_crud.get.return_value = different_loc # For fetching location name

        await self.cog.party_join.callback(self.cog, self.ctx, party_identifier="FarAwayParty")

        self.assertEqual(player_in_db.current_location_id, different_loc.id) # Player moved
        self.ctx.send.assert_called_once_with(f"{self.author.mention} успешно присоединился к группе 'FarAwayParty'! Текущая локация группы: Party's Hideout.")


if __name__ == '__main__':
    unittest.main()
