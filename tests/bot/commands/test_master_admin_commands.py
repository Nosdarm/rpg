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
        # self.patcher_is_admin = patch('src.bot.commands.master_ai_commands.is_administrator', return_value=lambda func: func)
        # self.mock_is_admin_check = self.patcher_is_admin.start()
        # No longer needed as we rely on default_permissions on the group

    async def asyncTearDown(self):
        # self.patcher_is_admin.stop()
        pass # Nothing to stop if nothing started in setUp specifically for all tests

    async def test_ping_command(self):
        """Test the /master_admin ping command."""
        mock_interaction = create_mock_interaction(guild_id=123) # Use helper

        await self.cog.ping_command.callback(self.cog, mock_interaction) # Call with cog instance and interaction

        mock_interaction.response.send_message.assert_called_once_with(
            f"Pong! Master Admin Cog is active in guild {mock_interaction.guild_id}.",
            ephemeral=True
        )

    @patch('src.bot.commands.master_admin_commands.get_db_session')
    @patch('src.bot.commands.master_admin_commands.player_crud')
    @patch('src.bot.commands.master_admin_commands.get_localized_message_template')
    async def test_player_view_found(self, mock_get_loc_msg, mock_player_crud, mock_get_session):
        mock_interaction = create_mock_interaction()
        mock_session_instance = AsyncMock()
        mock_get_session.return_value.__aenter__.return_value = mock_session_instance

        mock_player = Player(id=1, discord_id=789, guild_id=123, name="TestPlayer", level=5, xp=100, unspent_xp=2, current_status=PlayerStatus.EXPLORING, language="en", attributes_json={"str":10})
        mock_player_crud.get_by_id_and_guild = AsyncMock(return_value=mock_player)

        # General side effect for localization that formats the default template with provided kwargs
        mock_get_loc_msg.side_effect = lambda session, guild_id, key, lang_code, default_template, **kwargs: default_template.format(**kwargs)

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
        # Ensure the side_effect can handle the kwargs passed by the actual code
        mock_get_loc_msg.side_effect = lambda session, guild_id, key, lang_code, default_template, **kwargs: default_template.format(**kwargs)

        await self.cog.player_view.callback(self.cog, mock_interaction, player_id=1)

        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        # The actual key used in player_view is "player_view:not_found"
        # The default template is "Player with ID {player_id} not found in this guild."
        expected_message = "Player with ID 1 not found in this guild."
        mock_interaction.followup.send.assert_called_once_with(
            expected_message,
            ephemeral=True
        )

    @patch('src.bot.commands.master_admin_commands.get_db_session')
    @patch('src.bot.commands.master_admin_commands.update_rule_config')
    @patch('src.bot.commands.master_admin_commands.get_localized_message_template')
    async def test_ruleconfig_set_success(self, mock_get_loc_msg, mock_update_rule, mock_get_session):
        mock_interaction = create_mock_interaction()
        mock_session_instance = AsyncMock()
        mock_get_session.return_value.__aenter__.return_value = mock_session_instance

        mock_updated_rule = RuleConfig(guild_id=123, key="test_key", value_json={"data": "new_value"})
        mock_update_rule.return_value = mock_updated_rule

        mock_get_loc_msg.side_effect = lambda session, guild_id, key, lang_code, default_template, **kwargs: default_template.format(**kwargs)

        key_to_set = "my_rule"
        value_json_str = '{"value": 123, "enabled": true}'

        await self.cog.ruleconfig_set.callback(self.cog, mock_interaction, key=key_to_set, value_json=value_json_str)

        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        mock_update_rule.assert_called_once_with(mock_session_instance, guild_id=123, key=key_to_set, value={"value": 123, "enabled": True})
        # Default template for "ruleconfig_set:success" is "RuleConfig '{key_name}' has been set/updated successfully."
        expected_message = f"RuleConfig '{key_to_set}' has been set/updated successfully."
        mock_interaction.followup.send.assert_called_once_with(
            expected_message, ephemeral=True
        )

    @patch('src.bot.commands.master_admin_commands.get_db_session')
    @patch('src.bot.commands.master_admin_commands.get_localized_message_template')
    async def test_ruleconfig_set_invalid_json(self, mock_get_loc_msg, mock_get_session):
        mock_interaction = create_mock_interaction()
        mock_session_instance = AsyncMock() # This session is for the error message localization
        mock_get_session.return_value.__aenter__.return_value = mock_session_instance

        mock_get_loc_msg.side_effect = lambda session, guild_id, key, lang_code, default_template, **kwargs: default_template.format(**kwargs)

        key_to_set = "my_rule"
        invalid_value_json_str = '{"value": 123, "enabled": true' # Missing closing brace

        await self.cog.ruleconfig_set.callback(self.cog, mock_interaction, key=key_to_set, value_json=invalid_value_json_str)

        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        # Default template for "ruleconfig_set:error_invalid_json" is "Invalid JSON string provided for value: {json_string}"
        expected_message = f"Invalid JSON string provided for value: {invalid_value_json_str}"
        mock_interaction.followup.send.assert_called_once_with(
            expected_message, ephemeral=True
        )

    # TODO: Add tests for player_list, player_update, other ruleconfig commands, and conflict commands.
    # For player_update, test valid field updates, invalid field names, type conversion errors.
    # For conflict_resolve, test valid status, invalid status, conflict not found, conflict not pending.

if __name__ == '__main__':
    unittest.main()
