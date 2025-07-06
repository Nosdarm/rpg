import logging
import json
from typing import Dict, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

from src.core.crud.crud_mobile_group import mobile_group_crud
from src.core.crud.crud_location import location_crud # For validation
from src.core.crud.crud_global_npc import global_npc_crud # For dependency check
from src.core.database import get_db_session
from src.core.crud_base_definitions import update_entity
from src.core.localization_utils import get_localized_message_template

logger = logging.getLogger(__name__)

class MasterMobileGroupCog(commands.Cog, name="Master Mobile Group Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterMobileGroupCog initialized.")

    mobile_group_master_cmds = app_commands.Group(
        name="master_mobile_group",
        description="Master commands for managing Mobile Groups.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    @mobile_group_master_cmds.command(name="view", description="View details of a specific Mobile Group.")
    @app_commands.describe(group_id="The database ID of the Mobile Group to view.")
    async def mobile_group_view(self, interaction: discord.Interaction, group_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            group = await mobile_group_crud.get_by_id(session, id=group_id, guild_id=interaction.guild_id)

            if not group:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "mobile_group_view:not_found", lang_code,
                    "Mobile Group with ID {id} not found in this guild."
                ) # type: ignore
                await interaction.followup.send(not_found_msg.format(id=group_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "mobile_group_view:title", lang_code,
                "Mobile Group Details: {name} (ID: {id})"
            ) # type: ignore

            group_name_display = group.name_i18n.get(lang_code, group.name_i18n.get("en", f"Group {group.id}"))
            embed_title = title_template.format(name=group_name_display, id=group.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.purple())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"mobile_group_view:label_{key}", lang_code, default) # type: ignore

            async def format_json_field_helper(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str: # Renamed
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available") # type: ignore
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON") # type: ignore

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(group.guild_id), inline=True)
            embed.add_field(name=await get_label("current_location_id", "Current Location ID"), value=str(group.current_location_id) if group.current_location_id else "N/A", inline=True)

            name_i18n_str = await format_json_field_helper(group.name_i18n, "mobile_group_view:value_na_json", "mobile_group_view:error_serialization_name")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```" + ("..." if len(name_i18n_str) > 1000 else ""), inline=False)

            route_str = await format_json_field_helper(group.route_json, "mobile_group_view:value_na_json", "mobile_group_view:error_serialization_route")
            embed.add_field(name=await get_label("route_json", "Route JSON"), value=f"```json\n{route_str[:1000]}\n```" + ("..." if len(route_str) > 1000 else ""), inline=False)

            properties_str = await format_json_field_helper(group.properties_json, "mobile_group_view:value_na_json", "mobile_group_view:error_serialization_properties")
            embed.add_field(name=await get_label("properties_json", "Properties JSON"), value=f"```json\n{properties_str[:1000]}\n```" + ("..." if len(properties_str) > 1000 else ""), inline=False)

            # Assuming global_npc_crud.get_multi_by_guild_and_attribute exists and works as intended.
            members = await global_npc_crud.get_multi_by_guild_and_attribute(session, guild_id=interaction.guild_id, attribute_name="mobile_group_id", attribute_value=group_id, limit=25) # type: ignore
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

    @mobile_group_master_cmds.command(name="list", description="List Mobile Groups in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of Mobile Groups per page.")
    async def mobile_group_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

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
                ) # type: ignore
                await interaction.followup.send(no_groups_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "mobile_group_list:title", lang_code,
                "Mobile Group List (Page {page} of {total_pages})"
            ) # type: ignore
            total_pages = ((total_mobile_groups - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_purple())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "mobile_group_list:footer", lang_code,
                "Displaying {count} of {total} total Mobile Groups."
            ) # type: ignore
            embed.set_footer(text=footer_template.format(count=len(groups), total=total_mobile_groups))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "mobile_group_list:group_field_name", lang_code,
                "ID: {id} | {name}"
            ) # type: ignore
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "mobile_group_list:group_field_value", lang_code,
                "Location ID: {loc_id}"
            ) # type: ignore

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

    @mobile_group_master_cmds.command(name="create", description="Create a new Mobile Group.")
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

        lang_code = str(interaction.locale)
        parsed_name_i18n: Dict[str, str]
        parsed_route: Optional[Dict[str, Any]] = None
        parsed_props: Optional[Dict[str, Any]] = None
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            if current_location_id:
                loc = await location_crud.get_by_id(session, id=current_location_id, guild_id=interaction.guild_id)
                if not loc:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_create:error_location_not_found",lang_code,"Location ID {id} not found.") # type: ignore
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
            except ValueError as e: # Specific exception first
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_create:error_invalid_json",lang_code,"Invalid JSON: {details}") # type: ignore
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return
            except json.JSONDecodeError as e: # Broader exception later
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_create:error_invalid_json",lang_code,"Invalid JSON: {details}") # type: ignore
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return


            mg_data_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id, # Already checked not None
                "name_i18n": parsed_name_i18n,
                "current_location_id": current_location_id,
                "route_json": parsed_route or {}, "properties_json": parsed_props or {}
            }

            created_mg: Optional[Any] = None
            try:
                async with session.begin():
                    created_mg = await mobile_group_crud.create_with_guild(session, obj_in=mg_data_create, guild_id=interaction.guild_id) # type: ignore
                    await session.flush();
                    if created_mg: await session.refresh(created_mg)
            except Exception as e:
                logger.error(f"Error creating Mobile Group: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_create:error_generic_create",lang_code,"Error creating Mobile Group: {error}") # type: ignore
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return

            if not created_mg:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_create:error_unknown_fail",lang_code,"Mobile Group creation failed.") # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title = await get_localized_message_template(session,interaction.guild_id,"mg_create:success_title",lang_code,"Mobile Group Created: {name} (ID: {id})") # type: ignore
            created_name = created_mg.name_i18n.get(lang_code, created_mg.name_i18n.get("en", ""))
            embed = discord.Embed(title=success_title.format(name=created_name, id=created_mg.id), color=discord.Color.green())
            embed.add_field(name="Location ID", value=str(created_mg.current_location_id) if created_mg.current_location_id else "N/A", inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @mobile_group_master_cmds.command(name="update", description="Update a specific field for a Mobile Group.")
    @app_commands.describe(
        group_id="The database ID of the Mobile Group to update.",
        field_to_update="Field to update (e.g., name_i18n_json, current_location_id, route_json, properties_json).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable)."
    )
    async def mobile_group_update(self, interaction: discord.Interaction, group_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        allowed_fields = {
            "name_i18n": dict, # from name_i18n_json
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
                error_msg = await get_localized_message_template(temp_session,interaction.guild_id,"mg_update:error_field_not_allowed",lang_code,"Field '{f}' not allowed. Allowed: {l}") # type: ignore
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
                        parsed_value = int(new_value) # Can raise ValueError
                        if parsed_value is not None: # Check if not None before DB call
                            if not await location_crud.get_by_id(session, id=parsed_value, guild_id=interaction.guild_id):
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_loc_not_found",lang_code,"Location ID {id} not found.") # type: ignore
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                else: # Should not be reached
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_unknown_field",lang_code,"Unknown field for update.") # type: ignore
                    await interaction.followup.send(error_msg, ephemeral=True); return
            except ValueError as e: # Specific exception first
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_invalid_value",lang_code,"Invalid value for {f}: {details}") # type: ignore
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return
            except json.JSONDecodeError as e: # Broader exception later
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_invalid_json",lang_code,"Invalid JSON for {f}: {details}") # type: ignore
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            group_to_update = await mobile_group_crud.get_by_id(session, id=group_id, guild_id=interaction.guild_id)
            if not group_to_update:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_not_found",lang_code,"Mobile Group ID {id} not found.") # type: ignore
                await interaction.followup.send(error_msg.format(id=group_id), ephemeral=True); return

            update_data = {db_field_name: parsed_value}
            updated_group: Optional[Any] = None
            try:
                async with session.begin():
                    updated_group = await update_entity(session, entity=group_to_update, data=update_data)
                    await session.flush();
                    if updated_group: await session.refresh(updated_group)
            except Exception as e:
                logger.error(f"Error updating Mobile Group {group_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_generic_update",lang_code,"Error updating Mobile Group {id}: {err}") # type: ignore
                await interaction.followup.send(error_msg.format(id=group_id, err=str(e)), ephemeral=True); return

            if not updated_group:
                 error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:error_unknown_update_fail",lang_code,"Mobile Group update failed.") # type: ignore
                 await interaction.followup.send(error_msg, ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"mg_update:success",lang_code,"Mobile Group ID {id} updated. Field '{f}' set to '{v}'.") # type: ignore
            new_val_display = str(parsed_value)
            if isinstance(parsed_value, dict): new_val_display = json.dumps(parsed_value)
            elif parsed_value is None: new_val_display = "None"
            await interaction.followup.send(success_msg.format(id=updated_group.id, f=field_to_update, v=new_val_display), ephemeral=True)

    @mobile_group_master_cmds.command(name="delete", description="Delete a Mobile Group.")
    @app_commands.describe(group_id="The database ID of the Mobile Group to delete.")
    async def mobile_group_delete(self, interaction: discord.Interaction, group_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return
        lang_code = str(interaction.locale)
        async with get_db_session() as session:
            group_to_delete = await mobile_group_crud.get_by_id(session, id=group_id, guild_id=interaction.guild_id)

            if not group_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_delete:error_not_found",lang_code,"Mobile Group ID {id} not found.") # type: ignore
                await interaction.followup.send(error_msg.format(id=group_id), ephemeral=True); return

            group_name_for_msg = group_to_delete.name_i18n.get(lang_code, group_to_delete.name_i18n.get("en", f"Group {group_id}"))

            member_check_stmt = select(global_npc_crud.model.id).where(
                global_npc_crud.model.mobile_group_id == group_id, # Assuming this field exists on GlobalNpc model
                global_npc_crud.model.guild_id == interaction.guild_id
            ).limit(1)
            member_exists = (await session.execute(member_check_stmt)).scalar_one_or_none()

            if member_exists:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_delete:error_member_dependency",lang_code,"Cannot delete Mobile Group '{name}' (ID: {id}) as it has Global NPC members. Reassign them first.") # type: ignore
                await interaction.followup.send(error_msg.format(name=group_name_for_msg, id=group_id), ephemeral=True); return

            deleted_group: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_group = await mobile_group_crud.remove_by_id(session, id=group_id, guild_id=interaction.guild_id) # type: ignore

                if deleted_group:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"mg_delete:success",lang_code,"Mobile Group '{name}' (ID: {id}) deleted.") # type: ignore
                    await interaction.followup.send(success_msg.format(name=group_name_for_msg, id=group_id), ephemeral=True)
                else: # Should not happen if found before
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_delete:error_unknown_delete_fail",lang_code,"Mobile Group (ID: {id}) found but not deleted.") # type: ignore
                    await interaction.followup.send(error_msg.format(id=group_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Mobile Group {group_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"mg_delete:error_generic_delete",lang_code,"Error deleting Mobile Group '{name}' (ID: {id}): {err}") # type: ignore
                await interaction.followup.send(error_msg.format(name=group_name_for_msg, id=group_id, err=str(e)), ephemeral=True)

async def setup(bot: commands.Bot):
    cog = MasterMobileGroupCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterMobileGroupCog loaded.")
