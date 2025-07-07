import logging
import json
from typing import Dict, Any, Optional, List, Union

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, or_

from src.core.crud.crud_location import location_crud
from src.core.crud.crud_player import player_crud
from src.core.crud.crud_npc import npc_crud
from src.core.database import get_db_session
from src.core.crud_base_definitions import update_entity
from src.core.localization_utils import get_localized_message_template
from src.models.location import LocationType
from src.bot.utils import parse_json_parameter

logger = logging.getLogger(__name__)

class MasterLocationCog(commands.Cog, name="Master Location Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterLocationCog initialized.")

    location_master_cmds = app_commands.Group(
        name="master_location",
        description="Master commands for managing Locations.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    async def _format_json_field_display(self, interaction: discord.Interaction, data: Optional[Union[Dict[Any, Any], List[Any]]], lang_code: str) -> str:
        na_str = "Not available"
        error_str = "Error serializing JSON"
        try:
            async with get_db_session() as temp_session:
                na_str = await get_localized_message_template(temp_session, interaction.guild_id, "common:value_na_json", lang_code, "Not available")
                error_str = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_serialization", lang_code, "Error serializing JSON")
        except Exception:
            pass

        if not data: return na_str
        try: return json.dumps(data, indent=2, ensure_ascii=False)
        except TypeError: return error_str

    @location_master_cmds.command(name="view", description="View details of a specific Location.")
    @app_commands.describe(location_id="The database ID of the Location to view.")
    async def location_view(self, interaction: discord.Interaction, location_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            loc = await location_crud.get(session, id=location_id, guild_id=interaction.guild_id)

            if not loc:
                not_found_msg = await get_localized_message_template(session, interaction.guild_id, "location_view:not_found", lang_code, "Location with ID {id} not found in this guild.")
                await interaction.followup.send(not_found_msg.format(id=location_id), ephemeral=True); return

            title_template = await get_localized_message_template(session, interaction.guild_id, "location_view:title", lang_code, "Location Details: {loc_name} (ID: {loc_id})")
            loc_name_display = loc.name_i18n.get(lang_code, loc.name_i18n.get("en", f"Location {loc.id}"))
            embed_title = title_template.format(loc_name=loc_name_display, loc_id=loc.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_green())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"location_view:label_{key}", lang_code, default)

            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(loc.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=loc.static_id or na_value_str, inline=True)
            embed.add_field(name=await get_label("type", "Type"), value=loc.type.value if loc.type else na_value_str, inline=True)
            embed.add_field(name=await get_label("parent_id", "Parent ID"), value=str(loc.parent_location_id) if loc.parent_location_id else na_value_str, inline=True)

            name_i18n_str = await self._format_json_field_display(interaction, loc.name_i18n, lang_code)
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```", inline=False)
            desc_i18n_str = await self._format_json_field_display(interaction, loc.descriptions_i18n, lang_code)
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```", inline=False)
            details_str = await self._format_json_field_display(interaction, loc.generated_details_json, lang_code)
            embed.add_field(name=await get_label("generated_details", "Generated Details JSON"), value=f"```json\n{details_str[:1000]}\n```", inline=False)
            neighbors_str = await self._format_json_field_display(interaction, loc.neighbor_locations_json, lang_code)
            embed.add_field(name=await get_label("neighbors", "Neighbor Locations JSON"), value=f"```json\n{neighbors_str[:1000]}\n```", inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @location_master_cmds.command(name="list", description="List Locations in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of Locations per page.")
    async def location_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
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
            locations = await location_crud.get_multi(session, guild_id=interaction.guild_id, skip=offset, limit=limit)
            total_locations = await location_crud.get_count_by_guild(session, guild_id=interaction.guild_id) # type: ignore

            if not locations:
                no_locs_msg = await get_localized_message_template(session, interaction.guild_id, "location_list:no_locations_found_page", lang_code, "No Locations found for this guild (Page {page}).")
                await interaction.followup.send(no_locs_msg.format(page=page), ephemeral=True); return

            title_template = await get_localized_message_template(session, interaction.guild_id, "location_list:title", lang_code, "Location List (Page {page} of {total_pages})")
            total_pages = ((total_locations - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_blue())
            footer_template = await get_localized_message_template(session, interaction.guild_id, "location_list:footer", lang_code, "Displaying {count} of {total} total Locations.")
            embed.set_footer(text=footer_template.format(count=len(locations), total=total_locations))

            field_name_template = await get_localized_message_template(session, interaction.guild_id, "location_list:location_field_name", lang_code, "ID: {loc_id} | {loc_name} (Static: {static_id})")
            field_value_template = await get_localized_message_template(session, interaction.guild_id, "location_list:location_field_value", lang_code, "Type: {type}, Parent ID: {parent_id}, Neighbors: {neighbor_count}")

            for loc in locations:
                na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")
                loc_name_display = loc.name_i18n.get(lang_code, loc.name_i18n.get("en", f"Location {loc.id}"))
                neighbor_data = loc.neighbor_locations_json if isinstance(loc.neighbor_locations_json, list) else []
                neighbor_count = len(neighbor_data)
                embed.add_field(
                    name=field_name_template.format(loc_id=loc.id, loc_name=loc_name_display, static_id=loc.static_id or na_value_str),
                    value=field_value_template.format(type=loc.type.value if loc.type else na_value_str, parent_id=str(loc.parent_location_id) if loc.parent_location_id else na_value_str, neighbor_count=neighbor_count),
                    inline=False
                )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @location_master_cmds.command(name="create", description="Create a new Location in this guild.")
    @app_commands.describe(
        static_id="Optional: Static ID for this Location (must be unique within the guild).",
        name_i18n_json="JSON string for Location name (e.g., {\"en\": \"Town Square\", \"ru\": \"Городская площадь\"}).",
        type_name="Type of location (e.g., TOWN, FOREST, DUNGEON_ROOM, BUILDING_INTERIOR). See LocationType enum.",
        description_i18n_json="Optional: JSON string for Location description.",
        parent_location_id="Optional: Database ID of the parent Location.",
        properties_json="Optional: JSON string for additional Location properties (maps to generated_details_json).",
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
        lang_code = str(interaction.locale)
        parsed_location_type: LocationType
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            try:
                parsed_location_type = LocationType[type_name.upper()]
            except KeyError:
                valid_types = ", ".join([lt.name for lt in LocationType])
                error_detail_template = await get_localized_message_template(session, interaction.guild_id, "location_create:error_detail_invalid_type", lang_code, "Invalid type_name. Valid types: {valid_list}")
                error_msg = await get_localized_message_template(session, interaction.guild_id, "location_create:error_invalid_data", lang_code, "Invalid data provided: {details}")
                await interaction.followup.send(error_msg.format(details=error_detail_template.format(valid_list=valid_types)), ephemeral=True); return

            parsed_name_i18n = await parse_json_parameter(interaction, name_i18n_json, "name_i18n_json", session)
            if parsed_name_i18n is None: return
            error_detail_name_lang = await get_localized_message_template(session, interaction.guild_id, "location_create:error_detail_name_lang", lang_code, "name_i18n_json must contain 'en' or current language key.")
            if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code):
                 error_msg = await get_localized_message_template(session,interaction.guild_id,"location_create:error_invalid_json_content",lang_code,"Invalid JSON content: {details}")
                 await interaction.followup.send(error_msg.format(details=error_detail_name_lang), ephemeral=True); return

            parsed_description_i18n = await parse_json_parameter(interaction, description_i18n_json, "description_i18n_json", session)
            if parsed_description_i18n is None and description_i18n_json is not None: return

            parsed_properties = await parse_json_parameter(interaction, properties_json, "properties_json", session)
            if parsed_properties is None and properties_json is not None: return

            parsed_neighbors_list = await parse_json_parameter(interaction, neighbor_locations_json, "neighbor_locations_json", session)
            if parsed_neighbors_list is None and neighbor_locations_json is not None: return

            parsed_neighbors: Optional[List[Dict[str, Any]]] = None
            if isinstance(parsed_neighbors_list, list):
                parsed_neighbors = parsed_neighbors_list
                for neighbor_entry in parsed_neighbors: # type: ignore
                    if not isinstance(neighbor_entry, dict) or not isinstance(neighbor_entry.get("target_static_id"), str):
                        error_detail_neighbor_target_sid = await get_localized_message_template(session, interaction.guild_id, "location_create:error_detail_neighbor_target_sid", lang_code, "Each entry in neighbor_locations_json must be a dict with a 'target_static_id' (string).")
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"location_create:error_invalid_json_content",lang_code,"Invalid JSON content: {details}")
                        await interaction.followup.send(error_msg.format(details=error_detail_neighbor_target_sid), ephemeral=True); return
                    if "description_i18n" in neighbor_entry and (not isinstance(neighbor_entry["description_i18n"], dict) or not all(isinstance(k, str) and isinstance(v, str) for k,v in neighbor_entry["description_i18n"].items())):
                        error_detail_neighbor_desc_format = await get_localized_message_template(session, interaction.guild_id, "location_create:error_detail_neighbor_desc_format", lang_code, "Neighbor 'description_i18n' must be a dict of str:str if provided.")
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"location_create:error_invalid_json_content",lang_code,"Invalid JSON content: {details}")
                        await interaction.followup.send(error_msg.format(details=error_detail_neighbor_desc_format), ephemeral=True); return
            elif parsed_neighbors_list is not None and not isinstance(parsed_neighbors_list, list): # if it was provided but not a list
                 error_detail_neighbors_format = await get_localized_message_template(session, interaction.guild_id, "location_create:error_detail_neighbors_format", lang_code, "neighbor_locations_json must be a list of dictionaries.")
                 error_msg = await get_localized_message_template(session,interaction.guild_id,"location_create:error_invalid_json_content",lang_code,"Invalid JSON content: {details}")
                 await interaction.followup.send(error_msg.format(details=error_detail_neighbors_format), ephemeral=True); return


            if parent_location_id:
                parent_loc = await location_crud.get(session, id=parent_location_id, guild_id=interaction.guild_id)
                if not parent_loc:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "location_create:error_parent_not_found", lang_code, "Parent Location with ID {id} not found.")
                    await interaction.followup.send(error_msg.format(id=parent_location_id), ephemeral=True); return
            if static_id:
                existing_loc_static = await location_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=static_id)
                if existing_loc_static:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "location_create:error_static_id_exists", lang_code, "A Location with static_id '{id}' already exists.")
                    await interaction.followup.send(error_msg.format(id=static_id), ephemeral=True); return

            location_data_to_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id, "static_id": static_id,
                "name_i18n": parsed_name_i18n, # Already validated not None
                "descriptions_i18n": parsed_description_i18n or {}, # Corrected field name
                "type": parsed_location_type,
                "parent_location_id": parent_location_id,
                "generated_details_json": parsed_properties or {},
                "neighbor_locations_json": parsed_neighbors or [],
            }
            created_location: Optional[Any] = None
            try:
                async with session.begin():
                    created_location = await location_crud.create_with_guild(session, obj_in=location_data_to_create, guild_id=interaction.guild_id) # type: ignore
                    await session.flush();
                    if created_location: await session.refresh(created_location)
            except Exception as e:
                logger.error(f"Error creating Location: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, interaction.guild_id, "location_create:error_generic_create", lang_code, "An error occurred while creating the Location: {error_message}")
                await interaction.followup.send(error_msg.format(error_message=str(e)), ephemeral=True); return

            if not created_location:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "location_create:error_creation_failed_unknown", lang_code, "Location creation failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title_template = await get_localized_message_template(session, interaction.guild_id, "location_create:success_title", lang_code, "Location Created: {loc_name} (ID: {loc_id})")
            created_loc_name_display = created_location.name_i18n.get(lang_code, created_location.name_i18n.get("en", f"Location {created_location.id}"))
            embed = discord.Embed(title=success_title_template.format(loc_name=created_loc_name_display, loc_id=created_location.id), color=discord.Color.green())
            async def get_created_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"location_create:label_{key}", lang_code, default)
            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")
            embed.add_field(name=await get_created_label("static_id", "Static ID"), value=created_location.static_id or na_value_str, inline=True)
            embed.add_field(name=await get_created_label("type", "Type"), value=created_location.type.value, inline=True)
            embed.add_field(name=await get_created_label("parent_id", "Parent ID"), value=str(created_location.parent_location_id) if created_location.parent_location_id else na_value_str, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @location_master_cmds.command(name="update", description="Update a specific field for a Location.")
    @app_commands.describe(
        location_id="The database ID of the Location to update.",
        field_to_update="Field to update (e.g., static_id, name_i18n_json, type_name, parent_location_id, properties_json, neighbor_locations_json).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable fields; enum name for type_name)."
    )
    async def location_update(self, interaction: discord.Interaction, location_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        allowed_fields = {
            "static_id": (str, type(None)),
            "name_i18n": dict,
            "descriptions_i18n": dict, # Corrected from description_i18n
            "type": LocationType,
            "parent_location_id": (int, type(None)),
            "generated_details_json": dict,
            "neighbor_locations_json": list,
             "ai_metadata_json": dict, # Added
             "coordinates_json": dict, # Added
        }

        field_to_update_lower = field_to_update.lower()
        db_field_name = field_to_update_lower
        user_facing_field_name = field_to_update_lower

        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")
        elif field_to_update_lower == "type_name":
            db_field_name = "type"
            user_facing_field_name = "type_name"
        elif field_to_update_lower == "properties_json":
            db_field_name = "generated_details_json"
            user_facing_field_name = "properties_json"
        elif field_to_update_lower == "description_i18n_json": # map description to descriptions
            db_field_name = "descriptions_i18n"
            user_facing_field_name = "description_i18n_json"


        field_type_info = allowed_fields.get(db_field_name)

        if not field_type_info:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "location_update:error_field_not_allowed", lang_code, "Field '{field_name}' is not allowed for update. Allowed: {allowed_list}")
            user_friendly_allowed_keys = [ k[:-5]+"_json" if isinstance(v, (dict, list)) and k not in ["static_id", "type", "parent_location_id"] else ("type_name" if k == "type" else k) for k,v in allowed_fields.items() ]
            user_friendly_allowed_keys = [ "properties_json" if k == "generated_details_json" else k for k in user_friendly_allowed_keys]
            user_friendly_allowed_keys = [ "description_i18n_json" if k == "descriptions_i18n" else k for k in user_friendly_allowed_keys]

            await interaction.followup.send(error_msg.format(field_name=field_to_update, allowed_list=', '.join(user_friendly_allowed_keys)), ephemeral=True); return

        parsed_value: Any = None
        async with get_db_session() as session:
            location_to_update = await location_crud.get(session, id=location_id, guild_id=interaction.guild_id)
            if not location_to_update:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "location_update:error_location_not_found", lang_code, "Location with ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=location_id), ephemeral=True); return
            try:
                error_detail_static_id_exists_template = await get_localized_message_template(session, interaction.guild_id, "location_update:error_detail_static_id_exists", lang_code, "Another Location with static_id '{id}' already exists.")
                error_detail_invalid_type_template = await get_localized_message_template(session, interaction.guild_id, "location_update:error_detail_invalid_type", lang_code, "Invalid type_name. Valid types: {valid_list}")
                error_detail_parent_not_found_template = await get_localized_message_template(session, interaction.guild_id, "location_update:error_detail_parent_not_found", lang_code, "Parent Location with ID {id} not found.")
                error_detail_self_parent_template = await get_localized_message_template(session, interaction.guild_id, "location_update:error_detail_self_parent", lang_code, "Location cannot be its own parent.")
                error_detail_unknown_field_template = await get_localized_message_template(session, interaction.guild_id, "location_update:error_detail_unknown_field_type", lang_code, "Internal error: Unknown field type for '{field_name}'.")
                error_detail_neighbors_format_template = await get_localized_message_template(session, interaction.guild_id, "location_update:error_detail_neighbors_format", lang_code, "neighbor_locations_json must be a list of dictionaries.")
                error_detail_neighbor_target_sid_template = await get_localized_message_template(session, interaction.guild_id, "location_update:error_detail_neighbor_target_sid", lang_code, "Neighbor entry missing 'target_static_id'.")


                if db_field_name == "static_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = new_value
                        if parsed_value is not None and parsed_value != location_to_update.static_id: # Check only if changed
                            existing_loc_static = await location_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                            if existing_loc_static and existing_loc_static.id != location_id:
                                raise ValueError(error_detail_static_id_exists_template.format(id=parsed_value))
                elif db_field_name in ["name_i18n", "descriptions_i18n", "generated_details_json", "ai_metadata_json", "coordinates_json"]:
                    parsed_value = await parse_json_parameter(interaction, new_value, user_facing_field_name, session)
                    if parsed_value is None and new_value is not None: return # Error already sent
                elif db_field_name == "neighbor_locations_json":
                    parsed_value_list = await parse_json_parameter(interaction, new_value, user_facing_field_name, session)
                    if parsed_value_list is None and new_value is not None: return
                    if parsed_value_list and not isinstance(parsed_value_list, list):
                         raise ValueError(error_detail_neighbors_format_template)
                    if parsed_value_list:
                        for neighbor_entry in parsed_value_list: # type: ignore
                            if not isinstance(neighbor_entry, dict) or not isinstance(neighbor_entry.get("target_static_id"), str):
                                raise ValueError(error_detail_neighbor_target_sid_template)
                    parsed_value = parsed_value_list or [] # Ensure it's a list or empty list
                elif db_field_name == "type":
                    try:
                        parsed_value = LocationType[new_value.upper()]
                    except KeyError:
                        valid_types = ", ".join([lt.name for lt in LocationType])
                        raise ValueError(error_detail_invalid_type_template.format(valid_list=valid_types))
                elif db_field_name == "parent_location_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = int(new_value)
                        if parsed_value is not None:
                            if parsed_value == location_id: # Check for self-parenting
                                raise ValueError(error_detail_self_parent_template)
                            parent_loc = await location_crud.get(session, id=parsed_value, guild_id=interaction.guild_id)
                            if not parent_loc:
                                raise ValueError(error_detail_parent_not_found_template.format(id=parsed_value))
                else:
                     raise ValueError(error_detail_unknown_field_template.format(field_name=db_field_name))
            except ValueError as e:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "location_update:error_invalid_value_type", lang_code, "Invalid value '{value}' for field '{field_name}'. Details: {details}")
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True); return

            update_data_dict = {db_field_name: parsed_value}
            updated_location: Optional[Any] = None
            try:
                async with session.begin():
                    updated_location = await update_entity(session, entity=location_to_update, data=update_data_dict)
                    await session.flush()
                    if updated_location:
                        await session.refresh(updated_location)
            except Exception as e:
                logger.error(f"Error updating Location {location_id} with data {update_data_dict}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, interaction.guild_id, "location_update:error_generic_update", lang_code, "An error occurred while updating Location {id}: {error_message}")
                await interaction.followup.send(error_msg.format(id=location_id, error_message=str(e)), ephemeral=True); return

            if not updated_location:
                 error_msg = await get_localized_message_template(session, interaction.guild_id, "location_update:error_update_failed_unknown", lang_code, "Location update failed for an unknown reason after attempting to save.")
                 await interaction.followup.send(error_msg, ephemeral=True); return

            success_title_template = await get_localized_message_template(session, interaction.guild_id, "location_update:success_title", lang_code, "Location Updated: {loc_name} (ID: {loc_id})")
            updated_loc_name_display = updated_location.name_i18n.get(lang_code, updated_location.name_i18n.get("en", f"Location {updated_location.id}"))
            embed = discord.Embed(title=success_title_template.format(loc_name=updated_loc_name_display, loc_id=updated_location.id), color=discord.Color.orange())

            field_updated_label = await get_localized_message_template(session, interaction.guild_id, "location_update:label_field_updated", lang_code, "Field Updated")
            new_value_label = await get_localized_message_template(session, interaction.guild_id, "location_update:label_new_value", lang_code, "New Value")

            new_value_display_str = await self._format_json_field_display(interaction, parsed_value, lang_code) if isinstance(parsed_value, (dict, list)) else (await get_localized_message_template(session, interaction.guild_id, "common:value_none", lang_code, "None") if parsed_value is None else (parsed_value.name if isinstance(parsed_value, LocationType) else str(parsed_value)))

            embed.add_field(name=field_updated_label, value=field_to_update, inline=True)
            embed.add_field(name=new_value_label, value=new_value_display_str, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @location_master_cmds.command(name="delete", description="Delete a Location from this guild.")
    @app_commands.describe(location_id="The database ID of the Location to delete.")
    async def location_delete(self, interaction: discord.Interaction, location_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            location_to_delete = await location_crud.get(session, id=location_id, guild_id=interaction.guild_id)
            if not location_to_delete:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "location_delete:error_not_found", lang_code, "Location with ID {id} not found. Nothing to delete.")
                await interaction.followup.send(error_msg.format(id=location_id), ephemeral=True); return

            location_name_for_message = location_to_delete.name_i18n.get(lang_code, location_to_delete.name_i18n.get("en", f"Location {location_to_delete.id}"))

            players_in_location_stmt = select(player_crud.model.id).where(player_crud.model.current_location_id == location_id, player_crud.model.guild_id == interaction.guild_id).limit(1)
            if (await session.execute(players_in_location_stmt)).scalar_one_or_none():
                error_msg = await get_localized_message_template(session, interaction.guild_id, "location_delete:error_player_dependency", lang_code, "Cannot delete Location '{name}' (ID: {id}) as players are currently in it. Please move them first.")
                await interaction.followup.send(error_msg.format(name=location_name_for_message, id=location_id), ephemeral=True); return

            npcs_in_location_stmt = select(npc_crud.model.id).where(npc_crud.model.current_location_id == location_id, npc_crud.model.guild_id == interaction.guild_id).limit(1)
            if (await session.execute(npcs_in_location_stmt)).scalar_one_or_none():
                error_msg = await get_localized_message_template(session, interaction.guild_id, "location_delete:error_npc_dependency", lang_code, "Cannot delete Location '{name}' (ID: {id}) as NPCs are currently in it. Please move them or reassign their location first.")
                await interaction.followup.send(error_msg.format(name=location_name_for_message, id=location_id), ephemeral=True); return

            child_locations_stmt = select(location_crud.model.id).where(location_crud.model.parent_location_id == location_id, location_crud.model.guild_id == interaction.guild_id).limit(1) # type: ignore
            if (await session.execute(child_locations_stmt)).scalar_one_or_none():
                error_msg = await get_localized_message_template(session, interaction.guild_id, "location_delete:error_child_dependency", lang_code, "Cannot delete Location '{name}' (ID: {id}) as it has child locations. Please delete or re-parent them first.")
                await interaction.followup.send(error_msg.format(name=location_name_for_message, id=location_id), ephemeral=True); return

            deleted_location: Optional[Any] = None
            try:
                async with session.begin():
                    all_other_locations = await location_crud.get_multi_by_guild_id(session, guild_id=interaction.guild_id) # type: ignore
                    for other_loc in all_other_locations:
                        if other_loc.id == location_id: continue # type: ignore
                        if isinstance(other_loc.neighbor_locations_json, list): # type: ignore
                            new_neighbors = [n for n in other_loc.neighbor_locations_json if not (isinstance(n, dict) and n.get("target_static_id") == location_to_delete.static_id)] # type: ignore
                            if len(new_neighbors) != len(other_loc.neighbor_locations_json): # type: ignore
                                other_loc.neighbor_locations_json = new_neighbors # type: ignore
                                session.add(other_loc)
                    await session.flush()
                    deleted_location = await location_crud.delete(session, id=location_id, guild_id=interaction.guild_id)

                if deleted_location:
                    success_msg = await get_localized_message_template(session, interaction.guild_id, "location_delete:success", lang_code, "Location '{name}' (ID: {id}) has been deleted successfully.")
                    await interaction.followup.send(success_msg.format(name=location_name_for_message, id=location_id), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "location_delete:error_not_deleted_unknown", lang_code, "Location (ID: {id}) was found but could not be deleted.")
                    await interaction.followup.send(error_msg.format(id=location_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Location {location_id} for guild {interaction.guild_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, interaction.guild_id, "location_delete:error_generic", lang_code, "An error occurred while deleting Location '{name}' (ID: {id}): {error_message}")
                await interaction.followup.send(error_msg.format(name=location_name_for_message, id=location_id, error_message=str(e)), ephemeral=True); return

async def setup(bot: commands.Bot):
    cog = MasterLocationCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterLocationCog loaded.")
