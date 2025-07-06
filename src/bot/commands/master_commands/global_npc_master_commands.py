import logging
import json
from typing import Dict, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

from src.core.crud.crud_global_npc import global_npc_crud
from src.core.crud.crud_npc import npc_crud # To validate template_id
from src.core.crud.crud_location import location_crud # To validate location_id
from src.core.crud.crud_mobile_group import mobile_group_crud # To validate group_id
from src.core.database import get_db_session
from src.core.crud_base_definitions import update_entity
from src.core.localization_utils import get_localized_message_template

logger = logging.getLogger(__name__)

class MasterGlobalNpcCog(commands.Cog, name="Master Global NPC Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterGlobalNpcCog initialized.")

    global_npc_master_cmds = app_commands.Group(
        name="master_global_npc",
        description="Master commands for managing Global NPCs.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    @global_npc_master_cmds.command(name="view", description="View details of a specific Global NPC.")
    @app_commands.describe(global_npc_id="The database ID of the Global NPC to view.")
    async def global_npc_view(self, interaction: discord.Interaction, global_npc_id: int):
        await interaction.response.defer(ephemeral=True)

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

            async def format_json_field_helper(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(gnpc.guild_id), inline=True)
            embed.add_field(name=await get_label("npc_template_id", "NPC Template ID"), value=str(gnpc.npc_template_id) if gnpc.npc_template_id else "N/A", inline=True)
            embed.add_field(name=await get_label("current_location_id", "Current Location ID"), value=str(gnpc.current_location_id) if gnpc.current_location_id else "N/A", inline=True)
            embed.add_field(name=await get_label("current_hp", "Current HP"), value=str(gnpc.current_hp) if gnpc.current_hp is not None else "N/A", inline=True)
            embed.add_field(name=await get_label("mobile_group_id", "Mobile Group ID"), value=str(gnpc.mobile_group_id) if gnpc.mobile_group_id else "N/A", inline=True)

            name_i18n_str = await format_json_field_helper(gnpc.name_i18n, "global_npc_view:value_na_json", "global_npc_view:error_serialization_name")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```" + ("..." if len(name_i18n_str) > 1000 else ""), inline=False)

            route_str = await format_json_field_helper(gnpc.route_json, "global_npc_view:value_na_json", "global_npc_view:error_serialization_route")
            embed.add_field(name=await get_label("route_json", "Route JSON"), value=f"```json\n{route_str[:1000]}\n```" + ("..." if len(route_str) > 1000 else ""), inline=False)

            properties_str = await format_json_field_helper(gnpc.properties_json, "global_npc_view:value_na_json", "global_npc_view:error_serialization_properties")
            embed.add_field(name=await get_label("properties_json", "Properties JSON"), value=f"```json\n{properties_str[:1000]}\n```" + ("..." if len(properties_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @global_npc_master_cmds.command(name="list", description="List Global NPCs in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of Global NPCs per page.")
    async def global_npc_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            offset = (page - 1) * limit
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
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_magenta())

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

            for gnpc_obj in gnpcs:
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

    @global_npc_master_cmds.command(name="create", description="Create a new Global NPC.")
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

            created_gnpc: Optional[Any] = None
            try:
                async with session.begin():
                    created_gnpc = await global_npc_crud.create(session, obj_in=gnpc_data_create)
                    await session.flush();
                    if created_gnpc: await session.refresh(created_gnpc)
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

    @global_npc_master_cmds.command(name="update", description="Update a specific field for a Global NPC.")
    @app_commands.describe(
        global_npc_id="The database ID of the Global NPC to update.",
        field_to_update="Field to update (e.g., name_i18n_json, current_location_id, current_hp, mobile_group_id, route_json, properties_json).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable)."
    )
    async def global_npc_update(self, interaction: discord.Interaction, global_npc_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)

        allowed_fields = {
            "name_i18n": dict, # from name_i18n_json
            "current_location_id": (int, type(None)),
            "current_hp": (int, type(None)),
            "mobile_group_id": (int, type(None)),
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
                        if db_field_name == "current_location_id" and parsed_value is not None:
                            if not await location_crud.get_by_id_and_guild(session, id=parsed_value, guild_id=interaction.guild_id):
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_loc_not_found",lang_code,"Location ID {id} not found.")
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                        elif db_field_name == "mobile_group_id" and parsed_value is not None:
                             if not await mobile_group_crud.get_by_id_and_guild(session, id=parsed_value, guild_id=interaction.guild_id):
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_group_not_found",lang_code,"Mobile Group ID {id} not found.")
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                else:
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
            updated_gnpc: Optional[Any] = None
            try:
                async with session.begin():
                    updated_gnpc = await update_entity(session, entity=gnpc_to_update, data=update_data)
                    await session.flush();
                    if updated_gnpc: await session.refresh(updated_gnpc)
            except Exception as e:
                logger.error(f"Error updating Global NPC {global_npc_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_generic_update",lang_code,"Error updating Global NPC {id}: {err}")
                await interaction.followup.send(error_msg.format(id=global_npc_id, err=str(e)), ephemeral=True); return

            if not updated_gnpc:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_unknown_update_fail",lang_code,"Global NPC update failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:success",lang_code,"Global NPC ID {id} updated. Field '{f}' set to '{v}'.")
            new_val_display = str(parsed_value)
            if isinstance(parsed_value, dict): new_val_display = json.dumps(parsed_value)
            elif parsed_value is None: new_val_display = "None"
            await interaction.followup.send(success_msg.format(id=updated_gnpc.id, f=field_to_update, v=new_val_display), ephemeral=True)

    @global_npc_master_cmds.command(name="delete", description="Delete a Global NPC.")
    @app_commands.describe(global_npc_id="The database ID of the Global NPC to delete.")
    async def global_npc_delete(self, interaction: discord.Interaction, global_npc_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        async with get_db_session() as session:
            gnpc_to_delete = await global_npc_crud.get_by_id_and_guild(session, id=global_npc_id, guild_id=interaction.guild_id)

            if not gnpc_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_delete:error_not_found",lang_code,"Global NPC ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=global_npc_id), ephemeral=True); return

            gnpc_name_for_msg = gnpc_to_delete.name_i18n.get(lang_code, gnpc_to_delete.name_i18n.get("en", f"Global NPC {global_npc_id}"))
            deleted_gnpc: Optional[Any] = None
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

async def setup(bot: commands.Bot):
    cog = MasterGlobalNpcCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterGlobalNpcCog loaded.")
