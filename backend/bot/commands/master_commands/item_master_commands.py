import logging
import json
from typing import Dict, Any, Optional, List

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

from backend.core.crud.crud_item import item_crud
from backend.core.crud.crud_inventory_item import inventory_item_crud # For dependency check on delete
from backend.core.database import get_db_session
from backend.core.crud_base_definitions import update_entity
from backend.core.localization_utils import get_localized_message_template
from backend.bot.utils import parse_json_parameter # Import the utility

logger = logging.getLogger(__name__)

class MasterItemCog(commands.Cog, name="Master Item Commands"): # type: ignore[call-arg]
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterItemCog initialized.")

    item_master_cmds = app_commands.Group(
        name="master_item",
        description="Master commands for managing Items.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    @item_master_cmds.command(name="view", description="View details of a specific Item.")
    @app_commands.describe(item_id="The database ID of the Item to view.")
    async def item_view(self, interaction: discord.Interaction, item_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            item = await item_crud.get(session, id=item_id, guild_id=interaction.guild_id)

            if not item:
                not_found_msg = await get_localized_message_template(session, interaction.guild_id, "item_view:not_found", lang_code, "Item with ID {id} not found in this guild.")
                await interaction.followup.send(not_found_msg.format(id=item_id), ephemeral=True); return

            title_template = await get_localized_message_template(session, interaction.guild_id, "item_view:title", lang_code, "Item Details: {item_name} (ID: {item_id})")
            item_name_display = item.name_i18n.get(lang_code, item.name_i18n.get("en", f"Item {item.id}"))
            embed_title = title_template.format(item_name=item_name_display, item_id=item.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.gold())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"item_view:label_{key}", lang_code, default)

            async def format_json_field_helper(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str_val = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data: return na_str_val
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(item.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=item.static_id or na_value_str, inline=True)
            item_type_display = na_value_str
            if item.item_type_i18n:
                item_type_display = item.item_type_i18n.get(lang_code, item.item_type_i18n.get("en", na_value_str))
            embed.add_field(name=await get_label("item_type", "Type"), value=item_type_display, inline=True)
            embed.add_field(name=await get_label("base_value", "Base Value"), value=str(item.base_value) if item.base_value is not None else na_value_str, inline=True)
            embed.add_field(name=await get_label("slot_type", "Slot Type"), value=item.slot_type or na_value_str, inline=True)
            embed.add_field(name=await get_label("is_stackable", "Is Stackable"), value=str(item.is_stackable), inline=True)

            name_i18n_str = await format_json_field_helper(item.name_i18n, "item_view:value_na_json", "item_view:error_serialization")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```" + ("..." if len(name_i18n_str) > 1000 else ""), inline=False)
            desc_i18n_str = await format_json_field_helper(item.description_i18n, "item_view:value_na_json", "item_view:error_serialization")
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```" + ("..." if len(desc_i18n_str) > 1000 else ""), inline=False)
            props_str = await format_json_field_helper(item.properties_json, "item_view:value_na_json", "item_view:error_serialization")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{props_str[:1000]}\n```" + ("..." if len(props_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @item_master_cmds.command(name="list", description="List Items in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of Items per page.")
    async def item_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
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
            items = await item_crud.get_multi(session, guild_id=interaction.guild_id, skip=offset, limit=limit)
            total_items = await item_crud.get_count_by_guild(session, guild_id=interaction.guild_id) # type: ignore

            if not items:
                no_items_msg = await get_localized_message_template(session, interaction.guild_id, "item_list:no_items_found_page", lang_code, "No Items found for this guild (Page {page}).")
                await interaction.followup.send(no_items_msg.format(page=page), ephemeral=True); return

            title_template = await get_localized_message_template(session, interaction.guild_id, "item_list:title", lang_code, "Item List (Page {page} of {total_pages})")
            total_pages = ((total_items - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_gold())
            footer_template = await get_localized_message_template(session, interaction.guild_id, "item_list:footer", lang_code, "Displaying {count} of {total} total Items.")
            embed.set_footer(text=footer_template.format(count=len(items), total=total_items))

            field_name_template = await get_localized_message_template(session, interaction.guild_id, "item_list:item_field_name", lang_code, "ID: {item_id} | {item_name} (Static: {static_id})")
            field_value_template = await get_localized_message_template(session, interaction.guild_id, "item_list:item_field_value", lang_code, "Type: {type}, Value: {value}, Stackable: {stackable}")

            for item_obj in items:
                na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")
                item_name_display = item_obj.name_i18n.get(lang_code, item_obj.name_i18n.get("en", f"Item {item_obj.id}"))
                item_type_display = na_value_str
                if item_obj.item_type_i18n:
                    item_type_display = item_obj.item_type_i18n.get(lang_code, item_obj.item_type_i18n.get("en", na_value_str))
                embed.add_field(
                    name=field_name_template.format(item_id=item_obj.id, item_name=item_name_display, static_id=item_obj.static_id or na_value_str),
                    value=field_value_template.format(
                        type=item_type_display,
                        value=str(item_obj.base_value) if item_obj.base_value is not None else na_value_str,
                        stackable=str(item_obj.is_stackable)
                    ),
                    inline=False
                )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @item_master_cmds.command(name="create", description="Create a new Item in this guild.")
    @app_commands.describe(
        static_id="Static ID for this Item (must be unique within the guild).",
        name_i18n_json="JSON string for Item name (e.g., {\"en\": \"Sword\", \"ru\": \"Меч\"}).",
        item_type_i18n_json="JSON string for Item type (e.g., {\"en\": \"Weapon\", \"ru\": \"Оружие\"}).",
        description_i18n_json="Optional: JSON string for Item description.",
        properties_json="Optional: JSON string for additional Item properties.",
        base_value="Optional: Integer base value/cost of the item.",
        slot_type="Optional: Equipment slot if applicable (e.g., MAIN_HAND, CHEST).",
        is_stackable="Is the item stackable? (True/False, defaults to True)."
    )
    async def item_create(self, interaction: discord.Interaction,
                          static_id: str,
                          name_i18n_json: str,
                          item_type_i18n_json: str, # Changed from item_type
                          description_i18n_json: Optional[str] = None,
                          properties_json: Optional[str] = None,
                          base_value: Optional[int] = None,
                          slot_type: Optional[str] = None,
                          is_stackable: bool = True):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            parsed_name_i18n = await parse_json_parameter(interaction, name_i18n_json, "name_i18n_json", session)
            if parsed_name_i18n is None: return
            error_detail_name_lang = await get_localized_message_template(session, interaction.guild_id, "item_create:error_detail_name_lang", lang_code, "name_i18n_json must contain 'en' or current language key.")
            if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code):
                 error_msg = await get_localized_message_template(session,interaction.guild_id,"item_create:error_invalid_json_content",lang_code,"Invalid JSON content: {details}")
                 await interaction.followup.send(error_msg.format(details=error_detail_name_lang), ephemeral=True); return

            parsed_item_type_i18n = await parse_json_parameter(interaction, item_type_i18n_json, "item_type_i18n_json", session)
            if parsed_item_type_i18n is None: return
            error_detail_item_type_lang = await get_localized_message_template(session, interaction.guild_id, "item_create:error_detail_item_type_lang", lang_code, "item_type_i18n_json must contain 'en' or current language key.")
            if not parsed_item_type_i18n.get("en") and not parsed_item_type_i18n.get(lang_code):
                error_msg = await get_localized_message_template(session,interaction.guild_id,"item_create:error_invalid_json_content",lang_code,"Invalid JSON content: {details}")
                await interaction.followup.send(error_msg.format(details=error_detail_item_type_lang), ephemeral=True); return

            parsed_description_i18n = await parse_json_parameter(interaction, description_i18n_json, "description_i18n_json", session)
            if parsed_description_i18n is None and description_i18n_json is not None: return

            parsed_properties = await parse_json_parameter(interaction, properties_json, "properties_json", session)
            if parsed_properties is None and properties_json is not None: return

            if await item_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=static_id):
                error_msg = await get_localized_message_template(session, interaction.guild_id, "item_create:error_static_id_exists", lang_code, "An Item with static_id '{id}' already exists in this guild.")
                await interaction.followup.send(error_msg.format(id=static_id), ephemeral=True); return

            item_data_to_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id, "static_id": static_id,
                "name_i18n": parsed_name_i18n,
                "item_type_i18n": parsed_item_type_i18n,
                "description_i18n": parsed_description_i18n or {},
                "properties_json": parsed_properties or {},
                "base_value": base_value, "slot_type": slot_type, "is_stackable": is_stackable,
            }
            created_item: Optional[Any] = None
            try:
                async with session.begin():
                    created_item = await item_crud.create(session, obj_in=item_data_to_create)
                    await session.flush();
                    if created_item: await session.refresh(created_item)
            except Exception as e:
                logger.error(f"Error creating Item: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, interaction.guild_id, "item_create:error_generic_create", lang_code, "An error occurred while creating the Item: {error_message}")
                await interaction.followup.send(error_msg.format(error_message=str(e)), ephemeral=True); return

            if not created_item:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "item_create:error_creation_failed_unknown", lang_code, "Item creation failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title_template = await get_localized_message_template(session, interaction.guild_id, "item_create:success_title", lang_code, "Item Created: {item_name} (ID: {item_id})")
            created_item_name_display = created_item.name_i18n.get(lang_code, created_item.name_i18n.get("en", f"Item {created_item.id}"))
            embed = discord.Embed(title=success_title_template.format(item_name=created_item_name_display, item_id=created_item.id), color=discord.Color.green())
            async def get_created_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"item_create:label_{key}", lang_code, default)
            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")
            embed.add_field(name=await get_created_label("static_id", "Static ID"), value=created_item.static_id or na_value_str, inline=True)
            item_type_created_display = na_value_str
            if created_item.item_type_i18n:
                 item_type_created_display = created_item.item_type_i18n.get(lang_code, created_item.item_type_i18n.get("en", na_value_str))
            embed.add_field(name=await get_created_label("type","Type"), value=item_type_created_display, inline=True)
            embed.add_field(name=await get_created_label("stackable","Stackable"), value=str(created_item.is_stackable), inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @item_master_cmds.command(name="update", description="Update a specific field or multiple fields via JSON for an Item.")
    @app_commands.describe(
        item_id="The database ID of the Item to update.",
        field_to_update="Optional: Field to update (e.g., static_id, base_value, slot_type, is_stackable). Not for JSON fields.",
        new_value="Optional: New value for the single field_to_update.",
        data_json="Optional: JSON string with multiple fields to update (e.g., {\"name_i18n\": ..., \"properties_json\": ...})."
    )
    async def item_update(self, interaction: discord.Interaction,
                          item_id: int,
                          field_to_update: Optional[str] = None,
                          new_value: Optional[str] = None,
                          data_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        if not data_json and (field_to_update is None or new_value is None):
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "item_update:error_missing_params", lang_code, "Either 'data_json' or both 'field_to_update' and 'new_value' must be provided.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        if data_json and (field_to_update or new_value):
            async with get_db_session() as temp_session:
                warn_msg = await get_localized_message_template(temp_session, interaction.guild_id, "item_update:warn_data_json_priority", lang_code, "Warning: 'data_json' provided, 'field_to_update' and 'new_value' will be ignored.")
            await interaction.followup.send(warn_msg, ephemeral=True) # Send as a warning, but proceed with data_json

        allowed_fields = {
            "static_id": str, "name_i18n": dict, "description_i18n": dict,
            "item_type_i18n": dict, "base_value": (int, type(None)),
            "slot_type": (str, type(None)), "is_stackable": bool, "properties_json": dict,
        }
        update_data_dict: Dict[str, Any] = {}

        async with get_db_session() as session:
            item_to_update = await item_crud.get(session, id=item_id, guild_id=interaction.guild_id)
            if not item_to_update:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "item_update:error_item_not_found", lang_code, "Item with ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=item_id), ephemeral=True); return

            try:
                if data_json:
                    parsed_json_data = await parse_json_parameter(interaction, data_json, "data_json", session)
                    if parsed_json_data is None: return # Error already sent

                    for key, value in parsed_json_data.items():
                        db_key = key
                        if key.endswith("_json") and key.replace("_json", "") in allowed_fields:
                            db_key = key.replace("_json", "")

                        if db_key not in allowed_fields:
                            raise ValueError(f"Field '{key}' in data_json is not allowed for update.")

                        field_type_info = allowed_fields[db_key]
                        parsed_single_value: Any = None

                        if db_key == "static_id":
                            parsed_single_value = str(value)
                            if not parsed_single_value: raise ValueError("static_id cannot be empty.")
                            if parsed_single_value != item_to_update.static_id and \
                               await item_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_single_value):
                                raise ValueError(f"Another Item with static_id '{parsed_single_value}' already exists.")
                        elif isinstance(field_type_info, type) and field_type_info == dict : # name_i18n, description_i18n, etc.
                            if not isinstance(value, dict): raise ValueError(f"Field '{key}' must be a JSON object.")
                            parsed_single_value = value
                        elif db_key == "slot_type":
                            parsed_single_value = str(value) if value is not None else None
                        elif db_key == "base_value":
                            parsed_single_value = int(value) if value is not None else None
                        elif db_key == "is_stackable":
                            if not isinstance(value, bool): raise ValueError("is_stackable must be a boolean (true/false).")
                            parsed_single_value = value
                        else:
                            raise ValueError(f"Type processing for field '{key}' in data_json not fully implemented.")
                        update_data_dict[db_key] = parsed_single_value

                elif field_to_update and new_value is not None: # Single field update
                    field_to_update_lower = field_to_update.lower()
                    db_field_name = field_to_update_lower
                    user_facing_field_name = field_to_update_lower

                    if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
                        db_field_name = field_to_update_lower.replace("_json","")

                    field_type_info = allowed_fields.get(db_field_name)
                    if not field_type_info:
                        raise ValueError(f"Field '{field_to_update}' is not allowed for update.")

                    parsed_single_value: Any = None
                    if db_field_name == "static_id":
                        parsed_single_value = new_value
                        if not parsed_single_value: raise ValueError("static_id cannot be empty.")
                        if parsed_single_value != item_to_update.static_id and \
                           await item_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_single_value):
                            raise ValueError(f"Another Item with static_id '{parsed_single_value}' already exists.")
                    elif db_field_name in ["name_i18n", "description_i18n", "item_type_i18n", "properties_json"]:
                        parsed_single_value = await parse_json_parameter(interaction, new_value, user_facing_field_name, session)
                        if parsed_single_value is None: return
                    elif db_field_name == "slot_type":
                        if new_value.lower() == 'none' or new_value.lower() == 'null': parsed_single_value = None
                        else: parsed_single_value = new_value
                    elif db_field_name == "base_value":
                        if new_value.lower() == 'none' or new_value.lower() == 'null': parsed_single_value = None
                        else: parsed_single_value = int(new_value)
                    elif db_field_name == "is_stackable":
                        if new_value.lower() == 'true': parsed_single_value = True
                        elif new_value.lower() == 'false': parsed_single_value = False
                        else: raise ValueError("is_stackable must be 'True' or 'False'.")
                    else:
                        raise ValueError(f"Internal error: Unknown field type for '{db_field_name}'.")
                    update_data_dict = {db_field_name: parsed_single_value}

            except ValueError as e:
                error_msg_template = await get_localized_message_template(session, interaction.guild_id, "item_update:error_invalid_value_type", lang_code, "Invalid value. Details: {details}")
                await interaction.followup.send(error_msg_template.format(details=str(e)), ephemeral=True); return

            if not update_data_dict:
                no_changes_msg = await get_localized_message_template(session, interaction.guild_id, "item_update:no_changes_to_apply", lang_code, "No valid changes were provided to apply.")
                await interaction.followup.send(no_changes_msg, ephemeral=True); return

            updated_item: Optional[Any] = None
            try:
                async with session.begin():
                    updated_item = await update_entity(session, entity=item_to_update, data=update_data_dict)
                    await session.flush()
                    if updated_item:
                        await session.refresh(updated_item)
            except Exception as e:
                logger.error(f"Error updating Item {item_id} with data {update_data_dict}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, interaction.guild_id, "item_update:error_generic_update", lang_code, "An error occurred while updating Item {id}: {error_message}")
                await interaction.followup.send(error_msg.format(id=item_id, error_message=str(e)), ephemeral=True); return

            if not updated_item:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "item_update:error_update_failed_unknown", lang_code, "Item update failed for an unknown reason.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title_template = await get_localized_message_template(session, interaction.guild_id, "item_update:success_title", lang_code, "Item Updated: {item_name} (ID: {item_id})")
            updated_item_name_display = updated_item.name_i18n.get(lang_code, updated_item.name_i18n.get("en", f"Item {updated_item.id}")) if hasattr(updated_item, 'name_i18n') and updated_item.name_i18n else f"Item {updated_item.id}"
            embed = discord.Embed(title=success_title_template.format(item_name=updated_item_name_display, item_id=updated_item.id), color=discord.Color.orange())

            fields_updated_label = await get_localized_message_template(session, interaction.guild_id, "item_update:label_fields_updated", lang_code, "Fields Updated")

            updated_fields_details = []
            for key, value in update_data_dict.items():
                val_display: str
                if value is None: val_display = "None"
                elif isinstance(value, dict): val_display = f"```json\n{json.dumps(value, indent=2, ensure_ascii=False)[:200]}\n```" # Truncate for display
                elif isinstance(value, bool): val_display = str(value)
                else: val_display = str(value)
                updated_fields_details.append(f"**{key}**: {val_display}")

            embed.add_field(name=fields_updated_label, value="\n".join(updated_fields_details) if updated_fields_details else "No specific fields shown.", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @item_master_cmds.command(name="delete", description="Delete an Item definition from this guild.")
    @app_commands.describe(item_id="The database ID of the Item to delete.")
    async def item_delete(self, interaction: discord.Interaction, item_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            item_to_delete = await item_crud.get(session, id=item_id, guild_id=interaction.guild_id)
            if not item_to_delete:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "item_delete:error_not_found", lang_code, "Item with ID {id} not found. Nothing to delete.")
                await interaction.followup.send(error_msg.format(id=item_id), ephemeral=True); return

            item_name_for_message = item_to_delete.name_i18n.get(lang_code, item_to_delete.name_i18n.get("en", f"Item {item_to_delete.id}")) if hasattr(item_to_delete, 'name_i18n') and item_to_delete.name_i18n else f"Item {item_to_delete.id}"
            inventory_dependency_stmt = select(inventory_item_crud.model.id).where(inventory_item_crud.model.item_id == item_id, inventory_item_crud.model.guild_id == interaction.guild_id).limit(1)
            inventory_dependency = (await session.execute(inventory_dependency_stmt)).scalar_one_or_none()
            if inventory_dependency:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "item_delete:error_inventory_dependency", lang_code, "Cannot delete Item '{name}' (ID: {id}) as it exists in one or more inventories. Please remove all instances of this item first.")
                await interaction.followup.send(error_msg.format(name=item_name_for_message, id=item_id), ephemeral=True); return

            deleted_item: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_item = await item_crud.delete(session, id=item_id, guild_id=interaction.guild_id)
                if deleted_item:
                    success_msg = await get_localized_message_template(session, interaction.guild_id, "item_delete:success", lang_code, "Item '{name}' (ID: {id}) has been deleted successfully.")
                    await interaction.followup.send(success_msg.format(name=item_name_for_message, id=item_id), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "item_delete:error_not_deleted_unknown", lang_code, "Item (ID: {id}) was found but could not be deleted.")
                    await interaction.followup.send(error_msg.format(id=item_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Item {item_id} for guild {interaction.guild_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, interaction.guild_id, "item_delete:error_generic", lang_code, "An error occurred while deleting Item '{name}' (ID: {id}): {error_message}")
                await interaction.followup.send(error_msg.format(name=item_name_for_message, id=item_id, error_message=str(e)), ephemeral=True); return

async def setup(bot: commands.Bot):
    cog = MasterItemCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterItemCog loaded.")
