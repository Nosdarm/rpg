import logging
import json
from typing import Dict, Any, Optional, List

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

from src.core.crud.crud_npc import npc_crud
from src.core.crud.crud_faction import crud_faction # To validate faction_id
from src.core.crud.crud_location import location_crud # To validate location_id
from src.core.database import get_db_session
from src.core.crud_base_definitions import update_entity
from src.core.localization_utils import get_localized_message_template
from src.bot.utils import parse_json_parameter # Import the utility

logger = logging.getLogger(__name__)

class MasterNpcCog(commands.Cog, name="Master NPC Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterNpcCog initialized.")

    npc_master_cmds = app_commands.Group(
        name="master_npc",
        description="Master commands for managing Generated NPCs.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    @npc_master_cmds.command(name="view", description="View details of a specific Generated NPC.")
    @app_commands.describe(npc_id="The database ID of the NPC to view.")
    async def npc_view(self, interaction: discord.Interaction, npc_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            npc = await npc_crud.get(session, id=npc_id, guild_id=interaction.guild_id)

            if not npc:
                not_found_msg_template = await get_localized_message_template(session, interaction.guild_id, "npc_view:not_found", lang_code, "NPC with ID {npc_id} not found in this guild.")
                await interaction.followup.send(not_found_msg_template.format(npc_id=npc_id), ephemeral=True); return

            title_template = await get_localized_message_template(session, interaction.guild_id, "npc_view:title", lang_code, "NPC Details: {npc_name} (ID: {npc_id})")
            npc_name_display = npc.name_i18n.get(lang_code, npc.name_i18n.get("en", f"NPC {npc.id}"))
            embed_title = title_template.format(npc_name=npc_name_display, npc_id=npc.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.blurple())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"npc_view:label_{key}", lang_code, default)

            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(npc.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=npc.static_id or na_value_str, inline=True)
            embed.add_field(name=await get_label("faction_id", "Faction ID"), value=str(npc.faction_id) if hasattr(npc, 'faction_id') and npc.faction_id else na_value_str, inline=True)
            embed.add_field(name=await get_label("location_id", "Location ID"), value=str(npc.current_location_id) if npc.current_location_id else na_value_str, inline=True)

            async def format_json_field_helper(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str_val = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data: return na_str_val
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

            name_i18n_str = await format_json_field_helper(npc.name_i18n, "npc_view:value_na_json", "npc_view:error_serialization")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```", inline=False)
            description_i18n_str = await format_json_field_helper(npc.description_i18n, "npc_view:value_na_json", "npc_view:error_serialization")
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{description_i18n_str[:1000]}\n```", inline=False)
            properties_str = await format_json_field_helper(npc.properties_json, "npc_view:value_na_json", "npc_view:error_serialization")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{properties_str[:1000]}\n```", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @npc_master_cmds.command(name="list", description="List Generated NPCs in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of NPCs per page.")
    async def npc_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            offset = (page - 1) * limit
            npcs = await npc_crud.get_multi(session, guild_id=interaction.guild_id, skip=offset, limit=limit)
            total_npcs = await npc_crud.get_count_by_guild(session, guild_id=interaction.guild_id) # type: ignore

            if not npcs:
                no_npcs_msg = await get_localized_message_template(session, interaction.guild_id, "npc_list:no_npcs_found_page", lang_code, "No NPCs found for this guild (Page {page}).")
                await interaction.followup.send(no_npcs_msg.format(page=page), ephemeral=True); return

            title_template = await get_localized_message_template(session, interaction.guild_id, "npc_list:title", lang_code, "Generated NPC List (Page {page} of {total_pages})")
            total_pages = ((total_npcs - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.light_grey())
            footer_template = await get_localized_message_template(session, interaction.guild_id, "npc_list:footer", lang_code, "Displaying {count} of {total} total NPCs.")
            embed.set_footer(text=footer_template.format(count=len(npcs), total=total_npcs))

            field_name_template = await get_localized_message_template(session, interaction.guild_id, "npc_list:npc_field_name", lang_code, "ID: {npc_id} | {npc_name} (Static: {static_id})")
            field_value_template = await get_localized_message_template(session, interaction.guild_id, "npc_list:npc_field_value", lang_code, "Faction ID: {faction_id}, Location ID: {location_id}")

            for n in npcs:
                na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")
                npc_name_display = n.name_i18n.get(lang_code, n.name_i18n.get("en", f"NPC {n.id}"))
                embed.add_field(
                    name=field_name_template.format(npc_id=n.id, npc_name=npc_name_display, static_id=n.static_id or na_value_str),
                    value=field_value_template.format(faction_id=str(n.faction_id) if n.faction_id else na_value_str, location_id=str(n.current_location_id) if n.current_location_id else na_value_str),
                    inline=False
                )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @npc_master_cmds.command(name="create", description="Create a new Generated NPC in this guild.")
    @app_commands.describe(
        static_id="Optional: Static ID for this NPC.",
        name_i18n_json="JSON string for NPC name (e.g., {\"en\": \"Guard\", \"ru\": \"Стражник\"}).",
        description_i18n_json="Optional: JSON string for NPC description.",
        faction_id="Optional: Database ID of the faction this NPC belongs to.",
        current_location_id="Optional: Database ID of the NPC's current location.",
        properties_json="Optional: JSON string for additional NPC properties (e.g., stats, role)."
    )
    async def npc_create(self, interaction: discord.Interaction,
                         name_i18n_json: str,
                         static_id: Optional[str] = None,
                         description_i18n_json: Optional[str] = None,
                         faction_id: Optional[int] = None,
                         current_location_id: Optional[int] = None,
                         properties_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            parsed_name_i18n = await parse_json_parameter(interaction, name_i18n_json, "name_i18n_json", session)
            if parsed_name_i18n is None: return
            error_detail_name_lang = await get_localized_message_template(session, interaction.guild_id, "npc_create:error_detail_name_lang", lang_code, "name_i18n_json must contain at least an 'en' key or a key for the current interaction language.")
            if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code):
                 error_msg = await get_localized_message_template(session,interaction.guild_id,"npc_create:error_invalid_json_content",lang_code,"Invalid JSON content: {details}")
                 await interaction.followup.send(error_msg.format(details=error_detail_name_lang), ephemeral=True); return

            parsed_description_i18n = await parse_json_parameter(interaction, description_i18n_json, "description_i18n_json", session)
            if parsed_description_i18n is None and description_i18n_json is not None: return

            parsed_properties = await parse_json_parameter(interaction, properties_json, "properties_json", session)
            if parsed_properties is None and properties_json is not None: return

            if faction_id:
                existing_faction = await crud_faction.get(session, id=faction_id, guild_id=interaction.guild_id)
                if not existing_faction:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "npc_create:error_faction_not_found", lang_code, "Faction with ID {id} not found in this guild.")
                    await interaction.followup.send(error_msg.format(id=faction_id), ephemeral=True); return
            if current_location_id:
                existing_location = await location_crud.get(session, id=current_location_id, guild_id=interaction.guild_id)
                if not existing_location:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "npc_create:error_location_not_found", lang_code, "Location with ID {id} not found in this guild.")
                    await interaction.followup.send(error_msg.format(id=current_location_id), ephemeral=True); return
            if static_id:
                existing_npc_static = await npc_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=static_id)
                if existing_npc_static:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "npc_create:error_static_id_exists", lang_code, "An NPC with static_id '{id}' already exists in this guild.")
                    await interaction.followup.send(error_msg.format(id=static_id), ephemeral=True); return

            npc_data_to_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id,
                "static_id": static_id,
                "name_i18n": parsed_name_i18n, # Already validated not None
                "description_i18n": parsed_description_i18n or {},
                "faction_id": faction_id,
                "current_location_id": current_location_id,
                "properties_json": parsed_properties or {},
            }
            created_npc: Optional[Any] = None
            try:
                async with session.begin():
                    created_npc = await npc_crud.create(session, obj_in=npc_data_to_create)
                    await session.flush();
                    if created_npc: await session.refresh(created_npc)
            except Exception as e:
                logger.error(f"Error creating NPC: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, interaction.guild_id, "npc_create:error_generic_create", lang_code, "An error occurred while creating the NPC: {error_message}")
                await interaction.followup.send(error_msg.format(error_message=str(e)), ephemeral=True); return

            if not created_npc:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "npc_create:error_creation_failed_unknown", lang_code, "NPC creation failed for an unknown reason.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title_template = await get_localized_message_template(session, interaction.guild_id, "npc_create:success_title", lang_code, "NPC Created: {npc_name} (ID: {npc_id})")
            created_npc_name_display = created_npc.name_i18n.get(lang_code, created_npc.name_i18n.get("en", f"NPC {created_npc.id}"))
            embed = discord.Embed(title=success_title_template.format(npc_name=created_npc_name_display, npc_id=created_npc.id), color=discord.Color.green())
            async def get_created_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"npc_create:label_{key}", lang_code, default)
            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")
            embed.add_field(name=await get_created_label("static_id", "Static ID"), value=created_npc.static_id or na_value_str, inline=True)
            embed.add_field(name=await get_created_label("faction_id", "Faction ID"), value=str(created_npc.faction_id) if hasattr(created_npc, 'faction_id') and created_npc.faction_id else na_value_str, inline=True)
            embed.add_field(name=await get_created_label("location_id", "Location ID"), value=str(created_npc.current_location_id) if created_npc.current_location_id else na_value_str, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @npc_master_cmds.command(name="update", description="Update a specific field for a Generated NPC.")
    @app_commands.describe(
        npc_id="The database ID of the NPC to update.",
        field_to_update="Field to update (e.g., static_id, name_i18n_json, faction_id, current_location_id, properties_json).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable fields)."
    )
    async def npc_update(self, interaction: discord.Interaction, npc_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        allowed_fields = {
            "static_id": (str, type(None)),
            "name_i18n": dict,
            "description_i18n": dict,
            "faction_id": (int, type(None)),
            "current_location_id": (int, type(None)),
            "properties_json": dict,
        }

        field_to_update_lower = field_to_update.lower()
        db_field_name = field_to_update_lower
        user_facing_field_name = field_to_update_lower

        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")
        elif field_to_update_lower == "name_i18n_json":
            db_field_name = "name_i18n"
            user_facing_field_name = "name_i18n_json"
        elif field_to_update_lower == "description_i18n_json":
            db_field_name = "description_i18n"
            user_facing_field_name = "description_i18n_json"

        field_type = allowed_fields.get(db_field_name)

        if not field_type:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "npc_update:error_field_not_allowed", lang_code, "Field '{field_name}' is not allowed for update. Allowed: {allowed_list}")
            await interaction.followup.send(error_msg.format(field_name=field_to_update, allowed_list=', '.join(allowed_fields.keys())), ephemeral=True); return

        parsed_value: Any = None
        async with get_db_session() as session:
            npc_to_update = await npc_crud.get(session, id=npc_id, guild_id=interaction.guild_id)
            if not npc_to_update:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "npc_update:error_npc_not_found", lang_code, "NPC with ID {id} not found in this guild.")
                await interaction.followup.send(error_msg.format(id=npc_id), ephemeral=True); return
            try:
                error_detail_static_id_exists_template = await get_localized_message_template(session, interaction.guild_id, "npc_update:error_detail_static_id_exists", lang_code, "Another NPC with static_id '{id}' already exists.")
                error_detail_faction_not_found_template = await get_localized_message_template(session, interaction.guild_id, "npc_update:error_detail_faction_not_found", lang_code, "Faction with ID {id} not found.")
                error_detail_location_not_found_template = await get_localized_message_template(session, interaction.guild_id, "npc_update:error_detail_location_not_found", lang_code, "Location with ID {id} not found.")
                error_detail_unknown_field_template = await get_localized_message_template(session, interaction.guild_id, "npc_update:error_detail_unknown_field_type", lang_code, "Internal error: Unknown field type for '{field_name}'.")

                if db_field_name == "static_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = new_value
                        if parsed_value is not None and parsed_value != "" and parsed_value != npc_to_update.static_id:
                            existing_npc_static = await npc_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                            if existing_npc_static and existing_npc_static.id != npc_id:
                                raise ValueError(error_detail_static_id_exists_template.format(id=parsed_value))
                elif db_field_name in ["name_i18n", "description_i18n", "properties_json"]:
                    parsed_value = await parse_json_parameter(interaction, new_value, user_facing_field_name, session)
                    if parsed_value is None and new_value is not None : return
                elif db_field_name == "faction_id" or db_field_name == "current_location_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = int(new_value)
                        if parsed_value is not None:
                            if db_field_name == "faction_id" and not await crud_faction.get(session, id=parsed_value, guild_id=interaction.guild_id):
                                raise ValueError(error_detail_faction_not_found_template.format(id=parsed_value))
                            if db_field_name == "current_location_id" and not await location_crud.get(session, id=parsed_value, guild_id=interaction.guild_id):
                                raise ValueError(error_detail_location_not_found_template.format(id=parsed_value))
                else:
                     raise ValueError(error_detail_unknown_field_template.format(field_name=db_field_name))
            except ValueError as e:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "npc_update:error_invalid_value_type", lang_code, "Invalid value '{value}' for field '{field_name}'. Details: {details}")
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True); return

            update_data_dict = {db_field_name: parsed_value}
            updated_npc: Optional[Any] = None
            try:
                async with session.begin():
                    updated_npc = await update_entity(session, entity=npc_to_update, data=update_data_dict)
                    await session.flush()
                    if updated_npc:
                        await session.refresh(updated_npc)
            except Exception as e:
                logger.error(f"Error updating NPC {npc_id} with data {update_data_dict}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, interaction.guild_id, "npc_update:error_generic_update", lang_code, "An error occurred while updating NPC {id}: {error_message}")
                await interaction.followup.send(error_msg.format(id=npc_id, error_message=str(e)), ephemeral=True); return

            if not updated_npc:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "npc_update:error_update_failed_unknown", lang_code, "NPC update failed for an unknown reason.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title_template = await get_localized_message_template(session, interaction.guild_id, "npc_update:success_title", lang_code, "NPC Updated: {npc_name} (ID: {npc_id})")
            updated_npc_name_display = updated_npc.name_i18n.get(lang_code, updated_npc.name_i18n.get("en", f"NPC {updated_npc.id}"))
            embed = discord.Embed(title=success_title_template.format(npc_name=updated_npc_name_display, npc_id=updated_npc.id), color=discord.Color.orange())

            field_updated_label = await get_localized_message_template(session, interaction.guild_id, "npc_update:label_field_updated", lang_code, "Field Updated")
            new_value_label = await get_localized_message_template(session, interaction.guild_id, "npc_update:label_new_value", lang_code, "New Value")

            new_value_display_str: str
            if parsed_value is None:
                new_value_display_str = await get_localized_message_template(session, interaction.guild_id, "common:value_none", lang_code, "None")
            elif isinstance(parsed_value, (dict, list)):
                try:
                    json_str = json.dumps(parsed_value, indent=2, ensure_ascii=False)
                    new_value_display_str = f"```json\n{json_str[:1000]}\n```"
                    if len(json_str) > 1000: new_value_display_str += "..."
                except TypeError:
                    new_value_display_str = await get_localized_message_template(session, interaction.guild_id, "npc_update:error_serialization_new_value", lang_code, "Error displaying new value (non-serializable JSON).")
            else:
                new_value_display_str = str(parsed_value)

            embed.add_field(name=field_updated_label, value=field_to_update, inline=True)
            embed.add_field(name=new_value_label, value=new_value_display_str, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @npc_master_cmds.command(name="delete", description="Delete a Generated NPC from this guild.")
    @app_commands.describe(npc_id="The database ID of the NPC to delete.")
    async def npc_delete(self, interaction: discord.Interaction, npc_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            npc_to_delete = await npc_crud.get(session, id=npc_id, guild_id=interaction.guild_id)
            if not npc_to_delete:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "npc_delete:error_not_found", lang_code, "NPC with ID {id} not found. Nothing to delete.")
                await interaction.followup.send(error_msg.format(id=npc_id), ephemeral=True); return

            npc_name_for_message = npc_to_delete.name_i18n.get(lang_code, npc_to_delete.name_i18n.get("en", f"NPC {npc_to_delete.id}"))
            deleted_npc: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_npc = await npc_crud.delete(session, id=npc_id, guild_id=interaction.guild_id)
                if deleted_npc:
                    success_msg = await get_localized_message_template(session, interaction.guild_id, "npc_delete:success", lang_code, "NPC '{name}' (ID: {id}) has been deleted successfully.")
                    await interaction.followup.send(success_msg.format(name=npc_name_for_message, id=npc_id), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "npc_delete:error_not_deleted_unknown", lang_code, "NPC (ID: {id}) was found but could not be deleted.")
                    await interaction.followup.send(error_msg.format(id=npc_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting NPC {npc_id} for guild {interaction.guild_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, interaction.guild_id, "npc_delete:error_generic", lang_code, "An error occurred while deleting NPC '{name}' (ID: {id}): {error_message}")
                await interaction.followup.send(error_msg.format(name=npc_name_for_message, id=npc_id, error_message=str(e)), ephemeral=True); return

async def setup(bot: commands.Bot):
    cog = MasterNpcCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterNpcCog loaded.")
