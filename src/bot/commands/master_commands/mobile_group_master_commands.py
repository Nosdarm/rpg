import logging
import json
from typing import Optional, Dict, Any, Union, List # Added Union, List

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

from src.core.crud.crud_mobile_group import mobile_group_crud
from src.core.crud.crud_location import location_crud # For validation
from src.core.crud.crud_global_npc import global_npc_crud # For dependency check & validation
from src.core.database import get_db_session
from src.core.crud_base_definitions import update_entity
from src.core.localization_utils import get_localized_message_template
from src.bot.utils import parse_json_parameter # Import the utility

logger = logging.getLogger(__name__)

class MasterMobileGroupCog(commands.Cog, name="Master Mobile Group Commands"): # type: ignore[call-arg]
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterMobileGroupCog initialized.")

    mobile_group_master_cmds = app_commands.Group(
        name="master_mobile_group",
        description="Master commands for managing Mobile Groups.",
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

    @mobile_group_master_cmds.command(name="view", description="View details of a specific Mobile Group.")
    @app_commands.describe(group_id="The database ID of the Mobile Group to view.")
    async def mobile_group_view(self, interaction: discord.Interaction, group_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            group = await mobile_group_crud.get(session, id=group_id, guild_id=interaction.guild_id)

            if not group:
                not_found_msg = await get_localized_message_template(session, interaction.guild_id, "mobile_group_view:not_found", lang_code, "Mobile Group with ID {id} not found in this guild.")
                await interaction.followup.send(not_found_msg.format(id=group_id), ephemeral=True); return

            title_template = await get_localized_message_template(session, interaction.guild_id, "mobile_group_view:title", lang_code, "Mobile Group Details: {name} (ID: {id})")
            group_name_display = group.name_i18n.get(lang_code, group.name_i18n.get("en", f"Group {group.id}"))
            embed_title = title_template.format(name=group_name_display, id=group.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.purple())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"mobile_group_view:label_{key}", lang_code, default)

            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(group.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=group.static_id or na_value_str, inline=True)
            embed.add_field(name=await get_label("current_location_id", "Current Location ID"), value=str(group.current_location_id) if group.current_location_id else na_value_str, inline=True)

            leader_display = na_value_str
            if group.leader_global_npc_id:
                leader_npc = await global_npc_crud.get(session, id=group.leader_global_npc_id, guild_id=interaction.guild_id)
                if leader_npc:
                    leader_name = leader_npc.name_i18n.get(lang_code, leader_npc.name_i18n.get("en", f"GNPC {leader_npc.id}"))
                    leader_display = f"{leader_name} (ID: {leader_npc.id}, Static: {leader_npc.static_id or na_value_str})"
                else:
                    leader_display = f"GNPC ID: {group.leader_global_npc_id} (Not Found)"
            embed.add_field(name=await get_label("leader_npc", "Leader GNPC"), value=leader_display, inline=True)


            name_i18n_str = await self._format_json_field_display(interaction, group.name_i18n, lang_code)
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```", inline=False)

            desc_i18n_str = await self._format_json_field_display(interaction, group.description_i18n, lang_code)
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```", inline=False)

            behavior_type_i18n_str = await self._format_json_field_display(interaction, group.behavior_type_i18n, lang_code)
            embed.add_field(name=await get_label("behavior_type_i18n", "Behavior Type (i18n)"), value=f"```json\n{behavior_type_i18n_str[:1000]}\n```", inline=False)

            route_str = await self._format_json_field_display(interaction, group.route_json, lang_code)
            embed.add_field(name=await get_label("route_json", "Route JSON"), value=f"```json\n{route_str[:1000]}\n```", inline=False)

            members_def_str = await self._format_json_field_display(interaction, {"members": group.members_definition_json}, lang_code) # Wrap list for display
            embed.add_field(name=await get_label("members_definition_json", "Members Definition JSON"), value=f"```json\n{members_def_str[:1000]}\n```", inline=False)

            properties_str = await self._format_json_field_display(interaction, group.properties_json, lang_code)
            embed.add_field(name=await get_label("properties_json", "Properties JSON"), value=f"```json\n{properties_str[:1000]}\n```", inline=False)

            ai_meta_str = await self._format_json_field_display(interaction, group.ai_metadata_json, lang_code)
            embed.add_field(name=await get_label("ai_metadata_json", "AI Metadata JSON"), value=f"```json\n{ai_meta_str[:1000]}\n```", inline=False)


            members = await global_npc_crud.get_multi_by_attribute(session, guild_id=interaction.guild_id, attribute="mobile_group_id", value=group_id, limit=25)
            members_label_text = await get_label("members_assigned", "Assigned Members (Global NPCs)")
            if members:
                member_info_list = []
                for member_gnpc in members:
                    member_name = member_gnpc.name_i18n.get(lang_code, member_gnpc.name_i18n.get("en", f"GNPC {member_gnpc.id}"))
                    member_info_list.append(f"ID: {member_gnpc.id} - {member_name} (Static: {member_gnpc.static_id or na_value_str})")
                embed.add_field(name=f"{members_label_text} ({len(member_info_list)})", value="\n".join(member_info_list)[:1020], inline=False)
            else:
                no_members_msg = await get_localized_message_template(session, interaction.guild_id, "mobile_group_view:no_assigned_members", lang_code, "No Global NPCs currently assigned to this group.")
                embed.add_field(name=members_label_text, value=no_members_msg, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @mobile_group_master_cmds.command(name="list", description="List Mobile Groups in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of Mobile Groups per page.")
    async def mobile_group_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1;
        if limit < 1: limit = 1;
        if limit > 10: limit = 10
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            offset = (page - 1) * limit
            groups = await mobile_group_crud.get_multi(session, guild_id=interaction.guild_id, skip=offset, limit=limit)
            total_mobile_groups = await mobile_group_crud.count(session, guild_id=interaction.guild_id) # Changed to .count

            if not groups:
                no_groups_msg = await get_localized_message_template(session, interaction.guild_id, "mobile_group_list:no_groups_found_page", lang_code, "No Mobile Groups found for this guild (Page {page}).")
                await interaction.followup.send(no_groups_msg.format(page=page), ephemeral=True); return

            title_template = await get_localized_message_template(session, interaction.guild_id, "mobile_group_list:title", lang_code, "Mobile Group List (Page {page} of {total_pages})")
            total_pages = ((total_mobile_groups - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_purple())
            footer_template = await get_localized_message_template(session, interaction.guild_id, "mobile_group_list:footer", lang_code, "Displaying {count} of {total} total Mobile Groups.")
            embed.set_footer(text=footer_template.format(count=len(groups), total=total_mobile_groups))

            field_name_template = await get_localized_message_template(session, interaction.guild_id, "mobile_group_list:group_field_name", lang_code, "ID: {id} | Static: {sid} | {name}")
            field_value_template = await get_localized_message_template(session, interaction.guild_id, "mobile_group_list:group_field_value", lang_code, "Location ID: {loc_id}")

            for group_obj in groups:
                na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")
                group_name_display = group_obj.name_i18n.get(lang_code, group_obj.name_i18n.get("en", f"Group {group_obj.id}"))
                embed.add_field(
                    name=field_name_template.format(id=group_obj.id, sid=group_obj.static_id or na_value_str, name=group_name_display),
                    value=field_value_template.format(loc_id=str(group_obj.current_location_id) if group_obj.current_location_id else na_value_str),
                    inline=False
                )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @mobile_group_master_cmds.command(name="create", description="Create a new Mobile Group.")
    @app_commands.describe(
        static_id="Static ID for this group (unique within the guild).",
        name_i18n_json="JSON for Mobile Group name (e.g., {\"en\": \"Merchant Caravan\"}).",
        description_i18n_json="Optional: JSON for group description.",
        current_location_id="Optional: Database ID of the group's starting location.",
        leader_global_npc_id="Optional: Database ID of the Global NPC leading this group.",
        members_definition_json="Optional: JSON array for member definitions (e.g., [{\"global_npc_static_id\": \"guard1\", \"role_i18n\": {\"en\":\"Guard\"}}]).",
        behavior_type_i18n_json="Optional: JSON for group behavior type.",
        route_json="Optional: JSON describing the group's route or movement behavior.",
        properties_json="Optional: JSON for additional properties (status, goals, etc.)."
    )
    async def mobile_group_create(self, interaction: discord.Interaction,
                                  static_id: str,
                                  name_i18n_json: str,
                                  description_i18n_json: Optional[str] = None,
                                  current_location_id: Optional[int] = None,
                                  leader_global_npc_id: Optional[int] = None,
                                  members_definition_json: Optional[str] = None,
                                  behavior_type_i18n_json: Optional[str] = None,
                                  route_json: Optional[str] = None,
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
            parsed_desc_i18n = await parse_json_parameter(interaction, description_i18n_json, "description_i18n_json", session)
            if parsed_desc_i18n is None and description_i18n_json is not None: return
            parsed_members_def = await parse_json_parameter(interaction, members_definition_json, "members_definition_json", session)
            if parsed_members_def is None and members_definition_json is not None: return
            parsed_behavior_type_i18n = await parse_json_parameter(interaction, behavior_type_i18n_json, "behavior_type_i18n_json", session)
            if parsed_behavior_type_i18n is None and behavior_type_i18n_json is not None: return
            parsed_route = await parse_json_parameter(interaction, route_json, "route_json", session)
            if parsed_route is None and route_json is not None: return
            parsed_props = await parse_json_parameter(interaction, properties_json, "properties_json", session)
            if parsed_props is None and properties_json is not None: return

            if await mobile_group_crud.get_by_attribute(session, attribute="static_id", value=static_id, guild_id=interaction.guild_id):
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_create:error_static_id_exists",lang_code,"Mobile Group with static_id '{id}' already exists.")
                await interaction.followup.send(error_msg.format(id=static_id), ephemeral=True); return
            if current_location_id and not await location_crud.get(session, id=current_location_id, guild_id=interaction.guild_id):
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_create:error_location_not_found",lang_code,"Location ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=current_location_id), ephemeral=True); return
            if leader_global_npc_id and not await global_npc_crud.get(session, id=leader_global_npc_id, guild_id=interaction.guild_id):
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_create:error_leader_gnpc_not_found",lang_code,"Leader Global NPC ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=leader_global_npc_id), ephemeral=True); return

            if parsed_members_def: # Validate members_definition_json structure and existence of GNPCs
                if not isinstance(parsed_members_def, list):
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_create:error_members_def_not_list",lang_code,"members_definition_json must be a list.")
                    await interaction.followup.send(error_msg, ephemeral=True); return
                for member_entry in parsed_members_def:
                    if not isinstance(member_entry, dict) or "global_npc_static_id" not in member_entry or not isinstance(member_entry["global_npc_static_id"], str):
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_create:error_member_def_invalid_format",lang_code,"Each member definition must be a dict with a 'global_npc_static_id' (string).")
                        await interaction.followup.send(error_msg, ephemeral=True); return
                    gnpc_sid = member_entry["global_npc_static_id"]
                    if not await global_npc_crud.get_by_attribute(session, attribute="static_id", value=gnpc_sid, guild_id=interaction.guild_id):
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_create:error_member_gnpc_not_found",lang_code,"Member Global NPC with static_id '{sid}' not found.")
                        await interaction.followup.send(error_msg.format(sid=gnpc_sid), ephemeral=True); return
                    if "role_i18n" in member_entry and (not isinstance(member_entry["role_i18n"], dict) or not all(isinstance(k, str) and isinstance(v, str) for k,v in member_entry["role_i18n"].items())):
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_create:error_member_role_invalid_format",lang_code,"Member 'role_i18n' must be a dictionary of string keys and string values.")
                        await interaction.followup.send(error_msg, ephemeral=True); return

            mg_data_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id, "static_id": static_id,
                "name_i18n": parsed_name_i18n, "description_i18n": parsed_desc_i18n or {},
                "current_location_id": current_location_id, "leader_global_npc_id": leader_global_npc_id,
                "members_definition_json": parsed_members_def or [],
                "behavior_type_i18n": parsed_behavior_type_i18n or {},
                "route_json": parsed_route or {}, "properties_json": parsed_props or {}
            }
            created_mg: Optional[Any] = None
            try:
                async with session.begin():
                    created_mg = await mobile_group_crud.create(session, obj_in=mg_data_create)
                    await session.flush();
                    if created_mg: await session.refresh(created_mg)
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
            embed.add_field(name="Static ID", value=created_mg.static_id, inline=True)
            embed.add_field(name="Location ID", value=str(created_mg.current_location_id) if created_mg.current_location_id else "N/A", inline=True)
            if created_mg.leader_global_npc_id:
                 embed.add_field(name="Leader GNPC ID", value=str(created_mg.leader_global_npc_id), inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @mobile_group_master_cmds.command(name="update", description="Update a specific field for a Mobile Group.")
    @app_commands.describe(
        group_id="The database ID of the Mobile Group to update.",
        field_to_update="Field to update (e.g., static_id, name_i18n_json, current_location_id, leader_global_npc_id, members_definition_json, behavior_type_i18n_json, route_json, properties_json).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable)."
    )
    async def mobile_group_update(self, interaction: discord.Interaction, group_id: int, field_to_update: str, new_value: str):
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
            "leader_global_npc_id": (int, type(None)),
            "members_definition_json": list,
            "behavior_type_i18n": dict,
            "route_json": dict,
            "properties_json": dict,
        }
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
            group_to_update = await mobile_group_crud.get(session, id=group_id, guild_id=interaction.guild_id)
            if not group_to_update:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_not_found",lang_code,"Mobile Group ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=group_id), ephemeral=True); return
            try:
                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: raise ValueError("static_id cannot be empty.")
                    if parsed_value != group_to_update.static_id and await mobile_group_crud.get_by_attribute(session, attribute="static_id", value=parsed_value, guild_id=interaction.guild_id):
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_static_id_exists",lang_code,"Static ID '{id}' already in use.")
                        await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                elif db_field_name in ["name_i18n", "description_i18n", "behavior_type_i18n", "route_json", "properties_json"]:
                    temp_parsed = await parse_json_parameter(interaction, new_value, field_to_update_lower, session)
                    if temp_parsed is None: return
                    parsed_value = temp_parsed
                elif db_field_name == "members_definition_json":
                    temp_parsed_list = await parse_json_parameter(interaction, new_value, field_to_update_lower, session)
                    if temp_parsed_list is None: return
                    if not isinstance(temp_parsed_list, list):
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_members_def_not_list",lang_code,"members_definition_json must be a list.")
                        await interaction.followup.send(error_msg, ephemeral=True); return
                    for member_entry in temp_parsed_list: # Validate structure
                        if not isinstance(member_entry, dict) or "global_npc_static_id" not in member_entry or not isinstance(member_entry["global_npc_static_id"], str):
                            error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_member_def_invalid_format",lang_code,"Each member definition must be a dict with a 'global_npc_static_id' (string).")
                            await interaction.followup.send(error_msg, ephemeral=True); return
                        gnpc_sid = member_entry["global_npc_static_id"]
                        if not await global_npc_crud.get_by_attribute(session, attribute="static_id", value=gnpc_sid, guild_id=interaction.guild_id):
                            error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_member_gnpc_not_found",lang_code,"Member Global NPC with static_id '{sid}' not found.")
                            await interaction.followup.send(error_msg.format(sid=gnpc_sid), ephemeral=True); return
                    parsed_value = temp_parsed_list
                elif db_field_name == "current_location_id" or db_field_name == "leader_global_npc_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = int(new_value)
                        if parsed_value is not None:
                            if db_field_name == "current_location_id" and not await location_crud.get(session, id=parsed_value, guild_id=interaction.guild_id):
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_detail_loc_not_found",lang_code,"Location ID {id} not found.")
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                            if db_field_name == "leader_global_npc_id" and not await global_npc_crud.get(session, id=parsed_value, guild_id=interaction.guild_id):
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_detail_leader_gnpc_not_found",lang_code,"Leader GNPC ID {id} not found.")
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_detail_unknown_field",lang_code,"Unknown field for update: {field_name}")
                    await interaction.followup.send(error_msg.format(field_name=db_field_name), ephemeral=True); return
            except (ValueError, json.JSONDecodeError) as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_invalid_value_data",lang_code,"Invalid value or data for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            update_data = {db_field_name: parsed_value}
            updated_group: Optional[Any] = None
            try:
                async with session.begin():
                    updated_group = await update_entity(session, entity=group_to_update, data=update_data)
                    await session.flush();
                    if updated_group: await session.refresh(updated_group)
            except Exception as e:
                logger.error(f"Error updating Mobile Group {group_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_generic_update",lang_code,"Error updating Mobile Group {id}: {err}")
                await interaction.followup.send(error_msg.format(id=group_id, err=str(e)), ephemeral=True); return

            if not updated_group:
                 error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_unknown_update_fail",lang_code,"Mobile Group update failed.")
                 await interaction.followup.send(error_msg, ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:success",lang_code,"Mobile Group ID {id} updated. Field '{f}' set to '{v}'.")
            new_val_display_str = await self._format_json_field_display(interaction, parsed_value, lang_code) if isinstance(parsed_value, (dict, list)) else (await get_localized_message_template(session, interaction.guild_id, "common:value_none", lang_code, "None") if parsed_value is None else str(parsed_value))
            await interaction.followup.send(success_msg.format(id=updated_group.id, f=field_to_update, v=new_val_display_str), ephemeral=True)

    @mobile_group_master_cmds.command(name="delete", description="Delete a Mobile Group.")
    @app_commands.describe(group_id="The database ID of the Mobile Group to delete.")
    async def mobile_group_delete(self, interaction: discord.Interaction, group_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            group_to_delete = await mobile_group_crud.get(session, id=group_id, guild_id=interaction.guild_id)
            if not group_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_delete:error_not_found",lang_code,"Mobile Group ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=group_id), ephemeral=True); return

            group_name_for_msg = group_to_delete.name_i18n.get(lang_code, group_to_delete.name_i18n.get("en", f"Group {group_id}"))
            member_check_stmt = select(global_npc_crud.model.id).where(global_npc_crud.model.mobile_group_id == group_id, global_npc_crud.model.guild_id == interaction.guild_id).limit(1)
            member_exists = (await session.execute(member_check_stmt)).scalar_one_or_none()
            if member_exists:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_delete:error_member_dependency",lang_code,"Cannot delete Mobile Group '{name}' (ID: {id}) as it has Global NPC members. Reassign them first.")
                await interaction.followup.send(error_msg.format(name=group_name_for_msg, id=group_id), ephemeral=True); return

            deleted_group: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_group = await mobile_group_crud.delete(session, id=group_id, guild_id=interaction.guild_id)
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

async def setup(bot: commands.Bot):
    cog = MasterMobileGroupCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterMobileGroupCog loaded.")
