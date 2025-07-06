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
    player_group = app_commands.Group(name="player", description="Master commands for managing players.", parent=master_admin)

    @player_group.command(name="view", description="View details of a specific player.")
    @app_commands.describe(player_id="The database ID of the player to view.")
    # No specific permission decorator needed
    async def player_view(self, interaction: discord.Interaction, player_id: int):
        await interaction.response.defer(ephemeral=True)
        # No need for guild_id check if group is guild_only=True
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return

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
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 25: limit = 25 # Max embed field limit consideration

        from src.core.crud.crud_player import player_crud # Local import
        from src.core.database import get_db_session # Local import
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
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return

        from src.core.crud.crud_player import player_crud
        from src.core.database import get_db_session, transactional # transactional might be used if update_entity is not
        from src.core.crud_base_definitions import update_entity # Using generic update

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
            not_allowed_msg = await get_localized_message_template(
                session, interaction.guild_id, "player_update:field_not_allowed", lang_code,
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
                internal_error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "player_update:error_type_conversion_not_implemented", lang_code,
                    "Internal error: Type conversion for field '{field_name}' not implemented."
                )
                await interaction.followup.send(internal_error_msg.format(field_name=field_to_update), ephemeral=True)
                return

        except ValueError:
            invalid_value_msg = await get_localized_message_template(
                session, interaction.guild_id, "player_update:error_invalid_value_for_type", lang_code,
                "Invalid value '{value}' for field '{field_name}'. Expected type: {expected_type}."
            )
            expected_type_str = field_type.__name__ if not isinstance(field_type, tuple) else 'int or None'
            await interaction.followup.send(invalid_value_msg.format(value=new_value, field_name=field_to_update, expected_type=expected_type_str), ephemeral=True)
            return
        except json.JSONDecodeError:
            invalid_json_msg = await get_localized_message_template(
                session, interaction.guild_id, "player_update:error_invalid_json", lang_code,
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
    ruleconfig_group = app_commands.Group(name="ruleconfig", description="Master commands for managing RuleConfig entries.", parent=master_admin_group)

    @ruleconfig_group.command(name="get", description="Get a specific RuleConfig value.")
    @app_commands.describe(key="The key of the RuleConfig entry to view.")
    # No specific permission decorator needed
    async def ruleconfig_get(self, interaction: discord.Interaction, key: str):
        await interaction.response.defer(ephemeral=True)
        # No need for guild_id check
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return

        from src.core.rules import get_rule # Local import
        from src.core.database import get_db_session # Local import

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
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return

        from src.core.rules import update_rule_config # Local import
        from src.core.database import get_db_session # Local import for the context, though update_rule_config is @transactional

        lang_code = str(interaction.locale)
        try:
            new_value = json.loads(value_json)
        except json.JSONDecodeError:
            invalid_json_msg = await get_localized_message_template(
                session, interaction.guild_id, "ruleconfig_set:error_invalid_json", lang_code, # Assuming session is available from defer or a wrapper
                "Invalid JSON string provided for value: {json_string}"
            )
            # Need to get session for get_localized_message_template if not available.
            # For now, let's assume we will wrap this part or pass session if needed.
            # However, the plan is to use the session from `async with get_db_session()`.
            # So, localization calls should be within that block.
            # Let's move localization into the session block.
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
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10 # Embeds can get very long with many JSON values

        from src.core.rules import get_all_rules_for_guild # Local import
        from src.core.database import get_db_session # Local import

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            all_rules_dict = await get_all_rules_for_guild(session, guild_id=interaction.guild_id)

        if not all_rules_dict:
            no_rules_msg = await get_localized_message_template(
                session, interaction.guild_id, "ruleconfig_list:no_rules_found", lang_code, # Needs session, so call inside or pass one
                "No RuleConfig entries found for this guild."
            )
            # Similar to ruleconfig_set, if we want to localize this early error, we need a session.
            # For consistency, moving all localization calls that need session into the main session block.
            async with get_db_session() as temp_session_for_error_msg:
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

        from src.core.rules import rule_config_crud # Using CRUD directly for delete
        from src.core.database import get_db_session
        # from src.core.localization_utils import get_localized_message_template # Already imported or use self.

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
    conflict_group = app_commands.Group(name="conflict", description="Master commands for managing pending conflicts.", parent=master_admin_group)

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
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return

        from src.core.database import get_db_session # Keep for session management
        # from src.models.pending_conflict import PendingConflict # Not needed directly
        from src.models.enums import ConflictStatus
        from src.core.crud.crud_pending_conflict import pending_conflict_crud # Use specific CRUD
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
                        invalid_outcome_msg = await get_localized_message_template(
                            session, interaction.guild_id, "conflict_resolve:error_invalid_outcome_for_master", lang_code,
                            "Invalid outcome_status '{provided_status}'. Allowed values for master resolution: {allowed_list}"
                        )
                        await interaction.followup.send(invalid_outcome_msg.format(provided_status=outcome_status, allowed_list=allowed_values_str), ephemeral=True)
                        return

            if not resolved_status_enum: # Did not match any ConflictStatus name/value
                allowed_values_str = ", ".join([s.name for s in valid_resolution_statuses])
                unrecognized_outcome_msg = await get_localized_message_template(
                    session, interaction.guild_id, "conflict_resolve:error_unrecognized_outcome", lang_code,
                    "Outcome status '{provided_status}' not recognized or not a valid master resolution. Allowed: {allowed_list}"
                )
                await interaction.followup.send(unrecognized_outcome_msg.format(provided_status=outcome_status, allowed_list=allowed_values_str), ephemeral=True)
                return

        except ValueError: # Should not happen with current logic, but as a safeguard
            internal_error_msg = await get_localized_message_template(
                session, interaction.guild_id, "conflict_resolve:error_internal_status_check", lang_code,
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
            await interaction.followup.send("Command must be used in a guild.", ephemeral=True)
            return

        from src.core.database import get_db_session
        # from src.models.pending_conflict import PendingConflict # Not needed directly
        from src.core.crud.crud_pending_conflict import pending_conflict_crud # Use the specific CRUD
        # from src.core.localization_utils import get_localized_message_template # Already available in cog or via self

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
        # from src.core.localization_utils import get_localized_message_template

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
