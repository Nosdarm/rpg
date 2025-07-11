import logging
import json
from typing import Optional, Dict, Any, Union, List # Added Union, List

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

from backend.core.crud.crud_global_npc import global_npc_crud
from backend.core.crud.crud_npc import npc_crud # To validate template_id
from backend.core.crud.crud_location import location_crud # To validate location_id
from backend.core.crud.crud_mobile_group import mobile_group_crud # To validate group_id
from backend.core.database import get_db_session
from backend.core.crud_base_definitions import update_entity
from backend.core.localization_utils import get_localized_message_template
from backend.bot.utils import parse_json_parameter # Import the utility

logger = logging.getLogger(__name__)

class MasterGlobalNpcCog(commands.Cog, name="Master Global NPC Commands"): # type: ignore[call-arg]
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterGlobalNpcCog initialized.")

    global_npc_master_cmds = app_commands.Group(
        name="master_global_npc",
        description="Master commands for managing Global NPCs.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    async def _format_json_field_display(self, interaction: discord.Interaction, data: Optional[Union[Dict[Any, Any], List[Any]]], lang_code: str) -> str:
        # Simplified helper for display, not using default_na_key/error_key from view directly to avoid session issues
        # Fallback to basic strings if localization fails or not in session context of this helper
        na_str = "Not available"
        error_str = "Error serializing JSON"
        try:
            async with get_db_session() as temp_session: # Temporary session for this self-contained helper
                na_str = await get_localized_message_template(temp_session, interaction.guild_id, "common:value_na_json", lang_code, "Not available")
                error_str = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_serialization", lang_code, "Error serializing JSON")
        except Exception:
            pass # Use hardcoded fallbacks

        if not data: return na_str
        try: return json.dumps(data, indent=2, ensure_ascii=False)
        except TypeError: return error_str


    @global_npc_master_cmds.command(name="view", description="View details of a specific Global NPC.")
    @app_commands.describe(global_npc_id="The database ID of the Global NPC to view.")
    async def global_npc_view(self, interaction: discord.Interaction, global_npc_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            gnpc = await global_npc_crud.get(session, id=global_npc_id, guild_id=interaction.guild_id)

            if not gnpc:
                not_found_msg = await get_localized_message_template(session, interaction.guild_id, "global_npc_view:not_found", lang_code, "Global NPC with ID {id} not found in this guild.")
                await interaction.followup.send(not_found_msg.format(id=global_npc_id), ephemeral=True); return

            title_template = await get_localized_message_template(session, interaction.guild_id, "global_npc_view:title", lang_code, "Global NPC Details: {name} (ID: {id})")
            gnpc_name_display = gnpc.name_i18n.get(lang_code, gnpc.name_i18n.get("en", f"Global NPC {gnpc.id}"))
            embed_title = title_template.format(name=gnpc_name_display, id=gnpc.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.fuchsia())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"global_npc_view:label_{key}", lang_code, default)

            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(gnpc.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=gnpc.static_id or na_value_str, inline=True)
            embed.add_field(name=await get_label("base_npc_id", "Base NPC ID (Template)"), value=str(gnpc.base_npc_id) if gnpc.base_npc_id else na_value_str, inline=True)
            embed.add_field(name=await get_label("current_location_id", "Current Location ID"), value=str(gnpc.current_location_id) if gnpc.current_location_id else na_value_str, inline=True)
            current_hp_val = getattr(gnpc, 'current_hp', None) # Assuming current_hp is in properties_json
            if current_hp_val is None and gnpc.properties_json: current_hp_val = gnpc.properties_json.get("current_hp")
            embed.add_field(name=await get_label("current_hp", "Current HP"), value=str(current_hp_val) if current_hp_val is not None else na_value_str, inline=True)
            mobile_group_id_val = getattr(gnpc, 'mobile_group_id', None)
            embed.add_field(name=await get_label("mobile_group_id", "Mobile Group ID"), value=str(mobile_group_id_val) if mobile_group_id_val else na_value_str, inline=True)

            name_i18n_str = await self._format_json_field_display(interaction, gnpc.name_i18n, lang_code)
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```", inline=False)

            desc_i18n_str = await self._format_json_field_display(interaction, gnpc.description_i18n, lang_code)
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```", inline=False)

            route_data = gnpc.properties_json.get("route") if gnpc.properties_json else None
            route_str = await self._format_json_field_display(interaction, route_data, lang_code)
            embed.add_field(name=await get_label("route_json", "Route JSON (from Properties)"), value=f"```json\n{route_str[:1000]}\n```", inline=False)

            properties_str = await self._format_json_field_display(interaction, gnpc.properties_json, lang_code)
            embed.add_field(name=await get_label("properties_json", "Properties JSON"), value=f"```json\n{properties_str[:1000]}\n```", inline=False)

            ai_meta_str = await self._format_json_field_display(interaction, gnpc.ai_metadata_json, lang_code) # type: ignore[attr-defined]
            embed.add_field(name=await get_label("ai_metadata_json", "AI Metadata JSON"), value=f"```json\n{ai_meta_str[:1000]}\n```", inline=False)


            await interaction.followup.send(embed=embed, ephemeral=True)

    @global_npc_master_cmds.command(name="list", description="List Global NPCs in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of Global NPCs per page.")
    async def global_npc_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
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
            gnpcs = await global_npc_crud.get_multi(session, guild_id=interaction.guild_id, skip=offset, limit=limit)
            total_global_npcs = await global_npc_crud.get_count_by_guild(session, guild_id=interaction.guild_id) # type: ignore

            if not gnpcs:
                no_gnpcs_msg = await get_localized_message_template(session, interaction.guild_id, "global_npc_list:no_gnpcs_found_page", lang_code, "No Global NPCs found for this guild (Page {page}).")
                await interaction.followup.send(no_gnpcs_msg.format(page=page), ephemeral=True); return

            title_template = await get_localized_message_template(session, interaction.guild_id, "global_npc_list:title", lang_code, "Global NPC List (Page {page} of {total_pages})")
            total_pages = ((total_global_npcs - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_magenta())
            footer_template = await get_localized_message_template(session, interaction.guild_id, "global_npc_list:footer", lang_code, "Displaying {count} of {total} total Global NPCs.")
            embed.set_footer(text=footer_template.format(count=len(gnpcs), total=total_global_npcs))

            field_name_template = await get_localized_message_template(session, interaction.guild_id, "global_npc_list:gnpc_field_name", lang_code, "ID: {id} | Static: {sid} | {name}")
            field_value_template = await get_localized_message_template(session, interaction.guild_id, "global_npc_list:gnpc_field_value", lang_code, "Location ID: {loc_id}, Group ID: {group_id}")

            for gnpc_obj in gnpcs:
                na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")
                gnpc_name_display = gnpc_obj.name_i18n.get(lang_code, gnpc_obj.name_i18n.get("en", f"Global NPC {gnpc_obj.id}"))
                mobile_group_id_val = getattr(gnpc_obj, 'mobile_group_id', None)
                embed.add_field(
                    name=field_name_template.format(id=gnpc_obj.id, sid=gnpc_obj.static_id or na_value_str, name=gnpc_name_display),
                    value=field_value_template.format(
                        loc_id=str(gnpc_obj.current_location_id) if gnpc_obj.current_location_id else na_value_str,
                        group_id=str(mobile_group_id_val) if mobile_group_id_val else na_value_str
                    ),
                    inline=False
                )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @global_npc_master_cmds.command(name="create", description="Create a new Global NPC.")
    @app_commands.describe(
        static_id="Static ID for this Global NPC (unique within the guild).",
        name_i18n_json="JSON for Global NPC name (e.g., {\"en\": \"Travelling Merchant\"}).",
        description_i18n_json="Optional: JSON for Global NPC description.",
        npc_template_id="Optional: Database ID of a GeneratedNPC to use as a template.",
        current_location_id="Optional: Database ID of the Global NPC's starting location.",
        mobile_group_id="Optional: Database ID of the Mobile Group this NPC belongs to.",
        route_json="Optional: JSON describing the NPC's route or movement behavior (will be stored in properties_json).",
        properties_json="Optional: JSON for additional properties (status, goals, current_hp, etc.).",
        ai_metadata_json="Optional: JSON for AI metadata."
    )
    async def global_npc_create(self, interaction: discord.Interaction,
                                static_id: str,
                                name_i18n_json: str,
                                description_i18n_json: Optional[str] = None,
                                npc_template_id: Optional[int] = None,
                                current_location_id: Optional[int] = None,
                                mobile_group_id: Optional[int] = None,
                                route_json: Optional[str] = None,
                                properties_json: Optional[str] = None,
                                ai_metadata_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            parsed_name_i18n = await parse_json_parameter(interaction, name_i18n_json, "name_i18n_json", session)
            if parsed_name_i18n is None: return
            error_detail_name_lang = await get_localized_message_template(session, interaction.guild_id, "gnpc_create:error_detail_name_lang", lang_code, "name_i18n_json must contain 'en' or current language key.")
            if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code):
                 error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_create:error_invalid_json_content",lang_code,"Invalid JSON content: {details}")
                 await interaction.followup.send(error_msg.format(details=error_detail_name_lang), ephemeral=True); return

            parsed_desc_i18n = await parse_json_parameter(interaction, description_i18n_json, "description_i18n_json", session)
            if parsed_desc_i18n is None and description_i18n_json is not None: return
            parsed_route = await parse_json_parameter(interaction, route_json, "route_json", session)
            if parsed_route is None and route_json is not None: return
            parsed_props = await parse_json_parameter(interaction, properties_json, "properties_json", session)
            if parsed_props is None and properties_json is not None: return
            parsed_ai_meta = await parse_json_parameter(interaction, ai_metadata_json, "ai_metadata_json", session)
            if parsed_ai_meta is None and ai_metadata_json is not None: return

            if await global_npc_crud.get_by_attribute(session, attribute="static_id", value=static_id, guild_id=interaction.guild_id):
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_create:error_static_id_exists",lang_code,"Global NPC with static_id '{id}' already exists.")
                await interaction.followup.send(error_msg.format(id=static_id), ephemeral=True); return
            if npc_template_id and not await npc_crud.get(session, id=npc_template_id, guild_id=interaction.guild_id):
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_create:error_template_not_found",lang_code,"NPC Template ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=npc_template_id), ephemeral=True); return
            if current_location_id and not await location_crud.get(session, id=current_location_id, guild_id=interaction.guild_id):
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_create:error_location_not_found",lang_code,"Location ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=current_location_id), ephemeral=True); return
            if mobile_group_id and not await mobile_group_crud.get(session, id=mobile_group_id, guild_id=interaction.guild_id):
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_create:error_group_not_found",lang_code,"Mobile Group ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=mobile_group_id), ephemeral=True); return

            final_properties = parsed_props or {}
            if parsed_route: final_properties["route"] = parsed_route
            # current_hp from properties_json will override separate parameter if both provided
            # current_hp_from_param = final_properties.pop("current_hp", None) # Remove if exists to avoid conflict

            gnpc_data_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id, "static_id": static_id,
                "name_i18n": parsed_name_i18n, "description_i18n": parsed_desc_i18n or {},
                "base_npc_id": npc_template_id, "current_location_id": current_location_id,
                "mobile_group_id": mobile_group_id,
                "properties_json": final_properties, "ai_metadata_json": parsed_ai_meta or {}
            }
            # if current_hp_from_param is not None: # current_hp is not a direct model field anymore
            #     gnpc_data_create["current_hp"] = current_hp_from_param


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
            async def get_created_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"gnpc_create:label_{key}", lang_code, default)
            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")
            embed.add_field(name=await get_created_label("static_id", "Static ID"), value=created_gnpc.static_id, inline=True)
            embed.add_field(name=await get_created_label("location_id", "Location ID"), value=str(created_gnpc.current_location_id) if created_gnpc.current_location_id else na_value_str, inline=True)
            if created_gnpc.mobile_group_id:
                embed.add_field(name=await get_created_label("group_id", "Group ID"), value=str(created_gnpc.mobile_group_id), inline=True)
            if created_gnpc.base_npc_id:
                embed.add_field(name=await get_created_label("template_id", "Template ID"), value=str(created_gnpc.base_npc_id), inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @global_npc_master_cmds.command(name="update", description="Update a specific field for a Global NPC.")
    @app_commands.describe(
        global_npc_id="The database ID of the Global NPC to update.",
        field_to_update="Field to update (e.g., static_id, name_i18n_json, current_location_id, mobile_group_id, route_json, properties_json, ai_metadata_json).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable)."
    )
    async def global_npc_update(self, interaction: discord.Interaction, global_npc_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        allowed_fields = {
            "static_id": str,
            "name_i18n": dict,
            "description_i18n": dict,
            "current_location_id": (int, type(None)),
            # current_hp is managed via properties_json
            "mobile_group_id": (int, type(None)),
            "leader_global_npc_id": (int, type(None)), # Added from model
            "members_definition_json": list, # Added from model
            "behavior_type_i18n": dict, # Added from model
            "route_json": dict, # Stored in properties_json
            "properties_json": dict,
            "ai_metadata_json": dict,
        }

        field_to_update_lower = field_to_update.lower()
        db_field_name = field_to_update_lower
        user_facing_field_name = field_to_update_lower

        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")
        elif field_to_update_lower == "name_i18n_json":
            db_field_name = "name_i18n"
        elif field_to_update_lower == "description_i18n_json":
            db_field_name = "description_i18n"
        elif field_to_update_lower == "behavior_type_i18n_json":
            db_field_name = "behavior_type_i18n"
        elif field_to_update_lower == "ai_metadata_json": # Already matches
            pass


        field_type_info = allowed_fields.get(db_field_name)

        if not field_type_info:
            # Handle if field_to_update is 'route_json' which is part of 'properties_json'
            if field_to_update_lower == "route_json":
                field_type_info = dict # It's a dict within properties_json
            else:
                async with get_db_session() as temp_session:
                    error_msg = await get_localized_message_template(temp_session,interaction.guild_id,"gnpc_update:error_field_not_allowed",lang_code,"Field '{f}' not allowed. Allowed: {l}")
                await interaction.followup.send(error_msg.format(f=field_to_update, l=', '.join(allowed_fields.keys())), ephemeral=True); return

        parsed_value: Any = None
        async with get_db_session() as session:
            gnpc_to_update = await global_npc_crud.get(session, id=global_npc_id, guild_id=interaction.guild_id)
            if not gnpc_to_update:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_not_found",lang_code,"Global NPC ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=global_npc_id), ephemeral=True); return
            try:
                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: raise ValueError("static_id cannot be empty.")
                    if parsed_value != gnpc_to_update.static_id and await global_npc_crud.get_by_attribute(session, attribute="static_id", value=parsed_value, guild_id=interaction.guild_id):
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_static_id_exists",lang_code,"Static ID '{id}' already in use.")
                        await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                elif db_field_name in ["name_i18n", "description_i18n", "behavior_type_i18n", "properties_json", "ai_metadata_json"] or field_to_update_lower == "route_json":
                    # For route_json, user_facing_field_name is "route_json"
                    parsed_value = await parse_json_parameter(interaction, new_value, user_facing_field_name, session)
                    if parsed_value is None: return
                elif db_field_name == "members_definition_json":
                    temp_parsed_list = await parse_json_parameter(interaction, new_value, user_facing_field_name, session)
                    if temp_parsed_list is None: return
                    if not isinstance(temp_parsed_list, list):
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_members_def_not_list",lang_code,"members_definition_json must be a list.")
                        await interaction.followup.send(error_msg, ephemeral=True); return
                    # Further validation of member entries can be added here if needed
                    parsed_value = temp_parsed_list
                elif db_field_name in ["current_location_id", "mobile_group_id", "leader_global_npc_id"]:
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = int(new_value)
                        if parsed_value is not None:
                            if db_field_name == "current_location_id" and not await location_crud.get(session, id=parsed_value, guild_id=interaction.guild_id):
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_detail_loc_not_found",lang_code,"Location ID {id} not found.")
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                            if db_field_name == "mobile_group_id" and not await mobile_group_crud.get(session, id=parsed_value, guild_id=interaction.guild_id):
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_detail_group_not_found",lang_code,"Mobile Group ID {id} not found.")
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                            if db_field_name == "leader_global_npc_id" and not await global_npc_crud.get(session, id=parsed_value, guild_id=interaction.guild_id):
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_detail_leader_gnpc_not_found",lang_code,"Leader GNPC ID {id} not found.")
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_detail_unknown_field",lang_code,"Unknown field for update: {field_name}")
                    await interaction.followup.send(error_msg.format(field_name=db_field_name), ephemeral=True); return
            except (ValueError, json.JSONDecodeError) as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_update:error_invalid_value_data",lang_code,"Invalid value or data for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            update_data = {}
            if field_to_update_lower == "route_json":
                current_properties = dict(gnpc_to_update.properties_json or {})
                current_properties["route"] = parsed_value # parsed_value is already a dict here
                update_data = {"properties_json": current_properties}
            else:
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
            new_val_display_str = await self._format_json_field_display(interaction, parsed_value, lang_code) if isinstance(parsed_value, (dict,list)) else (await get_localized_message_template(session, interaction.guild_id, "common:value_none", lang_code, "None") if parsed_value is None else str(parsed_value))
            await interaction.followup.send(success_msg.format(id=updated_gnpc.id, f=field_to_update, v=new_val_display_str), ephemeral=True)

    @global_npc_master_cmds.command(name="delete", description="Delete a Global NPC.")
    @app_commands.describe(global_npc_id="The database ID of the Global NPC to delete.")
    async def global_npc_delete(self, interaction: discord.Interaction, global_npc_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            gnpc_to_delete = await global_npc_crud.get(session, id=global_npc_id, guild_id=interaction.guild_id)
            if not gnpc_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_delete:error_not_found",lang_code,"Global NPC ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=global_npc_id), ephemeral=True); return

            gnpc_name_for_msg = gnpc_to_delete.name_i18n.get(lang_code, gnpc_to_delete.name_i18n.get("en", f"Global NPC {global_npc_id}"))
            # Check dependencies: MobileGroup.leader_global_npc_id
            # This check should be against the ID of the GNPC being deleted.
            dependent_group_stmt = select(mobile_group_crud.model.id).where(mobile_group_crud.model.leader_global_npc_id == global_npc_id, mobile_group_crud.model.guild_id == interaction.guild_id).limit(1)
            dependent_group = (await session.execute(dependent_group_stmt)).scalar_one_or_none()
            if dependent_group:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gnpc_delete:error_leader_dependency",lang_code,"Cannot delete Global NPC '{name}' as it leads Mobile Group ID {dep_id}. Reassign leader first.")
                await interaction.followup.send(error_msg.format(name=gnpc_name_for_msg, dep_id=dependent_group), ephemeral=True); return

            deleted_gnpc: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_gnpc = await global_npc_crud.delete(session, id=global_npc_id, guild_id=interaction.guild_id)
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
