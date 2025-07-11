import logging
import json
from typing import Dict, Any, Optional, List, cast
from datetime import datetime # For casting active_se.applied_at

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, and_, or_

from backend.core.crud.crud_status_effect import status_effect_crud, active_status_effect_crud
from backend.core.database import get_db_session
from backend.core.crud_base_definitions import update_entity
from backend.core.localization_utils import get_localized_message_template
from backend.bot.utils import parse_json_parameter # Import the utility
from backend.models.enums import StatusEffectCategory as StatusEffectCategoryEnum, RelationshipEntityType

logger = logging.getLogger(__name__)

class MasterStatusEffectCog(commands.Cog, name="Master Status Effect Commands"): # type: ignore[call-arg]
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterStatusEffectCog initialized.")

    status_effect_master_cmds = app_commands.Group(
        name="master_status_effect",
        description="Master commands for managing Status Effects (definitions and active instances).",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    async def _format_json_field_display(self, interaction: discord.Interaction, data: Optional[Dict[Any, Any]], lang_code: str) -> str:
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

    # --- StatusEffect Definition Subcommands ---
    @status_effect_master_cmds.command(name="definition_view", description="View details of a Status Effect definition.")
    @app_commands.describe(status_effect_id="The database ID of the StatusEffect definition to view.")
    async def status_effect_def_view(self, interaction: discord.Interaction, status_effect_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            se_def = await status_effect_crud.get(session, id=status_effect_id, guild_id=interaction.guild_id)
            if not se_def and interaction.guild_id is not None:
                 global_se_def = await status_effect_crud.get(session, id=status_effect_id, guild_id=None)
                 if global_se_def: se_def = global_se_def
            elif not se_def and interaction.guild_id is None:
                 se_def = await status_effect_crud.get(session, id=status_effect_id, guild_id=None)

            if not se_def:
                not_found_msg = await get_localized_message_template(session, interaction.guild_id, "se_def_view:not_found", lang_code, "StatusEffect definition with ID {id} not found.")
                await interaction.followup.send(not_found_msg.format(id=status_effect_id), ephemeral=True); return

            title_template = await get_localized_message_template(session, interaction.guild_id, "se_def_view:title", lang_code, "StatusEffect Definition: {name} (ID: {id})")
            name_display = se_def.name_i18n.get(lang_code, se_def.name_i18n.get("en", f"StatusEffect {se_def.id}"))
            embed_title = title_template.format(name=name_display, id=se_def.id)
            embed_color = discord.Color.dark_green() if se_def.guild_id else discord.Color.dark_grey()
            embed = discord.Embed(title=embed_title, color=embed_color)

            async def get_label(key: str, default: str) -> str: return await get_localized_message_template(session, interaction.guild_id, f"se_def_view:label_{key}", lang_code, default)

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(se_def.guild_id) if se_def.guild_id else "Global", inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=se_def.static_id or "N/A", inline=True)
            embed.add_field(name=await get_label("category", "Category"), value=se_def.category.value if se_def.category else "N/A", inline=True)

            name_i18n_str = await self._format_json_field_display(interaction, se_def.name_i18n, lang_code)
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```", inline=False)
            desc_i18n_str = await self._format_json_field_display(interaction, se_def.description_i18n, lang_code)
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```", inline=False)
            props_str = await self._format_json_field_display(interaction, se_def.properties_json, lang_code)
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{props_str[:1000]}\n```", inline=False)
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
        current_guild_id_for_context = interaction.guild_id

        if scope and scope.value == "guild" and current_guild_id_for_context is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, current_guild_id_for_context, "common:error_guild_only_command_for_scope", lang_code, "Guild-specific scope requires this command to be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            filters = []
            scope_value = scope.value if scope else "all"

            if scope_value == "guild":
                if interaction.guild_id is None:
                    await interaction.followup.send("Cannot list guild-specific effects outside of a guild.", ephemeral=True); return
                filters.append(status_effect_crud.model.guild_id == interaction.guild_id)
            elif scope_value == "global":
                filters.append(status_effect_crud.model.guild_id.is_(None))
            else:
                if interaction.guild_id is not None:
                    filters.append(or_(status_effect_crud.model.guild_id == interaction.guild_id, status_effect_crud.model.guild_id.is_(None)))
                else:
                    filters.append(status_effect_crud.model.guild_id.is_(None))

            offset = (page - 1) * limit
            query = select(status_effect_crud.model).where(and_(*filters)).offset(offset).limit(limit).order_by(status_effect_crud.model.id.desc())
            result = await session.execute(query)
            se_defs = result.scalars().all()
            count_query = select(func.count(status_effect_crud.model.id)).where(and_(*filters))
            total_defs_res = await session.execute(count_query)
            total_definitions = total_defs_res.scalar_one_or_none() or 0

            scope_display_key = f"se_def_list:scope_{scope_value}"; scope_display_default = scope_value.capitalize()
            scope_display = await get_localized_message_template(session, interaction.guild_id, scope_display_key, lang_code, scope_display_default)
            if not se_defs:
                no_defs_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_list:no_defs_found",lang_code,"No StatusEffect definitions found for scope '{sc}' (Page {p}).")
                await interaction.followup.send(no_defs_msg.format(sc=scope_display, p=page), ephemeral=True); return

            title_tmpl = await get_localized_message_template(session,interaction.guild_id,"se_def_list:title",lang_code,"StatusEffect Definition List ({scope} - Page {p} of {tp})")
            total_pages = ((total_definitions - 1) // limit) + 1
            embed = discord.Embed(title=title_tmpl.format(scope=scope_display, p=page, tp=total_pages), color=discord.Color.dark_teal())
            footer_tmpl = await get_localized_message_template(session,interaction.guild_id,"se_def_list:footer",lang_code,"Displaying {c} of {t} total definitions.")
            embed.set_footer(text=footer_tmpl.format(c=len(se_defs), t=total_definitions))
            name_tmpl = await get_localized_message_template(session,interaction.guild_id,"se_def_list:def_name_field",lang_code,"ID: {id} | {name} (Static: {sid})")
            val_tmpl = await get_localized_message_template(session,interaction.guild_id,"se_def_list:def_value_field",lang_code,"Category: {cat}, Scope: {scope_val}")
            for se_def in se_defs:
                se_name = se_def.name_i18n.get(lang_code, se_def.name_i18n.get("en", "N/A"))
                scope_val_disp = "Global" if se_def.guild_id is None else f"Guild ({se_def.guild_id})"
                embed.add_field(name=name_tmpl.format(id=se_def.id, name=se_name, sid=se_def.static_id or "N/A"), value=val_tmpl.format(cat=se_def.category.value if se_def.category else "N/A", scope_val=scope_val_disp), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @status_effect_master_cmds.command(name="definition_create", description="Create a new Status Effect definition.")
    @app_commands.describe(static_id="Static ID (unique for its scope: global or guild).", name_i18n_json="JSON for name (e.g., {\"en\": \"Poisoned\", \"ru\": \"Отравлен\"}).", category="Category (BUFF, DEBUFF, NEUTRAL).", description_i18n_json="Optional: JSON for description.", properties_json="Optional: JSON for properties (effects, duration rules, etc.).", is_global="Set to True if this is a global definition. Defaults to False (guild-specific).")
    @app_commands.choices(category=[app_commands.Choice(name="Buff", value="BUFF"), app_commands.Choice(name="Debuff", value="DEBUFF"), app_commands.Choice(name="Neutral", value="NEUTRAL"),])
    async def status_effect_def_create(self, interaction: discord.Interaction, static_id: str, name_i18n_json: str, category: app_commands.Choice[str], description_i18n_json: Optional[str] = None, properties_json: Optional[str] = None, is_global: bool = False):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        target_guild_id: Optional[int] = interaction.guild_id if not is_global else None
        current_guild_id_for_messages: Optional[int] = interaction.guild_id

        if not is_global and current_guild_id_for_messages is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, current_guild_id_for_messages, "common:error_guild_only_command_for_action", lang_code, "Cannot create a guild-specific entry outside of a server. Use `is_global=True` or run in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        effective_guild_id_for_loc = current_guild_id_for_messages if current_guild_id_for_messages is not None else 0

        async with get_db_session() as session:
            parsed_name_i18n = await parse_json_parameter(interaction, name_i18n_json, "name_i18n_json", session)
            if parsed_name_i18n is None: return
            error_detail_name_lang = await get_localized_message_template(session, effective_guild_id_for_loc, "se_def_create:error_detail_name_lang", lang_code, "name_i18n_json must contain 'en' or current language key.")
            if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code):
                error_msg = await get_localized_message_template(session, effective_guild_id_for_loc,"se_def_create:error_invalid_json_content",lang_code,"Invalid JSON content: {details}")
                await interaction.followup.send(error_msg.format(details=error_detail_name_lang), ephemeral=True); return

            parsed_desc_i18n = await parse_json_parameter(interaction, description_i18n_json, "description_i18n_json", session)
            if parsed_desc_i18n is None and description_i18n_json is not None: return

            parsed_props = await parse_json_parameter(interaction, properties_json, "properties_json", session)
            if parsed_props is None and properties_json is not None: return

            existing_se_static = await status_effect_crud.get_by_static_id(session, static_id=static_id, guild_id=target_guild_id)
            if existing_se_static:
                scope_global_str = await get_localized_message_template(session, effective_guild_id_for_loc, "common:scope_global", lang_code, "global")
                scope_guild_tmpl = await get_localized_message_template(session, effective_guild_id_for_loc, "common:scope_guild_detail", lang_code, "guild {guild_id}")
                scope_str = scope_global_str if target_guild_id is None else scope_guild_tmpl.format(guild_id=target_guild_id)
                error_msg = await get_localized_message_template(session,effective_guild_id_for_loc,"se_def_create:error_static_id_exists",lang_code,"StatusEffect static_id '{id}' already exists in scope {sc}.")
                await interaction.followup.send(error_msg.format(id=static_id, sc=scope_str), ephemeral=True); return

            category_enum: StatusEffectCategoryEnum
            try:
                category_enum = StatusEffectCategoryEnum[category.value]
            except KeyError as e:
                error_detail_invalid_category = await get_localized_message_template(session, effective_guild_id_for_loc, "se_def_create:error_detail_invalid_category", lang_code, "Invalid category value: {value}")
                error_msg = await get_localized_message_template(session,effective_guild_id_for_loc,"se_def_create:error_invalid_category_key",lang_code,"Invalid category key: {details}")
                await interaction.followup.send(error_msg.format(details=error_detail_invalid_category.format(value=str(e))), ephemeral=True); return

            se_data_create: Dict[str, Any] = {
                "guild_id": target_guild_id, "static_id": static_id,
                "name_i18n": parsed_name_i18n, # Already validated not None
                "description_i18n": parsed_desc_i18n or {},
                "category": category_enum,
                "properties_json": parsed_props or {}
            }
            created_se: Optional[Any] = None
            try:
                async with session.begin():
                    created_se = await status_effect_crud.create(session, obj_in=se_data_create)
                    await session.flush();
                    if created_se: await session.refresh(created_se)
            except Exception as e:
                logger.error(f"Error creating StatusEffect definition: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,effective_guild_id_for_loc,"se_def_create:error_generic_create",lang_code,"Error creating definition: {error}")
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return
            if not created_se:
                error_msg = await get_localized_message_template(session,effective_guild_id_for_loc,"se_def_create:error_unknown_fail",lang_code,"Definition creation failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title = await get_localized_message_template(session,effective_guild_id_for_loc,"se_def_create:success_title",lang_code,"StatusEffect Definition Created: {name} (ID: {id})")
            created_name = created_se.name_i18n.get(lang_code, created_se.name_i18n.get("en", ""))
            scope_global_str = await get_localized_message_template(session, effective_guild_id_for_loc, "common:scope_global", lang_code, "Global")
            scope_guild_tmpl = await get_localized_message_template(session, effective_guild_id_for_loc, "common:scope_guild", lang_code, "Guild ({guild_id})")
            scope_disp = scope_global_str if created_se.guild_id is None else scope_guild_tmpl.format(guild_id=created_se.guild_id)
            embed = discord.Embed(title=success_title.format(name=created_name, id=created_se.id), color=discord.Color.green())
            label_static_id = await get_localized_message_template(session, effective_guild_id_for_loc, "se_def_create:label_static_id", lang_code, "Static ID")
            label_category = await get_localized_message_template(session, effective_guild_id_for_loc, "se_def_create:label_category", lang_code, "Category")
            label_scope = await get_localized_message_template(session, effective_guild_id_for_loc, "se_def_create:label_scope", lang_code, "Scope")
            embed.add_field(name=label_static_id, value=created_se.static_id, inline=True); embed.add_field(name=label_category, value=created_se.category.value, inline=True); embed.add_field(name=label_scope, value=scope_disp, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @status_effect_master_cmds.command(name="definition_update", description="Update a Status Effect definition.")
    @app_commands.describe(status_effect_id="ID of the StatusEffect definition to update.", field_to_update="Field to update (e.g., static_id, name_i18n_json, category, properties_json).", new_value="New value for the field.")
    @app_commands.choices(field_to_update=[app_commands.Choice(name="Static ID", value="static_id"), app_commands.Choice(name="Name (i18n JSON)", value="name_i18n_json"), app_commands.Choice(name="Description (i18n JSON)", value="description_i18n_json"), app_commands.Choice(name="Category (BUFF/DEBUFF/NEUTRAL)", value="category"), app_commands.Choice(name="Properties (JSON)", value="properties_json"),])
    async def status_effect_def_update(self, interaction: discord.Interaction, status_effect_id: int, field_to_update: app_commands.Choice[str], new_value: str):
        await interaction.response.defer(ephemeral=True)
        allowed_fields_map = {"static_id": {"db_field": "static_id", "type": str}, "name_i18n_json": {"db_field": "name_i18n", "type": dict}, "description_i18n_json": {"db_field": "description_i18n", "type": dict}, "category": {"db_field": "category", "type": StatusEffectCategoryEnum}, "properties_json": {"db_field": "properties_json", "type": dict},}
        lang_code = str(interaction.locale); command_field_name = field_to_update.value

        if command_field_name not in allowed_fields_map:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session,interaction.guild_id,"common:error_invalid_field_choice_internal",lang_code,"Internal error: Invalid field choice selected.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        db_field_name = allowed_fields_map[command_field_name]["db_field"]
        expected_type = allowed_fields_map[command_field_name]["type"]
        parsed_value: Any = None
        user_facing_field_name_for_parse = command_field_name # For parse_json_parameter

        async with get_db_session() as session:
            se_def_to_update = await status_effect_crud.get(session, id=status_effect_id, guild_id=interaction.guild_id)
            original_guild_id_for_check = interaction.guild_id
            if not se_def_to_update and interaction.guild_id is not None:
                global_se_def = await status_effect_crud.get(session, id=status_effect_id, guild_id=None)
                if global_se_def:
                    se_def_to_update = global_se_def
                    original_guild_id_for_check = None
            elif not se_def_to_update and interaction.guild_id is None:
                 se_def_to_update = await status_effect_crud.get(session, id=status_effect_id, guild_id=None)
                 original_guild_id_for_check = None

            if not se_def_to_update:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:error_not_found",lang_code,"StatusEffect def ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=status_effect_id), ephemeral=True); return

            try:
                error_detail_static_id_empty = await get_localized_message_template(session, interaction.guild_id, "se_def_update:error_detail_static_id_empty", lang_code, "static_id cannot be empty.")
                error_detail_invalid_category_template = await get_localized_message_template(session, interaction.guild_id, "se_def_update:error_detail_invalid_category", lang_code, "Invalid category. Use {valid_options}")

                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: raise ValueError(error_detail_static_id_empty)
                    if parsed_value != se_def_to_update.static_id: # Only check if changed
                        existing_se = await status_effect_crud.get_by_static_id(session, static_id=parsed_value, guild_id=original_guild_id_for_check)
                        if existing_se and existing_se.id != status_effect_id:
                            scope_global_str = await get_localized_message_template(session, interaction.guild_id, "common:scope_global", lang_code, "global")
                            scope_guild_tmpl = await get_localized_message_template(session, interaction.guild_id, "common:scope_guild_detail", lang_code, "guild {guild_id}")
                            scope_str = scope_global_str if original_guild_id_for_check is None else scope_guild_tmpl.format(guild_id=original_guild_id_for_check)
                            error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:error_static_id_exists",lang_code,"Static ID '{id}' already in use for scope {sc}.")
                            await interaction.followup.send(error_msg.format(id=parsed_value, sc=scope_str), ephemeral=True); return
                elif expected_type == dict:
                    parsed_value = await parse_json_parameter(interaction, new_value, user_facing_field_name_for_parse, session)
                    if parsed_value is None: return
                elif expected_type == StatusEffectCategoryEnum:
                    try: parsed_value = StatusEffectCategoryEnum[new_value.upper()]
                    except KeyError:
                        valid_categories = ", ".join([c.name for c in StatusEffectCategoryEnum])
                        raise ValueError(error_detail_invalid_category_template.format(valid_options=valid_categories))
                else: parsed_value = new_value
            except ValueError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:error_invalid_value",lang_code,"Invalid value for {f}: {details}")
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
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:error_generic_update",lang_code,"Error updating def {id}: {err}")
                await interaction.followup.send(error_msg.format(id=status_effect_id, err=str(e)), ephemeral=True); return

            if not updated_se:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:error_unknown_update_fail",lang_code,"Definition update failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_update:success",lang_code,"StatusEffect def ID {id} updated. Field '{f}' set to '{v}'.")

            new_val_display_str: str
            if parsed_value is None:
                new_val_display_str = await get_localized_message_template(session, interaction.guild_id, "common:value_none", lang_code, "None")
            elif isinstance(parsed_value, StatusEffectCategoryEnum):
                new_val_display_str = parsed_value.name
            elif isinstance(parsed_value, dict):
                new_val_display_str = await self._format_json_field_display(interaction, parsed_value, lang_code)
            else:
                new_val_display_str = str(parsed_value)

            await interaction.followup.send(success_msg.format(id=updated_se.id, f=command_field_name, v=new_val_display_str), ephemeral=True)

    @status_effect_master_cmds.command(name="definition_delete", description="Delete a Status Effect definition.")
    @app_commands.describe(status_effect_id="ID of the StatusEffect definition to delete.")
    async def status_effect_def_delete(self, interaction: discord.Interaction, status_effect_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)

        async with get_db_session() as session:
            se_def_to_delete = await status_effect_crud.get(session, id=status_effect_id, guild_id=interaction.guild_id)
            target_guild_id_for_delete = interaction.guild_id
            is_global_to_delete = False

            if not se_def_to_delete and interaction.guild_id is not None:
                global_se_def = await status_effect_crud.get(session, id=status_effect_id, guild_id=None)
                if global_se_def:
                    se_def_to_delete = global_se_def
                    target_guild_id_for_delete = None
                    is_global_to_delete = True
            elif not se_def_to_delete and interaction.guild_id is None:
                 se_def_to_delete = await status_effect_crud.get(session, id=status_effect_id, guild_id=None)
                 target_guild_id_for_delete = None
                 if se_def_to_delete: is_global_to_delete = True


            if not se_def_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_delete:error_not_found",lang_code,"StatusEffect def ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=status_effect_id), ephemeral=True); return

            se_name_for_msg = se_def_to_delete.name_i18n.get(lang_code, se_def_to_delete.name_i18n.get("en", f"SE Def {status_effect_id}"))
            scope_global_str = await get_localized_message_template(session, interaction.guild_id, "common:scope_global", lang_code, "Global")
            scope_guild_tmpl = await get_localized_message_template(session, interaction.guild_id, "common:scope_guild", lang_code, "Guild ({guild_id})")
            scope_for_msg = scope_global_str if is_global_to_delete else scope_guild_tmpl.format(guild_id=target_guild_id_for_delete)

            active_check_filters = [active_status_effect_crud.model.status_effect_id == status_effect_id]
            if target_guild_id_for_delete is not None:
                 active_check_filters.append(active_status_effect_crud.model.guild_id == target_guild_id_for_delete)

            active_dependency_stmt = select(active_status_effect_crud.model.id).where(and_(*active_check_filters)).limit(1)
            active_dependency_exists = (await session.execute(active_dependency_stmt)).scalar_one_or_none()

            if active_dependency_exists:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_delete:error_active_dependency",lang_code,"Cannot delete StatusEffect def '{name}' (ID: {id}, Scope: {scope}) as it is currently active. Remove active instances first.")
                await interaction.followup.send(error_msg.format(name=se_name_for_msg, id=status_effect_id, scope=scope_for_msg), ephemeral=True); return

            deleted_se_def: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_se_def = await status_effect_crud.delete(session, id=status_effect_id, guild_id=target_guild_id_for_delete)
                if deleted_se_def:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_delete:success",lang_code,"StatusEffect def '{name}' (ID: {id}, Scope: {scope}) deleted.")
                    await interaction.followup.send(success_msg.format(name=se_name_for_msg, id=status_effect_id, scope=scope_for_msg), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_delete:error_unknown_delete_fail",lang_code,"StatusEffect def (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=status_effect_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting StatusEffect def {status_effect_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"se_def_delete:error_generic_delete",lang_code,"Error deleting StatusEffect def '{name}' (ID: {id}): {err}")
                await interaction.followup.send(error_msg.format(name=se_name_for_msg, id=status_effect_id, err=str(e)), ephemeral=True)

    # --- ActiveStatusEffect (Instances) Subcommands ---
    @status_effect_master_cmds.command(name="active_view", description="View details of an active Status Effect instance.")
    @app_commands.describe(active_status_effect_id="The database ID of the ActiveStatusEffect instance.")
    async def active_status_effect_view(self, interaction: discord.Interaction, active_status_effect_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            active_se = await active_status_effect_crud.get(session, id=active_status_effect_id, guild_id=interaction.guild_id)
            if not active_se:
                not_found_msg = await get_localized_message_template(session, interaction.guild_id, "active_se_view:not_found", lang_code, "ActiveStatusEffect with ID {id} not found.")
                await interaction.followup.send(not_found_msg.format(id=active_status_effect_id), ephemeral=True); return

            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")
            infinite_str = await get_localized_message_template(session, interaction.guild_id, "common:value_infinite", lang_code, "Infinite")
            unknown_def_str = await get_localized_message_template(session, interaction.guild_id, "active_se_view:unknown_definition", lang_code, "Unknown Definition")

            se_def_name = unknown_def_str
            se_definition = await status_effect_crud.get(session, id=active_se.status_effect_id, guild_id=active_se.guild_id)
            if not se_definition:
                 se_definition = await status_effect_crud.get(session, id=active_se.status_effect_id, guild_id=None)
            if se_definition: se_def_name = se_definition.name_i18n.get(lang_code, se_definition.name_i18n.get("en", f"Def ID {active_se.status_effect_id}"))

            title_template = await get_localized_message_template(session, interaction.guild_id, "active_se_view:title", lang_code, "Active Status Effect: {name} (Instance ID: {id})")
            embed = discord.Embed(title=title_template.format(name=se_def_name, id=active_se.id), color=discord.Color.lighter_grey())
            async def get_label(key: str, default: str) -> str: return await get_localized_message_template(session, interaction.guild_id, f"active_se_view:label_{key}", lang_code, default)

            embed.add_field(name=await get_label("guild", "Guild ID"), value=str(active_se.guild_id), inline=True)
            embed.add_field(name=await get_label("def_id", "Definition ID"), value=str(active_se.status_effect_id), inline=True)
            embed.add_field(name=await get_label("entity_type", "Entity Type"), value=active_se.entity_type if active_se.entity_type else na_value_str, inline=True)
            embed.add_field(name=await get_label("entity_id", "Entity ID"), value=str(active_se.entity_id), inline=True)
            embed.add_field(name=await get_label("duration", "Duration (Turns)"), value=str(active_se.duration_turns) if active_se.duration_turns is not None else infinite_str, inline=True)
            embed.add_field(name=await get_label("remaining", "Remaining (Turns)"), value=str(active_se.remaining_turns) if active_se.remaining_turns is not None else infinite_str, inline=True)
            source_entity_type_val = active_se.source_entity_type if active_se.source_entity_type else na_value_str
            source_entity_id_val = str(active_se.source_entity_id) if active_se.source_entity_id is not None else na_value_str
            embed.add_field(name=await get_label("source_entity", "Source Entity"), value=f"{source_entity_type_val}({source_entity_id_val})", inline=True)
            embed.add_field(name=await get_label("source_ability_id", "Source Ability ID"), value=str(active_se.source_ability_id) if active_se.source_ability_id else na_value_str, inline=True)
            applied_at_val = discord.utils.format_dt(cast(datetime, active_se.applied_at), style='F') if active_se.applied_at else na_value_str
            embed.add_field(name=await get_label("applied_at", "Applied At"), value=applied_at_val, inline=False)
            props_str = await self._format_json_field_display(interaction, active_se.custom_properties_json, lang_code)
            embed.add_field(name=await get_label("instance_props", "Instance Properties JSON"), value=f"```json\n{props_str[:1000]}\n```", inline=False)
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
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            if entity_type:
                try: entity_type_enum = RelationshipEntityType[entity_type.upper()]
                except KeyError:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_list:error_invalid_entity_type",lang_code,"Invalid entity_type.")
                    await interaction.followup.send(error_msg, ephemeral=True); return
            if entity_id is not None and entity_type_enum is None:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_list:error_entity_id_no_type",lang_code,"If entity_id provided, entity_type is required.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            filters = [active_status_effect_crud.model.guild_id == interaction.guild_id]
            if entity_id is not None and entity_type_enum: filters.append(active_status_effect_crud.model.entity_id == entity_id); filters.append(active_status_effect_crud.model.entity_type == entity_type_enum)
            if status_effect_def_id is not None: filters.append(active_status_effect_crud.model.status_effect_id == status_effect_def_id)
            offset = (page - 1) * limit
            query = select(active_status_effect_crud.model).where(and_(*filters)).offset(offset).limit(limit).order_by(active_status_effect_crud.model.id.desc())
            result = await session.execute(query)
            active_ses = result.scalars().all()
            total_active_ses = await active_status_effect_crud.get_count_for_filters(session, guild_id=interaction.guild_id, entity_id=entity_id, entity_type=entity_type_enum, status_effect_id=status_effect_def_id) # type: ignore

            filter_parts = []
            entity_filter_label = await get_localized_message_template(session, interaction.guild_id, "active_se_list:filter_entity", lang_code, "Entity")
            def_id_filter_label = await get_localized_message_template(session, interaction.guild_id, "active_se_list:filter_def_id", lang_code, "Def ID")
            all_filter_str = await get_localized_message_template(session, interaction.guild_id, "common:filter_all", lang_code, "All")

            if entity_id is not None and entity_type_enum: filter_parts.append(f"{entity_filter_label}: {entity_type_enum.name}({entity_id})")
            if status_effect_def_id is not None: filter_parts.append(f"{def_id_filter_label}: {status_effect_def_id}")
            filter_display = ", ".join(filter_parts) if filter_parts else all_filter_str

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
                defs_query = select(status_effect_crud.model).where(status_effect_crud.model.id.in_(def_ids))
                defs_result = await session.execute(defs_query)
                defs = defs_result.scalars().all()
                for d in defs: def_names[d.id] = d.name_i18n.get(lang_code, d.name_i18n.get("en", f"Def {d.id}"))

            name_tmpl = await get_localized_message_template(session,interaction.guild_id,"active_se_list:ase_name_field",lang_code,"ID: {id} | {def_name} (Def ID: {def_id})")
            val_tmpl = await get_localized_message_template(session,interaction.guild_id,"active_se_list:ase_value_field",lang_code,"On: {e_type}({e_id}), Turns Left: {turns}")
            for ase in active_ses:
                na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")
                infinite_str = await get_localized_message_template(session, interaction.guild_id, "common:value_infinite", lang_code, "Infinite")
                unknown_def_str = await get_localized_message_template(session, interaction.guild_id, "active_se_list:unknown_definition", lang_code, "Unknown Def")

                def_name = def_names.get(ase.status_effect_id, unknown_def_str)
                turns_left = str(ase.remaining_turns) if ase.remaining_turns is not None else infinite_str
                embed.add_field(name=name_tmpl.format(id=ase.id, def_name=def_name, def_id=ase.status_effect_id), value=val_tmpl.format(e_type=ase.entity_type if ase.entity_type else na_value_str, e_id=ase.entity_id, turns=turns_left), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @status_effect_master_cmds.command(name="active_remove", description="Remove an active Status Effect instance from an entity.")
    @app_commands.describe(active_status_effect_id="The database ID of the ActiveStatusEffect instance to remove.")
    async def active_status_effect_remove(self, interaction: discord.Interaction, active_status_effect_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            active_se_to_delete = await active_status_effect_crud.get(session, id=active_status_effect_id, guild_id=interaction.guild_id)
            if not active_se_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_remove:error_not_found",lang_code,"ActiveStatusEffect ID {id} not found in this guild.")
                await interaction.followup.send(error_msg.format(id=active_status_effect_id), ephemeral=True); return

            entity_id_for_msg = active_se_to_delete.entity_id
            entity_type_for_msg = active_se_to_delete.entity_type if active_se_to_delete.entity_type else "Unknown"
            status_effect_id_for_msg = active_se_to_delete.status_effect_id
            deleted_ase: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_ase = await active_status_effect_crud.delete(session, id=active_status_effect_id, guild_id=interaction.guild_id)
                if deleted_ase:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"active_se_remove:success",lang_code,"ActiveStatusEffect ID {id} (Def ID: {def_id}) removed from Entity {e_type}({e_id}).")
                    await interaction.followup.send(success_msg.format(id=active_status_effect_id, def_id=status_effect_id_for_msg, e_type=entity_type_for_msg, e_id=entity_id_for_msg), ephemeral=True)
                else:
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
