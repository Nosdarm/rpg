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
            # This should ideally not be reached if guild_only=True is effective on the group
            async with get_db_session() as temp_session: # Need session for localization
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", str(interaction.locale), # interaction.guild_id might be None here
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
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

            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A") # type: ignore

            embed.add_field(name=await get_label("location_id", "Current Location ID"), value=str(player.current_location_id) if player.current_location_id else na_value_str, inline=True)
            embed.add_field(name=await get_label("party_id", "Current Party ID"), value=str(player.current_party_id) if player.current_party_id else na_value_str, inline=True)
            embed.add_field(name=await get_label("status", "Status"), value=player.current_status.value if player.current_status else na_value_str, inline=True)
            player_language = getattr(player, 'selected_language', None) # Use selected_language as per model
            embed.add_field(name=await get_label("language", "Language"), value=player_language or na_value_str, inline=True)


            attributes_label = await get_label("attributes_json", "Attributes JSON")
            attributes_str = await get_localized_message_template(session, interaction.guild_id, "player_view:no_attributes", lang_code, "No attributes") # type: ignore
            if player.attributes_json:
                try:
                    attributes_str = json.dumps(player.attributes_json, indent=2, ensure_ascii=False)
                except TypeError:
                    attributes_str = await get_localized_message_template(session, interaction.guild_id, "player_view:error_attributes_serialization", lang_code, "Error displaying attributes (non-serializable).")

            embed.add_field(name=attributes_label, value=f"```json\n{attributes_str[:1000]}\n```" + ("..." if len(attributes_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @player_master_cmds.command(name="create", description="Create a new player in this guild.")
    @app_commands.describe(
        discord_user="The Discord user to create a player for.",
        player_name="The in-game name for the player.",
        level="Optional: Initial level (default: 1).",
        xp="Optional: Initial XP (default: 0).",
        unspent_xp="Optional: Initial unspent XP (default: 0).",
        gold="Optional: Initial gold (default: 0).",
        current_hp="Optional: Initial current HP (defaults to max HP based on rules/attributes if not set).",
        language="Optional: Player's preferred language (e.g., 'en', 'ru'). Defaults to guild's main language or 'en'.",
        current_location_id="Optional: Database ID of the player's starting location.",
        attributes_json_str="Optional: JSON string for player's attributes (e.g., {\"strength\": 10})."
    )
    async def player_create(
        self,
        interaction: discord.Interaction,
        discord_user: discord.User,
        player_name: str,
        level: Optional[int] = None,
        xp: Optional[int] = None,
        unspent_xp: Optional[int] = None,
        gold: Optional[int] = None,
        current_hp: Optional[int] = None,
        language: Optional[str] = None,
        current_location_id: Optional[int] = None,
        attributes_json_str: Optional[str] = None
    ):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        guild_id = interaction.guild_id # Store for consistent use

        if guild_id is None:
            async with get_db_session() as temp_session: # Session for localization
                error_msg = await get_localized_message_template(
                    temp_session, None, "common:error_guild_only_command", lang_code, # Pass None for guild_id
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        async with get_db_session() as session:
            # Use the new utility for parsing JSON
            from src.bot.utils import parse_json_parameter # Import utility

            parsed_attributes = await parse_json_parameter(
                interaction=interaction,
                json_str=attributes_json_str,
                field_name="attributes_json_str",
                session=session
            )
            if parsed_attributes is None and attributes_json_str is not None: # Error occurred during parsing
                return # parse_json_parameter already sent the error message

            # Check for existing player
            existing_player = await player_crud.get_by_discord_id(session, guild_id=guild_id, discord_id=discord_user.id)
            if existing_player:
                error_msg = await get_localized_message_template(
                    session, guild_id, "player_create:error_discord_id_exists", lang_code,
                    "A player for Discord user <@{discord_id}> (ID: {discord_id_val}) already exists in this guild (Player ID: {player_db_id})."
                ) # type: ignore
                await interaction.followup.send(error_msg.format(discord_id=discord_user.id, discord_id_val=discord_user.id, player_db_id=existing_player.id), ephemeral=True)
                return

            # Use create_with_defaults to leverage default attribute initialization
            # Then, override specific fields if they are provided.
            try:
                # Ensure current_location_id is valid if provided (optional check, depends on strictness)
                # For now, assuming it's either valid or None

                new_player = await player_crud.create_with_defaults(
                    session,
                    guild_id=interaction.guild_id,
                    discord_id=discord_user.id,
                    name=player_name,
                    current_location_id=current_location_id,
                    selected_language=language or discord_user.locale.value # Fallback to user's discord locale
                )

                update_data_for_override: Dict[str, Any] = {}
                if level is not None: update_data_for_override["level"] = level
                if xp is not None: update_data_for_override["xp"] = xp
                if unspent_xp is not None: update_data_for_override["unspent_xp"] = unspent_xp
                if gold is not None: update_data_for_override["gold"] = gold
                if current_hp is not None: update_data_for_override["current_hp"] = current_hp
                # language is handled by create_with_defaults or user's locale
                # current_location_id is handled by create_with_defaults

                if parsed_attributes is not None: # Override attributes if provided
                    update_data_for_override["attributes_json"] = parsed_attributes

                if update_data_for_override:
                    async with session.begin_nested(): # Use nested transaction for the update part
                        new_player = await update_entity(session, entity=new_player, data=update_data_for_override)
                        if new_player: # Should always be true if update_entity succeeds
                             await session.refresh(new_player)

                await session.commit() # Commit the main transaction (create + optional update)

            except Exception as e:
                logger.error(f"Error creating player for {discord_user.id} in guild {interaction.guild_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "player_create:error_generic_create", lang_code,
                    "An error occurred while creating the player: {error_message}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(error_message=str(e)), ephemeral=True)
                return

            if not new_player: # Should not happen if commit was successful
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "player_create:error_creation_failed_unknown", lang_code,
                    "Player creation failed for an unknown reason after commit attempt."
                ) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "player_create:success_title", lang_code,
                "Player Created: {player_name} (ID: {player_id})"
            ) # type: ignore
            embed = discord.Embed(title=success_title_template.format(player_name=new_player.name, player_id=new_player.id), color=discord.Color.green())

            async def get_created_label(key: str, default: str) -> str: # Using a different name to avoid conflict if used in same scope
                return await get_localized_message_template(session, interaction.guild_id, f"player_create:label_{key}", lang_code, default) # type: ignore

            embed.add_field(name=await get_created_label("discord_user", "Discord User"), value=f"<@{new_player.discord_id}> ({new_player.discord_id})", inline=True)
            embed.add_field(name=await get_created_label("level", "Level"), value=str(new_player.level), inline=True)
            embed.add_field(name=await get_created_label("xp", "XP"), value=str(new_player.xp), inline=True)
            embed.add_field(name=await get_created_label("gold", "Gold"), value=str(new_player.gold), inline=True)
            if new_player.current_location_id:
                embed.add_field(name=await get_created_label("location_id", "Location ID"), value=str(new_player.current_location_id), inline=True)
            if new_player.selected_language:
                embed.add_field(name=await get_created_label("language", "Language"), value=new_player.selected_language, inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)


    @player_master_cmds.command(name="list", description="List players in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of players per page.")
    async def player_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale) # For potential error message
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 25: limit = 25 # Max 25 for embeds
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
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
        field_to_update="Field to update (e.g., name, level, xp, gold, current_hp, current_status, language, attributes_json_str).",
        new_value="New value for the field (use JSON for attributes_json_str; PlayerStatus enum name for current_status)."
    )
    async def player_update(self, interaction: discord.Interaction, player_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale) # For potential error message
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        # Import PlayerStatus locally if not already at top level, or ensure it is.
        from src.models.enums import PlayerStatus # Ensure PlayerStatus is available

        allowed_fields = {
            "name": str,
            "level": int,
            "xp": int,
            "unspent_xp": int,
            "gold": int,
            "current_hp": (int, type(None)),
            "current_status": PlayerStatus, # Will parse from string to enum member
            "language": (str, type(None)), # Allow language to be set to None (or empty string for DB if model implies)
            "current_location_id": (int, type(None)),
            "current_party_id": (int, type(None)),
            "attributes_json": dict, # Will parse from new_value if field_to_update is 'attributes_json_str'
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()
        db_field_name = field_to_update_lower
        if field_to_update_lower == "attributes_json_str": # Map attributes_json_str to attributes_json
            db_field_name = "attributes_json"
        field_type_info = allowed_fields.get(db_field_name)


        if not field_type_info:
            async with get_db_session() as temp_session_for_error_msg:
                not_allowed_msg = await get_localized_message_template(
                    temp_session_for_error_msg, interaction.guild_id, "player_update:field_not_allowed", lang_code,
                    "Field '{field_name}' is not allowed for update or does not exist. Allowed fields: {allowed_list}"
                ) # type: ignore
            # Show user-friendly field names (e.g., attributes_json_str instead of attributes_json)
            user_friendly_allowed_keys = [k if k != "attributes_json" else "attributes_json_str" for k in allowed_fields.keys()]
            await interaction.followup.send(not_allowed_msg.format(field_name=field_to_update, allowed_list=', '.join(user_friendly_allowed_keys)), ephemeral=True)
            return

        parsed_value: Any = None
        try:
            is_optional_field = isinstance(field_type_info, tuple) and type(None) in field_type_info

            if new_value.lower() == 'none' or new_value.lower() == 'null':
                if is_optional_field:
                    parsed_value = None
                else:
                    error_detail_template = await get_localized_message_template(session, interaction.guild_id, "player_update:error_detail_cannot_be_none", lang_code, "Field '{field_name}' cannot be set to None/null.") # type: ignore
                    raise ValueError(error_detail_template.format(field_name=db_field_name))
            elif field_type_info == str:
                parsed_value = new_value
            elif field_type_info == int or (isinstance(field_type_info, tuple) and int in field_type_info): # Handles int and Optional[int]
                parsed_value = int(new_value) # Can raise ValueError
            elif field_type_info == PlayerStatus:
                try:
                    parsed_value = PlayerStatus[new_value.upper()]
                except KeyError:
                    valid_statuses = ", ".join([s.name for s in PlayerStatus])
                    error_detail_template = await get_localized_message_template(session, interaction.guild_id, "player_update:error_detail_invalid_status", lang_code, "Invalid PlayerStatus. Use one of: {valid_options}") # type: ignore
                    raise ValueError(error_detail_template.format(valid_options=valid_statuses))
            elif field_type_info == dict: # For attributes_json
                if db_field_name == "attributes_json":
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict):
                        error_detail_template = await get_localized_message_template(session, interaction.guild_id, "player_update:error_detail_attributes_not_object", lang_code, "attributes_json must be a valid JSON object string.") # type: ignore
                        raise ValueError(error_detail_template)
                else:
                    error_detail_template = await get_localized_message_template(session, interaction.guild_id, "player_update:error_detail_internal_json_mismatch", lang_code, "Internal error: Attempting to parse JSON for a non-JSON field '{field_name}'.") # type: ignore
                    raise ValueError(error_detail_template.format(field_name=db_field_name))
            elif is_optional_field and field_type_info[0] == str :
                 parsed_value = new_value
            else:
                async with get_db_session() as temp_session_for_error_msg: # Should not be reached
                    internal_error_msg = await get_localized_message_template(
                        temp_session_for_error_msg, interaction.guild_id, "player_update:error_type_conversion_not_implemented", lang_code,
                        "Internal error: Type conversion for field '{field_name}' not implemented."
                    ) # type: ignore
                await interaction.followup.send(internal_error_msg.format(field_name=field_to_update), ephemeral=True)
                return
        except (ValueError, json.JSONDecodeError) as e: # Catches int(), PlayerStatus, json.loads errors and explicit ValueErrors
            async with get_db_session() as temp_session_for_error_msg:
                invalid_value_msg = await get_localized_message_template(
                    temp_session_for_error_msg, interaction.guild_id, "player_update:error_invalid_value_for_type", lang_code,
                    "Invalid value '{value}' for field '{field_name}'. Details: {details}"
                ) # type: ignore
            await interaction.followup.send(invalid_value_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True)
            return

        update_data = {db_field_name: parsed_value}

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

            new_value_display_str: str
            if parsed_value is None:
                new_value_display_str = await get_localized_message_template(session, interaction.guild_id, "common:value_none", lang_code, "None") # type: ignore
            elif isinstance(parsed_value, PlayerStatus):
                new_value_display_str = parsed_value.name # Enum name
            elif isinstance(parsed_value, dict): # For attributes_json
                try:
                    new_value_display_str = f"```json\n{json.dumps(parsed_value, indent=2, ensure_ascii=False)[:1000]}\n```"
                    if len(json.dumps(parsed_value, indent=2, ensure_ascii=False)) > 1000:
                        new_value_display_str += "..."
                except TypeError:
                    new_value_display_str = await get_localized_message_template(session, interaction.guild_id, "player_update:error_serialization_new_value", lang_code, "Error displaying new value (non-serializable JSON).") # type: ignore
            else:
                new_value_display_str = str(parsed_value)

            embed.add_field(name=new_value_label, value=new_value_display_str, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @player_master_cmds.command(name="delete", description="Delete a player from this guild.")
    @app_commands.describe(player_id="The database ID of the player to delete.")
    async def player_delete(self, interaction: discord.Interaction, player_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale) # For potential error message
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        # lang_code = str(interaction.locale) # Already defined
        async with get_db_session() as session:
            player_to_delete = await player_crud.get_by_id_and_guild(session, id=player_id, guild_id=interaction.guild_id)

            if not player_to_delete:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "player_delete:error_not_found", lang_code,
                    "Player with ID {player_id} not found in this guild. Nothing to delete."
                ) # type: ignore
                await interaction.followup.send(error_msg.format(player_id=player_id), ephemeral=True)
                return

            player_name_for_message = player_to_delete.name
            party_id_of_player = player_to_delete.current_party_id

            try:
                async with session.begin():
                    # Handle party leadership and membership
                    if party_id_of_player:
                        from src.core.crud.crud_party import party_crud # Local import to avoid circular dependency at module level
                        party = await party_crud.get(session, id=party_id_of_player, guild_id=interaction.guild_id)
                        if party:
                            new_player_ids = [pid for pid in (party.player_ids_json or []) if pid != player_id]
                            party_update_data = {"player_ids_json": new_player_ids}
                            if party.leader_player_id == player_id:
                                party_update_data["leader_player_id"] = None # Or assign to another member if logic exists
                                # If new_player_ids is empty after removing this player, party could be marked for deletion or handled by game logic.
                                # For now, just nullify leader if it's the deleted player.

                            await update_entity(session, entity=party, data=party_update_data)
                            # Player's current_party_id will be implicitly nullified by FK on player table if party is deleted,
                            # or should be handled by player deletion if party remains.
                            # Since player is being deleted, their current_party_id becomes irrelevant.

                    # player_crud.delete should handle cascades defined in the model (quest_progress, inventory_items)
                    deleted_player = await player_crud.delete(session, id=player_id, guild_id=interaction.guild_id)

                # No need to commit here as session.begin() handles it or CRUDBase.delete handles it.
                # If CRUDBase.delete doesn't commit, then session.commit() would be needed here.
                # Assuming CRUDBase.delete commits or the outer session.begin() handles it.

                if deleted_player:
                    success_msg = await get_localized_message_template(
                        session, interaction.guild_id, "player_delete:success", lang_code,
                        "Player '{player_name}' (ID: {player_id}) has been deleted successfully."
                    ) # type: ignore
                    await interaction.followup.send(success_msg.format(player_name=player_name_for_message, player_id=player_id), ephemeral=True)
                else: # Should not happen if found before and no exception
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "player_delete:error_not_deleted_unknown", lang_code,
                        "Player (ID: {player_id}) was found but could not be deleted for an unknown reason."
                    ) # type: ignore
                    await interaction.followup.send(error_msg.format(player_id=player_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting player {player_id} for guild {interaction.guild_id}: {e}", exc_info=True)
                # Rollback is handled by the transactional decorator or session context manager on exception
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "player_delete:error_generic", lang_code,
                    "An error occurred while deleting player '{player_name}' (ID: {player_id}): {error_message}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(player_name=player_name_for_message, player_id=player_id, error_message=str(e)), ephemeral=True)
                return


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
