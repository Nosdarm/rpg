import logging
import json
from typing import Dict, Any, Optional, List

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, and_, or_

from src.core.crud.crud_crafting_recipe import crud_crafting_recipe
from src.core.crud.crud_item import item_crud # For validating result_item_id and ingredient item_ids
from src.core.crud.crud_skill import skill_crud # For validating required_skill_id (assuming skill_crud exists)
from src.core.database import get_db_session
from src.core.crud_base_definitions import update_entity
from src.core.localization_utils import get_localized_message_template
# from src.models.crafting_recipe import CraftingRecipe # For type hinting if needed directly

logger = logging.getLogger(__name__)

class MasterCraftingRecipeCog(commands.Cog, name="Master Crafting Recipe Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterCraftingRecipeCog initialized.")

    recipe_master_cmds = app_commands.Group(
        name="master_recipe",
        description="Master commands for managing Crafting Recipes.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    async def _format_json_field_helper(self, interaction: discord.Interaction, data: Optional[Dict[Any, Any]], lang_code: str, default_na_key: str, error_key: str) -> str:
        # Helper needs session for localization, get it or pass it
        async with get_db_session() as session: # This creates a new session, consider passing if already in one
            na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
            if not data: return na_str
            try: return json.dumps(data, indent=2, ensure_ascii=False)
            except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

    @recipe_master_cmds.command(name="view", description="View details of a specific Crafting Recipe.")
    @app_commands.describe(recipe_id="The database ID of the Crafting Recipe to view.")
    async def recipe_view(self, interaction: discord.Interaction, recipe_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        current_guild_id_for_context = interaction.guild_id

        if current_guild_id_for_context is None: # Should be handled by guild_only=True on group
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, current_guild_id_for_context, "common:error_guild_only_command", lang_code, "This command must be used in a server.") # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        # lang_code is already defined
        async with get_db_session() as session:
            recipe = await crud_crafting_recipe.get(session, id=recipe_id) # Get by primary ID

            # Check if recipe belongs to the guild or is global
            if not recipe or (recipe.guild_id is not None and recipe.guild_id != interaction.guild_id):
                not_found_msg = await get_localized_message_template(session, interaction.guild_id, "recipe_view:not_found", lang_code, "Recipe with ID {id} not found.")
                await interaction.followup.send(not_found_msg.format(id=recipe_id), ephemeral=True); return

            title_template = await get_localized_message_template(session, interaction.guild_id, "recipe_view:title", lang_code, "Recipe: {name} (ID: {id})")
            recipe_name_display = recipe.name_i18n.get(lang_code, recipe.name_i18n.get("en", f"Recipe {recipe.id}"))
            embed_title = title_template.format(name=recipe_name_display, id=recipe.id)
            embed_color = discord.Color(0xA52A2A) if recipe.guild_id else discord.Color.light_grey() # Brown hex
            embed = discord.Embed(title=embed_title, color=embed_color)

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"recipe_view:label_{key}", lang_code, default)

            na_value_str = await get_localized_message_template(session, current_guild_id_for_context, "common:value_na", lang_code, "N/A")
            scope_global_str = await get_localized_message_template(session, current_guild_id_for_context, "common:scope_global", lang_code, "Global")
            scope_guild_tmpl = await get_localized_message_template(session, current_guild_id_for_context, "common:scope_guild", lang_code, "Guild ({guild_id})")
            scope_display = scope_global_str if recipe.guild_id is None else scope_guild_tmpl.format(guild_id=recipe.guild_id)

            embed.add_field(name=await get_label("scope", "Scope"), value=scope_display, inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=recipe.static_id, inline=True) # static_id is not nullable
            embed.add_field(name=await get_label("result_item_id", "Result Item ID"), value=str(recipe.result_item_id), inline=True)
            embed.add_field(name=await get_label("result_quantity", "Result Quantity"), value=str(recipe.result_quantity), inline=True)
            embed.add_field(name=await get_label("req_skill_id", "Required Skill ID"), value=str(recipe.required_skill_id) if recipe.required_skill_id else na_value_str, inline=True)
            embed.add_field(name=await get_label("req_skill_level", "Required Skill Level"), value=str(recipe.required_skill_level) if recipe.required_skill_level else na_value_str, inline=True)

            name_i18n_str = await self._format_json_field_helper(interaction, recipe.name_i18n, lang_code, "recipe_view:value_na", "recipe_view:error_json")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```", inline=False)
            desc_i18n_str = await self._format_json_field_helper(interaction, recipe.description_i18n, lang_code, "recipe_view:value_na", "recipe_view:error_json")
            embed.add_field(name=await get_label("desc_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```", inline=False)
            ingredients_str = await self._format_json_field_helper(interaction, {"ingredients": recipe.ingredients_json}, lang_code, "recipe_view:value_na", "recipe_view:error_json") # Wrap list in dict for helper
            embed.add_field(name=await get_label("ingredients", "Ingredients JSON"), value=f"```json\n{ingredients_str[:1000]}\n```", inline=False)
            properties_str = await self._format_json_field_helper(interaction, recipe.properties_json, lang_code, "recipe_view:value_na", "recipe_view:error_json")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{properties_str[:1000]}\n```", inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @recipe_master_cmds.command(name="list", description="List Crafting Recipes.")
    @app_commands.describe(scope="Filter by scope ('guild', 'global', 'all'). Defaults to 'all'.", page="Page number.", limit="Recipes per page.")
    @app_commands.choices(scope=[app_commands.Choice(name="All (Guild & Global)", value="all"), app_commands.Choice(name="Guild-Specific", value="guild"), app_commands.Choice(name="Global Only", value="global"),])
    async def recipe_list(self, interaction: discord.Interaction, scope: Optional[app_commands.Choice[str]] = None, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10
        lang_code = str(interaction.locale)

        # Guild ID is needed for localization and for 'guild' or 'all' scope when in a guild
        current_guild_id_for_context = interaction.guild_id
        if scope and scope.value == "guild" and current_guild_id_for_context is None:
            await interaction.followup.send("Guild-specific scope requires this command to be used in a guild.", ephemeral=True); return

        async with get_db_session() as session:
            scope_value = scope.value if scope else "all"
            recipes = await crud_crafting_recipe.get_multi_by_guild_or_global(session, guild_id=current_guild_id_for_context if scope_value != "global" else None, skip=(page-1)*limit, limit=limit)
            total_recipes = await crud_crafting_recipe.get_all_for_guild_or_global_count(session, guild_id=current_guild_id_for_context if scope_value != "global" else None)

            scope_display_key = f"recipe_list:scope_{scope_value}"; scope_display_default = scope_value.capitalize()
            scope_display = await get_localized_message_template(session, current_guild_id_for_context, scope_display_key, lang_code, scope_display_default)

            if not recipes:
                no_recipes_msg = await get_localized_message_template(session,current_guild_id_for_context,"recipe_list:no_recipes_found",lang_code,"No Recipes for scope '{sc}' (Page {p}).")
                await interaction.followup.send(no_recipes_msg.format(sc=scope_display, p=page), ephemeral=True); return

            title_tmpl = await get_localized_message_template(session,current_guild_id_for_context,"recipe_list:title",lang_code,"Recipe List ({scope} - Page {p} of {tp})")
            total_pages = ((total_recipes - 1) // limit) + 1
            embed = discord.Embed(title=title_tmpl.format(scope=scope_display, p=page, tp=total_pages), color=discord.Color.dark_orange())
            footer_tmpl = await get_localized_message_template(session,current_guild_id_for_context,"recipe_list:footer",lang_code,"Displaying {c} of {t} total Recipes.")
            embed.set_footer(text=footer_tmpl.format(c=len(recipes), t=total_recipes))
            name_tmpl = await get_localized_message_template(session,current_guild_id_for_context,"recipe_list:recipe_name_field",lang_code,"ID: {id} | {name} (Static: {sid})")
            val_tmpl = await get_localized_message_template(session,current_guild_id_for_context,"recipe_list:recipe_value_field",lang_code,"Result: Item ID {res_id} (Qty: {res_qty}), Scope: {scope_val}")

            for rcp in recipes:
                rcp_name = rcp.name_i18n.get(lang_code, rcp.name_i18n.get("en", "N/A"))
                scope_val_disp = "Global" if rcp.guild_id is None else f"Guild ({rcp.guild_id})"
                embed.add_field(name=name_tmpl.format(id=rcp.id, name=rcp_name, sid=rcp.static_id or "N/A"), value=val_tmpl.format(res_id=rcp.result_item_id, res_qty=rcp.result_quantity, scope_val=scope_val_disp), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @recipe_master_cmds.command(name="create", description="Create a new Crafting Recipe.")
    @app_commands.describe(
        static_id="Static ID for this recipe (unique for its scope: global or guild).",
        name_i18n_json="JSON for recipe name (e.g., {\"en\": \"Healing Potion Recipe\"}).",
        result_item_id="Database ID of the Item this recipe produces.",
        result_quantity="Quantity of the item produced (defaults to 1).",
        ingredients_json="JSON array of ingredients (e.g., [{\"item_id\": 1, \"quantity\": 2}, {\"item_id\": 2, \"quantity\": 1}]).",
        description_i18n_json="Optional: JSON for recipe description.",
        required_skill_id="Optional: Database ID of the Skill required to craft this.",
        required_skill_level="Optional: Level of the skill required.",
        properties_json="Optional: JSON for additional properties (e.g., crafting station).",
        is_global="Set to True if this is a global recipe. Defaults to False (guild-specific)."
    )
    async def recipe_create(self, interaction: discord.Interaction,
                            static_id: str,
                            name_i18n_json: str,
                            result_item_id: int,
                            ingredients_json: str,
                            result_quantity: int = 1,
                            description_i18n_json: Optional[str] = None,
                            required_skill_id: Optional[int] = None,
                            required_skill_level: Optional[int] = None,
                            properties_json: Optional[str] = None,
                            is_global: bool = False):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        parsed_name_i18n: Dict[str, str]
        parsed_desc_i18n: Optional[Dict[str, str]] = None
        parsed_ingredients: List[Dict[str, Any]]
        parsed_props: Optional[Dict[str, Any]] = None

        target_guild_id_for_recipe: Optional[int] = interaction.guild_id if not is_global else None
        # Guild ID for messages should be interaction.guild_id if available, or a fallback for global context
        current_guild_id_for_messages: Optional[int] = interaction.guild_id

        if not is_global and current_guild_id_for_messages is None:
            await interaction.followup.send("Cannot create a guild-specific recipe outside of a guild. Use `is_global=True` or run in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            # Validate static_id uniqueness
            existing_recipe_static = await crud_crafting_recipe.get_by_static_id(session, static_id=static_id, guild_id=target_guild_id_for_recipe)
            if existing_recipe_static:
                scope_str = "global" if target_guild_id_for_recipe is None else f"guild {target_guild_id_for_recipe}"
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "recipe_create:error_static_id_exists", lang_code, "Recipe static_id '{id}' already exists in scope {sc}.")
                await interaction.followup.send(error_msg.format(id=static_id, sc=scope_str), ephemeral=True); return

            # Validate result_item_id (check if item exists, could be global or guild-specific)
            res_item = await item_crud.get(session, id=result_item_id, guild_id=current_guild_id_for_messages) # Check in current guild
            if not res_item: # If not in current guild, check global
                 res_item = await item_crud.get(session, id=result_item_id, guild_id=None)
            if not res_item:
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "recipe_create:error_result_item_not_found", lang_code, "Result Item ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=result_item_id), ephemeral=True); return

            # Validate required_skill_id (if provided)
            if required_skill_id:
                # Skills can be global or guild-specific, similar to items/abilities
                req_skill = await skill_crud.get(session, id=required_skill_id, guild_id=current_guild_id_for_messages)
                if not req_skill: # Fallback to global
                    req_skill = await skill_crud.get(session, id=required_skill_id, guild_id=None)
                if not req_skill:
                    error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "recipe_create:error_skill_not_found", lang_code, "Required Skill ID {id} not found.")
                    await interaction.followup.send(error_msg.format(id=required_skill_id), ephemeral=True); return

            if result_quantity < 1: result_quantity = 1

            try:
                parsed_name_i18n = json.loads(name_i18n_json)
                if not isinstance(parsed_name_i18n, dict) or not all(isinstance(k,str)and isinstance(v,str) for k,v in parsed_name_i18n.items()): raise ValueError("name_i18n_json must be dict str:str.")
                if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code): raise ValueError("name_i18n_json must contain 'en' or current language key.")

                parsed_ingredients = json.loads(ingredients_json)
                if not isinstance(parsed_ingredients, list) or not all(isinstance(ing, dict) and isinstance(ing.get("item_id"), int) and isinstance(ing.get("quantity"), int) and ing["quantity"] > 0 for ing in parsed_ingredients):
                    raise ValueError("ingredients_json must be a list of objects, each with 'item_id' (int) and 'quantity' (int > 0).")

                # Validate ingredient item_ids
                ingredient_item_ids = [ing["item_id"] for ing in parsed_ingredients]
                if ingredient_item_ids:
                    # Fetch both guild-specific and global items that match these IDs
                    # This check is simplified; ideally, it should confirm each specific item_id exists.
                    # A more robust check would iterate and try fetching each item_id.
                    # For now, assuming item_crud.get_many_by_ids can find them across scopes if designed that way,
                    # or we check each one individually.
                    # Let's do a quick check for each.
                    for ing_item_id in ingredient_item_ids:
                        ing_item_def = await item_crud.get(session, id=ing_item_id, guild_id=current_guild_id_for_messages)
                        if not ing_item_def: ing_item_def = await item_crud.get(session, id=ing_item_id, guild_id=None)
                        if not ing_item_def:
                            raise ValueError(f"Ingredient Item ID {ing_item_id} not found.")

                if description_i18n_json:
                    parsed_desc_i18n = json.loads(description_i18n_json)
                    if not isinstance(parsed_desc_i18n, dict) or not all(isinstance(k,str)and isinstance(v,str) for k,v in parsed_desc_i18n.items()): raise ValueError("description_i18n_json must be dict str:str.")
                if properties_json:
                    parsed_props = json.loads(properties_json)
                    if not isinstance(parsed_props, dict): raise ValueError("properties_json must be a dict.")
            except (json.JSONDecodeError, ValueError, AssertionError) as e:
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "recipe_create:error_invalid_json_data", lang_code, "Invalid JSON or data: {details}")
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return

            recipe_data_create: Dict[str, Any] = {
                "guild_id": target_guild_id_for_recipe,
                "static_id": static_id,
                "name_i18n": parsed_name_i18n,
                "description_i18n": parsed_desc_i18n or {},
                "result_item_id": result_item_id,
                "result_quantity": result_quantity,
                "ingredients_json": parsed_ingredients,
                "required_skill_id": required_skill_id,
                "required_skill_level": required_skill_level,
                "properties_json": parsed_props or {}
            }
            created_recipe: Optional[Any] = None
            try:
                async with session.begin():
                    created_recipe = await crud_crafting_recipe.create(session, obj_in=recipe_data_create)
                    await session.flush();
                    if created_recipe: await session.refresh(created_recipe)
            except Exception as e:
                logger.error(f"Error creating Crafting Recipe: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "recipe_create:error_generic_create", lang_code, "Error creating recipe: {error}")
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return

            if not created_recipe:
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "recipe_create:error_unknown_fail", lang_code, "Recipe creation failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title = await get_localized_message_template(session, current_guild_id_for_messages, "recipe_create:success_title", lang_code, "Recipe Created: {name} (ID: {id})")
            created_name = created_recipe.name_i18n.get(lang_code, created_recipe.name_i18n.get("en", ""))
            scope_disp = "Global" if created_recipe.guild_id is None else f"Guild {created_recipe.guild_id}"
            embed = discord.Embed(title=success_title.format(name=created_name, id=created_recipe.id), color=discord.Color.green())
            embed.add_field(name="Static ID", value=created_recipe.static_id, inline=True)
            embed.add_field(name="Scope", value=scope_disp, inline=True)
            embed.add_field(name="Result Item ID", value=str(created_recipe.result_item_id), inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @recipe_master_cmds.command(name="update", description="Update a specific Crafting Recipe.")
    @app_commands.describe(
        recipe_id="ID of the recipe to update.",
        field_to_update="Field to update (e.g., static_id, name_i18n_json, result_item_id, ingredients_json).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable fields)."
    )
    async def recipe_update(self, interaction: discord.Interaction, recipe_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        current_guild_id_for_messages: Optional[int] = interaction.guild_id # For messages
        if not current_guild_id_for_messages : # Should not happen due to guild_only=True
             await interaction.followup.send("Command must be used in a guild context for updates.", ephemeral=True); return

        allowed_fields = {
            "static_id": str, "name_i18n": dict, "description_i18n": dict,
            "result_item_id": int, "result_quantity": int, "ingredients_json": list,
            "required_skill_id": (int, type(None)), "required_skill_level": (int, type(None)),
            "properties_json": dict
        }
        field_to_update_lower = field_to_update.lower()
        db_field_name = field_to_update_lower
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json", "") in allowed_fields:
            db_field_name = field_to_update_lower.replace("_json", "")

        field_type_info = allowed_fields.get(db_field_name)
        if not field_type_info:
            async with get_db_session() as temp_session: error_msg = await get_localized_message_template(temp_session, current_guild_id_for_messages, "recipe_update:error_field_not_allowed", lang_code, "Field '{f}' not allowed.")
            await interaction.followup.send(error_msg.format(f=field_to_update), ephemeral=True); return

        parsed_value: Any = None
        from typing import cast # For casting IDs

        async with get_db_session() as session:
            recipe_to_update = await crud_crafting_recipe.get(session, id=recipe_id) # Get by primary ID
            if not recipe_to_update or (recipe_to_update.guild_id is not None and recipe_to_update.guild_id != current_guild_id_for_messages):
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "recipe_update:error_not_found", lang_code, "Recipe ID {id} not found or not accessible.")
                await interaction.followup.send(error_msg.format(id=recipe_id), ephemeral=True); return

            original_recipe_guild_id_scope = recipe_to_update.guild_id # This is the scope for static_id check

            try:
                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: raise ValueError("static_id cannot be empty.")
                    existing_recipe = await crud_crafting_recipe.get_by_static_id(session, static_id=parsed_value, guild_id=original_recipe_guild_id_scope)
                    if existing_recipe and existing_recipe.id != recipe_id:
                        error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "recipe_update:error_static_id_exists", lang_code, "Static ID '{id}' already in use for its scope.")
                        await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                elif field_type_info == dict: parsed_value = json.loads(new_value); assert isinstance(parsed_value, dict)
                elif field_type_info == list: parsed_value = json.loads(new_value); assert isinstance(parsed_value, list)
                elif field_type_info == int: parsed_value = int(new_value)
                elif isinstance(field_type_info, tuple) and int in field_type_info and type(None) in field_type_info: # Optional[int]
                    if new_value.lower() == 'none' or new_value.lower() == 'null': parsed_value = None
                    else: parsed_value = int(new_value)
                else: raise ValueError(f"Unsupported type for field {db_field_name}")

                # Validations for specific fields
                if db_field_name == "result_item_id":
                    item_id_to_check = cast(int, parsed_value)
                    res_item_val = await item_crud.get(session, id=item_id_to_check, guild_id=current_guild_id_for_messages)
                    if not res_item_val: res_item_val = await item_crud.get(session, id=item_id_to_check, guild_id=None)
                    if not res_item_val: raise ValueError(f"Result Item ID {item_id_to_check} not found.")
                if db_field_name == "ingredients_json":
                    if not all(isinstance(ing, dict) and isinstance(ing.get("item_id"), int) and isinstance(ing.get("quantity"), int) and ing["quantity"] > 0 for ing in parsed_value): # type: ignore
                        raise ValueError("ingredients_json must be list of {'item_id': int, 'quantity': int > 0}.")
                    for ing in parsed_value: # type: ignore
                        ing_item_id_val = cast(int, ing["item_id"])
                        ing_item_def = await item_crud.get(session, id=ing_item_id_val, guild_id=current_guild_id_for_messages)
                        if not ing_item_def: ing_item_def = await item_crud.get(session, id=ing_item_id_val, guild_id=None)
                        if not ing_item_def: raise ValueError(f"Ingredient Item ID {ing_item_id_val} not found.")
                if db_field_name == "required_skill_id" and parsed_value is not None:
                    skill_id_to_check = cast(int, parsed_value)
                    req_skill_val = await skill_crud.get(session, id=skill_id_to_check, guild_id=current_guild_id_for_messages)
                    if not req_skill_val: req_skill_val = await skill_crud.get(session, id=skill_id_to_check, guild_id=None)
                    if not req_skill_val: raise ValueError(f"Required Skill ID {skill_id_to_check} not found.")

            except (ValueError, json.JSONDecodeError, AssertionError) as e:
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "recipe_update:error_invalid_value", lang_code, "Invalid value for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            update_data = {db_field_name: parsed_value}
            updated_recipe: Optional[Any] = None
            try:
                async with session.begin():
                    updated_recipe = await update_entity(session, entity=recipe_to_update, data=update_data)
                    await session.flush();
                    if updated_recipe: await session.refresh(updated_recipe)
            except Exception as e:
                logger.error(f"Error updating Recipe {recipe_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "recipe_update:error_generic_update", lang_code, "Error updating Recipe {id}: {err}")
                await interaction.followup.send(error_msg.format(id=recipe_id, err=str(e)), ephemeral=True); return

            if not updated_recipe:
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "recipe_update:error_unknown_fail", lang_code, "Recipe update failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_msg = await get_localized_message_template(session, current_guild_id_for_messages, "recipe_update:success", lang_code, "Recipe ID {id} updated. Field '{f}' set to '{v}'.")
            new_val_display = str(parsed_value)
            if isinstance(parsed_value, (dict, list)): new_val_display = json.dumps(parsed_value)
            elif parsed_value is None: new_val_display = "None"
            await interaction.followup.send(success_msg.format(id=updated_recipe.id, f=field_to_update, v=new_val_display), ephemeral=True)

    @recipe_master_cmds.command(name="delete", description="Delete a Crafting Recipe.")
    @app_commands.describe(recipe_id="The database ID of the Crafting Recipe to delete.")
    async def recipe_delete(self, interaction: discord.Interaction, recipe_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        current_guild_id_for_messages: Optional[int] = interaction.guild_id
        if not current_guild_id_for_messages:
            await interaction.followup.send("Command must be used in a guild context for this operation.", ephemeral=True); return

        async with get_db_session() as session:
            recipe_to_delete = await crud_crafting_recipe.get(session, id=recipe_id)
            if not recipe_to_delete or (recipe_to_delete.guild_id is not None and recipe_to_delete.guild_id != current_guild_id_for_messages):
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "recipe_delete:error_not_found", lang_code, "Recipe ID {id} not found or not accessible.")
                await interaction.followup.send(error_msg.format(id=recipe_id), ephemeral=True); return

            recipe_name_for_msg = recipe_to_delete.name_i18n.get(lang_code, recipe_to_delete.name_i18n.get("en", f"Recipe {recipe_id}"))
            scope_for_msg = "Global" if recipe_to_delete.guild_id is None else f"Guild {recipe_to_delete.guild_id}"

            # Add dependency checks here if necessary (e.g., if players have learned this recipe)

            deleted_recipe: Optional[Any] = None
            try:
                async with session.begin():
                    # crud_crafting_recipe.delete needs to handle guild_id (or None for global) correctly or remove by ID only.
                    # Since we fetched by ID and verified scope, deleting by ID should be fine.
                    deleted_recipe = await crud_crafting_recipe.delete(session, id=recipe_id) # Assuming delete by ID is sufficient after scope check
                if deleted_recipe:
                    success_msg = await get_localized_message_template(session, current_guild_id_for_messages, "recipe_delete:success", lang_code, "Recipe '{name}' (ID: {id}, Scope: {scope}) deleted.")
                    await interaction.followup.send(success_msg.format(name=recipe_name_for_msg, id=recipe_id, scope=scope_for_msg), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "recipe_delete:error_unknown_fail", lang_code, "Recipe (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=recipe_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Recipe {recipe_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "recipe_delete:error_generic_delete", lang_code, "Error deleting Recipe '{name}' (ID: {id}): {err}")
                await interaction.followup.send(error_msg.format(name=recipe_name_for_msg, id=recipe_id, err=str(e)), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MasterCraftingRecipeCog(bot))
    logger.info("MasterCraftingRecipeCog loaded.")

# Placeholder for skill_crud if not already defined elsewhere
# class CRUDSkillPlaceholder: async def get(self, session, id, guild_id): return None
# skill_crud = CRUDSkillPlaceholder()
# This should be imported from its actual location if it exists
try:
    from src.core.crud.crud_skill import skill_crud
except ImportError:
    logger.warning("skill_crud not found, MasterCraftingRecipeCog may have limited validation for required_skill_id.")
    # Define a dummy if not available to prevent NameError, real one should be used
    class DummySkillCRUD:
        async def get(self, session: Any, *, id: int, guild_id: Optional[int] = None) -> Optional[Any]:
            return None
    skill_crud = DummySkillCRUD() # type: ignore
