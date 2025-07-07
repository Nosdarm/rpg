import logging
import json
from typing import Dict, Any, Optional, List

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, or_

from src.core.crud.crud_location import location_crud
from src.core.crud.crud_player import player_crud  # For dependency checks
from src.core.crud.crud_npc import npc_crud  # For dependency checks
from src.core.database import get_db_session
from src.core.crud_base_definitions import update_entity
from src.core.localization_utils import get_localized_message_template
from src.models.location import LocationType

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

    @location_master_cmds.command(name="view", description="View details of a specific Location.")
    @app_commands.describe(location_id="The database ID of the Location to view.")
    async def location_view(self, interaction: discord.Interaction, location_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            loc = await location_crud.get(session, id=location_id, guild_id=interaction.guild_id)

            if not loc:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_view:not_found", lang_code,
                    "Location with ID {id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg.format(id=location_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "location_view:title", lang_code,
                "Location Details: {loc_name} (ID: {loc_id})"
            )

            loc_name_display = loc.name_i18n.get(lang_code, loc.name_i18n.get("en", f"Location {loc.id}"))
            embed_title = title_template.format(loc_name=loc_name_display, loc_id=loc.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_green())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"location_view:label_{key}", lang_code, default) # type: ignore

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(loc.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=loc.static_id or "N/A", inline=True)
            embed.add_field(name=await get_label("type", "Type"), value=loc.type.value if loc.type else "N/A", inline=True)
            embed.add_field(name=await get_label("parent_id", "Parent ID"), value=str(loc.parent_location_id) if loc.parent_location_id else "N/A", inline=True)

            async def format_json_field_helper(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str: # Renamed to avoid conflict
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available") # type: ignore
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON") # type: ignore

            name_i18n_str = await format_json_field_helper(loc.name_i18n, "location_view:value_na_json", "location_view:error_serialization")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```" + ("..." if len(name_i18n_str) > 1000 else ""), inline=False)

            desc_i18n_str = await format_json_field_helper(loc.description_i18n, "location_view:value_na_json", "location_view:error_serialization")
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```" + ("..." if len(desc_i18n_str) > 1000 else ""), inline=False)

            props_str = await format_json_field_helper(loc.properties_json, "location_view:value_na_json", "location_view:error_serialization")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{props_str[:1000]}\n```" + ("..." if len(props_str) > 1000 else ""), inline=False)

            neighbors_str = await format_json_field_helper(loc.neighbor_locations_json, "location_view:value_na_json", "location_view:error_serialization")
            embed.add_field(name=await get_label("neighbors", "Neighbor Locations JSON"), value=f"```json\n{neighbors_str[:1000]}\n```" + ("..." if len(neighbors_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @location_master_cmds.command(name="list", description="List Locations in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of Locations per page.")
    async def location_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
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
            locations = await location_crud.get_multi(session, guild_id=interaction.guild_id, skip=offset, limit=limit)

            total_locations_stmt = select(func.count(location_crud.model.id)).where(location_crud.model.guild_id == interaction.guild_id)
            total_locations_result = await session.execute(total_locations_stmt)
            total_locations = total_locations_result.scalar_one_or_none() or 0

            if not locations:
                no_locs_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_list:no_locations_found_page", lang_code,
                    "No Locations found for this guild (Page {page})."
                )
                await interaction.followup.send(no_locs_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "location_list:title", lang_code,
                "Location List (Page {page} of {total_pages})"
            )
            total_pages = ((total_locations - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_blue())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "location_list:footer", lang_code,
                "Displaying {count} of {total} total Locations."
            ) # type: ignore
            embed.set_footer(text=footer_template.format(count=len(locations), total=total_locations))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "location_list:location_field_name", lang_code,
                "ID: {loc_id} | {loc_name} (Static: {static_id})"
            ) # type: ignore
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "location_list:location_field_value", lang_code,
                "Type: {type}, Parent ID: {parent_id}, Neighbors: {neighbor_count}"
            ) # type: ignore

            for loc in locations:
                loc_name_display = loc.name_i18n.get(lang_code, loc.name_i18n.get("en", f"Location {loc.id}"))
                neighbor_count = len(loc.neighbor_locations_json) if loc.neighbor_locations_json else 0
                embed.add_field(
                    name=field_name_template.format(loc_id=loc.id, loc_name=loc_name_display, static_id=loc.static_id or "N/A"),
                    value=field_value_template.format(
                        type=loc.type.value if loc.type else "N/A",
                        parent_id=str(loc.parent_location_id) if loc.parent_location_id else "N/A",
                        neighbor_count=neighbor_count
                    ),
                    inline=False
                )

            if len(embed.fields) == 0:
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_list:no_locations_to_display", lang_code,
                    "No Locations found to display on page {page}."
                )
                await interaction.followup.send(no_display_msg.format(page=page), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @location_master_cmds.command(name="create", description="Create a new Location in this guild.")
    @app_commands.describe(
        static_id="Optional: Static ID for this Location (must be unique within the guild).",
        name_i18n_json="JSON string for Location name (e.g., {\"en\": \"Town Square\", \"ru\": \"Городская площадь\"}).",
        type_name="Type of location (e.g., TOWN, FOREST, DUNGEON_ROOM, BUILDING_INTERIOR). See LocationType enum.",
        description_i18n_json="Optional: JSON string for Location description.",
        parent_location_id="Optional: Database ID of the parent Location.",
        properties_json="Optional: JSON string for additional Location properties.",
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
        parsed_name_i18n: Dict[str, str]
        parsed_description_i18n: Optional[Dict[str, str]] = None
        parsed_properties: Optional[Dict[str, Any]] = None
        parsed_neighbors: Optional[List[Dict[str, Any]]] = None
        parsed_location_type: LocationType
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            try:
                parsed_location_type = LocationType[type_name.upper()]
            except KeyError:
                valid_types = ", ".join([lt.name for lt in LocationType])
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_create:error_invalid_type", lang_code,
                    "Invalid type_name '{type_val}'. Valid types: {valid_list}"
                )
                await interaction.followup.send(error_msg.format(type_val=type_name, valid_list=valid_types), ephemeral=True)
                return

            if parent_location_id:
                parent_loc = await location_crud.get(session, id=parent_location_id, guild_id=interaction.guild_id)
                if not parent_loc:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "location_create:error_parent_not_found", lang_code,
                        "Parent Location with ID {id} not found."
                    )
                    await interaction.followup.send(error_msg.format(id=parent_location_id), ephemeral=True)
                    return

            if static_id:
                existing_loc_static = await location_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=static_id)
                if existing_loc_static:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "location_create:error_static_id_exists", lang_code,
                        "A Location with static_id '{id}' already exists."
                    )
                    await interaction.followup.send(error_msg.format(id=static_id), ephemeral=True)
                    return

            try:
                parsed_name_i18n = json.loads(name_i18n_json)
                if not isinstance(parsed_name_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_name_i18n.items()):
                    raise ValueError("name_i18n_json must be a dict of str:str.")
                if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code):
                     raise ValueError("name_i18n_json must contain 'en' or current language key.")

                if description_i18n_json:
                    parsed_description_i18n = json.loads(description_i18n_json)
                    if not isinstance(parsed_description_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_description_i18n.items()):
                        raise ValueError("description_i18n_json must be a dict of str:str.")

                if properties_json:
                    parsed_properties = json.loads(properties_json)
                    if not isinstance(parsed_properties, dict):
                        raise ValueError("properties_json must be a dictionary.")

                if neighbor_locations_json:
                    parsed_neighbors = json.loads(neighbor_locations_json)
                    if not isinstance(parsed_neighbors, list) or not all(isinstance(n, dict) for n in parsed_neighbors):
                        raise ValueError("neighbor_locations_json must be a list of dictionaries.")
                    for neighbor_entry in parsed_neighbors:
                        if not isinstance(neighbor_entry.get("target_static_id"), str):
                            raise ValueError("Each entry in neighbor_locations_json must have a 'target_static_id' (string).")
                        if "description_i18n" in neighbor_entry and (
                            not isinstance(neighbor_entry["description_i18n"], dict) or \
                            not all(isinstance(k, str) and isinstance(v, str) for k,v in neighbor_entry["description_i18n"].items())
                        ):
                            raise ValueError("Neighbor 'description_i18n' must be a dict of str:str if provided.")
            except ValueError as e: # Specific exception first
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_create:error_invalid_json_format", lang_code,
                    "Invalid JSON format or structure for one of the input fields: {error_details}"
                )
                await interaction.followup.send(error_msg.format(error_details=str(e)), ephemeral=True)
                return
            # JSONDecodeError is a subclass of ValueError, so this block is unreachable if ValueError is caught first.
            # except json.JSONDecodeError as e:
            #     error_msg = await get_localized_message_template(
            #         session, interaction.guild_id, "location_create:error_invalid_json_format", lang_code,
            #         "Invalid JSON format or structure for one of the input fields: {error_details}"
            #     )
            #     await interaction.followup.send(error_msg.format(error_details=str(e)), ephemeral=True)
            #     return

            location_data_to_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id, # Ensured not None by early check
                "static_id": static_id,
                "name_i18n": parsed_name_i18n,
                "description_i18n": parsed_description_i18n if parsed_description_i18n else {},
                "type": parsed_location_type,
                "parent_location_id": parent_location_id,
                "properties_json": parsed_properties if parsed_properties else {},
                "neighbor_locations_json": parsed_neighbors if parsed_neighbors else [],
            }

            created_location: Optional[Any] = None
            try:
                async with session.begin():
                    created_location = await location_crud.create_with_guild(session, obj_in=location_data_to_create, guild_id=interaction.guild_id) # type: ignore
                    await session.flush()
                    if created_location:
                         await session.refresh(created_location)
            except Exception as e:
                logger.error(f"Error creating Location with data {location_data_to_create}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_create:error_generic_create", lang_code,
                    "An error occurred while creating the Location: {error_message}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(error_message=str(e)), ephemeral=True)
                return

            if not created_location:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_create:error_creation_failed_unknown", lang_code,
                    "Location creation failed for an unknown reason."
                ) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "location_create:success_title", lang_code,
                "Location Created: {loc_name} (ID: {loc_id})"
            ) # type: ignore
            created_loc_name_display = created_location.name_i18n.get(lang_code, created_location.name_i18n.get("en", f"Location {created_location.id}"))

            embed = discord.Embed(title=success_title_template.format(loc_name=created_loc_name_display, loc_id=created_location.id), color=discord.Color.green())
            embed.add_field(name="Static ID", value=created_location.static_id or "N/A", inline=True)
            embed.add_field(name="Type", value=created_location.type.value, inline=True)
            embed.add_field(name="Parent ID", value=str(created_location.parent_location_id) if created_location.parent_location_id else "N/A", inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @location_master_cmds.command(name="update", description="Update a specific field for a Location.")
    @app_commands.describe(
        location_id="The database ID of the Location to update.",
        field_to_update="Field to update (e.g., static_id, name_i18n_json, type_name, parent_location_id, properties_json, neighbor_locations_json).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable fields; enum name for type_name)."
    )
    async def location_update(self, interaction: discord.Interaction, location_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        allowed_fields = {
            "static_id": (str, type(None)),
            "name_i18n": dict, # from name_i18n_json
            "description_i18n": dict, # from description_i18n_json
            "type": LocationType, # from type_name
            "parent_location_id": (int, type(None)),
            "properties_json": dict,
            "neighbor_locations_json": list,
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()
        db_field_name = field_to_update_lower

        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")
        elif field_to_update_lower == "type_name": # map type_name from command to 'type' in DB
            db_field_name = "type"

        field_type_info = allowed_fields.get(db_field_name)

        if not field_type_info:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "location_update:error_field_not_allowed", lang_code,
                    "Field '{field_name}' is not allowed for update. Allowed: {allowed_list}"
                ) # type: ignore
            # Show user-friendly field names
            user_friendly_allowed_keys = [k[:-5] if k.endswith("_json") else ("type_name" if k == "type" else k) for k in allowed_fields.keys()]
            await interaction.followup.send(error_msg.format(field_name=field_to_update, allowed_list=', '.join(user_friendly_allowed_keys)), ephemeral=True)
            return

        parsed_value: Any = None
        async with get_db_session() as session:
            try:
                if db_field_name == "static_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = new_value
                        if parsed_value is not None: # This check is a bit redundant due to the one above, but safe
                            existing_loc_static = await location_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                            if existing_loc_static and existing_loc_static.id != location_id:
                                error_msg = await get_localized_message_template(
                                    session, interaction.guild_id, "location_update:error_static_id_exists", lang_code,
                                    "Another Location with static_id '{id}' already exists."
                                ) # type: ignore
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True)
                                return
                elif db_field_name in ["name_i18n", "description_i18n", "properties_json"]:
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict):
                        raise ValueError(f"{db_field_name} must be a dictionary.")
                elif db_field_name == "neighbor_locations_json":
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, list) or not all(isinstance(n, dict) for n in parsed_value):
                        raise ValueError("neighbor_locations_json must be a list of dictionaries.")
                    for neighbor_entry in parsed_value:
                        if not isinstance(neighbor_entry.get("target_static_id"), str):
                            raise ValueError("Neighbor entry missing 'target_static_id'.")
                elif db_field_name == "type":
                    try:
                        parsed_value = LocationType[new_value.upper()]
                    except KeyError:
                        valid_types = ", ".join([lt.name for lt in LocationType])
                        error_msg = await get_localized_message_template(
                            session, interaction.guild_id, "location_update:error_invalid_type", lang_code,
                            "Invalid type_name '{value}'. Valid types: {types}"
                        ) # type: ignore
                        await interaction.followup.send(error_msg.format(value=new_value, types=valid_types), ephemeral=True)
                        return
                elif db_field_name == "parent_location_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = int(new_value)
                        if parsed_value is not None:
                            parent_loc = await location_crud.get(session, id=parsed_value, guild_id=interaction.guild_id)
                            if not parent_loc:
                                error_msg = await get_localized_message_template(
                                    session, interaction.guild_id, "location_update:error_parent_not_found", lang_code,
                                    "Parent Location with ID {id} not found."
                                ) # type: ignore
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True)
                                return
                            if parent_loc.id == location_id:
                                error_msg = await get_localized_message_template(
                                    session, interaction.guild_id, "location_update:error_self_parent", lang_code,
                                    "Location cannot be its own parent."
                                ) # type: ignore
                                await interaction.followup.send(error_msg, ephemeral=True)
                                return
                else:
                     error_msg = await get_localized_message_template(
                         session, interaction.guild_id, "location_update:error_unknown_field_type", lang_code,
                        "Internal error: Unknown field type for '{field_name}'."
                    ) # type: ignore
                     await interaction.followup.send(error_msg.format(field_name=db_field_name), ephemeral=True)
                     return
            except ValueError as e: # Specific exception first
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_update:error_invalid_value_type", lang_code,
                    "Invalid value '{value}' for field '{field_name}'. Details: {details}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True)
                return
            # JSONDecodeError is a subclass of ValueError, so this block is unreachable if ValueError is caught first.
            # except json.JSONDecodeError as e:
            #     error_msg = await get_localized_message_template(
            #         session, interaction.guild_id, "location_update:error_invalid_json", lang_code,
            #         "Invalid JSON string '{value}' for field '{field_name}'. Details: {details}"
            #     ) # type: ignore
            #     await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True)
            #     return

            location_to_update = await location_crud.get(session, id=location_id, guild_id=interaction.guild_id)
            if not location_to_update:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_update:error_location_not_found", lang_code,
                    "Location with ID {id} not found."
                ) # type: ignore
                await interaction.followup.send(error_msg.format(id=location_id), ephemeral=True)
                return

            update_data_dict = {db_field_name: parsed_value}
            updated_location: Optional[Any] = None
            try:
                async with session.begin():
                    updated_location = await update_entity(session, entity=location_to_update, data=update_data_dict)
                    await session.flush()
                    if updated_location: # Refresh only if not None
                        await session.refresh(updated_location)
            except Exception as e:
                logger.error(f"Error updating Location {location_id} with data {update_data_dict}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_update:error_generic_update", lang_code,
                    "An error occurred while updating Location {id}: {error_message}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(id=location_id, error_message=str(e)), ephemeral=True)
                return

            if not updated_location: # Check after potential refresh
                 error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_update:error_update_failed_unknown", lang_code,
                    "Location update failed for an unknown reason after attempting to save."
                ) # type: ignore
                 await interaction.followup.send(error_msg, ephemeral=True)
                 return


            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "location_update:success_title", lang_code,
                "Location Updated: {loc_name} (ID: {loc_id})"
            ) # type: ignore
            updated_loc_name_display = updated_location.name_i18n.get(lang_code, updated_location.name_i18n.get("en", f"Location {updated_location.id}"))
            embed = discord.Embed(title=success_title_template.format(loc_name=updated_loc_name_display, loc_id=updated_location.id), color=discord.Color.orange())

            field_updated_label = await get_localized_message_template(session, interaction.guild_id, "location_update:label_field_updated", lang_code, "Field Updated") # type: ignore
            new_value_label = await get_localized_message_template(session, interaction.guild_id, "location_update:label_new_value", lang_code, "New Value") # type: ignore

            new_value_display = str(parsed_value)
            if isinstance(parsed_value, (dict, list)):
                new_value_display = f"```json\n{json.dumps(parsed_value, indent=2, ensure_ascii=False)}\n```"
            elif isinstance(parsed_value, LocationType):
                new_value_display = parsed_value.name
            elif parsed_value is None:
                 new_value_display = "None"

            embed.add_field(name=field_updated_label, value=field_to_update, inline=True)
            embed.add_field(name=new_value_label, value=new_value_display, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @location_master_cmds.command(name="delete", description="Delete a Location from this guild.")
    @app_commands.describe(location_id="The database ID of the Location to delete.")
    async def location_delete(self, interaction: discord.Interaction, location_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        lang_code = str(interaction.locale)
        async with get_db_session() as session:
            location_to_delete = await location_crud.get(session, id=location_id, guild_id=interaction.guild_id)

            if not location_to_delete:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_delete:error_not_found", lang_code,
                    "Location with ID {id} not found. Nothing to delete."
                ) # type: ignore
                await interaction.followup.send(error_msg.format(id=location_id), ephemeral=True)
                return

            location_name_for_message = location_to_delete.name_i18n.get(lang_code, location_to_delete.name_i18n.get("en", f"Location {location_to_delete.id}"))

            players_in_location_stmt = select(player_crud.model.id).where(player_crud.model.current_location_id == location_id, player_crud.model.guild_id == interaction.guild_id).limit(1)
            player_dependency = (await session.execute(players_in_location_stmt)).scalar_one_or_none()
            if player_dependency:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_delete:error_player_dependency", lang_code,
                    "Cannot delete Location '{name}' (ID: {id}) as players are currently in it. Please move them first."
                ) # type: ignore
                await interaction.followup.send(error_msg.format(name=location_name_for_message, id=location_id), ephemeral=True)
                return

            npcs_in_location_stmt = select(npc_crud.model.id).where(npc_crud.model.current_location_id == location_id, npc_crud.model.guild_id == interaction.guild_id).limit(1)
            npc_dependency = (await session.execute(npcs_in_location_stmt)).scalar_one_or_none()
            if npc_dependency:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_delete:error_npc_dependency", lang_code,
                    "Cannot delete Location '{name}' (ID: {id}) as NPCs are currently in it. Please move them or reassign their location first."
                ) # type: ignore
                await interaction.followup.send(error_msg.format(name=location_name_for_message, id=location_id), ephemeral=True)
                return

            child_locations_stmt = select(location_crud.model.id).where(location_crud.model.parent_location_id == location_id, location_crud.model.guild_id == interaction.guild_id).limit(1) # type: ignore
            child_dependency = (await session.execute(child_locations_stmt)).scalar_one_or_none()
            if child_dependency:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_delete:error_child_dependency", lang_code,
                    "Cannot delete Location '{name}' (ID: {id}) as it has child locations. Please delete or re-parent them first."
                ) # type: ignore
                await interaction.followup.send(error_msg.format(name=location_name_for_message, id=location_id), ephemeral=True)
                return

            deleted_location: Optional[Any] = None
            try:
                async with session.begin():
                    all_other_locations = await location_crud.get_multi_by_guild_id(session, guild_id=interaction.guild_id) # type: ignore
                    updated_other_locations = False
                    for other_loc in all_other_locations:
                        if other_loc.id == location_id: # type: ignore
                            continue
                        if other_loc.neighbor_locations_json: # type: ignore
                            new_neighbors = []
                            changed = False
                            for neighbor_link in other_loc.neighbor_locations_json: # type: ignore
                                if isinstance(neighbor_link, dict) and neighbor_link.get("target_static_id") == location_to_delete.static_id:
                                    changed = True
                                    continue
                                new_neighbors.append(neighbor_link)
                            if changed:
                                other_loc.neighbor_locations_json = new_neighbors # type: ignore
                                session.add(other_loc)
                                updated_other_locations = True
                    if updated_other_locations:
                        await session.flush()
                    deleted_location = await location_crud.delete(session, id=location_id, guild_id=interaction.guild_id)

                if deleted_location:
                    success_msg = await get_localized_message_template(
                        session, interaction.guild_id, "location_delete:success", lang_code,
                        "Location '{name}' (ID: {id}) has been deleted successfully."
                    ) # type: ignore
                    await interaction.followup.send(success_msg.format(name=location_name_for_message, id=location_id), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "location_delete:error_not_deleted_unknown", lang_code,
                        "Location (ID: {id}) was found but could not be deleted."
                    ) # type: ignore
                    await interaction.followup.send(error_msg.format(id=location_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Location {location_id} for guild {interaction.guild_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "location_delete:error_generic", lang_code,
                    "An error occurred while deleting Location '{name}' (ID: {id}): {error_message}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(name=location_name_for_message, id=location_id, error_message=str(e)), ephemeral=True)
                return

async def setup(bot: commands.Bot):
    cog = MasterLocationCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterLocationCog loaded.")
