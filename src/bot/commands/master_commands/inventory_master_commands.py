import logging
import json
from typing import Dict, Any, Optional, List

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, and_

from src.core.crud.crud_inventory_item import inventory_item_crud
from src.core.crud.crud_item import item_crud # To validate item_id and get item names
from src.core.crud.crud_player import player_crud # To validate owner
from src.core.crud.crud_npc import npc_crud # To validate owner
from src.core.database import get_db_session
from src.core.crud_base_definitions import update_entity
from src.core.localization_utils import get_localized_message_template
from src.models.enums import OwnerEntityType
from src.models.inventory_item import InventoryItem # For type hinting

logger = logging.getLogger(__name__)

class MasterInventoryItemCog(commands.Cog, name="Master Inventory Item Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterInventoryItemCog initialized.")

    inventory_item_master_cmds = app_commands.Group(
        name="master_inventory_item",
        description="Master commands for managing Inventory Items.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    @inventory_item_master_cmds.command(name="view", description="View details of a specific Inventory Item instance.")
    @app_commands.describe(inventory_item_id="The database ID of the InventoryItem to view.")
    async def inventory_item_view(self, interaction: discord.Interaction, inventory_item_id: int):
        await interaction.response.defer(ephemeral=True)

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            inv_item = await inventory_item_crud.get_by_id_and_guild(session, id=inventory_item_id, guild_id=interaction.guild_id)

            if not inv_item:
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "inv_item_view:not_found", lang_code,
                    "InventoryItem with ID {id} not found in this guild."
                )
                await interaction.followup.send(not_found_msg.format(id=inventory_item_id), ephemeral=True)
                return

            item_definition = await item_crud.get(session, id=inv_item.item_id)
            item_name_display = "Unknown Item"
            if item_definition: # Item definitions are global, but linked items should be in the same guild context implicitly
                item_name_display = item_definition.name_i18n.get(lang_code, item_definition.name_i18n.get("en", f"Item {item_definition.id}"))

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "inv_item_view:title", lang_code,
                "Inventory Item: {item_name} (Instance ID: {instance_id})"
            )
            embed_title = title_template.format(item_name=item_name_display, instance_id=inv_item.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.greyple())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"inv_item_view:label_{key}", lang_code, default)

            async def format_json_field_helper(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(inv_item.guild_id), inline=True)
            embed.add_field(name=await get_label("item_id", "Base Item ID"), value=str(inv_item.item_id), inline=True)
            embed.add_field(name=await get_label("quantity", "Quantity"), value=str(inv_item.quantity), inline=True)

            owner_type_display = inv_item.owner_entity_type.value if inv_item.owner_entity_type else "N/A"
            embed.add_field(name=await get_label("owner_type", "Owner Type"), value=owner_type_display, inline=True)
            embed.add_field(name=await get_label("owner_id", "Owner ID"), value=str(inv_item.owner_entity_id), inline=True)
            embed.add_field(name=await get_label("equipped_status", "Equipped Status"), value=inv_item.equipped_status or "N/A", inline=True)

            props_str = await format_json_field_helper(inv_item.instance_specific_properties_json, "inv_item_view:value_na_json", "inv_item_view:error_serialization_props")
            embed.add_field(name=await get_label("instance_properties", "Instance Properties JSON"), value=f"```json\n{props_str[:1000]}\n```" + ("..." if len(props_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @inventory_item_master_cmds.command(name="list", description="List Inventory Items with filters.")
    @app_commands.describe(
        owner_id="Optional: Filter by Owner ID.",
        owner_type="Optional: Filter by Owner Type (PLAYER or GENERATED_NPC).",
        item_id="Optional: Filter by base Item ID.",
        page="Page number.",
        limit="Items per page."
    )
    async def inventory_item_list(self, interaction: discord.Interaction,
                                  owner_id: Optional[int] = None,
                                  owner_type: Optional[str] = None,
                                  item_id: Optional[int] = None,
                                  page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10

        lang_code = str(interaction.locale)
        owner_type_enum: Optional[OwnerEntityType] = None

        async with get_db_session() as session:
            if owner_type:
                try: owner_type_enum = OwnerEntityType[owner_type.upper()]
                except KeyError:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_list:error_invalid_owner_type",lang_code,"Invalid owner_type.")
                    await interaction.followup.send(error_msg, ephemeral=True); return

            if owner_id is not None and owner_type_enum is None:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_list:error_owner_id_no_type",lang_code,"If owner_id is provided, owner_type must also be provided.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            filters = [inventory_item_crud.model.guild_id == interaction.guild_id]
            if owner_id is not None and owner_type_enum:
                filters.append(inventory_item_crud.model.owner_entity_id == owner_id)
                filters.append(inventory_item_crud.model.owner_entity_type == owner_type_enum)
            if item_id is not None:
                filters.append(inventory_item_crud.model.item_id == item_id)

            offset = (page - 1) * limit
            query = select(inventory_item_crud.model).where(and_(*filters)).offset(offset).limit(limit).order_by(inventory_item_crud.model.id.desc())
            result = await session.execute(query)
            inv_items = result.scalars().all()

            count_query = select(func.count(inventory_item_crud.model.id)).where(and_(*filters))
            total_inv_items_res = await session.execute(count_query)
            total_inv_items = total_inv_items_res.scalar_one_or_none() or 0

            filter_parts = []
            if owner_id is not None and owner_type_enum: filter_parts.append(f"Owner: {owner_type_enum.name}({owner_id})")
            if item_id is not None: filter_parts.append(f"Item ID: {item_id}")
            filter_display = ", ".join(filter_parts) if filter_parts else "All"

            if not inv_items:
                no_items_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_list:no_items_found",lang_code,"No InventoryItems found for {filter} (Page {p}).")
                await interaction.followup.send(no_items_msg.format(filter=filter_display, p=page), ephemeral=True); return

            title_tmpl = await get_localized_message_template(session,interaction.guild_id,"inv_item_list:title",lang_code,"InventoryItem List ({filter} - Page {p} of {tp})")
            total_pages = ((total_inv_items - 1) // limit) + 1
            embed = discord.Embed(title=title_tmpl.format(filter=filter_display, p=page, tp=total_pages), color=discord.Color.light_grey())

            footer_tmpl = await get_localized_message_template(session,interaction.guild_id,"inv_item_list:footer",lang_code,"Displaying {c} of {t} total items.")
            embed.set_footer(text=footer_tmpl.format(c=len(inv_items), t=total_inv_items))

            item_ids_to_fetch = list(set(ii.item_id for ii in inv_items))
            item_defs_dict = {}
            if item_ids_to_fetch:
                item_definitions = await item_crud.get_many_by_ids(session, ids=item_ids_to_fetch) # Assuming Item IDs are global or this CRUD handles context
                item_defs_dict = {item_def.id: item_def for item_def in item_definitions}

            name_tmpl = await get_localized_message_template(session,interaction.guild_id,"inv_item_list:item_name_field",lang_code,"ID: {id} | Item: {name} (Base ID: {base_id})")
            val_tmpl = await get_localized_message_template(session,interaction.guild_id,"inv_item_list:item_value_field",lang_code,"Owner: {o_type}({o_id}), Qty: {qty}, Equipped: {eq}")

            for ii in inv_items:
                base_item_def = item_defs_dict.get(ii.item_id)
                item_name = base_item_def.name_i18n.get(lang_code, base_item_def.name_i18n.get("en", "Unknown")) if base_item_def else "Unknown Base Item"

                embed.add_field(
                    name=name_tmpl.format(id=ii.id, name=item_name, base_id=ii.item_id),
                    value=val_tmpl.format(o_type=ii.owner_entity_type.name if ii.owner_entity_type else "N/A" , o_id=ii.owner_entity_id, qty=ii.quantity, eq=ii.equipped_status or "N/A"),
                    inline=False
                )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @inventory_item_master_cmds.command(name="create", description="Add an item to an owner's inventory.")
    @app_commands.describe(
        owner_id="Database ID of the owner (Player or GeneratedNPC).",
        owner_type="Type of the owner (PLAYER or GENERATED_NPC).",
        item_id="Database ID of the base Item to add.",
        quantity="Quantity of the item to add (defaults to 1).",
        equipped_status="Optional: Equipped status (e.g., EQUIPPED_MAIN_HAND).",
        properties_json="Optional: JSON string for instance-specific properties."
    )
    async def inventory_item_create(self, interaction: discord.Interaction,
                                    owner_id: int,
                                    owner_type: str,
                                    item_id: int,
                                    quantity: int = 1,
                                    equipped_status: Optional[str] = None,
                                    properties_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)

        lang_code = str(interaction.locale)
        parsed_props: Optional[Dict[str, Any]] = None
        owner_type_enum: OwnerEntityType

        async with get_db_session() as session:
            try:
                owner_type_enum = OwnerEntityType[owner_type.upper()]
            except KeyError:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_create:error_invalid_owner_type",lang_code,"Invalid owner_type. Use PLAYER or GENERATED_NPC.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            owner_exists = False
            if owner_type_enum == OwnerEntityType.PLAYER:
                owner_exists = await player_crud.get_by_id_and_guild(session, id=owner_id, guild_id=interaction.guild_id) is not None
            elif owner_type_enum == OwnerEntityType.GENERATED_NPC:
                owner_exists = await npc_crud.get_by_id_and_guild(session, id=owner_id, guild_id=interaction.guild_id) is not None

            if not owner_exists:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_create:error_owner_not_found",lang_code,"Owner {type}({id}) not found.")
                await interaction.followup.send(error_msg.format(type=owner_type_enum.name, id=owner_id), ephemeral=True); return

            base_item = await item_crud.get_by_id_and_guild(session, id=item_id, guild_id=interaction.guild_id)
            if not base_item:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_create:error_item_def_not_found",lang_code,"Base Item with ID {id} not found in this guild.")
                await interaction.followup.send(error_msg.format(id=item_id), ephemeral=True); return

            if quantity < 1:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_create:error_invalid_quantity",lang_code,"Quantity must be 1 or greater.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            try:
                if properties_json:
                    parsed_props = json.loads(properties_json)
                    if not isinstance(parsed_props, dict): raise ValueError("properties_json must be a dict.")
            except (json.JSONDecodeError, ValueError) as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_create:error_invalid_json_props",lang_code,"Invalid JSON for properties: {details}")
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return

            created_inv_item: Optional[InventoryItem] = None
            try:
                async with session.begin():
                    created_inv_item = await inventory_item_crud.add_item_to_owner(
                        session=session, guild_id=interaction.guild_id,
                        owner_entity_id=owner_id, owner_entity_type=owner_type_enum,
                        item_id=item_id, quantity=quantity,
                        instance_specific_properties_json=parsed_props,
                        equipped_status=equipped_status
                    )
                    if created_inv_item:
                        await session.refresh(created_inv_item)
            except Exception as e:
                logger.error(f"Error in add_item_to_owner or subsequent ops: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_create:error_generic_create",lang_code,"Error adding item to inventory: {error}")
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return

            if not created_inv_item:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_create:error_unknown_fail",lang_code,"Failed to add item to inventory.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_create:success",lang_code,"Item instance ID {id} (Qty: {qty}) added to {owner_type} {owner_id}.")
            await interaction.followup.send(success_msg.format(id=created_inv_item.id, qty=created_inv_item.quantity, owner_type=owner_type_enum.name, owner_id=owner_id), ephemeral=True)

    @inventory_item_master_cmds.command(name="update", description="Update an Inventory Item instance.")
    @app_commands.describe(
        inventory_item_id="Database ID of the InventoryItem to update.",
        field_to_update="Field to update (quantity, equipped_status, properties_json).",
        new_value="New value (integer for quantity; string for equipped_status; JSON string for properties)."
    )
    async def inventory_item_update(self, interaction: discord.Interaction, inventory_item_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)

        allowed_fields = {
            "quantity": int,
            "equipped_status": (str, type(None)),
            "instance_specific_properties_json": dict, # from properties_json
        }

        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()
        db_field_name = field_to_update_lower
        if field_to_update_lower == "properties_json":
            db_field_name = "instance_specific_properties_json"

        field_type_info = allowed_fields.get(db_field_name) # Use db_field_name for lookup

        if not field_type_info:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session,interaction.guild_id,"inv_item_update:error_field_not_allowed",lang_code,"Field '{f}' not allowed. Allowed: {l}")
            await interaction.followup.send(error_msg.format(f=field_to_update, l=', '.join(allowed_fields.keys())), ephemeral=True); return

        parsed_value: Any = None
        async with get_db_session() as session:
            try:
                if db_field_name == "quantity":
                    parsed_value = int(new_value)
                    if parsed_value < 0: raise ValueError("Quantity cannot be negative. Use delete or set to 0 to remove.")
                elif db_field_name == "equipped_status":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = new_value
                elif db_field_name == "instance_specific_properties_json":
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict): raise ValueError("properties_json must be a dict.")
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_update:error_unknown_field",lang_code,"Unknown field for update.")
                    await interaction.followup.send(error_msg, ephemeral=True); return
            except ValueError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_update:error_invalid_value",lang_code,"Invalid value for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return
            except json.JSONDecodeError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_update:error_invalid_json",lang_code,"Invalid JSON for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            inv_item_to_update = await inventory_item_crud.get_by_id_and_guild(session, id=inventory_item_id, guild_id=interaction.guild_id)
            if not inv_item_to_update:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_update:error_not_found",lang_code,"InventoryItem ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=inventory_item_id), ephemeral=True); return

            if db_field_name == "quantity" and parsed_value == 0:
                try:
                    async with session.begin():
                        await inventory_item_crud.remove(session, id=inventory_item_id)
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_update:success_deleted_qty_zero",lang_code,"InventoryItem ID {id} quantity set to 0 and was deleted.")
                    await interaction.followup.send(success_msg.format(id=inventory_item_id), ephemeral=True)
                    return
                except Exception as e:
                    logger.error(f"Error deleting InventoryItem {inventory_item_id} due to quantity 0: {e}", exc_info=True)
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_update:error_delete_on_zero_qty",lang_code,"Error deleting item ID {id} when setting quantity to 0: {err}")
                    await interaction.followup.send(error_msg.format(id=inventory_item_id, err=str(e)), ephemeral=True); return

            update_data = {db_field_name: parsed_value}
            updated_inv_item: Optional[InventoryItem] = None
            try:
                async with session.begin():
                    updated_inv_item = await update_entity(session, entity=inv_item_to_update, data=update_data)
                    await session.flush();
                    if updated_inv_item: await session.refresh(updated_inv_item)
            except Exception as e:
                logger.error(f"Error updating InventoryItem {inventory_item_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_update:error_generic_update",lang_code,"Error updating InventoryItem {id}: {err}")
                await interaction.followup.send(error_msg.format(id=inventory_item_id, err=str(e)), ephemeral=True); return

            if not updated_inv_item:
                 error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_update:error_unknown_update_fail",lang_code,"InventoryItem update failed.")
                 await interaction.followup.send(error_msg, ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_update:success",lang_code,"InventoryItem ID {id} updated. Field '{f}' set to '{v}'.")
            new_val_display = str(parsed_value)
            if isinstance(parsed_value, dict): new_val_display = json.dumps(parsed_value)
            elif parsed_value is None: new_val_display = "None"
            await interaction.followup.send(success_msg.format(id=updated_inv_item.id, f=field_to_update, v=new_val_display), ephemeral=True)

    @inventory_item_master_cmds.command(name="delete", description="Delete an Inventory Item instance.")
    @app_commands.describe(inventory_item_id="The database ID of the InventoryItem to delete.")
    async def inventory_item_delete(self, interaction: discord.Interaction, inventory_item_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        async with get_db_session() as session:
            inv_item_to_delete = await inventory_item_crud.get_by_id_and_guild(session, id=inventory_item_id, guild_id=interaction.guild_id)

            if not inv_item_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_delete:error_not_found",lang_code,"InventoryItem ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=inventory_item_id), ephemeral=True); return

            item_id_for_msg = inv_item_to_delete.item_id
            owner_id_for_msg = inv_item_to_delete.owner_entity_id
            owner_type_for_msg = inv_item_to_delete.owner_entity_type.name if inv_item_to_delete.owner_entity_type else "Unknown"

            deleted_inv_item: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_inv_item = await inventory_item_crud.remove(session, id=inventory_item_id)

                if deleted_inv_item:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_delete:success",lang_code,"InventoryItem ID {id} (Item ID: {item_id}) for Owner {owner_type}({owner_id}) deleted.")
                    await interaction.followup.send(success_msg.format(id=inventory_item_id, item_id=item_id_for_msg, owner_type=owner_type_for_msg, owner_id=owner_id_for_msg ), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_delete:error_unknown_delete_fail",lang_code,"InventoryItem (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=inventory_item_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting InventoryItem {inventory_item_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"inv_item_delete:error_generic_delete",lang_code,"Error deleting InventoryItem ID {id}: {err}")
                await interaction.followup.send(error_msg.format(id=inventory_item_id, err=str(e)), ephemeral=True)

async def setup(bot: commands.Bot):
    cog = MasterInventoryItemCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterInventoryItemCog loaded.")
