import logging
import json
from typing import Dict, Any, Optional, List

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

from src.core.crud.crud_item import item_crud
from src.core.crud.crud_inventory_item import inventory_item_crud # For dependency check on delete
from src.core.database import get_db_session
from src.core.crud_base_definitions import update_entity
from src.core.localization_utils import get_localized_message_template

logger = logging.getLogger(__name__)

class MasterItemCog(commands.Cog, name="Master Item Commands"):
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
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            item = await item_crud.get(session, id=item_id, guild_id=interaction.guild_id)

            if not item:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_view:not_found", lang_code,
                    "Item with ID {id} not found in this guild."
                ) # type: ignore
                await interaction.followup.send(not_found_msg.format(id=item_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "item_view:title", lang_code,
                "Item Details: {item_name} (ID: {item_id})"
            ) # type: ignore

            item_name_display = item.name_i18n.get(lang_code, item.name_i18n.get("en", f"Item {item.id}"))
            embed_title = title_template.format(item_name=item_name_display, item_id=item.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.gold())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"item_view:label_{key}", lang_code, default) # type: ignore

            async def format_json_field_helper(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str: # Renamed to avoid conflict
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available") # type: ignore
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON") # type: ignore


            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(item.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=item.static_id or "N/A", inline=True)
            item_type_display = "N/A"
            if item.item_type_i18n:
                item_type_display = item.item_type_i18n.get(lang_code, item.item_type_i18n.get("en", "N/A"))
            embed.add_field(name=await get_label("item_type", "Type"), value=item_type_display, inline=True)
            embed.add_field(name=await get_label("base_value", "Base Value"), value=str(item.base_value) if item.base_value is not None else "N/A", inline=True)
            embed.add_field(name=await get_label("slot_type", "Slot Type"), value=item.slot_type or "N/A", inline=True)
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
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            offset = (page - 1) * limit
            items = await item_crud.get_multi(session, guild_id=interaction.guild_id, skip=offset, limit=limit)

            total_items_stmt = select(func.count(item_crud.model.id)).where(item_crud.model.guild_id == interaction.guild_id)
            total_items_result = await session.execute(total_items_stmt)
            total_items = total_items_result.scalar_one_or_none() or 0

            if not items:
                no_items_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_list:no_items_found_page", lang_code,
                    "No Items found for this guild (Page {page})."
                ) # type: ignore
                await interaction.followup.send(no_items_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "item_list:title", lang_code,
                "Item List (Page {page} of {total_pages})"
            ) # type: ignore
            total_pages = ((total_items - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_gold())

            footer_template = await get_localized_message_template(
                session, interaction.guild_id, "item_list:footer", lang_code,
                "Displaying {count} of {total} total Items."
            ) # type: ignore
            embed.set_footer(text=footer_template.format(count=len(items), total=total_items))

            field_name_template = await get_localized_message_template(
                session, interaction.guild_id, "item_list:item_field_name", lang_code,
                "ID: {item_id} | {item_name} (Static: {static_id})"
            ) # type: ignore
            field_value_template = await get_localized_message_template(
                session, interaction.guild_id, "item_list:item_field_value", lang_code,
                "Type: {type}, Value: {value}, Stackable: {stackable}"
            ) # type: ignore

            for item_obj in items:
                item_name_display = item_obj.name_i18n.get(lang_code, item_obj.name_i18n.get("en", f"Item {item_obj.id}"))
                item_type_display = "N/A"
                if item_obj.item_type_i18n:
                    item_type_display = item_obj.item_type_i18n.get(lang_code, item_obj.item_type_i18n.get("en", "N/A"))
                embed.add_field(
                    name=field_name_template.format(item_id=item_obj.id, item_name=item_name_display, static_id=item_obj.static_id or "N/A"),
                    value=field_value_template.format(
                        type=item_type_display,
                        value=str(item_obj.base_value) if item_obj.base_value is not None else "N/A",
                        stackable=str(item_obj.is_stackable)
                    ),
                    inline=False
                )

            if len(embed.fields) == 0:
                no_display_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_list:no_items_to_display", lang_code,
                    "No Items found to display on page {page}."
                )
                await interaction.followup.send(no_display_msg.format(page=page), ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

    @item_master_cmds.command(name="create", description="Create a new Item in this guild.")
    @app_commands.describe(
        static_id="Static ID for this Item (must be unique within the guild).",
        name_i18n_json="JSON string for Item name (e.g., {\"en\": \"Sword\", \"ru\": \"Меч\"}).",
        item_type="Type of item (e.g., WEAPON, ARMOR, POTION, QUEST_ITEM).",
        description_i18n_json="Optional: JSON string for Item description.",
        properties_json="Optional: JSON string for additional Item properties.",
        base_value="Optional: Integer base value/cost of the item.",
        slot_type="Optional: Equipment slot if applicable (e.g., MAIN_HAND, CHEST).",
        is_stackable="Is the item stackable? (True/False, defaults to True)."
    )
    async def item_create(self, interaction: discord.Interaction,
                          static_id: str,
                          name_i18n_json: str,
                          item_type: str,
                          description_i18n_json: Optional[str] = None,
                          properties_json: Optional[str] = None,
                          base_value: Optional[int] = None,
                          slot_type: Optional[str] = None,
                          is_stackable: bool = True):
        await interaction.response.defer(ephemeral=True)

        lang_code = str(interaction.locale)
        parsed_name_i18n: Dict[str, str]
        parsed_description_i18n: Optional[Dict[str, str]] = None
        parsed_properties: Optional[Dict[str, Any]] = None
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            existing_item_static = await item_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=static_id)
            if existing_item_static:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_create:error_static_id_exists", lang_code,
                    "An Item with static_id '{id}' already exists in this guild."
                ) # type: ignore
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
            except ValueError as e: # Specific exception first
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_create:error_invalid_json_format", lang_code,
                    "Invalid JSON format or structure for one of the input fields: {error_details}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(error_details=str(e)), ephemeral=True)
                return
            # JSONDecodeError is a subclass of ValueError, so this block is unreachable if ValueError is caught first.
            # except json.JSONDecodeError as e:
            #     error_msg = await get_localized_message_template(
            #         session, interaction.guild_id, "item_create:error_invalid_json_format", lang_code,
            #         "Invalid JSON format or structure for one of the input fields: {error_details}"
            #     ) # type: ignore
            #     await interaction.followup.send(error_msg.format(error_details=str(e)), ephemeral=True)
            #     return

            item_data_to_create: Dict[str, Any] = {
                "guild_id": interaction.guild_id, # Already checked not None
                "static_id": static_id,
                "name_i18n": parsed_name_i18n,
                "item_type_i18n": {"en": item_type, lang_code: item_type} if lang_code != "en" else {"en": item_type},
                "description_i18n": parsed_description_i18n if parsed_description_i18n else {},
                "properties_json": parsed_properties if parsed_properties else {},
                "base_value": base_value,
                "slot_type": slot_type,
                "is_stackable": is_stackable,
            }

            created_item: Optional[Any] = None
            try:
                async with session.begin():
                    # guild_id is already in item_data_to_create and handled by CRUDBase.create
                    created_item = await item_crud.create(session, obj_in=item_data_to_create)
                    await session.flush()
                    if created_item:
                         await session.refresh(created_item)
            except Exception as e:
                logger.error(f"Error creating Item with data {item_data_to_create}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_create:error_generic_create", lang_code,
                    "An error occurred while creating the Item: {error_message}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(error_message=str(e)), ephemeral=True)
                return

            if not created_item:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_create:error_creation_failed_unknown", lang_code,
                    "Item creation failed for an unknown reason."
                ) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "item_create:success_title", lang_code,
                "Item Created: {item_name} (ID: {item_id})"
            ) # type: ignore
            created_item_name_display = created_item.name_i18n.get(lang_code, created_item.name_i18n.get("en", f"Item {created_item.id}"))

            embed = discord.Embed(title=success_title_template.format(item_name=created_item_name_display, item_id=created_item.id), color=discord.Color.green())
            embed.add_field(name="Static ID", value=created_item.static_id, inline=True)
            embed.add_field(name="Type", value=created_item.item_type, inline=True)
            embed.add_field(name="Stackable", value=str(created_item.is_stackable), inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @item_master_cmds.command(name="update", description="Update a specific field for an Item.")
    @app_commands.describe(
        item_id="The database ID of the Item to update.",
        field_to_update="Field to update (e.g., static_id, name_i18n_json, item_type, base_value, slot_type, is_stackable, properties_json).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable; True/False for boolean)."
    )
    async def item_update(self, interaction: discord.Interaction, item_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        allowed_fields = {
            "static_id": str,
            "name_i18n": dict, # from name_i18n_json
            "description_i18n": dict, # from description_i18n_json
            "item_type": str,
            "base_value": (int, type(None)),
            "slot_type": (str, type(None)),
            "is_stackable": bool,
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
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "item_update:error_field_not_allowed", lang_code,
                    "Field '{field_name}' is not allowed for update. Allowed: {allowed_list}"
                ) # type: ignore
            await interaction.followup.send(error_msg.format(field_name=field_to_update, allowed_list=', '.join(allowed_fields.keys())), ephemeral=True)
            return

        parsed_value: Any = None
        async with get_db_session() as session:
            try:
                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: # static_id cannot be None or empty for an existing item, it's a key part of its definition
                        raise ValueError("static_id cannot be set to empty. If you meant to remove it, this operation is not supported. Consider deleting and recreating if it's optional in your model and you want it null.")
                    existing_item_static = await item_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                    if existing_item_static and existing_item_static.id != item_id:
                        error_msg = await get_localized_message_template(
                            session, interaction.guild_id, "item_update:error_static_id_exists", lang_code,
                            "Another Item with static_id '{id}' already exists."
                        ) # type: ignore
                        await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True)
                        return
                elif db_field_name in ["name_i18n", "description_i18n", "properties_json"]:
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict):
                        raise ValueError(f"{db_field_name} must be a dictionary.")
                elif db_field_name == "item_type" or db_field_name == "slot_type":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        if db_field_name == "item_type": # item_type is likely not nullable
                             raise ValueError("item_type cannot be None.")
                        parsed_value = None
                    else:
                        parsed_value = new_value
                elif db_field_name == "base_value":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = int(new_value) # Can raise ValueError
                elif db_field_name == "is_stackable":
                    if new_value.lower() == 'true':
                        parsed_value = True
                    elif new_value.lower() == 'false':
                        parsed_value = False
                    else:
                        raise ValueError("is_stackable must be 'True' or 'False'.")
                else: # Should not be reached
                     error_msg = await get_localized_message_template(
                         session, interaction.guild_id, "item_update:error_unknown_field_type", lang_code,
                        "Internal error: Unknown field type for '{field_name}'."
                    ) # type: ignore
                     await interaction.followup.send(error_msg.format(field_name=db_field_name), ephemeral=True)
                     return
            except ValueError as e: # Specific exception first
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_update:error_invalid_value_type", lang_code,
                    "Invalid value '{value}' for field '{field_name}'. Details: {details}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True)
                return
            # JSONDecodeError is a subclass of ValueError, so this block is unreachable if ValueError is caught first.
            # except json.JSONDecodeError as e:
            #     error_msg = await get_localized_message_template(
            #         session, interaction.guild_id, "item_update:error_invalid_json", lang_code,
            #         "Invalid JSON string '{value}' for field '{field_name}'. Details: {details}"
            #     ) # type: ignore
            #     await interaction.followup.send(error_msg.format(value=new_value, field_name=field_to_update, details=str(e)), ephemeral=True)
            #     return

            item_to_update = await item_crud.get(session, id=item_id, guild_id=interaction.guild_id)
            if not item_to_update:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_update:error_item_not_found", lang_code,
                    "Item with ID {id} not found."
                ) # type: ignore
                await interaction.followup.send(error_msg.format(id=item_id), ephemeral=True)
                return

            update_data_dict = {db_field_name: parsed_value}
            updated_item: Optional[Any] = None
            try:
                async with session.begin():
                    updated_item = await update_entity(session, entity=item_to_update, data=update_data_dict)
                    await session.flush()
                    if updated_item: # Refresh only if not None
                        await session.refresh(updated_item)
            except Exception as e:
                logger.error(f"Error updating Item {item_id} with data {update_data_dict}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_update:error_generic_update", lang_code,
                    "An error occurred while updating Item {id}: {error_message}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(id=item_id, error_message=str(e)), ephemeral=True)
                return

            if not updated_item: # Check after potential refresh
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_update:error_update_failed_unknown", lang_code,
                    "Item update failed for an unknown reason."
                ) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)
                return


            success_title_template = await get_localized_message_template(
                session, interaction.guild_id, "item_update:success_title", lang_code,
                "Item Updated: {item_name} (ID: {item_id})"
            ) # type: ignore
            updated_item_name_display = updated_item.name_i18n.get(lang_code, updated_item.name_i18n.get("en", f"Item {updated_item.id}")) if hasattr(updated_item, 'name_i18n') and updated_item.name_i18n else f"Item {updated_item.id}" # type: ignore
            embed = discord.Embed(title=success_title_template.format(item_name=updated_item_name_display, item_id=updated_item.id), color=discord.Color.orange()) # type: ignore

            field_updated_label = await get_localized_message_template(session, interaction.guild_id, "item_update:label_field_updated", lang_code, "Field Updated") # type: ignore
            new_value_label = await get_localized_message_template(session, interaction.guild_id, "item_update:label_new_value", lang_code, "New Value") # type: ignore

            new_value_display = str(parsed_value)
            if isinstance(parsed_value, (dict, list)):
                new_value_display = f"```json\n{json.dumps(parsed_value, indent=2, ensure_ascii=False)}\n```"
            elif isinstance(parsed_value, bool):
                new_value_display = str(parsed_value)
            elif parsed_value is None:
                 new_value_display = "None"

            embed.add_field(name=field_updated_label, value=field_to_update, inline=True)
            embed.add_field(name=new_value_label, value=new_value_display, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @item_master_cmds.command(name="delete", description="Delete an Item definition from this guild.")
    @app_commands.describe(item_id="The database ID of the Item to delete.")
    async def item_delete(self, interaction: discord.Interaction, item_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        lang_code = str(interaction.locale)
        async with get_db_session() as session:
            item_to_delete = await item_crud.get(session, id=item_id, guild_id=interaction.guild_id)

            if not item_to_delete:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_delete:error_not_found", lang_code,
                    "Item with ID {id} not found. Nothing to delete."
                ) # type: ignore
                await interaction.followup.send(error_msg.format(id=item_id), ephemeral=True)
                return

            item_name_for_message = item_to_delete.name_i18n.get(lang_code, item_to_delete.name_i18n.get("en", f"Item {item_to_delete.id}")) if hasattr(item_to_delete, 'name_i18n') and item_to_delete.name_i18n else f"Item {item_to_delete.id}"
            # Check for dependencies in inventory items
            inventory_dependency_stmt = select(inventory_item_crud.model.id).where(
                inventory_item_crud.model.item_id == item_id,
                inventory_item_crud.model.guild_id == interaction.guild_id # Ensure check is within the same guild
            ).limit(1)
            inventory_dependency = (await session.execute(inventory_dependency_stmt)).scalar_one_or_none()


            if inventory_dependency:
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_delete:error_inventory_dependency", lang_code,
                    "Cannot delete Item '{name}' (ID: {id}) as it exists in one or more inventories. Please remove all instances of this item first."
                ) # type: ignore
                await interaction.followup.send(error_msg.format(name=item_name_for_message, id=item_id), ephemeral=True)
                return

            deleted_item: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_item = await item_crud.delete(session, id=item_id, guild_id=interaction.guild_id)

                if deleted_item:
                    success_msg = await get_localized_message_template(
                        session, interaction.guild_id, "item_delete:success", lang_code,
                        "Item '{name}' (ID: {id}) has been deleted successfully."
                    ) # type: ignore
                    await interaction.followup.send(success_msg.format(name=item_name_for_message, id=item_id), ephemeral=True)
                else: # Should not happen if found before
                    error_msg = await get_localized_message_template(
                        session, interaction.guild_id, "item_delete:error_not_deleted_unknown", lang_code,
                        "Item (ID: {id}) was found but could not be deleted."
                    ) # type: ignore
                    await interaction.followup.send(error_msg.format(id=item_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Item {item_id} for guild {interaction.guild_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(
                    session, interaction.guild_id, "item_delete:error_generic", lang_code,
                    "An error occurred while deleting Item '{name}' (ID: {id}): {error_message}"
                ) # type: ignore
                await interaction.followup.send(error_msg.format(name=item_name_for_message, id=item_id, error_message=str(e)), ephemeral=True)
                return

async def setup(bot: commands.Bot):
    cog = MasterItemCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterItemCog loaded.")
