import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord.ext import commands # Added import
from sqlalchemy.ext.asyncio import AsyncSession # Added for type hinting

from src.bot.commands.master_commands.monitoring_master_commands import MasterMonitoringCog
from src.models import StoryLog, EventType, Player, RuleConfig, Location, LocationType, GeneratedNpc, Party, GlobalNpc, MobileGroup
from src.models.enums import PlayerStatus # Assuming PlayerStatus is needed for player view
from src.core.crud.crud_story_log import story_log_crud
from src.core.crud.crud_rule_config import rule_config_crud
from src.core.crud.crud_location import location_crud
from src.core.crud.crud_player import player_crud
# Add other CRUDs if their models are directly returned and formatted in detail by commands being tested

# Helper to create a mock interaction object
def create_mock_interaction(guild_id: int, user_id: int, locale: str = "en") -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = guild_id
    interaction.user = MagicMock(spec=discord.User)
    interaction.user.id = user_id
    interaction.user.guild_permissions = MagicMock(spec=discord.Permissions)
    interaction.user.guild_permissions.administrator = True
    interaction.client = MagicMock(spec=discord.Client) # Needed for ensure_guild_configured_and_get_session
    interaction.client.user = MagicMock(spec=discord.ClientUser)
    # interaction.locale = discord.Locale(locale) # This was causing errors
    mock_locale = MagicMock(spec=discord.Locale)
    mock_locale.__str__ = MagicMock(return_value=locale)
    interaction.locale = mock_locale
    interaction.response = MagicMock(spec=discord.InteractionResponse)
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock(spec=discord.Webhook)
    interaction.followup.send = AsyncMock()
    return interaction

class TestMasterMonitoringCog(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.bot_mock = AsyncMock(spec=commands.Bot)
        self.cog = MasterMonitoringCog(self.bot_mock)

        # Mock ensure_guild_configured_and_get_session to avoid DB dependency in most tests
        self.mock_session = AsyncMock(spec=AsyncSession) # Added spec
        self.mock_master_player = MagicMock(spec=Player)

        # Configure the mock_session.execute behavior
        mock_execute_result = AsyncMock()

        mock_scalars_obj = MagicMock()
        mock_scalars_obj.all.return_value = [] # Default: no rules found
        mock_scalars_obj.one_or_none.return_value = None # Default for scalar_one_or_none

        mock_execute_result.scalars.return_value = mock_scalars_obj
        mock_execute_result.scalar_one_or_none.return_value = None # For direct scalar results from execute

        self.mock_session.execute.return_value = mock_execute_result

        self.patch_ensure_guild = patch(
            "src.bot.commands.master_commands.monitoring_master_commands.ensure_guild_configured_and_get_session",
            return_value=(self.mock_master_player, self.mock_session)
        )
        self.mock_ensure_guild_func = self.patch_ensure_guild.start()

        # Mock localization utils
        self.patch_get_localized_text = patch(
            "src.bot.commands.master_commands.monitoring_master_commands.get_localized_text",
            side_effect=lambda key, locale, params=None: f"loc_{key}" + (f"_{params}" if params else "")
        )
        self.mock_get_localized_text_func = self.patch_get_localized_text.start()

        discord.utils.format_dt = MagicMock(side_effect=lambda dt, style='f': f"[Formatted DT: {dt}]")


    async def asyncTearDown(self):
        self.patch_ensure_guild.stop()
        self.patch_get_localized_text.stop()
        patch.stopall() # Stops any other patches if necessary


    @patch("src.bot.commands.master_commands.monitoring_master_commands.story_log_crud.get", new_callable=AsyncMock)
    async def test_log_view_found(self, mock_story_log_get):
        interaction = create_mock_interaction(guild_id=1, user_id=100)
        log_id_to_view = 123

        mock_log_entry = MagicMock(spec=StoryLog)
        mock_log_entry.id = log_id_to_view
        mock_log_entry.event_type = EventType.PLAYER_ACTION # Enum member
        mock_log_entry.timestamp = discord.utils.utcnow()
        mock_log_entry.location_id = 10
        mock_log_entry.turn_number = 5
        mock_log_entry.details_json = {"action": "test"}
        mock_log_entry.entity_ids_json = {"player_ids": [1]}
        mock_log_entry.narrative_i18n = {"en": "Test narrative"}

        mock_story_log_get.return_value = mock_log_entry

        await self.cog.log_view.callback(self.cog, interaction, log_id=log_id_to_view) # type: ignore[call-arg]

        interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_story_log_get.assert_called_once_with(self.mock_session, id=log_id_to_view, guild_id=interaction.guild_id)
        interaction.followup.send.assert_called_once()

        # Check embed contents (simplified)
        sent_embed = interaction.followup.send.call_args[1]['embed']
        self.assertIn(str(log_id_to_view), sent_embed.title)
        self.assertEqual(len(sent_embed.fields), 6) # Based on current implementation for a full entry
        self.assertEqual(sent_embed.fields[0].value, EventType.PLAYER_ACTION.value)

    @patch("src.bot.commands.master_commands.monitoring_master_commands.story_log_crud.get", new_callable=AsyncMock)
    async def test_log_view_not_found(self, mock_story_log_get):
        interaction = create_mock_interaction(guild_id=1, user_id=100)
        log_id_to_view = 404
        mock_story_log_get.return_value = None

        await self.cog.log_view.callback(self.cog, interaction, log_id=log_id_to_view) # type: ignore[call-arg]

        interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_story_log_get.assert_called_once_with(self.mock_session, id=log_id_to_view, guild_id=interaction.guild_id)
        interaction.followup.send.assert_called_once_with(f"loc_master_monitor.log_view.not_found_{{'log_id': {log_id_to_view}}}", ephemeral=True)

    @patch("src.bot.commands.master_commands.monitoring_master_commands.story_log_crud.count_by_guild_with_filters", new_callable=AsyncMock)
    @patch("src.bot.commands.master_commands.monitoring_master_commands.story_log_crud.get_multi_by_guild_with_filters", new_callable=AsyncMock)
    async def test_log_list_success(self, mock_get_multi, mock_count):
        interaction = create_mock_interaction(guild_id=1, user_id=100)
        page, limit = 1, 5

        mock_count.return_value = 2
        mock_log_entries = [MagicMock(spec=StoryLog, id=i, event_type=EventType.SYSTEM_EVENT, timestamp=discord.utils.utcnow(), details_json={"msg":f"Entry {i}"}) for i in range(1,3)]
        mock_get_multi.return_value = mock_log_entries

        await self.cog.log_list.callback(self.cog, interaction, page=page, limit=limit, event_type_filter=None) # type: ignore[call-arg]

        interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_count.assert_called_once_with(self.mock_session, guild_id=interaction.guild_id, event_type=None)
        mock_get_multi.assert_called_once_with(self.mock_session, guild_id=interaction.guild_id, skip=0, limit=limit, event_type=None, descending=True)
        interaction.followup.send.assert_called_once()
        sent_embed = interaction.followup.send.call_args[1]['embed']
        self.assertIn("loc_master_monitor.log_list.embed_title", sent_embed.title)
        self.assertTrue(len(sent_embed.description.split("\n")) == 2) # Two entries
        self.assertIn("loc_master_monitor.log_list.footer_pagination_current", sent_embed.footer.text)


    @patch("src.bot.commands.master_commands.monitoring_master_commands.story_log_crud.count_by_guild_with_filters", new_callable=AsyncMock)
    @patch("src.bot.commands.master_commands.monitoring_master_commands.story_log_crud.get_multi_by_guild_with_filters", new_callable=AsyncMock)
    async def test_log_list_empty(self, mock_get_multi, mock_count):
        interaction = create_mock_interaction(guild_id=1, user_id=100)
        page, limit = 1, 5

        mock_count.return_value = 0
        mock_get_multi.return_value = []

        await self.cog.log_list.callback(self.cog, interaction, page=page, limit=limit, event_type_filter=None) # type: ignore[call-arg]

        interaction.followup.send.assert_called_once_with(f"loc_master_monitor.log_list.no_entries_{{'page': {page}}}", ephemeral=True)


    @patch("src.bot.commands.master_commands.monitoring_master_commands.rule_config_crud.get_by_key", new_callable=AsyncMock)
    async def test_worldstate_get_found(self, mock_rule_get_by_key):
        interaction = create_mock_interaction(guild_id=1, user_id=100)
        key_to_get = "worldstate:test_flag"

        mock_rule_entry = MagicMock(spec=RuleConfig)
        mock_rule_entry.key = key_to_get
        mock_rule_entry.value_json = {"value": True}
        mock_rule_entry.description = "A test flag"
        mock_rule_entry.updated_at = discord.utils.utcnow()
        mock_rule_get_by_key.return_value = mock_rule_entry

        await self.cog.worldstate_get.callback(self.cog, interaction, key=key_to_get) # type: ignore[call-arg]

        mock_rule_get_by_key.assert_called_once_with(self.mock_session, guild_id=interaction.guild_id, key=key_to_get)
        sent_embed = interaction.followup.send.call_args[1]['embed']
        self.assertIn(key_to_get, sent_embed.title)
        self.assertEqual(len(sent_embed.fields), 3)


    @patch("src.bot.commands.master_commands.monitoring_master_commands.location_crud.count", new_callable=AsyncMock) # Patched to .count
    @patch("src.bot.commands.master_commands.monitoring_master_commands.location_crud.get_multi", new_callable=AsyncMock) # Patched to .get_multi
    async def test_map_list_locations_success(self, mock_get_multi_loc, mock_count_loc):
        interaction = create_mock_interaction(guild_id=1, user_id=100)
        page, limit = 1, 2

        mock_count_loc.return_value = 1
        mock_loc_entry = MagicMock(spec=Location, id=1, static_id="loc1", name_i18n={"en":"Test Location"}, type=LocationType.TOWN)
        mock_get_multi_loc.return_value = [mock_loc_entry]

        await self.cog.map_list_locations.callback(self.cog, interaction, page=page, limit=limit) # type: ignore[call-arg]

        mock_count_loc.assert_called_once_with(self.mock_session, guild_id=interaction.guild_id)
        mock_get_multi_loc.assert_called_once_with(self.mock_session, guild_id=interaction.guild_id, skip=0, limit=limit)
        sent_embed = interaction.followup.send.call_args[1]['embed']
        self.assertIn("loc_master_monitor.map_list_locations.embed_title", sent_embed.title)
        self.assertTrue(len(sent_embed.description.split("\n")) == 1)


    @patch("src.bot.commands.master_commands.monitoring_master_commands.player_crud.get", new_callable=AsyncMock)
    @patch("src.bot.commands.master_commands.monitoring_master_commands.location_crud.get", new_callable=AsyncMock) # For player's location
    @patch("src.bot.commands.master_commands.monitoring_master_commands.party_crud.get", new_callable=AsyncMock) # For player's party
    async def test_entities_view_player_found(self, mock_party_get, mock_location_get, mock_player_get):
        interaction = create_mock_interaction(guild_id=1, user_id=100)
        player_id_to_view = 77

        mock_player = MagicMock(spec=Player)
        mock_player.id = player_id_to_view
        mock_player.name_i18n = {"en": "Test Player"}
        mock_player.description_i18n = {"en": "A brave adventurer."}
        mock_player.discord_user_id = "123456789012345678"
        mock_player.level = 5
        mock_player.xp = 1000
        mock_player.unspent_xp = 10
        mock_player.current_status = PlayerStatus.IDLE
        mock_player.location_id = 1
        mock_player.party_id = None # No party for simplicity
        mock_player.attributes_json = {"str": 12}
        mock_player.properties_json = {}
        mock_player.created_at = discord.utils.utcnow()
        mock_player.updated_at = discord.utils.utcnow()
        mock_player_get.return_value = mock_player

        mock_location = MagicMock(spec=Location, id=1, name_i18n={"en":"Player's Town"})
        mock_location_get.return_value = mock_location

        await self.cog.entities_view_player.callback(self.cog, interaction, player_id=player_id_to_view) # type: ignore[call-arg]

        mock_player_get.assert_called_once_with(self.mock_session, id=player_id_to_view, guild_id=interaction.guild_id)
        sent_embed = interaction.followup.send.call_args[1]['embed']
        self.assertIn("Test Player", sent_embed.title)
        self.assertTrue(len(sent_embed.fields) > 5) # Check for a reasonable number of fields

if __name__ == "__main__":
    unittest.main()
