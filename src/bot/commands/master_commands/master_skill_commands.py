import logging
import json
from typing import Dict, Any, Optional, List

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, and_, or_

from src.core.crud.crud_skill import skill_crud
from src.core.database import get_db_session
from src.core.crud_base_definitions import update_entity
from src.core.localization_utils import get_localized_message_template
from src.bot.utils import parse_json_parameter # Import the utility

logger = logging.getLogger(__name__)

class MasterSkillCog(commands.Cog, name="Master Skill Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterSkillCog initialized.")

    skill_master_cmds = app_commands.Group(
        name="master_skill",
        description="Master commands for managing Skills.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    async def _format_json_field_helper(self, interaction: discord.Interaction, data: Optional[Dict[Any, Any]], lang_code: str, default_na_key: str, error_key: str) -> str:
        async with get_db_session() as session:
            na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available") # type: ignore
            if not data: return na_str
            try: return json.dumps(data, indent=2, ensure_ascii=False)
            except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON") # type: ignore

    @skill_master_cmds.command(name="view", description="View details of a specific Skill.")
    @app_commands.describe(skill_id="The database ID of the Skill to view.")
    async def skill_view(self, interaction: discord.Interaction, skill_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        current_guild_id_for_context = interaction.guild_id

        if current_guild_id_for_context is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, current_guild_id_for_context, "common:error_guild_only_command", lang_code, "This command must be used in a server.") # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        # lang_code is already defined
        async with get_db_session() as session:
            skill = await skill_crud.get(session, id=skill_id) # Get by primary ID

            if not skill or (skill.guild_id is not None and skill.guild_id != current_guild_id_for_context):
                not_found_msg = await get_localized_message_template(session, current_guild_id_for_context, "skill_view:not_found", lang_code, "Skill with ID {id} not found.") # type: ignore
                await interaction.followup.send(not_found_msg.format(id=skill_id), ephemeral=True); return

            title_template = await get_localized_message_template(session, current_guild_id_for_context, "skill_view:title", lang_code, "Skill: {name} (ID: {id})") # type: ignore
            skill_name_display = skill.name_i18n.get(lang_code, skill.name_i18n.get("en", f"Skill {skill.id}"))
            embed_title = title_template.format(name=skill_name_display, id=skill.id)
            embed_color = discord.Color.dark_blue() if skill.guild_id else discord.Color.dark_grey() # Distinguish guild vs global
            embed = discord.Embed(title=embed_title, color=embed_color)

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, current_guild_id_for_context, f"skill_view:label_{key}", lang_code, default) # type: ignore

            scope_global_str = await get_localized_message_template(session, current_guild_id_for_context, "common:scope_global", lang_code, "Global") # type: ignore
            scope_guild_tmpl = await get_localized_message_template(session, current_guild_id_for_context, "common:scope_guild", lang_code, "Guild ({guild_id})") # type: ignore
            scope_display = scope_global_str if skill.guild_id is None else scope_guild_tmpl.format(guild_id=skill.guild_id)

            embed.add_field(name=await get_label("scope", "Scope"), value=scope_display, inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=skill.static_id, inline=True)

            name_i18n_str = await self._format_json_field_helper(interaction, skill.name_i18n, lang_code, "skill_view:value_na", "skill_view:error_json")
            embed.add_field(name=await get_label("name_i18n", "Name (i18n)"), value=f"```json\n{name_i18n_str[:1000]}\n```", inline=False)
            desc_i18n_str = await self._format_json_field_helper(interaction, skill.description_i18n, lang_code, "skill_view:value_na", "skill_view:error_json")
            embed.add_field(name=await get_label("desc_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```", inline=False)
            related_attr_str = await self._format_json_field_helper(interaction, skill.related_attribute_i18n, lang_code, "skill_view:value_na", "skill_view:error_json")
            embed.add_field(name=await get_label("related_attr", "Related Attribute (i18n)"), value=f"```json\n{related_attr_str[:1000]}\n```", inline=False)
            properties_str = await self._format_json_field_helper(interaction, skill.properties_json, lang_code, "skill_view:value_na", "skill_view:error_json")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{properties_str[:1000]}\n```", inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @skill_master_cmds.command(name="list", description="List Skills.")
    @app_commands.describe(scope="Filter by scope ('guild', 'global', 'all'). Defaults to 'all'.", page="Page number.", limit="Skills per page.")
    @app_commands.choices(scope=[app_commands.Choice(name="All (Guild & Global)", value="all"), app_commands.Choice(name="Guild-Specific", value="guild"), app_commands.Choice(name="Global Only", value="global"),])
    async def skill_list(self, interaction: discord.Interaction, scope: Optional[app_commands.Choice[str]] = None, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10
        lang_code = str(interaction.locale)

        current_guild_id_for_context = interaction.guild_id
        if scope and scope.value == "guild" and current_guild_id_for_context is None:
            async with get_db_session() as temp_session: # Session for localization
                error_msg = await get_localized_message_template(temp_session, current_guild_id_for_context, "common:error_guild_only_command", lang_code, "Guild-specific scope requires this command to be used in a server.") # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            scope_value = scope.value if scope else "all"
            # Determine effective guild_id for query based on scope
            query_guild_id: Optional[int] = None
            if scope_value == "guild":
                query_guild_id = current_guild_id_for_context
            elif scope_value == "all" and current_guild_id_for_context is not None:
                query_guild_id = current_guild_id_for_context # Means guild + global
            # If scope is "global", query_guild_id remains None (fetches only global)
            # If scope is "all" from DM, query_guild_id remains None (fetches only global)

            skills = await skill_crud.get_multi_by_guild_or_global(session, guild_id=query_guild_id, skip=(page-1)*limit, limit=limit)
            total_skills = await skill_crud.get_all_for_guild_or_global_count(session, guild_id=query_guild_id)

            scope_display_key = f"skill_list:scope_{scope_value}"; scope_display_default = scope_value.capitalize()
            scope_display = await get_localized_message_template(session, current_guild_id_for_context, scope_display_key, lang_code, scope_display_default) # type: ignore

            if not skills:
                no_skills_msg = await get_localized_message_template(session,current_guild_id_for_context,"skill_list:no_skills_found",lang_code,"No Skills for scope '{sc}' (Page {p}).") # type: ignore
                await interaction.followup.send(no_skills_msg.format(sc=scope_display, p=page), ephemeral=True); return

            title_tmpl = await get_localized_message_template(session,current_guild_id_for_context,"skill_list:title",lang_code,"Skill List ({scope} - Page {p} of {tp})") # type: ignore
            total_pages = ((total_skills - 1) // limit) + 1
            embed = discord.Embed(title=title_tmpl.format(scope=scope_display, p=page, tp=total_pages), color=discord.Color.purple())
            footer_tmpl = await get_localized_message_template(session,current_guild_id_for_context,"skill_list:footer",lang_code,"Displaying {c} of {t} total Skills.") # type: ignore
            embed.set_footer(text=footer_tmpl.format(c=len(skills), t=total_skills))
            name_tmpl = await get_localized_message_template(session,current_guild_id_for_context,"skill_list:skill_name_field",lang_code,"ID: {id} | {name} (Static: {sid})") # type: ignore
            val_tmpl = await get_localized_message_template(session,current_guild_id_for_context,"skill_list:skill_value_field",lang_code,"Scope: {scope_val}") # type: ignore

            for sk in skills:
                na_value_str = await get_localized_message_template(session, current_guild_id_for_context, "common:value_na", lang_code, "N/A") # type: ignore
                sk_name = sk.name_i18n.get(lang_code, sk.name_i18n.get("en", na_value_str))

                scope_global_str = await get_localized_message_template(session, current_guild_id_for_context, "common:scope_global", lang_code, "Global") # type: ignore
                scope_guild_tmpl = await get_localized_message_template(session, current_guild_id_for_context, "common:scope_guild", lang_code, "Guild ({guild_id})") # type: ignore
                scope_val_disp = scope_global_str if sk.guild_id is None else scope_guild_tmpl.format(guild_id=sk.guild_id)

                embed.add_field(name=name_tmpl.format(id=sk.id, name=sk_name, sid=sk.static_id or na_value_str), value=val_tmpl.format(scope_val=scope_val_disp), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @skill_master_cmds.command(name="create", description="Create a new Skill.")
    @app_commands.describe(
        static_id="Static ID for this skill (unique for its scope: global or guild).",
        name_i18n_json="JSON for skill name (e.g., {\"en\": \"Swordsmanship\"}).",
        description_i18n_json="JSON for skill description.",
        related_attribute_i18n_json="Optional: JSON for related attribute (e.g., {\"en\": \"Strength\"}).",
        properties_json="Optional: JSON for additional skill properties.",
        is_global="Set to True if this is a global skill. Defaults to False (guild-specific)."
    )
    async def skill_create(self, interaction: discord.Interaction,
                           static_id: str,
                           name_i18n_json: str,
                           description_i18n_json: str,
                           related_attribute_i18n_json: Optional[str] = None,
                           properties_json: Optional[str] = None,
                           is_global: bool = False):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)

        target_guild_id_for_skill: Optional[int] = interaction.guild_id if not is_global else None
        current_guild_id_for_messages: Optional[int] = interaction.guild_id

        if not is_global and current_guild_id_for_messages is None:
            async with get_db_session() as temp_session:
                error_msg_template = await get_localized_message_template(temp_session, current_guild_id_for_messages, "skill_create:error_guild_specific_no_guild", lang_code, "Cannot create a guild-specific skill outside of a guild. Use `is_global=True` or run in a guild.") # type: ignore
            await interaction.followup.send(error_msg_template, ephemeral=True); return

        async with get_db_session() as session:
            parsed_name_i18n = await parse_json_parameter(interaction, name_i18n_json, "name_i18n_json", session)
            if parsed_name_i18n is None: return
            error_detail_name_lang = await get_localized_message_template(session, current_guild_id_for_messages, "skill_create:error_detail_name_lang", lang_code, "name_i18n_json must contain 'en' or current language key.") # type: ignore
            if not parsed_name_i18n.get("en") and not parsed_name_i18n.get(lang_code):
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "skill_create:error_invalid_json_content", lang_code, "Invalid JSON content: {details}") # type: ignore
                await interaction.followup.send(error_msg.format(details=error_detail_name_lang), ephemeral=True); return

            parsed_desc_i18n = await parse_json_parameter(interaction, description_i18n_json, "description_i18n_json", session)
            if parsed_desc_i18n is None: return # description_i18n_json is not optional in command, so if it's None here, it means parsing failed.

            parsed_related_attr = await parse_json_parameter(interaction, related_attribute_i18n_json, "related_attribute_i18n_json", session)
            if parsed_related_attr is None and related_attribute_i18n_json is not None: return

            parsed_props = await parse_json_parameter(interaction, properties_json, "properties_json", session)
            if parsed_props is None and properties_json is not None: return


            existing_skill_static = await skill_crud.get_by_static_id(session, static_id=static_id, guild_id=target_guild_id_for_skill)
            if existing_skill_static:
                scope_global_str = await get_localized_message_template(session, current_guild_id_for_messages, "common:scope_global", lang_code, "global") # type: ignore
                scope_guild_tmpl = await get_localized_message_template(session, current_guild_id_for_messages, "common:scope_guild_detail", lang_code, "guild {guild_id}") # type: ignore
                scope_str = scope_global_str if target_guild_id_for_skill is None else scope_guild_tmpl.format(guild_id=target_guild_id_for_skill)
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "skill_create:error_static_id_exists", lang_code, "Skill static_id '{id}' already exists in scope {sc}.") # type: ignore
                await interaction.followup.send(error_msg.format(id=static_id, sc=scope_str), ephemeral=True); return

            skill_data_create: Dict[str, Any] = {
                "guild_id": target_guild_id_for_skill, "static_id": static_id,
                "name_i18n": parsed_name_i18n, "description_i18n": parsed_desc_i18n, # Now parsed_desc_i18n is not optional if input was not
                "related_attribute_i18n": parsed_related_attr or {},
                "properties_json": parsed_props or {}
            }
            created_skill: Optional[Any] = None
            try:
                async with session.begin():
                    created_skill = await skill_crud.create(session, obj_in=skill_data_create)
                    await session.flush();
                    if created_skill: await session.refresh(created_skill)
            except Exception as e:
                logger.error(f"Error creating Skill: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "skill_create:error_generic_create", lang_code, "Error creating skill: {error}") # type: ignore
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return

            if not created_skill:
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "skill_create:error_unknown_fail", lang_code, "Skill creation failed.") # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title = await get_localized_message_template(session, current_guild_id_for_messages, "skill_create:success_title", lang_code, "Skill Created: {name} (ID: {id})") # type: ignore
            created_name_display = created_skill.name_i18n.get(lang_code, created_skill.name_i18n.get("en", ""))

            scope_global_str = await get_localized_message_template(session, current_guild_id_for_messages, "common:scope_global", lang_code, "Global") # type: ignore
            scope_guild_tmpl = await get_localized_message_template(session, current_guild_id_for_messages, "common:scope_guild", lang_code, "Guild ({guild_id})") # type: ignore
            scope_disp = scope_global_str if created_skill.guild_id is None else scope_guild_tmpl.format(guild_id=created_skill.guild_id)

            embed = discord.Embed(title=success_title.format(name=created_name_display, id=created_skill.id), color=discord.Color.green())

            label_static_id = await get_localized_message_template(session, current_guild_id_for_messages, "skill_create:label_static_id", lang_code, "Static ID") # type: ignore
            label_scope = await get_localized_message_template(session, current_guild_id_for_messages, "skill_create:label_scope", lang_code, "Scope") # type: ignore

            embed.add_field(name=label_static_id, value=created_skill.static_id, inline=True)
            embed.add_field(name=label_scope, value=scope_disp, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @skill_master_cmds.command(name="update", description="Update a specific Skill.")
    @app_commands.describe(
        skill_id="ID of the skill to update.",
        field_to_update="Field to update (e.g., static_id, name_i18n_json, properties_json).",
        new_value="New value for the field (use JSON for complex types)."
    )
    async def skill_update(self, interaction: discord.Interaction, skill_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        current_guild_id_for_messages: Optional[int] = interaction.guild_id
        if not current_guild_id_for_messages:
             await interaction.followup.send("Command must be used in a guild context for updates.", ephemeral=True); return

        allowed_fields = {
            "static_id": str, "name_i18n": dict, "description_i18n": dict,
            "related_attribute_i18n": dict, "properties_json": dict
        }
        field_to_update_lower = field_to_update.lower()
        db_field_name = field_to_update_lower
        user_facing_field_name = field_to_update_lower # For messages from parse_json_parameter

        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json", "") in allowed_fields:
            db_field_name = field_to_update_lower.replace("_json", "")
        # Add other specific mappings if user_facing_field_name differs from db_field_name
        # e.g. if user types "name_json" but db is "name_i18n"
        elif field_to_update_lower == "name_i18n_json":
            db_field_name = "name_i18n"
            user_facing_field_name = "name_i18n_json"
        elif field_to_update_lower == "description_i18n_json":
            db_field_name = "description_i18n"
            user_facing_field_name = "description_i18n_json"
        elif field_to_update_lower == "related_attribute_i18n_json":
            db_field_name = "related_attribute_i18n"
            user_facing_field_name = "related_attribute_i18n_json"
        elif field_to_update_lower == "properties_json": # Already matches
            pass


        field_type_info = allowed_fields.get(db_field_name)
        if not field_type_info:
            async with get_db_session() as temp_session: error_msg = await get_localized_message_template(temp_session, current_guild_id_for_messages, "skill_update:error_field_not_allowed", lang_code, "Field '{f}' not allowed.") # type: ignore
            await interaction.followup.send(error_msg.format(f=field_to_update), ephemeral=True); return

        parsed_value: Any = None
        async with get_db_session() as session:
            skill_to_update = await skill_crud.get(session, id=skill_id)
            if not skill_to_update or (skill_to_update.guild_id is not None and skill_to_update.guild_id != current_guild_id_for_messages):
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "skill_update:error_not_found", lang_code, "Skill ID {id} not found or not accessible.") # type: ignore
                await interaction.followup.send(error_msg.format(id=skill_id), ephemeral=True); return

            original_skill_guild_id_scope = skill_to_update.guild_id

            try:
                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: raise ValueError("static_id cannot be empty.")
                    if parsed_value != skill_to_update.static_id: # Only check if changed
                        existing_skill = await skill_crud.get_by_static_id(session, static_id=parsed_value, guild_id=original_skill_guild_id_scope)
                        if existing_skill and existing_skill.id != skill_id:
                            error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "skill_update:error_static_id_exists", lang_code, "Static ID '{id}' already in use for its scope.") # type: ignore
                            await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                elif field_type_info == dict:
                    parsed_value = await parse_json_parameter(interaction, new_value, user_facing_field_name, session)
                    if parsed_value is None: return
                else: raise ValueError(f"Unsupported type for field {db_field_name}")
            except (ValueError, AssertionError) as e: # Removed json.JSONDecodeError
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "skill_update:error_invalid_value", lang_code, "Invalid value for {f}: {details}") # type: ignore
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            update_data = {db_field_name: parsed_value}
            updated_skill: Optional[Any] = None
            try:
                async with session.begin():
                    updated_skill = await update_entity(session, entity=skill_to_update, data=update_data)
                    await session.flush();
                    if updated_skill: await session.refresh(updated_skill)
            except Exception as e:
                logger.error(f"Error updating Skill {skill_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "skill_update:error_generic_update", lang_code, "Error updating Skill {id}: {err}") # type: ignore
                await interaction.followup.send(error_msg.format(id=skill_id, err=str(e)), ephemeral=True); return

            if not updated_skill:
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "skill_update:error_unknown_fail", lang_code, "Skill update failed.") # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_msg = await get_localized_message_template(session, current_guild_id_for_messages, "skill_update:success", lang_code, "Skill ID {id} updated. Field '{f}' set to '{v}'.") # type: ignore

            new_val_display_str: str
            if parsed_value is None: # Should not happen for current allowed_fields in skill_update, but good practice
                new_val_display_str = await get_localized_message_template(session, current_guild_id_for_messages, "common:value_none", lang_code, "None") # type: ignore
            elif isinstance(parsed_value, dict):
                try:
                    json_str = json.dumps(parsed_value, indent=2, ensure_ascii=False)
                    new_val_display_str = f"```json\n{json_str[:1000]}\n```"
                    if len(json_str) > 1000: new_val_display_str += "..."
                except TypeError:
                    new_val_display_str = await get_localized_message_template(session, current_guild_id_for_messages, "skill_update:error_serialization_new_value", lang_code, "Error displaying new value (non-serializable JSON).") # type: ignore
            else:
                new_val_display_str = str(parsed_value)

            await interaction.followup.send(success_msg.format(id=updated_skill.id, f=field_to_update, v=new_val_display_str), ephemeral=True)

    @skill_master_cmds.command(name="delete", description="Delete a Skill.")
    @app_commands.describe(skill_id="The database ID of the Skill to delete.")
    async def skill_delete(self, interaction: discord.Interaction, skill_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        current_guild_id_for_messages: Optional[int] = interaction.guild_id
        if not current_guild_id_for_messages:
            await interaction.followup.send("Command must be used in a guild context for this operation.", ephemeral=True); return

        async with get_db_session() as session:
            skill_to_delete = await skill_crud.get(session, id=skill_id)
            if not skill_to_delete or (skill_to_delete.guild_id is not None and skill_to_delete.guild_id != current_guild_id_for_messages):
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "skill_delete:error_not_found", lang_code, "Skill ID {id} not found or not accessible.") # type: ignore
                await interaction.followup.send(error_msg.format(id=skill_id), ephemeral=True); return

            skill_name_for_msg = skill_to_delete.name_i18n.get(lang_code, skill_to_delete.name_i18n.get("en", f"Skill {skill_id}"))

            scope_global_str = await get_localized_message_template(session, current_guild_id_for_messages, "common:scope_global", lang_code, "Global") # type: ignore
            scope_guild_tmpl = await get_localized_message_template(session, current_guild_id_for_messages, "common:scope_guild", lang_code, "Guild ({guild_id})") # type: ignore
            scope_for_msg = scope_global_str if skill_to_delete.guild_id is None else scope_guild_tmpl.format(guild_id=skill_to_delete.guild_id)

            # Dependency Check: CraftingRecipe.required_skill_id
            from src.core.crud.crud_crafting_recipe import crud_crafting_recipe # Local import
            stmt = select(crud_crafting_recipe.model.id).where(crud_crafting_recipe.model.required_skill_id == skill_id).limit(1)
            dependency_exists = (await session.execute(stmt)).scalar_one_or_none()
            if dependency_exists:
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "skill_delete:error_recipe_dependency", lang_code, "Cannot delete Skill '{name}' as it's required by one or more crafting recipes.") # type: ignore
                await interaction.followup.send(error_msg.format(name=skill_name_for_msg), ephemeral=True); return

            deleted_skill: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_skill = await skill_crud.delete(session, id=skill_id)
                if deleted_skill:
                    success_msg = await get_localized_message_template(session, current_guild_id_for_messages, "skill_delete:success", lang_code, "Skill '{name}' (ID: {id}, Scope: {scope}) deleted.") # type: ignore
                    await interaction.followup.send(success_msg.format(name=skill_name_for_msg, id=skill_id, scope=scope_for_msg), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "skill_delete:error_unknown_fail", lang_code, "Skill (ID: {id}) found but not deleted.") # type: ignore
                    await interaction.followup.send(error_msg.format(id=skill_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Skill {skill_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, current_guild_id_for_messages, "skill_delete:error_generic_delete", lang_code, "Error deleting Skill '{name}' (ID: {id}): {err}") # type: ignore
                await interaction.followup.send(error_msg.format(name=skill_name_for_msg, id=skill_id, err=str(e)), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(MasterSkillCog(bot))
    logger.info("MasterSkillCog loaded.")
