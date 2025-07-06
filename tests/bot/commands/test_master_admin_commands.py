import unittest
from unittest.mock import AsyncMock, MagicMock, patch, ANY

import discord # type: ignore
from discord import app_commands # type: ignore
from discord.ext import commands as discord_commands # type: ignore

from src.bot.commands.master_admin_commands import MasterAdminCog
from src.models import Player, RuleConfig, PendingConflict # Import models used by commands
from src.models.enums import PlayerStatus, ConflictStatus # Import enums

# Helper to create a mock Interaction object
def create_mock_interaction(guild_id: int = 123, user_id: int = 456, locale_str: str = "en-US"):
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = guild_id
    interaction.user = MagicMock(spec=discord.User)
    interaction.user.id = user_id
    interaction.client = MagicMock(spec=discord_commands.Bot) # Mock bot/client attached to interaction

    # Mock locale
    # discord.Locale can be one of the predefined ones or a custom string
    # For simplicity, we'll mock its string representation directly if that's what our code uses
    interaction.locale = MagicMock(spec=discord.Locale)
    interaction.locale.__str__ = MagicMock(return_value=locale_str) # Make str(interaction.locale) work

    interaction.response = AsyncMock(spec=discord.InteractionResponse)
    interaction.followup = AsyncMock(spec=discord.Webhook)
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction

class TestMasterAdminCog(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.bot = AsyncMock(spec=discord_commands.Bot)
        self.cog = MasterAdminCog(self.bot)
        # Mock the is_administrator check to always return True for these tests
        # This is important if the decorator itself isn't being tested here.
        self.patcher_is_admin = patch('src.bot.commands.master_ai_commands.is_administrator', return_value=lambda func: func)
        self.mock_is_admin_check = self.patcher_is_admin.start()

        # It's often better to patch specific dependencies within each test method
        # or use a more targetted patch for the decorator if its logic needs to be bypassed for all tests in this class.
        # For now, this broad approach simplifies bypassing the permission check for command logic testing.

    async def asyncTearDown(self):
        self.patcher_is_admin.stop()

    @patch('src.bot.commands.master_admin_commands.get_db_session')
    @patch('src.bot.commands.master_admin_commands.player_crud')
    @patch('src.bot.commands.master_admin_commands.get_localized_message_template')
    async def test_player_view_found(self, mock_get_loc_msg, mock_player_crud, mock_get_session):
        mock_interaction = create_mock_interaction()

        mock_session_instance = AsyncMock()
        mock_get_session.return_value.__aenter__.return_value = mock_session_instance # For async with

        mock_player = Player(id=1, discord_id=789, guild_id=123, name="TestPlayer", level=5, xp=100, unspent_xp=2, current_status=PlayerStatus.EXPLORING, language="en")
        mock_player_crud.get_by_id_and_guild = AsyncMock(return_value=mock_player)

        mock_get_loc_msg.side_effect = lambda s, gid, key, lc, default: default # Simple mock for localization

        await self.cog.player_view.callback(self.cog, mock_interaction, player_id=1)

        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_player_crud.get_by_id_and_guild.assert_called_once_with(mock_session_instance, id=1, guild_id=123)
        mock_interaction.followup.send.assert_called_once()

        # Check embed details (simplified)
        args, kwargs = mock_interaction.followup.send.call_args
        self.assertIn('embed', kwargs)
        embed = kwargs['embed']
        self.assertEqual(embed.title, "Player Details: TestPlayer (ID: 1)") # Assuming default template used
        self.assertTrue(any(field.name == "Discord ID" and field.value == "789" for field in embed.fields))

    @patch('src.bot.commands.master_admin_commands.get_db_session')
    @patch('src.bot.commands.master_admin_commands.player_crud')
    @patch('src.bot.commands.master_admin_commands.get_localized_message_template')
    async def test_player_view_not_found(self, mock_get_loc_msg, mock_player_crud, mock_get_session):
        mock_interaction = create_mock_interaction()
        mock_session_instance = AsyncMock()
        mock_get_session.return_value.__aenter__.return_value = mock_session_instance

        mock_player_crud.get_by_id_and_guild = AsyncMock(return_value=None)
        mock_get_loc_msg.side_effect = lambda s, gid, key, lc, default: default.format(player_id=1)


        await self.cog.player_view.callback(self.cog, mock_interaction, player_id=1)

        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_interaction.followup.send.assert_called_once_with(
            "Player with ID 1 not found in this guild.", # Assuming default template
            ephemeral=True
        )

    @patch('src.bot.commands.master_admin_commands.get_db_session')
    @patch('src.bot.commands.master_admin_commands.update_rule_config') # Patching the core function
    async def test_ruleconfig_set_success(self, mock_update_rule, mock_get_session):
        mock_interaction = create_mock_interaction()
        mock_session_instance = AsyncMock()
        mock_get_session.return_value.__aenter__.return_value = mock_session_instance

        mock_updated_rule = RuleConfig(guild_id=123, key="test_key", value_json={"data": "new_value"})
        mock_update_rule.return_value = mock_updated_rule # update_rule_config returns the RuleConfig object

        key_to_set = "my_rule"
        value_json_str = '{"value": 123, "enabled": true}'

        await self.cog.ruleconfig_set.callback(self.cog, mock_interaction, key=key_to_set, value_json=value_json_str)

        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_update_rule.assert_called_once_with(mock_session_instance, guild_id=123, key=key_to_set, value={"value": 123, "enabled": True})
        mock_interaction.followup.send.assert_called_once_with(
            f"RuleConfig '{key_to_set}' has been set/updated successfully.", ephemeral=True
        )

    @patch('src.bot.commands.master_admin_commands.get_db_session')
    async def test_ruleconfig_set_invalid_json(self, mock_get_session):
        mock_interaction = create_mock_interaction()
        # No need to mock session instance if JSON parsing fails before DB interaction

        key_to_set = "my_rule"
        invalid_value_json_str = '{"value": 123, "enabled": true' # Missing closing brace

        await self.cog.ruleconfig_set.callback(self.cog, mock_interaction, key=key_to_set, value_json=invalid_value_json_str)

        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_interaction.followup.send.assert_called_once_with(
            f"Invalid JSON string provided for value: {invalid_value_json_str}", ephemeral=True
        )

    # TODO: Add tests for player_list, player_update, other ruleconfig commands, and conflict commands.
    # For player_update, test valid field updates, invalid field names, type conversion errors.
    # For conflict_resolve, test valid status, invalid status, conflict not found, conflict not pending.

if __name__ == '__main__':
    unittest.main()
