import logging
import json
from typing import Dict, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

from src.core.crud.crud_faction import crud_faction
from src.core.crud.crud_npc import npc_crud # For dependency validation
from src.core.database import get_db_session
from src.core.crud_base_definitions import update_entity
from src.core.localization_utils import get_localized_message_template

logger = logging.getLogger(__name__)

class MasterFactionCog(commands.Cog, name="Master Faction Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterFactionCog initialized.")

    faction_master_cmds = app_commands.Group(
        name="master_faction",
        description="Master commands for managing Generated Factions.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    @faction_master_cmds.command(name="view", description="View details of a specific Faction.")
    @app_commands.describe(faction_id="The database ID of the Faction to view.")
    async def faction_view(self, interaction: discord.Interaction, faction_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.") # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            faction = await crud_faction.get(session, id=faction_id, guild_id=interaction.guild_id)

            if not faction:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_view:not_found", lang_code,
                    "Faction with ID {id} not found in this guild."
                ) # type: ignore
                await interaction.followup.send(not_found_msg.format(id=faction_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "faction_view:title", lang_code,
                "Faction Details: {faction_name} (ID: {faction_id})"
            ) # type: ignore

            faction_name_display = faction.name_i18n.get(lang_code, faction.name_i18n.get("en", f"Faction {faction.id}"))
            embed_title = title_template.format(faction_name=faction_name_display, faction_id=faction.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_red())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"faction_view:label_{key}", lang_code, default) # type: ignore

            async def format_json_field_helper(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str: # Renamed
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available") # type: ignore
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON") # type: ignore

            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A") # type: ignore

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(faction.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=faction.static_id or na_value_str, inline=True)
            leader_npc_sid = getattr(faction, 'leader_npc_static_id', None)
            embed.add_field(name=await get_label("leader_npc_id", "Leader NPC Static ID"), value=leader_npc_sid or na_value_str, inline=True)


            name_i18n_str = await format_json_field_helper(faction.name_i18n, "faction_view:value_na_json", "faction_view:error_serialization_name")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```" + ("..." if len(name_i18n_str) > 1000 else ""), inline=False)

            desc_i18n_str = await format_json_field_helper(faction.description_i18n, "faction_view:value_na_json", "faction_view:error_serialization_desc")
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```" + ("..." if len(desc_i18n_str) > 1000 else ""), inline=False)

            ideology_i18n_str = await format_json_field_helper(faction.ideology_i18n, "faction_view:value_na_json", "faction_view:error_serialization_ideology")
            embed.add_field(name=await get_label("ideology_i18n", "Ideology (i18n)"), value=f"```json\n{ideology_i18n_str[:1000]}\n```" + ("..." if len(ideology_i18n_str) > 1000 else ""), inline=False)

            resources_str = await format_json_field_helper(faction.resources_json, "faction_view:value_na_json", "faction_view:error_serialization_resources")
            embed.add_field(name=await get_label("resources", "Resources JSON"), value=f"```json\n{resources_str[:1000]}\n```" + ("..." if len(resources_str) > 1000 else ""), inline=False)

            ai_meta_str = await format_json_field_helper(faction.ai_metadata_json, "faction_view:value_na_json", "faction_view:error_serialization_ai_meta")
            embed.add_field(name=await get_label("ai_metadata", "AI Metadata JSON"), value=f"```json\n{ai_meta_str[:1000]}\n```" + ("..." if len(ai_meta_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @faction_master_cmds.command(name="list", description="List Generated Factions in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of Factions per page.")
    async def faction_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.") # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            offset = (page - 1) * limit
            # Assuming get_multi_by_guild_id is the correct method name
            factions = await crud_faction.get_multi_by_guild_id(session, guild_id=interaction.guild_id, skip=offset, limit=limit)

            total_factions_stmt = select(func.count(crud_faction.model.id)).where(crud_faction.model.guild_id == interaction.guild_id)
            total_factions_result = await session.execute(total_factions_stmt)
            total_factions = total_factions_result.scalar_one_or_none() or 0

            if not factions:
                no_factions_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_list:no_factions_found_page", lang_code,
                    "No Factions found for this guild (Page {page})."
                ) # type: ignore
                await interaction.followup.send(no_factions_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "faction_list:title", lang_code,
                "Faction List (Page {page} of {total_pages})"
            ) # type: ignore
            total_pages = ((total_factions - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_magenta())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "faction_list:footer", lang_code,
                "Displaying {count} of {total} total Factions."
            ) # type: ignore
            embed.set_footer(text=footer_template.format(count=len(factions), total=total_factions))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "faction_list:faction_field_name", lang_code,
                "ID: {faction_id} | {faction_name} (Static: {static_id})"
            ) # type: ignore
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "faction_list:faction_field_value", lang_code,
                "Leader NPC Static ID: {leader_id}"
            ) # type: ignore

            for f in factions:
                na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A") # type: ignore
                faction_name_display = f.name_i18n.get(lang_code, f.name_i18n.get("en", f"Faction {f.id}"))
                leader_npc_sid = getattr(f, 'leader_npc_static_id', None)
                embed.add_field(
                    name=field_name_template.format(faction_id=f.id, faction_name=faction_name_display, static_id=f.static_id or na_value_str),
                    value=field_value_template.format(leader_id=leader_npc_sid or na_value_str),
                    inline=False
                )

            if len(embed.fields) == 0: # Should not happen if `not factions` check passes, but good for safety
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_list:no_factions_to_display", lang_code,
                    "No Factions found to display on page {page}."
                ) # type: ignore
                await interaction.followup.send(no_display_msg.format(page=page), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @faction_master_cmds.command(name="create", description="Create a new Generated Faction in this guild.")
    @app_commands.describe(
        static_id="Static ID for this Faction (must be unique within the guild).",
        name_i18n_json="JSON string for Faction name (e.g., {\"en\": \"The Guardians\", \"ru\": \"Стражи\"}).",
        description_i18n_json="Optional: JSON string for Faction description.",
        ideology_i18n_json="Optional: JSON string for Faction ideology.",
        leader_npc_static_id="Optional: Static ID of the NPC who leads this faction (must exist).",
        resources_json="Optional: JSON string for Faction resources.",
        ai_metadata_json="Optional: JSON string for AI metadata related to this faction."
    )
    async def faction_create(self, interaction: discord.Interaction,
                             static_id: str,
                             name_i18n_json: str,
                             description_i18n_json: Optional[str] = None,
                             ideology_i18n_json: Optional[str] = None,
                             leader_npc_static_id: Optional[str] = None,
                             resources_json: Optional[str] = None,
                             ai_metadata_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)

        lang_code = str(interaction.locale)
        parsed_name_i18n: Dict[str, str]
        parsed_desc_i18n: Optional[Dict[str, str]] = None
        parsed_ideology_i18n: Optional[Dict[str, str]] = None
        parsed_resources: Optional[Dict[str, Any]] = None
        parsed_ai_meta: Optional[Dict[str, Any]] = None
        if interaction.guild_id is None: # lang_code already defined
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.") # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        async with get_db_session() as session:
            existing_faction_static = await crud_faction.get_by_static_id(session, guild_id=interaction.guild_id, static_id=static_id)
            if existing_faction_static:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_create:error_static_id_exists", lang_code,
                    "A Faction with static_id '{id}' already exists."
                ) # type: ignore
                await interaction.followup.send(error_msg.format(id=static_id), ephemeral=True)
                return

            if leader_npc_static_id:
                leader_npc = await npc_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=leader_npc_static_id)
                if not leader_npc:
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "faction_create:error_leader_npc_not_found", lang_code,
                        "Leader NPC with static_id '{id}' not found in this guild."
                    ) # type: ignore
                    await interaction.followup.send(error_msg.format(id=leader_npc_static_id), ephemeral=True)
                    return

            try:
                parsed_name_i18n = json.loads(name_i18n_json)
                error_detail_name_format = await get_localized_message_template(session, interaction.guild_id, "faction_create:error_detail_name_format", lang_code, "name_i18n_json must be a dictionary of string keys and string values.") # type: ignore
                error_detail_name_lang = await get_localized_message_template(session, interaction.guild_id, "faction_create:error_detail_name_lang", lang_code, "name_i18n_json must contain 'en' or current language key.") # type: ignore
                error_detail_desc_format = await get_localized_message_template(session, interaction.guild_id, "faction_create:error_detail_desc_format", lang_code, "description_i18n_json must be a dictionary of string keys and string values.") # type: ignore
                error_detail_ideology_format = await get_localized_message_template(session, interaction.guild_id, "faction_create:error_detail_ideology_format", lang_code, "ideology_i18n_json must be a dictionary of string keys and string values.") # type: ignore
                error_detail_resources_format = await get_localized_message_template(session, interaction.guild_id, "faction_create:error_detail_resources_format", lang_code, "resources_json must be a dictionary.") # type: ignore
                error_detail_ai_meta_format = await get_localized_message_template(session, interaction.guild_id, "faction_create:error_detail_ai_meta_format", lang_code, "ai_metadata_json must be a dictionary.") # type: ignore

                if not isinstance(parsed_name_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_name_i18n.items()):
                    raise ValueError(error_detail_name_format)
                if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code):
                     raise ValueError(error_detail_name_lang)

                if description_i18n_json:
                    parsed_desc_i18n = json.loads(description_i18n_json)
                    if not isinstance(parsed_desc_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_desc_i18n.items()):
                        raise ValueError(error_detail_desc_format)

                if ideology_i18n_json:
                    parsed_ideology_i18n = json.loads(ideology_i18n_json)
                    if not isinstance(parsed_ideology_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed_ideology_i18n.items()):
                        raise ValueError(error_detail_ideology_format)

                if resources_json:
                    parsed_resources = json.loads(resources_json)
                    if not isinstance(parsed_resources, dict):
                        raise ValueError(error_detail_resources_format)

                if ai_metadata_json:
                    parsed_ai_meta = json.loads(ai_metadata_json)
                    if not isinstance(parsed_ai_meta, dict):
                        raise ValueError(error_detail_ai_meta_format)
            except ValueError as e: # Specific exception first
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_create:error_invalid_json_format", lang_code,
                    "Invalid JSON format or structure for one of the input fields: {error_details}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(error_details=str(e)), ephemeral=True)
                return
            # JSONDecodeError is a subclass of ValueError, so this block is unreachable if ValueError is caught first.
            # except json.JSONDecodeError as e:
            #     error_msg = await get_localized_message_template(
            #         session, interaction.guild_id, "faction_create:error_invalid_json_format", lang_code,
            #         "Invalid JSON format or structure for one of the input fields: {error_details}"
            #     ) # type: ignore
            #     await interaction.followup.send(error_msg.format(error_details=str(e)), ephemeral=True)
            #     return


            faction_data_to_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id, # Already checked not None
                "static_id": static_id,
                "name_i18n": parsed_name_i18n,
                "description_i18n": parsed_desc_i18n if parsed_desc_i18n else {},
                "ideology_i18n": parsed_ideology_i18n if parsed_ideology_i18n else {},
                "leader_npc_static_id": leader_npc_static_id,
                "resources_json": parsed_resources if parsed_resources else {},
                "ai_metadata_json": parsed_ai_meta if parsed_ai_meta else {},
            }

            created_faction: Optional[Any] = None
            try:
                async with session.begin():
                    # guild_id is already in faction_data_to_create and handled by CRUDBase.create
                    created_faction = await crud_faction.create(session, obj_in=faction_data_to_create)
                    await session.flush()
                    if created_faction:
                         await session.refresh(created_faction)
            except Exception as e:
                logger.error(f"Error creating Faction with data {faction_data_to_create}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_create:error_generic_create", lang_code,
                    "An error occurred while creating the Faction: {error_message}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(error_message=str(e)), ephemeral=True)
                return

            if not created_faction:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_create:error_creation_failed_unknown", lang_code,
                    "Faction creation failed for an unknown reason."
                ) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "faction_create:success_title", lang_code,
                "Faction Created: {faction_name} (ID: {faction_id})"
            ) # type: ignore
            created_faction_name_display = created_faction.name_i18n.get(lang_code, created_faction.name_i18n.get("en", f"Faction {created_faction.id}"))

            async def get_created_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"faction_create:label_{key}", lang_code, default) # type: ignore
            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A") # type: ignore

            embed = discord.Embed(title=success_title_template.format(faction_name=created_faction_name_display, faction_id=created_faction.id), color=discord.Color.green())
            embed.add_field(name=await get_created_label("static_id", "Static ID"), value=created_faction.static_id, inline=True)
            leader_npc_sid = getattr(created_faction, 'leader_npc_static_id', None)
            embed.add_field(name=await get_created_label("leader_npc_sid", "Leader NPC Static ID"), value=leader_npc_sid or na_value_str, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @faction_master_cmds.command(name="update", description="Update a specific field for a Faction.")
    @app_commands.describe(
        faction_id="The database ID of the Faction to update.",
        field_to_update="Field to update (e.g., static_id, name_i18n_json, leader_npc_static_id, resources_json).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable string fields)."
    )
    async def faction_update(self, interaction: discord.Interaction, faction_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.") # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        allowed_fields = {
            "static_id": str,
            "name_i18n": dict, # from name_i18n_json
            "description_i18n": dict, # from description_i18n_json
            "ideology_i18n": dict, # from ideology_i18n_json
            "leader_npc_static_id": (str, type(None)),
            "resources_json": dict,
            "ai_metadata_json": dict,
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()
        db_field_name = field_to_update_lower
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")

        field_type_info = allowed_fields.get(db_field_name)

        if not field_type_info:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "faction_update:error_field_not_allowed", lang_code,
                    "Field '{field_name}' is not allowed for update. Allowed: {allowed_list}"
                ) # type: ignore
            await interaction.followup.send(error_msg.format(field_name=field_to_update, allowed_list=', '.join(allowed_fields.keys())), ephemeral=True)
            return

        parsed_value: Any = None
        async with get_db_session() as session:
            try:
                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: raise ValueError("static_id cannot be empty.")
                    existing_faction_static = await crud_faction.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                    if existing_faction_static and existing_faction_static.id != faction_id:
                        error_msg = await get_localized_message_template(
                            session, interaction.guild_id, "faction_update:error_static_id_exists", lang_code,
                            "Another Faction with static_id '{id}' already exists."
                        ) # type: ignore
                        await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True)
                        return
                elif db_field_name in ["name_i18n", "description_i18n", "ideology_i18n", "resources_json", "ai_metadata_json"]:
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict):
                        raise ValueError(f"{db_field_name} must be a dictionary.")
                elif db_field_name == "leader_npc_static_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = new_value
                        if parsed_value is not None: # Check if not None before DB call
                            leader_npc = await npc_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                            if not leader_npc:
                                error_msg = await get_localized_message_template(
                                    session, interaction.guild_id, "faction_update:error_leader_npc_not_found", lang_code,
                                    "Leader NPC with static_id '{id}' not found."
                                ) # type: ignore
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True)
                                return
                else: # Should not be reached
                     error_msg = await get_localized_message_template(
                         session, interaction.guild_id, "faction_update:error_unknown_field_type", lang_code,
                        "Internal error: Unknown field type for '{field_name}'."
                    ) # type: ignore
                     await interaction.followup.send(error_msg.format(field_name=db_field_name), ephemeral=True)
                     return
            except ValueError as e: # Specific exception first
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_update:error_invalid_value_type", lang_code,
                    "Invalid value '{value}' for field '{field_name}'. Details: {details}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True)
                return
            # JSONDecodeError is a subclass of ValueError, so this block is unreachable if ValueError is caught first.
            # except json.JSONDecodeError as e:
            #     error_msg = await get_localized_message_template(
            #         session, interaction.guild_id, "faction_update:error_invalid_json", lang_code,
            #         "Invalid JSON string '{value}' for field '{field_name}'. Details: {details}"
            #     ) # type: ignore
            #     await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True)
            #     return

            faction_to_update = await crud_faction.get(session, id=faction_id, guild_id=interaction.guild_id)
            if not faction_to_update:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_update:error_faction_not_found", lang_code,
                    "Faction with ID {id} not found."
                ) # type: ignore
                await interaction.followup.send(error_msg.format(id=faction_id), ephemeral=True)
                return

            update_data_dict = {db_field_name: parsed_value}
            updated_faction: Optional[Any] = None
            try:
                async with session.begin():
                    updated_faction = await update_entity(session, entity=faction_to_update, data=update_data_dict)
                    await session.flush()
                    if updated_faction: # Refresh only if not None
                        await session.refresh(updated_faction)
            except Exception as e:
                logger.error(f"Error updating Faction {faction_id} with data {update_data_dict}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_update:error_generic_update", lang_code,
                    "An error occurred while updating Faction {id}: {error_message}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(id=faction_id, error_message=str(e)), ephemeral=True)
                return

            if not updated_faction: # Check after potential refresh
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_update:error_update_failed_unknown", lang_code,
                    "Faction update failed for an unknown reason."
                ) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "faction_update:success_title", lang_code,
                "Faction Updated: {faction_name} (ID: {faction_id})"
            ) # type: ignore
            updated_faction_name_display = updated_faction.name_i18n.get(lang_code, updated_faction.name_i18n.get("en", f"Faction {updated_faction.id}")) if hasattr(updated_faction, 'name_i18n') and updated_faction.name_i18n else f"Faction {updated_faction.id}" # type: ignore
            embed = discord.Embed(title=success_title_template.format(faction_name=updated_faction_name_display, faction_id=updated_faction.id), color=discord.Color.orange()) # type: ignore

            field_updated_label = await get_localized_message_template(session, interaction.guild_id, "faction_update:label_field_updated", lang_code, "Field Updated") # type: ignore
            new_value_label = await get_localized_message_template(session, interaction.guild_id, "faction_update:label_new_value", lang_code, "New Value") # type: ignore

            new_value_display_str: str
            if parsed_value is None:
                new_value_display_str = await get_localized_message_template(session, interaction.guild_id, "common:value_none", lang_code, "None") # type: ignore
            elif isinstance(parsed_value, (dict, list)):
                try:
                    json_str = json.dumps(parsed_value, indent=2, ensure_ascii=False)
                    new_value_display_str = f"```json\n{json_str[:1000]}\n```"
                    if len(json_str) > 1000: new_value_display_str += "..."
                except TypeError:
                    new_value_display_str = await get_localized_message_template(session, interaction.guild_id, "faction_update:error_serialization_new_value", lang_code, "Error displaying new value (non-serializable JSON).") # type: ignore
            else:
                new_value_display_str = str(parsed_value)

            embed.add_field(name=field_updated_label, value=field_to_update, inline=True)
            embed.add_field(name=new_value_label, value=new_value_display, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @faction_master_cmds.command(name="delete", description="Delete a Faction from this guild.")
    @app_commands.describe(faction_id="The database ID of the Faction to delete.")
    async def faction_delete(self, interaction: discord.Interaction, faction_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.") # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        # lang_code = str(interaction.locale) # Already defined
        async with get_db_session() as session:
            faction_to_delete = await crud_faction.get(session, id=faction_id, guild_id=interaction.guild_id)

            if not faction_to_delete:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_delete:error_not_found", lang_code,
                    "Faction with ID {id} not found. Nothing to delete."
                ) # type: ignore
                await interaction.followup.send(error_msg.format(id=faction_id), ephemeral=True)
                return

            faction_name_for_message = faction_to_delete.name_i18n.get(lang_code, faction_to_delete.name_i18n.get("en", f"Faction {faction_to_delete.id}")) if hasattr(faction_to_delete, 'name_i18n') and faction_to_delete.name_i18n else f"Faction {faction_to_delete.id}"

            error_detail_static_id_empty = await get_localized_message_template(session, interaction.guild_id, "faction_update:error_detail_static_id_empty", lang_code, "static_id cannot be empty.") # type: ignore
            error_detail_json_not_dict_template = await get_localized_message_template(session, interaction.guild_id, "faction_update:error_detail_json_not_dict", lang_code, "{field_name} must be a dictionary.") # type: ignore
            error_detail_leader_not_found_template = await get_localized_message_template(session, interaction.guild_id, "faction_update:error_detail_leader_not_found", lang_code, "Leader NPC with static_id '{id}' not found.") # type: ignore

            # The ValueErrors in faction_update try block need to be updated to use these templates.
            # This change is for faction_delete, so I'll just update the existing error messages in faction_delete for now.

            npc_dependency_stmt = select(npc_crud.model.id).where(
                npc_crud.model.faction_id == faction_id,
                npc_crud.model.guild_id == interaction.guild_id
            ).limit(1)
            npc_dependency = (await session.execute(npc_dependency_stmt)).scalar_one_or_none()

            if npc_dependency:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_delete:error_npc_dependency", lang_code,
                    "Cannot delete Faction '{name}' (ID: {id}) as NPCs are still members of it. Please reassign or delete them first."
                ) # type: ignore
                await interaction.followup.send(error_msg.format(name=faction_name_for_message, id=faction_id), ephemeral=True)
                return

            deleted_faction: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_faction = await crud_faction.delete(session, id=faction_id, guild_id=interaction.guild_id)

                if deleted_faction:
                    success_msg = await get_localized_message_template(
                        session, interaction.guild_id, "faction_delete:success", lang_code,
                        "Faction '{name}' (ID: {id}) has been deleted successfully."
                    ) # type: ignore
                    await interaction.followup.send(success_msg.format(name=faction_name_for_message, id=faction_id), ephemeral=True)
                else: # Should not happen if found before
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "faction_delete:error_not_deleted_unknown", lang_code,
                        "Faction (ID: {id}) was found but could not be deleted."
                    ) # type: ignore
                    await interaction.followup.send(error_msg.format(id=faction_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Faction {faction_id} for guild {interaction.guild_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "faction_delete:error_generic", lang_code,
                    "An error occurred while deleting Faction '{name}' (ID: {id}): {error_message}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(name=faction_name_for_message, id=faction_id, error_message=str(e)), ephemeral=True)
                return

async def setup(bot: commands.Bot):
    cog = MasterFactionCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterFactionCog loaded.")
