import logging
import json
from typing import Dict, Any, Optional, List

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select # For count

from src.core.crud.crud_player import player_crud
from src.core.database import get_db_session, transactional
from src.core.crud_base_definitions import update_entity
from src.core.localization_utils import get_localized_message_template
# from src.models.player import PlayerStatus # If needed for direct enum comparison

logger = logging.getLogger(__name__)

class MasterPlayerCog(commands.Cog, name="Master Player Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterPlayerCog initialized.")

    player_master_cmds = app_commands.Group(
        name="master_player",
        description="Master commands for managing players.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    @player_master_cmds.command(name="view", description="View details of a specific player.")
    @app_commands.describe(player_id="The database ID of the player to view.")
    async def player_view(self, interaction: discord.Interaction, player_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            player = await player_crud.get(session, id=player_id, guild_id=interaction.guild_id)
            lang_code = str(interaction.locale)

            if not player:
                not_found_msg_template = await get_localized_message_template(
                    session, interaction.guild_id, "player_view:not_found", lang_code,
                    "Player with ID {player_id} not found in this guild."
                ) # type: ignore
                await interaction.followup.send(not_found_msg_template.format(player_id=player_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "player_view:title", lang_code,
                "Player Details: {player_name} (ID: {player_id})"
            ) # type: ignore
            embed_title = title_template.format(player_name=player.name, player_id=player.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.green())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"player_view:field_{key}", lang_code, default) # type: ignore

            embed.add_field(name=await get_label("discord_id", "Discord ID"), value=str(player.discord_id), inline=True)
            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(player.guild_id), inline=True)
            embed.add_field(name=await get_label("level", "Level"), value=str(player.level), inline=True)
            embed.add_field(name=await get_label("xp", "XP"), value=str(player.xp), inline=True)
            embed.add_field(name=await get_label("unspent_xp", "Unspent XP"), value=str(player.unspent_xp), inline=True)
            embed.add_field(name=await get_label("location_id", "Current Location ID"), value=str(player.current_location_id) if player.current_location_id else "N/A", inline=True)
            embed.add_field(name=await get_label("party_id", "Current Party ID"), value=str(player.current_party_id) if player.current_party_id else "N/A", inline=True)
            embed.add_field(name=await get_label("status", "Status"), value=player.current_status.value if player.current_status else "N/A", inline=True)
            player_language = getattr(player, 'language', "N/A") # Defensive access
            embed.add_field(name=await get_label("language", "Language"), value=player_language or "N/A", inline=True)


            attributes_label = await get_label("attributes_json", "Attributes JSON")
            attributes_str = await get_localized_message_template(session, interaction.guild_id, "player_view:no_attributes", lang_code, "No attributes") # type: ignore
            if player.attributes_json:
                try:
                    attributes_str = json.dumps(player.attributes_json, indent=2, ensure_ascii=False)
                except TypeError:
                    attributes_str = await get_localized_message_template(session, interaction.guild_id, "player_view:error_attributes_serialization", lang_code, "Error displaying attributes (non-serializable).")

            embed.add_field(name=attributes_label, value=f"```json\n{attributes_str[:1000]}\n```" + ("..." if len(attributes_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @player_master_cmds.command(name="list", description="List players in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of players per page.")
    async def player_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 25: limit = 25 # Max 25 for embeds
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            offset = (page - 1) * limit
            players = await player_crud.get_multi(session, guild_id=interaction.guild_id, skip=offset, limit=limit)

            total_players_stmt = select(func.count(player_crud.model.id)).where(player_crud.model.guild_id == interaction.guild_id)
            total_players_result = await session.execute(total_players_stmt)
            total_players = total_players_result.scalar_one_or_none() or 0
            lang_code = str(interaction.locale)

            if not players:
                no_players_msg = await get_localized_message_template(
                    session, interaction.guild_id, "player_list:no_players_found_page", lang_code,
                    "No players found for this guild (Page {page})."
                ) # type: ignore
                await interaction.followup.send(no_players_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "player_list:title", lang_code,
                "Player List (Page {page} of {total_pages})"
            ) # type: ignore
            total_pages = ((total_players - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.blue())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "player_list:footer", lang_code,
                "Displaying {count} of {total} total players."
            ) # type: ignore
            embed.set_footer(text=footer_template.format(count=len(players), total=total_players))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "player_list:player_field_name", lang_code,
                "ID: {player_id} | {player_name}"
            ) # type: ignore
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "player_list:player_field_value", lang_code,
                "Discord: <@{discord_id}>\nLevel: {level}, Status: {status}"
            ) # type: ignore

            for p in players:
                embed.add_field(
                    name=field_name_template.format(player_id=p.id, player_name=p.name),
                    value=field_value_template.format(discord_id=p.discord_id, level=p.level, status=p.current_status.value),
                    inline=False
                )

            if len(embed.fields) == 0: # Should not happen if `not players` check is passed
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "player_list:no_players_to_display", lang_code,
                    "No players found to display on page {page}."
                ) # type: ignore
                await interaction.followup.send(no_display_msg.format(page=page), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @player_master_cmds.command(name="update", description="Update a specific field for a player.")
    @app_commands.describe(
        player_id="The database ID of the player to update.",
        field_to_update="The name of the player field to update (e.g., name, level, xp, language).",
        new_value="The new value for the field (use JSON for complex types if supported)."
    )
    async def player_update(self, interaction: discord.Interaction, player_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        allowed_fields = {
            "name": str,
            "level": int,
            "xp": int,
            "unspent_xp": int,
            "language": str,
            "current_location_id": (int, type(None)), # Made Optional
            "current_party_id": (int, type(None)),
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()
        field_type_info = allowed_fields.get(field_to_update_lower)

        if not field_type_info:
            async with get_db_session() as temp_session_for_error_msg:
                not_allowed_msg = await get_localized_message_template(
                    temp_session_for_error_msg, interaction.guild_id, "player_update:field_not_allowed", lang_code,
                    "Field '{field_name}' is not allowed for update or does not exist. Allowed fields: {allowed_list}"
                ) # type: ignore
            await interaction.followup.send(not_allowed_msg.format(field_name=field_to_update, allowed_list=', '.join(allowed_fields.keys())), ephemeral=True)
            return

        parsed_value: Any = None
        try:
            is_optional_int = isinstance(field_type_info, tuple) and int in field_type_info and type(None) in field_type_info

            if new_value.lower() == 'none' or new_value.lower() == 'null':
                if is_optional_int or field_to_update_lower == "language": # language can be nullable string
                    parsed_value = None
                else: # Field is not Optional[int] or not 'language', so None is not allowed
                    raise ValueError(f"Field '{field_to_update_lower}' cannot be set to None.")
            elif field_type_info == str:
                parsed_value = new_value
            elif field_type_info == int or is_optional_int:
                parsed_value = int(new_value) # Can raise ValueError
            # Note: No JSON fields are currently allowed for direct update via this command in `allowed_fields`
            else: # Should not be reached due to field_type_info check
                async with get_db_session() as temp_session_for_error_msg:
                    internal_error_msg = await get_localized_message_template(
                        temp_session_for_error_msg, interaction.guild_id, "player_update:error_type_conversion_not_implemented", lang_code,
                        "Internal error: Type conversion for field '{field_name}' not implemented."
                    ) # type: ignore
                await interaction.followup.send(internal_error_msg.format(field_name=field_to_update), ephemeral=True)
                return
        except ValueError as e: # Catches int() conversion errors and explicit ValueErrors
            async with get_db_session() as temp_session_for_error_msg:
                invalid_value_msg = await get_localized_message_template(
                    temp_session_for_error_msg, interaction.guild_id, "player_update:error_invalid_value_for_type", lang_code,
                    "Invalid value '{value}' for field '{field_name}'. Details: {details}"
                ) # type: ignore
            expected_type_str = field_type_info.__name__ if not isinstance(field_type_info, tuple) else 'int or None'
            if field_type_info == str and field_to_update_lower == "language": expected_type_str = "string or None"

            await interaction.followup.send(invalid_value_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True)
            return
        # Removed json.JSONDecodeError catch as no JSON fields are currently updatable

        update_data = {field_to_update_lower: parsed_value}

        async with get_db_session() as session:
            player = await player_crud.get(session, id=player_id, guild_id=interaction.guild_id)
            if not player:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "player_update:player_not_found", lang_code,
                    "Player with ID {player_id} not found in this guild."
                ) # type: ignore
                await interaction.followup.send(not_found_msg.format(player_id=player_id), ephemeral=True)
                return

            updated_player: Optional[Any] = None # Ensure updated_player is defined before try block
            try:
                async with session.begin():
                    updated_player = await update_entity(session, entity=player, data=update_data)
                    if updated_player: # Refresh only if update_entity returned an object
                        await session.refresh(updated_player)
            except Exception as e:
                logger.error(f"Error updating player {player_id} with data {update_data}: {e}", exc_info=True)
                generic_error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "player_update:error_generic_update", lang_code,
                    "An error occurred while updating player {player_id}: {error_message}"
                ) # type: ignore
                await interaction.followup.send(generic_error_msg.format(player_id=player_id, error_message=str(e)), ephemeral=True)
                return

            if not updated_player: # Check if update or refresh failed
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "player_update:error_update_failed_unknown", lang_code,
                    "Player update failed for an unknown reason."
                ) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)
                return


            title_template = await get_localized_message_template(
                session, interaction.guild_id, "player_update:success_title", lang_code,
                "Player Updated: {player_name} (ID: {player_id})"
            ) # type: ignore
            embed_title = title_template.format(player_name=updated_player.name, player_id=updated_player.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.orange())

            field_updated_label = await get_localized_message_template(session, interaction.guild_id, "player_update:label_field_updated", lang_code, "Field Updated") # type: ignore
            new_value_label = await get_localized_message_template(session, interaction.guild_id, "player_update:label_new_value", lang_code, "New Value") # type: ignore

            embed.add_field(name=field_updated_label, value=field_to_update, inline=True)
            new_value_display = str(parsed_value)
            if parsed_value is None:
                new_value_display = "None"
            embed.add_field(name=new_value_label, value=new_value_display, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    cog = MasterPlayerCog(bot)
    await bot.add_cog(cog)
    # If player_master_cmds is a Group defined in the Cog instance:
    # bot.tree.add_command(cog.player_master_cmds)
    # However, if it's a class variable, it's typically added when the Cog is added.
    # For app_commands.Group, it should be automatically registered if the Cog is added.
    # If issues arise, explicit bot.tree.add_command(cog.player_master_cmds, guild=discord.Object(id=GUILD_ID) or guilds=[discord.Object(id=GUILD_ID)]) might be needed
    # but guild_only=True on the group should handle this.
    logger.info("MasterPlayerCog loaded and commands (hopefully) registered.")
