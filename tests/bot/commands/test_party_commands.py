import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call # Added call
from sqlalchemy.ext.asyncio import AsyncSession # Added AsyncSession

# Add the project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import discord # type: ignore
from discord.ext import commands # type: ignore
from typing import Optional # Added Optional

from backend.bot.commands.party_commands import PartyCog
from backend.models.player import Player, PlayerStatus
from backend.models.party import Party, PartyTurnStatus
from backend.models.location import Location, LocationType

# Моки для discord.py объектов
class MockGuild:
    def __init__(self, id):
        self.id = id

class MockAuthor(discord.User): # Наследуемся от discord.User для type hints
    def __init__(self, id, name, display_name=None):
        user_data = {'id': str(id), 'username': name, 'discriminator': '0000', 'avatar': None}
        if display_name:
            user_data['global_name'] = display_name
        super().__init__(state=MagicMock(), data=user_data) # type: ignore
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
        self.patcher_get_db_session = patch('backend.bot.commands.party_commands.get_db_session')
        self.mock_get_db_session = self.patcher_get_db_session.start()
        self.mock_get_db_session.return_value.__aenter__.return_value = self.session_mock

        self.patcher_player_crud = patch('backend.bot.commands.party_commands.player_crud', new_callable=AsyncMock)
        self.mock_player_crud = self.patcher_player_crud.start()

        self.patcher_party_crud = patch('backend.bot.commands.party_commands.party_crud', new_callable=AsyncMock)
        self.mock_party_crud = self.patcher_party_crud.start()

        self.patcher_location_crud = patch('backend.bot.commands.party_commands.location_crud', new_callable=AsyncMock)
        self.mock_location_crud = self.patcher_location_crud.start()

        # Patch get_rule
        self.patcher_get_rule = patch('backend.bot.commands.party_commands.get_rule', new_callable=AsyncMock)
        self.mock_get_rule = self.patcher_get_rule.start()

        self.patcher_get_localized_text = patch('backend.bot.commands.party_commands.get_localized_text')
        self.mock_get_localized_text = self.patcher_get_localized_text.start()

        # Mock get_localized_text for party_commands (must be synchronous)
        def mock_get_loc_text_for_party_sync(*args, **kwargs):
            i18n_data = kwargs.get('i18n_dict') # Corrected kwarg name
            language = kwargs.get('language', 'en')
            default_lang = kwargs.get('default_lang', 'en')

            if i18n_data is not None and isinstance(i18n_data, dict):
                name = i18n_data.get(language)
                if name:
                    return name
                name = i18n_data.get(default_lang)
                if name:
                    return name
                # Fallback if no specific language match, try 'en' or first available from dict
                # or a very specific default if dict is empty or value is not string
                for val in i18n_data.values(): # Ensure there's at least one string value
                    if isinstance(val, str):
                        return i18n_data.get("en", next(iter(i18n_data.values())))
                return "Location Name Missing From i18n_dict Values"


            # Fallback to key/default_text logic if i18n_dict not primary source or not suitable
            key = kwargs.get('key')
            default_text = kwargs.get('default_text')
            format_kwargs_actual = kwargs.get('format_kwargs', {})

            final_text_template = default_text if default_text is not None else key
            if final_text_template is None:
                return "Mocked Text (No Key/Default/i18n_dict)"

            if format_kwargs_actual and isinstance(final_text_template, str):
                try:
                    return final_text_template.format(**format_kwargs_actual)
                except KeyError:
                    return final_text_template # Return unformatted if keys missing
            return str(final_text_template) # Ensure string return

        self.mock_get_localized_text.side_effect = mock_get_loc_text_for_party_sync

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
        self.patcher_get_rule.stop()

    async def test_party_create_success(self):
        player_in_db = Player(id=1, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=None, current_location_id=self.player_location.id)
        self.mock_player_crud.get_by_discord_id.return_value = player_in_db

        # Mock RuleConfig values for validation
        self.mock_get_rule.side_effect = lambda session, guild_id, key, default: {
            "party:name_validation_regex": "^[a-zA-Z0-9\\s'-_]{3,32}$",
            "party:name_max_length": 32
        }.get(key, default)

        # Mock party_crud.get_by_name for uniqueness check
        self.mock_party_crud.get_by_name.return_value = None

        created_party = Party(id=100, guild_id=self.guild.id, name="Cool Adventurers", player_ids_json=[player_in_db.id], current_location_id=player_in_db.current_location_id)
        self.mock_party_crud.create.return_value = created_party

        await self.cog.party_create.callback(self.cog, self.ctx, party_name="Cool Adventurers") # type: ignore

        self.mock_party_crud.get_by_name.assert_called_once_with(self.session_mock, name="Cool Adventurers", guild_id=self.guild.id)
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

        await self.cog.party_create.callback(self.cog, self.ctx, party_name="New Party") # type: ignore

        self.mock_party_crud.create.assert_not_called()
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, ты уже состоишь в группе 'Old Party'. Сначала покинь ее.")

    async def test_party_create_name_fails_regex(self):
        player_in_db = Player(id=1, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=None)
        self.mock_player_crud.get_by_discord_id.return_value = player_in_db
        self.mock_get_rule.side_effect = lambda session, guild_id, key, default: {
            "party:name_validation_regex": "^[a-zA-Z0-9]{3,5}$", # Strict regex: only letters/numbers, 3-5 chars
            "party:name_max_length": 5
        }.get(key, default)
        self.mock_party_crud.get_by_name.return_value = None

        await self.cog.party_create.callback(self.cog, self.ctx, party_name="Invalid Name!") # type: ignore

        self.ctx.send.assert_called_once_with(f"{self.author.mention}, название группы содержит недопустимые символы или не соответствует требованиям по длине (3-32 символа, буквы, цифры, пробелы, дефисы, апострофы).")
        self.mock_party_crud.create.assert_not_called()

    async def test_party_create_name_too_long(self):
        player_in_db = Player(id=1, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=None)
        self.mock_player_crud.get_by_discord_id.return_value = player_in_db
        self.mock_get_rule.side_effect = lambda session, guild_id, key, default: {
            "party:name_validation_regex": "^[a-zA-Z0-9\\s'-_]{3,10}$",
            "party:name_max_length": 10
        }.get(key, default)
        self.mock_party_crud.get_by_name.return_value = None

        await self.cog.party_create.callback(self.cog, self.ctx, party_name="This Name Is Way Too Long") # type: ignore

        self.ctx.send.assert_called_once_with(f"{self.author.mention}, название группы слишком длинное (максимум 10 символов).")
        self.mock_party_crud.create.assert_not_called()

    async def test_party_create_name_not_unique(self):
        player_in_db = Player(id=1, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=None)
        self.mock_player_crud.get_by_discord_id.return_value = player_in_db
        self.mock_get_rule.side_effect = lambda session, guild_id, key, default: {
            "party:name_validation_regex": "^[a-zA-Z0-9\\s'-_]{3,32}$",
            "party:name_max_length": 32
        }.get(key, default)

        existing_party = Party(id=200, name="Taken Name")
        self.mock_party_crud.get_by_name.return_value = existing_party # Name is taken

        await self.cog.party_create.callback(self.cog, self.ctx, party_name="Taken Name") # type: ignore

        self.ctx.send.assert_called_once_with(f"{self.author.mention}, группа с названием 'Taken Name' уже существует. Пожалуйста, выбери другое название.")
        self.mock_party_crud.create.assert_not_called()

    async def test_party_leave_empties_party_and_disbands(self): # Renamed for clarity
        party_to_leave = Party(id=102, guild_id=self.guild.id, name="Solo Group", player_ids_json=[1], leader_player_id=1)
        player_in_db = Player(id=1, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=party_to_leave.id)

        self.mock_player_crud.get_by_discord_id.return_value = player_in_db
        self.mock_party_crud.get.return_value = party_to_leave

        # Mock remove_player_from_party_json to simulate party becoming empty
        async def mock_remove_player(session, party, player_id):
            party.player_ids_json = []
            return party
        self.mock_party_crud.remove_player_from_party_json.side_effect = mock_remove_player

        # Mock get_rule for disband policies (though not strictly needed if party becomes empty)
        self.mock_get_rule.side_effect = lambda session, guild_id, key, default: default # Return defaults

        await self.cog.party_leave.callback(self.cog, self.ctx) # type: ignore

        self.mock_party_crud.remove_player_from_party_json.assert_called_once_with(self.session_mock, party=party_to_leave, player_id=player_in_db.id)
        self.assertIsNone(player_in_db.current_party_id)
        self.mock_party_crud.delete.assert_called_once_with(self.session_mock, id=party_to_leave.id, guild_id=self.guild.id)
        self.session_mock.commit.assert_called_once()
        self.ctx.send.assert_called_once_with(f"{self.author.mention} покинул группу 'Solo Group'. Группа была распущена.") # Message changed slightly in SUT

    async def test_party_disband_success(self):
        # self.author.id is 321
        party_to_disband = Party(id=103, guild_id=self.guild.id, name="To Be Disbanded", leader_player_id=self.author.id, player_ids_json=[self.author.id, 2])
        leader_player = Player(id=self.author.id, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=party_to_disband.id)
        member2 = Player(id=2, discord_id=999, guild_id=self.guild.id, name="Member2", current_party_id=party_to_disband.id)

        self.mock_player_crud.get_by_discord_id.return_value = leader_player # The one issuing command is the leader
        self.mock_party_crud.get.return_value = party_to_disband

        # Mock player_crud.get to return members when updating their current_party_id
        def get_player_side_effect(session, id, guild_id=None): # Adjusted signature to match potential calls
            if id == self.author.id: return leader_player
            if id == 2: return member2
            return None
        self.mock_player_crud.get.side_effect = get_player_side_effect

        # Mock get_rule just in case (though not directly used by this part of disband logic)
        self.mock_get_rule.side_effect = lambda session, guild_id, key, default: default

        await self.cog.party_disband.callback(self.cog, self.ctx) # type: ignore

        self.mock_party_crud.delete.assert_called_once_with(self.session_mock, id=party_to_disband.id, guild_id=self.guild.id)

        # Check player updates
        self.assertEqual(self.session_mock.merge.call_count, 2) # For player_in_db and member2
        self.assertIsNone(player_in_db.current_party_id)
        self.assertIsNone(member2.current_party_id)

        self.session_mock.commit.assert_called_once()
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, группа 'To Be Disbanded' была успешно распущена. Все участники покинули группу.")

    async def test_party_leave_leader_leaves_promote_new_leader(self):
        member_to_promote_id = 2
        # Initial party: author (leader, id=321), member_to_promote (id=2), another_member (id=3)
        party_obj = Party(id=103, guild_id=self.guild.id, name="Council of Three", leader_player_id=self.author.id, player_ids_json=[self.author.id, member_to_promote_id, 3])
        leader_player = Player(id=self.author.id, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=party_obj.id)

        self.mock_player_crud.get_by_discord_id.return_value = leader_player
        self.mock_party_crud.get.return_value = party_obj

        # Simulate removing the leader (self.author.id)
        async def mock_remove_player(session, party, player_id):
            if player_id == self.author.id and player_id in party.player_ids_json:
                party.player_ids_json.remove(player_id) # Remaining: [member_to_promote_id, 3]
            return party
        self.mock_party_crud.remove_player_from_party_json.side_effect = mock_remove_player

        self.mock_get_rule.side_effect = lambda session, guild_id, key, default: {
            "party:leader_transfer_policy": "promote_oldest_member", # Simplifies to picking first from remaining
            "party:auto_disband_threshold": 1 # Won't disband as 2 members remain
        }.get(key, default)

        await self.cog.party_leave.callback(self.cog, self.ctx)

        self.assertIsNone(leader_player.current_party_id)
        self.assertEqual(party_obj.leader_player_id, member_to_promote_id) # New leader promoted
        self.mock_party_crud.delete.assert_not_called() # Party should not be deleted

        # Check that player and party were added to session for update
        calls = [call(leader_player), call(party_obj)]
        self.session_mock.merge.assert_has_calls(calls, any_order=True)

        self.ctx.send.assert_called_once_with(f"{self.author.mention} покинул группу 'Council of Three'.")

    async def test_party_leave_leader_leaves_policy_disband_on_leave(self):
        member_remaining_id = 2
        party_obj = Party(id=104, guild_id=self.guild.id, name="Fragile Alliance", leader_player_id=self.author.id, player_ids_json=[self.author.id, member_remaining_id])
        leader_player = Player(id=self.author.id, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=party_obj.id)

        self.mock_player_crud.get_by_discord_id.return_value = leader_player
        self.mock_party_crud.get.return_value = party_obj

        async def mock_remove_player(session, party, player_id):
            if player_id == self.author.id and player_id in party.player_ids_json:
                party.player_ids_json.remove(player_id)
            return party
        self.mock_party_crud.remove_player_from_party_json.side_effect = mock_remove_player

        self.mock_get_rule.side_effect = lambda session, guild_id, key, default: {
            "party:leader_transfer_policy": "disband_on_leader_leave", # Explicit disband
            "party:auto_disband_threshold": 1
        }.get(key, default)

        await self.cog.party_leave.callback(self.cog, self.ctx)

        self.assertIsNone(leader_player.current_party_id)
        self.mock_party_crud.delete.assert_called_once_with(self.session_mock, id=party_obj.id, guild_id=self.guild.id)
        self.ctx.send.assert_called_once_with(f"{self.author.mention} покинул группу 'Fragile Alliance'. Группа была распущена.")

    async def test_party_leave_member_leaves_below_threshold_disband(self):
        leader_id = 1 # Some other player is leader
        # self.author.id is 321
        party_obj = Party(id=105, guild_id=self.guild.id, name="Small Squad", leader_player_id=leader_id, player_ids_json=[leader_id, self.author.id])
        leaving_player = Player(id=self.author.id, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=party_obj.id)

        self.mock_player_crud.get_by_discord_id.return_value = leaving_player
        self.mock_party_crud.get.return_value = party_obj

        async def mock_remove_player(session, party, player_id):
            if player_id == self.author.id and player_id in party.player_ids_json:
                party.player_ids_json.remove(player_id) # Now only leader_id (1) remains
            return party
        self.mock_party_crud.remove_player_from_party_json.side_effect = mock_remove_player

        self.mock_get_rule.side_effect = lambda session, guild_id, key, default: {
            "party:leader_transfer_policy": "disband_if_empty_else_promote", # Not relevant as non-leader leaves
            "party:auto_disband_threshold": 2 # Disband if < 2 members (i.e. if 1 member remains)
        }.get(key, default)

        await self.cog.party_leave.callback(self.cog, self.ctx)

        self.assertIsNone(leaving_player.current_party_id)
        self.mock_party_crud.delete.assert_called_once_with(self.session_mock, id=party_obj.id, guild_id=self.guild.id)
        self.ctx.send.assert_called_once_with(f"{self.author.mention} покинул группу 'Small Squad'. Группа была распущена.")

    async def test_party_disband_fails_if_not_leader(self):
        other_leader_id = 99
        party_obj = Party(id=106, guild_id=self.guild.id, name="Leader's Party", leader_player_id=other_leader_id, player_ids_json=[other_leader_id, self.author.id])
        # self.author is a member, but not the leader
        member_player = Player(id=self.author.id, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=party_obj.id)

        self.mock_player_crud.get_by_discord_id.return_value = member_player
        self.mock_party_crud.get.return_value = party_obj

        # Mock get_rule just in case (though not directly used by this part of disband logic)
        self.mock_get_rule.side_effect = lambda session, guild_id, key, default: default

        await self.cog.party_disband.callback(self.cog, self.ctx)

        self.mock_party_crud.delete.assert_not_called() # Party should not be deleted
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, только лидер группы может ее распустить.")

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

        await self.cog.party_join.callback(self.cog, self.ctx, party_identifier="Joinable Party") # type: ignore

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

        await self.cog.party_join.callback(self.cog, self.ctx, party_identifier="FarAwayParty") # type: ignore

        self.assertEqual(player_in_db.current_location_id, different_loc.id) # Player moved
        self.ctx.send.assert_called_once_with(f"{self.author.mention} успешно присоединился к группе 'FarAwayParty'! Текущая локация группы: Party's Hideout.")

    async def test_party_join_fails_party_full(self):
        player_in_db = Player(id=5, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=None)
        self.mock_player_crud.get_by_discord_id.return_value = player_in_db

        # Party is already full (e.g., 1 member, max size 1)
        target_party = Party(id=106, guild_id=self.guild.id, name="Full Party", player_ids_json=[99], current_location_id=self.player_location.id)
        self.mock_party_crud.get_by_name.return_value = target_party

        self.mock_get_rule.side_effect = lambda session, guild_id, key, default: \
            1 if key == "party:max_size" else \
            "open" if key == "party:default_invite_policy" else \
            1 if key == "party:default_min_level_req" else default

        await self.cog.party_join.callback(self.cog, self.ctx, party_identifier="Full Party")

        self.mock_party_crud.add_player_to_party_json.assert_not_called()
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, группа 'Full Party' уже заполнена (максимум 1 участников).")

    async def test_party_join_fails_invite_only(self):
        player_in_db = Player(id=6, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=None)
        self.mock_player_crud.get_by_discord_id.return_value = player_in_db

        target_party = Party(id=107, guild_id=self.guild.id, name="Exclusive Club", player_ids_json=[], properties_json={"invite_policy": "invite_only"})
        self.mock_party_crud.get_by_name.return_value = target_party

        self.mock_get_rule.side_effect = lambda session, guild_id, key, default: \
            5 if key == "party:max_size" else \
            "open" if key == "party:default_invite_policy" else \
            1 if key == "party:default_min_level_req" else default # default_invite_policy won't be used due to party property

        await self.cog.party_join.callback(self.cog, self.ctx, party_identifier="Exclusive Club")

        self.mock_party_crud.add_player_to_party_json.assert_not_called()
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, для вступления в группу 'Exclusive Club' требуется приглашение.")

    async def test_party_join_fails_level_too_low(self):
        player_in_db = Player(id=7, discord_id=self.author.id, guild_id=self.guild.id, name=self.author.name, current_party_id=None, level=1) # Player is level 1
        self.mock_player_crud.get_by_discord_id.return_value = player_in_db

        target_party = Party(id=108, guild_id=self.guild.id, name="Elite Squad", player_ids_json=[], properties_json={"min_level_req": 5})
        self.mock_party_crud.get_by_name.return_value = target_party

        self.mock_get_rule.side_effect = lambda session, guild_id, key, default: \
            5 if key == "party:max_size" else \
            "open" if key == "party:default_invite_policy" else \
            1 if key == "party:default_min_level_req" else default # default_min_level_req won't be used

        await self.cog.party_join.callback(self.cog, self.ctx, party_identifier="Elite Squad")

        self.mock_party_crud.add_player_to_party_json.assert_not_called()
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, твой уровень (1) слишком низок для вступления в группу 'Elite Squad'. Требуемый уровень: 5.")


if __name__ == '__main__':
    unittest.main()
