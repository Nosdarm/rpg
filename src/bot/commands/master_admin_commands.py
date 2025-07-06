import logging
import json # Added for player_view and other JSON parsing
from typing import Dict, Any, Optional # Added for type hinting

import discord
from discord import app_commands
from discord.ext import commands

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession # Will be needed for localization function
import json # For some commands that handle JSON directly or display it
import logging

# from .master_ai_commands import is_administrator # Let's try to use default_permissions first

logger = logging.getLogger(__name__)

class MasterAdminCog(commands.Cog, name="Master Admin"): # Added name="Master Admin" for clarity in help
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterAdminCog initialized.")

    # Основная группа команд для Мастера
    # Set default_permissions here to apply to all commands in this group and its subgroups.
    master_admin = app_commands.Group(
        name="master_admin",
        description="Master GM commands for guild administration.",
        default_permissions=discord.Permissions(administrator=True), # Requires administrator permission
        guild_only=True
    )

    # Пример простой команды внутри группы
    @master_admin.command(name="ping", description="A simple ping command for the Master Admin cog.")
    # No specific permission decorator needed if default_permissions is set on the group
    async def ping_command(self, interaction: discord.Interaction):
        """Responds with pong, testing the cog and permissions."""
        # guild_only=True on the group handles the guild check implicitly
        # interaction.guild_id will be available.
        await interaction.response.send_message(f"Pong! Master Admin Cog is active in guild {interaction.guild_id}.", ephemeral=True)
        logger.debug(f"MasterAdminCog ping command executed by {interaction.user} in guild {interaction.guild_id}")

    # --- Player CRUD ---
    # parent=master_admin should inherit default_permissions
    player_group = app_commands.Group(name="player", description="Master commands for managing players.", parent=master_admin) # Corrected: parent was master_admin_group

    @player_group.command(name="view", description="View details of a specific player.")
    @app_commands.describe(player_id="The database ID of the player to view.")
    # No specific permission decorator needed
    async def player_view(self, interaction: discord.Interaction, player_id: int):
        await interaction.response.defer(ephemeral=True)
        # No need for guild_id check if group is guild_only=True
        # Removed:
        #     await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
        #     return

        from src.core.crud.crud_player import player_crud # Local import
        from src.core.database import get_db_session # Local import
        from src.core.localization_utils import get_localized_message_template # For localization

        async with get_db_session() as session:
            player = await player_crud.get_by_id_and_guild(session, id=player_id, guild_id=interaction.guild_id)
            lang_code = str(interaction.locale)

            if not player:
                not_found_msg_template = await get_localized_message_template(
                    session, interaction.guild_id, "player_view:not_found", lang_code,
                    "Player with ID {player_id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg_template.format(player_id=player_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "player_view:title", lang_code,
                "Player Details: {player_name} (ID: {player_id})"
            )
            embed_title = title_template.format(player_name=player.name, player_id=player.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.green())

            # Helper function for field names
            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"player_view:field_{key}", lang_code, default)

            embed.add_field(name=await get_label("discord_id", "Discord ID"), value=str(player.discord_id), inline=True)
            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(player.guild_id), inline=True)
            embed.add_field(name=await get_label("level", "Level"), value=str(player.level), inline=True)
            embed.add_field(name=await get_label("xp", "XP"), value=str(player.xp), inline=True)
            embed.add_field(name=await get_label("unspent_xp", "Unspent XP"), value=str(player.unspent_xp), inline=True)
            embed.add_field(name=await get_label("location_id", "Current Location ID"), value=str(player.current_location_id) if player.current_location_id else "N/A", inline=True)
            embed.add_field(name=await get_label("party_id", "Current Party ID"), value=str(player.current_party_id) if player.current_party_id else "N/A", inline=True)
            embed.add_field(name=await get_label("status", "Status"), value=player.current_status.value if player.current_status else "N/A", inline=True)
            embed.add_field(name=await get_label("language", "Language"), value=player.language or "N/A", inline=True)
            
            attributes_label = await get_label("attributes_json", "Attributes JSON")
            attributes_str = await get_localized_message_template(session, interaction.guild_id, "player_view:no_attributes", lang_code, "No attributes")
            if player.attributes_json:
                try:
                    attributes_str = json.dumps(player.attributes_json, indent=2, ensure_ascii=False)
                except TypeError:
                    attributes_str = await get_localized_message_template(session, interaction.guild_id, "player_view:error_attributes_serialization", lang_code, "Error displaying attributes (non-serializable).")
            
            embed.add_field(name=attributes_label, value=f"```json\n{attributes_str[:1000]}\n```" + ("..." if len(attributes_str) > 1000 else ""), inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)

    @player_group.command(name="list", description="List players in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of players per page.")
    # No specific permission decorator needed
    async def player_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        # No need for guild_id check
        # Removed:
        #     await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
        #     return
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 25: limit = 25 # Max embed field limit consideration

        from src.core.crud.crud_player import player_crud # Local import
        from src.core.database import get_db_session # Local import
        from src.core.localization_utils import get_localized_message_template # IMPORT ADDED
        from sqlalchemy import func, select # For count

        async with get_db_session() as session:
            offset = (page - 1) * limit
            players = await player_crud.get_multi_by_guild(session, guild_id=interaction.guild_id, skip=offset, limit=limit)
            
            total_players_stmt = select(func.count(player_crud.model.id)).where(player_crud.model.guild_id == interaction.guild_id)
            total_players_result = await session.execute(total_players_stmt)
            total_players = total_players_result.scalar_one_or_none() or 0
            lang_code = str(interaction.locale)

            if not players:
                no_players_msg = await get_localized_message_template(
                    session, interaction.guild_id, "player_list:no_players_found_page", lang_code,
                    "No players found for this guild (Page {page})."
                )
                await interaction.followup.send(no_players_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "player_list:title", lang_code,
                "Player List (Page {page} of {total_pages})"
            )
            total_pages = ((total_players - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.blue())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "player_list:footer", lang_code,
                "Displaying {count} of {total} total players."
            )
            embed.set_footer(text=footer_template.format(count=len(players), total=total_players))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "player_list:player_field_name", lang_code,
                "ID: {player_id} | {player_name}"
            )
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "player_list:player_field_value", lang_code,
                "Discord: <@{discord_id}>\nLevel: {level}, Status: {status}"
            )

            for p in players:
                embed.add_field(
                    name=field_name_template.format(player_id=p.id, player_name=p.name),
                    value=field_value_template.format(discord_id=p.discord_id, level=p.level, status=p.current_status.value),
                    inline=False
                )

            if len(embed.fields) == 0: # Should be caught by "not players" but as a safeguard
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "player_list:no_players_to_display", lang_code,
                    "No players found to display on page {page}."
                )
                await interaction.followup.send(no_display_msg.format(page=page), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @player_group.command(name="update", description="Update a specific field for a player.")
    @app_commands.describe(
        player_id="The database ID of the player to update.",
        field_to_update="The name of the player field to update (e.g., name, level, xp, language).",
        new_value="The new value for the field (use JSON for complex types if supported)."
    )
    # No specific permission decorator needed
    async def player_update(self, interaction: discord.Interaction, player_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        # No need for guild_id check
        # Removed:
        #     await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
        #     return

        from src.core.crud.crud_player import player_crud
        from src.core.database import get_db_session, transactional # transactional might be used if update_entity is not
        from src.core.crud_base_definitions import update_entity # Using generic update
        from src.core.localization_utils import get_localized_message_template # IMPORT ADDED

        allowed_fields = {
            "name": str,
            "level": int,
            "xp": int,
            "unspent_xp": int,
            "language": str,
            "current_location_id": int, # Added
            "current_party_id": (int, type(None)), # Added, allow None
            # "attributes_json": dict, # Example for future: requires JSON parsing for new_value
            # "current_status": PlayerStatus # Example for future: requires enum conversion
        }

        lang_code = str(interaction.locale) # For localization

        field_to_update_lower = field_to_update.lower()
        field_type = allowed_fields.get(field_to_update_lower)

        if not field_type:
            async with get_db_session() as temp_session_for_error_msg: # Create a temporary session for this error message
                not_allowed_msg = await get_localized_message_template(
                    temp_session_for_error_msg, interaction.guild_id, "player_update:field_not_allowed", lang_code,
                    "Field '{field_name}' is not allowed for update or does not exist. Allowed fields: {allowed_list}"
                )
            await interaction.followup.send(not_allowed_msg.format(field_name=field_to_update, allowed_list=', '.join(allowed_fields.keys())), ephemeral=True)
            return

        parsed_value: any = None
        try:
            if field_type == str:
                parsed_value = new_value
            elif field_type == int:
                parsed_value = int(new_value)
            elif field_type == dict: # For future attributes_json
                parsed_value = json.loads(new_value)
            elif field_type == (int, type(None)): # For nullable int fields like current_party_id
                if new_value.lower() == 'none' or new_value.lower() == 'null':
                    parsed_value = None
                else:
                    parsed_value = int(new_value)
            # Add more type conversions as needed (e.g., for enums like PlayerStatus)
            else:
                async with get_db_session() as temp_session_for_error_msg: # Temporary session for error message
                    internal_error_msg = await get_localized_message_template(
                        temp_session_for_error_msg, interaction.guild_id, "player_update:error_type_conversion_not_implemented", lang_code,
                        "Internal error: Type conversion for field '{field_name}' not implemented."
                    )
                await interaction.followup.send(internal_error_msg.format(field_name=field_to_update), ephemeral=True)
                return

        except ValueError:
            async with get_db_session() as temp_session_for_error_msg: # Temporary session for error message
                invalid_value_msg = await get_localized_message_template(
                    temp_session_for_error_msg, interaction.guild_id, "player_update:error_invalid_value_for_type", lang_code,
                    "Invalid value '{value}' for field '{field_name}'. Expected type: {expected_type}."
                )
            expected_type_str = field_type.__name__ if not isinstance(field_type, tuple) else 'int or None'
            await interaction.followup.send(invalid_value_msg.format(value=new_value, field_name=field_to_update, expected_type=expected_type_str), ephemeral=True)
            return
        except json.JSONDecodeError:
            async with get_db_session() as temp_session_for_error_msg: # Temporary session for error message
                invalid_json_msg = await get_localized_message_template(
                    temp_session_for_error_msg, interaction.guild_id, "player_update:error_invalid_json", lang_code,
                    "Invalid JSON string '{value}' for field '{field_name}'."
                )
            await interaction.followup.send(invalid_json_msg.format(value=new_value, field_name=field_to_update), ephemeral=True)
            return

        update_data = {field_to_update_lower: parsed_value} # Use field_to_update_lower

        # get_db_session() is already called at the beginning of the command for localization
        # No, it's not, player_update is a separate command. Need to ensure session is active.
        # The existing code uses a new `async with get_db_session() as session:` block, which is correct.
        async with get_db_session() as session: # This is the correct session for DB operations
            player = await player_crud.get_by_id_and_guild(session, id=player_id, guild_id=interaction.guild_id)
            if not player:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "player_update:player_not_found", lang_code,
                    "Player with ID {player_id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg.format(player_id=player_id), ephemeral=True)
                return

            try:
                async with session.begin(): # Ensure atomic update
                    updated_player = await update_entity(session, entity=player, data=update_data)
                    # session.commit() will be called by session.begin() if no exceptions
                    await session.refresh(updated_player)
            except Exception as e:
                # session.begin() handles rollback on exception
                logger.error(f"Error updating player {player_id} with data {update_data}: {e}", exc_info=True)
                generic_error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "player_update:error_generic_update", lang_code,
                    "An error occurred while updating player {player_id}: {error_message}"
                )
                await interaction.followup.send(generic_error_msg.format(player_id=player_id, error_message=str(e)), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "player_update:success_title", lang_code,
                "Player Updated: {player_name} (ID: {player_id})"
            )
            embed_title = title_template.format(player_name=updated_player.name, player_id=updated_player.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.orange())

            field_updated_label = await get_localized_message_template(session, interaction.guild_id, "player_update:label_field_updated", lang_code, "Field Updated")
            new_value_label = await get_localized_message_template(session, interaction.guild_id, "player_update:label_new_value", lang_code, "New Value")

            embed.add_field(name=field_updated_label, value=field_to_update, inline=True)
            new_value_display = str(parsed_value)
            if isinstance(parsed_value, dict): # Should not happen with current allowed_fields
                new_value_display = f"```json\n{json.dumps(parsed_value, indent=2)}\n```"
            elif parsed_value is None:
                new_value_display = "None"

            embed.add_field(name=new_value_label, value=new_value_display, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    # --- RuleConfig CRUD ---
    ruleconfig_group = app_commands.Group(name="ruleconfig", description="Master commands for managing RuleConfig entries.", parent=master_admin)

    @ruleconfig_group.command(name="get", description="Get a specific RuleConfig value.")
    @app_commands.describe(key="The key of the RuleConfig entry to view.")
    # No specific permission decorator needed
    async def ruleconfig_get(self, interaction: discord.Interaction, key: str):
        await interaction.response.defer(ephemeral=True)
        # No need for guild_id check
        # Removed:
        #     await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
        #     return

        from src.core.rules import get_rule # Local import
        from src.core.database import get_db_session # Local import
        from src.core.localization_utils import get_localized_message_template # IMPORT ADDED

        async with get_db_session() as session:
            # get_rule returns the value directly, or None if not found (using default=None)
            lang_code = str(interaction.locale)
            rule_value = await get_rule(session, guild_id=interaction.guild_id, key=key) # get_rule uses default=None

            if rule_value is None:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ruleconfig_get:not_found", lang_code,
                    "RuleConfig with key '{key_name}' not found for this guild."
                )
                await interaction.followup.send(not_found_msg.format(key_name=key), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "ruleconfig_get:title", lang_code,
                "RuleConfig: {key_name}"
            )
            embed = discord.Embed(title=title_template.format(key_name=key), color=discord.Color.purple())

            key_label = await get_localized_message_template(session, interaction.guild_id, "ruleconfig_get:label_key", lang_code, "Key")
            value_label = await get_localized_message_template(session, interaction.guild_id, "ruleconfig_get:label_value", lang_code, "Value")

            try:
                value_str = json.dumps(rule_value, indent=2, ensure_ascii=False)
            except TypeError:
                value_str = await get_localized_message_template(
                    session, interaction.guild_id, "ruleconfig_get:error_serialization", lang_code,
                    "Error displaying value (non-serializable)."
                )

            embed.add_field(name=key_label, value=key, inline=False)
            embed.add_field(name=value_label, value=f"```json\n{value_str[:1000]}\n```" + ("..." if len(value_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @ruleconfig_group.command(name="set", description="Set or update a RuleConfig value.")
    @app_commands.describe(key="The key of the RuleConfig entry.", value_json="The new JSON value for the rule.")
    # No specific permission decorator needed
    async def ruleconfig_set(self, interaction: discord.Interaction, key: str, value_json: str):
        await interaction.response.defer(ephemeral=True)
        # No need for guild_id check
        # Removed:
        #     await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
        #     return

        from src.core.rules import update_rule_config # Local import
        from src.core.database import get_db_session # Local import for the context, though update_rule_config is @transactional
        from src.core.localization_utils import get_localized_message_template # IMPORT ADDED

        lang_code = str(interaction.locale)
        try:
            new_value = json.loads(value_json)
        except json.JSONDecodeError:
            # The erroneous call that used an undefined 'session' has been removed.
            # The correct call is within the temp_session_for_error_msg block below.
            async with get_db_session() as temp_session_for_error_msg: # Temporary session just for this error message if JSON parsing fails early
                 invalid_json_msg = await get_localized_message_template(
                    temp_session_for_error_msg, interaction.guild_id, "ruleconfig_set:error_invalid_json", lang_code,
                    "Invalid JSON string provided for value: {json_string}"
                )
            await interaction.followup.send(invalid_json_msg.format(json_string=value_json), ephemeral=True)
            return

        async with get_db_session() as session:
            try:
                updated_rule = await update_rule_config(session, guild_id=interaction.guild_id, key=key, value=new_value)
            except Exception as e:
                logger.error(f"Error calling update_rule_config for key {key} with value {new_value}: {e}", exc_info=True)
                error_set_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ruleconfig_set:error_generic_set", lang_code,
                    "An error occurred while setting rule '{key_name}': {error_message}"
                )
                await interaction.followup.send(error_set_msg.format(key_name=key, error_message=str(e)), ephemeral=True)
                return

            success_msg = await get_localized_message_template(
                session, interaction.guild_id, "ruleconfig_set:success", lang_code,
                "RuleConfig '{key_name}' has been set/updated successfully."
            )
            await interaction.followup.send(success_msg.format(key_name=key), ephemeral=True)

    @ruleconfig_group.command(name="list", description="List all RuleConfig entries for this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of rules per page.")
    # No specific permission decorator needed
    async def ruleconfig_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        # No need for guild_id check
        # Removed:
        #     await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
        #     return
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10 # Embeds can get very long with many JSON values

        from src.core.rules import get_all_rules_for_guild # Local import
        from src.core.database import get_db_session # Local import
        from src.core.localization_utils import get_localized_message_template # IMPORT ADDED

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            all_rules_dict = await get_all_rules_for_guild(session, guild_id=interaction.guild_id)

        if not all_rules_dict:
            # The erroneous call that used an undefined 'session' has been removed.
            # The correct call is within the temp_session_for_error_msg block below.
            async with get_db_session() as temp_session_for_error_msg:
                lang_code = str(interaction.locale) # ensure lang_code is in this scope
                no_rules_msg = await get_localized_message_template(
                    temp_session_for_error_msg, interaction.guild_id, "ruleconfig_list:no_rules_found", lang_code,
                    "No RuleConfig entries found for this guild."
                )
            await interaction.followup.send(no_rules_msg, ephemeral=True)
            return

        rules_list = sorted(all_rules_dict.items())
        total_rules = len(rules_list)
        
        start_index = (page - 1) * limit
        end_index = start_index + limit
        paginated_rules = rules_list[start_index:end_index]

        async with get_db_session() as session: # Session for subsequent localization calls
            lang_code = str(interaction.locale) # Redefine for this scope if needed, or pass from outer scope. It's fine here.
            if not paginated_rules:
                no_rules_on_page_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ruleconfig_list:no_rules_on_page", lang_code,
                    "No rules found on page {page_num}."
                )
                await interaction.followup.send(no_rules_on_page_msg.format(page_num=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "ruleconfig_list:title", lang_code,
                "RuleConfig List (Page {page_num} of {total_pages})"
            )
            total_pages = ((total_rules - 1) // limit) + 1
            embed_title = title_template.format(page_num=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_purple())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "ruleconfig_list:footer", lang_code,
                "Displaying {count} of {total} total rules."
            )
            embed.set_footer(text=footer_template.format(count=len(paginated_rules), total=total_rules))

            error_serialization_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ruleconfig_list:error_serialization", lang_code,
                    "Error: Non-serializable value."
                )

            for key, value in paginated_rules:
                try:
                    value_str = json.dumps(value, ensure_ascii=False)
                    if len(value_str) > 150:
                        value_str = value_str[:150] + "..."
                except TypeError:
                    value_str = error_serialization_msg
                embed.add_field(name=key, value=f"```json\n{value_str}\n```", inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @ruleconfig_group.command(name="delete", description="Delete a specific RuleConfig entry.")
    @app_commands.describe(key="The key of the RuleConfig entry to delete.")
    # No specific permission decorator needed
    async def ruleconfig_delete(self, interaction: discord.Interaction, key: str):
        await interaction.response.defer(ephemeral=True)
        # No need for guild_id check
        # Removed: (There wasn't one here, but ensuring consistency)

        from src.core.rules import rule_config_crud # Using CRUD directly for delete
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template # IMPORT ADDED

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            # Check if the rule exists first to provide a better message
            existing_rule = await rule_config_crud.get_by_guild_and_key(session, guild_id=interaction.guild_id, key=key)
            if not existing_rule:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ruleconfig_delete:not_found", lang_code,
                    "RuleConfig with key '{key_name}' not found. Nothing to delete."
                )
                await interaction.followup.send(not_found_msg.format(key_name=key), ephemeral=True)
                return

            try:
                # rule_config_crud.remove_by_guild_and_key is @transactional
                # It returns the number of deleted rows or the deleted object, depending on implementation.
                # Let's assume it returns the deleted object or raises an error if not found (which we checked).
                # If it's transactional, it handles its own commit/rollback.
                # We might not need to pass the session explicitly if it creates its own via @transactional.
                # However, remove_by_guild_and_key in CRUDBase takes a session.

                # The CRUDBase remove_by_guild_and_key is NOT @transactional.
                # It expects an active session.
                async with session.begin(): # Ensure atomicity
                    deleted_count = await rule_config_crud.remove_by_guild_and_key(
                        session=session, guild_id=interaction.guild_id, key=key
                    )
                    # session.commit() will be called by session.begin()

                if deleted_count and deleted_count > 0: # Assuming it returns count of deleted rows
                    success_msg = await get_localized_message_template(
                        session, interaction.guild_id, "ruleconfig_delete:success", lang_code,
                        "RuleConfig '{key_name}' has been deleted successfully."
                    )
                    await interaction.followup.send(success_msg.format(key_name=key), ephemeral=True)
                else: # Should have been caught by 'existing_rule' check, but as a safeguard
                    error_not_deleted_msg = await get_localized_message_template(
                        session, interaction.guild_id, "ruleconfig_delete:error_not_deleted", lang_code,
                        "RuleConfig '{key_name}' was found but could not be deleted."
                    )
                    await interaction.followup.send(error_not_deleted_msg.format(key_name=key), ephemeral=True)

            except Exception as e:
                logger.error(f"Error deleting RuleConfig key {key} for guild {interaction.guild_id}: {e}", exc_info=True)
                generic_error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ruleconfig_delete:error_generic", lang_code,
                    "An error occurred while deleting rule '{key_name}': {error_message}"
                )
                await interaction.followup.send(generic_error_msg.format(key_name=key, error_message=str(e)), ephemeral=True)
                return

    # --- PendingConflict Management ---
    conflict_group = app_commands.Group(name="conflict", description="Master commands for managing pending conflicts.", parent=master_admin)

    @conflict_group.command(name="resolve", description="Resolve a pending conflict.")
    @app_commands.describe(
        pending_conflict_id="The ID of the pending conflict to resolve.",
        outcome_status="The resolution status (e.g., RESOLVED_BY_MASTER_FAVOR_ACTION1, RESOLVED_BY_MASTER_CUSTOM).",
        # resolved_action_json="Optional JSON for the custom resolved action (if outcome requires it).", # TODO: Add later if needed
        notes="Optional notes about the resolution."
    )
    # No specific permission decorator needed
    async def conflict_resolve(self, interaction: discord.Interaction,
                               pending_conflict_id: int,
                               outcome_status: str,
                               # resolved_action_json: Optional[str] = None, # TODO
                               notes: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        # No need for guild_id check
        # Removed:
        #     await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
        #     return

        from src.core.database import get_db_session # Keep for session management
        # from src.models.pending_conflict import PendingConflict # Not needed directly
        from src.models.enums import ConflictStatus
        from src.core.crud.crud_pending_conflict import pending_conflict_crud # Use specific CRUD
        from src.core.localization_utils import get_localized_message_template # IMPORT ADDED
        # from src.core.crud_base_definitions import update_entity # Will use pending_conflict_crud.update
        from typing import Dict, Any, Optional

        lang_code = str(interaction.locale)

        try:
            # Validate outcome_status against ConflictStatus enum
            # We only allow resolution statuses that imply Master action.
            valid_resolution_statuses = {
                ConflictStatus.RESOLVED_BY_MASTER_FAVOR_ACTION1,
                ConflictStatus.RESOLVED_BY_MASTER_FAVOR_ACTION2, # Assuming there might be a second action
                ConflictStatus.RESOLVED_BY_MASTER_CUSTOM_ACTION,
                ConflictStatus.RESOLVED_BY_MASTER_DISMISS
            }
            resolved_status_enum: Optional[ConflictStatus] = None
            for status_member in ConflictStatus: # Iterate through enum members
                if status_member.name.upper() == outcome_status.upper() or status_member.value.upper() == outcome_status.upper():
                    if status_member in valid_resolution_statuses:
                        resolved_status_enum = status_member
                        break
                    else: # Matched a ConflictStatus name/value, but not one of the allowed master resolution types
                        allowed_values_str = ", ".join([s.name for s in valid_resolution_statuses])
                        async with get_db_session() as temp_session_for_error_msg: # Temporary session for error message
                            invalid_outcome_msg = await get_localized_message_template(
                                temp_session_for_error_msg, interaction.guild_id, "conflict_resolve:error_invalid_outcome_for_master", lang_code,
                                "Invalid outcome_status '{provided_status}'. Allowed values for master resolution: {allowed_list}"
                            )
                        await interaction.followup.send(invalid_outcome_msg.format(provided_status=outcome_status, allowed_list=allowed_values_str), ephemeral=True)
                        return

            if not resolved_status_enum: # Did not match any ConflictStatus name/value
                allowed_values_str = ", ".join([s.name for s in valid_resolution_statuses])
                async with get_db_session() as temp_session_for_error_msg: # Temporary session for error message
                    unrecognized_outcome_msg = await get_localized_message_template(
                        temp_session_for_error_msg, interaction.guild_id, "conflict_resolve:error_unrecognized_outcome", lang_code,
                        "Outcome status '{provided_status}' not recognized or not a valid master resolution. Allowed: {allowed_list}"
                    )
                await interaction.followup.send(unrecognized_outcome_msg.format(provided_status=outcome_status, allowed_list=allowed_values_str), ephemeral=True)
                return

        except ValueError: # Should not happen with current logic, but as a safeguard
            async with get_db_session() as temp_session_for_error_msg: # Temporary session for error message
                internal_error_msg = await get_localized_message_template(
                    temp_session_for_error_msg, interaction.guild_id, "conflict_resolve:error_internal_status_check", lang_code,
                    "Internal error processing outcome_status: '{provided_status}'."
                )
            await interaction.followup.send(internal_error_msg.format(provided_status=outcome_status), ephemeral=True)
            return

        # TODO: Parse resolved_action_json if provided and outcome_status is RESOLVED_BY_MASTER_CUSTOM_ACTION
        # parsed_resolved_action = None
        # if resolved_action_json and resolved_status_enum == ConflictStatus.RESOLVED_BY_MASTER_CUSTOM_ACTION:
        #     try:
        #         parsed_resolved_action = json.loads(resolved_action_json)
        #         # Potentially validate against ParsedAction model if needed
        #     except json.JSONDecodeError:
        #         await interaction.followup.send("Invalid JSON string for resolved_action_json.", ephemeral=True)
        #         return
        # elif resolved_action_json: # Provided but not needed for this status
        #     await interaction.followup.send(f"resolved_action_json is only applicable if outcome_status is RESOLVED_BY_MASTER_CUSTOM_ACTION.", ephemeral=True)
        #     return


        update_data: Dict[str, Any] = {
            "status": resolved_status_enum, # Store the enum member itself
            "resolution_notes": notes,
            "resolved_at": discord.utils.utcnow() # Set resolution time
        }
        # if parsed_resolved_action:
        #     update_data["resolved_action_json"] = parsed_resolved_action

        # The session for localization calls for outcome_status errors is handled inside that try-except block
        # Now, the main session for DB operations:
        async with get_db_session() as session:
            lang_code = str(interaction.locale) # Ensure lang_code is available in this scope
            try:
                async with session.begin():
                    conflict_to_update = await pending_conflict_crud.get_by_id_and_guild(session, id=pending_conflict_id, guild_id=interaction.guild_id)

                    if not conflict_to_update:
                        not_found_msg = await get_localized_message_template(
                            session, interaction.guild_id, "conflict_resolve:not_found", lang_code,
                            "PendingConflict with ID {conflict_id} not found in this guild."
                        )
                        await interaction.followup.send(not_found_msg.format(conflict_id=pending_conflict_id), ephemeral=True)
                        return # session.begin() will rollback if an error wasn't raised

                    if conflict_to_update.status != ConflictStatus.PENDING_MASTER_RESOLUTION:
                        not_pending_msg = await get_localized_message_template(
                            session, interaction.guild_id, "conflict_resolve:not_pending_master_resolution", lang_code,
                            "Conflict ID {conflict_id} is not awaiting master resolution (current status: {current_status})."
                        )
                        await interaction.followup.send(not_pending_msg.format(conflict_id=pending_conflict_id, current_status=conflict_to_update.status.value), ephemeral=True)
                        return

                    # Use the specific CRUD update method if it exists and is preferred,
                    # otherwise, CRUDBase.update (which update_entity was likely a wrapper for) is fine.
                    # CRUDBase.update takes db_obj and obj_in (a dict or Pydantic model).
                    updated_conflict = await pending_conflict_crud.update(session, db_obj=conflict_to_update, obj_in=update_data)
                    # CRUDBase.update does session.add and session.flush. session.begin() handles commit.
                    await session.refresh(updated_conflict) # Refresh to get any DB-generated changes like triggers if any

                    # Placeholder for actual signaling:
                    logger.info(f"Conflict {updated_conflict.id} resolved by Master. Current status: {updated_conflict.status.value}. Notes: '{updated_conflict.resolution_notes}'. Action Processor signaling mechanism TBD.")

                # If session.begin() committed successfully
                success_msg = await get_localized_message_template(
                    session, interaction.guild_id, "conflict_resolve:success", lang_code,
                    "Conflict ID {conflict_id} has been resolved with status '{status_name}'. Notes: {notes_value}"
                )
                await interaction.followup.send(success_msg.format(conflict_id=pending_conflict_id, status_name=resolved_status_enum.name, notes_value=(notes or "N/A")), ephemeral=True)

            except Exception as e:
                # session.begin() handles rollback
                logger.error(f"Error resolving conflict {pending_conflict_id} for guild {interaction.guild_id}: {e}", exc_info=True)
                generic_error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "conflict_resolve:error_generic", lang_code,
                    "An error occurred while resolving conflict {conflict_id}: {error_message}"
                )
                await interaction.followup.send(generic_error_msg.format(conflict_id=pending_conflict_id, error_message=str(e)), ephemeral=True)
                return
    
    @conflict_group.command(name="view", description="View details of a specific pending conflict.")
    @app_commands.describe(pending_conflict_id="The ID of the pending conflict to view.")
    # No specific permission decorator needed
    async def conflict_view(self, interaction: discord.Interaction, pending_conflict_id: int):
        await interaction.response.defer(ephemeral=True)
        # No need for guild_id check
        # Removed:
        #     await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
        #     return

        from src.core.database import get_db_session
        # from src.models.pending_conflict import PendingConflict # Not needed directly
        from src.core.crud.crud_pending_conflict import pending_conflict_crud # Use the specific CRUD
        from src.core.localization_utils import get_localized_message_template # IMPORT ADDED

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            conflict = await pending_conflict_crud.get_by_id_and_guild(session, id=pending_conflict_id, guild_id=interaction.guild_id)

            if not conflict:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "conflict_view:not_found", lang_code,
                    "PendingConflict with ID {conflict_id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg.format(conflict_id=pending_conflict_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "conflict_view:title", lang_code,
                "Conflict Details (ID: {conflict_id})"
            )
            embed = discord.Embed(title=title_template.format(conflict_id=conflict.id), color=discord.Color.red())

            # Helper for field labels
            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"conflict_view:label_{key}", lang_code, default)

            embed.add_field(name=await get_label("status", "Status"), value=conflict.status.value, inline=True)
            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(conflict.guild_id), inline=True)
            created_at_val = discord.utils.format_dt(conflict.created_at, style='F') if conflict.created_at else await get_label("value_na", "N/A")
            embed.add_field(name=await get_label("created_at", "Created At"), value=created_at_val, inline=True)

            if conflict.resolved_at:
                resolved_at_val = discord.utils.format_dt(conflict.resolved_at, style='F')
                embed.add_field(name=await get_label("resolved_at", "Resolved At"), value=resolved_at_val, inline=True)

            error_serialization_msg = await get_localized_message_template(session, interaction.guild_id, "conflict_view:error_serialization", lang_code, "Error: Non-serializable data")
            na_msg = await get_localized_message_template(session, interaction.guild_id, "conflict_view:value_na_json", lang_code, "Not available")

            involved_str = na_msg
            if conflict.involved_entities_json:
                try:
                    involved_str = json.dumps(conflict.involved_entities_json, indent=2, ensure_ascii=False)
                except TypeError: involved_str = error_serialization_msg
            embed.add_field(name=await get_label("involved_entities", "Involved Entities"), value=f"```json\n{involved_str[:1000]}\n```" + ("..." if len(involved_str) > 1000 else ""), inline=False)

            actions_str = na_msg
            if conflict.conflicting_actions_json:
                try:
                    actions_str = json.dumps(conflict.conflicting_actions_json, indent=2, ensure_ascii=False)
                except TypeError: actions_str = error_serialization_msg
            embed.add_field(name=await get_label("conflicting_actions", "Conflicting Actions"), value=f"```json\n{actions_str[:1000]}\n```" + ("..." if len(actions_str) > 1000 else ""), inline=False)

            if conflict.resolution_notes:
                embed.add_field(name=await get_label("resolution_notes", "Resolution Notes"), value=conflict.resolution_notes[:1020] + ("..." if len(conflict.resolution_notes) > 1020 else ""), inline=False)

            if conflict.resolved_action_json:
                resolved_action_str = na_msg
                try:
                    resolved_action_str = json.dumps(conflict.resolved_action_json, indent=2, ensure_ascii=False)
                except TypeError: resolved_action_str = error_serialization_msg
                embed.add_field(name=await get_label("resolved_action", "Resolved Action"), value=f"```json\n{resolved_action_str[:1000]}\n```" + ("..." if len(resolved_action_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @conflict_group.command(name="list", description="List pending conflicts in this guild.")
    @app_commands.describe(
        status="Filter by status (e.g., PENDING_MASTER_RESOLUTION, RESOLVED_BY_MASTER_CUSTOM_ACTION). Optional.",
        page="Page number to display.",
        limit="Number of conflicts per page."
    )
    # No specific permission decorator needed
    async def conflict_list(self, interaction: discord.Interaction, status: Optional[str] = None, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)

        from src.core.database import get_db_session
        from src.core.crud.crud_pending_conflict import pending_conflict_crud
        from src.models.enums import ConflictStatus
        from src.core.localization_utils import get_localized_message_template # IMPORT ADDED

        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10 # Keep embed size reasonable

        status_enum: Optional[ConflictStatus] = None
        lang_code = str(interaction.locale) # For localization

        async with get_db_session() as session: # Session for all DB and localization calls
            if status:
                try:
                    status_enum = ConflictStatus[status.upper()] # Try to match by name
                except KeyError:
                    try:
                        status_enum = ConflictStatus(status) # Try to match by value
                    except ValueError:
                        invalid_status_msg = await get_localized_message_template(
                            session, interaction.guild_id, "conflict_list:error_invalid_status", lang_code,
                            "Invalid status value '{provided_status}'. Valid statuses are: {valid_statuses}"
                        )
                        valid_statuses_str = ", ".join([s.name for s in ConflictStatus])
                        await interaction.followup.send(invalid_status_msg.format(provided_status=status, valid_statuses=valid_statuses_str), ephemeral=True)
                        return

            offset = (page - 1) * limit
            conflicts = await pending_conflict_crud.get_multi_by_guild_and_status_paginated(
                session, guild_id=interaction.guild_id, status=status_enum, skip=offset, limit=limit
            )
            total_conflicts = await pending_conflict_crud.get_count_by_guild_and_status(
                session, guild_id=interaction.guild_id, status=status_enum
            )

            if not conflicts:
                no_conflicts_msg = await get_localized_message_template(
                    session, interaction.guild_id, "conflict_list:no_conflicts_found", lang_code,
                    "No conflicts found for the given criteria (Status: {status_filter}, Page: {page_num})."
                )
                status_filter_str = status_enum.name if status_enum else "Any"
                await interaction.followup.send(no_conflicts_msg.format(status_filter=status_filter_str, page_num=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "conflict_list:title", lang_code,
                "Conflict List (Status: {status_filter}, Page {page_num} of {total_pages})"
            )
            total_pages = ((total_conflicts - 1) // limit) + 1
            status_filter_display = status_enum.name if status_enum else await get_localized_message_template(session, interaction.guild_id, "conflict_list:status_any", lang_code, "Any")
            embed_title = title_template.format(status_filter=status_filter_display, page_num=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.orange())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "conflict_list:footer", lang_code,
                "Displaying {count} of {total} total conflicts."
            )
            embed.set_footer(text=footer_template.format(count=len(conflicts), total=total_conflicts))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "conflict_list:conflict_field_name", lang_code,
                "ID: {conflict_id} | Status: {status_value}"
            )
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "conflict_list:conflict_field_value", lang_code,
                "Created: {created_at_dt}\nInvolved: {involved_count} entities"
            )

            for c in conflicts:
                involved_count = len(c.involved_entities_json) if isinstance(c.involved_entities_json, list) else 0
                created_at_dt_str = discord.utils.format_dt(c.created_at, style='R') if c.created_at else "N/A"
                embed.add_field(
                    name=field_name_template.format(conflict_id=c.id, status_value=c.status.value),
                    value=field_value_template.format(created_at_dt=created_at_dt_str, involved_count=involved_count),
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

    # --- Party CRUD ---
    party_group = app_commands.Group(name="party", description="Master commands for managing parties.", parent=master_admin)

    @party_group.command(name="view", description="View details of a specific party.")
    @app_commands.describe(party_id="The database ID of the party to view.")
    async def party_view(self, interaction: discord.Interaction, party_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_party import party_crud
        from src.core.crud.crud_player import player_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            party = await party_crud.get_by_id_and_guild(session, id=party_id, guild_id=interaction.guild_id)

            if not party:
                not_found_msg_template = await get_localized_message_template(
                    session, interaction.guild_id, "party_view:not_found", lang_code,
                    "Party with ID {party_id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg_template.format(party_id=party_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "party_view:title", lang_code,
                "Party Details: {party_name} (ID: {party_id})"
            )
            party_name_i18n = party.name_i18n.get(lang_code, party.name_i18n.get("en", f"Party {party.id}"))
            embed_title = title_template.format(party_name=party_name_i18n, party_id=party.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_gold())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"party_view:label_{key}", lang_code, default)

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(party.guild_id), inline=True)
            embed.add_field(name=await get_label("leader_id", "Leader Player ID"), value=str(party.leader_player_id) if party.leader_player_id else "N/A", inline=True)
            embed.add_field(name=await get_label("status", "Turn Status"), value=party.turn_status.value if party.turn_status else "N/A", inline=True)

            name_i18n_str = await get_localized_message_template(session, interaction.guild_id, "party_view:value_na_json", lang_code, "Not available")
            if party.name_i18n:
                try:
                    name_i18n_str = json.dumps(party.name_i18n, indent=2, ensure_ascii=False)
                except TypeError:
                    name_i18n_str = await get_localized_message_template(session, interaction.guild_id, "party_view:error_serialization", lang_code, "Error serializing Name i18n")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```" + ("..." if len(name_i18n_str) > 1000 else ""), inline=False)

            properties_str = await get_localized_message_template(session, interaction.guild_id, "party_view:value_na_json", lang_code, "Not available")
            if party.properties_json:
                try:
                    properties_str = json.dumps(party.properties_json, indent=2, ensure_ascii=False)
                except TypeError:
                    properties_str = await get_localized_message_template(session, interaction.guild_id, "party_view:error_serialization", lang_code, "Error serializing Properties JSON")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{properties_str[:1000]}\n```" + ("..." if len(properties_str) > 1000 else ""), inline=False)

            player_ids = party.player_ids_json if party.player_ids_json else []
            members_info = []
            if player_ids:
                # Fetch player names for better display
                # Note: This could be slow if there are many players. Consider if names are essential here or just IDs.
                # For now, let's fetch names.
                players_in_party = await player_crud.get_many_by_ids_and_guild(session, ids=player_ids, guild_id=interaction.guild_id)
                player_id_to_name_map = {p.id: p.name for p in players_in_party}

                for p_id in player_ids:
                    p_name = player_id_to_name_map.get(p_id, "Unknown Player")
                    members_info.append(f"ID: {p_id} (Name: {p_name})")

            members_label = await get_label("members", "Members")
            if members_info:
                embed.add_field(name=f"{members_label} ({len(members_info)})", value="\n".join(members_info)[:1020] + ("..." if len("\n".join(members_info)) > 1020 else ""), inline=False)
            else:
                no_members_msg = await get_localized_message_template(session, interaction.guild_id, "party_view:no_members", lang_code, "No members in this party.")
                embed.add_field(name=members_label, value=no_members_msg, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @party_group.command(name="list", description="List parties in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of parties per page.")
    async def party_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10 # Max embed field limit consideration

        from src.core.crud.crud_party import party_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import func, select

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            offset = (page - 1) * limit
            parties = await party_crud.get_multi_by_guild(session, guild_id=interaction.guild_id, skip=offset, limit=limit)

            total_parties_stmt = select(func.count(party_crud.model.id)).where(party_crud.model.guild_id == interaction.guild_id)
            total_parties_result = await session.execute(total_parties_stmt)
            total_parties = total_parties_result.scalar_one_or_none() or 0

            if not parties:
                no_parties_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_list:no_parties_found_page", lang_code,
                    "No parties found for this guild (Page {page})."
                )
                await interaction.followup.send(no_parties_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "party_list:title", lang_code,
                "Party List (Page {page} of {total_pages})"
            )
            total_pages = ((total_parties - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_teal())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "party_list:footer", lang_code,
                "Displaying {count} of {total} total parties."
            )
            embed.set_footer(text=footer_template.format(count=len(parties), total=total_parties))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "party_list:party_field_name", lang_code,
                "ID: {party_id} | {party_name}"
            )
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "party_list:party_field_value", lang_code,
                "Leader ID: {leader_id}, Members: {member_count}, Status: {status}"
            )

            for p in parties:
                party_name_i18n = p.name_i18n.get(lang_code, p.name_i18n.get("en", f"Party {p.id}"))
                member_count = len(p.player_ids_json) if p.player_ids_json else 0
                embed.add_field(
                    name=field_name_template.format(party_id=p.id, party_name=party_name_i18n),
                    value=field_value_template.format(
                        leader_id=str(p.leader_player_id) if p.leader_player_id else "N/A",
                        member_count=member_count,
                        status=p.turn_status.value if p.turn_status else "N/A"
                    ),
                    inline=False
                )

            if len(embed.fields) == 0:
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_list:no_parties_to_display", lang_code,
                    "No parties found to display on page {page}."
                )
                await interaction.followup.send(no_display_msg.format(page=page), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @party_group.command(name="create", description="Create a new party in this guild.")
    @app_commands.describe(
        leader_player_id="Optional: The database ID of the player who will lead this party.",
        name_i18n_json="Optional: JSON string for party name in multiple languages (e.g., {\"en\": \"My Party\", \"ru\": \"Моя группа\"}).",
        player_ids_json="Optional: JSON string of player IDs to add to this party (e.g., [1, 2, 3]).",
        properties_json="Optional: JSON string for additional party properties."
    )
    async def party_create(self, interaction: discord.Interaction,
                           leader_player_id: Optional[int] = None,
                           name_i18n_json: Optional[str] = None,
                           player_ids_json: Optional[str] = None,
                           properties_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_party import party_crud
        from src.core.crud.crud_player import player_crud # To validate leader and members
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from src.models.party import PartyTurnStatus # Default status
        from src.models.party import Party # For type hinting

        lang_code = str(interaction.locale)
        parsed_name_i18n: Optional[Dict[str, str]] = None
        parsed_player_ids: Optional[List[int]] = None
        parsed_properties: Optional[Dict[str, Any]] = None

        async with get_db_session() as session: # Session for all operations
            # Validate leader_player_id if provided
            if leader_player_id:
                leader_player = await player_crud.get_by_id_and_guild(session, id=leader_player_id, guild_id=interaction.guild_id)
                if not leader_player:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "party_create:error_leader_not_found", lang_code,
                        "Leader player with ID {player_id} not found in this guild."
                    )
                    await interaction.followup.send(error_msg.format(player_id=leader_player_id), ephemeral=True)
                    return

            # Parse name_i18n_json
            if name_i18n_json:
                try:
                    parsed_name_i18n = json.loads(name_i18n_json)
                    if not isinstance(parsed_name_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_name_i18n.items()):
                        raise ValueError("name_i18n_json must be a dictionary of string keys and string values.")
                except (json.JSONDecodeError, ValueError) as e:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "party_create:error_invalid_name_json", lang_code,
                        "Invalid format for name_i18n_json: {error_details}"
                    )
                    await interaction.followup.send(error_msg.format(error_details=str(e)), ephemeral=True)
                    return

            # Parse and validate player_ids_json
            if player_ids_json:
                try:
                    parsed_player_ids = json.loads(player_ids_json)
                    if not isinstance(parsed_player_ids, list) or not all(isinstance(pid, int) for pid in parsed_player_ids):
                        raise ValueError("player_ids_json must be a list of integers.")

                    # Validate that all player IDs exist in the guild
                    if parsed_player_ids:
                        found_players = await player_crud.get_many_by_ids_and_guild(session, ids=parsed_player_ids, guild_id=interaction.guild_id)
                        found_player_ids = {p.id for p in found_players}
                        missing_player_ids = [pid for pid in parsed_player_ids if pid not in found_player_ids]
                        if missing_player_ids:
                            error_msg = await get_localized_message_template(
                                session, interaction.guild_id, "party_create:error_member_not_found", lang_code,
                                "One or more player IDs in player_ids_json not found in this guild: {missing_ids}"
                            )
                            await interaction.followup.send(error_msg.format(missing_ids=", ".join(map(str, missing_player_ids))), ephemeral=True)
                            return
                except (json.JSONDecodeError, ValueError) as e:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "party_create:error_invalid_player_ids_json", lang_code,
                        "Invalid format for player_ids_json: {error_details}"
                    )
                    await interaction.followup.send(error_msg.format(error_details=str(e)), ephemeral=True)
                    return

            # Parse properties_json
            if properties_json:
                try:
                    parsed_properties = json.loads(properties_json)
                    if not isinstance(parsed_properties, dict):
                        raise ValueError("properties_json must be a dictionary.")
                except (json.JSONDecodeError, ValueError) as e:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "party_create:error_invalid_properties_json", lang_code,
                        "Invalid format for properties_json: {error_details}"
                    )
                    await interaction.followup.send(error_msg.format(error_details=str(e)), ephemeral=True)
                    return

            party_data_to_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id,
                "leader_player_id": leader_player_id,
                "name_i18n": parsed_name_i18n if parsed_name_i18n else {"en": "New Party", lang_code: "New Party"}, # Default name
                "player_ids_json": parsed_player_ids if parsed_player_ids else [],
                "turn_status": PartyTurnStatus.ACTIVE, # Default status
                "properties_json": parsed_properties if parsed_properties else {}
            }

            # Ensure name_i18n has at least 'en' or current lang_code
            if lang_code not in party_data_to_create["name_i18n"] and "en" not in party_data_to_create["name_i18n"]:
                 party_data_to_create["name_i18n"][lang_code] = f"Party (Unnamed)"


            try:
                # CRUDBase.create expects a Pydantic schema or dict. We pass a dict.
                # It is already @transactional or should be called within a transaction block.
                # For master commands, direct creation like this is fine.
                # The CRUDBase.create is not @transactional, so wrap in session.begin()
                async with session.begin():
                    created_party = await party_crud.create(session, obj_in=party_data_to_create)
                    # Update current_party_id for all members
                    if created_party and parsed_player_ids:
                        for p_id in parsed_player_ids:
                            player_to_update = await player_crud.get(session, id=p_id) # Already validated they exist
                            if player_to_update: # Should always be true here
                                player_to_update.current_party_id = created_party.id
                                session.add(player_to_update)
                    await session.flush() # Flush to get created_party.id if needed for players
                    if created_party: # only refresh if created_party is not None
                        await session.refresh(created_party)

            except Exception as e:
                logger.error(f"Error creating party with data {party_data_to_create}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_create:error_generic_create", lang_code,
                    "An error occurred while creating the party: {error_message}"
                )
                await interaction.followup.send(error_msg.format(error_message=str(e)), ephemeral=True)
                return

            if not created_party: # Should be caught by exception, but as safeguard
                error_msg = await get_localized_message_template(
                     session, interaction.guild_id, "party_create:error_creation_failed_unknown", lang_code,
                    "Party creation failed for an unknown reason."
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "party_create:success_title", lang_code,
                "Party Created: {party_name} (ID: {party_id})"
            )
            created_party_name_i18n = created_party.name_i18n.get(lang_code, created_party.name_i18n.get("en", f"Party {created_party.id}"))

            embed = discord.Embed(title=success_title_template.format(party_name=created_party_name_i18n, party_id=created_party.id), color=discord.Color.green())
            # Add more fields if needed, similar to party_view
            embed.add_field(name="Leader Player ID", value=str(created_party.leader_player_id) if created_party.leader_player_id else "N/A", inline=True)
            embed.add_field(name="Member Count", value=str(len(created_party.player_ids_json or [])), inline=True)
            embed.add_field(name="Status", value=created_party.turn_status.value, inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @party_group.command(name="update", description="Update a specific field for a party.")
    @app_commands.describe(
        party_id="The database ID of the party to update.",
        field_to_update="The name of the party field to update (e.g., leader_player_id, name_i18n_json, player_ids_json, properties_json, turn_status).",
        new_value="The new value for the field (use JSON for complex types; for player_ids_json, provide a complete new list; for turn_status, use enum name like ACTIVE)."
    )
    async def party_update(self, interaction: discord.Interaction, party_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_party import party_crud
        from src.core.crud.crud_player import player_crud # For validating player IDs
        from src.core.database import get_db_session
        from src.core.crud_base_definitions import update_entity
        from src.core.localization_utils import get_localized_message_template
        from src.models.party import PartyTurnStatus # For enum conversion
        from typing import List, Dict, Any # For type hints

        allowed_fields = {
            "leader_player_id": (int, type(None)),
            "name_i18n_json": dict,
            "player_ids_json": list,
            "properties_json": dict,
            "turn_status": PartyTurnStatus,
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()

        # Normalize field names (e.g. name_i18n from name_i18n_json)
        db_field_name = field_to_update_lower
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")


        field_type = allowed_fields.get(db_field_name)


        if not field_type:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "party_update:error_field_not_allowed", lang_code,
                    "Field '{field_name}' is not allowed for update or does not exist. Allowed fields: {allowed_list}"
                )
            await interaction.followup.send(error_msg.format(field_name=field_to_update, allowed_list=', '.join(allowed_fields.keys())), ephemeral=True)
            return

        parsed_value: Any = None
        original_player_ids_before_update: Optional[List[int]] = None # To track changes for player.current_party_id

        async with get_db_session() as session: # Session for initial validation and final update
            try:
                if db_field_name == "leader_player_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = int(new_value)
                        # Validate new leader exists
                        if parsed_value is not None:
                            leader_player = await player_crud.get_by_id_and_guild(session, id=parsed_value, guild_id=interaction.guild_id)
                            if not leader_player:
                                error_msg = await get_localized_message_template(
                                    session, interaction.guild_id, "party_update:error_leader_not_found", lang_code,
                                    "New leader player with ID {player_id} not found in this guild."
                                )
                                await interaction.followup.send(error_msg.format(player_id=parsed_value), ephemeral=True)
                                return
                elif db_field_name == "name_i18n":
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_value.items()):
                        raise ValueError("name_i18n must be a dictionary of string keys and string values.")
                elif db_field_name == "player_ids_json":
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, list) or not all(isinstance(pid, int) for pid in parsed_value):
                        raise ValueError("player_ids_json must be a list of integers.")
                    # Validate new player IDs
                    if parsed_value:
                        found_players = await player_crud.get_many_by_ids_and_guild(session, ids=parsed_value, guild_id=interaction.guild_id)
                        found_player_ids = {p.id for p in found_players}
                        missing_player_ids = [pid for pid in parsed_value if pid not in found_player_ids]
                        if missing_player_ids:
                            error_msg = await get_localized_message_template(
                                session, interaction.guild_id, "party_update:error_member_not_found", lang_code,
                                "One or more player IDs in new player_ids_json not found: {missing_ids}"
                            )
                            await interaction.followup.send(error_msg.format(missing_ids=", ".join(map(str, missing_player_ids))), ephemeral=True)
                            return
                elif db_field_name == "properties_json":
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict):
                        raise ValueError("properties_json must be a dictionary.")
                elif db_field_name == "turn_status":
                    try:
                        parsed_value = PartyTurnStatus[new_value.upper()]
                    except KeyError:
                        valid_statuses = ", ".join([s.name for s in PartyTurnStatus])
                        error_msg = await get_localized_message_template(
                            session, interaction.guild_id, "party_update:error_invalid_turn_status", lang_code,
                            "Invalid turn_status '{value}'. Valid statuses: {statuses}"
                        )
                        await interaction.followup.send(error_msg.format(value=new_value, statuses=valid_statuses), ephemeral=True)
                        return
                else: # Should not happen due to initial check
                    error_msg = await get_localized_message_template(
                         session, interaction.guild_id, "party_update:error_unknown_field_type", lang_code,
                        "Internal error: Unknown field type for '{field_name}'."
                    )
                    await interaction.followup.send(error_msg.format(field_name=db_field_name), ephemeral=True)
                    return

            except ValueError as e: # Catches int conversion errors primarily
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_update:error_invalid_value_type", lang_code,
                    "Invalid value '{value}' for field '{field_name}'. Expected type: {expected_type}. Details: {details}"
                )
                expected_type_str = field_type.__name__ if not isinstance(field_type, tuple) else 'int or None'
                if field_type == PartyTurnStatus: expected_type_str = "PartyTurnStatus enum name"
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, expected_type=expected_type_str, details=str(e)), ephemeral=True)
                return
            except json.JSONDecodeError as e:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_update:error_invalid_json", lang_code,
                    "Invalid JSON string '{value}' for field '{field_name}'. Details: {details}"
                )
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True)
                return

            # Fetch the party to update
            party_to_update = await party_crud.get_by_id_and_guild(session, id=party_id, guild_id=interaction.guild_id)
            if not party_to_update:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_update:error_party_not_found", lang_code,
                    "Party with ID {party_id} not found in this guild."
                )
                await interaction.followup.send(error_msg.format(party_id=party_id), ephemeral=True)
                return

            if db_field_name == "player_ids_json":
                original_player_ids_before_update = list(party_to_update.player_ids_json) if party_to_update.player_ids_json else []


            update_data_dict = {db_field_name: parsed_value}

            try:
                async with session.begin(): # Atomic update for party and potentially players
                    updated_party = await update_entity(session, entity=party_to_update, data=update_data_dict)

                    # If player_ids_json was updated, we need to manage Player.current_party_id
                    if db_field_name == "player_ids_json" and parsed_value is not None:
                        new_player_ids_set = set(parsed_value)
                        old_player_ids_set = set(original_player_ids_before_update if original_player_ids_before_update is not None else [])

                        players_to_remove_from_party = old_player_ids_set - new_player_ids_set
                        players_to_add_to_party = new_player_ids_set - old_player_ids_set

                        for p_id in players_to_remove_from_party:
                            player = await player_crud.get(session, id=p_id)
                            if player and player.current_party_id == updated_party.id:
                                player.current_party_id = None
                                session.add(player)

                        for p_id in players_to_add_to_party:
                            player = await player_crud.get(session, id=p_id)
                            if player: # Should exist due to earlier validation
                                player.current_party_id = updated_party.id
                                session.add(player)

                    await session.flush()
                    await session.refresh(updated_party)
            except Exception as e:
                logger.error(f"Error updating party {party_id} with data {update_data_dict}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_update:error_generic_update", lang_code,
                    "An error occurred while updating party {party_id}: {error_message}"
                )
                await interaction.followup.send(error_msg.format(party_id=party_id, error_message=str(e)), ephemeral=True)
                return

            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "party_update:success_title", lang_code,
                "Party Updated: {party_name} (ID: {party_id})"
            )
            updated_party_name_i18n = updated_party.name_i18n.get(lang_code, updated_party.name_i18n.get("en", f"Party {updated_party.id}"))
            embed = discord.Embed(title=success_title_template.format(party_name=updated_party_name_i18n, party_id=updated_party.id), color=discord.Color.orange())

            field_updated_label = await get_localized_message_template(session, interaction.guild_id, "party_update:label_field_updated", lang_code, "Field Updated")
            new_value_label = await get_localized_message_template(session, interaction.guild_id, "party_update:label_new_value", lang_code, "New Value")

            new_value_display = str(parsed_value)
            if isinstance(parsed_value, (dict, list)):
                new_value_display = f"```json\n{json.dumps(parsed_value, indent=2, ensure_ascii=False)}\n```"
            elif isinstance(parsed_value, PartyTurnStatus):
                new_value_display = parsed_value.name
            elif parsed_value is None:
                 new_value_display = "None"


            embed.add_field(name=field_updated_label, value=field_to_update, inline=True)
            embed.add_field(name=new_value_label, value=new_value_display, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @party_group.command(name="delete", description="Delete a party from this guild.")
    @app_commands.describe(party_id="The database ID of the party to delete.")
    async def party_delete(self, interaction: discord.Interaction, party_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_party import party_crud
        from src.core.crud.crud_player import player_crud # To update player's current_party_id
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            party_to_delete = await party_crud.get_by_id_and_guild(session, id=party_id, guild_id=interaction.guild_id)

            if not party_to_delete:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_delete:error_not_found", lang_code,
                    "Party with ID {party_id} not found in this guild. Nothing to delete."
                )
                await interaction.followup.send(error_msg.format(party_id=party_id), ephemeral=True)
                return

            party_name_for_message = party_to_delete.name_i18n.get(lang_code, party_to_delete.name_i18n.get("en", f"Party {party_to_delete.id}"))
            player_ids_in_party = list(party_to_delete.player_ids_json) if party_to_delete.player_ids_json else []

            try:
                async with session.begin():
                    # Set current_party_id to None for all players who were in this party
                    if player_ids_in_party:
                        for p_id in player_ids_in_party:
                            player = await player_crud.get(session, id=p_id)
                            if player and player.current_party_id == party_id:
                                player.current_party_id = None
                                session.add(player)

                    # CRUDBase.remove is not @transactional, relies on outer session.begin()
                    deleted_party = await party_crud.remove(session, id=party_id)
                    # remove returns the deleted object or None if not found (already checked)
                    # session.commit() handled by session.begin()

                if deleted_party: # Should always be true if party_to_delete was found
                    success_msg = await get_localized_message_template(
                        session, interaction.guild_id, "party_delete:success", lang_code,
                        "Party '{party_name}' (ID: {party_id}) has been deleted successfully."
                    )
                    await interaction.followup.send(success_msg.format(party_name=party_name_for_message, party_id=party_id), ephemeral=True)
                else: # Safeguard, should have been caught by party_to_delete check
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "party_delete:error_not_deleted_unknown", lang_code,
                        "Party (ID: {party_id}) was found but could not be deleted for an unknown reason."
                    )
                    await interaction.followup.send(error_msg.format(party_id=party_id), ephemeral=True)

            except Exception as e:
                # session.begin() handles rollback
                logger.error(f"Error deleting party {party_id} for guild {interaction.guild_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "party_delete:error_generic", lang_code,
                    "An error occurred while deleting party '{party_name}' (ID: {party_id}): {error_message}"
                )
                await interaction.followup.send(error_msg.format(party_name=party_name_for_message, party_id=party_id, error_message=str(e)), ephemeral=True)
                return

    # --- GeneratedNpc CRUD ---
    npc_group = app_commands.Group(name="npc", description="Master commands for managing Generated NPCs.", parent=master_admin)

    @npc_group.command(name="view", description="View details of a specific Generated NPC.")
    @app_commands.describe(npc_id="The database ID of the NPC to view.")
    async def npc_view(self, interaction: discord.Interaction, npc_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_npc import npc_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            npc = await npc_crud.get_by_id_and_guild(session, id=npc_id, guild_id=interaction.guild_id)

            if not npc:
                not_found_msg_template = await get_localized_message_template(
                    session, interaction.guild_id, "npc_view:not_found", lang_code,
                    "NPC with ID {npc_id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg_template.format(npc_id=npc_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "npc_view:title", lang_code,
                "NPC Details: {npc_name} (ID: {npc_id})"
            )

            npc_name_display = npc.name_i18n.get(lang_code, npc.name_i18n.get("en", f"NPC {npc.id}"))
            embed_title = title_template.format(npc_name=npc_name_display, npc_id=npc.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.blurple())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"npc_view:label_{key}", lang_code, default)

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(npc.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=npc.static_id or "N/A", inline=True)
            embed.add_field(name=await get_label("faction_id", "Faction ID"), value=str(npc.faction_id) if npc.faction_id else "N/A", inline=True)
            embed.add_field(name=await get_label("location_id", "Location ID"), value=str(npc.current_location_id) if npc.current_location_id else "N/A", inline=True)

            name_i18n_str = await get_localized_message_template(session, interaction.guild_id, "npc_view:value_na_json", lang_code, "Not available")
            if npc.name_i18n:
                try: name_i18n_str = json.dumps(npc.name_i18n, indent=2, ensure_ascii=False)
                except TypeError: name_i18n_str = await get_localized_message_template(session, interaction.guild_id, "npc_view:error_serialization", lang_code, "Error serializing Name i18n")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```" + ("..." if len(name_i18n_str) > 1000 else ""), inline=False)

            description_i18n_str = await get_localized_message_template(session, interaction.guild_id, "npc_view:value_na_json", lang_code, "Not available")
            if npc.description_i18n:
                try: description_i18n_str = json.dumps(npc.description_i18n, indent=2, ensure_ascii=False)
                except TypeError: description_i18n_str = await get_localized_message_template(session, interaction.guild_id, "npc_view:error_serialization", lang_code, "Error serializing Description i18n")
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{description_i18n_str[:1000]}\n```" + ("..." if len(description_i18n_str) > 1000 else ""), inline=False)

            properties_str = await get_localized_message_template(session, interaction.guild_id, "npc_view:value_na_json", lang_code, "Not available")
            if npc.properties_json:
                try: properties_str = json.dumps(npc.properties_json, indent=2, ensure_ascii=False)
                except TypeError: properties_str = await get_localized_message_template(session, interaction.guild_id, "npc_view:error_serialization", lang_code, "Error serializing Properties JSON")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{properties_str[:1000]}\n```" + ("..." if len(properties_str) > 1000 else ""), inline=False)

            # TODO: Consider showing inventory items if relevant and if InventoryItem CRUD exists and is easy to integrate.
            # For now, keeping it simple.

            await interaction.followup.send(embed=embed, ephemeral=True)

    @npc_group.command(name="list", description="List Generated NPCs in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of NPCs per page.")
    async def npc_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10

        from src.core.crud.crud_npc import npc_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import func, select

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            offset = (page - 1) * limit
            npcs = await npc_crud.get_multi_by_guild(session, guild_id=interaction.guild_id, skip=offset, limit=limit)

            total_npcs_stmt = select(func.count(npc_crud.model.id)).where(npc_crud.model.guild_id == interaction.guild_id)
            total_npcs_result = await session.execute(total_npcs_stmt)
            total_npcs = total_npcs_result.scalar_one_or_none() or 0

            if not npcs:
                no_npcs_msg = await get_localized_message_template(
                    session, interaction.guild_id, "npc_list:no_npcs_found_page", lang_code,
                    "No NPCs found for this guild (Page {page})."
                )
                await interaction.followup.send(no_npcs_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "npc_list:title", lang_code,
                "Generated NPC List (Page {page} of {total_pages})"
            )
            total_pages = ((total_npcs - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.light_grey())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "npc_list:footer", lang_code,
                "Displaying {count} of {total} total NPCs."
            )
            embed.set_footer(text=footer_template.format(count=len(npcs), total=total_npcs))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "npc_list:npc_field_name", lang_code,
                "ID: {npc_id} | {npc_name} (Static: {static_id})"
            )
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "npc_list:npc_field_value", lang_code,
                "Faction ID: {faction_id}, Location ID: {location_id}"
            )

            for n in npcs:
                npc_name_display = n.name_i18n.get(lang_code, n.name_i18n.get("en", f"NPC {n.id}"))
                embed.add_field(
                    name=field_name_template.format(npc_id=n.id, npc_name=npc_name_display, static_id=n.static_id or "N/A"),
                    value=field_value_template.format(
                        faction_id=str(n.faction_id) if n.faction_id else "N/A",
                        location_id=str(n.current_location_id) if n.current_location_id else "N/A"
                    ),
                    inline=False
                )

            if len(embed.fields) == 0:
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "npc_list:no_npcs_to_display", lang_code,
                    "No NPCs found to display on page {page}."
                )
                await interaction.followup.send(no_display_msg.format(page=page), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @npc_group.command(name="create", description="Create a new Generated NPC in this guild.")
    @app_commands.describe(
        static_id="Optional: Static ID for this NPC.",
        name_i18n_json="JSON string for NPC name (e.g., {\"en\": \"Guard\", \"ru\": \"Стражник\"}).",
        description_i18n_json="Optional: JSON string for NPC description.",
        faction_id="Optional: Database ID of the faction this NPC belongs to.",
        current_location_id="Optional: Database ID of the NPC's current location.",
        properties_json="Optional: JSON string for additional NPC properties (e.g., stats, role)."
        # inventory_items_json: Optional: JSON string for items in NPC's inventory. Later.
    )
    async def npc_create(self, interaction: discord.Interaction,
                         name_i18n_json: str,
                         static_id: Optional[str] = None,
                         description_i18n_json: Optional[str] = None,
                         faction_id: Optional[int] = None,
                         current_location_id: Optional[int] = None,
                         properties_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_npc import npc_crud
        from src.core.crud.crud_faction import crud_faction # To validate faction_id
        from src.core.crud.crud_location import location_crud # To validate location_id
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any, List # For type hints

        lang_code = str(interaction.locale)
        parsed_name_i18n: Dict[str, str]
        parsed_description_i18n: Optional[Dict[str, str]] = None
        parsed_properties: Optional[Dict[str, Any]] = None

        async with get_db_session() as session: # Session for all operations
            # Validate faction_id if provided
            if faction_id:
                existing_faction = await crud_faction.get_by_id_and_guild(session, id=faction_id, guild_id=interaction.guild_id)
                if not existing_faction:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "npc_create:error_faction_not_found", lang_code,
                        "Faction with ID {id} not found in this guild."
                    )
                    await interaction.followup.send(error_msg.format(id=faction_id), ephemeral=True)
                    return

            # Validate current_location_id if provided
            if current_location_id:
                existing_location = await location_crud.get_by_id_and_guild(session, id=current_location_id, guild_id=interaction.guild_id)
                if not existing_location:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "npc_create:error_location_not_found", lang_code,
                        "Location with ID {id} not found in this guild."
                    )
                    await interaction.followup.send(error_msg.format(id=current_location_id), ephemeral=True)
                    return

            # Validate static_id uniqueness if provided
            if static_id:
                existing_npc_static = await npc_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=static_id)
                if existing_npc_static:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "npc_create:error_static_id_exists", lang_code,
                        "An NPC with static_id '{id}' already exists in this guild."
                    )
                    await interaction.followup.send(error_msg.format(id=static_id), ephemeral=True)
                    return

            try:
                parsed_name_i18n = json.loads(name_i18n_json)
                if not isinstance(parsed_name_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_name_i18n.items()):
                    raise ValueError("name_i18n_json must be a dictionary of string keys and string values.")
                if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code): # Must have at least one common language
                     raise ValueError("name_i18n_json must contain at least an 'en' key or a key for the current interaction language.")


                if description_i18n_json:
                    parsed_description_i18n = json.loads(description_i18n_json)
                    if not isinstance(parsed_description_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_description_i18n.items()):
                        raise ValueError("description_i18n_json must be a dictionary of string keys and string values.")

                if properties_json:
                    parsed_properties = json.loads(properties_json)
                    if not isinstance(parsed_properties, dict):
                        raise ValueError("properties_json must be a dictionary.")
            except (json.JSONDecodeError, ValueError) as e:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "npc_create:error_invalid_json_format", lang_code,
                    "Invalid JSON format for one of the input fields: {error_details}"
                )
                await interaction.followup.send(error_msg.format(error_details=str(e)), ephemeral=True)
                return

            npc_data_to_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id,
                "static_id": static_id,
                "name_i18n": parsed_name_i18n,
                "description_i18n": parsed_description_i18n if parsed_description_i18n else {},
                "faction_id": faction_id,
                "current_location_id": current_location_id,
                "properties_json": parsed_properties if parsed_properties else {},
                # "inventory_items_json": [], # For future
            }

            try:
                async with session.begin():
                    created_npc = await npc_crud.create(session, obj_in=npc_data_to_create)
                    await session.flush()
                    if created_npc:
                         await session.refresh(created_npc)
            except Exception as e:
                logger.error(f"Error creating NPC with data {npc_data_to_create}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "npc_create:error_generic_create", lang_code,
                    "An error occurred while creating the NPC: {error_message}"
                )
                await interaction.followup.send(error_msg.format(error_message=str(e)), ephemeral=True)
                return

            if not created_npc:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "npc_create:error_creation_failed_unknown", lang_code,
                    "NPC creation failed for an unknown reason."
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "npc_create:success_title", lang_code,
                "NPC Created: {npc_name} (ID: {npc_id})"
            )
            created_npc_name_display = created_npc.name_i18n.get(lang_code, created_npc.name_i18n.get("en", f"NPC {created_npc.id}"))

            embed = discord.Embed(title=success_title_template.format(npc_name=created_npc_name_display, npc_id=created_npc.id), color=discord.Color.green())
            embed.add_field(name="Static ID", value=created_npc.static_id or "N/A", inline=True)
            embed.add_field(name="Faction ID", value=str(created_npc.faction_id) if created_npc.faction_id else "N/A", inline=True)
            embed.add_field(name="Location ID", value=str(created_npc.current_location_id) if created_npc.current_location_id else "N/A", inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @npc_group.command(name="update", description="Update a specific field for a Generated NPC.")
    @app_commands.describe(
        npc_id="The database ID of the NPC to update.",
        field_to_update="Field to update (e.g., static_id, name_i18n_json, faction_id, current_location_id, properties_json).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable fields)."
    )
    async def npc_update(self, interaction: discord.Interaction, npc_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_npc import npc_crud
        from src.core.crud.crud_faction import crud_faction
        from src.core.crud.crud_location import location_crud
        from src.core.database import get_db_session
        from src.core.crud_base_definitions import update_entity
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any, Optional, Union # For type hints

        allowed_fields = {
            "static_id": (str, type(None)), # Allow setting static_id to None or a new string
            "name_i18n_json": dict,
            "description_i18n_json": dict,
            "faction_id": (int, type(None)),
            "current_location_id": (int, type(None)),
            "properties_json": dict,
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()

        db_field_name = field_to_update_lower
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")

        field_type = allowed_fields.get(db_field_name)

        if not field_type:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "npc_update:error_field_not_allowed", lang_code,
                    "Field '{field_name}' is not allowed for update. Allowed: {allowed_list}"
                )
            await interaction.followup.send(error_msg.format(field_name=field_to_update, allowed_list=', '.join(allowed_fields.keys())), ephemeral=True)
            return

        parsed_value: Any = None

        async with get_db_session() as session: # Session for validation and update
            try:
                if db_field_name == "static_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = new_value
                        # Validate static_id uniqueness if being set to a new non-null value
                        existing_npc_static = await npc_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                        if existing_npc_static and existing_npc_static.id != npc_id: # Check it's not the same NPC
                            error_msg = await get_localized_message_template(
                                session, interaction.guild_id, "npc_update:error_static_id_exists", lang_code,
                                "Another NPC with static_id '{id}' already exists."
                            )
                            await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True)
                            return
                elif db_field_name == "name_i18n":
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_value.items()):
                        raise ValueError("name_i18n must be a dictionary of string keys and string values.")
                elif db_field_name == "description_i18n":
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_value.items()):
                        raise ValueError("description_i18n must be a dictionary of string keys and string values.")
                elif db_field_name == "faction_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = int(new_value)
                        if parsed_value is not None: # Validate faction exists
                            existing_faction = await crud_faction.get_by_id_and_guild(session, id=parsed_value, guild_id=interaction.guild_id)
                            if not existing_faction:
                                error_msg = await get_localized_message_template(
                                    session, interaction.guild_id, "npc_update:error_faction_not_found", lang_code,
                                    "Faction with ID {id} not found."
                                )
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True)
                                return
                elif db_field_name == "current_location_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = int(new_value)
                        if parsed_value is not None: # Validate location exists
                            existing_location = await location_crud.get_by_id_and_guild(session, id=parsed_value, guild_id=interaction.guild_id)
                            if not existing_location:
                                error_msg = await get_localized_message_template(
                                    session, interaction.guild_id, "npc_update:error_location_not_found", lang_code,
                                    "Location with ID {id} not found."
                                )
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True)
                                return
                elif db_field_name == "properties_json":
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict):
                        raise ValueError("properties_json must be a dictionary.")
                else: # Should not happen
                     error_msg = await get_localized_message_template(
                         session, interaction.guild_id, "npc_update:error_unknown_field_type", lang_code,
                        "Internal error: Unknown field type for '{field_name}'."
                    )
                     await interaction.followup.send(error_msg.format(field_name=db_field_name), ephemeral=True)
                     return

            except ValueError as e:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "npc_update:error_invalid_value_type", lang_code,
                    "Invalid value '{value}' for field '{field_name}'. Expected type: {expected_type}. Details: {details}"
                )
                expected_type_str = field_type.__name__ if not isinstance(field_type, tuple) else 'str/int or None'
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, expected_type=expected_type_str, details=str(e)), ephemeral=True)
                return
            except json.JSONDecodeError as e:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "npc_update:error_invalid_json", lang_code,
                    "Invalid JSON string '{value}' for field '{field_name}'. Details: {details}"
                )
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True)
                return

            npc_to_update = await npc_crud.get_by_id_and_guild(session, id=npc_id, guild_id=interaction.guild_id)
            if not npc_to_update:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "npc_update:error_npc_not_found", lang_code,
                    "NPC with ID {id} not found in this guild."
                )
                await interaction.followup.send(error_msg.format(id=npc_id), ephemeral=True)
                return

            update_data_dict = {db_field_name: parsed_value}

            try:
                async with session.begin():
                    updated_npc = await update_entity(session, entity=npc_to_update, data=update_data_dict)
                    await session.flush()
                    await session.refresh(updated_npc)
            except Exception as e:
                logger.error(f"Error updating NPC {npc_id} with data {update_data_dict}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "npc_update:error_generic_update", lang_code,
                    "An error occurred while updating NPC {id}: {error_message}"
                )
                await interaction.followup.send(error_msg.format(id=npc_id, error_message=str(e)), ephemeral=True)
                return

            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "npc_update:success_title", lang_code,
                "NPC Updated: {npc_name} (ID: {npc_id})"
            )
            updated_npc_name_display = updated_npc.name_i18n.get(lang_code, updated_npc.name_i18n.get("en", f"NPC {updated_npc.id}"))
            embed = discord.Embed(title=success_title_template.format(npc_name=updated_npc_name_display, npc_id=updated_npc.id), color=discord.Color.orange())

            field_updated_label = await get_localized_message_template(session, interaction.guild_id, "npc_update:label_field_updated", lang_code, "Field Updated")
            new_value_label = await get_localized_message_template(session, interaction.guild_id, "npc_update:label_new_value", lang_code, "New Value")

            new_value_display = str(parsed_value)
            if isinstance(parsed_value, (dict, list)):
                new_value_display = f"```json\n{json.dumps(parsed_value, indent=2, ensure_ascii=False)}\n```"
            elif parsed_value is None:
                 new_value_display = "None"

            embed.add_field(name=field_updated_label, value=field_to_update, inline=True)
            embed.add_field(name=new_value_label, value=new_value_display, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @npc_group.command(name="delete", description="Delete a Generated NPC from this guild.")
    @app_commands.describe(npc_id="The database ID of the NPC to delete.")
    async def npc_delete(self, interaction: discord.Interaction, npc_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_npc import npc_crud
        # from src.core.crud.crud_inventory_item import inventory_item_crud # If NPC deletion should clear inventory
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            npc_to_delete = await npc_crud.get_by_id_and_guild(session, id=npc_id, guild_id=interaction.guild_id)

            if not npc_to_delete:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "npc_delete:error_not_found", lang_code,
                    "NPC with ID {id} not found. Nothing to delete."
                )
                await interaction.followup.send(error_msg.format(id=npc_id), ephemeral=True)
                return

            npc_name_for_message = npc_to_delete.name_i18n.get(lang_code, npc_to_delete.name_i18n.get("en", f"NPC {npc_to_delete.id}"))

            # TODO: Consider related data:
            # - InventoryItem: Delete items owned by this NPC.
            # - Relationships: Delete relationships involving this NPC.
            # - PlayerNpcMemory: Delete memory entries related to this NPC.
            # - ActiveStatusEffect: Delete statuses on this NPC.
            # - Quest assignments, etc.
            # For now, simple delete of the NPC record. Cascades in DB might handle some.

            try:
                async with session.begin():
                    # Before deleting NPC, handle inventory if InventoryItem model and CRUD exist
                    # from src.models.inventory_item import OwnerEntityType
                    # from src.core.crud.crud_inventory_item import inventory_item_crud # Placed here to avoid import if not used
                    # await inventory_item_crud.remove_all_for_owner(session, owner_id=npc_id, owner_type=OwnerEntityType.GENERATED_NPC)
                    # logger.info(f"Cleared inventory for NPC ID {npc_id} before deletion.")

                    deleted_npc = await npc_crud.remove(session, id=npc_id)

                if deleted_npc:
                    success_msg = await get_localized_message_template(
                        session, interaction.guild_id, "npc_delete:success", lang_code,
                        "NPC '{name}' (ID: {id}) has been deleted successfully."
                    )
                    await interaction.followup.send(success_msg.format(name=npc_name_for_message, id=npc_id), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "npc_delete:error_not_deleted_unknown", lang_code,
                        "NPC (ID: {id}) was found but could not be deleted."
                    )
                    await interaction.followup.send(error_msg.format(id=npc_id), ephemeral=True)

            except Exception as e:
                logger.error(f"Error deleting NPC {npc_id} for guild {interaction.guild_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "npc_delete:error_generic", lang_code,
                    "An error occurred while deleting NPC '{name}' (ID: {id}): {error_message}"
                )
                await interaction.followup.send(error_msg.format(name=npc_name_for_message, id=npc_id, error_message=str(e)), ephemeral=True)
                return

    # --- Location CRUD ---
    location_group = app_commands.Group(name="location", description="Master commands for managing Locations.", parent=master_admin)

    @location_group.command(name="view", description="View details of a specific Location.")
    @app_commands.describe(location_id="The database ID of the Location to view.")
    async def location_view(self, interaction: discord.Interaction, location_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_location import location_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            loc = await location_crud.get_by_id_and_guild(session, id=location_id, guild_id=interaction.guild_id)

            if not loc:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_view:not_found", lang_code,
                    "Location with ID {id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg.format(id=location_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "location_view:title", lang_code,
                "Location Details: {loc_name} (ID: {loc_id})"
            )

            loc_name_display = loc.name_i18n.get(lang_code, loc.name_i18n.get("en", f"Location {loc.id}"))
            embed_title = title_template.format(loc_name=loc_name_display, loc_id=loc.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_green())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"location_view:label_{key}", lang_code, default)

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(loc.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=loc.static_id or "N/A", inline=True)
            embed.add_field(name=await get_label("type", "Type"), value=loc.type.value if loc.type else "N/A", inline=True)
            embed.add_field(name=await get_label("parent_id", "Parent ID"), value=str(loc.parent_location_id) if loc.parent_location_id else "N/A", inline=True)

            name_i18n_str = await get_localized_message_template(session, interaction.guild_id, "location_view:value_na_json", lang_code, "Not available")
            if loc.name_i18n:
                try: name_i18n_str = json.dumps(loc.name_i18n, indent=2, ensure_ascii=False)
                except TypeError: name_i18n_str = await get_localized_message_template(session, interaction.guild_id, "location_view:error_serialization", lang_code, "Error serializing Name i18n")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```" + ("..." if len(name_i18n_str) > 1000 else ""), inline=False)

            desc_i18n_str = await get_localized_message_template(session, interaction.guild_id, "location_view:value_na_json", lang_code, "Not available")
            if loc.description_i18n:
                try: desc_i18n_str = json.dumps(loc.description_i18n, indent=2, ensure_ascii=False)
                except TypeError: desc_i18n_str = await get_localized_message_template(session, interaction.guild_id, "location_view:error_serialization", lang_code, "Error serializing Description i18n")
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```" + ("..." if len(desc_i18n_str) > 1000 else ""), inline=False)

            props_str = await get_localized_message_template(session, interaction.guild_id, "location_view:value_na_json", lang_code, "Not available")
            if loc.properties_json:
                try: props_str = json.dumps(loc.properties_json, indent=2, ensure_ascii=False)
                except TypeError: props_str = await get_localized_message_template(session, interaction.guild_id, "location_view:error_serialization", lang_code, "Error serializing Properties JSON")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{props_str[:1000]}\n```" + ("..." if len(props_str) > 1000 else ""), inline=False)

            neighbors_str = await get_localized_message_template(session, interaction.guild_id, "location_view:value_na_json", lang_code, "Not available")
            if loc.neighbor_locations_json:
                try: neighbors_str = json.dumps(loc.neighbor_locations_json, indent=2, ensure_ascii=False)
                except TypeError: neighbors_str = await get_localized_message_template(session, interaction.guild_id, "location_view:error_serialization", lang_code, "Error serializing Neighbors JSON")
            embed.add_field(name=await get_label("neighbors", "Neighbor Locations JSON"), value=f"```json\n{neighbors_str[:1000]}\n```" + ("..." if len(neighbors_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @location_group.command(name="list", description="List Locations in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of Locations per page.")
    async def location_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10

        from src.core.crud.crud_location import location_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import func, select

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            offset = (page - 1) * limit
            locations = await location_crud.get_multi_by_guild(session, guild_id=interaction.guild_id, skip=offset, limit=limit)

            total_locations_stmt = select(func.count(location_crud.model.id)).where(location_crud.model.guild_id == interaction.guild_id)
            total_locations_result = await session.execute(total_locations_stmt)
            total_locations = total_locations_result.scalar_one_or_none() or 0

            if not locations:
                no_locs_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_list:no_locations_found_page", lang_code,
                    "No Locations found for this guild (Page {page})."
                )
                await interaction.followup.send(no_locs_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "location_list:title", lang_code,
                "Location List (Page {page} of {total_pages})"
            )
            total_pages = ((total_locations - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_blue())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "location_list:footer", lang_code,
                "Displaying {count} of {total} total Locations."
            )
            embed.set_footer(text=footer_template.format(count=len(locations), total=total_locations))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "location_list:location_field_name", lang_code,
                "ID: {loc_id} | {loc_name} (Static: {static_id})"
            )
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "location_list:location_field_value", lang_code,
                "Type: {type}, Parent ID: {parent_id}, Neighbors: {neighbor_count}"
            )

            for loc in locations:
                loc_name_display = loc.name_i18n.get(lang_code, loc.name_i18n.get("en", f"Location {loc.id}"))
                neighbor_count = len(loc.neighbor_locations_json) if loc.neighbor_locations_json else 0
                embed.add_field(
                    name=field_name_template.format(loc_id=loc.id, loc_name=loc_name_display, static_id=loc.static_id or "N/A"),
                    value=field_value_template.format(
                        type=loc.type.value if loc.type else "N/A",
                        parent_id=str(loc.parent_location_id) if loc.parent_location_id else "N/A",
                        neighbor_count=neighbor_count
                    ),
                    inline=False
                )

            if len(embed.fields) == 0:
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_list:no_locations_to_display", lang_code,
                    "No Locations found to display on page {page}."
                )
                await interaction.followup.send(no_display_msg.format(page=page), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @location_group.command(name="create", description="Create a new Location in this guild.")
    @app_commands.describe(
        static_id="Optional: Static ID for this Location (must be unique within the guild).",
        name_i18n_json="JSON string for Location name (e.g., {\"en\": \"Town Square\", \"ru\": \"Городская площадь\"}).",
        type_name="Type of location (e.g., TOWN, FOREST, DUNGEON_ROOM, BUILDING_INTERIOR). See LocationType enum.",
        description_i18n_json="Optional: JSON string for Location description.",
        parent_location_id="Optional: Database ID of the parent Location.",
        properties_json="Optional: JSON string for additional Location properties.",
        neighbor_locations_json="Optional: JSON string for neighbor connections (e.g., [{\"target_static_id\": \"forest_path_1\", \"description_i18n\": {\"en\": \"Path to forest\"}}])."
    )
    async def location_create(self, interaction: discord.Interaction,
                              name_i18n_json: str,
                              type_name: str,
                              static_id: Optional[str] = None,
                              description_i18n_json: Optional[str] = None,
                              parent_location_id: Optional[int] = None,
                              properties_json: Optional[str] = None,
                              neighbor_locations_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_location import location_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from src.models.location import LocationType # For enum conversion
        from typing import Dict, Any, List # For type hints

        lang_code = str(interaction.locale)
        parsed_name_i18n: Dict[str, str]
        parsed_description_i18n: Optional[Dict[str, str]] = None
        parsed_properties: Optional[Dict[str, Any]] = None
        parsed_neighbors: Optional[List[Dict[str, Any]]] = None
        parsed_location_type: LocationType

        async with get_db_session() as session: # Session for all operations
            # Validate type_name
            try:
                parsed_location_type = LocationType[type_name.upper()]
            except KeyError:
                valid_types = ", ".join([lt.name for lt in LocationType])
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_create:error_invalid_type", lang_code,
                    "Invalid type_name '{type_val}'. Valid types: {valid_list}"
                )
                await interaction.followup.send(error_msg.format(type_val=type_name, valid_list=valid_types), ephemeral=True)
                return

            # Validate parent_location_id if provided
            if parent_location_id:
                parent_loc = await location_crud.get_by_id_and_guild(session, id=parent_location_id, guild_id=interaction.guild_id)
                if not parent_loc:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "location_create:error_parent_not_found", lang_code,
                        "Parent Location with ID {id} not found."
                    )
                    await interaction.followup.send(error_msg.format(id=parent_location_id), ephemeral=True)
                    return

            # Validate static_id uniqueness if provided
            if static_id:
                existing_loc_static = await location_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=static_id)
                if existing_loc_static:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "location_create:error_static_id_exists", lang_code,
                        "A Location with static_id '{id}' already exists."
                    )
                    await interaction.followup.send(error_msg.format(id=static_id), ephemeral=True)
                    return

            try:
                parsed_name_i18n = json.loads(name_i18n_json)
                if not isinstance(parsed_name_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_name_i18n.items()):
                    raise ValueError("name_i18n_json must be a dict of str:str.")
                if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code):
                     raise ValueError("name_i18n_json must contain 'en' or current language key.")

                if description_i18n_json:
                    parsed_description_i18n = json.loads(description_i18n_json)
                    if not isinstance(parsed_description_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_description_i18n.items()):
                        raise ValueError("description_i18n_json must be a dict of str:str.")

                if properties_json:
                    parsed_properties = json.loads(properties_json)
                    if not isinstance(parsed_properties, dict):
                        raise ValueError("properties_json must be a dictionary.")

                if neighbor_locations_json:
                    parsed_neighbors = json.loads(neighbor_locations_json)
                    if not isinstance(parsed_neighbors, list) or not all(isinstance(n, dict) for n in parsed_neighbors):
                        raise ValueError("neighbor_locations_json must be a list of dictionaries.")
                    # Further validation of neighbor structure can be added here if needed
                    # e.g., check for 'target_static_id' in each neighbor dict.
                    for neighbor_entry in parsed_neighbors:
                        if not isinstance(neighbor_entry.get("target_static_id"), str):
                            raise ValueError("Each entry in neighbor_locations_json must have a 'target_static_id' (string).")
                        if "description_i18n" in neighbor_entry and (
                            not isinstance(neighbor_entry["description_i18n"], dict) or \
                            not all(isinstance(k, str) and isinstance(v, str) for k,v in neighbor_entry["description_i18n"].items())
                        ):
                            raise ValueError("Neighbor 'description_i18n' must be a dict of str:str if provided.")


            except (json.JSONDecodeError, ValueError) as e:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_create:error_invalid_json_format", lang_code,
                    "Invalid JSON format or structure for one of the input fields: {error_details}"
                )
                await interaction.followup.send(error_msg.format(error_details=str(e)), ephemeral=True)
                return

            location_data_to_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id,
                "static_id": static_id,
                "name_i18n": parsed_name_i18n,
                "description_i18n": parsed_description_i18n if parsed_description_i18n else {},
                "type": parsed_location_type,
                "parent_location_id": parent_location_id,
                "properties_json": parsed_properties if parsed_properties else {},
                "neighbor_locations_json": parsed_neighbors if parsed_neighbors else [],
            }

            try:
                async with session.begin():
                    # create_with_guild ensures guild_id is handled correctly by CRUDBase.create
                    created_location = await location_crud.create_with_guild(session, obj_in=location_data_to_create, guild_id=interaction.guild_id)
                    await session.flush()
                    if created_location:
                         await session.refresh(created_location)
            except Exception as e:
                logger.error(f"Error creating Location with data {location_data_to_create}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_create:error_generic_create", lang_code,
                    "An error occurred while creating the Location: {error_message}"
                )
                await interaction.followup.send(error_msg.format(error_message=str(e)), ephemeral=True)
                return

            if not created_location:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_create:error_creation_failed_unknown", lang_code,
                    "Location creation failed for an unknown reason."
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "location_create:success_title", lang_code,
                "Location Created: {loc_name} (ID: {loc_id})"
            )
            created_loc_name_display = created_location.name_i18n.get(lang_code, created_location.name_i18n.get("en", f"Location {created_location.id}"))

            embed = discord.Embed(title=success_title_template.format(loc_name=created_loc_name_display, loc_id=created_location.id), color=discord.Color.green())
            embed.add_field(name="Static ID", value=created_location.static_id or "N/A", inline=True)
            embed.add_field(name="Type", value=created_location.type.value, inline=True)
            embed.add_field(name="Parent ID", value=str(created_location.parent_location_id) if created_location.parent_location_id else "N/A", inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @location_group.command(name="update", description="Update a specific field for a Location.")
    @app_commands.describe(
        location_id="The database ID of the Location to update.",
        field_to_update="Field to update (e.g., static_id, name_i18n_json, type_name, parent_location_id, properties_json, neighbor_locations_json).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable fields; enum name for type_name)."
    )
    async def location_update(self, interaction: discord.Interaction, location_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_location import location_crud
        from src.core.database import get_db_session
        from src.core.crud_base_definitions import update_entity
        from src.core.localization_utils import get_localized_message_template
        from src.models.location import LocationType # For enum conversion
        from typing import Dict, Any, Optional, Union, List # For type hints

        allowed_fields = {
            "static_id": (str, type(None)),
            "name_i18n_json": dict,
            "description_i18n_json": dict,
            "type_name": LocationType, # Handled as string input, converted to enum
            "parent_location_id": (int, type(None)),
            "properties_json": dict,
            "neighbor_locations_json": list,
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()

        db_field_name = field_to_update_lower
        # Adjust for fields that are named differently in DB vs command (e.g. type vs type_name)
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")
        elif field_to_update_lower == "type_name":
            db_field_name = "type"


        field_type_info = allowed_fields.get(field_to_update_lower) # Use original command field name for lookup

        if not field_type_info:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "location_update:error_field_not_allowed", lang_code,
                    "Field '{field_name}' is not allowed for update. Allowed: {allowed_list}"
                )
            await interaction.followup.send(error_msg.format(field_name=field_to_update, allowed_list=', '.join(allowed_fields.keys())), ephemeral=True)
            return

        parsed_value: Any = None

        async with get_db_session() as session: # Session for validation and update
            try:
                if db_field_name == "static_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = new_value
                        if parsed_value is not None: # Validate uniqueness if not None
                            existing_loc_static = await location_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                            if existing_loc_static and existing_loc_static.id != location_id:
                                error_msg = await get_localized_message_template(
                                    session, interaction.guild_id, "location_update:error_static_id_exists", lang_code,
                                    "Another Location with static_id '{id}' already exists."
                                )
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True)
                                return
                elif db_field_name == "name_i18n" or db_field_name == "description_i18n" or db_field_name == "properties_json":
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict):
                        raise ValueError(f"{db_field_name} must be a dictionary.")
                elif db_field_name == "neighbor_locations_json":
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, list) or not all(isinstance(n, dict) for n in parsed_value):
                        raise ValueError("neighbor_locations_json must be a list of dictionaries.")
                    for neighbor_entry in parsed_value: # Basic validation
                        if not isinstance(neighbor_entry.get("target_static_id"), str):
                            raise ValueError("Neighbor entry missing 'target_static_id'.")
                elif db_field_name == "type": # From type_name
                    try:
                        parsed_value = LocationType[new_value.upper()]
                    except KeyError:
                        valid_types = ", ".join([lt.name for lt in LocationType])
                        error_msg = await get_localized_message_template(
                            session, interaction.guild_id, "location_update:error_invalid_type", lang_code,
                            "Invalid type_name '{value}'. Valid types: {types}"
                        )
                        await interaction.followup.send(error_msg.format(value=new_value, types=valid_types), ephemeral=True)
                        return
                elif db_field_name == "parent_location_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = int(new_value)
                        if parsed_value is not None: # Validate parent exists
                            parent_loc = await location_crud.get_by_id_and_guild(session, id=parsed_value, guild_id=interaction.guild_id)
                            if not parent_loc:
                                error_msg = await get_localized_message_template(
                                    session, interaction.guild_id, "location_update:error_parent_not_found", lang_code,
                                    "Parent Location with ID {id} not found."
                                )
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True)
                                return
                            if parent_loc.id == location_id: # Prevent self-parenting
                                error_msg = await get_localized_message_template(
                                    session, interaction.guild_id, "location_update:error_self_parent", lang_code,
                                    "Location cannot be its own parent."
                                )
                                await interaction.followup.send(error_msg, ephemeral=True)
                                return
                else:
                     error_msg = await get_localized_message_template(
                         session, interaction.guild_id, "location_update:error_unknown_field_type", lang_code,
                        "Internal error: Unknown field type for '{field_name}'."
                    )
                     await interaction.followup.send(error_msg.format(field_name=db_field_name), ephemeral=True)
                     return

            except ValueError as e:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_update:error_invalid_value_type", lang_code,
                    "Invalid value '{value}' for field '{field_name}'. Details: {details}"
                )
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True)
                return
            except json.JSONDecodeError as e:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_update:error_invalid_json", lang_code,
                    "Invalid JSON string '{value}' for field '{field_name}'. Details: {details}"
                )
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True)
                return

            location_to_update = await location_crud.get_by_id_and_guild(session, id=location_id, guild_id=interaction.guild_id)
            if not location_to_update:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_update:error_location_not_found", lang_code,
                    "Location with ID {id} not found."
                )
                await interaction.followup.send(error_msg.format(id=location_id), ephemeral=True)
                return

            update_data_dict = {db_field_name: parsed_value}

            try:
                async with session.begin():
                    updated_location = await update_entity(session, entity=location_to_update, data=update_data_dict)
                    await session.flush()
                    await session.refresh(updated_location)
            except Exception as e:
                logger.error(f"Error updating Location {location_id} with data {update_data_dict}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_update:error_generic_update", lang_code,
                    "An error occurred while updating Location {id}: {error_message}"
                )
                await interaction.followup.send(error_msg.format(id=location_id, error_message=str(e)), ephemeral=True)
                return

            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "location_update:success_title", lang_code,
                "Location Updated: {loc_name} (ID: {loc_id})"
            )
            updated_loc_name_display = updated_location.name_i18n.get(lang_code, updated_location.name_i18n.get("en", f"Location {updated_location.id}"))
            embed = discord.Embed(title=success_title_template.format(loc_name=updated_loc_name_display, loc_id=updated_location.id), color=discord.Color.orange())

            field_updated_label = await get_localized_message_template(session, interaction.guild_id, "location_update:label_field_updated", lang_code, "Field Updated")
            new_value_label = await get_localized_message_template(session, interaction.guild_id, "location_update:label_new_value", lang_code, "New Value")

            new_value_display = str(parsed_value)
            if isinstance(parsed_value, (dict, list)):
                new_value_display = f"```json\n{json.dumps(parsed_value, indent=2, ensure_ascii=False)}\n```"
            elif isinstance(parsed_value, LocationType):
                new_value_display = parsed_value.name
            elif parsed_value is None:
                 new_value_display = "None"

            embed.add_field(name=field_updated_label, value=field_to_update, inline=True) # Show original field name from command
            embed.add_field(name=new_value_label, value=new_value_display, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @location_group.command(name="delete", description="Delete a Location from this guild.")
    @app_commands.describe(location_id="The database ID of the Location to delete.")
    async def location_delete(self, interaction: discord.Interaction, location_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_location import location_crud
        # Need to check for players/NPCs in location, child locations, and neighbor links
        from src.core.crud.crud_player import player_crud
        from src.core.crud.crud_npc import npc_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import select, or_

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            location_to_delete = await location_crud.get_by_id_and_guild(session, id=location_id, guild_id=interaction.guild_id)

            if not location_to_delete:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_delete:error_not_found", lang_code,
                    "Location with ID {id} not found. Nothing to delete."
                )
                await interaction.followup.send(error_msg.format(id=location_id), ephemeral=True)
                return

            location_name_for_message = location_to_delete.name_i18n.get(lang_code, location_to_delete.name_i18n.get("en", f"Location {location_to_delete.id}"))

            # Check for dependencies: Players in this location
            players_in_location_stmt = select(player_crud.model.id).where(player_crud.model.current_location_id == location_id, player_crud.model.guild_id == interaction.guild_id).limit(1)
            player_dependency = (await session.execute(players_in_location_stmt)).scalar_one_or_none()
            if player_dependency:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_delete:error_player_dependency", lang_code,
                    "Cannot delete Location '{name}' (ID: {id}) as players are currently in it. Please move them first."
                )
                await interaction.followup.send(error_msg.format(name=location_name_for_message, id=location_id), ephemeral=True)
                return

            # Check for dependencies: NPCs in this location
            npcs_in_location_stmt = select(npc_crud.model.id).where(npc_crud.model.current_location_id == location_id, npc_crud.model.guild_id == interaction.guild_id).limit(1)
            npc_dependency = (await session.execute(npcs_in_location_stmt)).scalar_one_or_none()
            if npc_dependency:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_delete:error_npc_dependency", lang_code,
                    "Cannot delete Location '{name}' (ID: {id}) as NPCs are currently in it. Please move them or reassign their location first."
                )
                await interaction.followup.send(error_msg.format(name=location_name_for_message, id=location_id), ephemeral=True)
                return

            # Check for dependencies: Child locations
            child_locations_stmt = select(location_crud.model.id).where(location_crud.model.parent_location_id == location_id, location_crud.model.guild_id == interaction.guild_id).limit(1)
            child_dependency = (await session.execute(child_locations_stmt)).scalar_one_or_none()
            if child_dependency:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_delete:error_child_dependency", lang_code,
                    "Cannot delete Location '{name}' (ID: {id}) as it has child locations. Please delete or re-parent them first."
                )
                await interaction.followup.send(error_msg.format(name=location_name_for_message, id=location_id), ephemeral=True)
                return

            # Check for dependencies: Neighbor links (more complex, this is a basic check)
            # This check is simplified: it looks for any location that lists THIS location as a neighbor.
            # A more robust solution would parse neighbor_locations_json of all other locations.
            # For now, we'll skip the neighbor check on other locations to avoid performance issues on simple delete.
            # The DB foreign key constraint on parent_location_id is the most critical.
            # If neighbor_locations_json contains IDs, a constraint might be needed there or manual cleanup.

            try:
                async with session.begin():
                    # If we reach here, basic dependencies are clear.
                    # If neighbor_locations_json of OTHER locations point here by ID, that's a data integrity issue
                    # not typically handled by simple ON DELETE CASCADE if it's just JSON.
                    # We should also clear this location's own neighbor_locations_json to be clean, though it's being deleted.
                    # And clear parent_location_id of this location if it points to something (though not strictly necessary for delete).

                    # Advanced: Clear this location from other locations' neighbor lists
                    all_other_locations = await location_crud.get_multi_by_guild(session, guild_id=interaction.guild_id)
                    updated_other_locations = False
                    for other_loc in all_other_locations:
                        if other_loc.id == location_id:
                            continue
                        if other_loc.neighbor_locations_json:
                            new_neighbors = []
                            changed = False
                            for neighbor_link in other_loc.neighbor_locations_json:
                                # Assuming target_static_id is used, or if target_id was used.
                                # If location_to_delete.static_id is present in target_static_id
                                if isinstance(neighbor_link, dict) and neighbor_link.get("target_static_id") == location_to_delete.static_id:
                                    changed = True
                                    continue # Skip adding this link
                                # If it was by ID (less likely based on current create command)
                                # elif isinstance(neighbor_link, dict) and neighbor_link.get("target_id") == location_id:
                                #     changed = True
                                #     continue
                                new_neighbors.append(neighbor_link)

                            if changed:
                                other_loc.neighbor_locations_json = new_neighbors
                                session.add(other_loc)
                                updated_other_locations = True
                    if updated_other_locations:
                        await session.flush()


                    deleted_location = await location_crud.remove(session, id=location_id)

                if deleted_location:
                    success_msg = await get_localized_message_template(
                        session, interaction.guild_id, "location_delete:success", lang_code,
                        "Location '{name}' (ID: {id}) has been deleted successfully."
                    )
                    await interaction.followup.send(success_msg.format(name=location_name_for_message, id=location_id), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "location_delete:error_not_deleted_unknown", lang_code,
                        "Location (ID: {id}) was found but could not be deleted."
                    )
                    await interaction.followup.send(error_msg.format(id=location_id), ephemeral=True)

            except Exception as e:
                logger.error(f"Error deleting Location {location_id} for guild {interaction.guild_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_delete:error_generic", lang_code,
                    "An error occurred while deleting Location '{name}' (ID: {id}): {error_message}"
                )
                await interaction.followup.send(error_msg.format(name=location_name_for_message, id=location_id, error_message=str(e)), ephemeral=True)
                return

    # --- Item CRUD ---
    item_group = app_commands.Group(name="item", description="Master commands for managing Items.", parent=master_admin)

    @item_group.command(name="view", description="View details of a specific Item.")
    @app_commands.describe(item_id="The database ID of the Item to view.")
    async def item_view(self, interaction: discord.Interaction, item_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_item import item_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            item = await item_crud.get_by_id_and_guild(session, id=item_id, guild_id=interaction.guild_id)

            if not item:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_view:not_found", lang_code,
                    "Item with ID {id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg.format(id=item_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "item_view:title", lang_code,
                "Item Details: {item_name} (ID: {item_id})"
            )

            item_name_display = item.name_i18n.get(lang_code, item.name_i18n.get("en", f"Item {item.id}"))
            embed_title = title_template.format(item_name=item_name_display, item_id=item.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.gold())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"item_view:label_{key}", lang_code, default)

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(item.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=item.static_id or "N/A", inline=True)
            embed.add_field(name=await get_label("item_type", "Type"), value=item.item_type or "N/A", inline=True)
            embed.add_field(name=await get_label("base_value", "Base Value"), value=str(item.base_value) if item.base_value is not None else "N/A", inline=True)
            embed.add_field(name=await get_label("slot_type", "Slot Type"), value=item.slot_type or "N/A", inline=True)
            embed.add_field(name=await get_label("is_stackable", "Is Stackable"), value=str(item.is_stackable), inline=True)

            name_i18n_str = await get_localized_message_template(session, interaction.guild_id, "item_view:value_na_json", lang_code, "Not available")
            if item.name_i18n:
                try: name_i18n_str = json.dumps(item.name_i18n, indent=2, ensure_ascii=False)
                except TypeError: name_i18n_str = await get_localized_message_template(session, interaction.guild_id, "item_view:error_serialization", lang_code, "Error serializing Name i18n")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```" + ("..." if len(name_i18n_str) > 1000 else ""), inline=False)

            desc_i18n_str = await get_localized_message_template(session, interaction.guild_id, "item_view:value_na_json", lang_code, "Not available")
            if item.description_i18n:
                try: desc_i18n_str = json.dumps(item.description_i18n, indent=2, ensure_ascii=False)
                except TypeError: desc_i18n_str = await get_localized_message_template(session, interaction.guild_id, "item_view:error_serialization", lang_code, "Error serializing Description i18n")
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```" + ("..." if len(desc_i18n_str) > 1000 else ""), inline=False)

            props_str = await get_localized_message_template(session, interaction.guild_id, "item_view:value_na_json", lang_code, "Not available")
            if item.properties_json:
                try: props_str = json.dumps(item.properties_json, indent=2, ensure_ascii=False)
                except TypeError: props_str = await get_localized_message_template(session, interaction.guild_id, "item_view:error_serialization", lang_code, "Error serializing Properties JSON")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{props_str[:1000]}\n```" + ("..." if len(props_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @item_group.command(name="list", description="List Items in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of Items per page.")
    async def item_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10

        from src.core.crud.crud_item import item_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import func, select

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            offset = (page - 1) * limit
            items = await item_crud.get_multi_by_guild(session, guild_id=interaction.guild_id, skip=offset, limit=limit)

            total_items_stmt = select(func.count(item_crud.model.id)).where(item_crud.model.guild_id == interaction.guild_id)
            total_items_result = await session.execute(total_items_stmt)
            total_items = total_items_result.scalar_one_or_none() or 0

            if not items:
                no_items_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_list:no_items_found_page", lang_code,
                    "No Items found for this guild (Page {page})."
                )
                await interaction.followup.send(no_items_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "item_list:title", lang_code,
                "Item List (Page {page} of {total_pages})"
            )
            total_pages = ((total_items - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_gold())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "item_list:footer", lang_code,
                "Displaying {count} of {total} total Items."
            )
            embed.set_footer(text=footer_template.format(count=len(items), total=total_items))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "item_list:item_field_name", lang_code,
                "ID: {item_id} | {item_name} (Static: {static_id})"
            )
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "item_list:item_field_value", lang_code,
                "Type: {type}, Value: {value}, Stackable: {stackable}"
            )

            for item_obj in items: # Renamed to avoid conflict with item_group
                item_name_display = item_obj.name_i18n.get(lang_code, item_obj.name_i18n.get("en", f"Item {item_obj.id}"))
                embed.add_field(
                    name=field_name_template.format(item_id=item_obj.id, item_name=item_name_display, static_id=item_obj.static_id or "N/A"),
                    value=field_value_template.format(
                        type=item_obj.item_type or "N/A",
                        value=str(item_obj.base_value) if item_obj.base_value is not None else "N/A",
                        stackable=str(item_obj.is_stackable)
                    ),
                    inline=False
                )

            if len(embed.fields) == 0:
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_list:no_items_to_display", lang_code,
                    "No Items found to display on page {page}."
                )
                await interaction.followup.send(no_display_msg.format(page=page), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @item_group.command(name="create", description="Create a new Item in this guild.")
    @app_commands.describe(
        static_id="Static ID for this Item (must be unique within the guild).",
        name_i18n_json="JSON string for Item name (e.g., {\"en\": \"Sword\", \"ru\": \"Меч\"}).",
        item_type="Type of item (e.g., WEAPON, ARMOR, POTION, QUEST_ITEM).",
        description_i18n_json="Optional: JSON string for Item description.",
        properties_json="Optional: JSON string for additional Item properties.",
        base_value="Optional: Integer base value/cost of the item.",
        slot_type="Optional: Equipment slot if applicable (e.g., MAIN_HAND, CHEST).",
        is_stackable="Is the item stackable? (True/False, defaults to True)."
    )
    async def item_create(self, interaction: discord.Interaction,
                          static_id: str,
                          name_i18n_json: str,
                          item_type: str,
                          description_i18n_json: Optional[str] = None,
                          properties_json: Optional[str] = None,
                          base_value: Optional[int] = None,
                          slot_type: Optional[str] = None,
                          is_stackable: bool = True): # Default to True as per model
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_item import item_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any # For type hints

        lang_code = str(interaction.locale)
        parsed_name_i18n: Dict[str, str]
        parsed_description_i18n: Optional[Dict[str, str]] = None
        parsed_properties: Optional[Dict[str, Any]] = None

        async with get_db_session() as session: # Session for all operations
            # Validate static_id uniqueness
            existing_item_static = await item_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=static_id)
            if existing_item_static:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_create:error_static_id_exists", lang_code,
                    "An Item with static_id '{id}' already exists in this guild."
                )
                await interaction.followup.send(error_msg.format(id=static_id), ephemeral=True)
                return

            try:
                parsed_name_i18n = json.loads(name_i18n_json)
                if not isinstance(parsed_name_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_name_i18n.items()):
                    raise ValueError("name_i18n_json must be a dict of str:str.")
                if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code):
                     raise ValueError("name_i18n_json must contain 'en' or current language key.")

                if description_i18n_json:
                    parsed_description_i18n = json.loads(description_i18n_json)
                    if not isinstance(parsed_description_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_description_i18n.items()):
                        raise ValueError("description_i18n_json must be a dict of str:str.")

                if properties_json:
                    parsed_properties = json.loads(properties_json)
                    if not isinstance(parsed_properties, dict):
                        raise ValueError("properties_json must be a dictionary.")
            except (json.JSONDecodeError, ValueError) as e:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_create:error_invalid_json_format", lang_code,
                    "Invalid JSON format or structure for one of the input fields: {error_details}"
                )
                await interaction.followup.send(error_msg.format(error_details=str(e)), ephemeral=True)
                return

            item_data_to_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id,
                "static_id": static_id,
                "name_i18n": parsed_name_i18n,
                "item_type": item_type, # Direct string, consider enum/validation later if needed
                "description_i18n": parsed_description_i18n if parsed_description_i18n else {},
                "properties_json": parsed_properties if parsed_properties else {},
                "base_value": base_value,
                "slot_type": slot_type,
                "is_stackable": is_stackable,
            }

            try:
                async with session.begin():
                    created_item = await item_crud.create(session, obj_in=item_data_to_create) # CRUDBase.create handles guild_id
                    await session.flush()
                    if created_item:
                         await session.refresh(created_item)
            except Exception as e:
                logger.error(f"Error creating Item with data {item_data_to_create}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_create:error_generic_create", lang_code,
                    "An error occurred while creating the Item: {error_message}"
                )
                await interaction.followup.send(error_msg.format(error_message=str(e)), ephemeral=True)
                return

            if not created_item:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_create:error_creation_failed_unknown", lang_code,
                    "Item creation failed for an unknown reason."
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "item_create:success_title", lang_code,
                "Item Created: {item_name} (ID: {item_id})"
            )
            created_item_name_display = created_item.name_i18n.get(lang_code, created_item.name_i18n.get("en", f"Item {created_item.id}"))

            embed = discord.Embed(title=success_title_template.format(item_name=created_item_name_display, item_id=created_item.id), color=discord.Color.green())
            embed.add_field(name="Static ID", value=created_item.static_id, inline=True)
            embed.add_field(name="Type", value=created_item.item_type, inline=True)
            embed.add_field(name="Stackable", value=str(created_item.is_stackable), inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @item_group.command(name="update", description="Update a specific field for an Item.")
    @app_commands.describe(
        item_id="The database ID of the Item to update.",
        field_to_update="Field to update (e.g., static_id, name_i18n_json, item_type, base_value, slot_type, is_stackable, properties_json).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable; True/False for boolean)."
    )
    async def item_update(self, interaction: discord.Interaction, item_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_item import item_crud
        from src.core.database import get_db_session
        from src.core.crud_base_definitions import update_entity
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any, Optional, Union # For type hints

        allowed_fields = {
            "static_id": str, # Static ID usually shouldn't be None once set, but allow update to new unique
            "name_i18n_json": dict,
            "description_i18n_json": dict,
            "item_type": str,
            "base_value": (int, type(None)),
            "slot_type": (str, type(None)),
            "is_stackable": bool,
            "properties_json": dict,
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()

        db_field_name = field_to_update_lower
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")

        field_type_info = allowed_fields.get(db_field_name)

        if not field_type_info:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "item_update:error_field_not_allowed", lang_code,
                    "Field '{field_name}' is not allowed for update. Allowed: {allowed_list}"
                )
            await interaction.followup.send(error_msg.format(field_name=field_to_update, allowed_list=', '.join(allowed_fields.keys())), ephemeral=True)
            return

        parsed_value: Any = None

        async with get_db_session() as session: # Session for validation and update
            try:
                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: # Cannot set static_id to empty or None after initial creation if it was set
                        raise ValueError("static_id cannot be set to empty or None if it was previously set. Delete and recreate if needed.")
                    existing_item_static = await item_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                    if existing_item_static and existing_item_static.id != item_id:
                        error_msg = await get_localized_message_template(
                            session, interaction.guild_id, "item_update:error_static_id_exists", lang_code,
                            "Another Item with static_id '{id}' already exists."
                        )
                        await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True)
                        return
                elif db_field_name in ["name_i18n", "description_i18n", "properties_json"]:
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict):
                        raise ValueError(f"{db_field_name} must be a dictionary.")
                elif db_field_name == "item_type" or db_field_name == "slot_type":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        if db_field_name == "item_type": # item_type is not nullable
                             raise ValueError("item_type cannot be None.")
                        parsed_value = None
                    else:
                        parsed_value = new_value
                elif db_field_name == "base_value":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = int(new_value)
                elif db_field_name == "is_stackable":
                    if new_value.lower() == 'true':
                        parsed_value = True
                    elif new_value.lower() == 'false':
                        parsed_value = False
                    else:
                        raise ValueError("is_stackable must be 'True' or 'False'.")
                else:
                     error_msg = await get_localized_message_template(
                         session, interaction.guild_id, "item_update:error_unknown_field_type", lang_code,
                        "Internal error: Unknown field type for '{field_name}'."
                    )
                     await interaction.followup.send(error_msg.format(field_name=db_field_name), ephemeral=True)
                     return

            except ValueError as e:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_update:error_invalid_value_type", lang_code,
                    "Invalid value '{value}' for field '{field_name}'. Details: {details}"
                )
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True)
                return
            except json.JSONDecodeError as e:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_update:error_invalid_json", lang_code,
                    "Invalid JSON string '{value}' for field '{field_name}'. Details: {details}"
                )
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True)
                return

            item_to_update = await item_crud.get_by_id_and_guild(session, id=item_id, guild_id=interaction.guild_id)
            if not item_to_update:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_update:error_item_not_found", lang_code,
                    "Item with ID {id} not found."
                )
                await interaction.followup.send(error_msg.format(id=item_id), ephemeral=True)
                return

            update_data_dict = {db_field_name: parsed_value}

            try:
                async with session.begin():
                    updated_item = await update_entity(session, entity=item_to_update, data=update_data_dict)
                    await session.flush()
                    await session.refresh(updated_item)
            except Exception as e:
                logger.error(f"Error updating Item {item_id} with data {update_data_dict}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_update:error_generic_update", lang_code,
                    "An error occurred while updating Item {id}: {error_message}"
                )
                await interaction.followup.send(error_msg.format(id=item_id, error_message=str(e)), ephemeral=True)
                return

            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "item_update:success_title", lang_code,
                "Item Updated: {item_name} (ID: {item_id})"
            )
            updated_item_name_display = updated_item.name_i18n.get(lang_code, updated_item.name_i18n.get("en", f"Item {updated_item.id}"))
            embed = discord.Embed(title=success_title_template.format(item_name=updated_item_name_display, item_id=updated_item.id), color=discord.Color.orange())

            field_updated_label = await get_localized_message_template(session, interaction.guild_id, "item_update:label_field_updated", lang_code, "Field Updated")
            new_value_label = await get_localized_message_template(session, interaction.guild_id, "item_update:label_new_value", lang_code, "New Value")

            new_value_display = str(parsed_value)
            if isinstance(parsed_value, (dict, list)):
                new_value_display = f"```json\n{json.dumps(parsed_value, indent=2, ensure_ascii=False)}\n```"
            elif isinstance(parsed_value, bool):
                new_value_display = str(parsed_value)
            elif parsed_value is None:
                 new_value_display = "None"

            embed.add_field(name=field_updated_label, value=field_to_update, inline=True)
            embed.add_field(name=new_value_label, value=new_value_display, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @item_group.command(name="delete", description="Delete an Item definition from this guild.")
    @app_commands.describe(item_id="The database ID of the Item to delete.")
    async def item_delete(self, interaction: discord.Interaction, item_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_item import item_crud
        from src.core.crud.crud_inventory_item import inventory_item_crud # To check for dependencies
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import select

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            item_to_delete = await item_crud.get_by_id_and_guild(session, id=item_id, guild_id=interaction.guild_id)

            if not item_to_delete:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_delete:error_not_found", lang_code,
                    "Item with ID {id} not found. Nothing to delete."
                )
                await interaction.followup.send(error_msg.format(id=item_id), ephemeral=True)
                return

            item_name_for_message = item_to_delete.name_i18n.get(lang_code, item_to_delete.name_i18n.get("en", f"Item {item_to_delete.id}"))

            # Check for dependencies: InventoryItems referencing this Item
            # This requires inventory_item_crud to have a method to count by item_id and guild_id, or a generic way to query.
            # Let's assume inventory_item_crud.model has 'item_id' and 'guild_id' (though guild_id might be via owner)
            # For simplicity, we query directly here.

            # A more direct way if InventoryItem has guild_id (it does not directly, it's through owner)
            # This check is tricky because InventoryItem links to Player/NPC which has guild_id.
            # A simpler check might be to see if ANY InventoryItem references this item_id.
            # If we want to be guild-specific, we'd need a join.
            # For now, let's do a simpler check for any InventoryItem.
            # This could be refined if inventory_item_crud gets a specific method.

            # This is a simplified check. A full check would join through owners (Player/NPC) to filter by guild.
            # However, item_id is globally unique for Item definitions, but InventoryItem uses this global item_id.
            # The master command should only delete items from *their* guild.
            # If an Item is only defined for one guild, then checking for any InventoryItem is okay.
            # If Items could be shared (not current design), this would be insufficient.

            # Given Items are guild-scoped (Item.guild_id), an InventoryItem in another guild SHOULD NOT
            # reference an Item from THIS guild. So, checking all InventoryItems for this item_id is acceptable.
            inventory_dependency_stmt = select(inventory_item_crud.model.id).where(inventory_item_crud.model.item_id == item_id).limit(1)
            inventory_dependency = (await session.execute(inventory_dependency_stmt)).scalar_one_or_none()

            if inventory_dependency:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_delete:error_inventory_dependency", lang_code,
                    "Cannot delete Item '{name}' (ID: {id}) as it exists in one or more inventories. Please remove all instances of this item first."
                )
                await interaction.followup.send(error_msg.format(name=item_name_for_message, id=item_id), ephemeral=True)
                return

            try:
                async with session.begin():
                    deleted_item = await item_crud.remove(session, id=item_id) # remove uses the primary key

                if deleted_item:
                    success_msg = await get_localized_message_template(
                        session, interaction.guild_id, "item_delete:success", lang_code,
                        "Item '{name}' (ID: {id}) has been deleted successfully."
                    )
                    await interaction.followup.send(success_msg.format(name=item_name_for_message, id=item_id), ephemeral=True)
                else: # Should be caught by item_to_delete check
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "item_delete:error_not_deleted_unknown", lang_code,
                        "Item (ID: {id}) was found but could not be deleted."
                    )
                    await interaction.followup.send(error_msg.format(id=item_id), ephemeral=True)

            except Exception as e:
                logger.error(f"Error deleting Item {item_id} for guild {interaction.guild_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_delete:error_generic", lang_code,
                    "An error occurred while deleting Item '{name}' (ID: {id}): {error_message}"
                )
                await interaction.followup.send(error_msg.format(name=item_name_for_message, id=item_id, error_message=str(e)), ephemeral=True)
                return

    # --- GeneratedFaction CRUD ---
    faction_group = app_commands.Group(name="faction", description="Master commands for managing Generated Factions.", parent=master_admin)

    @faction_group.command(name="view", description="View details of a specific Faction.")
    @app_commands.describe(faction_id="The database ID of the Faction to view.")
    async def faction_view(self, interaction: discord.Interaction, faction_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_faction import crud_faction
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            # crud_faction uses 'db' as session name, but we pass 'session'
            faction = await crud_faction.get_by_id_and_guild(session, id=faction_id, guild_id=interaction.guild_id)

            if not faction:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_view:not_found", lang_code,
                    "Faction with ID {id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg.format(id=faction_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "faction_view:title", lang_code,
                "Faction Details: {faction_name} (ID: {faction_id})"
            )

            faction_name_display = faction.name_i18n.get(lang_code, faction.name_i18n.get("en", f"Faction {faction.id}"))
            embed_title = title_template.format(faction_name=faction_name_display, faction_id=faction.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_red())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"faction_view:label_{key}", lang_code, default)

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(faction.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=faction.static_id or "N/A", inline=True)
            embed.add_field(name=await get_label("leader_npc_id", "Leader NPC Static ID"), value=faction.leader_npc_static_id or "N/A", inline=True)

            # Helper for JSON fields
            async def format_json_field(data: Optional[Dict[Any, Any]], field_name_key: str, default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data:
                    return na_str
                try:
                    return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError:
                    return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

            name_i18n_str = await format_json_field(faction.name_i18n, "name_i18n", "faction_view:value_na_json", "faction_view:error_serialization_name")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```" + ("..." if len(name_i18n_str) > 1000 else ""), inline=False)

            desc_i18n_str = await format_json_field(faction.description_i18n, "description_i18n", "faction_view:value_na_json", "faction_view:error_serialization_desc")
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```" + ("..." if len(desc_i18n_str) > 1000 else ""), inline=False)

            ideology_i18n_str = await format_json_field(faction.ideology_i18n, "ideology_i18n", "faction_view:value_na_json", "faction_view:error_serialization_ideology")
            embed.add_field(name=await get_label("ideology_i18n", "Ideology (i18n)"), value=f"```json\n{ideology_i18n_str[:1000]}\n```" + ("..." if len(ideology_i18n_str) > 1000 else ""), inline=False)

            resources_str = await format_json_field(faction.resources_json, "resources_json", "faction_view:value_na_json", "faction_view:error_serialization_resources")
            embed.add_field(name=await get_label("resources", "Resources JSON"), value=f"```json\n{resources_str[:1000]}\n```" + ("..." if len(resources_str) > 1000 else ""), inline=False)

            ai_meta_str = await format_json_field(faction.ai_metadata_json, "ai_metadata_json", "faction_view:value_na_json", "faction_view:error_serialization_ai_meta")
            embed.add_field(name=await get_label("ai_metadata", "AI Metadata JSON"), value=f"```json\n{ai_meta_str[:1000]}\n```" + ("..." if len(ai_meta_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @faction_group.command(name="list", description="List Generated Factions in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of Factions per page.")
    async def faction_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10

        from src.core.crud.crud_faction import crud_faction
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import func, select # For count

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            offset = (page - 1) * limit
            # crud_faction.get_multi_by_guild_id uses 'db' as session name
            factions = await crud_faction.get_multi_by_guild_id(session, guild_id=interaction.guild_id, skip=offset, limit=limit)

            total_factions_stmt = select(func.count(crud_faction.model.id)).where(crud_faction.model.guild_id == interaction.guild_id)
            total_factions_result = await session.execute(total_factions_stmt)
            total_factions = total_factions_result.scalar_one_or_none() or 0

            if not factions:
                no_factions_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_list:no_factions_found_page", lang_code,
                    "No Factions found for this guild (Page {page})."
                )
                await interaction.followup.send(no_factions_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "faction_list:title", lang_code,
                "Faction List (Page {page} of {total_pages})"
            )
            total_pages = ((total_factions - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_magenta())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "faction_list:footer", lang_code,
                "Displaying {count} of {total} total Factions."
            )
            embed.set_footer(text=footer_template.format(count=len(factions), total=total_factions))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "faction_list:faction_field_name", lang_code,
                "ID: {faction_id} | {faction_name} (Static: {static_id})"
            )
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "faction_list:faction_field_value", lang_code,
                "Leader NPC Static ID: {leader_id}" # Add more details if concise enough
            )

            for f in factions:
                faction_name_display = f.name_i18n.get(lang_code, f.name_i18n.get("en", f"Faction {f.id}"))
                embed.add_field(
                    name=field_name_template.format(faction_id=f.id, faction_name=faction_name_display, static_id=f.static_id or "N/A"),
                    value=field_value_template.format(leader_id=f.leader_npc_static_id or "N/A"),
                    inline=False
                )

            if len(embed.fields) == 0:
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_list:no_factions_to_display", lang_code,
                    "No Factions found to display on page {page}."
                )
                await interaction.followup.send(no_display_msg.format(page=page), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @faction_group.command(name="create", description="Create a new Generated Faction in this guild.")
    @app_commands.describe(
        static_id="Static ID for this Faction (must be unique within the guild).",
        name_i18n_json="JSON string for Faction name (e.g., {\"en\": \"The Guardians\", \"ru\": \"Стражи\"}).",
        description_i18n_json="Optional: JSON string for Faction description.",
        ideology_i18n_json="Optional: JSON string for Faction ideology.",
        leader_npc_static_id="Optional: Static ID of the NPC who leads this faction (must exist).",
        resources_json="Optional: JSON string for Faction resources.",
        ai_metadata_json="Optional: JSON string for AI metadata related to this faction."
    )
    async def faction_create(self, interaction: discord.Interaction,
                             static_id: str,
                             name_i18n_json: str,
                             description_i18n_json: Optional[str] = None,
                             ideology_i18n_json: Optional[str] = None,
                             leader_npc_static_id: Optional[str] = None,
                             resources_json: Optional[str] = None,
                             ai_metadata_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_faction import crud_faction
        from src.core.crud.crud_npc import npc_crud # To validate leader_npc_static_id
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any # For type hints

        lang_code = str(interaction.locale)
        parsed_name_i18n: Dict[str, str]
        parsed_desc_i18n: Optional[Dict[str, str]] = None
        parsed_ideology_i18n: Optional[Dict[str, str]] = None
        parsed_resources: Optional[Dict[str, Any]] = None
        parsed_ai_meta: Optional[Dict[str, Any]] = None

        async with get_db_session() as session: # Session for all operations
            # Validate static_id uniqueness
            existing_faction_static = await crud_faction.get_by_static_id(session, guild_id=interaction.guild_id, static_id=static_id)
            if existing_faction_static:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_create:error_static_id_exists", lang_code,
                    "A Faction with static_id '{id}' already exists."
                )
                await interaction.followup.send(error_msg.format(id=static_id), ephemeral=True)
                return

            # Validate leader_npc_static_id if provided
            if leader_npc_static_id:
                leader_npc = await npc_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=leader_npc_static_id)
                if not leader_npc:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "faction_create:error_leader_npc_not_found", lang_code,
                        "Leader NPC with static_id '{id}' not found in this guild."
                    )
                    await interaction.followup.send(error_msg.format(id=leader_npc_static_id), ephemeral=True)
                    return

            try:
                parsed_name_i18n = json.loads(name_i18n_json)
                if not isinstance(parsed_name_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_name_i18n.items()):
                    raise ValueError("name_i18n_json must be a dict of str:str.")
                if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code):
                     raise ValueError("name_i18n_json must contain 'en' or current language key.")

                if description_i18n_json:
                    parsed_desc_i18n = json.loads(description_i18n_json)
                    if not isinstance(parsed_desc_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_desc_i18n.items()):
                        raise ValueError("description_i18n_json must be a dict of str:str.")

                if ideology_i18n_json:
                    parsed_ideology_i18n = json.loads(ideology_i18n_json)
                    if not isinstance(parsed_ideology_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_ideology_i18n.items()):
                        raise ValueError("ideology_i18n_json must be a dict of str:str.")

                if resources_json:
                    parsed_resources = json.loads(resources_json)
                    if not isinstance(parsed_resources, dict):
                        raise ValueError("resources_json must be a dictionary.")

                if ai_metadata_json:
                    parsed_ai_meta = json.loads(ai_metadata_json)
                    if not isinstance(parsed_ai_meta, dict):
                        raise ValueError("ai_metadata_json must be a dictionary.")

            except (json.JSONDecodeError, ValueError) as e:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_create:error_invalid_json_format", lang_code,
                    "Invalid JSON format or structure for one of the input fields: {error_details}"
                )
                await interaction.followup.send(error_msg.format(error_details=str(e)), ephemeral=True)
                return

            faction_data_to_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id,
                "static_id": static_id,
                "name_i18n": parsed_name_i18n,
                "description_i18n": parsed_desc_i18n if parsed_desc_i18n else {},
                "ideology_i18n": parsed_ideology_i18n if parsed_ideology_i18n else {},
                "leader_npc_static_id": leader_npc_static_id,
                "resources_json": parsed_resources if parsed_resources else {},
                "ai_metadata_json": parsed_ai_meta if parsed_ai_meta else {},
            }

            try:
                async with session.begin():
                    created_faction = await crud_faction.create(session, obj_in=faction_data_to_create)
                    await session.flush()
                    if created_faction:
                         await session.refresh(created_faction)
            except Exception as e:
                logger.error(f"Error creating Faction with data {faction_data_to_create}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_create:error_generic_create", lang_code,
                    "An error occurred while creating the Faction: {error_message}"
                )
                await interaction.followup.send(error_msg.format(error_message=str(e)), ephemeral=True)
                return

            if not created_faction:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_create:error_creation_failed_unknown", lang_code,
                    "Faction creation failed for an unknown reason."
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "faction_create:success_title", lang_code,
                "Faction Created: {faction_name} (ID: {faction_id})"
            )
            created_faction_name_display = created_faction.name_i18n.get(lang_code, created_faction.name_i18n.get("en", f"Faction {created_faction.id}"))

            embed = discord.Embed(title=success_title_template.format(faction_name=created_faction_name_display, faction_id=created_faction.id), color=discord.Color.green())
            embed.add_field(name="Static ID", value=created_faction.static_id, inline=True)
            embed.add_field(name="Leader NPC Static ID", value=created_faction.leader_npc_static_id or "N/A", inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @faction_group.command(name="update", description="Update a specific field for a Faction.")
    @app_commands.describe(
        faction_id="The database ID of the Faction to update.",
        field_to_update="Field to update (e.g., static_id, name_i18n_json, leader_npc_static_id, resources_json).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable string fields)."
    )
    async def faction_update(self, interaction: discord.Interaction, faction_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_faction import crud_faction
        from src.core.crud.crud_npc import npc_crud # For validating leader_npc_static_id
        from src.core.database import get_db_session
        from src.core.crud_base_definitions import update_entity
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any, Optional # For type hints

        allowed_fields = {
            "static_id": str,
            "name_i18n_json": dict,
            "description_i18n_json": dict,
            "ideology_i18n_json": dict,
            "leader_npc_static_id": (str, type(None)),
            "resources_json": dict,
            "ai_metadata_json": dict,
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()

        db_field_name = field_to_update_lower
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")

        field_type_info = allowed_fields.get(db_field_name)

        if not field_type_info:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "faction_update:error_field_not_allowed", lang_code,
                    "Field '{field_name}' is not allowed for update. Allowed: {allowed_list}"
                )
            await interaction.followup.send(error_msg.format(field_name=field_to_update, allowed_list=', '.join(allowed_fields.keys())), ephemeral=True)
            return

        parsed_value: Any = None

        async with get_db_session() as session: # Session for validation and update
            try:
                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: raise ValueError("static_id cannot be empty.")
                    existing_faction_static = await crud_faction.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                    if existing_faction_static and existing_faction_static.id != faction_id:
                        error_msg = await get_localized_message_template(
                            session, interaction.guild_id, "faction_update:error_static_id_exists", lang_code,
                            "Another Faction with static_id '{id}' already exists."
                        )
                        await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True)
                        return
                elif db_field_name in ["name_i18n", "description_i18n", "ideology_i18n", "resources_json", "ai_metadata_json"]:
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict):
                        raise ValueError(f"{db_field_name} must be a dictionary.")
                elif db_field_name == "leader_npc_static_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = new_value
                        leader_npc = await npc_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                        if not leader_npc:
                            error_msg = await get_localized_message_template(
                                session, interaction.guild_id, "faction_update:error_leader_npc_not_found", lang_code,
                                "Leader NPC with static_id '{id}' not found."
                            )
                            await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True)
                            return
                else:
                     error_msg = await get_localized_message_template(
                         session, interaction.guild_id, "faction_update:error_unknown_field_type", lang_code,
                        "Internal error: Unknown field type for '{field_name}'."
                    )
                     await interaction.followup.send(error_msg.format(field_name=db_field_name), ephemeral=True)
                     return

            except ValueError as e:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_update:error_invalid_value_type", lang_code,
                    "Invalid value '{value}' for field '{field_name}'. Details: {details}"
                )
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True)
                return
            except json.JSONDecodeError as e:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_update:error_invalid_json", lang_code,
                    "Invalid JSON string '{value}' for field '{field_name}'. Details: {details}"
                )
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True)
                return

            faction_to_update = await crud_faction.get_by_id_and_guild(session, id=faction_id, guild_id=interaction.guild_id)
            if not faction_to_update:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_update:error_faction_not_found", lang_code,
                    "Faction with ID {id} not found."
                )
                await interaction.followup.send(error_msg.format(id=faction_id), ephemeral=True)
                return

            update_data_dict = {db_field_name: parsed_value}

            try:
                async with session.begin():
                    updated_faction = await update_entity(session, entity=faction_to_update, data=update_data_dict)
                    await session.flush()
                    await session.refresh(updated_faction)
            except Exception as e:
                logger.error(f"Error updating Faction {faction_id} with data {update_data_dict}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_update:error_generic_update", lang_code,
                    "An error occurred while updating Faction {id}: {error_message}"
                )
                await interaction.followup.send(error_msg.format(id=faction_id, error_message=str(e)), ephemeral=True)
                return

            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "faction_update:success_title", lang_code,
                "Faction Updated: {faction_name} (ID: {faction_id})"
            )
            updated_faction_name_display = updated_faction.name_i18n.get(lang_code, updated_faction.name_i18n.get("en", f"Faction {updated_faction.id}"))
            embed = discord.Embed(title=success_title_template.format(faction_name=updated_faction_name_display, faction_id=updated_faction.id), color=discord.Color.orange())

            field_updated_label = await get_localized_message_template(session, interaction.guild_id, "faction_update:label_field_updated", lang_code, "Field Updated")
            new_value_label = await get_localized_message_template(session, interaction.guild_id, "faction_update:label_new_value", lang_code, "New Value")

            new_value_display = str(parsed_value)
            if isinstance(parsed_value, (dict, list)): # Should only be dict for current allowed fields
                new_value_display = f"```json\n{json.dumps(parsed_value, indent=2, ensure_ascii=False)}\n```"
            elif parsed_value is None:
                 new_value_display = "None"

            embed.add_field(name=field_updated_label, value=field_to_update, inline=True)
            embed.add_field(name=new_value_label, value=new_value_display, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @faction_group.command(name="delete", description="Delete a Faction from this guild.")
    @app_commands.describe(faction_id="The database ID of the Faction to delete.")
    async def faction_delete(self, interaction: discord.Interaction, faction_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_faction import crud_faction
        from src.core.crud.crud_npc import npc_crud # To check for NPC dependencies
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import select

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            faction_to_delete = await crud_faction.get_by_id_and_guild(session, id=faction_id, guild_id=interaction.guild_id)

            if not faction_to_delete:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_delete:error_not_found", lang_code,
                    "Faction with ID {id} not found. Nothing to delete."
                )
                await interaction.followup.send(error_msg.format(id=faction_id), ephemeral=True)
                return

            faction_name_for_message = faction_to_delete.name_i18n.get(lang_code, faction_to_delete.name_i18n.get("en", f"Faction {faction_to_delete.id}"))

            # Check for NPC dependencies
            npc_dependency_stmt = select(npc_crud.model.id).where(
                npc_crud.model.faction_id == faction_id,
                npc_crud.model.guild_id == interaction.guild_id # Ensure NPC is in the same guild
            ).limit(1)
            npc_dependency = (await session.execute(npc_dependency_stmt)).scalar_one_or_none()

            if npc_dependency:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_delete:error_npc_dependency", lang_code,
                    "Cannot delete Faction '{name}' (ID: {id}) as NPCs are still members of it. Please reassign or delete them first."
                )
                await interaction.followup.send(error_msg.format(name=faction_name_for_message, id=faction_id), ephemeral=True)
                return

            # TODO: Consider other dependencies like Relationships involving this faction.

            try:
                async with session.begin():
                    deleted_faction = await crud_faction.remove(session, id=faction_id)

                if deleted_faction:
                    success_msg = await get_localized_message_template(
                        session, interaction.guild_id, "faction_delete:success", lang_code,
                        "Faction '{name}' (ID: {id}) has been deleted successfully."
                    )
                    await interaction.followup.send(success_msg.format(name=faction_name_for_message, id=faction_id), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "faction_delete:error_not_deleted_unknown", lang_code,
                        "Faction (ID: {id}) was found but could not be deleted."
                    )
                    await interaction.followup.send(error_msg.format(id=faction_id), ephemeral=True)

            except Exception as e:
                logger.error(f"Error deleting Faction {faction_id} for guild {interaction.guild_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_delete:error_generic", lang_code,
                    "An error occurred while deleting Faction '{name}' (ID: {id}): {error_message}"
                )
                await interaction.followup.send(error_msg.format(name=faction_name_for_message, id=faction_id, error_message=str(e)), ephemeral=True)
                return

    # --- Relationship CRUD ---
    relationship_group = app_commands.Group(name="relationship", description="Master commands for managing Relationships.", parent=master_admin)

    @relationship_group.command(name="view", description="View details of a specific Relationship.")
    @app_commands.describe(relationship_id="The database ID of the Relationship to view.")
    async def relationship_view(self, interaction: discord.Interaction, relationship_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_relationship import crud_relationship
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            # crud_relationship methods use 'session' as param name
            relationship = await crud_relationship.get_by_id_and_guild(session, id=relationship_id, guild_id=interaction.guild_id)

            if not relationship:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "relationship_view:not_found", lang_code,
                    "Relationship with ID {id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg.format(id=relationship_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "relationship_view:title", lang_code,
                "Relationship Details (ID: {id})"
            )
            embed_title = title_template.format(id=relationship.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_purple())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"relationship_view:label_{key}", lang_code, default)

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(relationship.guild_id), inline=True)
            embed.add_field(name=await get_label("type", "Type"), value=relationship.relationship_type, inline=True)
            embed.add_field(name=await get_label("value", "Value"), value=str(relationship.value), inline=True)

            embed.add_field(name=await get_label("entity1_type", "Entity 1 Type"), value=relationship.entity1_type.value, inline=True)
            embed.add_field(name=await get_label("entity1_id", "Entity 1 ID"), value=str(relationship.entity1_id), inline=True)
            embed.add_field(name=await get_label("entity2_type", "Entity 2 Type"), value=relationship.entity2_type.value, inline=True)
            embed.add_field(name=await get_label("entity2_id", "Entity 2 ID"), value=str(relationship.entity2_id), inline=True)

            source_log_id_val = str(relationship.source_log_id) if relationship.source_log_id else "N/A"
            embed.add_field(name=await get_label("source_log_id", "Source Log ID"), value=source_log_id_val, inline=True)

            created_at_val = discord.utils.format_dt(relationship.created_at, style='F') if relationship.created_at else "N/A"
            updated_at_val = discord.utils.format_dt(relationship.updated_at, style='F') if relationship.updated_at else "N/A"
            embed.add_field(name=await get_label("created_at", "Created At"), value=created_at_val, inline=False)
            embed.add_field(name=await get_label("updated_at", "Updated At"), value=updated_at_val, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @relationship_group.command(name="list", description="List Relationships in this guild, with optional filters.")
    @app_commands.describe(
        entity1_id="Optional: Filter by ID of the first entity.",
        entity1_type="Optional: Filter by type of the first entity (PLAYER, GENERATED_NPC, FACTION, etc.).",
        entity2_id="Optional: Filter by ID of the second entity.",
        entity2_type="Optional: Filter by type of the second entity.",
        relationship_type_filter="Optional: Filter by relationship type (e.g., neutral, friendly).",
        page="Page number to display.",
        limit="Number of Relationships per page."
    )
    async def relationship_list(self, interaction: discord.Interaction,
                                entity1_id: Optional[int] = None, entity1_type: Optional[str] = None,
                                entity2_id: Optional[int] = None, entity2_type: Optional[str] = None,
                                relationship_type_filter: Optional[str] = None,
                                page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 5: limit = 5 # Embeds can get very long with relationship details

        from src.core.crud.crud_relationship import crud_relationship
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from src.models.enums import RelationshipEntityType
        from sqlalchemy import select, func, and_ # For count and filtering

        lang_code = str(interaction.locale)
        e1_type_enum: Optional[RelationshipEntityType] = None
        e2_type_enum: Optional[RelationshipEntityType] = None

        async with get_db_session() as session: # Session for all operations
            # Validate entity types if provided
            if entity1_type:
                try: e1_type_enum = RelationshipEntityType[entity1_type.upper()]
                except KeyError:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_list:error_invalid_e1_type", lang_code, "Invalid entity1_type.")
                    await interaction.followup.send(error_msg, ephemeral=True); return
            if entity2_type:
                try: e2_type_enum = RelationshipEntityType[entity2_type.upper()]
                except KeyError:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_list:error_invalid_e2_type", lang_code, "Invalid entity2_type.")
                    await interaction.followup.send(error_msg, ephemeral=True); return

            # Build query filters
            filters = [crud_relationship.model.guild_id == interaction.guild_id]
            if entity1_id is not None and e1_type_enum is not None:
                filters.append(crud_relationship.model.entity1_id == entity1_id)
                filters.append(crud_relationship.model.entity1_type == e1_type_enum)
            elif entity1_id is not None or e1_type_enum is not None: # Partial filter for entity1
                 error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_list:error_partial_e1_filter", lang_code, "If filtering by entity1, both ID and Type must be provided.")
                 await interaction.followup.send(error_msg, ephemeral=True); return

            if entity2_id is not None and e2_type_enum is not None:
                filters.append(crud_relationship.model.entity2_id == entity2_id)
                filters.append(crud_relationship.model.entity2_type == e2_type_enum)
            elif entity2_id is not None or e2_type_enum is not None: # Partial filter for entity2
                 error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_list:error_partial_e2_filter", lang_code, "If filtering by entity2, both ID and Type must be provided.")
                 await interaction.followup.send(error_msg, ephemeral=True); return

            if relationship_type_filter:
                filters.append(crud_relationship.model.relationship_type.ilike(f"%{relationship_type_filter}%"))

            offset = (page - 1) * limit

            query = select(crud_relationship.model).where(and_(*filters)).offset(offset).limit(limit).order_by(crud_relationship.model.id.desc())
            result = await session.execute(query)
            relationships = result.scalars().all()

            count_query = select(func.count(crud_relationship.model.id)).where(and_(*filters))
            total_relationships_result = await session.execute(count_query)
            total_relationships = total_relationships_result.scalar_one_or_none() or 0

            if not relationships:
                no_rels_msg = await get_localized_message_template(
                    session, interaction.guild_id, "relationship_list:no_relationships_found_page", lang_code,
                    "No Relationships found for the given criteria (Page {page})."
                )
                await interaction.followup.send(no_rels_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "relationship_list:title", lang_code,
                "Relationship List (Page {page} of {total_pages})"
            )
            total_pages = ((total_relationships - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_gray())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "relationship_list:footer", lang_code,
                "Displaying {count} of {total} total Relationships."
            )
            embed.set_footer(text=footer_template.format(count=len(relationships), total=total_relationships))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "relationship_list:relationship_field_name", lang_code,
                "ID: {rel_id} | {e1_type} ({e1_id}) <=> {e2_type} ({e2_id})"
            )
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "relationship_list:relationship_field_value", lang_code,
                "Type: {type}, Value: {value}"
            )

            for rel in relationships:
                embed.add_field(
                    name=field_name_template.format(rel_id=rel.id, e1_type=rel.entity1_type.name, e1_id=rel.entity1_id, e2_type=rel.entity2_type.name, e2_id=rel.entity2_id),
                    value=field_value_template.format(type=rel.relationship_type, value=rel.value),
                    inline=False
                )

            if len(embed.fields) == 0: # Should be caught by "not relationships" but as safeguard
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "relationship_list:no_rels_to_display", lang_code,
                    "No relationships found to display on page {page}."
                )
                await interaction.followup.send(no_display_msg.format(page=page), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @relationship_group.command(name="create", description="Create a new Relationship.")
    @app_commands.describe(
        entity1_id="ID of the first entity.",
        entity1_type="Type of the first entity (PLAYER, GENERATED_NPC, FACTION).",
        entity2_id="ID of the second entity.",
        entity2_type="Type of the second entity (PLAYER, GENERATED_NPC, FACTION).",
        relationship_type="Type of relationship (e.g., neutral, friendly, hostile, family).",
        value="Numerical value of the relationship (e.g., 0, 50, -100).",
        source_log_id="Optional: ID of the StoryLog entry that caused this relationship."
    )
    async def relationship_create(self, interaction: discord.Interaction,
                                  entity1_id: int, entity1_type: str,
                                  entity2_id: int, entity2_type: str,
                                  relationship_type: str,
                                  value: int,
                                  source_log_id: Optional[int] = None):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_relationship import crud_relationship
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from src.models.enums import RelationshipEntityType
        # Import CRUDs for entity validation
        from src.core.crud.crud_player import player_crud
        from src.core.crud.crud_npc import npc_crud
        from src.core.crud.crud_faction import crud_faction
        from typing import Dict, Any, Optional

        lang_code = str(interaction.locale)
        e1_type_enum: RelationshipEntityType
        e2_type_enum: RelationshipEntityType

        async def validate_entity(session: AsyncSession, entity_id: int, entity_type_str: str, entity_type_enum: RelationshipEntityType, guild_id: int, entity_label: str) -> bool:
            crud_map = {
                RelationshipEntityType.PLAYER: player_crud,
                RelationshipEntityType.GENERATED_NPC: npc_crud,
                RelationshipEntityType.FACTION: crud_faction,
                # Add other types if they become valid relationship participants
            }
            crud_instance = crud_map.get(entity_type_enum)
            if not crud_instance:
                error_msg = await get_localized_message_template(session, guild_id, "relationship_create:error_unsupported_type", lang_code, f"Unsupported entity type for {entity_label}: {{type}}")
                await interaction.followup.send(error_msg.format(type=entity_type_str), ephemeral=True)
                return False

            entity = await crud_instance.get_by_id_and_guild(session, id=entity_id, guild_id=guild_id)
            if not entity:
                error_msg = await get_localized_message_template(session, guild_id, "relationship_create:error_entity_not_found", lang_code, f"{entity_label} with ID {{id}} and Type {{type}} not found in this guild.")
                await interaction.followup.send(error_msg.format(id=entity_id, type=entity_type_str), ephemeral=True)
                return False
            return True

        async with get_db_session() as session:
            try:
                e1_type_enum = RelationshipEntityType[entity1_type.upper()]
                e2_type_enum = RelationshipEntityType[entity2_type.upper()]
            except KeyError:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_create:error_invalid_entity_type", lang_code, "Invalid entity_type provided. Use PLAYER, GENERATED_NPC, or FACTION.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            if not await validate_entity(session, entity1_id, entity1_type, e1_type_enum, interaction.guild_id, "Entity 1"): return
            if not await validate_entity(session, entity2_id, entity2_type, e2_type_enum, interaction.guild_id, "Entity 2"): return

            # Prevent self-relationship
            if entity1_id == entity2_id and e1_type_enum == e2_type_enum:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_create:error_self_relationship", lang_code, "Entities cannot have a relationship with themselves.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            # Check if relationship already exists
            existing_rel = await crud_relationship.get_relationship_between_entities(
                session, guild_id=interaction.guild_id,
                entity1_id=entity1_id, entity1_type=e1_type_enum,
                entity2_id=entity2_id, entity2_type=e2_type_enum
            )
            if existing_rel:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_create:error_already_exists", lang_code, "A relationship between these entities already exists (ID: {id}). Use update instead.")
                await interaction.followup.send(error_msg.format(id=existing_rel.id), ephemeral=True); return

            # TODO: Validate source_log_id if provided (check if StoryLog entry exists)

            relationship_data_to_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id,
                "entity1_id": entity1_id,
                "entity1_type": e1_type_enum,
                "entity2_id": entity2_id,
                "entity2_type": e2_type_enum,
                "relationship_type": relationship_type,
                "value": value,
                "source_log_id": source_log_id,
            }

            try:
                async with session.begin():
                    created_relationship = await crud_relationship.create(session, obj_in=relationship_data_to_create)
                    await session.flush()
                    if created_relationship:
                         await session.refresh(created_relationship)
            except Exception as e:
                logger.error(f"Error creating Relationship: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_create:error_generic_create", lang_code, "Error creating relationship: {error}")
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return

            if not created_relationship:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "relationship_create:error_creation_failed_unknown", lang_code, "Relationship creation failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_msg_template = await get_localized_message_template(
                session, interaction.guild_id, "relationship_create:success", lang_code,
                "Relationship (ID: {id}) created: {e1_type}({e1_id}) <=> {e2_type}({e2_id}), Type: {type}, Value: {val}."
            )
            await interaction.followup.send(success_msg_template.format(
                id=created_relationship.id,
                e1_type=created_relationship.entity1_type.name, e1_id=created_relationship.entity1_id,
                e2_type=created_relationship.entity2_type.name, e2_id=created_relationship.entity2_id,
                type=created_relationship.relationship_type, val=created_relationship.value
            ), ephemeral=True)

    @relationship_group.command(name="update", description="Update a specific Relationship.")
    @app_commands.describe(
        relationship_id="The database ID of the Relationship to update.",
        field_to_update="Field to update (relationship_type or value).",
        new_value="New value for the field."
    )
    async def relationship_update(self, interaction: discord.Interaction, relationship_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_relationship import crud_relationship
        from src.core.database import get_db_session
        from src.core.crud_base_definitions import update_entity
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any, Optional

        allowed_fields = {
            "relationship_type": str,
            "value": int,
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()

        if field_to_update_lower not in allowed_fields:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "relationship_update:error_field_not_allowed", lang_code,
                    "Field '{field_name}' is not allowed for update. Allowed: {allowed_list}"
                )
            await interaction.followup.send(error_msg.format(field_name=field_to_update, allowed_list=', '.join(allowed_fields.keys())), ephemeral=True)
            return

        parsed_value: Any = None
        field_type = allowed_fields[field_to_update_lower]

        async with get_db_session() as session: # Session for validation and update
            try:
                if field_type == str:
                    parsed_value = new_value
                elif field_type == int:
                    parsed_value = int(new_value)
                # Add more type conversions if other fields become updatable
            except ValueError:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "relationship_update:error_invalid_value_type", lang_code,
                    "Invalid value '{value}' for field '{field_name}'. Expected type: {expected_type}."
                )
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, expected_type=field_type.__name__), ephemeral=True)
                return

            relationship_to_update = await crud_relationship.get_by_id_and_guild(session, id=relationship_id, guild_id=interaction.guild_id)
            if not relationship_to_update:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "relationship_update:error_relationship_not_found", lang_code,
                    "Relationship with ID {id} not found."
                )
                await interaction.followup.send(error_msg.format(id=relationship_id), ephemeral=True)
                return

            update_data_dict = {field_to_update_lower: parsed_value}

            try:
                async with session.begin():
                    updated_relationship = await update_entity(session, entity=relationship_to_update, data=update_data_dict)
                    await session.flush()
                    await session.refresh(updated_relationship)
            except Exception as e:
                logger.error(f"Error updating Relationship {relationship_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "relationship_update:error_generic_update", lang_code,
                    "Error updating Relationship {id}: {error_message}"
                )
                await interaction.followup.send(error_msg.format(id=relationship_id, error_message=str(e)), ephemeral=True)
                return

            success_msg_template = await get_localized_message_template(
                session, interaction.guild_id, "relationship_update:success", lang_code,
                "Relationship ID {id} updated. Field '{field}' set to '{val}'."
            )
            await interaction.followup.send(success_msg_template.format(id=updated_relationship.id, field=field_to_update, val=parsed_value), ephemeral=True)

    @relationship_group.command(name="delete", description="Delete a Relationship.")
    @app_commands.describe(relationship_id="The database ID of the Relationship to delete.")
    async def relationship_delete(self, interaction: discord.Interaction, relationship_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_relationship import crud_relationship
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            relationship_to_delete = await crud_relationship.get_by_id_and_guild(session, id=relationship_id, guild_id=interaction.guild_id)

            if not relationship_to_delete:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "relationship_delete:error_not_found", lang_code,
                    "Relationship with ID {id} not found. Nothing to delete."
                )
                await interaction.followup.send(error_msg.format(id=relationship_id), ephemeral=True)
                return

            rel_repr = f"{relationship_to_delete.entity1_type.name}({relationship_to_delete.entity1_id}) <=> {relationship_to_delete.entity2_type.name}({relationship_to_delete.entity2_id})"

            try:
                async with session.begin():
                    deleted_relationship = await crud_relationship.remove(session, id=relationship_id)

                if deleted_relationship:
                    success_msg = await get_localized_message_template(
                        session, interaction.guild_id, "relationship_delete:success", lang_code,
                        "Relationship (ID: {id}, Details: {repr}) has been deleted successfully."
                    )
                    await interaction.followup.send(success_msg.format(id=relationship_id, repr=rel_repr), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "relationship_delete:error_not_deleted_unknown", lang_code,
                        "Relationship (ID: {id}) was found but could not be deleted."
                    )
                    await interaction.followup.send(error_msg.format(id=relationship_id), ephemeral=True)

            except Exception as e:
                logger.error(f"Error deleting Relationship {relationship_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "relationship_delete:error_generic", lang_code,
                    "An error occurred while deleting Relationship (ID: {id}, Details: {repr}): {error_message}"
                )
                await interaction.followup.send(error_msg.format(id=relationship_id, repr=rel_repr, error_message=str(e)), ephemeral=True)
                return

    # --- Quest CRUD (Questline & GeneratedQuest) ---
    quest_group = app_commands.Group(name="quest", description="Master commands for managing Quests and Questlines.", parent=master_admin)

    # --- Questline Subcommands ---
    @quest_group.command(name="questline_view", description="View details of a specific Questline.")
    @app_commands.describe(questline_id="The database ID of the Questline to view.")
    async def questline_view(self, interaction: discord.Interaction, questline_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_quest import questline_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            # questline_crud uses 'db' as session name
            q_line = await questline_crud.get_by_id_and_guild(session, id=questline_id, guild_id=interaction.guild_id)

            if not q_line:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "questline_view:not_found", lang_code,
                    "Questline with ID {id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg.format(id=questline_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "questline_view:title", lang_code,
                "Questline Details: {ql_title} (ID: {ql_id})"
            )

            ql_title_display = q_line.title_i18n.get(lang_code, q_line.title_i18n.get("en", f"Questline {q_line.id}"))
            embed_title = title_template.format(ql_title=ql_title_display, ql_id=q_line.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_teal())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"questline_view:label_{key}", lang_code, default)

            async def format_json_field(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(q_line.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=q_line.static_id or "N/A", inline=True)
            embed.add_field(name=await get_label("is_main", "Is Main Storyline"), value=str(q_line.is_main_storyline), inline=True)
            embed.add_field(name=await get_label("starting_quest_sid", "Starting Quest Static ID"), value=q_line.starting_quest_static_id or "N/A", inline=True)
            embed.add_field(name=await get_label("req_prev_ql_sid", "Required Previous Questline Static ID"), value=q_line.required_previous_questline_static_id or "N/A", inline=True)

            title_i18n_str = await format_json_field(q_line.title_i18n, "questline_view:value_na_json", "questline_view:error_serialization_title")
            embed.add_field(name=await get_label("title_i18n", "Title (i18n)"), value=f"```json\n{title_i18n_str[:1000]}\n```" + ("..." if len(title_i18n_str) > 1000 else ""), inline=False)

            desc_i18n_str = await format_json_field(q_line.description_i18n, "questline_view:value_na_json", "questline_view:error_serialization_desc")
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```" + ("..." if len(desc_i18n_str) > 1000 else ""), inline=False)

            props_str = await format_json_field(q_line.properties_json, "questline_view:value_na_json", "questline_view:error_serialization_props")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{props_str[:1000]}\n```" + ("..." if len(props_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_group.command(name="questline_list", description="List Questlines in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of Questlines per page.")
    async def questline_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10

        from src.core.crud.crud_quest import questline_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import func, select

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            offset = (page - 1) * limit
            # questline_crud.get_multi_by_guild uses 'db' as session name
            questlines = await questline_crud.get_multi_by_guild(session, guild_id=interaction.guild_id, skip=offset, limit=limit)

            total_ql_stmt = select(func.count(questline_crud.model.id)).where(questline_crud.model.guild_id == interaction.guild_id)
            total_ql_result = await session.execute(total_ql_stmt)
            total_questlines = total_ql_result.scalar_one_or_none() or 0

            if not questlines:
                no_ql_msg = await get_localized_message_template(
                    session, interaction.guild_id, "questline_list:no_questlines_found_page", lang_code,
                    "No Questlines found for this guild (Page {page})."
                )
                await interaction.followup.send(no_ql_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "questline_list:title", lang_code,
                "Questline List (Page {page} of {total_pages})"
            )
            total_pages = ((total_questlines - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_blue())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "questline_list:footer", lang_code,
                "Displaying {count} of {total} total Questlines."
            )
            embed.set_footer(text=footer_template.format(count=len(questlines), total=total_questlines))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "questline_list:ql_field_name", lang_code,
                "ID: {ql_id} | {ql_title} (Static: {static_id})"
            )
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "questline_list:ql_field_value", lang_code,
                "Main: {is_main}, Starts with: {starting_sid}"
            )

            for ql in questlines:
                ql_title_display = ql.title_i18n.get(lang_code, ql.title_i18n.get("en", f"Questline {ql.id}"))
                embed.add_field(
                    name=field_name_template.format(ql_id=ql.id, ql_title=ql_title_display, static_id=ql.static_id or "N/A"),
                    value=field_value_template.format(
                        is_main=str(ql.is_main_storyline),
                        starting_sid=ql.starting_quest_static_id or "N/A"
                    ),
                    inline=False
                )

            if len(embed.fields) == 0:
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "questline_list:no_ql_to_display", lang_code,
                    "No Questlines found to display on page {page}."
                )
                await interaction.followup.send(no_display_msg.format(page=page), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_group.command(name="questline_create", description="Create a new Questline.")
    @app_commands.describe(
        static_id="Static ID for this Questline (unique within guild).",
        title_i18n_json="JSON for Questline title (e.g., {\"en\": \"Main Story\", \"ru\": \"Главный Сюжет\"}).",
        description_i18n_json="Optional: JSON for Questline description.",
        starting_quest_static_id="Optional: Static ID of the first GeneratedQuest in this line.",
        is_main_storyline="Is this a main storyline? (True/False, defaults to False).",
        required_previous_questline_static_id="Optional: Static ID of a Questline that must be completed first.",
        properties_json="Optional: JSON for additional Questline properties."
    )
    async def questline_create(self, interaction: discord.Interaction,
                               static_id: str,
                               title_i18n_json: str,
                               description_i18n_json: Optional[str] = None,
                               starting_quest_static_id: Optional[str] = None,
                               is_main_storyline: bool = False,
                               required_previous_questline_static_id: Optional[str] = None,
                               properties_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_quest import questline_crud, generated_quest_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any, Optional

        lang_code = str(interaction.locale)
        parsed_title_i18n: Dict[str, str]
        parsed_desc_i18n: Optional[Dict[str, str]] = None
        parsed_props: Optional[Dict[str, Any]] = None

        async with get_db_session() as session:
            # Validate static_id uniqueness
            existing_ql_static = await questline_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=static_id)
            if existing_ql_static:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "questline_create:error_static_id_exists", lang_code, "Questline static_id '{id}' already exists.")
                await interaction.followup.send(error_msg.format(id=static_id), ephemeral=True); return

            # Validate starting_quest_static_id if provided
            if starting_quest_static_id:
                start_quest = await generated_quest_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=starting_quest_static_id)
                if not start_quest:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "questline_create:error_start_quest_not_found", lang_code, "Starting quest with static_id '{id}' not found.")
                    await interaction.followup.send(error_msg.format(id=starting_quest_static_id), ephemeral=True); return

            # Validate required_previous_questline_static_id if provided
            if required_previous_questline_static_id:
                prev_ql = await questline_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=required_previous_questline_static_id)
                if not prev_ql:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "questline_create:error_prev_ql_not_found", lang_code, "Required previous questline with static_id '{id}' not found.")
                    await interaction.followup.send(error_msg.format(id=required_previous_questline_static_id), ephemeral=True); return

            try:
                parsed_title_i18n = json.loads(title_i18n_json)
                if not isinstance(parsed_title_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k,v in parsed_title_i18n.items()):
                    raise ValueError("title_i18n_json must be a dict of str:str.")
                if not parsed_title_i18n.get("en") and not parsed_title_i18n.get(lang_code):
                     raise ValueError("title_i18n_json must contain 'en' or current language key.")

                if description_i18n_json:
                    parsed_desc_i18n = json.loads(description_i18n_json)
                    if not isinstance(parsed_desc_i18n, dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in parsed_desc_i18n.items()):
                        raise ValueError("description_i18n_json must be a dict of str:str.")
                if properties_json:
                    parsed_props = json.loads(properties_json)
                    if not isinstance(parsed_props, dict): raise ValueError("properties_json must be a dict.")
            except (json.JSONDecodeError, ValueError) as e:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "questline_create:error_invalid_json", lang_code, "Invalid JSON for i18n/properties: {details}")
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return

            ql_data_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id, "static_id": static_id, "title_i18n": parsed_title_i18n,
                "description_i18n": parsed_desc_i18n or {}, "starting_quest_static_id": starting_quest_static_id,
                "is_main_storyline": is_main_storyline, "required_previous_questline_static_id": required_previous_questline_static_id,
                "properties_json": parsed_props or {}
            }

            try:
                async with session.begin():
                    created_ql = await questline_crud.create(session, obj_in=ql_data_create)
                    await session.flush(); await session.refresh(created_ql)
            except Exception as e:
                logger.error(f"Error creating Questline: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, interaction.guild_id, "questline_create:error_generic_create", lang_code, "Error creating Questline: {error}")
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return

            if not created_ql: # Should be caught by exception
                error_msg = await get_localized_message_template(session, interaction.guild_id, "questline_create:error_unknown_fail", lang_code, "Questline creation failed mysteriously.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title = await get_localized_message_template(session, interaction.guild_id, "questline_create:success_title", lang_code, "Questline Created: {title} (ID: {id})")
            created_ql_title_display = created_ql.title_i18n.get(lang_code, created_ql.title_i18n.get("en", ""))
            embed = discord.Embed(title=success_title.format(title=created_ql_title_display, id=created_ql.id), color=discord.Color.green())
            embed.add_field(name="Static ID", value=created_ql.static_id, inline=True)
            embed.add_field(name="Is Main", value=str(created_ql.is_main_storyline), inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_group.command(name="questline_update", description="Update a specific field for a Questline.")
    @app_commands.describe(
        questline_id="The database ID of the Questline to update.",
        field_to_update="Field to update (e.g., static_id, title_i18n_json, starting_quest_static_id, is_main_storyline).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable; True/False for boolean)."
    )
    async def questline_update(self, interaction: discord.Interaction, questline_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_quest import questline_crud, generated_quest_crud
        from src.core.database import get_db_session
        from src.core.crud_base_definitions import update_entity
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any, Optional

        allowed_fields = {
            "static_id": str,
            "title_i18n_json": dict,
            "description_i18n_json": dict,
            "starting_quest_static_id": (str, type(None)),
            "is_main_storyline": bool,
            "required_previous_questline_static_id": (str, type(None)),
            "properties_json": dict,
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()

        db_field_name = field_to_update_lower
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")

        field_type_info = allowed_fields.get(db_field_name)

        if not field_type_info:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "questline_update:error_field_not_allowed", lang_code, "Field '{f}' not allowed. Allowed: {l}")
            await interaction.followup.send(error_msg.format(f=field_to_update, l=', '.join(allowed_fields.keys())), ephemeral=True); return

        parsed_value: Any = None

        async with get_db_session() as session:
            try:
                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: raise ValueError("static_id cannot be empty.")
                    existing_ql = await questline_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                    if existing_ql and existing_ql.id != questline_id:
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_static_id_exists",lang_code,"Static ID '{id}' already in use.")
                        await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                elif db_field_name in ["title_i18n", "description_i18n", "properties_json"]:
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict): raise ValueError(f"{db_field_name} must be a dict.")
                elif db_field_name == "starting_quest_static_id" or db_field_name == "required_previous_questline_static_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = new_value
                        # Validate existence if setting to a new value
                        if db_field_name == "starting_quest_static_id" and parsed_value:
                            related_quest = await generated_quest_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                            if not related_quest:
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_start_quest_not_found",lang_code,"Starting quest static_id '{id}' not found.")
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                        elif db_field_name == "required_previous_questline_static_id" and parsed_value:
                            related_ql = await questline_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                            if not related_ql:
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_prev_ql_not_found",lang_code,"Required previous questline static_id '{id}' not found.")
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                            if related_ql.id == questline_id: # Prevent self-dependency
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_self_dependency",lang_code,"Questline cannot require itself.")
                                await interaction.followup.send(error_msg, ephemeral=True); return
                elif db_field_name == "is_main_storyline":
                    if new_value.lower() == 'true': parsed_value = True
                    elif new_value.lower() == 'false': parsed_value = False
                    else: raise ValueError("is_main_storyline must be True or False.")
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_unknown_field",lang_code,"Unknown field for update.")
                    await interaction.followup.send(error_msg, ephemeral=True); return
            except ValueError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_invalid_value",lang_code,"Invalid value for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return
            except json.JSONDecodeError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_invalid_json",lang_code,"Invalid JSON for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            ql_to_update = await questline_crud.get_by_id_and_guild(session, id=questline_id, guild_id=interaction.guild_id)
            if not ql_to_update:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_not_found",lang_code,"Questline ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=questline_id), ephemeral=True); return

            update_data = {db_field_name: parsed_value}
            try:
                async with session.begin():
                    updated_ql = await update_entity(session, entity=ql_to_update, data=update_data)
                    await session.flush(); await session.refresh(updated_ql)
            except Exception as e:
                logger.error(f"Error updating Questline {questline_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_generic_update",lang_code,"Error updating Questline {id}: {err}")
                await interaction.followup.send(error_msg.format(id=questline_id, err=str(e)), ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:success",lang_code,"Questline ID {id} updated. Field '{f}' set to '{v}'.")
            new_val_display = str(parsed_value)
            if isinstance(parsed_value, dict): new_val_display = json.dumps(parsed_value)
            await interaction.followup.send(success_msg.format(id=updated_ql.id, f=field_to_update, v=new_val_display), ephemeral=True)

    @quest_group.command(name="questline_delete", description="Delete a Questline.")
    @app_commands.describe(questline_id="The database ID of the Questline to delete.")
    async def questline_delete(self, interaction: discord.Interaction, questline_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_quest import questline_crud, generated_quest_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import select

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            ql_to_delete = await questline_crud.get_by_id_and_guild(session, id=questline_id, guild_id=interaction.guild_id)

            if not ql_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_delete:error_not_found",lang_code,"Questline ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=questline_id), ephemeral=True); return

            ql_title_for_msg = ql_to_delete.title_i18n.get(lang_code, ql_to_delete.title_i18n.get("en", f"Questline {ql_to_delete.id}"))

            # Check for GeneratedQuest dependencies
            linked_quests_stmt = select(generated_quest_crud.model.id).where(
                generated_quest_crud.model.questline_id == questline_id,
                generated_quest_crud.model.guild_id == interaction.guild_id # Ensure quest is in the same guild
            ).limit(1)
            linked_quest_exists = (await session.execute(linked_quests_stmt)).scalar_one_or_none()
            if linked_quest_exists:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_delete:error_quest_dependency",lang_code,"Cannot delete Questline '{title}' (ID: {id}) as it has associated quests. Delete them first.")
                await interaction.followup.send(error_msg.format(title=ql_title_for_msg, id=questline_id), ephemeral=True); return

            # Check for other Questlines requiring this one
            if ql_to_delete.static_id: # Only if this questline has a static_id to be referenced
                dependent_ql_stmt = select(questline_crud.model.id).where(
                    questline_crud.model.required_previous_questline_static_id == ql_to_delete.static_id,
                    questline_crud.model.guild_id == interaction.guild_id
                ).limit(1)
                dependent_ql_exists = (await session.execute(dependent_ql_stmt)).scalar_one_or_none()
                if dependent_ql_exists:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_delete:error_dependent_ql_dependency",lang_code,"Cannot delete Questline '{title}' (ID: {id}) as other questlines depend on it. Update those dependencies first.")
                    await interaction.followup.send(error_msg.format(title=ql_title_for_msg, id=questline_id), ephemeral=True); return

            try:
                async with session.begin():
                    deleted_ql = await questline_crud.remove(session, id=questline_id)

                if deleted_ql:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"questline_delete:success",lang_code,"Questline '{title}' (ID: {id}) deleted successfully.")
                    await interaction.followup.send(success_msg.format(title=ql_title_for_msg, id=questline_id), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_delete:error_unknown_delete_fail",lang_code,"Questline (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=questline_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Questline {questline_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_delete:error_generic_delete",lang_code,"Error deleting Questline '{title}' (ID: {id}): {err}")
                await interaction.followup.send(error_msg.format(title=ql_title_for_msg, id=questline_id, err=str(e)), ephemeral=True)

    # --- GeneratedQuest Subcommands ---
    @quest_group.command(name="generated_quest_view", description="View details of a specific GeneratedQuest.")
    @app_commands.describe(quest_id="The database ID of the GeneratedQuest to view.")
    async def generated_quest_view(self, interaction: discord.Interaction, quest_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_quest import generated_quest_crud #, quest_step_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            # generated_quest_crud uses 'db' as session name
            gq = await generated_quest_crud.get_by_id_and_guild(session, id=quest_id, guild_id=interaction.guild_id)

            if not gq:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "gq_view:not_found", lang_code,
                    "GeneratedQuest with ID {id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg.format(id=quest_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "gq_view:title", lang_code,
                "GeneratedQuest Details: {gq_title} (ID: {gq_id})"
            )

            gq_title_display = gq.title_i18n.get(lang_code, gq.title_i18n.get("en", f"Quest {gq.id}"))
            embed_title = title_template.format(gq_title=gq_title_display, gq_id=gq.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_orange())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"gq_view:label_{key}", lang_code, default)

            async def format_json_field(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(gq.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=gq.static_id or "N/A", inline=True)
            embed.add_field(name=await get_label("questline_id", "Questline ID"), value=str(gq.questline_id) if gq.questline_id else "N/A", inline=True)
            embed.add_field(name=await get_label("type", "Type"), value=gq.type or "N/A", inline=True)
            embed.add_field(name=await get_label("is_repeatable", "Is Repeatable"), value=str(gq.is_repeatable), inline=True)

            title_i18n_str = await format_json_field(gq.title_i18n, "gq_view:value_na_json", "gq_view:error_serialization_title")
            embed.add_field(name=await get_label("title_i18n", "Title (i18n)"), value=f"```json\n{title_i18n_str[:1000]}\n```" + ("..." if len(title_i18n_str) > 1000 else ""), inline=False)

            desc_i18n_str = await format_json_field(gq.description_i18n, "gq_view:value_na_json", "gq_view:error_serialization_desc")
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```" + ("..." if len(desc_i18n_str) > 1000 else ""), inline=False)

            props_str = await format_json_field(gq.properties_json, "gq_view:value_na_json", "gq_view:error_serialization_props")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{props_str[:1000]}\n```" + ("..." if len(props_str) > 1000 else ""), inline=False)

            rewards_str = await format_json_field(gq.rewards_json, "gq_view:value_na_json", "gq_view:error_serialization_rewards")
            embed.add_field(name=await get_label("rewards", "Rewards JSON"), value=f"```json\n{rewards_str[:1000]}\n```" + ("..." if len(rewards_str) > 1000 else ""), inline=False)

            # TODO: Optionally list QuestSteps associated with this quest.
            # steps = await quest_step_crud.get_all_for_quest(session, quest_id=gq.id)
            # if steps:
            #    step_info = "\n".join([f"Order: {s.step_order}, Title: {s.title_i18n.get(lang_code, s.title_i18n.get('en', 'Step'))}" for s in steps])
            #    embed.add_field(name="Steps", value=step_info[:1024], inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_group.command(name="generated_quest_list", description="List GeneratedQuests in this guild, optionally filtered by Questline.")
    @app_commands.describe(
        questline_id="Optional: Database ID of the Questline to filter quests by.",
        page="Page number to display.",
        limit="Number of GeneratedQuests per page."
    )
    async def generated_quest_list(self, interaction: discord.Interaction,
                                   questline_id: Optional[int] = None,
                                   page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10

        from src.core.crud.crud_quest import generated_quest_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import func, select, and_

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            filters = [generated_quest_crud.model.guild_id == interaction.guild_id]
            if questline_id is not None:
                filters.append(generated_quest_crud.model.questline_id == questline_id)

            offset = (page - 1) * limit

            query = select(generated_quest_crud.model).where(and_(*filters)).offset(offset).limit(limit).order_by(generated_quest_crud.model.id.desc())
            result = await session.execute(query)
            g_quests = result.scalars().all()

            count_query = select(func.count(generated_quest_crud.model.id)).where(and_(*filters))
            total_gq_result = await session.execute(count_query)
            total_g_quests = total_gq_result.scalar_one_or_none() or 0

            filter_desc = f"Questline ID: {questline_id}" if questline_id else "All"

            if not g_quests:
                no_gq_msg = await get_localized_message_template(
                    session, interaction.guild_id, "gq_list:no_gq_found_page", lang_code,
                    "No GeneratedQuests found for {filter_criteria} (Page {page})."
                )
                await interaction.followup.send(no_gq_msg.format(filter_criteria=filter_desc, page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "gq_list:title", lang_code,
                "GeneratedQuest List ({filter_criteria} - Page {page} of {total_pages})"
            )
            total_pages = ((total_g_quests - 1) // limit) + 1
            embed_title = title_template.format(filter_criteria=filter_desc, page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_gold())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "gq_list:footer", lang_code,
                "Displaying {count} of {total} total GeneratedQuests."
            )
            embed.set_footer(text=footer_template.format(count=len(g_quests), total=total_g_quests))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "gq_list:gq_field_name", lang_code,
                "ID: {gq_id} | {gq_title} (Static: {static_id})"
            )
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "gq_list:gq_field_value", lang_code,
                "Type: {type}, Questline ID: {ql_id}, Repeatable: {repeatable}"
            )

            for gq_obj in g_quests:
                gq_title_display = gq_obj.title_i18n.get(lang_code, gq_obj.title_i18n.get("en", f"Quest {gq_obj.id}"))
                embed.add_field(
                    name=field_name_template.format(gq_id=gq_obj.id, gq_title=gq_title_display, static_id=gq_obj.static_id or "N/A"),
                    value=field_value_template.format(
                        type=gq_obj.type or "N/A",
                        ql_id=str(gq_obj.questline_id) if gq_obj.questline_id else "N/A",
                        repeatable=str(gq_obj.is_repeatable)
                    ),
                    inline=False
                )

            if len(embed.fields) == 0:
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "gq_list:no_gq_to_display", lang_code,
                    "No GeneratedQuests found to display on page {page} for {filter_criteria}."
                )
                await interaction.followup.send(no_display_msg.format(page=page, filter_criteria=filter_desc), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_group.command(name="generated_quest_create", description="Create a new GeneratedQuest.")
    @app_commands.describe(
        static_id="Static ID for this quest (unique within guild).",
        title_i18n_json="JSON for quest title (e.g., {\"en\": \"Slay Goblins\", \"ru\": \"Убить Гоблинов\"}).",
        description_i18n_json="Optional: JSON for quest description.",
        quest_type="Optional: Type of the quest (e.g., SLAY, FETCH, EXPLORE).",
        questline_id="Optional: Database ID of the Questline this quest belongs to.",
        is_repeatable="Is this quest repeatable? (True/False, defaults to False).",
        properties_json="Optional: JSON for additional quest properties.",
        rewards_json="Optional: JSON describing rewards for completing the quest."
    )
    async def generated_quest_create(self, interaction: discord.Interaction,
                                     static_id: str,
                                     title_i18n_json: str,
                                     description_i18n_json: Optional[str] = None,
                                     quest_type: Optional[str] = None,
                                     questline_id: Optional[int] = None,
                                     is_repeatable: bool = False,
                                     properties_json: Optional[str] = None,
                                     rewards_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_quest import generated_quest_crud, questline_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any, Optional

        lang_code = str(interaction.locale)
        parsed_title_i18n: Dict[str, str]
        parsed_desc_i18n: Optional[Dict[str, str]] = None
        parsed_props: Optional[Dict[str, Any]] = None
        parsed_rewards: Optional[Dict[str, Any]] = None

        async with get_db_session() as session:
            # Validate static_id uniqueness
            existing_gq_static = await generated_quest_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=static_id)
            if existing_gq_static:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "gq_create:error_static_id_exists", lang_code, "GeneratedQuest static_id '{id}' already exists.")
                await interaction.followup.send(error_msg.format(id=static_id), ephemeral=True); return

            # Validate questline_id if provided
            if questline_id:
                ql = await questline_crud.get_by_id_and_guild(session, id=questline_id, guild_id=interaction.guild_id)
                if not ql:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "gq_create:error_questline_not_found", lang_code, "Questline with ID {id} not found.")
                    await interaction.followup.send(error_msg.format(id=questline_id), ephemeral=True); return

            try:
                parsed_title_i18n = json.loads(title_i18n_json)
                if not isinstance(parsed_title_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k,v in parsed_title_i18n.items()):
                    raise ValueError("title_i18n_json must be a dict of str:str.")
                if not parsed_title_i18n.get("en") and not parsed_title_i18n.get(lang_code):
                     raise ValueError("title_i18n_json must contain 'en' or current language key.")

                if description_i18n_json:
                    parsed_desc_i18n = json.loads(description_i18n_json)
                    if not isinstance(parsed_desc_i18n, dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in parsed_desc_i18n.items()):
                        raise ValueError("description_i18n_json must be a dict of str:str.")
                if properties_json:
                    parsed_props = json.loads(properties_json)
                    if not isinstance(parsed_props, dict): raise ValueError("properties_json must be a dict.")
                if rewards_json:
                    parsed_rewards = json.loads(rewards_json)
                    if not isinstance(parsed_rewards, dict): raise ValueError("rewards_json must be a dict.")
            except (json.JSONDecodeError, ValueError) as e:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "gq_create:error_invalid_json", lang_code, "Invalid JSON for i18n/properties/rewards: {details}")
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return

            gq_data_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id, "static_id": static_id, "title_i18n": parsed_title_i18n,
                "description_i18n": parsed_desc_i18n or {}, "type": quest_type, "questline_id": questline_id,
                "is_repeatable": is_repeatable, "properties_json": parsed_props or {}, "rewards_json": parsed_rewards or {}
            }

            try:
                async with session.begin():
                    created_gq = await generated_quest_crud.create(session, obj_in=gq_data_create)
                    await session.flush(); await session.refresh(created_gq)
            except Exception as e:
                logger.error(f"Error creating GeneratedQuest: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, interaction.guild_id, "gq_create:error_generic_create", lang_code, "Error creating GeneratedQuest: {error}")
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return

            if not created_gq:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "gq_create:error_unknown_fail", lang_code, "GeneratedQuest creation failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title = await get_localized_message_template(session, interaction.guild_id, "gq_create:success_title", lang_code, "GeneratedQuest Created: {title} (ID: {id})")
            created_gq_title_display = created_gq.title_i18n.get(lang_code, created_gq.title_i18n.get("en", ""))
            embed = discord.Embed(title=success_title.format(title=created_gq_title_display, id=created_gq.id), color=discord.Color.green())
            embed.add_field(name="Static ID", value=created_gq.static_id, inline=True)
            embed.add_field(name="Type", value=created_gq.type or "N/A", inline=True)
            embed.add_field(name="Questline ID", value=str(created_gq.questline_id) if created_gq.questline_id else "N/A", inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_group.command(name="generated_quest_update", description="Update a specific field for a GeneratedQuest.")
    @app_commands.describe(
        quest_id="The database ID of the GeneratedQuest to update.",
        field_to_update="Field to update (e.g., static_id, title_i18n_json, questline_id, is_repeatable).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable; True/False for boolean)."
    )
    async def generated_quest_update(self, interaction: discord.Interaction, quest_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_quest import generated_quest_crud, questline_crud
        from src.core.database import get_db_session
        from src.core.crud_base_definitions import update_entity
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any, Optional

        allowed_fields = {
            "static_id": str,
            "title_i18n_json": dict,
            "description_i18n_json": dict,
            "type": (str, type(None)),
            "questline_id": (int, type(None)),
            "is_repeatable": bool,
            "properties_json": dict,
            "rewards_json": dict,
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()

        db_field_name = field_to_update_lower
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")

        field_type_info = allowed_fields.get(db_field_name)

        if not field_type_info:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "gq_update:error_field_not_allowed", lang_code, "Field '{f}' not allowed. Allowed: {l}")
            await interaction.followup.send(error_msg.format(f=field_to_update, l=', '.join(allowed_fields.keys())), ephemeral=True); return

        parsed_value: Any = None

        async with get_db_session() as session:
            try:
                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: raise ValueError("static_id cannot be empty.")
                    existing_gq = await generated_quest_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                    if existing_gq and existing_gq.id != quest_id:
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:error_static_id_exists",lang_code,"Static ID '{id}' already in use.")
                        await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                elif db_field_name in ["title_i18n", "description_i18n", "properties_json", "rewards_json"]:
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict): raise ValueError(f"{db_field_name} must be a dict.")
                elif db_field_name == "type":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = new_value # Assuming type is a string
                elif db_field_name == "questline_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = int(new_value)
                        if parsed_value is not None: # Validate questline exists
                            ql = await questline_crud.get_by_id_and_guild(session, id=parsed_value, guild_id=interaction.guild_id)
                            if not ql:
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:error_questline_not_found",lang_code,"Questline ID '{id}' not found.")
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                elif db_field_name == "is_repeatable":
                    if new_value.lower() == 'true': parsed_value = True
                    elif new_value.lower() == 'false': parsed_value = False
                    else: raise ValueError("is_repeatable must be True or False.")
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:error_unknown_field",lang_code,"Unknown field for update.")
                    await interaction.followup.send(error_msg, ephemeral=True); return
            except ValueError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:error_invalid_value",lang_code,"Invalid value for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return
            except json.JSONDecodeError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:error_invalid_json",lang_code,"Invalid JSON for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            gq_to_update = await generated_quest_crud.get_by_id_and_guild(session, id=quest_id, guild_id=interaction.guild_id)
            if not gq_to_update:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:error_not_found",lang_code,"GeneratedQuest ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=quest_id), ephemeral=True); return

            update_data = {db_field_name: parsed_value}
            try:
                async with session.begin():
                    updated_gq = await update_entity(session, entity=gq_to_update, data=update_data)
                    await session.flush(); await session.refresh(updated_gq)
            except Exception as e:
                logger.error(f"Error updating GeneratedQuest {quest_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:error_generic_update",lang_code,"Error updating GeneratedQuest {id}: {err}")
                await interaction.followup.send(error_msg.format(id=quest_id, err=str(e)), ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:success",lang_code,"GeneratedQuest ID {id} updated. Field '{f}' set to '{v}'.")
            new_val_display = str(parsed_value)
            if isinstance(parsed_value, dict): new_val_display = json.dumps(parsed_value)
            await interaction.followup.send(success_msg.format(id=updated_gq.id, f=field_to_update, v=new_val_display), ephemeral=True)

    @quest_group.command(name="generated_quest_delete", description="Delete a GeneratedQuest and its associated steps & progress.")
    @app_commands.describe(quest_id="The database ID of the GeneratedQuest to delete.")
    async def generated_quest_delete(self, interaction: discord.Interaction, quest_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_quest import generated_quest_crud, quest_step_crud, player_quest_progress_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import delete # For bulk delete

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            gq_to_delete = await generated_quest_crud.get_by_id_and_guild(session, id=quest_id, guild_id=interaction.guild_id)

            if not gq_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_delete:error_not_found",lang_code,"GeneratedQuest ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=quest_id), ephemeral=True); return

            gq_title_for_msg = gq_to_delete.title_i18n.get(lang_code, gq_to_delete.title_i18n.get("en", f"Quest {gq_to_delete.id}"))

            try:
                async with session.begin():
                    # Delete associated QuestSteps
                    # Assuming QuestStep model is imported as QStepModel for clarity
                    from src.models.quest import QuestStep as QStepModel
                    stmt_steps = delete(QStepModel).where(QStepModel.quest_id == quest_id)
                    await session.execute(stmt_steps)

                    # Delete associated PlayerQuestProgress
                    # Assuming PlayerQuestProgress model is imported as PQPModel
                    from src.models.quest import PlayerQuestProgress as PQPModel
                    stmt_progress = delete(PQPModel).where(PQPModel.quest_id == quest_id)
                    # Note: PlayerQuestProgress also has guild_id, but deleting by quest_id should be sufficient if quest_id is globally unique or if cascade is set up.
                    # For safety, let's ensure we only delete progress from the same guild, though this should be implicit if quests are guild-scoped.
                    # stmt_progress = delete(PQPModel).where(PQPModel.quest_id == quest_id, PQPModel.guild_id == interaction.guild_id)
                    await session.execute(stmt_progress)

                    # Delete the GeneratedQuest itself
                    deleted_gq = await generated_quest_crud.remove(session, id=quest_id)

                if deleted_gq:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"gq_delete:success",lang_code,"GeneratedQuest '{title}' (ID: {id}) and its data deleted.")
                    await interaction.followup.send(success_msg.format(title=gq_title_for_msg, id=quest_id), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_delete:error_unknown_delete_fail",lang_code,"GeneratedQuest (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=quest_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting GeneratedQuest {quest_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_delete:error_generic_delete",lang_code,"Error deleting GeneratedQuest '{title}' (ID: {id}): {err}")
                await interaction.followup.send(error_msg.format(title=gq_title_for_msg, id=quest_id, err=str(e)), ephemeral=True)

    # --- CombatEncounter CRUD ---
    combat_encounter_group = app_commands.Group(name="combat_encounter", description="Master commands for managing Combat Encounters.", parent=master_admin)

    @combat_encounter_group.command(name="view", description="View details of a specific Combat Encounter.")
    @app_commands.describe(encounter_id="The database ID of the Combat Encounter to view.")
    async def combat_encounter_view(self, interaction: discord.Interaction, encounter_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_combat_encounter import combat_encounter_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            encounter = await combat_encounter_crud.get_by_id_and_guild(session, id=encounter_id, guild_id=interaction.guild_id)

            if not encounter:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "combat_encounter_view:not_found", lang_code,
                    "Combat Encounter with ID {id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg.format(id=encounter_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "combat_encounter_view:title", lang_code,
                "Combat Encounter Details (ID: {id})"
            )
            embed_title = title_template.format(id=encounter.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_red())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"combat_encounter_view:label_{key}", lang_code, default)

            async def format_json_field(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(encounter.guild_id), inline=True)
            embed.add_field(name=await get_label("location_id", "Location ID"), value=str(encounter.location_id) if encounter.location_id else "N/A", inline=True)
            embed.add_field(name=await get_label("status", "Status"), value=encounter.status.value if encounter.status else "N/A", inline=True)
            embed.add_field(name=await get_label("turn_number", "Turn Number"), value=str(encounter.current_turn_number), inline=True)
            embed.add_field(name=await get_label("current_index", "Current Index"), value=str(encounter.current_index_in_turn_order), inline=True)

            current_entity_id_val = str(encounter.current_turn_entity_id) if encounter.current_turn_entity_id else "N/A"
            current_entity_type_val = encounter.current_turn_entity_type.value if encounter.current_turn_entity_type else "N/A"
            embed.add_field(name=await get_label("current_entity", "Current Turn Entity"), value=f"ID: {current_entity_id_val}, Type: {current_entity_type_val}", inline=True)

            participants_str = await format_json_field(encounter.participants_json, "combat_encounter_view:value_na_json", "combat_encounter_view:error_serialization_participants")
            embed.add_field(name=await get_label("participants", "Participants JSON"), value=f"```json\n{participants_str[:1000]}\n```" + ("..." if len(participants_str) > 1000 else ""), inline=False)

            turn_order_str = await format_json_field(encounter.turn_order_json, "combat_encounter_view:value_na_json", "combat_encounter_view:error_serialization_turn_order")
            embed.add_field(name=await get_label("turn_order", "Turn Order JSON"), value=f"```json\n{turn_order_str[:1000]}\n```" + ("..." if len(turn_order_str) > 1000 else ""), inline=False)

            rules_snapshot_str = await format_json_field(encounter.rules_config_snapshot_json, "combat_encounter_view:value_na_json", "combat_encounter_view:error_serialization_rules")
            embed.add_field(name=await get_label("rules_snapshot", "Rules Snapshot JSON"), value=f"```json\n{rules_snapshot_str[:1000]}\n```" + ("..." if len(rules_snapshot_str) > 1000 else ""), inline=False)

            combat_log_str = await format_json_field(encounter.combat_log_json, "combat_encounter_view:value_na_json", "combat_encounter_view:error_serialization_log")
            embed.add_field(name=await get_label("combat_log", "Combat Log JSON"), value=f"```json\n{combat_log_str[:1000]}\n```" + ("..." if len(combat_log_str) > 1000 else ""), inline=False)

            created_at_val = discord.utils.format_dt(encounter.created_at, style='F') if encounter.created_at else "N/A"
            updated_at_val = discord.utils.format_dt(encounter.updated_at, style='F') if encounter.updated_at else "N/A"
            embed.add_field(name=await get_label("created_at", "Created At"), value=created_at_val, inline=False)
            embed.add_field(name=await get_label("updated_at", "Updated At"), value=updated_at_val, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @combat_encounter_group.command(name="list", description="List Combat Encounters in this guild, optionally filtered by status.")
    @app_commands.describe(
        status="Optional: Filter by status (e.g., ACTIVE, FINISHED_PLAYER_WON, FINISHED_NPC_WON).",
        page="Page number to display.",
        limit="Number of Combat Encounters per page."
    )
    async def combat_encounter_list(self, interaction: discord.Interaction,
                                    status: Optional[str] = None,
                                    page: int = 1, limit: int = 5): # Limit to 5 due to potentially large embeds
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 5: limit = 5

        from src.core.crud.crud_combat_encounter import combat_encounter_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from src.models.enums import CombatStatus # For status validation
        from sqlalchemy import func, select, and_

        lang_code = str(interaction.locale)
        status_enum: Optional[CombatStatus] = None

        async with get_db_session() as session:
            if status:
                try:
                    status_enum = CombatStatus[status.upper()]
                except KeyError:
                    valid_statuses = ", ".join([s.name for s in CombatStatus])
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "ce_list:error_invalid_status", lang_code, "Invalid status. Valid: {list}")
                    await interaction.followup.send(error_msg.format(list=valid_statuses), ephemeral=True); return

            filters = [combat_encounter_crud.model.guild_id == interaction.guild_id]
            if status_enum:
                filters.append(combat_encounter_crud.model.status == status_enum)

            offset = (page - 1) * limit

            query = select(combat_encounter_crud.model).where(and_(*filters)).offset(offset).limit(limit).order_by(combat_encounter_crud.model.id.desc())
            result = await session.execute(query)
            encounters = result.scalars().all()

            count_query = select(func.count(combat_encounter_crud.model.id)).where(and_(*filters))
            total_enc_result = await session.execute(count_query)
            total_encounters = total_enc_result.scalar_one_or_none() or 0

            filter_desc_key = "ce_list:filter_all" if not status_enum else "ce_list:filter_status"
            filter_desc_default = "All" if not status_enum else "Status: {status_name}"
            filter_desc_val = await get_localized_message_template(session, interaction.guild_id, filter_desc_key, lang_code, filter_desc_default)
            filter_display = filter_desc_val.format(status_name=status_enum.name if status_enum else "")


            if not encounters:
                no_enc_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ce_list:no_encounters_found_page", lang_code,
                    "No Combat Encounters found for {filter_criteria} (Page {page})."
                )
                await interaction.followup.send(no_enc_msg.format(filter_criteria=filter_display, page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "ce_list:title", lang_code,
                "Combat Encounter List ({filter_criteria} - Page {page} of {total_pages})"
            )
            total_pages = ((total_encounters - 1) // limit) + 1
            embed_title = title_template.format(filter_criteria=filter_display, page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_purple())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "ce_list:footer", lang_code,
                "Displaying {count} of {total} total Encounters."
            )
            embed.set_footer(text=footer_template.format(count=len(encounters), total=total_encounters))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "ce_list:encounter_field_name", lang_code,
                "ID: {id} | Status: {status_val}"
            )
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "ce_list:encounter_field_value", lang_code,
                "Location ID: {loc_id}, Turn: {turn}, Participants: {p_count}"
            )

            for enc in encounters:
                participant_count = len(enc.participants_json.get("entities", [])) if enc.participants_json else 0
                embed.add_field(
                    name=field_name_template.format(id=enc.id, status_val=enc.status.value if enc.status else "N/A"),
                    value=field_value_template.format(
                        loc_id=str(enc.location_id) if enc.location_id else "N/A",
                        turn=enc.current_turn_number,
                        p_count=participant_count
                    ),
                    inline=False
                )

            if len(embed.fields) == 0:
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ce_list:no_enc_to_display", lang_code,
                    "No Encounters found to display on page {page} for {filter_criteria}."
                )
                await interaction.followup.send(no_display_msg.format(page=page, filter_criteria=filter_display), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @combat_encounter_group.command(name="delete", description="Delete a Combat Encounter.")
    @app_commands.describe(encounter_id="The database ID of the Combat Encounter to delete.")
    async def combat_encounter_delete(self, interaction: discord.Interaction, encounter_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_combat_encounter import combat_encounter_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        # Potentially need Player CRUD to update player statuses if deleting an ACTIVE combat.
        # from src.core.crud.crud_player import player_crud
        # from src.models.enums import PlayerStatus

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            encounter_to_delete = await combat_encounter_crud.get_by_id_and_guild(session, id=encounter_id, guild_id=interaction.guild_id)

            if not encounter_to_delete:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ce_delete:error_not_found", lang_code,
                    "Combat Encounter with ID {id} not found. Nothing to delete."
                )
                await interaction.followup.send(error_msg.format(id=encounter_id), ephemeral=True)
                return

            encounter_repr = f"Encounter ID {encounter_to_delete.id} (Status: {encounter_to_delete.status.value if encounter_to_delete.status else 'Unknown'})"

            # Optional: Add logic to reset player/party statuses if deleting an ACTIVE combat.
            # This can be complex as it involves parsing participants_json.
            # For now, a simple delete is implemented. Master should ensure combat is resolved or cleanup manually.
            # if encounter_to_delete.status == CombatStatus.ACTIVE and encounter_to_delete.participants_json:
            #     try:
            #         async with session.begin_nested(): # or use separate transaction for player updates
            #             for p_info in encounter_to_delete.participants_json.get("entities", []):
            #                 if p_info.get("type") == RelationshipEntityType.PLAYER.value: # or .name depending on storage
            #                     player = await player_crud.get(session, id=p_info.get("id"))
            #                     if player and player.current_status == PlayerStatus.IN_COMBAT:
            #                         player.current_status = PlayerStatus.ACTIVE
            #                         session.add(player)
            #             await session.flush()
            #         logger.info(f"Reset player statuses for deleted active combat {encounter_id}")
            #     except Exception as e_status:
            #         logger.error(f"Error resetting player statuses for deleted combat {encounter_id}: {e_status}")
            #         # Decide if this error should halt deletion or just be logged.

            try:
                async with session.begin():
                    deleted_encounter = await combat_encounter_crud.remove(session, id=encounter_id)

                if deleted_encounter:
                    success_msg = await get_localized_message_template(
                        session, interaction.guild_id, "ce_delete:success", lang_code,
                        "Combat Encounter (ID: {id}) has been deleted successfully."
                    )
                    await interaction.followup.send(success_msg.format(id=encounter_id), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "ce_delete:error_not_deleted_unknown", lang_code,
                        "Combat Encounter (ID: {id}) was found but could not be deleted."
                    )
                    await interaction.followup.send(error_msg.format(id=encounter_id), ephemeral=True)

            except Exception as e:
                logger.error(f"Error deleting Combat Encounter {encounter_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ce_delete:error_generic", lang_code,
                    "An error occurred while deleting Combat Encounter (ID: {id}): {error_message}"
                )
                await interaction.followup.send(error_msg.format(id=encounter_id, error_message=str(e)), ephemeral=True)
                return

    # --- GlobalNpc CRUD ---
    global_npc_group = app_commands.Group(name="global_npc", description="Master commands for managing Global NPCs.", parent=master_admin)

    @global_npc_group.command(name="view", description="View details of a specific Global NPC.")
    @app_commands.describe(global_npc_id="The database ID of the Global NPC to view.")
    async def global_npc_view(self, interaction: discord.Interaction, global_npc_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_global_npc import global_npc_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            gnpc = await global_npc_crud.get_by_id_and_guild(session, id=global_npc_id, guild_id=interaction.guild_id)

            if not gnpc:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "global_npc_view:not_found", lang_code,
                    "Global NPC with ID {id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg.format(id=global_npc_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "global_npc_view:title", lang_code,
                "Global NPC Details: {name} (ID: {id})"
            )

            gnpc_name_display = gnpc.name_i18n.get(lang_code, gnpc.name_i18n.get("en", f"Global NPC {gnpc.id}"))
            embed_title = title_template.format(name=gnpc_name_display, id=gnpc.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.fuchsia())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"global_npc_view:label_{key}", lang_code, default)

            async def format_json_field(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(gnpc.guild_id), inline=True)
            embed.add_field(name=await get_label("npc_template_id", "NPC Template ID"), value=str(gnpc.npc_template_id) if gnpc.npc_template_id else "N/A", inline=True)
            embed.add_field(name=await get_label("current_location_id", "Current Location ID"), value=str(gnpc.current_location_id) if gnpc.current_location_id else "N/A", inline=True)
            embed.add_field(name=await get_label("current_hp", "Current HP"), value=str(gnpc.current_hp) if gnpc.current_hp is not None else "N/A", inline=True)
            embed.add_field(name=await get_label("mobile_group_id", "Mobile Group ID"), value=str(gnpc.mobile_group_id) if gnpc.mobile_group_id else "N/A", inline=True)


            name_i18n_str = await format_json_field(gnpc.name_i18n, "global_npc_view:value_na_json", "global_npc_view:error_serialization_name")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```" + ("..." if len(name_i18n_str) > 1000 else ""), inline=False)

            route_str = await format_json_field(gnpc.route_json, "global_npc_view:value_na_json", "global_npc_view:error_serialization_route")
            embed.add_field(name=await get_label("route_json", "Route JSON"), value=f"```json\n{route_str[:1000]}\n```" + ("..." if len(route_str) > 1000 else ""), inline=False)

            properties_str = await format_json_field(gnpc.properties_json, "global_npc_view:value_na_json", "global_npc_view:error_serialization_properties")
            embed.add_field(name=await get_label("properties_json", "Properties JSON"), value=f"```json\n{properties_str[:1000]}\n```" + ("..." if len(properties_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @global_npc_group.command(name="list", description="List Global NPCs in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of Global NPCs per page.")
    async def global_npc_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10

        from src.core.crud.crud_global_npc import global_npc_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import func, select

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            offset = (page - 1) * limit
            # global_npc_crud.get_multi_by_guild_id uses 'session' as param name
            gnpcs = await global_npc_crud.get_multi_by_guild_id(session, guild_id=interaction.guild_id, skip=offset, limit=limit)

            total_gnpcs_stmt = select(func.count(global_npc_crud.model.id)).where(global_npc_crud.model.guild_id == interaction.guild_id)
            total_gnpcs_result = await session.execute(total_gnpcs_stmt)
            total_global_npcs = total_gnpcs_result.scalar_one_or_none() or 0

            if not gnpcs:
                no_gnpcs_msg = await get_localized_message_template(
                    session, interaction.guild_id, "global_npc_list:no_gnpcs_found_page", lang_code,
                    "No Global NPCs found for this guild (Page {page})."
                )
                await interaction.followup.send(no_gnpcs_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "global_npc_list:title", lang_code,
                "Global NPC List (Page {page} of {total_pages})"
            )
            total_pages = ((total_global_npcs - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_magenta()) # Changed color

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "global_npc_list:footer", lang_code,
                "Displaying {count} of {total} total Global NPCs."
            )
            embed.set_footer(text=footer_template.format(count=len(gnpcs), total=total_global_npcs))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "global_npc_list:gnpc_field_name", lang_code,
                "ID: {id} | {name}"
            )
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "global_npc_list:gnpc_field_value", lang_code,
                "Location ID: {loc_id}, HP: {hp}, Group ID: {group_id}"
            )

            for gnpc_obj in gnpcs: # Renamed to avoid conflict
                gnpc_name_display = gnpc_obj.name_i18n.get(lang_code, gnpc_obj.name_i18n.get("en", f"Global NPC {gnpc_obj.id}"))
                embed.add_field(
                    name=field_name_template.format(id=gnpc_obj.id, name=gnpc_name_display),
                    value=field_value_template.format(
                        loc_id=str(gnpc_obj.current_location_id) if gnpc_obj.current_location_id else "N/A",
                        hp=str(gnpc_obj.current_hp) if gnpc_obj.current_hp is not None else "N/A",
                        group_id=str(gnpc_obj.mobile_group_id) if gnpc_obj.mobile_group_id else "N/A"
                    ),
                    inline=False
                )

            if len(embed.fields) == 0:
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "global_npc_list:no_gnpcs_to_display", lang_code,
                    "No Global NPCs found to display on page {page}."
                )
                await interaction.followup.send(no_display_msg.format(page=page), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @global_npc_group.command(name="create", description="Create a new Global NPC.")
    @app_commands.describe(
        name_i18n_json="JSON for Global NPC name (e.g., {\"en\": \"Travelling Merchant\"}).",
        npc_template_id="Optional: Database ID of a GeneratedNPC to use as a template.",
        current_location_id="Optional: Database ID of the Global NPC's starting location.",
        current_hp="Optional: Current HP of the Global NPC.",
        mobile_group_id="Optional: Database ID of the Mobile Group this NPC belongs to.",
        route_json="Optional: JSON describing the NPC's route or movement behavior.",
        properties_json="Optional: JSON for additional properties (status, goals, etc.)."
    )
    async def global_npc_create(self, interaction: discord.Interaction,
                                name_i18n_json: str,
                                npc_template_id: Optional[int] = None,
                                current_location_id: Optional[int] = None,
                                current_hp: Optional[int] = None,
                                mobile_group_id: Optional[int] = None,
                                route_json: Optional[str] = None,
                                properties_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_global_npc import global_npc_crud
        from src.core.crud.crud_npc import npc_crud # To validate template_id
        from src.core.crud.crud_location import location_crud # To validate location_id
        from src.core.crud.crud_mobile_group import mobile_group_crud # To validate group_id
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any, Optional

        lang_code = str(interaction.locale)
        parsed_name_i18n: Dict[str, str]
        parsed_route: Optional[Dict[str, Any]] = None
        parsed_props: Optional[Dict[str, Any]] = None

        async with get_db_session() as session:
            if npc_template_id:
                template = await npc_crud.get_by_id_and_guild(session, id=npc_template_id, guild_id=interaction.guild_id)
                if not template:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_create:error_template_not_found",lang_code,"NPC Template ID {id} not found.")
                    await interaction.followup.send(error_msg.format(id=npc_template_id), ephemeral=True); return
            if current_location_id:
                loc = await location_crud.get_by_id_and_guild(session, id=current_location_id, guild_id=interaction.guild_id)
                if not loc:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_create:error_location_not_found",lang_code,"Location ID {id} not found.")
                    await interaction.followup.send(error_msg.format(id=current_location_id), ephemeral=True); return
            if mobile_group_id:
                group = await mobile_group_crud.get_by_id_and_guild(session, id=mobile_group_id, guild_id=interaction.guild_id)
                if not group:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_create:error_group_not_found",lang_code,"Mobile Group ID {id} not found.")
                    await interaction.followup.send(error_msg.format(id=mobile_group_id), ephemeral=True); return

            try:
                parsed_name_i18n = json.loads(name_i18n_json)
                if not isinstance(parsed_name_i18n, dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in parsed_name_i18n.items()):
                    raise ValueError("name_i18n_json must be a dict of str:str.")
                if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code):
                     raise ValueError("name_i18n_json must contain 'en' or current language key.")

                if route_json:
                    parsed_route = json.loads(route_json)
                    if not isinstance(parsed_route, dict): raise ValueError("route_json must be a dict.")
                if properties_json:
                    parsed_props = json.loads(properties_json)
                    if not isinstance(parsed_props, dict): raise ValueError("properties_json must be a dict.")
            except (json.JSONDecodeError, ValueError) as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_create:error_invalid_json",lang_code,"Invalid JSON: {details}")
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return

            gnpc_data_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id, "name_i18n": parsed_name_i18n,
                "npc_template_id": npc_template_id, "current_location_id": current_location_id,
                "current_hp": current_hp, "mobile_group_id": mobile_group_id,
                "route_json": parsed_route or {}, "properties_json": parsed_props or {}
            }

            try:
                async with session.begin():
                    created_gnpc = await global_npc_crud.create(session, obj_in=gnpc_data_create)
                    await session.flush(); await session.refresh(created_gnpc)
            except Exception as e:
                logger.error(f"Error creating Global NPC: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_create:error_generic_create",lang_code,"Error creating Global NPC: {error}")
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return

            if not created_gnpc:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_create:error_unknown_fail",lang_code,"Global NPC creation failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title = await get_localized_message_template(session,interaction.guild_id,"gnpc_create:success_title",lang_code,"Global NPC Created: {name} (ID: {id})")
            created_name = created_gnpc.name_i18n.get(lang_code, created_gnpc.name_i18n.get("en", ""))
            embed = discord.Embed(title=success_title.format(name=created_name, id=created_gnpc.id), color=discord.Color.green())
            embed.add_field(name="Location ID", value=str(created_gnpc.current_location_id) if created_gnpc.current_location_id else "N/A", inline=True)
            embed.add_field(name="HP", value=str(created_gnpc.current_hp) if created_gnpc.current_hp is not None else "N/A", inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @global_npc_group.command(name="update", description="Update a specific field for a Global NPC.")
    @app_commands.describe(
        global_npc_id="The database ID of the Global NPC to update.",
        field_to_update="Field to update (e.g., name_i18n_json, current_location_id, current_hp, mobile_group_id, route_json, properties_json).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable)."
    )
    async def global_npc_update(self, interaction: discord.Interaction, global_npc_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_global_npc import global_npc_crud
        from src.core.crud.crud_location import location_crud
        from src.core.crud.crud_mobile_group import mobile_group_crud
        # npc_template_id is not typically updated after creation, so not including npc_crud here.
        from src.core.database import get_db_session
        from src.core.crud_base_definitions import update_entity
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any, Optional

        allowed_fields = {
            "name_i18n_json": dict,
            "current_location_id": (int, type(None)),
            "current_hp": (int, type(None)),
            "mobile_group_id": (int, type(None)),
            "route_json": dict,
            "properties_json": dict,
            # npc_template_id is generally not updatable for an existing GlobalNPC instance.
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()

        db_field_name = field_to_update_lower
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")

        field_type_info = allowed_fields.get(db_field_name)

        if not field_type_info:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session,interaction.guild_id,"gnpc_update:error_field_not_allowed",lang_code,"Field '{f}' not allowed. Allowed: {l}")
            await interaction.followup.send(error_msg.format(f=field_to_update, l=', '.join(allowed_fields.keys())), ephemeral=True); return

        parsed_value: Any = None

        async with get_db_session() as session:
            try:
                if db_field_name in ["name_i18n", "route_json", "properties_json"]:
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict): raise ValueError(f"{db_field_name} must be a dict.")
                elif db_field_name in ["current_location_id", "current_hp", "mobile_group_id"]:
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = int(new_value)
                        # Validation for foreign keys
                        if db_field_name == "current_location_id" and parsed_value is not None:
                            if not await location_crud.get_by_id_and_guild(session, id=parsed_value, guild_id=interaction.guild_id):
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_loc_not_found",lang_code,"Location ID {id} not found.")
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                        elif db_field_name == "mobile_group_id" and parsed_value is not None:
                             if not await mobile_group_crud.get_by_id_and_guild(session, id=parsed_value, guild_id=interaction.guild_id):
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_group_not_found",lang_code,"Mobile Group ID {id} not found.")
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                else: # Should not be reached due to initial check
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_unknown_field",lang_code,"Unknown field for update.")
                    await interaction.followup.send(error_msg, ephemeral=True); return
            except ValueError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_invalid_value",lang_code,"Invalid value for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return
            except json.JSONDecodeError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_invalid_json",lang_code,"Invalid JSON for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            gnpc_to_update = await global_npc_crud.get_by_id_and_guild(session, id=global_npc_id, guild_id=interaction.guild_id)
            if not gnpc_to_update:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_not_found",lang_code,"Global NPC ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=global_npc_id), ephemeral=True); return

            update_data = {db_field_name: parsed_value}
            try:
                async with session.begin():
                    updated_gnpc = await update_entity(session, entity=gnpc_to_update, data=update_data)
                    await session.flush(); await session.refresh(updated_gnpc)
            except Exception as e:
                logger.error(f"Error updating Global NPC {global_npc_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_generic_update",lang_code,"Error updating Global NPC {id}: {err}")
                await interaction.followup.send(error_msg.format(id=global_npc_id, err=str(e)), ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:success",lang_code,"Global NPC ID {id} updated. Field '{f}' set to '{v}'.")
            new_val_display = str(parsed_value)
            if isinstance(parsed_value, dict): new_val_display = json.dumps(parsed_value)
            elif parsed_value is None: new_val_display = "None"
            await interaction.followup.send(success_msg.format(id=updated_gnpc.id, f=field_to_update, v=new_val_display), ephemeral=True)

    @global_npc_group.command(name="delete", description="Delete a Global NPC.")
    @app_commands.describe(global_npc_id="The database ID of the Global NPC to delete.")
    async def global_npc_delete(self, interaction: discord.Interaction, global_npc_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_global_npc import global_npc_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            gnpc_to_delete = await global_npc_crud.get_by_id_and_guild(session, id=global_npc_id, guild_id=interaction.guild_id)

            if not gnpc_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_delete:error_not_found",lang_code,"Global NPC ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=global_npc_id), ephemeral=True); return

            gnpc_name_for_msg = gnpc_to_delete.name_i18n.get(lang_code, gnpc_to_delete.name_i18n.get("en", f"Global NPC {global_npc_id}"))

            # Consider if Global NPC being part of a Mobile Group requires special handling.
            # If mobile_group_id is just a link and the group can exist without this NPC, simple delete is fine.
            # If deleting the NPC should also affect the group (e.g., remove from group's member list if stored there),
            # that logic would be more complex and might belong in a service layer or be handled by DB cascades if set up.
            # For now, direct deletion.

            try:
                async with session.begin():
                    deleted_gnpc = await global_npc_crud.remove(session, id=global_npc_id)

                if deleted_gnpc:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_delete:success",lang_code,"Global NPC '{name}' (ID: {id}) deleted.")
                    await interaction.followup.send(success_msg.format(name=gnpc_name_for_msg, id=global_npc_id), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_delete:error_unknown_delete_fail",lang_code,"Global NPC (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=global_npc_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Global NPC {global_npc_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_delete:error_generic_delete",lang_code,"Error deleting Global NPC '{name}' (ID: {id}): {err}")
                await interaction.followup.send(error_msg.format(name=gnpc_name_for_msg, id=global_npc_id, err=str(e)), ephemeral=True)

    # --- MobileGroup CRUD ---
    mobile_group_group = app_commands.Group(name="mobile_group", description="Master commands for managing Mobile Groups.", parent=master_admin)

    @mobile_group_group.command(name="view", description="View details of a specific Mobile Group.")
    @app_commands.describe(group_id="The database ID of the Mobile Group to view.")
    async def mobile_group_view(self, interaction: discord.Interaction, group_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_mobile_group import mobile_group_crud
        # Need GlobalNpc CRUD to list members
        from src.core.crud.crud_global_npc import global_npc_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            group = await mobile_group_crud.get_by_id_and_guild(session, id=group_id, guild_id=interaction.guild_id)

            if not group:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "mobile_group_view:not_found", lang_code,
                    "Mobile Group with ID {id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg.format(id=group_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "mobile_group_view:title", lang_code,
                "Mobile Group Details: {name} (ID: {id})"
            )

            group_name_display = group.name_i18n.get(lang_code, group.name_i18n.get("en", f"Group {group.id}"))
            embed_title = title_template.format(name=group_name_display, id=group.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.purple()) # New color

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"mobile_group_view:label_{key}", lang_code, default)

            async def format_json_field(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(group.guild_id), inline=True)
            embed.add_field(name=await get_label("current_location_id", "Current Location ID"), value=str(group.current_location_id) if group.current_location_id else "N/A", inline=True)

            name_i18n_str = await format_json_field(group.name_i18n, "mobile_group_view:value_na_json", "mobile_group_view:error_serialization_name")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```" + ("..." if len(name_i18n_str) > 1000 else ""), inline=False)

            route_str = await format_json_field(group.route_json, "mobile_group_view:value_na_json", "mobile_group_view:error_serialization_route")
            embed.add_field(name=await get_label("route_json", "Route JSON"), value=f"```json\n{route_str[:1000]}\n```" + ("..." if len(route_str) > 1000 else ""), inline=False)

            properties_str = await format_json_field(group.properties_json, "mobile_group_view:value_na_json", "mobile_group_view:error_serialization_properties")
            embed.add_field(name=await get_label("properties_json", "Properties JSON"), value=f"```json\n{properties_str[:1000]}\n```" + ("..." if len(properties_str) > 1000 else ""), inline=False)

            # List members (GlobalNpcs)
            members = await global_npc_crud.get_multi_by_guild_and_attribute(session, guild_id=interaction.guild_id, attribute_name="mobile_group_id", attribute_value=group_id, limit=25) # Limit for display
            members_label = await get_label("members", "Members (Global NPCs)")
            if members:
                member_info_list = []
                for member_gnpc in members:
                    member_name = member_gnpc.name_i18n.get(lang_code, member_gnpc.name_i18n.get("en", f"GNPC {member_gnpc.id}"))
                    member_info_list.append(f"ID: {member_gnpc.id} - {member_name}")
                embed.add_field(name=f"{members_label} ({len(member_info_list)})", value="\n".join(member_info_list)[:1020], inline=False)
            else:
                no_members_msg = await get_localized_message_template(session, interaction.guild_id, "mobile_group_view:no_members", lang_code, "No Global NPC members in this group.")
                embed.add_field(name=members_label, value=no_members_msg, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @mobile_group_group.command(name="list", description="List Mobile Groups in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of Mobile Groups per page.")
    async def mobile_group_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10

        from src.core.crud.crud_mobile_group import mobile_group_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import func, select

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            offset = (page - 1) * limit
            groups = await mobile_group_crud.get_multi_by_guild_id(session, guild_id=interaction.guild_id, skip=offset, limit=limit)

            total_groups_stmt = select(func.count(mobile_group_crud.model.id)).where(mobile_group_crud.model.guild_id == interaction.guild_id)
            total_groups_result = await session.execute(total_groups_stmt)
            total_mobile_groups = total_groups_result.scalar_one_or_none() or 0

            if not groups:
                no_groups_msg = await get_localized_message_template(
                    session, interaction.guild_id, "mobile_group_list:no_groups_found_page", lang_code,
                    "No Mobile Groups found for this guild (Page {page})."
                )
                await interaction.followup.send(no_groups_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "mobile_group_list:title", lang_code,
                "Mobile Group List (Page {page} of {total_pages})"
            )
            total_pages = ((total_mobile_groups - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_purple()) # Reused color

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "mobile_group_list:footer", lang_code,
                "Displaying {count} of {total} total Mobile Groups."
            )
            embed.set_footer(text=footer_template.format(count=len(groups), total=total_mobile_groups))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "mobile_group_list:group_field_name", lang_code,
                "ID: {id} | {name}"
            )
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "mobile_group_list:group_field_value", lang_code,
                "Location ID: {loc_id}" # Add member count later if efficient
            )

            for group_obj in groups:
                group_name_display = group_obj.name_i18n.get(lang_code, group_obj.name_i18n.get("en", f"Group {group_obj.id}"))
                embed.add_field(
                    name=field_name_template.format(id=group_obj.id, name=group_name_display),
                    value=field_value_template.format(
                        loc_id=str(group_obj.current_location_id) if group_obj.current_location_id else "N/A"
                    ),
                    inline=False
                )

            if len(embed.fields) == 0:
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "mobile_group_list:no_groups_to_display", lang_code,
                    "No Mobile Groups found to display on page {page}."
                )
                await interaction.followup.send(no_display_msg.format(page=page), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @mobile_group_group.command(name="create", description="Create a new Mobile Group.")
    @app_commands.describe(
        name_i18n_json="JSON for Mobile Group name (e.g., {\"en\": \"Merchant Caravan\"}).",
        current_location_id="Optional: Database ID of the group's starting location.",
        route_json="Optional: JSON describing the group's route or movement behavior.",
        properties_json="Optional: JSON for additional properties (status, goals, etc.)."
    )
    async def mobile_group_create(self, interaction: discord.Interaction,
                                  name_i18n_json: str,
                                  current_location_id: Optional[int] = None,
                                  route_json: Optional[str] = None,
                                  properties_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_mobile_group import mobile_group_crud
        from src.core.crud.crud_location import location_crud # To validate location_id
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any, Optional

        lang_code = str(interaction.locale)
        parsed_name_i18n: Dict[str, str]
        parsed_route: Optional[Dict[str, Any]] = None
        parsed_props: Optional[Dict[str, Any]] = None

        async with get_db_session() as session:
            if current_location_id:
                loc = await location_crud.get_by_id_and_guild(session, id=current_location_id, guild_id=interaction.guild_id)
                if not loc:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_create:error_location_not_found",lang_code,"Location ID {id} not found.")
                    await interaction.followup.send(error_msg.format(id=current_location_id), ephemeral=True); return

            try:
                parsed_name_i18n = json.loads(name_i18n_json)
                if not isinstance(parsed_name_i18n, dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in parsed_name_i18n.items()):
                    raise ValueError("name_i18n_json must be a dict of str:str.")
                if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code):
                     raise ValueError("name_i18n_json must contain 'en' or current language key.")

                if route_json:
                    parsed_route = json.loads(route_json)
                    if not isinstance(parsed_route, dict): raise ValueError("route_json must be a dict.")
                if properties_json:
                    parsed_props = json.loads(properties_json)
                    if not isinstance(parsed_props, dict): raise ValueError("properties_json must be a dict.")
            except (json.JSONDecodeError, ValueError) as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_create:error_invalid_json",lang_code,"Invalid JSON: {details}")
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return

            mg_data_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id, "name_i18n": parsed_name_i18n,
                "current_location_id": current_location_id,
                "route_json": parsed_route or {}, "properties_json": parsed_props or {}
            }

            try:
                async with session.begin():
                    created_mg = await mobile_group_crud.create(session, obj_in=mg_data_create)
                    await session.flush(); await session.refresh(created_mg)
            except Exception as e:
                logger.error(f"Error creating Mobile Group: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_create:error_generic_create",lang_code,"Error creating Mobile Group: {error}")
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return

            if not created_mg:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_create:error_unknown_fail",lang_code,"Mobile Group creation failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title = await get_localized_message_template(session,interaction.guild_id,"mg_create:success_title",lang_code,"Mobile Group Created: {name} (ID: {id})")
            created_name = created_mg.name_i18n.get(lang_code, created_mg.name_i18n.get("en", ""))
            embed = discord.Embed(title=success_title.format(name=created_name, id=created_mg.id), color=discord.Color.green())
            embed.add_field(name="Location ID", value=str(created_mg.current_location_id) if created_mg.current_location_id else "N/A", inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @mobile_group_group.command(name="update", description="Update a specific field for a Mobile Group.")
    @app_commands.describe(
        group_id="The database ID of the Mobile Group to update.",
        field_to_update="Field to update (e.g., name_i18n_json, current_location_id, route_json, properties_json).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable)."
    )
    async def mobile_group_update(self, interaction: discord.Interaction, group_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_mobile_group import mobile_group_crud
        from src.core.crud.crud_location import location_crud
        from src.core.database import get_db_session
        from src.core.crud_base_definitions import update_entity
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any, Optional

        allowed_fields = {
            "name_i18n_json": dict,
            "current_location_id": (int, type(None)),
            "route_json": dict,
            "properties_json": dict,
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()

        db_field_name = field_to_update_lower
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")

        field_type_info = allowed_fields.get(db_field_name)

        if not field_type_info:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session,interaction.guild_id,"mg_update:error_field_not_allowed",lang_code,"Field '{f}' not allowed. Allowed: {l}")
            await interaction.followup.send(error_msg.format(f=field_to_update, l=', '.join(allowed_fields.keys())), ephemeral=True); return

        parsed_value: Any = None

        async with get_db_session() as session:
            try:
                if db_field_name in ["name_i18n", "route_json", "properties_json"]:
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict): raise ValueError(f"{db_field_name} must be a dict.")
                elif db_field_name == "current_location_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = int(new_value)
                        if parsed_value is not None:
                            if not await location_crud.get_by_id_and_guild(session, id=parsed_value, guild_id=interaction.guild_id):
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_loc_not_found",lang_code,"Location ID {id} not found.")
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_unknown_field",lang_code,"Unknown field for update.")
                    await interaction.followup.send(error_msg, ephemeral=True); return
            except ValueError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_invalid_value",lang_code,"Invalid value for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return
            except json.JSONDecodeError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_invalid_json",lang_code,"Invalid JSON for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            group_to_update = await mobile_group_crud.get_by_id_and_guild(session, id=group_id, guild_id=interaction.guild_id)
            if not group_to_update:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_not_found",lang_code,"Mobile Group ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=group_id), ephemeral=True); return

            update_data = {db_field_name: parsed_value}
            try:
                async with session.begin():
                    updated_group = await update_entity(session, entity=group_to_update, data=update_data)
                    await session.flush(); await session.refresh(updated_group)
            except Exception as e:
                logger.error(f"Error updating Mobile Group {group_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_generic_update",lang_code,"Error updating Mobile Group {id}: {err}")
                await interaction.followup.send(error_msg.format(id=group_id, err=str(e)), ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:success",lang_code,"Mobile Group ID {id} updated. Field '{f}' set to '{v}'.")
            new_val_display = str(parsed_value)
            if isinstance(parsed_value, dict): new_val_display = json.dumps(parsed_value)
            elif parsed_value is None: new_val_display = "None"
            await interaction.followup.send(success_msg.format(id=updated_group.id, f=field_to_update, v=new_val_display), ephemeral=True)

    @mobile_group_group.command(name="delete", description="Delete a Mobile Group.")
    @app_commands.describe(group_id="The database ID of the Mobile Group to delete.")
    async def mobile_group_delete(self, interaction: discord.Interaction, group_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_mobile_group import mobile_group_crud
        from src.core.crud.crud_global_npc import global_npc_crud # To check for members
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import select

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            group_to_delete = await mobile_group_crud.get_by_id_and_guild(session, id=group_id, guild_id=interaction.guild_id)

            if not group_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_delete:error_not_found",lang_code,"Mobile Group ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=group_id), ephemeral=True); return

            group_name_for_msg = group_to_delete.name_i18n.get(lang_code, group_to_delete.name_i18n.get("en", f"Group {group_id}"))

            # Check for GlobalNPC members
            member_check_stmt = select(global_npc_crud.model.id).where(
                global_npc_crud.model.mobile_group_id == group_id,
                global_npc_crud.model.guild_id == interaction.guild_id
            ).limit(1)
            member_exists = (await session.execute(member_check_stmt)).scalar_one_or_none()

            if member_exists:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_delete:error_member_dependency",lang_code,"Cannot delete Mobile Group '{name}' (ID: {id}) as it has Global NPC members. Reassign them first.")
                await interaction.followup.send(error_msg.format(name=group_name_for_msg, id=group_id), ephemeral=True); return

            try:
                async with session.begin():
                    deleted_group = await mobile_group_crud.remove(session, id=group_id)

                if deleted_group:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"mg_delete:success",lang_code,"Mobile Group '{name}' (ID: {id}) deleted.")
                    await interaction.followup.send(success_msg.format(name=group_name_for_msg, id=group_id), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_delete:error_unknown_delete_fail",lang_code,"Mobile Group (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=group_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Mobile Group {group_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_delete:error_generic_delete",lang_code,"Error deleting Mobile Group '{name}' (ID: {id}): {err}")
                await interaction.followup.send(error_msg.format(name=group_name_for_msg, id=group_id, err=str(e)), ephemeral=True)

    # --- InventoryItem CRUD ---
    inventory_item_group = app_commands.Group(name="inventory_item", description="Master commands for managing Inventory Items.", parent=master_admin)

    @inventory_item_group.command(name="view", description="View details of a specific Inventory Item instance.")
    @app_commands.describe(inventory_item_id="The database ID of the InventoryItem to view.")
    async def inventory_item_view(self, interaction: discord.Interaction, inventory_item_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_inventory_item import inventory_item_crud
        from src.core.crud.crud_item import item_crud # To get item name
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            inv_item = await inventory_item_crud.get_by_id_and_guild(session, id=inventory_item_id, guild_id=interaction.guild_id)

            if not inv_item:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "inv_item_view:not_found", lang_code,
                    "InventoryItem with ID {id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg.format(id=inventory_item_id), ephemeral=True)
                return

            item_definition = await item_crud.get(session, id=inv_item.item_id) # No guild_id needed for item_crud.get if item_id is global PK
            item_name_display = "Unknown Item"
            if item_definition:
                item_name_display = item_definition.name_i18n.get(lang_code, item_definition.name_i18n.get("en", f"Item {item_definition.id}"))

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "inv_item_view:title", lang_code,
                "Inventory Item: {item_name} (Instance ID: {instance_id})"
            )
            embed_title = title_template.format(item_name=item_name_display, instance_id=inv_item.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.greyple())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"inv_item_view:label_{key}", lang_code, default)

            async def format_json_field(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(inv_item.guild_id), inline=True)
            embed.add_field(name=await get_label("item_id", "Base Item ID"), value=str(inv_item.item_id), inline=True)
            embed.add_field(name=await get_label("quantity", "Quantity"), value=str(inv_item.quantity), inline=True)

            owner_type_display = inv_item.owner_entity_type.value if inv_item.owner_entity_type else "N/A"
            embed.add_field(name=await get_label("owner_type", "Owner Type"), value=owner_type_display, inline=True)
            embed.add_field(name=await get_label("owner_id", "Owner ID"), value=str(inv_item.owner_entity_id), inline=True)
            embed.add_field(name=await get_label("equipped_status", "Equipped Status"), value=inv_item.equipped_status or "N/A", inline=True)

            props_str = await format_json_field(inv_item.instance_specific_properties_json, "inv_item_view:value_na_json", "inv_item_view:error_serialization_props")
            embed.add_field(name=await get_label("instance_properties", "Instance Properties JSON"), value=f"```json\n{props_str[:1000]}\n```" + ("..." if len(props_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @inventory_item_group.command(name="list", description="List Inventory Items with filters.")
    @app_commands.describe(
        owner_id="Optional: Filter by Owner ID.",
        owner_type="Optional: Filter by Owner Type (PLAYER or GENERATED_NPC).",
        item_id="Optional: Filter by base Item ID.",
        page="Page number.",
        limit="Items per page."
    )
    async def inventory_item_list(self, interaction: discord.Interaction,
                                  owner_id: Optional[int] = None,
                                  owner_type: Optional[str] = None,
                                  item_id: Optional[int] = None,
                                  page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10

        from src.core.crud.crud_inventory_item import inventory_item_crud
        from src.core.crud.crud_item import item_crud # For item names
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from src.models.enums import OwnerEntityType
        from sqlalchemy import select, func, and_

        lang_code = str(interaction.locale)
        owner_type_enum: Optional[OwnerEntityType] = None

        async with get_db_session() as session:
            if owner_type:
                try: owner_type_enum = OwnerEntityType[owner_type.upper()]
                except KeyError:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_list:error_invalid_owner_type",lang_code,"Invalid owner_type.")
                    await interaction.followup.send(error_msg, ephemeral=True); return

            if owner_id is not None and owner_type_enum is None:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_list:error_owner_id_no_type",lang_code,"If owner_id is provided, owner_type must also be provided.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            filters = [inventory_item_crud.model.guild_id == interaction.guild_id]
            if owner_id is not None and owner_type_enum:
                filters.append(inventory_item_crud.model.owner_entity_id == owner_id)
                filters.append(inventory_item_crud.model.owner_entity_type == owner_type_enum)
            if item_id is not None:
                filters.append(inventory_item_crud.model.item_id == item_id)

            offset = (page - 1) * limit
            query = select(inventory_item_crud.model).where(and_(*filters)).offset(offset).limit(limit).order_by(inventory_item_crud.model.id.desc())
            result = await session.execute(query)
            inv_items = result.scalars().all()

            count_query = select(func.count(inventory_item_crud.model.id)).where(and_(*filters))
            total_inv_items_res = await session.execute(count_query)
            total_inv_items = total_inv_items_res.scalar_one_or_none() or 0

            filter_parts = []
            if owner_id is not None and owner_type_enum: filter_parts.append(f"Owner: {owner_type_enum.name}({owner_id})")
            if item_id is not None: filter_parts.append(f"Item ID: {item_id}")
            filter_display = ", ".join(filter_parts) if filter_parts else "All"

            if not inv_items:
                no_items_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_list:no_items_found",lang_code,"No InventoryItems found for {filter} (Page {p}).")
                await interaction.followup.send(no_items_msg.format(filter=filter_display, p=page), ephemeral=True); return

            title_tmpl = await get_localized_message_template(session,interaction.guild_id,"inv_item_list:title",lang_code,"InventoryItem List ({filter} - Page {p} of {tp})")
            total_pages = ((total_inv_items - 1) // limit) + 1
            embed = discord.Embed(title=title_tmpl.format(filter=filter_display, p=page, tp=total_pages), color=discord.Color.light_grey())

            footer_tmpl = await get_localized_message_template(session,interaction.guild_id,"inv_item_list:footer",lang_code,"Displaying {c} of {t} total items.")
            embed.set_footer(text=footer_tmpl.format(c=len(inv_items), t=total_inv_items))

            # Pre-fetch all unique item definitions for names to optimize
            item_ids_to_fetch = list(set(ii.item_id for ii in inv_items))
            item_defs_dict = {}
            if item_ids_to_fetch:
                # Assuming item_crud.get_many_by_ids does not require guild_id as Item IDs are global
                item_definitions = await item_crud.get_many_by_ids(session, ids=item_ids_to_fetch)
                item_defs_dict = {item_def.id: item_def for item_def in item_definitions}

            name_tmpl = await get_localized_message_template(session,interaction.guild_id,"inv_item_list:item_name_field",lang_code,"ID: {id} | Item: {name} (Base ID: {base_id})")
            val_tmpl = await get_localized_message_template(session,interaction.guild_id,"inv_item_list:item_value_field",lang_code,"Owner: {o_type}({o_id}), Qty: {qty}, Equipped: {eq}")

            for ii in inv_items:
                base_item_def = item_defs_dict.get(ii.item_id)
                item_name = base_item_def.name_i18n.get(lang_code, base_item_def.name_i18n.get("en", "Unknown")) if base_item_def else "Unknown Base Item"

                embed.add_field(
                    name=name_tmpl.format(id=ii.id, name=item_name, base_id=ii.item_id),
                    value=val_tmpl.format(o_type=ii.owner_entity_type.name, o_id=ii.owner_entity_id, qty=ii.quantity, eq=ii.equipped_status or "N/A"),
                    inline=False
                )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @inventory_item_group.command(name="create", description="Add an item to an owner's inventory.")
    @app_commands.describe(
        owner_id="Database ID of the owner (Player or GeneratedNPC).",
        owner_type="Type of the owner (PLAYER or GENERATED_NPC).",
        item_id="Database ID of the base Item to add.",
        quantity="Quantity of the item to add (defaults to 1).",
        equipped_status="Optional: Equipped status (e.g., EQUIPPED_MAIN_HAND).",
        properties_json="Optional: JSON string for instance-specific properties."
    )
    async def inventory_item_create(self, interaction: discord.Interaction,
                                    owner_id: int,
                                    owner_type: str,
                                    item_id: int,
                                    quantity: int = 1,
                                    equipped_status: Optional[str] = None,
                                    properties_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_inventory_item import inventory_item_crud
        from src.core.crud.crud_item import item_crud # To validate item_id
        from src.core.crud.crud_player import player_crud # To validate owner
        from src.core.crud.crud_npc import npc_crud # To validate owner
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from src.models.enums import OwnerEntityType
        from typing import Dict, Any, Optional

        lang_code = str(interaction.locale)
        parsed_props: Optional[Dict[str, Any]] = None
        owner_type_enum: OwnerEntityType

        async with get_db_session() as session:
            try:
                owner_type_enum = OwnerEntityType[owner_type.upper()]
            except KeyError:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_create:error_invalid_owner_type",lang_code,"Invalid owner_type. Use PLAYER or GENERATED_NPC.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            # Validate owner
            owner_exists = False
            if owner_type_enum == OwnerEntityType.PLAYER:
                owner_exists = await player_crud.get_by_id_and_guild(session, id=owner_id, guild_id=interaction.guild_id) is not None
            elif owner_type_enum == OwnerEntityType.GENERATED_NPC:
                owner_exists = await npc_crud.get_by_id_and_guild(session, id=owner_id, guild_id=interaction.guild_id) is not None

            if not owner_exists:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_create:error_owner_not_found",lang_code,"Owner {type}({id}) not found.")
                await interaction.followup.send(error_msg.format(type=owner_type_enum.name, id=owner_id), ephemeral=True); return

            # Validate item_id (Item definition must exist in the same guild as the InventoryItem)
            base_item = await item_crud.get_by_id_and_guild(session, id=item_id, guild_id=interaction.guild_id)
            if not base_item:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_create:error_item_def_not_found",lang_code,"Base Item with ID {id} not found in this guild.")
                await interaction.followup.send(error_msg.format(id=item_id), ephemeral=True); return

            if quantity < 1:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_create:error_invalid_quantity",lang_code,"Quantity must be 1 or greater.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            try:
                if properties_json:
                    parsed_props = json.loads(properties_json)
                    if not isinstance(parsed_props, dict): raise ValueError("properties_json must be a dict.")
            except (json.JSONDecodeError, ValueError) as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_create:error_invalid_json_props",lang_code,"Invalid JSON for properties: {details}")
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return

            # The add_item_to_owner method handles stacking or creating new.
            # It uses commit internally, which is unusual for CRUD but noted in its docstring.
            # For a master command, this directness might be acceptable.
            # Let's ensure our call is within a transaction if add_item_to_owner is refactored later
            # to not commit itself. For now, follow its current design.
            # UPDATE: Refactored add_item_to_owner to not commit. Wrap in session.begin().

            created_inv_item: Optional[InventoryItem] = None
            try:
                async with session.begin(): # Ensure atomicity
                    created_inv_item = await inventory_item_crud.add_item_to_owner(
                        session=session, guild_id=interaction.guild_id,
                        owner_entity_id=owner_id, owner_entity_type=owner_type_enum,
                        item_id=item_id, quantity=quantity,
                        instance_specific_properties_json=parsed_props,
                        equipped_status=equipped_status
                    )
                    # add_item_to_owner now relies on outer commit from session.begin()
                    if created_inv_item: # Should always be true if no exception
                        await session.refresh(created_inv_item)
            except Exception as e: # Catch potential unique constraint violations or other DB errors
                logger.error(f"Error in add_item_to_owner or subsequent ops: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_create:error_generic_create",lang_code,"Error adding item to inventory: {error}")
                # Check for unique constraint violation specifically if possible (depends on DB driver and error details)
                # if "unique constraint" in str(e).lower():
                #    error_msg = "Item already exists with different properties (violates unique key). Update instead or use different properties."
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return

            if not created_inv_item:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_create:error_unknown_fail",lang_code,"Failed to add item to inventory.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_create:success",lang_code,"Item instance ID {id} (Qty: {qty}) added to {owner_type} {owner_id}.")
            await interaction.followup.send(success_msg.format(id=created_inv_item.id, qty=created_inv_item.quantity, owner_type=owner_type_enum.name, owner_id=owner_id), ephemeral=True)

    @inventory_item_group.command(name="update", description="Update an Inventory Item instance.")
    @app_commands.describe(
        inventory_item_id="Database ID of the InventoryItem to update.",
        field_to_update="Field to update (quantity, equipped_status, properties_json).",
        new_value="New value (integer for quantity; string for equipped_status; JSON string for properties)."
    )
    async def inventory_item_update(self, interaction: discord.Interaction, inventory_item_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_inventory_item import inventory_item_crud
        from src.core.database import get_db_session
        from src.core.crud_base_definitions import update_entity
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any, Optional

        allowed_fields = {
            "quantity": int,
            "equipped_status": (str, type(None)), # Can be set to None
            "properties_json": dict, # instance_specific_properties_json in model
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()

        db_field_name = field_to_update_lower
        if field_to_update_lower == "properties_json": # Model field name adjustment
            db_field_name = "instance_specific_properties_json"

        field_type_info = allowed_fields.get(field_to_update_lower) # Use command field name for lookup

        if not field_type_info:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session,interaction.guild_id,"inv_item_update:error_field_not_allowed",lang_code,"Field '{f}' not allowed. Allowed: {l}")
            await interaction.followup.send(error_msg.format(f=field_to_update, l=', '.join(allowed_fields.keys())), ephemeral=True); return

        parsed_value: Any = None
        async with get_db_session() as session:
            try:
                if db_field_name == "quantity":
                    parsed_value = int(new_value)
                    if parsed_value < 0: raise ValueError("Quantity cannot be negative. Use delete or set to 0 to remove.")
                elif db_field_name == "equipped_status":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = new_value # Assume string, no specific enum validation here for simplicity
                elif db_field_name == "instance_specific_properties_json":
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict): raise ValueError("properties_json must be a dict.")
                else: # Should not be reached
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_update:error_unknown_field",lang_code,"Unknown field for update.")
                    await interaction.followup.send(error_msg, ephemeral=True); return
            except ValueError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_update:error_invalid_value",lang_code,"Invalid value for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return
            except json.JSONDecodeError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_update:error_invalid_json",lang_code,"Invalid JSON for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            inv_item_to_update = await inventory_item_crud.get_by_id_and_guild(session, id=inventory_item_id, guild_id=interaction.guild_id)
            if not inv_item_to_update:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_update:error_not_found",lang_code,"InventoryItem ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=inventory_item_id), ephemeral=True); return

            if db_field_name == "quantity" and parsed_value == 0:
                # Special case: setting quantity to 0 means deleting the item instance
                try:
                    async with session.begin():
                        await inventory_item_crud.remove(session, id=inventory_item_id)
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_update:success_deleted_qty_zero",lang_code,"InventoryItem ID {id} quantity set to 0 and was deleted.")
                    await interaction.followup.send(success_msg.format(id=inventory_item_id), ephemeral=True)
                    return
                except Exception as e:
                    logger.error(f"Error deleting InventoryItem {inventory_item_id} due to quantity 0: {e}", exc_info=True)
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_update:error_delete_on_zero_qty",lang_code,"Error deleting item ID {id} when setting quantity to 0: {err}")
                    await interaction.followup.send(error_msg.format(id=inventory_item_id, err=str(e)), ephemeral=True); return


            update_data = {db_field_name: parsed_value}
            try:
                async with session.begin():
                    updated_inv_item = await update_entity(session, entity=inv_item_to_update, data=update_data)
                    await session.flush(); await session.refresh(updated_inv_item)
            except Exception as e:
                logger.error(f"Error updating InventoryItem {inventory_item_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_update:error_generic_update",lang_code,"Error updating InventoryItem {id}: {err}")
                await interaction.followup.send(error_msg.format(id=inventory_item_id, err=str(e)), ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_update:success",lang_code,"InventoryItem ID {id} updated. Field '{f}' set to '{v}'.")
            new_val_display = str(parsed_value)
            if isinstance(parsed_value, dict): new_val_display = json.dumps(parsed_value)
            elif parsed_value is None: new_val_display = "None"
            await interaction.followup.send(success_msg.format(id=updated_inv_item.id, f=field_to_update, v=new_val_display), ephemeral=True)

    @inventory_item_group.command(name="delete", description="Delete an Inventory Item instance.")
    @app_commands.describe(inventory_item_id="The database ID of the InventoryItem to delete.")
    async def inventory_item_delete(self, interaction: discord.Interaction, inventory_item_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_inventory_item import inventory_item_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            inv_item_to_delete = await inventory_item_crud.get_by_id_and_guild(session, id=inventory_item_id, guild_id=interaction.guild_id)

            if not inv_item_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_delete:error_not_found",lang_code,"InventoryItem ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=inventory_item_id), ephemeral=True); return

            item_id_for_msg = inv_item_to_delete.item_id
            owner_id_for_msg = inv_item_to_delete.owner_entity_id
            owner_type_for_msg = inv_item_to_delete.owner_entity_type.name

            try:
                async with session.begin():
                    deleted_inv_item = await inventory_item_crud.remove(session, id=inventory_item_id)

                if deleted_inv_item:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_delete:success",lang_code,"InventoryItem ID {id} (Item ID: {item_id}) for Owner {owner_type}({owner_id}) deleted.")
                    await interaction.followup.send(success_msg.format(id=inventory_item_id, item_id=item_id_for_msg, owner_type=owner_type_for_msg, owner_id=owner_id_for_msg ), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_delete:error_unknown_delete_fail",lang_code,"InventoryItem (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=inventory_item_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting InventoryItem {inventory_item_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_delete:error_generic_delete",lang_code,"Error deleting InventoryItem ID {id}: {err}")
                await interaction.followup.send(error_msg.format(id=inventory_item_id, err=str(e)), ephemeral=True)

    # --- Ability CRUD ---
    ability_group = app_commands.Group(name="ability", description="Master commands for managing Abilities.", parent=master_admin)

    @ability_group.command(name="view", description="View details of a specific Ability.")
    @app_commands.describe(ability_id="The database ID of the Ability to view.")
    async def ability_view(self, interaction: discord.Interaction, ability_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_ability import ability_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            # First, try to get by ID and current guild_id
            ability = await ability_crud.get_by_id_and_guild(session, id=ability_id, guild_id=interaction.guild_id)

            if not ability: # If not found in guild, try to find as a global ability (guild_id is None)
                ability = await ability_crud.get(session, id=ability_id) # Generic get, then check guild_id
                if ability and ability.guild_id is not None: # Found by ID, but belongs to another guild
                    ability = None

            if not ability:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ability_view:not_found", lang_code,
                    "Ability with ID {id} not found in this guild or globally."
                )
                await interaction.followup.send(not_found_msg.format(id=ability_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "ability_view:title", lang_code,
                "Ability Details: {name} (ID: {id})"
            )

            name_display = ability.name_i18n.get(lang_code, ability.name_i18n.get("en", f"Ability {ability.id}"))
            embed_title = title_template.format(name=name_display, id=ability.id)
            embed_color = discord.Color.blue() if ability.guild_id else discord.Color.light_grey() # Different color for global
            embed = discord.Embed(title=embed_title, color=embed_color)

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"ability_view:label_{key}", lang_code, default)

            async def format_json_field(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(ability.guild_id) if ability.guild_id else "Global", inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=ability.static_id or "N/A", inline=True)
            embed.add_field(name=await get_label("type", "Type"), value=ability.type or "N/A", inline=True)

            name_i18n_str = await format_json_field(ability.name_i18n, "ability_view:value_na_json", "ability_view:error_serialization_name")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```" + ("..." if len(name_i18n_str) > 1000 else ""), inline=False)

            desc_i18n_str = await format_json_field(ability.description_i18n, "ability_view:value_na_json", "ability_view:error_serialization_desc")
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```" + ("..." if len(desc_i18n_str) > 1000 else ""), inline=False)

            props_str = await format_json_field(ability.properties_json, "ability_view:value_na_json", "ability_view:error_serialization_props")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{props_str[:1000]}\n```" + ("..." if len(props_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @ability_group.command(name="list", description="List Abilities, optionally filtered by scope.")
    @app_commands.describe(
        scope="Scope to filter by ('guild', 'global', or 'all'). Defaults to 'all' (guild-specific + global).",
        page="Page number.",
        limit="Abilities per page."
    )
    @app_commands.choices(scope=[
        app_commands.Choice(name="All (Guild & Global)", value="all"),
        app_commands.Choice(name="Guild-Specific", value="guild"),
        app_commands.Choice(name="Global Only", value="global"),
    ])
    async def ability_list(self, interaction: discord.Interaction,
                           scope: Optional[app_commands.Choice[str]] = None,
                           page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10

        from src.core.crud.crud_ability import ability_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import func, select, and_, or_

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            filters = []
            scope_value = scope.value if scope else "all"

            if scope_value == "guild":
                filters.append(ability_crud.model.guild_id == interaction.guild_id)
            elif scope_value == "global":
                filters.append(ability_crud.model.guild_id.is_(None))
            else: # 'all' or default
                filters.append(or_(ability_crud.model.guild_id == interaction.guild_id, ability_crud.model.guild_id.is_(None)))

            offset = (page - 1) * limit
            query = select(ability_crud.model).where(and_(*filters)).offset(offset).limit(limit).order_by(ability_crud.model.id.desc())
            result = await session.execute(query)
            abilities = result.scalars().all()

            count_query = select(func.count(ability_crud.model.id)).where(and_(*filters))
            total_abilities_res = await session.execute(count_query)
            total_abilities = total_abilities_res.scalar_one_or_none() or 0

            scope_display_key = f"ability_list:scope_{scope_value}"
            scope_display_default = scope_value.capitalize()
            scope_display = await get_localized_message_template(session, interaction.guild_id, scope_display_key, lang_code, scope_display_default)

            if not abilities:
                no_abilities_msg = await get_localized_message_template(session,interaction.guild_id,"ability_list:no_abilities_found",lang_code,"No Abilities found for scope '{sc}' (Page {p}).")
                await interaction.followup.send(no_abilities_msg.format(sc=scope_display, p=page), ephemeral=True); return

            title_tmpl = await get_localized_message_template(session,interaction.guild_id,"ability_list:title",lang_code,"Ability List ({scope} - Page {p} of {tp})")
            total_pages = ((total_abilities - 1) // limit) + 1
            embed = discord.Embed(title=title_tmpl.format(scope=scope_display, p=page, tp=total_pages), color=discord.Color.teal())

            footer_tmpl = await get_localized_message_template(session,interaction.guild_id,"ability_list:footer",lang_code,"Displaying {c} of {t} total Abilities.")
            embed.set_footer(text=footer_tmpl.format(c=len(abilities), t=total_abilities))

            name_tmpl = await get_localized_message_template(session,interaction.guild_id,"ability_list:ability_name_field",lang_code,"ID: {id} | {name} (Static: {sid})")
            val_tmpl = await get_localized_message_template(session,interaction.guild_id,"ability_list:ability_value_field",lang_code,"Type: {type}, Scope: {scope_val}")

            for ab in abilities:
                ab_name = ab.name_i18n.get(lang_code, ab.name_i18n.get("en", "N/A"))
                scope_val_disp = "Global" if ab.guild_id is None else f"Guild ({ab.guild_id})"
                embed.add_field(
                    name=name_tmpl.format(id=ab.id, name=ab_name, sid=ab.static_id or "N/A"),
                    value=val_tmpl.format(type=ab.type or "N/A", scope_val=scope_val_disp),
                    inline=False
                )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @ability_group.command(name="create", description="Create a new Ability.")
    @app_commands.describe(
        static_id="Static ID for this Ability (must be unique for its scope: global or guild).",
        name_i18n_json="JSON for Ability name (e.g., {\"en\": \"Fireball\", \"ru\": \"Огненный шар\"}).",
        description_i18n_json="Optional: JSON for Ability description.",
        ability_type="Optional: Type of the ability (e.g., SPELL, SKILL, COMBAT_MANEUVER).",
        properties_json="Optional: JSON for additional properties (effects, costs, requirements).",
        is_global="Set to True if this is a global ability (not tied to this guild). Defaults to False (guild-specific)."
    )
    async def ability_create(self, interaction: discord.Interaction,
                             static_id: str,
                             name_i18n_json: str,
                             description_i18n_json: Optional[str] = None,
                             ability_type: Optional[str] = None,
                             properties_json: Optional[str] = None,
                             is_global: bool = False):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_ability import ability_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any, Optional

        lang_code = str(interaction.locale)
        parsed_name_i18n: Dict[str, str]
        parsed_desc_i18n: Optional[Dict[str, str]] = None
        parsed_props: Optional[Dict[str, Any]] = None

        target_guild_id: Optional[int] = interaction.guild_id if not is_global else None

        async with get_db_session() as session:
            # Validate static_id uniqueness within its scope
            existing_ab_static = await ability_crud.get_by_static_id(session, static_id=static_id, guild_id=target_guild_id)
            if existing_ab_static:
                scope_str = "global" if target_guild_id is None else f"guild {target_guild_id}"
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_create:error_static_id_exists",lang_code,"Ability static_id '{id}' already exists in scope {sc}.")
                await interaction.followup.send(error_msg.format(id=static_id, sc=scope_str), ephemeral=True); return

            try:
                parsed_name_i18n = json.loads(name_i18n_json)
                if not isinstance(parsed_name_i18n, dict) or not all(isinstance(k,str)and isinstance(v,str) for k,v in parsed_name_i18n.items()):
                    raise ValueError("name_i18n_json must be a dict of str:str.")
                if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code):
                     raise ValueError("name_i18n_json must contain 'en' or current language key.")

                if description_i18n_json:
                    parsed_desc_i18n = json.loads(description_i18n_json)
                    if not isinstance(parsed_desc_i18n, dict) or not all(isinstance(k,str)and isinstance(v,str) for k,v in parsed_desc_i18n.items()):
                        raise ValueError("description_i18n_json must be a dict of str:str.")
                if properties_json:
                    parsed_props = json.loads(properties_json)
                    if not isinstance(parsed_props, dict): raise ValueError("properties_json must be a dict.")
            except (json.JSONDecodeError, ValueError) as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_create:error_invalid_json",lang_code,"Invalid JSON: {details}")
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return

            ab_data_create: Dict[str, Any] = {
                "guild_id": target_guild_id, "static_id": static_id, "name_i18n": parsed_name_i18n,
                "description_i18n": parsed_desc_i18n or {}, "type": ability_type,
                "properties_json": parsed_props or {}
            }

            try:
                async with session.begin():
                    # CRUDBase.create will handle guild_id correctly (can be None)
                    created_ab = await ability_crud.create(session, obj_in=ab_data_create)
                    await session.flush(); await session.refresh(created_ab)
            except Exception as e:
                logger.error(f"Error creating Ability: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_create:error_generic_create",lang_code,"Error creating Ability: {error}")
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return

            if not created_ab:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_create:error_unknown_fail",lang_code,"Ability creation failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title = await get_localized_message_template(session,interaction.guild_id,"ability_create:success_title",lang_code,"Ability Created: {name} (ID: {id})")
            created_name = created_ab.name_i18n.get(lang_code, created_ab.name_i18n.get("en", ""))
            scope_disp = "Global" if created_ab.guild_id is None else f"Guild {created_ab.guild_id}"
            embed = discord.Embed(title=success_title.format(name=created_name, id=created_ab.id), color=discord.Color.green())
            embed.add_field(name="Static ID", value=created_ab.static_id, inline=True)
            embed.add_field(name="Type", value=created_ab.type or "N/A", inline=True)
            embed.add_field(name="Scope", value=scope_disp, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @ability_group.command(name="update", description="Update a specific field for an Ability.")
    @app_commands.describe(
        ability_id="The database ID of the Ability to update.",
        field_to_update="Field to update (e.g., static_id, name_i18n_json, type, properties_json). Guild ID cannot be changed.",
        new_value="New value for the field (use JSON for complex types)."
    )
    async def ability_update(self, interaction: discord.Interaction, ability_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_ability import ability_crud
        from src.core.database import get_db_session
        from src.core.crud_base_definitions import update_entity
        from src.core.localization_utils import get_localized_message_template
        from typing import Dict, Any, Optional

        allowed_fields = {
            "static_id": str,
            "name_i18n": dict, # Note: command will take name_i18n_json
            "description_i18n": dict, # Note: command will take description_i18n_json
            "type": (str, type(None)),
            "properties_json": dict,
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()

        # Determine the actual database field name
        db_field_name = field_to_update_lower
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json", "") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json", "")

        # Check if the db_field_name (potentially stripped of _json) is in allowed_fields
        field_type_info = allowed_fields.get(db_field_name)

        if not field_type_info:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session,interaction.guild_id,"ability_update:error_field_not_allowed",lang_code,"Field '{f}' not allowed. Allowed: {l}")
            # Show user-friendly field names in error message
            user_friendly_allowed_fields = [f + "_json" if isinstance(allowed_fields[f], dict) else f for f in allowed_fields]
            await interaction.followup.send(error_msg.format(f=field_to_update, l=', '.join(user_friendly_allowed_fields)), ephemeral=True); return

        parsed_value: Any = None

        async with get_db_session() as session:
            ability_to_update = await ability_crud.get_by_id_and_guild(session, id=ability_id, guild_id=interaction.guild_id)
            original_guild_id_of_ability = interaction.guild_id # Assume guild-specific by default
            if not ability_to_update:
                temp_ability = await ability_crud.get(session, id=ability_id)
                if temp_ability and temp_ability.guild_id is None:
                    ability_to_update = temp_ability
                    original_guild_id_of_ability = None # It's a global ability
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_update:error_not_found",lang_code,"Ability ID {id} not found.")
                    await interaction.followup.send(error_msg.format(id=ability_id), ephemeral=True); return

            try:
                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: raise ValueError("static_id cannot be empty.")
                    existing_ab = await ability_crud.get_by_static_id(session, static_id=parsed_value, guild_id=original_guild_id_of_ability)
                    if existing_ab and existing_ab.id != ability_id:
                        scope_str = "global" if original_guild_id_of_ability is None else f"guild {original_guild_id_of_ability}"
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_update:error_static_id_exists",lang_code,"Static ID '{id}' already in use within its scope ({sc}).")
                        await interaction.followup.send(error_msg.format(id=parsed_value, sc=scope_str), ephemeral=True); return
                elif db_field_name in ["name_i18n", "description_i18n", "properties_json"]:
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict): raise ValueError(f"{db_field_name} must be a dict.")
                elif db_field_name == "type":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = new_value
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_update:error_unknown_field_internal",lang_code,"Internal error: field definition mismatch.")
                    await interaction.followup.send(error_msg, ephemeral=True); return
            except ValueError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_update:error_invalid_value",lang_code,"Invalid value for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return
            except json.JSONDecodeError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_update:error_invalid_json",lang_code,"Invalid JSON for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            update_data = {db_field_name: parsed_value}
            try:
                async with session.begin():
                    updated_ab = await update_entity(session, entity=ability_to_update, data=update_data)
                    await session.flush(); await session.refresh(updated_ab)
            except Exception as e:
                logger.error(f"Error updating Ability {ability_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_update:error_generic_update",lang_code,"Error updating Ability {id}: {err}")
                await interaction.followup.send(error_msg.format(id=ability_id, err=str(e)), ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"ability_update:success",lang_code,"Ability ID {id} updated. Field '{f}' set to '{v}'.")
            new_val_display = str(parsed_value)
            if isinstance(parsed_value, dict): new_val_display = json.dumps(parsed_value)
            elif parsed_value is None: new_val_display = "None"
            await interaction.followup.send(success_msg.format(id=updated_ab.id, f=field_to_update, v=new_val_display), ephemeral=True)

    @ability_group.command(name="delete", description="Delete an Ability.")
    @app_commands.describe(ability_id="The database ID of the Ability to delete.")
    async def ability_delete(self, interaction: discord.Interaction, ability_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_ability import ability_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            # Try to find guild-specific first, then global
            ability_to_delete = await ability_crud.get_by_id_and_guild(session, id=ability_id, guild_id=interaction.guild_id)
            if not ability_to_delete:
                temp_ab = await ability_crud.get(session, id=ability_id)
                if temp_ab and temp_ab.guild_id is None: # It's a global one we might be allowed to delete
                    ability_to_delete = temp_ab
                # If it belongs to another guild, we shouldn't find it/delete it.

            if not ability_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_delete:error_not_found",lang_code,"Ability ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=ability_id), ephemeral=True); return

            ab_name_for_msg = ability_to_delete.name_i18n.get(lang_code, ability_to_delete.name_i18n.get("en", f"Ability {ability_id}"))
            scope_for_msg = "Global" if ability_to_delete.guild_id is None else f"Guild {ability_to_delete.guild_id}"

            # TODO: Add checks for dependencies (e.g., if ability is used in RuleConfig, by characters, etc.)
            # For now, direct delete.

            try:
                async with session.begin():
                    deleted_ab = await ability_crud.remove(session, id=ability_id) # remove by PK

                if deleted_ab:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"ability_delete:success",lang_code,"Ability '{name}' (ID: {id}, Scope: {scope}) deleted.")
                    await interaction.followup.send(success_msg.format(name=ab_name_for_msg, id=ability_id, scope=scope_for_msg), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_delete:error_unknown_delete_fail",lang_code,"Ability (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=ability_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Ability {ability_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"ability_delete:error_generic_delete",lang_code,"Error deleting Ability '{name}' (ID: {id}): {err}")
                await interaction.followup.send(error_msg.format(name=ab_name_for_msg, id=ability_id, err=str(e)), ephemeral=True)

    # --- StatusEffect Definition CRUD ---
    status_effect_def_group = app_commands.Group(name="status_effect_definition", description="Master commands for managing Status Effect definitions.", parent=master_admin)

    @status_effect_def_group.command(name="view", description="View details of a specific Status Effect definition.")
    @app_commands.describe(status_effect_id="The database ID of the StatusEffect definition to view.")
    async def status_effect_def_view(self, interaction: discord.Interaction, status_effect_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_status_effect import status_effect_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            # Try guild-specific first, then global
            se_def = await status_effect_crud.get_by_id_and_guild(session, id=status_effect_id, guild_id=interaction.guild_id)
            if not se_def:
                temp_se = await status_effect_crud.get(session, id=status_effect_id)
                if temp_se and temp_se.guild_id is None:
                    se_def = temp_se

            if not se_def:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "se_def_view:not_found", lang_code,
                    "StatusEffect definition with ID {id} not found."
                )
                await interaction.followup.send(not_found_msg.format(id=status_effect_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "se_def_view:title", lang_code,
                "StatusEffect Definition: {name} (ID: {id})"
            )

            name_display = se_def.name_i18n.get(lang_code, se_def.name_i18n.get("en", f"StatusEffect {se_def.id}"))
            embed_title = title_template.format(name=name_display, id=se_def.id)
            embed_color = discord.Color.dark_green() if se_def.guild_id else discord.Color.dark_grey()
            embed = discord.Embed(title=embed_title, color=embed_color)

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"se_def_view:label_{key}", lang_code, default)

            async def format_json_field(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(se_def.guild_id) if se_def.guild_id else "Global", inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=se_def.static_id or "N/A", inline=True)
            embed.add_field(name=await get_label("category", "Category"), value=se_def.category.value if se_def.category else "N/A", inline=True)

            name_i18n_str = await format_json_field(se_def.name_i18n, "se_def_view:value_na_json", "se_def_view:error_serialization_name")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```" + ("..." if len(name_i18n_str) > 1000 else ""), inline=False)

            desc_i18n_str = await format_json_field(se_def.description_i18n, "se_def_view:value_na_json", "se_def_view:error_serialization_desc")
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```" + ("..." if len(desc_i18n_str) > 1000 else ""), inline=False)

            props_str = await format_json_field(se_def.properties_json, "se_def_view:value_na_json", "se_def_view:error_serialization_props")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{props_str[:1000]}\n```" + ("..." if len(props_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @status_effect_def_group.command(name="list", description="List Status Effect definitions.")
    @app_commands.describe(
        scope="Scope to filter by ('guild', 'global', or 'all'). Defaults to 'all'.",
        page="Page number.",
        limit="Definitions per page."
    )
    @app_commands.choices(scope=[
        app_commands.Choice(name="All (Guild & Global)", value="all"),
        app_commands.Choice(name="Guild-Specific", value="guild"),
        app_commands.Choice(name="Global Only", value="global"),
    ])
    async def status_effect_def_list(self, interaction: discord.Interaction,
                                     scope: Optional[app_commands.Choice[str]] = None,
                                     page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10

        from src.core.crud.crud_status_effect import status_effect_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import func, select, and_, or_

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            filters = []
            scope_value = scope.value if scope else "all"

            if scope_value == "guild":
                filters.append(status_effect_crud.model.guild_id == interaction.guild_id)
            elif scope_value == "global":
                filters.append(status_effect_crud.model.guild_id.is_(None))
            else: # 'all' or default
                filters.append(or_(status_effect_crud.model.guild_id == interaction.guild_id, status_effect_crud.model.guild_id.is_(None)))

            offset = (page - 1) * limit
            query = select(status_effect_crud.model).where(and_(*filters)).offset(offset).limit(limit).order_by(status_effect_crud.model.id.desc())
            result = await session.execute(query)
            se_defs = result.scalars().all()

            count_query = select(func.count(status_effect_crud.model.id)).where(and_(*filters))
            total_defs_res = await session.execute(count_query)
            total_definitions = total_defs_res.scalar_one_or_none() or 0

            scope_display_key = f"se_def_list:scope_{scope_value}"
            scope_display_default = scope_value.capitalize()
            scope_display = await get_localized_message_template(session, interaction.guild_id, scope_display_key, lang_code, scope_display_default)

            if not se_defs:
                no_defs_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_list:no_defs_found",lang_code,"No StatusEffect definitions found for scope '{sc}' (Page {p}).")
                await interaction.followup.send(no_defs_msg.format(sc=scope_display, p=page), ephemeral=True); return

            title_tmpl = await get_localized_message_template(session,interaction.guild_id,"se_def_list:title",lang_code,"StatusEffect Definition List ({scope} - Page {p} of {tp})")
            total_pages = ((total_definitions - 1) // limit) + 1
            embed = discord.Embed(title=title_tmpl.format(scope=scope_display, p=page, tp=total_pages), color=discord.Color.dark_teal())

            footer_tmpl = await get_localized_message_template(session,interaction.guild_id,"se_def_list:footer",lang_code,"Displaying {c} of {t} total definitions.")
            embed.set_footer(text=footer_tmpl.format(c=len(se_defs), t=total_definitions))

            name_tmpl = await get_localized_message_template(session,interaction.guild_id,"se_def_list:def_name_field",lang_code,"ID: {id} | {name} (Static: {sid})")
            val_tmpl = await get_localized_message_template(session,interaction.guild_id,"se_def_list:def_value_field",lang_code,"Category: {cat}, Scope: {scope_val}")

            for se_def in se_defs:
                se_name = se_def.name_i18n.get(lang_code, se_def.name_i18n.get("en", "N/A"))
                scope_val_disp = "Global" if se_def.guild_id is None else f"Guild ({se_def.guild_id})"
                embed.add_field(
                    name=name_tmpl.format(id=se_def.id, name=se_name, sid=se_def.static_id or "N/A"),
                    value=val_tmpl.format(cat=se_def.category.value if se_def.category else "N/A", scope_val=scope_val_disp),
                    inline=False
                )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @status_effect_def_group.command(name="create", description="Create a new Status Effect definition.")
    @app_commands.describe(
        static_id="Static ID (unique for its scope: global or guild).",
        name_i18n_json="JSON for name (e.g., {\"en\": \"Poisoned\", \"ru\": \"Отравлен\"}).",
        category="Category (BUFF, DEBUFF, NEUTRAL).",
        description_i18n_json="Optional: JSON for description.",
        properties_json="Optional: JSON for properties (effects, duration rules, etc.).",
        is_global="Set to True if this is a global definition. Defaults to False (guild-specific)."
    )
    @app_commands.choices(category=[
        app_commands.Choice(name="Buff", value="BUFF"),
        app_commands.Choice(name="Debuff", value="DEBUFF"),
        app_commands.Choice(name="Neutral", value="NEUTRAL"),
    ])
    async def status_effect_def_create(self, interaction: discord.Interaction,
                                       static_id: str,
                                       name_i18n_json: str,
                                       category: app_commands.Choice[str],
                                       description_i18n_json: Optional[str] = None,
                                       properties_json: Optional[str] = None,
                                       is_global: bool = False):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_status_effect import status_effect_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from src.models.enums import StatusEffectCategory
        from typing import Dict, Any, Optional

        lang_code = str(interaction.locale)
        parsed_name_i18n: Dict[str, str]
        parsed_desc_i18n: Optional[Dict[str, str]] = None
        parsed_props: Optional[Dict[str, Any]] = None

        target_guild_id: Optional[int] = interaction.guild_id if not is_global else None

        async with get_db_session() as session:
            existing_se_static = await status_effect_crud.get_by_static_id(session, static_id=static_id, guild_id=target_guild_id)
            if existing_se_static:
                scope_str = "global" if target_guild_id is None else f"guild {target_guild_id}"
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_create:error_static_id_exists",lang_code,"StatusEffect static_id '{id}' already exists in scope {sc}.")
                await interaction.followup.send(error_msg.format(id=static_id, sc=scope_str), ephemeral=True); return

            try:
                category_enum = StatusEffectCategory[category.value] # Convert choice value to enum

                parsed_name_i18n = json.loads(name_i18n_json)
                if not isinstance(parsed_name_i18n, dict) or not all(isinstance(k,str)and isinstance(v,str) for k,v in parsed_name_i18n.items()):
                    raise ValueError("name_i18n_json must be a dict of str:str.")
                if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code):
                     raise ValueError("name_i18n_json must contain 'en' or current language key.")

                if description_i18n_json:
                    parsed_desc_i18n = json.loads(description_i18n_json)
                    if not isinstance(parsed_desc_i18n, dict) or not all(isinstance(k,str)and isinstance(v,str) for k,v in parsed_desc_i18n.items()):
                        raise ValueError("description_i18n_json must be a dict of str:str.")
                if properties_json:
                    parsed_props = json.loads(properties_json)
                    if not isinstance(parsed_props, dict): raise ValueError("properties_json must be a dict.")
            except (json.JSONDecodeError, ValueError, KeyError) as e: # Added KeyError for category
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_create:error_invalid_input",lang_code,"Invalid input: {details}")
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return

            se_data_create: Dict[str, Any] = {
                "guild_id": target_guild_id, "static_id": static_id, "name_i18n": parsed_name_i18n,
                "description_i18n": parsed_desc_i18n or {}, "category": category_enum,
                "properties_json": parsed_props or {}
            }

            try:
                async with session.begin():
                    created_se = await status_effect_crud.create(session, obj_in=se_data_create)
                    await session.flush(); await session.refresh(created_se)
            except Exception as e:
                logger.error(f"Error creating StatusEffect definition: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_create:error_generic_create",lang_code,"Error creating definition: {error}")
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return

            if not created_se:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_create:error_unknown_fail",lang_code,"Definition creation failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title = await get_localized_message_template(session,interaction.guild_id,"se_def_create:success_title",lang_code,"StatusEffect Definition Created: {name} (ID: {id})")
            created_name = created_se.name_i18n.get(lang_code, created_se.name_i18n.get("en", ""))
            scope_disp = "Global" if created_se.guild_id is None else f"Guild {created_se.guild_id}"
            embed = discord.Embed(title=success_title.format(name=created_name, id=created_se.id), color=discord.Color.green())
            embed.add_field(name="Static ID", value=created_se.static_id, inline=True)
            embed.add_field(name="Category", value=created_se.category.value, inline=True)
            embed.add_field(name="Scope", value=scope_disp, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @status_effect_def_group.command(name="update", description="Update a Status Effect definition.")
    @app_commands.describe(
        status_effect_id="ID of the StatusEffect definition to update.",
        field_to_update="Field to update (e.g., static_id, name_i18n_json, category, properties_json).",
        new_value="New value for the field."
    )
    @app_commands.choices(field_to_update=[ # Provide choices for common fields for better UX
        app_commands.Choice(name="Static ID", value="static_id"),
        app_commands.Choice(name="Name (i18n JSON)", value="name_i18n_json"),
        app_commands.Choice(name="Description (i18n JSON)", value="description_i18n_json"),
        app_commands.Choice(name="Category (BUFF/DEBUFF/NEUTRAL)", value="category"),
        app_commands.Choice(name="Properties (JSON)", value="properties_json"),
    ])
    async def status_effect_def_update(self, interaction: discord.Interaction,
                                       status_effect_id: int,
                                       field_to_update: app_commands.Choice[str],
                                       new_value: str):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_status_effect import status_effect_crud
        from src.core.database import get_db_session
        from src.core.crud_base_definitions import update_entity
        from src.core.localization_utils import get_localized_message_template
        from src.models.enums import StatusEffectCategory
        from typing import Dict, Any, Optional

        # Map command choice value to actual DB field names and types
        allowed_fields_map = {
            "static_id": {"db_field": "static_id", "type": str},
            "name_i18n_json": {"db_field": "name_i18n", "type": dict},
            "description_i18n_json": {"db_field": "description_i18n", "type": dict},
            "category": {"db_field": "category", "type": StatusEffectCategory},
            "properties_json": {"db_field": "properties_json", "type": dict},
        }

        lang_code = str(interaction.locale)
        command_field_name = field_to_update.value # Get string value from Choice

        if command_field_name not in allowed_fields_map:
            async with get_db_session() as temp_session: # Should not happen due to choices
                error_msg = await get_localized_message_template(temp_session,interaction.guild_id,"se_def_update:error_field_not_allowed_internal",lang_code,"Internal error: Invalid field choice.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        db_field_name = allowed_fields_map[command_field_name]["db_field"]
        expected_type = allowed_fields_map[command_field_name]["type"]
        parsed_value: Any = None

        async with get_db_session() as session:
            se_def_to_update = await status_effect_crud.get_by_id_and_guild(session, id=status_effect_id, guild_id=interaction.guild_id)
            original_guild_id = interaction.guild_id
            if not se_def_to_update:
                temp_se = await status_effect_crud.get(session, id=status_effect_id)
                if temp_se and temp_se.guild_id is None:
                    se_def_to_update = temp_se
                    original_guild_id = None
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:error_not_found",lang_code,"StatusEffect def ID {id} not found.")
                    await interaction.followup.send(error_msg.format(id=status_effect_id), ephemeral=True); return

            try:
                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: raise ValueError("static_id cannot be empty.")
                    existing_se = await status_effect_crud.get_by_static_id(session, static_id=parsed_value, guild_id=original_guild_id)
                    if existing_se and existing_se.id != status_effect_id:
                        scope_str = "global" if original_guild_id is None else f"guild {original_guild_id}"
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:error_static_id_exists",lang_code,"Static ID '{id}' already in use for scope {sc}.")
                        await interaction.followup.send(error_msg.format(id=parsed_value, sc=scope_str), ephemeral=True); return
                elif expected_type == dict: # Handles all _json fields
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict): raise ValueError(f"{command_field_name} must be a dict.")
                elif expected_type == StatusEffectCategory:
                    try: parsed_value = StatusEffectCategory[new_value.upper()]
                    except KeyError: raise ValueError(f"Invalid category. Use {', '.join([c.name for c in StatusEffectCategory])}")
                else: # Should be str (for type, though not explicitly in map this way)
                    parsed_value = new_value
            except ValueError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:error_invalid_value",lang_code,"Invalid value for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=command_field_name, details=str(e)), ephemeral=True); return
            except json.JSONDecodeError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:error_invalid_json",lang_code,"Invalid JSON for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=command_field_name, details=str(e)), ephemeral=True); return

            update_data = {db_field_name: parsed_value}
            try:
                async with session.begin():
                    updated_se = await update_entity(session, entity=se_def_to_update, data=update_data)
                    await session.flush(); await session.refresh(updated_se)
            except Exception as e:
                logger.error(f"Error updating StatusEffect def {status_effect_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:error_generic_update",lang_code,"Error updating def {id}: {err}")
                await interaction.followup.send(error_msg.format(id=status_effect_id, err=str(e)), ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:success",lang_code,"StatusEffect def ID {id} updated. Field '{f}' set to '{v}'.")
            new_val_display = str(parsed_value.name if isinstance(parsed_value, StatusEffectCategory) else parsed_value)
            if isinstance(parsed_value, dict): new_val_display = json.dumps(parsed_value)
            await interaction.followup.send(success_msg.format(id=updated_se.id, f=command_field_name, v=new_val_display), ephemeral=True)

    @status_effect_def_group.command(name="delete", description="Delete a Status Effect definition.")
    @app_commands.describe(status_effect_id="ID of the StatusEffect definition to delete.")
    async def status_effect_def_delete(self, interaction: discord.Interaction, status_effect_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_status_effect import status_effect_crud, active_status_effect_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from sqlalchemy import select

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            se_def_to_delete = await status_effect_crud.get_by_id_and_guild(session, id=status_effect_id, guild_id=interaction.guild_id)
            is_global_to_delete = False
            if not se_def_to_delete:
                temp_se = await status_effect_crud.get(session, id=status_effect_id)
                if temp_se and temp_se.guild_id is None:
                    se_def_to_delete = temp_se
                    is_global_to_delete = True

            if not se_def_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_delete:error_not_found",lang_code,"StatusEffect def ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=status_effect_id), ephemeral=True); return

            se_name_for_msg = se_def_to_delete.name_i18n.get(lang_code, se_def_to_delete.name_i18n.get("en", f"SE Def {status_effect_id}"))
            scope_for_msg = "Global" if is_global_to_delete else f"Guild {interaction.guild_id}"

            active_check_filters = [active_status_effect_crud.model.status_effect_id == status_effect_id]
            if not is_global_to_delete:
                 active_check_filters.append(active_status_effect_crud.model.guild_id == interaction.guild_id)

            active_dependency_stmt = select(active_status_effect_crud.model.id).where(*active_check_filters).limit(1)
            active_dependency_exists = (await session.execute(active_dependency_stmt)).scalar_one_or_none()

            if active_dependency_exists:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_delete:error_active_dependency",lang_code,"Cannot delete StatusEffect def '{name}' (ID: {id}, Scope: {scope}) as it is currently active. Remove active instances first.")
                await interaction.followup.send(error_msg.format(name=se_name_for_msg, id=status_effect_id, scope=scope_for_msg), ephemeral=True); return

            try:
                async with session.begin():
                    deleted_se_def = await status_effect_crud.remove(session, id=status_effect_id)

                if deleted_se_def:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_delete:success",lang_code,"StatusEffect def '{name}' (ID: {id}, Scope: {scope}) deleted.")
                    await interaction.followup.send(success_msg.format(name=se_name_for_msg, id=status_effect_id, scope=scope_for_msg), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_delete:error_unknown_delete_fail",lang_code,"StatusEffect def (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=status_effect_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting StatusEffect def {status_effect_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_delete:error_generic_delete",lang_code,"Error deleting StatusEffect def '{name}' (ID: {id}): {err}")
                await interaction.followup.send(error_msg.format(name=se_name_for_msg, id=status_effect_id, err=str(e)), ephemeral=True)

    # --- ActiveStatusEffect (Instances) CRUD ---
    active_status_effect_group = app_commands.Group(name="active_status_effect", description="Master commands for managing active Status Effect instances.", parent=master_admin)

    @active_status_effect_group.command(name="view_instance", description="View details of an active Status Effect instance.")
    @app_commands.describe(active_status_effect_id="The database ID of the ActiveStatusEffect instance.")
    async def active_status_effect_view(self, interaction: discord.Interaction, active_status_effect_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_status_effect import active_status_effect_crud, status_effect_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            active_se = await active_status_effect_crud.get_by_id_and_guild(session, id=active_status_effect_id, guild_id=interaction.guild_id)

            if not active_se:
                not_found_msg = await get_localized_message_template(session, interaction.guild_id, "active_se_view:not_found", lang_code, "ActiveStatusEffect with ID {id} not found.")
                await interaction.followup.send(not_found_msg.format(id=active_status_effect_id), ephemeral=True); return

            se_def_name = "Unknown Definition"
            se_definition = await status_effect_crud.get(session, id=active_se.status_effect_id)
            if se_definition:
                se_def_name = se_definition.name_i18n.get(lang_code, se_definition.name_i18n.get("en", f"Def ID {active_se.status_effect_id}"))

            title_template = await get_localized_message_template(session, interaction.guild_id, "active_se_view:title", lang_code, "Active Status Effect: {name} (Instance ID: {id})")
            embed_title = title_template.format(name=se_def_name, id=active_se.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.lighter_grey())

            async def get_label(key: str, default: str) -> str: return await get_localized_message_template(session, interaction.guild_id, f"active_se_view:label_{key}", lang_code, default)
            async def format_json_field(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

            embed.add_field(name=await get_label("guild", "Guild ID"), value=str(active_se.guild_id), inline=True)
            embed.add_field(name=await get_label("def_id", "Definition ID"), value=str(active_se.status_effect_id), inline=True)
            embed.add_field(name=await get_label("entity_type", "Entity Type"), value=active_se.entity_type.value if active_se.entity_type else "N/A", inline=True)
            embed.add_field(name=await get_label("entity_id", "Entity ID"), value=str(active_se.entity_id), inline=True)
            embed.add_field(name=await get_label("duration", "Duration (Turns)"), value=str(active_se.duration_turns) if active_se.duration_turns is not None else "Infinite", inline=True)
            embed.add_field(name=await get_label("remaining", "Remaining (Turns)"), value=str(active_se.remaining_turns) if active_se.remaining_turns is not None else "Infinite", inline=True)

            source_entity_type_val = active_se.source_entity_type.value if active_se.source_entity_type else "N/A"
            source_entity_id_val = str(active_se.source_entity_id) if active_se.source_entity_id is not None else "N/A"
            embed.add_field(name=await get_label("source_entity", "Source Entity"), value=f"{source_entity_type_val}({source_entity_id_val})", inline=True)
            embed.add_field(name=await get_label("source_ability_id", "Source Ability ID"), value=str(active_se.source_ability_id) if active_se.source_ability_id else "N/A", inline=True)
            embed.add_field(name=await get_label("source_log_id", "Source Log ID"), value=str(active_se.source_log_id) if active_se.source_log_id else "N/A", inline=True)

            applied_at_val = discord.utils.format_dt(active_se.applied_at, style='F') if active_se.applied_at else "N/A"
            embed.add_field(name=await get_label("applied_at", "Applied At"), value=applied_at_val, inline=False)

            props_str = await format_json_field(active_se.instance_properties_json, "active_se_view:value_na_json", "active_se_view:error_serialization_props")
            embed.add_field(name=await get_label("instance_props", "Instance Properties JSON"), value=f"```json\n{props_str[:1000]}\n```" + ("..." if len(props_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @active_status_effect_group.command(name="list_instances", description="List active Status Effect instances.")
    @app_commands.describe(
        entity_id="Optional: Filter by ID of the entity bearing the status.",
        entity_type="Optional: Filter by type of the entity (PLAYER, GENERATED_NPC). Requires entity_id.",
        status_effect_def_id="Optional: Filter by the base StatusEffect definition ID.",
        page="Page number.",
        limit="Instances per page."
    )
    async def active_status_effect_list(self, interaction: discord.Interaction,
                                        entity_id: Optional[int] = None,
                                        entity_type: Optional[str] = None,
                                        status_effect_def_id: Optional[int] = None,
                                        page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 5: limit = 5 # Embeds can be long

        from src.core.crud.crud_status_effect import active_status_effect_crud, status_effect_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from src.models.enums import RelationshipEntityType # For entity_type validation
        from sqlalchemy import select, func, and_

        lang_code = str(interaction.locale)
        entity_type_enum: Optional[RelationshipEntityType] = None

        async with get_db_session() as session:
            if entity_type:
                try: entity_type_enum = RelationshipEntityType[entity_type.upper()]
                except KeyError:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_list:error_invalid_entity_type",lang_code,"Invalid entity_type.")
                    await interaction.followup.send(error_msg, ephemeral=True); return

            if entity_id is not None and entity_type_enum is None:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_list:error_entity_id_no_type",lang_code,"If entity_id provided, entity_type is required.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            filters = [active_status_effect_crud.model.guild_id == interaction.guild_id]
            if entity_id is not None and entity_type_enum:
                filters.append(active_status_effect_crud.model.entity_id == entity_id)
                filters.append(active_status_effect_crud.model.entity_type == entity_type_enum)
            if status_effect_def_id is not None:
                filters.append(active_status_effect_crud.model.status_effect_id == status_effect_def_id)

            offset = (page - 1) * limit
            query = select(active_status_effect_crud.model).where(and_(*filters)).offset(offset).limit(limit).order_by(active_status_effect_crud.model.id.desc())
            result = await session.execute(query)
            active_ses = result.scalars().all()

            count_query = select(func.count(active_status_effect_crud.model.id)).where(and_(*filters))
            total_active_ses_res = await session.execute(count_query)
            total_active_ses = total_active_ses_res.scalar_one_or_none() or 0

            filter_parts = []
            if entity_id is not None and entity_type_enum: filter_parts.append(f"Entity: {entity_type_enum.name}({entity_id})")
            if status_effect_def_id is not None: filter_parts.append(f"Def ID: {status_effect_def_id}")
            filter_display = ", ".join(filter_parts) if filter_parts else "All"

            if not active_ses:
                no_ases_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_list:no_ases_found",lang_code,"No Active StatusEffects for {filter} (Page {p}).")
                await interaction.followup.send(no_ases_msg.format(filter=filter_display, p=page), ephemeral=True); return

            title_tmpl = await get_localized_message_template(session,interaction.guild_id,"active_se_list:title",lang_code,"Active StatusEffect List ({filter} - Page {p} of {tp})")
            total_pages = ((total_active_ses - 1) // limit) + 1
            embed = discord.Embed(title=title_tmpl.format(filter=filter_display, p=page, tp=total_pages), color=discord.Color.dark_gray())

            footer_tmpl = await get_localized_message_template(session,interaction.guild_id,"active_se_list:footer",lang_code,"Displaying {c} of {t} total active effects.")
            embed.set_footer(text=footer_tmpl.format(c=len(active_ses), t=total_active_ses))

            # Pre-fetch all unique item definitions for names to optimize
            def_ids = list(set(ase.status_effect_id for ase in active_ses))
            def_names = {}
            if def_ids:
                defs = await status_effect_crud.get_many_by_ids(session, ids=def_ids)
                for d in defs: def_names[d.id] = d.name_i18n.get(lang_code, d.name_i18n.get("en", f"Def {d.id}"))

            name_tmpl = await get_localized_message_template(session,interaction.guild_id,"active_se_list:ase_name_field",lang_code,"ID: {id} | {def_name} (Def ID: {def_id})")
            val_tmpl = await get_localized_message_template(session,interaction.guild_id,"active_se_list:ase_value_field",lang_code,"On: {e_type}({e_id}), Turns Left: {turns}")

            for ase in active_ses:
                def_name = def_names.get(ase.status_effect_id, "Unknown Def")
                turns_left = str(ase.remaining_turns) if ase.remaining_turns is not None else "Infinite"
                embed.add_field(
                    name=name_tmpl.format(id=ase.id, def_name=def_name, def_id=ase.status_effect_id),
                    value=val_tmpl.format(e_type=ase.entity_type.name if ase.entity_type else "N/A", e_id=ase.entity_id, turns=turns_left),
                    inline=False
                )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @active_status_effect_group.command(name="remove_instance", description="Remove an active Status Effect instance from an entity.")
    @app_commands.describe(active_status_effect_id="The database ID of the ActiveStatusEffect instance to remove.")
    async def active_status_effect_remove(self, interaction: discord.Interaction, active_status_effect_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.core.crud.crud_status_effect import active_status_effect_crud
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        # May need ability_system.remove_status if it contains more logic than simple DB delete.
        # For now, using direct CRUD remove.

        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            active_se_to_delete = await active_status_effect_crud.get_by_id_and_guild(
                session, id=active_status_effect_id, guild_id=interaction.guild_id
            )

            if not active_se_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_remove:error_not_found",lang_code,"ActiveStatusEffect ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=active_status_effect_id), ephemeral=True); return

            entity_id_for_msg = active_se_to_delete.entity_id
            entity_type_for_msg = active_se_to_delete.entity_type.name if active_se_to_delete.entity_type else "Unknown"
            status_effect_id_for_msg = active_se_to_delete.status_effect_id


            # Note: This is a direct DB removal. Game logic for "on_remove" effects is bypassed.
            # This is acceptable for a master command intended for direct intervention.
            try:
                async with session.begin():
                    deleted_ase = await active_status_effect_crud.remove(session, id=active_status_effect_id)

                if deleted_ase:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_remove:success",lang_code,"ActiveStatusEffect ID {id} (Def ID: {def_id}) removed from Entity {e_type}({e_id}).")
                    await interaction.followup.send(success_msg.format(id=active_status_effect_id, def_id=status_effect_id_for_msg, e_type=entity_type_for_msg, e_id=entity_id_for_msg), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_remove:error_unknown_delete_fail",lang_code,"ActiveStatusEffect (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=active_status_effect_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error removing ActiveStatusEffect {active_status_effect_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_remove:error_generic_delete",lang_code,"Error removing ActiveStatusEffect ID {id}: {err}")
                await interaction.followup.send(error_msg.format(id=active_status_effect_id, err=str(e)), ephemeral=True)

    # --- StoryLog CRUD (View/List Only) ---
    story_log_group = app_commands.Group(name="story_log", description="Master commands for viewing Story Log entries.", parent=master_admin)

    @story_log_group.command(name="view", description="View details of a specific Story Log entry.")
    @app_commands.describe(log_id="The database ID of the Story Log entry to view.")
    async def story_log_view(self, interaction: discord.Interaction, log_id: int):
        await interaction.response.defer(ephemeral=True)

        from src.models.story_log import StoryLog # Import model
        from src.core.crud_base_definitions import CRUDBase # Use base CRUD
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template

        story_log_crud_instance = CRUDBase(StoryLog)

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            log_entry = await story_log_crud_instance.get_by_id_and_guild(session, id=log_id, guild_id=interaction.guild_id)

            if not log_entry:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "story_log_view:not_found", lang_code,
                    "Story Log entry with ID {id} not found."
                )
                await interaction.followup.send(not_found_msg.format(id=log_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "story_log_view:title", lang_code,
                "Story Log Entry (ID: {id})"
            )
            embed_title = title_template.format(id=log_entry.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.blue())

            async def get_label(key: str, default: str) -> str: return await get_localized_message_template(session, interaction.guild_id, f"story_log_view:label_{key}", lang_code, default)
            async def format_json_field(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(log_entry.guild_id), inline=True)
            embed.add_field(name=await get_label("event_type", "Event Type"), value=log_entry.event_type.value if log_entry.event_type else "N/A", inline=True)
            embed.add_field(name=await get_label("turn_number", "Turn Number"), value=str(log_entry.turn_number) if log_entry.turn_number is not None else "N/A", inline=True)

            timestamp_val = discord.utils.format_dt(log_entry.timestamp, style='F') if log_entry.timestamp else "N/A"
            embed.add_field(name=await get_label("timestamp", "Timestamp"), value=timestamp_val, inline=False)

            embed.add_field(name=await get_label("short_description", "Short Description"), value=log_entry.short_description_i18n.get(lang_code, log_entry.short_description_i18n.get("en", "N/A"))[:1020], inline=False)

            details_str = await format_json_field(log_entry.details_json, "story_log_view:value_na_json", "story_log_view:error_serialization_details")
            embed.add_field(name=await get_label("details_json", "Details JSON"), value=f"```json\n{details_str[:1000]}\n```" + ("..." if len(details_str) > 1000 else ""), inline=False)

            entities_str = await format_json_field(log_entry.entity_ids_json, "story_log_view:value_na_json", "story_log_view:error_serialization_entities")
            embed.add_field(name=await get_label("entity_ids_json", "Entity IDs JSON"), value=f"```json\n{entities_str[:1000]}\n```" + ("..." if len(entities_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @story_log_group.command(name="list", description="List Story Log entries with filters.")
    @app_commands.describe(
        event_type="Optional: Filter by EventType (e.g., PLAYER_ACTION, COMBAT_START).",
        turn_number="Optional: Filter by turn number.",
        # entity_id="Optional: Filter by an entity ID involved in the event (searches entity_ids_json).", # Complex to implement efficiently
        # entity_type="Optional: Filter by an entity type involved (used with entity_id).", # Complex
        page="Page number.",
        limit="Entries per page."
    )
    async def story_log_list(self, interaction: discord.Interaction,
                             event_type: Optional[str] = None,
                             turn_number: Optional[int] = None,
                             page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 5: limit = 5 # Embeds can be very long with JSON

        from src.models.story_log import StoryLog
        from src.core.crud_base_definitions import CRUDBase
        from src.core.database import get_db_session
        from src.core.localization_utils import get_localized_message_template
        from src.models.enums import EventType as EventTypeEnum # For validation
        from sqlalchemy import select, func, and_

        story_log_crud_instance = CRUDBase(StoryLog)
        lang_code = str(interaction.locale)
        event_type_enum_val: Optional[EventTypeEnum] = None

        async with get_db_session() as session:
            if event_type:
                try: event_type_enum_val = EventTypeEnum[event_type.upper()]
                except KeyError:
                    valid_types = ", ".join([et.name for et in EventTypeEnum])
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"story_log_list:error_invalid_event_type",lang_code,"Invalid event_type. Valid: {list}")
                    await interaction.followup.send(error_msg.format(list=valid_types), ephemeral=True); return

            filters = [story_log_crud_instance.model.guild_id == interaction.guild_id]
            if event_type_enum_val:
                filters.append(story_log_crud_instance.model.event_type == event_type_enum_val)
            if turn_number is not None:
                filters.append(story_log_crud_instance.model.turn_number == turn_number)
            # Filtering by entity_ids_json is more complex and might require JSON operators or fetching and filtering in Python.
            # For now, we'll omit direct entity_id/entity_type filtering in the query for simplicity.

            offset = (page - 1) * limit
            query = select(story_log_crud_instance.model).where(and_(*filters)).offset(offset).limit(limit).order_by(story_log_crud_instance.model.timestamp.desc(), story_log_crud_instance.model.id.desc())
            result = await session.execute(query)
            log_entries = result.scalars().all()

            count_query = select(func.count(story_log_crud_instance.model.id)).where(and_(*filters))
            total_logs_res = await session.execute(count_query)
            total_logs = total_logs_res.scalar_one_or_none() or 0

            filter_parts = []
            if event_type_enum_val: filter_parts.append(f"Event: {event_type_enum_val.name}")
            if turn_number is not None: filter_parts.append(f"Turn: {turn_number}")
            filter_display = ", ".join(filter_parts) if filter_parts else "All"

            if not log_entries:
                no_logs_msg = await get_localized_message_template(session,interaction.guild_id,"story_log_list:no_logs_found",lang_code,"No Story Log entries for {filter} (Page {p}).")
                await interaction.followup.send(no_logs_msg.format(filter=filter_display, p=page), ephemeral=True); return

            title_tmpl = await get_localized_message_template(session,interaction.guild_id,"story_log_list:title",lang_code,"Story Log List ({filter} - Page {p} of {tp})")
            total_pages = ((total_logs - 1) // limit) + 1
            embed = discord.Embed(title=title_tmpl.format(filter=filter_display, p=page, tp=total_pages), color=discord.Color.dark_blue())

            footer_tmpl = await get_localized_message_template(session,interaction.guild_id,"story_log_list:footer",lang_code,"Displaying {c} of {t} total log entries.")
            embed.set_footer(text=footer_tmpl.format(c=len(log_entries), t=total_logs))

            name_tmpl = await get_localized_message_template(session,interaction.guild_id,"story_log_list:log_name_field",lang_code,"ID: {id} | {event_type_val} (Turn: {tn})")
            val_tmpl = await get_localized_message_template(session,interaction.guild_id,"story_log_list:log_value_field",lang_code,"{desc} (@ {ts})")

            for entry in log_entries:
                desc_short = entry.short_description_i18n.get(lang_code, entry.short_description_i18n.get("en", "No description"))
                ts_formatted = discord.utils.format_dt(entry.timestamp, style='R') if entry.timestamp else "No timestamp"
                embed.add_field(
                    name=name_tmpl.format(id=entry.id, event_type_val=entry.event_type.value if entry.event_type else "N/A", tn=entry.turn_number if entry.turn_number is not None else "N/A"),
                    value=val_tmpl.format(desc=desc_short[:200] + ("..." if len(desc_short) > 200 else ""), ts=ts_formatted),
                    inline=False
                )
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    # Need to import json for player_view's attributes_json
    import json # Make json available in the cog's scope if methods need it
    cog = MasterAdminCog(bot)
    # Manually attach the player_group to the master_admin_group if not done by parent param.
    # This is usually handled by the parent=master_admin_group in Group definition.
    # For clarity, we can log or verify this.
    # logger.debug(f"MasterAdminCog master_admin_group: {cog.master_admin_group}")
    # logger.debug(f"Player group parent: {cog.player_group.parent}")
    await bot.add_cog(cog)
    logger.info("MasterAdminCog loaded successfully with player commands.")

# Не забудьте добавить "src.bot.commands.master_admin_commands" в BOT_COGS в src/config/settings.py
# BOT_COGS = [
#     "src.bot.commands.general_commands",
#     "src.bot.commands.movement_commands",
#     "src.bot.commands.party_commands",
#     "src.bot.commands.master_ai_commands",
#     "src.bot.commands.master_map_commands",
#     "src.bot.commands.character_commands", # Task 32
#     "src.bot.commands.master_admin_commands", # Новая строка
# ]
