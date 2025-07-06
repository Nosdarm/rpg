import logging
import json
from typing import Dict, Any, Optional, List

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, and_, or_

from src.core.crud.crud_status_effect import status_effect_crud, active_status_effect_crud
from src.core.database import get_db_session
from src.core.crud_base_definitions import update_entity
from src.core.localization_utils import get_localized_message_template
from src.models.enums import StatusEffectCategory as StatusEffectCategoryEnum, RelationshipEntityType # RelationshipEntityType for ActiveSE

logger = logging.getLogger(__name__)

class MasterStatusEffectCog(commands.Cog, name="Master Status Effect Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterStatusEffectCog initialized.")

    status_effect_master_cmds = app_commands.Group(
        name="master_status_effect",
        description="Master commands for managing Status Effects (definitions and active instances).",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    # --- StatusEffect Definition Subcommands ---
    @status_effect_master_cmds.command(name="definition_view", description="View details of a Status Effect definition.")
    @app_commands.describe(status_effect_id="The database ID of the StatusEffect definition to view.")
    async def status_effect_def_view(self, interaction: discord.Interaction, status_effect_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None: # Check guild_id early
            await interaction.followup.send("This command can only be used in a guild if viewing guild-specific effects.", ephemeral=True)
            # Allow viewing global effects even if guild_id is None
            # The logic below handles fetching global effects if guild_id is None or guild-specific if present.

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            # Try to get by ID, respecting guild_id if present, or allowing global if guild_id is None
            se_def = await status_effect_crud.get_by_id(session, id=status_effect_id, guild_id=interaction.guild_id)
            if not se_def and interaction.guild_id is not None: # If not found in guild, try global
                 global_se_def = await status_effect_crud.get_by_id(session, id=status_effect_id, guild_id=None)
                 if global_se_def:
                     se_def = global_se_def
            elif not se_def and interaction.guild_id is None: # If called from DM and not found as global
                 pass # se_def remains None

            if not se_def:
                not_found_msg = await get_localized_message_template(session, interaction.guild_id, "se_def_view:not_found", lang_code, "StatusEffect definition with ID {id} not found.") # type: ignore
                await interaction.followup.send(not_found_msg.format(id=status_effect_id), ephemeral=True); return

            title_template = await get_localized_message_template(session, interaction.guild_id, "se_def_view:title", lang_code, "StatusEffect Definition: {name} (ID: {id})") # type: ignore
            name_display = se_def.name_i18n.get(lang_code, se_def.name_i18n.get("en", f"StatusEffect {se_def.id}"))
            embed_title = title_template.format(name=name_display, id=se_def.id)
            embed_color = discord.Color.dark_green() if se_def.guild_id else discord.Color.dark_grey()
            embed = discord.Embed(title=embed_title, color=embed_color)

            async def get_label(key: str, default: str) -> str: return await get_localized_message_template(session, interaction.guild_id, f"se_def_view:label_{key}", lang_code, default) # type: ignore
            async def format_json_field_helper(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available") # type: ignore
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON") # type: ignore

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(se_def.guild_id) if se_def.guild_id else "Global", inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=se_def.static_id or "N/A", inline=True)
            embed.add_field(name=await get_label("category", "Category"), value=se_def.category.value if se_def.category else "N/A", inline=True) # type: ignore
            name_i18n_str = await format_json_field_helper(se_def.name_i18n, "se_def_view:value_na_json", "se_def_view:error_serialization_name")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```" + ("..." if len(name_i18n_str) > 1000 else ""), inline=False)
            desc_i18n_str = await format_json_field_helper(se_def.description_i18n, "se_def_view:value_na_json", "se_def_view:error_serialization_desc")
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```" + ("..." if len(desc_i18n_str) > 1000 else ""), inline=False)
            props_str = await format_json_field_helper(se_def.properties_json, "se_def_view:value_na_json", "se_def_view:error_serialization_props")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{props_str[:1000]}\n```" + ("..." if len(props_str) > 1000 else ""), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @status_effect_master_cmds.command(name="definition_list", description="List Status Effect definitions.")
    @app_commands.describe(scope="Scope to filter by ('guild', 'global', or 'all'). Defaults to 'all'.", page="Page number.", limit="Definitions per page.")
    @app_commands.choices(scope=[app_commands.Choice(name="All (Guild & Global)", value="all"), app_commands.Choice(name="Guild-Specific", value="guild"), app_commands.Choice(name="Global Only", value="global"),])
    async def status_effect_def_list(self, interaction: discord.Interaction, scope: Optional[app_commands.Choice[str]] = None, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10
        lang_code = str(interaction.locale)

        # Early guild_id check for guild-specific scope
        if scope and scope.value == "guild" and interaction.guild_id is None:
            await interaction.followup.send("Guild-specific scope requires this command to be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            filters = []
            scope_value = scope.value if scope else "all"

            if scope_value == "guild":
                if interaction.guild_id is None: # Should have been caught above, but as a safeguard
                    await interaction.followup.send("Cannot list guild-specific effects outside of a guild.", ephemeral=True)
                    return
                filters.append(status_effect_crud.model.guild_id == interaction.guild_id)
            elif scope_value == "global":
                filters.append(status_effect_crud.model.guild_id.is_(None))
            else: # 'all'
                if interaction.guild_id is not None:
                    filters.append(or_(status_effect_crud.model.guild_id == interaction.guild_id, status_effect_crud.model.guild_id.is_(None)))
                else: # If in DM and scope is 'all', only show global
                    filters.append(status_effect_crud.model.guild_id.is_(None))

            offset = (page - 1) * limit
            query = select(status_effect_crud.model).where(and_(*filters)).offset(offset).limit(limit).order_by(status_effect_crud.model.id.desc())
            result = await session.execute(query)
            se_defs = result.scalars().all()
            count_query = select(func.count(status_effect_crud.model.id)).where(and_(*filters))
            total_defs_res = await session.execute(count_query)
            total_definitions = total_defs_res.scalar_one_or_none() or 0

            scope_display_key = f"se_def_list:scope_{scope_value}"; scope_display_default = scope_value.capitalize()
            scope_display = await get_localized_message_template(session, interaction.guild_id, scope_display_key, lang_code, scope_display_default) # type: ignore
            if not se_defs:
                no_defs_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_list:no_defs_found",lang_code,"No StatusEffect definitions found for scope '{sc}' (Page {p}).") # type: ignore
                await interaction.followup.send(no_defs_msg.format(sc=scope_display, p=page), ephemeral=True); return
            title_tmpl = await get_localized_message_template(session,interaction.guild_id,"se_def_list:title",lang_code,"StatusEffect Definition List ({scope} - Page {p} of {tp})") # type: ignore
            total_pages = ((total_definitions - 1) // limit) + 1
            embed = discord.Embed(title=title_tmpl.format(scope=scope_display, p=page, tp=total_pages), color=discord.Color.dark_teal())
            footer_tmpl = await get_localized_message_template(session,interaction.guild_id,"se_def_list:footer",lang_code,"Displaying {c} of {t} total definitions.") # type: ignore
            embed.set_footer(text=footer_tmpl.format(c=len(se_defs), t=total_definitions))
            name_tmpl = await get_localized_message_template(session,interaction.guild_id,"se_def_list:def_name_field",lang_code,"ID: {id} | {name} (Static: {sid})") # type: ignore
            val_tmpl = await get_localized_message_template(session,interaction.guild_id,"se_def_list:def_value_field",lang_code,"Category: {cat}, Scope: {scope_val}") # type: ignore
            for se_def in se_defs:
                se_name = se_def.name_i18n.get(lang_code, se_def.name_i18n.get("en", "N/A"))
                scope_val_disp = "Global" if se_def.guild_id is None else f"Guild ({se_def.guild_id})"
                embed.add_field(name=name_tmpl.format(id=se_def.id, name=se_name, sid=se_def.static_id or "N/A"), value=val_tmpl.format(cat=se_def.category.value if se_def.category else "N/A", scope_val=scope_val_disp), inline=False) # type: ignore
            await interaction.followup.send(embed=embed, ephemeral=True)

    @status_effect_master_cmds.command(name="definition_create", description="Create a new Status Effect definition.")
    @app_commands.describe(static_id="Static ID (unique for its scope: global or guild).", name_i18n_json="JSON for name (e.g., {\"en\": \"Poisoned\", \"ru\": \"Отравлен\"}).", category="Category (BUFF, DEBUFF, NEUTRAL).", description_i18n_json="Optional: JSON for description.", properties_json="Optional: JSON for properties (effects, duration rules, etc.).", is_global="Set to True if this is a global definition. Defaults to False (guild-specific).")
    @app_commands.choices(category=[app_commands.Choice(name="Buff", value="BUFF"), app_commands.Choice(name="Debuff", value="DEBUFF"), app_commands.Choice(name="Neutral", value="NEUTRAL"),])
    async def status_effect_def_create(self, interaction: discord.Interaction, static_id: str, name_i18n_json: str, category: app_commands.Choice[str], description_i18n_json: Optional[str] = None, properties_json: Optional[str] = None, is_global: bool = False):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        parsed_name_i18n: Dict[str, str]; parsed_desc_i18n: Optional[Dict[str, str]] = None; parsed_props: Optional[Dict[str, Any]] = None
        target_guild_id: Optional[int] = interaction.guild_id if not is_global else None

        if not is_global and interaction.guild_id is None:
            await interaction.followup.send("Cannot create a guild-specific status effect outside of a guild. Use `is_global=True` or run in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            existing_se_static = await status_effect_crud.get_by_static_id(session, static_id=static_id, guild_id=target_guild_id)
            if existing_se_static:
                scope_str = "global" if target_guild_id is None else f"guild {target_guild_id}"
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_create:error_static_id_exists",lang_code,"StatusEffect static_id '{id}' already exists in scope {sc}.") # type: ignore
                await interaction.followup.send(error_msg.format(id=static_id, sc=scope_str), ephemeral=True); return
            try:
                category_enum = StatusEffectCategoryEnum[category.value]
                parsed_name_i18n = json.loads(name_i18n_json)
                if not isinstance(parsed_name_i18n, dict) or not all(isinstance(k,str)and isinstance(v,str) for k,v in parsed_name_i18n.items()): raise ValueError("name_i18n_json must be a dict of str:str.")
                if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code): raise ValueError("name_i18n_json must contain 'en' or current language key.")
                if description_i18n_json:
                    parsed_desc_i18n = json.loads(description_i18n_json)
                    if not isinstance(parsed_desc_i18n, dict) or not all(isinstance(k,str)and isinstance(v,str) for k,v in parsed_desc_i18n.items()): raise ValueError("description_i18n_json must be a dict of str:str.")
                if properties_json:
                    parsed_props = json.loads(properties_json)
                    if not isinstance(parsed_props, dict): raise ValueError("properties_json must be a dict.")
            except ValueError as e: # Specific exception first
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_create:error_invalid_input",lang_code,"Invalid input: {details}") # type: ignore
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return
            except json.JSONDecodeError as e: # Broader exception later
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_create:error_invalid_input",lang_code,"Invalid input: {details}") # type: ignore
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return
            except KeyError as e: # For StatusEffectCategoryEnum
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_create:error_invalid_input",lang_code,"Invalid input: {details}") # type: ignore
                await interaction.followup.send(error_msg.format(details=f"Invalid category value: {str(e)}"), ephemeral=True); return


            se_data_create: Dict[str, Any] = {"guild_id": target_guild_id, "static_id": static_id, "name_i18n": parsed_name_i18n, "description_i18n": parsed_desc_i18n or {}, "category": category_enum, "properties_json": parsed_props or {}}
            created_se: Optional[Any] = None
            try:
                async with session.begin():
                    created_se = await status_effect_crud.create_with_guild_or_global(session, obj_in=se_data_create, guild_id=target_guild_id) # type: ignore
                    await session.flush();
                    if created_se: await session.refresh(created_se)
            except Exception as e:
                logger.error(f"Error creating StatusEffect definition: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_create:error_generic_create",lang_code,"Error creating definition: {error}") # type: ignore
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return
            if not created_se:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_create:error_unknown_fail",lang_code,"Definition creation failed.") # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title = await get_localized_message_template(session,interaction.guild_id,"se_def_create:success_title",lang_code,"StatusEffect Definition Created: {name} (ID: {id})") # type: ignore
            created_name = created_se.name_i18n.get(lang_code, created_se.name_i18n.get("en", ""))
            scope_disp = "Global" if created_se.guild_id is None else f"Guild {created_se.guild_id}"
            embed = discord.Embed(title=success_title.format(name=created_name, id=created_se.id), color=discord.Color.green())
            embed.add_field(name="Static ID", value=created_se.static_id, inline=True); embed.add_field(name="Category", value=created_se.category.value, inline=True); embed.add_field(name="Scope", value=scope_disp, inline=True) # type: ignore
            await interaction.followup.send(embed=embed, ephemeral=True)

    @status_effect_master_cmds.command(name="definition_update", description="Update a Status Effect definition.")
    @app_commands.describe(status_effect_id="ID of the StatusEffect definition to update.", field_to_update="Field to update (e.g., static_id, name_i18n_json, category, properties_json).", new_value="New value for the field.")
    @app_commands.choices(field_to_update=[app_commands.Choice(name="Static ID", value="static_id"), app_commands.Choice(name="Name (i18n JSON)", value="name_i18n_json"), app_commands.Choice(name="Description (i18n JSON)", value="description_i18n_json"), app_commands.Choice(name="Category (BUFF/DEBUFF/NEUTRAL)", value="category"), app_commands.Choice(name="Properties (JSON)", value="properties_json"),])
    async def status_effect_def_update(self, interaction: discord.Interaction, status_effect_id: int, field_to_update: app_commands.Choice[str], new_value: str):
        await interaction.response.defer(ephemeral=True)
        allowed_fields_map = {"static_id": {"db_field": "static_id", "type": str}, "name_i18n_json": {"db_field": "name_i18n", "type": dict}, "description_i18n_json": {"db_field": "description_i18n", "type": dict}, "category": {"db_field": "category", "type": StatusEffectCategoryEnum}, "properties_json": {"db_field": "properties_json", "type": dict},}
        lang_code = str(interaction.locale); command_field_name = field_to_update.value

        if command_field_name not in allowed_fields_map: # This check should ideally be redundant due to @app_commands.choices
            async with get_db_session() as temp_session: error_msg = await get_localized_message_template(temp_session,interaction.guild_id,"se_def_update:error_field_not_allowed_internal",lang_code,"Internal error: Invalid field choice.") # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True); return

        db_field_name = allowed_fields_map[command_field_name]["db_field"]; expected_type = allowed_fields_map[command_field_name]["type"]
        parsed_value: Any = None

        async with get_db_session() as session:
            # Determine if we are updating a guild-specific or global effect
            se_def_to_update = await status_effect_crud.get_by_id(session, id=status_effect_id, guild_id=interaction.guild_id)
            original_guild_id_for_check = interaction.guild_id # Used for static_id uniqueness check
            if not se_def_to_update and interaction.guild_id is not None: # If not found in guild, try global
                global_se_def = await status_effect_crud.get_by_id(session, id=status_effect_id, guild_id=None)
                if global_se_def:
                    se_def_to_update = global_se_def
                    original_guild_id_for_check = None # Check static_id globally
            elif not se_def_to_update and interaction.guild_id is None: # If in DM, it must be global
                 se_def_to_update = await status_effect_crud.get_by_id(session, id=status_effect_id, guild_id=None)
                 original_guild_id_for_check = None


            if not se_def_to_update:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:error_not_found",lang_code,"StatusEffect def ID {id} not found.") # type: ignore
                await interaction.followup.send(error_msg.format(id=status_effect_id), ephemeral=True); return
            try:
                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: raise ValueError("static_id cannot be empty.")
                    existing_se = await status_effect_crud.get_by_static_id(session, static_id=parsed_value, guild_id=original_guild_id_for_check)
                    if existing_se and existing_se.id != status_effect_id:
                        scope_str = "global" if original_guild_id_for_check is None else f"guild {original_guild_id_for_check}"
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:error_static_id_exists",lang_code,"Static ID '{id}' already in use for scope {sc}.") # type: ignore
                        await interaction.followup.send(error_msg.format(id=parsed_value, sc=scope_str), ephemeral=True); return
                elif expected_type == dict:
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict): raise ValueError(f"{command_field_name} must be a dict.")
                elif expected_type == StatusEffectCategoryEnum:
                    try: parsed_value = StatusEffectCategoryEnum[new_value.upper()]
                    except KeyError: raise ValueError(f"Invalid category. Use {', '.join([c.name for c in StatusEffectCategoryEnum])}")
                else: parsed_value = new_value # Should be str
            except ValueError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:error_invalid_value",lang_code,"Invalid value for {f}: {details}") # type: ignore
                await interaction.followup.send(error_msg.format(f=command_field_name, details=str(e)), ephemeral=True); return
            except json.JSONDecodeError as e: # Broader exception later
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:error_invalid_json",lang_code,"Invalid JSON for {f}: {details}") # type: ignore
                await interaction.followup.send(error_msg.format(f=command_field_name, details=str(e)), ephemeral=True); return

            update_data = {db_field_name: parsed_value}
            updated_se: Optional[Any] = None
            try:
                async with session.begin():
                    updated_se = await update_entity(session, entity=se_def_to_update, data=update_data)
                    await session.flush();
                    if updated_se: await session.refresh(updated_se)
            except Exception as e:
                logger.error(f"Error updating StatusEffect def {status_effect_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:error_generic_update",lang_code,"Error updating def {id}: {err}") # type: ignore
                await interaction.followup.send(error_msg.format(id=status_effect_id, err=str(e)), ephemeral=True); return

            if not updated_se:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:error_unknown_update_fail",lang_code,"Definition update failed.") # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:success",lang_code,"StatusEffect def ID {id} updated. Field '{f}' set to '{v}'.") # type: ignore
            new_val_display = str(parsed_value.name if isinstance(parsed_value, StatusEffectCategoryEnum) else parsed_value)
            if isinstance(parsed_value, dict): new_val_display = json.dumps(parsed_value) # type: ignore
            await interaction.followup.send(success_msg.format(id=updated_se.id, f=command_field_name, v=new_val_display), ephemeral=True)

    @status_effect_master_cmds.command(name="definition_delete", description="Delete a Status Effect definition.")
    @app_commands.describe(status_effect_id="ID of the StatusEffect definition to delete.")
    async def status_effect_def_delete(self, interaction: discord.Interaction, status_effect_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            se_def_to_delete = await status_effect_crud.get_by_id(session, id=status_effect_id, guild_id=interaction.guild_id)
            target_guild_id_for_delete = interaction.guild_id
            is_global_to_delete = False

            if not se_def_to_delete and interaction.guild_id is not None: # If not found in guild, try global
                global_se_def = await status_effect_crud.get_by_id(session, id=status_effect_id, guild_id=None)
                if global_se_def:
                    se_def_to_delete = global_se_def
                    target_guild_id_for_delete = None
                    is_global_to_delete = True
            elif not se_def_to_delete and interaction.guild_id is None: # If in DM, it must be global
                 se_def_to_delete = await status_effect_crud.get_by_id(session, id=status_effect_id, guild_id=None)
                 target_guild_id_for_delete = None
                 if se_def_to_delete: is_global_to_delete = True


            if not se_def_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_delete:error_not_found",lang_code,"StatusEffect def ID {id} not found.") # type: ignore
                await interaction.followup.send(error_msg.format(id=status_effect_id), ephemeral=True); return

            se_name_for_msg = se_def_to_delete.name_i18n.get(lang_code, se_def_to_delete.name_i18n.get("en", f"SE Def {status_effect_id}"))
            scope_for_msg = "Global" if is_global_to_delete else f"Guild {se_def_to_delete.guild_id}"
            active_check_filters = [active_status_effect_crud.model.status_effect_id == status_effect_id]
            # Check active instances in the correct scope
            if target_guild_id_for_delete is not None:
                 active_check_filters.append(active_status_effect_crud.model.guild_id == target_guild_id_for_delete)
            # If it's a global definition being deleted, we should check for active instances across ALL guilds.
            # This might be too broad or slow. For now, we only check current guild if guild_id is present,
            # or no guild filter if deleting a global effect (meaning it checks all active effects for this def_id).
            # A more precise check for global would be complex.

            active_dependency_stmt = select(active_status_effect_crud.model.id).where(and_(*active_check_filters)).limit(1)
            active_dependency_exists = (await session.execute(active_dependency_stmt)).scalar_one_or_none()

            if active_dependency_exists:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_delete:error_active_dependency",lang_code,"Cannot delete StatusEffect def '{name}' (ID: {id}, Scope: {scope}) as it is currently active. Remove active instances first.") # type: ignore
                await interaction.followup.send(error_msg.format(name=se_name_for_msg, id=status_effect_id, scope=scope_for_msg), ephemeral=True); return

            deleted_se_def: Optional[Any] = None
            try:
                async with session.begin():
                    # Pass the correct guild_id for removal (None for global)
                    deleted_se_def = await status_effect_crud.remove_by_id(session, id=status_effect_id, guild_id=target_guild_id_for_delete) # type: ignore
                if deleted_se_def:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_delete:success",lang_code,"StatusEffect def '{name}' (ID: {id}, Scope: {scope}) deleted.") # type: ignore
                    await interaction.followup.send(success_msg.format(name=se_name_for_msg, id=status_effect_id, scope=scope_for_msg), ephemeral=True)
                else: # Should ideally not happen if found before
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_delete:error_unknown_delete_fail",lang_code,"StatusEffect def (ID: {id}) found but not deleted.") # type: ignore
                    await interaction.followup.send(error_msg.format(id=status_effect_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting StatusEffect def {status_effect_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_delete:error_generic_delete",lang_code,"Error deleting StatusEffect def '{name}' (ID: {id}): {err}") # type: ignore
                await interaction.followup.send(error_msg.format(name=se_name_for_msg, id=status_effect_id, err=str(e)), ephemeral=True)

    # --- ActiveStatusEffect (Instances) Subcommands ---
    @status_effect_master_cmds.command(name="active_view", description="View details of an active Status Effect instance.")
    @app_commands.describe(active_status_effect_id="The database ID of the ActiveStatusEffect instance.")
    async def active_status_effect_view(self, interaction: discord.Interaction, active_status_effect_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command can only be used in a guild.", ephemeral=True)
            return
        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            active_se = await active_status_effect_crud.get_by_id(session, id=active_status_effect_id, guild_id=interaction.guild_id) # type: ignore
            if not active_se:
                not_found_msg = await get_localized_message_template(session, interaction.guild_id, "active_se_view:not_found", lang_code, "ActiveStatusEffect with ID {id} not found.")
                await interaction.followup.send(not_found_msg.format(id=active_status_effect_id), ephemeral=True); return

            se_def_name = "Unknown Definition"
            # Try to get the definition from the same guild, then global if not found
            se_definition = await status_effect_crud.get_by_id(session, id=active_se.status_effect_id, guild_id=active_se.guild_id)
            if not se_definition:
                 se_definition = await status_effect_crud.get_by_id(session, id=active_se.status_effect_id, guild_id=None)

            if se_definition: se_def_name = se_definition.name_i18n.get(lang_code, se_definition.name_i18n.get("en", f"Def ID {active_se.status_effect_id}"))

            title_template = await get_localized_message_template(session, interaction.guild_id, "active_se_view:title", lang_code, "Active Status Effect: {name} (Instance ID: {id})")
            embed = discord.Embed(title=title_template.format(name=se_def_name, id=active_se.id), color=discord.Color.lighter_grey())
            async def get_label(key: str, default: str) -> str: return await get_localized_message_template(session, interaction.guild_id, f"active_se_view:label_{key}", lang_code, default) # type: ignore
            async def format_json_field(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available") # type: ignore
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON") # type: ignore

            embed.add_field(name=await get_label("guild", "Guild ID"), value=str(active_se.guild_id), inline=True)
            embed.add_field(name=await get_label("def_id", "Definition ID"), value=str(active_se.status_effect_id), inline=True)
            embed.add_field(name=await get_label("entity_type", "Entity Type"), value=active_se.entity_type.value if active_se.entity_type else "N/A", inline=True)
            embed.add_field(name=await get_label("entity_id", "Entity ID"), value=str(active_se.entity_id), inline=True)
            embed.add_field(name=await get_label("duration", "Duration (Turns)"), value=str(active_se.duration_turns) if active_se.duration_turns is not None else "Infinite", inline=True)
            embed.add_field(name=await get_label("remaining", "Remaining (Turns)"), value=str(active_se.remaining_turns) if active_se.remaining_turns is not None else "Infinite", inline=True)
            source_entity_type_val = active_se.source_entity_type.value if active_se.source_entity_type else "N/A"
            source_entity_id_val = str(active_se.source_entity_id) if active_se.source_entity_id is not None else "N/A"
            embed.add_field(name=await get_label("source_entity", "Source Entity"), value=f"{source_entity_type_val}({source_entity_id_val})", inline=True)
            embed.add_field(name=await get_label("source_ability_id", "Source Ability ID"), value=str(active_se.source_ability_id) if active_se.source_ability_id else "N/A", inline=True)
            embed.add_field(name=await get_label("source_log_id", "Source Log ID"), value=str(active_se.source_log_id) if active_se.source_log_id else "N/A", inline=True)
            applied_at_val = discord.utils.format_dt(active_se.applied_at, style='F') if active_se.applied_at else "N/A"
            embed.add_field(name=await get_label("applied_at", "Applied At"), value=applied_at_val, inline=False)
            props_str = await format_json_field(active_se.instance_properties_json, "active_se_view:value_na_json", "active_se_view:error_serialization_props")
            embed.add_field(name=await get_label("instance_props", "Instance Properties JSON"), value=f"```json\n{props_str[:1000]}\n```" + ("..." if len(props_str) > 1000 else ""), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @status_effect_master_cmds.command(name="active_list", description="List active Status Effect instances.")
    @app_commands.describe(entity_id="Optional: Filter by ID of the entity bearing the status.", entity_type="Optional: Filter by type of the entity (PLAYER, GENERATED_NPC). Requires entity_id.", status_effect_def_id="Optional: Filter by the base StatusEffect definition ID.", page="Page number.", limit="Instances per page.")
    async def active_status_effect_list(self, interaction: discord.Interaction, entity_id: Optional[int] = None, entity_type: Optional[str] = None, status_effect_def_id: Optional[int] = None, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 5: limit = 5
        lang_code = str(interaction.locale); entity_type_enum: Optional[RelationshipEntityType] = None

        if interaction.guild_id is None:
            await interaction.followup.send("This command can only be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            if entity_type:
                try: entity_type_enum = RelationshipEntityType[entity_type.upper()]
                except KeyError:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_list:error_invalid_entity_type",lang_code,"Invalid entity_type.")
                    await interaction.followup.send(error_msg, ephemeral=True); return
            if entity_id is not None and entity_type_enum is None: # entity_type is required if entity_id is given
                error_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_list:error_entity_id_no_type",lang_code,"If entity_id provided, entity_type is required.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            filters = [active_status_effect_crud.model.guild_id == interaction.guild_id]
            if entity_id is not None and entity_type_enum: filters.append(active_status_effect_crud.model.entity_id == entity_id); filters.append(active_status_effect_crud.model.entity_type == entity_type_enum)
            if status_effect_def_id is not None: filters.append(active_status_effect_crud.model.status_effect_id == status_effect_def_id)
            offset = (page - 1) * limit
            query = select(active_status_effect_crud.model).where(and_(*filters)).offset(offset).limit(limit).order_by(active_status_effect_crud.model.id.desc())
            result = await session.execute(query)
            active_ses = result.scalars().all()
            count_query = select(func.count(active_status_effect_crud.model.id)).where(and_(*filters))
            total_active_ses_res = await session.execute(count_query)
            total_active_ses = total_active_ses_res.scalar_one_or_none() or 0

            filter_parts = []
            if entity_id is not None and entity_type_enum: filter_parts.append(f"Entity: {entity_type_enum.name}({entity_id})")
            if status_effect_def_id is not None: filter_parts.append(f"Def ID: {status_effect_def_id}")
            filter_display = ", ".join(filter_parts) if filter_parts else "All"

            if not active_ses:
                no_ases_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_list:no_ases_found",lang_code,"No Active StatusEffects for {filter} (Page {p}).")
                await interaction.followup.send(no_ases_msg.format(filter=filter_display, p=page), ephemeral=True); return

            title_tmpl = await get_localized_message_template(session,interaction.guild_id,"active_se_list:title",lang_code,"Active StatusEffect List ({filter} - Page {p} of {tp})")
            total_pages = ((total_active_ses - 1) // limit) + 1
            embed = discord.Embed(title=title_tmpl.format(filter=filter_display, p=page, tp=total_pages), color=discord.Color.dark_gray())
            footer_tmpl = await get_localized_message_template(session,interaction.guild_id,"active_se_list:footer",lang_code,"Displaying {c} of {t} total active effects.")
            embed.set_footer(text=footer_tmpl.format(c=len(active_ses), t=total_active_ses))
            def_ids = list(set(ase.status_effect_id for ase in active_ses)); def_names = {}
            if def_ids:
                # Fetch definitions considering they might be global or guild-specific
                defs_query = select(status_effect_crud.model).where(status_effect_crud.model.id.in_(def_ids))
                defs_result = await session.execute(defs_query)
                defs = defs_result.scalars().all()
                for d in defs: def_names[d.id] = d.name_i18n.get(lang_code, d.name_i18n.get("en", f"Def {d.id}"))

            name_tmpl = await get_localized_message_template(session,interaction.guild_id,"active_se_list:ase_name_field",lang_code,"ID: {id} | {def_name} (Def ID: {def_id})")
            val_tmpl = await get_localized_message_template(session,interaction.guild_id,"active_se_list:ase_value_field",lang_code,"On: {e_type}({e_id}), Turns Left: {turns}")
            for ase in active_ses:
                def_name = def_names.get(ase.status_effect_id, "Unknown Def")
                turns_left = str(ase.remaining_turns) if ase.remaining_turns is not None else "Infinite"
                embed.add_field(name=name_tmpl.format(id=ase.id, def_name=def_name, def_id=ase.status_effect_id), value=val_tmpl.format(e_type=ase.entity_type.name if ase.entity_type else "N/A", e_id=ase.entity_id, turns=turns_left), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @status_effect_master_cmds.command(name="active_remove", description="Remove an active Status Effect instance from an entity.")
    @app_commands.describe(active_status_effect_id="The database ID of the ActiveStatusEffect instance to remove.")
    async def active_status_effect_remove(self, interaction: discord.Interaction, active_status_effect_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            await interaction.followup.send("This command can only be used in a guild.", ephemeral=True)
            return
        async with get_db_session() as session:
            # Ensure we only try to remove an effect from the current guild
            active_se_to_delete = await active_status_effect_crud.get_by_id(session, id=active_status_effect_id, guild_id=interaction.guild_id) # type: ignore
            if not active_se_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_remove:error_not_found",lang_code,"ActiveStatusEffect ID {id} not found in this guild.")
                await interaction.followup.send(error_msg.format(id=active_status_effect_id), ephemeral=True); return

            entity_id_for_msg = active_se_to_delete.entity_id
            entity_type_for_msg = active_se_to_delete.entity_type.name if active_se_to_delete.entity_type else "Unknown"
            status_effect_id_for_msg = active_se_to_delete.status_effect_id
            deleted_ase: Optional[Any] = None
            try:
                async with session.begin():
                    # Pass guild_id to ensure we only remove from the correct guild context
                    deleted_ase = await active_status_effect_crud.remove_by_id(session, id=active_status_effect_id, guild_id=interaction.guild_id) # type: ignore
                if deleted_ase:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_remove:success",lang_code,"ActiveStatusEffect ID {id} (Def ID: {def_id}) removed from Entity {e_type}({e_id}).")
                    await interaction.followup.send(success_msg.format(id=active_status_effect_id, def_id=status_effect_id_for_msg, e_type=entity_type_for_msg, e_id=entity_id_for_msg), ephemeral=True)
                else: # Should not happen if found before
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_remove:error_unknown_delete_fail",lang_code,"ActiveStatusEffect (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=active_status_effect_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error removing ActiveStatusEffect {active_status_effect_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_remove:error_generic_delete",lang_code,"Error removing ActiveStatusEffect ID {id}: {err}")
                await interaction.followup.send(error_msg.format(id=active_status_effect_id, err=str(e)), ephemeral=True)

async def setup(bot: commands.Bot):
    cog = MasterStatusEffectCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterStatusEffectCog loaded.")
