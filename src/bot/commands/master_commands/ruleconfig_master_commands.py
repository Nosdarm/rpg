import logging
import json
from typing import Dict, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.rules import get_rule, update_rule_config, get_all_rules_for_guild, rule_config_crud
from src.core.database import get_db_session
from src.core.localization_utils import get_localized_message_template

logger = logging.getLogger(__name__)

class MasterRuleConfigCog(commands.Cog, name="Master RuleConfig Commands"): # type: ignore[call-arg]
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterRuleConfigCog initialized.")

    ruleconfig_master_cmds = app_commands.Group(
        name="master_ruleconfig",
        description="Master commands for managing RuleConfig entries.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    @ruleconfig_master_cmds.command(name="get", description="Get a specific RuleConfig value.")
    @app_commands.describe(key="The key of the RuleConfig entry to view.")
    async def ruleconfig_get(self, interaction: discord.Interaction, key: str):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.") # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            rule_value = await get_rule(session, guild_id=interaction.guild_id, key=key)

            if rule_value is None:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ruleconfig_get:not_found", lang_code,
                    "RuleConfig with key '{key_name}' not found for this guild."
                ) # type: ignore
                await interaction.followup.send(not_found_msg.format(key_name=key), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "ruleconfig_get:title", lang_code,
                "RuleConfig: {key_name}"
            ) # type: ignore
            embed = discord.Embed(title=title_template.format(key_name=key), color=discord.Color.purple())

            key_label = await get_localized_message_template(session, interaction.guild_id, "ruleconfig_get:label_key", lang_code, "Key") # type: ignore
            value_label = await get_localized_message_template(session, interaction.guild_id, "ruleconfig_get:label_value", lang_code, "Value") # type: ignore

            try:
                value_str = json.dumps(rule_value, indent=2, ensure_ascii=False)
            except TypeError:
                value_str = await get_localized_message_template(
                    session, interaction.guild_id, "ruleconfig_get:error_serialization", lang_code,
                    "Error displaying value (non-serializable)."
                ) # type: ignore

            embed.add_field(name=key_label, value=key, inline=False)
            embed.add_field(name=value_label, value=f"```json\n{value_str[:1000]}\n```" + ("..." if len(value_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @ruleconfig_master_cmds.command(name="set", description="Set or update a RuleConfig value.")
    @app_commands.describe(key="The key of the RuleConfig entry.", value_json="The new JSON value for the rule.")
    async def ruleconfig_set(self, interaction: discord.Interaction, key: str, value_json: str):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.") # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        # lang_code = str(interaction.locale) # Already defined
        new_value: Any
        try:
            new_value = json.loads(value_json)
        except json.JSONDecodeError:
            async with get_db_session() as temp_session_for_error_msg: # Separate session for early error message
                 invalid_json_msg = await get_localized_message_template(
                    temp_session_for_error_msg, interaction.guild_id, "ruleconfig_set:error_invalid_json", lang_code,
                    "Invalid JSON string provided for value: {json_string}"
                ) # type: ignore
            await interaction.followup.send(invalid_json_msg.format(json_string=value_json), ephemeral=True)
            return

        async with get_db_session() as session:
            try:
                # guild_id is confirmed not None here
                updated_rule = await update_rule_config(session, guild_id=interaction.guild_id, key=key, value=new_value)
            except Exception as e:
                logger.error(f"Error calling update_rule_config for key {key} with value {new_value}: {e}", exc_info=True)
                error_set_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ruleconfig_set:error_generic_set", lang_code,
                    "An error occurred while setting rule '{key_name}': {error_message}"
                ) # type: ignore
                await interaction.followup.send(error_set_msg.format(key_name=key, error_message=str(e)), ephemeral=True)
                return

            success_msg = await get_localized_message_template(
                session, interaction.guild_id, "ruleconfig_set:success", lang_code,
                "RuleConfig '{key_name}' has been set/updated successfully."
            ) # type: ignore
            await interaction.followup.send(success_msg.format(key_name=key), ephemeral=True)

    @ruleconfig_master_cmds.command(name="list", description="List all RuleConfig entries for this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of rules per page.")
    async def ruleconfig_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.") # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            # guild_id is confirmed not None here
            all_rules_dict = await get_all_rules_for_guild(session, guild_id=interaction.guild_id)

            if not all_rules_dict:
                no_rules_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ruleconfig_list:no_rules_found", lang_code,
                    "No RuleConfig entries found for this guild."
                ) # type: ignore
                await interaction.followup.send(no_rules_msg, ephemeral=True)
                return

            rules_list = sorted(all_rules_dict.items())
            total_rules = len(rules_list)

            start_index = (page - 1) * limit
            end_index = start_index + limit
            paginated_rules = rules_list[start_index:end_index]

            if not paginated_rules: # This case should ideally be covered by "no_rules_found" if total_rules is 0
                no_rules_on_page_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ruleconfig_list:no_rules_on_page", lang_code,
                    "No rules found on page {page_num}."
                ) # type: ignore
                await interaction.followup.send(no_rules_on_page_msg.format(page_num=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "ruleconfig_list:title", lang_code,
                "RuleConfig List (Page {page_num} of {total_pages})"
            ) # type: ignore
            total_pages = ((total_rules - 1) // limit) + 1
            embed_title = title_template.format(page_num=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_purple())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "ruleconfig_list:footer", lang_code,
                "Displaying {count} of {total} total rules."
            ) # type: ignore
            embed.set_footer(text=footer_template.format(count=len(paginated_rules), total=total_rules))

            error_serialization_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ruleconfig_list:error_serialization", lang_code,
                    "Error: Non-serializable value."
                ) # type: ignore

            for key, value in paginated_rules:
                try:
                    value_str = json.dumps(value, ensure_ascii=False)
                    if len(value_str) > 150: # Keep value preview brief
                        value_str = value_str[:150] + "..."
                except TypeError:
                    value_str = error_serialization_msg
                embed.add_field(name=key, value=f"```json\n{value_str}\n```", inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @ruleconfig_master_cmds.command(name="delete", description="Delete a specific RuleConfig entry.")
    @app_commands.describe(key="The key of the RuleConfig entry to delete.")
    async def ruleconfig_delete(self, interaction: discord.Interaction, key: str):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.") # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            # Assuming get_by_key is the correct replacement for get_by_guild_and_key
            existing_rule = await rule_config_crud.get_by_key(session, guild_id=interaction.guild_id, key=key) # type: ignore
            if not existing_rule:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ruleconfig_delete:not_found", lang_code,
                    "RuleConfig with key '{key_name}' not found. Nothing to delete."
                ) # type: ignore
                await interaction.followup.send(not_found_msg.format(key_name=key), ephemeral=True)
                return

            try:
                async with session.begin():
                    # Assuming remove_by_key is the correct replacement
                    deleted_count = await rule_config_crud.remove_by_key( # type: ignore
                        session=session, guild_id=interaction.guild_id, key=key
                    )

                if deleted_count and deleted_count > 0:
                    success_msg = await get_localized_message_template(
                        session, interaction.guild_id, "ruleconfig_delete:success", lang_code,
                        "RuleConfig '{key_name}' has been deleted successfully."
                    ) # type: ignore
                    await interaction.followup.send(success_msg.format(key_name=key), ephemeral=True)
                else: # Should not happen if existing_rule was found
                    error_not_deleted_msg = await get_localized_message_template(
                        session, interaction.guild_id, "ruleconfig_delete:error_not_deleted", lang_code,
                        "RuleConfig '{key_name}' was found but could not be deleted."
                    ) # type: ignore
                    await interaction.followup.send(error_not_deleted_msg.format(key_name=key), ephemeral=True)

            except Exception as e:
                logger.error(f"Error deleting RuleConfig key {key} for guild {interaction.guild_id}: {e}", exc_info=True)
                generic_error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "ruleconfig_delete:error_generic", lang_code,
                    "An error occurred while deleting rule '{key_name}': {error_message}"
                ) # type: ignore
                await interaction.followup.send(generic_error_msg.format(key_name=key, error_message=str(e)), ephemeral=True)
                return

async def setup(bot: commands.Bot):
    cog = MasterRuleConfigCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterRuleConfigCog loaded.")
