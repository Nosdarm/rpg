import logging
import json
from typing import Dict, Any, Optional, List

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, and_

from src.core.crud.crud_quest import questline_crud, generated_quest_crud, quest_step_crud, player_quest_progress_crud
from src.core.database import get_db_session
from src.core.crud_base_definitions import update_entity
from src.core.localization_utils import get_localized_message_template
from src.models.quest import QuestStep as QStepModel, PlayerQuestProgress as PQPModel # For bulk delete

logger = logging.getLogger(__name__)

class MasterQuestCog(commands.Cog, name="Master Quest Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterQuestCog initialized.")

    quest_master_cmds = app_commands.Group(
        name="master_quest",
        description="Master commands for managing Quests and Questlines.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    # --- Questline Subcommands ---
    @quest_master_cmds.command(name="questline_view", description="View details of a specific Questline.")
    @app_commands.describe(questline_id="The database ID of the Questline to view.")
    async def questline_view(self, interaction: discord.Interaction, questline_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command can only be used in a guild.", ephemeral=True)
            return
        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            q_line = await questline_crud.get_by_id(session, id=questline_id, guild_id=interaction.guild_id)

            if not q_line:
                not_found_msg = await get_localized_message_template(session, interaction.guild_id, "questline_view:not_found", lang_code, "Questline with ID {id} not found in this guild.")
                await interaction.followup.send(not_found_msg.format(id=questline_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(session, interaction.guild_id, "questline_view:title", lang_code, "Questline Details: {ql_title} (ID: {ql_id})")
            ql_title_display = q_line.title_i18n.get(lang_code, q_line.title_i18n.get("en", f"Questline {q_line.id}"))
            embed_title = title_template.format(ql_title=ql_title_display, ql_id=q_line.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_teal())

            async def get_label(key: str, default: str) -> str: return await get_localized_message_template(session, interaction.guild_id, f"questline_view:label_{key}", lang_code, default) # type: ignore
            async def format_json_field(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available") # type: ignore
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON") # type: ignore

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(q_line.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=q_line.static_id or "N/A", inline=True)
            embed.add_field(name=await get_label("is_main", "Is Main Storyline"), value=str(q_line.is_main_storyline), inline=True)
            embed.add_field(name=await get_label("starting_quest_sid", "Starting Quest Static ID"), value=q_line.starting_quest_static_id or "N/A", inline=True)
            embed.add_field(name=await get_label("req_prev_ql_sid", "Required Previous Questline Static ID"), value=q_line.required_previous_questline_static_id or "N/A", inline=True)
            title_i18n_str = await format_json_field(q_line.title_i18n, "questline_view:value_na_json", "questline_view:error_serialization_title")
            embed.add_field(name=await get_label("title_i18n", "Title (i18n)"), value=f"```json\n{title_i18n_str[:1000]}\n```" + ("..." if len(title_i18n_str) > 1000 else ""), inline=False)
            desc_i18n_str = await format_json_field(q_line.description_i18n, "questline_view:value_na_json", "questline_view:error_serialization_desc")
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```" + ("..." if len(desc_i18n_str) > 1000 else ""), inline=False)
            props_str = await format_json_field(q_line.properties_json, "questline_view:value_na_json", "questline_view:error_serialization_props")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{props_str[:1000]}\n```" + ("..." if len(props_str) > 1000 else ""), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_master_cmds.command(name="questline_list", description="List Questlines in this guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of Questlines per page.")
    async def questline_list(self, interaction: discord.Interaction, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10
        if interaction.guild_id is None:
            await interaction.followup.send("This command can only be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            offset = (page - 1) * limit
            questlines = await questline_crud.get_multi_by_guild_id(session, guild_id=interaction.guild_id, skip=offset, limit=limit)
            total_ql_stmt = select(func.count(questline_crud.model.id)).where(questline_crud.model.guild_id == interaction.guild_id)
            total_ql_result = await session.execute(total_ql_stmt)
            total_questlines = total_ql_result.scalar_one_or_none() or 0

            if not questlines:
                no_ql_msg = await get_localized_message_template(session, interaction.guild_id, "questline_list:no_questlines_found_page", lang_code, "No Questlines found for this guild (Page {page}).")
                await interaction.followup.send(no_ql_msg.format(page=page), ephemeral=True)
                return

            title_template = await get_localized_message_template(session, interaction.guild_id, "questline_list:title", lang_code, "Questline List (Page {page} of {total_pages})")
            total_pages = ((total_questlines - 1) // limit) + 1
            embed_title = title_template.format(page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_blue())
            footer_template = await get_localized_message_template(session, interaction.guild_id, "questline_list:footer", lang_code, "Displaying {count} of {total} total Questlines.")
            embed.set_footer(text=footer_template.format(count=len(questlines), total=total_questlines))
            field_name_template = await get_localized_message_template(session, interaction.guild_id, "questline_list:ql_field_name", lang_code, "ID: {ql_id} | {ql_title} (Static: {static_id})") # type: ignore
            field_value_template = await get_localized_message_template(session, interaction.guild_id, "questline_list:ql_field_value", lang_code, "Main: {is_main}, Starts with: {starting_sid}") # type: ignore

            for ql in questlines:
                ql_title_display = ql.title_i18n.get(lang_code, ql.title_i18n.get("en", f"Questline {ql.id}"))
                embed.add_field(
                    name=field_name_template.format(ql_id=ql.id, ql_title=ql_title_display, static_id=ql.static_id or "N/A"),
                    value=field_value_template.format(is_main=str(ql.is_main_storyline), starting_sid=ql.starting_quest_static_id or "N/A"),
                    inline=False)
            if len(embed.fields) == 0:
                no_display_msg = await get_localized_message_template(session, interaction.guild_id, "questline_list:no_ql_to_display", lang_code, "No Questlines found to display on page {page}.")
                await interaction.followup.send(no_display_msg.format(page=page), ephemeral=True)
                return
            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_master_cmds.command(name="questline_create", description="Create a new Questline.")
    @app_commands.describe(
        static_id="Static ID for this Questline (unique within guild).",
        title_i18n_json="JSON for Questline title (e.g., {\"en\": \"Main Story\", \"ru\": \"Главный Сюжет\"}).",
        description_i18n_json="Optional: JSON for Questline description.",
        starting_quest_static_id="Optional: Static ID of the first GeneratedQuest in this line.",
        is_main_storyline="Is this a main storyline? (True/False, defaults to False).",
        required_previous_questline_static_id="Optional: Static ID of a Questline that must be completed first.",
        properties_json="Optional: JSON for additional Questline properties."
    )
    async def questline_create(self, interaction: discord.Interaction, static_id: str, title_i18n_json: str, description_i18n_json: Optional[str] = None, starting_quest_static_id: Optional[str] = None, is_main_storyline: bool = False, required_previous_questline_static_id: Optional[str] = None, properties_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        parsed_title_i18n: Dict[str, str]
        parsed_desc_i18n: Optional[Dict[str, str]] = None
        parsed_props: Optional[Dict[str, Any]] = None
        if interaction.guild_id is None:
            await interaction.followup.send("This command can only be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            existing_ql_static = await questline_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=static_id)
            if existing_ql_static:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "questline_create:error_static_id_exists", lang_code, "Questline static_id '{id}' already exists.")
                await interaction.followup.send(error_msg.format(id=static_id), ephemeral=True); return
            if starting_quest_static_id:
                start_quest = await generated_quest_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=starting_quest_static_id)
                if not start_quest:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "questline_create:error_start_quest_not_found", lang_code, "Starting quest with static_id '{id}' not found.")
                    await interaction.followup.send(error_msg.format(id=starting_quest_static_id), ephemeral=True); return
            if required_previous_questline_static_id:
                prev_ql = await questline_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=required_previous_questline_static_id)
                if not prev_ql:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "questline_create:error_prev_ql_not_found", lang_code, "Required previous questline with static_id '{id}' not found.")
                    await interaction.followup.send(error_msg.format(id=required_previous_questline_static_id), ephemeral=True); return
            try:
                parsed_title_i18n = json.loads(title_i18n_json)
                if not isinstance(parsed_title_i18n, dict) or not all(isinstance(k, str) and isinstance(v, str) for k,v in parsed_title_i18n.items()): raise ValueError("title_i18n_json must be a dict of str:str.")
                if not parsed_title_i18n.get("en") and not parsed_title_i18n.get(lang_code): raise ValueError("title_i18n_json must contain 'en' or current language key.")
                if description_i18n_json:
                    parsed_desc_i18n = json.loads(description_i18n_json)
                    if not isinstance(parsed_desc_i18n, dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in parsed_desc_i18n.items()): raise ValueError("description_i18n_json must be a dict of str:str.")
                if properties_json:
                    parsed_props = json.loads(properties_json)
                    if not isinstance(parsed_props, dict): raise ValueError("properties_json must be a dict.")
            except ValueError as e: # Specific exception first
                error_msg = await get_localized_message_template(session, interaction.guild_id, "questline_create:error_invalid_json", lang_code, "Invalid JSON for i18n/properties: {details}")
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return
            except json.JSONDecodeError as e: # Broader exception later
                error_msg = await get_localized_message_template(session, interaction.guild_id, "questline_create:error_invalid_json", lang_code, "Invalid JSON for i18n/properties: {details}")
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return

            ql_data_create: Dict[str, Any] = {"guild_id": interaction.guild_id, "static_id": static_id, "title_i18n": parsed_title_i18n, "description_i18n": parsed_desc_i18n or {}, "starting_quest_static_id": starting_quest_static_id, "is_main_storyline": is_main_storyline, "required_previous_questline_static_id": required_previous_questline_static_id, "properties_json": parsed_props or {}}
            created_ql: Optional[Any] = None
            try:
                async with session.begin():
                    created_ql = await questline_crud.create_with_guild(session, obj_in=ql_data_create, guild_id=interaction.guild_id) # type: ignore
                    await session.flush();
                    if created_ql: await session.refresh(created_ql)
            except Exception as e:
                logger.error(f"Error creating Questline: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, interaction.guild_id, "questline_create:error_generic_create", lang_code, "Error creating Questline: {error}")
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return
            if not created_ql:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "questline_create:error_unknown_fail", lang_code, "Questline creation failed mysteriously.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title = await get_localized_message_template(session, interaction.guild_id, "questline_create:success_title", lang_code, "Questline Created: {title} (ID: {id})")
            created_ql_title_display = created_ql.title_i18n.get(lang_code, created_ql.title_i18n.get("en", ""))
            embed = discord.Embed(title=success_title.format(title=created_ql_title_display, id=created_ql.id), color=discord.Color.green())
            embed.add_field(name="Static ID", value=created_ql.static_id, inline=True)
            embed.add_field(name="Is Main", value=str(created_ql.is_main_storyline), inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_master_cmds.command(name="questline_update", description="Update a specific field for a Questline.")
    @app_commands.describe(
        questline_id="The database ID of the Questline to update.",
        field_to_update="Field to update (e.g., static_id, title_i18n_json, starting_quest_static_id, is_main_storyline).",
        new_value="New value for the field (use JSON for complex types; 'None' for nullable; True/False for boolean)."
    )
    async def questline_update(self, interaction: discord.Interaction, questline_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        allowed_fields = {"static_id": str, "title_i18n": dict, "description_i18n": dict, "starting_quest_static_id": (str, type(None)), "is_main_storyline": bool, "required_previous_questline_static_id": (str, type(None)), "properties_json": dict}
        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()
        db_field_name = field_to_update_lower
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")
        field_type_info = allowed_fields.get(db_field_name)
        if interaction.guild_id is None:
            await interaction.followup.send("This command can only be used in a guild.", ephemeral=True)
            return

        if not field_type_info:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "questline_update:error_field_not_allowed", lang_code, "Field '{f}' not allowed. Allowed: {l}")
            await interaction.followup.send(error_msg.format(f=field_to_update, l=', '.join(allowed_fields.keys())), ephemeral=True); return

        parsed_value: Any = None
        async with get_db_session() as session:
            try:
                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: raise ValueError("static_id cannot be empty.")
                    existing_ql = await questline_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                    if existing_ql and existing_ql.id != questline_id:
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_static_id_exists",lang_code,"Static ID '{id}' already in use.")
                        await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                elif db_field_name in ["title_i18n", "description_i18n", "properties_json"]:
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict): raise ValueError(f"{db_field_name} must be a dict.")
                elif db_field_name == "starting_quest_static_id" or db_field_name == "required_previous_questline_static_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = new_value
                        if db_field_name == "starting_quest_static_id" and parsed_value:
                            related_quest = await generated_quest_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                            if not related_quest:
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_start_quest_not_found",lang_code,"Starting quest static_id '{id}' not found.")
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                        elif db_field_name == "required_previous_questline_static_id" and parsed_value:
                            related_ql = await questline_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                            if not related_ql:
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_prev_ql_not_found",lang_code,"Required previous questline static_id '{id}' not found.")
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                            if related_ql.id == questline_id:
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_self_dependency",lang_code,"Questline cannot require itself.")
                                await interaction.followup.send(error_msg, ephemeral=True); return
                elif db_field_name == "is_main_storyline":
                    if new_value.lower() == 'true': parsed_value = True
                    elif new_value.lower() == 'false': parsed_value = False
                    else: raise ValueError("is_main_storyline must be True or False.")
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_unknown_field",lang_code,"Unknown field for update.")
                    await interaction.followup.send(error_msg, ephemeral=True); return
            except ValueError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_invalid_value",lang_code,"Invalid value for {f}: {details}") # type: ignore
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return
            except json.JSONDecodeError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_invalid_json",lang_code,"Invalid JSON for {f}: {details}") # type: ignore
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            ql_to_update = await questline_crud.get_by_id(session, id=questline_id, guild_id=interaction.guild_id) # type: ignore
            if not ql_to_update:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_not_found",lang_code,"Questline ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=questline_id), ephemeral=True); return

            update_data = {db_field_name: parsed_value}
            updated_ql: Optional[Any] = None
            try:
                async with session.begin():
                    updated_ql = await update_entity(session, entity=ql_to_update, data=update_data)
                    await session.flush();
                    if updated_ql: await session.refresh(updated_ql)
            except Exception as e:
                logger.error(f"Error updating Questline {questline_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_generic_update",lang_code,"Error updating Questline {id}: {err}")
                await interaction.followup.send(error_msg.format(id=questline_id, err=str(e)), ephemeral=True); return

            if not updated_ql: # Should not happen if previous checks pass and no exception
                error_msg = await get_localized_message_template(session, interaction.guild_id, "questline_update:error_unknown_update_fail", lang_code, "Questline update failed for an unknown reason.")
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:success",lang_code,"Questline ID {id} updated. Field '{f}' set to '{v}'.")
            new_val_display = str(parsed_value)
            if isinstance(parsed_value, dict): new_val_display = json.dumps(parsed_value)
            await interaction.followup.send(success_msg.format(id=updated_ql.id, f=field_to_update, v=new_val_display), ephemeral=True)

    @quest_master_cmds.command(name="questline_delete", description="Delete a Questline.")
    @app_commands.describe(questline_id="The database ID of the Questline to delete.")
    async def questline_delete(self, interaction: discord.Interaction, questline_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            await interaction.followup.send("This command can only be used in a guild.", ephemeral=True)
            return
        async with get_db_session() as session:
            ql_to_delete = await questline_crud.get_by_id(session, id=questline_id, guild_id=interaction.guild_id) # type: ignore
            if not ql_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_delete:error_not_found",lang_code,"Questline ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=questline_id), ephemeral=True); return

            ql_title_for_msg = ql_to_delete.title_i18n.get(lang_code, ql_to_delete.title_i18n.get("en", f"Questline {ql_to_delete.id}"))
            linked_quests_stmt = select(generated_quest_crud.model.id).where(generated_quest_crud.model.questline_id == questline_id, generated_quest_crud.model.guild_id == interaction.guild_id).limit(1)
            linked_quest_exists = (await session.execute(linked_quests_stmt)).scalar_one_or_none()
            if linked_quest_exists:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_delete:error_quest_dependency",lang_code,"Cannot delete Questline '{title}' (ID: {id}) as it has associated quests. Delete them first.")
                await interaction.followup.send(error_msg.format(title=ql_title_for_msg, id=questline_id), ephemeral=True); return
            if ql_to_delete.static_id:
                dependent_ql_stmt = select(questline_crud.model.id).where(questline_crud.model.required_previous_questline_static_id == ql_to_delete.static_id, questline_crud.model.guild_id == interaction.guild_id).limit(1)
                dependent_ql_exists = (await session.execute(dependent_ql_stmt)).scalar_one_or_none()
                if dependent_ql_exists:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_delete:error_dependent_ql_dependency",lang_code,"Cannot delete Questline '{title}' (ID: {id}) as other questlines depend on it. Update those dependencies first.")
                    await interaction.followup.send(error_msg.format(title=ql_title_for_msg, id=questline_id), ephemeral=True); return

            deleted_ql: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_ql = await questline_crud.remove_by_id(session, id=questline_id, guild_id=interaction.guild_id) # type: ignore
                if deleted_ql:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"questline_delete:success",lang_code,"Questline '{title}' (ID: {id}) deleted successfully.")
                    await interaction.followup.send(success_msg.format(title=ql_title_for_msg, id=questline_id), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_delete:error_unknown_delete_fail",lang_code,"Questline (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=questline_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Questline {questline_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_delete:error_generic_delete",lang_code,"Error deleting Questline '{title}' (ID: {id}): {err}")
                await interaction.followup.send(error_msg.format(title=ql_title_for_msg, id=questline_id, err=str(e)), ephemeral=True)

    # --- GeneratedQuest Subcommands ---
    @quest_master_cmds.command(name="generated_quest_view", description="View details of a specific GeneratedQuest.")
    @app_commands.describe(quest_id="The database ID of the GeneratedQuest to view.")
    async def generated_quest_view(self, interaction: discord.Interaction, quest_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("This command can only be used in a guild.", ephemeral=True)
            return
        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            gq = await generated_quest_crud.get_by_id(session, id=quest_id, guild_id=interaction.guild_id) # type: ignore
            if not gq:
                not_found_msg = await get_localized_message_template(session, interaction.guild_id, "gq_view:not_found", lang_code, "GeneratedQuest with ID {id} not found in this guild.")
                await interaction.followup.send(not_found_msg.format(id=quest_id), ephemeral=True); return

            title_template = await get_localized_message_template(session, interaction.guild_id, "gq_view:title", lang_code, "GeneratedQuest Details: {gq_title} (ID: {gq_id})")
            gq_title_display = gq.title_i18n.get(lang_code, gq.title_i18n.get("en", f"Quest {gq.id}"))
            embed_title = title_template.format(gq_title=gq_title_display, gq_id=gq.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_orange())

            async def get_label(key: str, default: str) -> str: return await get_localized_message_template(session, interaction.guild_id, f"gq_view:label_{key}", lang_code, default) # type: ignore
            async def format_json_field(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available") # type: ignore
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON") # type: ignore

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(gq.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=gq.static_id or "N/A", inline=True)
            embed.add_field(name=await get_label("questline_id", "Questline ID"), value=str(gq.questline_id) if gq.questline_id else "N/A", inline=True)
            embed.add_field(name=await get_label("type", "Type"), value=gq.quest_type or "N/A", inline=True) # Changed gq.type to gq.quest_type
            embed.add_field(name=await get_label("is_repeatable", "Is Repeatable"), value=str(gq.is_repeatable), inline=True)
            title_i18n_str = await format_json_field(gq.title_i18n, "gq_view:value_na_json", "gq_view:error_serialization_title")
            embed.add_field(name=await get_label("title_i18n", "Title (i18n)"), value=f"```json\n{title_i18n_str[:1000]}\n```" + ("..." if len(title_i18n_str) > 1000 else ""), inline=False)
            desc_i18n_str = await format_json_field(gq.description_i18n, "gq_view:value_na_json", "gq_view:error_serialization_desc")
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```" + ("..." if len(desc_i18n_str) > 1000 else ""), inline=False)
            props_str = await format_json_field(gq.properties_json, "gq_view:value_na_json", "gq_view:error_serialization_props")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{props_str[:1000]}\n```" + ("..." if len(props_str) > 1000 else ""), inline=False)
            rewards_str = await format_json_field(gq.rewards_json, "gq_view:value_na_json", "gq_view:error_serialization_rewards")
            embed.add_field(name=await get_label("rewards", "Rewards JSON"), value=f"```json\n{rewards_str[:1000]}\n```" + ("..." if len(rewards_str) > 1000 else ""), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_master_cmds.command(name="generated_quest_list", description="List GeneratedQuests in this guild, optionally filtered by Questline.")
    @app_commands.describe(questline_id="Optional: Database ID of the Questline to filter quests by.", page="Page number to display.", limit="Number of GeneratedQuests per page.")
    async def generated_quest_list(self, interaction: discord.Interaction, questline_id: Optional[int] = None, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            await interaction.followup.send("This command can only be used in a guild.", ephemeral=True)
            return
        async with get_db_session() as session:
            filters = [generated_quest_crud.model.guild_id == interaction.guild_id]
            if questline_id is not None: filters.append(generated_quest_crud.model.questline_id == questline_id)
            offset = (page - 1) * limit
            query = select(generated_quest_crud.model).where(and_(*filters)).offset(offset).limit(limit).order_by(generated_quest_crud.model.id.desc())
            result = await session.execute(query)
            g_quests = result.scalars().all()
            count_query = select(func.count(generated_quest_crud.model.id)).where(and_(*filters))
            total_gq_result = await session.execute(count_query)
            total_g_quests = total_gq_result.scalar_one_or_none() or 0
            filter_desc = f"Questline ID: {questline_id}" if questline_id else "All"

            if not g_quests:
                no_gq_msg = await get_localized_message_template(session, interaction.guild_id, "gq_list:no_gq_found_page", lang_code, "No GeneratedQuests found for {filter_criteria} (Page {page}).")
                await interaction.followup.send(no_gq_msg.format(filter_criteria=filter_desc, page=page), ephemeral=True); return

            title_template = await get_localized_message_template(session, interaction.guild_id, "gq_list:title", lang_code, "GeneratedQuest List ({filter_criteria} - Page {page} of {total_pages})")
            total_pages = ((total_g_quests - 1) // limit) + 1
            embed_title = title_template.format(filter_criteria=filter_desc, page=page, total_pages=total_pages)
            embed = discord.Embed(title=embed_title, color=discord.Color.dark_gold())
            footer_template = await get_localized_message_template(session, interaction.guild_id, "gq_list:footer", lang_code, "Displaying {count} of {total} total GeneratedQuests.")
            embed.set_footer(text=footer_template.format(count=len(g_quests), total=total_g_quests))
            field_name_template = await get_localized_message_template(session, interaction.guild_id, "gq_list:gq_field_name", lang_code, "ID: {gq_id} | {gq_title} (Static: {static_id})") # type: ignore
            field_value_template = await get_localized_message_template(session, interaction.guild_id, "gq_list:gq_field_value", lang_code, "Type: {type}, Questline ID: {ql_id}, Repeatable: {repeatable}") # type: ignore

            for gq_obj in g_quests:
                gq_title_display = gq_obj.title_i18n.get(lang_code, gq_obj.title_i18n.get("en", f"Quest {gq_obj.id}"))
                embed.add_field(name=field_name_template.format(gq_id=gq_obj.id, gq_title=gq_title_display, static_id=gq_obj.static_id or "N/A"),
                                value=field_value_template.format(type=gq_obj.quest_type or "N/A", ql_id=str(gq_obj.questline_id) if gq_obj.questline_id else "N/A", repeatable=str(gq_obj.is_repeatable)), # Changed gq_obj.type to gq_obj.quest_type
                                inline=False)
            if len(embed.fields) == 0:
                no_display_msg = await get_localized_message_template(session, interaction.guild_id, "gq_list:no_gq_to_display", lang_code, "No GeneratedQuests found to display on page {page} for {filter_criteria}.")
                await interaction.followup.send(no_display_msg.format(page=page, filter_criteria=filter_desc), ephemeral=True); return
            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_master_cmds.command(name="generated_quest_create", description="Create a new GeneratedQuest.")
    @app_commands.describe( static_id="Static ID for this quest (unique within guild).", title_i18n_json="JSON for quest title (e.g., {\"en\": \"Slay Goblins\", \"ru\": \"Убить Гоблинов\"}).", description_i18n_json="Optional: JSON for quest description.", quest_type="Optional: Type of the quest (e.g., SLAY, FETCH, EXPLORE).", questline_id="Optional: Database ID of the Questline this quest belongs to.", is_repeatable="Is this quest repeatable? (True/False, defaults to False).", properties_json="Optional: JSON for additional quest properties.", rewards_json="Optional: JSON describing rewards for completing the quest.")
    async def generated_quest_create(self, interaction: discord.Interaction, static_id: str, title_i18n_json: str, description_i18n_json: Optional[str] = None, quest_type: Optional[str] = None, questline_id: Optional[int] = None, is_repeatable: bool = False, properties_json: Optional[str] = None, rewards_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        parsed_title_i18n: Dict[str, str]; parsed_desc_i18n: Optional[Dict[str, str]] = None; parsed_props: Optional[Dict[str, Any]] = None; parsed_rewards: Optional[Dict[str, Any]] = None
        if interaction.guild_id is None:
            await interaction.followup.send("This command can only be used in a guild.", ephemeral=True)
            return
        async with get_db_session() as session:
            existing_gq_static = await generated_quest_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=static_id)
            if existing_gq_static:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "gq_create:error_static_id_exists", lang_code, "GeneratedQuest static_id '{id}' already exists.")
                await interaction.followup.send(error_msg.format(id=static_id), ephemeral=True); return
            if questline_id:
                ql = await questline_crud.get_by_id(session, id=questline_id, guild_id=interaction.guild_id) # type: ignore
                if not ql:
                    error_msg = await get_localized_message_template(session, interaction.guild_id, "gq_create:error_questline_not_found", lang_code, "Questline with ID {id} not found.")
                    await interaction.followup.send(error_msg.format(id=questline_id), ephemeral=True); return
            try:
                parsed_title_i18n = json.loads(title_i18n_json)
                if not isinstance(parsed_title_i18n, dict) or not all(isinstance(k, str) and isinstance(v,str) for k,v in parsed_title_i18n.items()): raise ValueError("title_i18n_json must be a dict of str:str.")
                if not parsed_title_i18n.get("en") and not parsed_title_i18n.get(lang_code): raise ValueError("title_i18n_json must contain 'en' or current language key.")
                if description_i18n_json:
                    parsed_desc_i18n = json.loads(description_i18n_json)
                    if not isinstance(parsed_desc_i18n, dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in parsed_desc_i18n.items()): raise ValueError("description_i18n_json must be a dict of str:str.")
                if properties_json:
                    parsed_props = json.loads(properties_json)
                    if not isinstance(parsed_props, dict): raise ValueError("properties_json must be a dict.")
                if rewards_json:
                    parsed_rewards = json.loads(rewards_json)
                    if not isinstance(parsed_rewards, dict): raise ValueError("rewards_json must be a dict.")
            except ValueError as e: # Specific exception first
                error_msg = await get_localized_message_template(session, interaction.guild_id, "gq_create:error_invalid_json", lang_code, "Invalid JSON for i18n/properties/rewards: {details}")
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return
            except json.JSONDecodeError as e: # Broader exception later
                error_msg = await get_localized_message_template(session, interaction.guild_id, "gq_create:error_invalid_json", lang_code, "Invalid JSON for i18n/properties/rewards: {details}")
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return

            gq_data_create: Dict[str, Any] = {"guild_id": interaction.guild_id, "static_id": static_id, "title_i18n": parsed_title_i18n, "description_i18n": parsed_desc_i18n or {}, "quest_type": quest_type, "questline_id": questline_id, "is_repeatable": is_repeatable, "properties_json": parsed_props or {}, "rewards_json": parsed_rewards or {}} # Changed "type" to "quest_type"
            created_gq: Optional[Any] = None
            try:
                async with session.begin():
                    created_gq = await generated_quest_crud.create_with_guild(session, obj_in=gq_data_create, guild_id=interaction.guild_id) # type: ignore
                    await session.flush();
                    if created_gq: await session.refresh(created_gq)
            except Exception as e:
                logger.error(f"Error creating GeneratedQuest: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, interaction.guild_id, "gq_create:error_generic_create", lang_code, "Error creating GeneratedQuest: {error}")
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return
            if not created_gq:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "gq_create:error_unknown_fail", lang_code, "GeneratedQuest creation failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title = await get_localized_message_template(session, interaction.guild_id, "gq_create:success_title", lang_code, "GeneratedQuest Created: {title} (ID: {id})")
            created_gq_title_display = created_gq.title_i18n.get(lang_code, created_gq.title_i18n.get("en", ""))
            embed = discord.Embed(title=success_title.format(title=created_gq_title_display, id=created_gq.id), color=discord.Color.green())
            embed.add_field(name="Static ID", value=created_gq.static_id, inline=True)
            embed.add_field(name="Type", value=created_gq.quest_type or "N/A", inline=True) # Changed created_gq.type to created_gq.quest_type
            embed.add_field(name="Questline ID", value=str(created_gq.questline_id) if created_gq.questline_id else "N/A", inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_master_cmds.command(name="generated_quest_update", description="Update a specific field for a GeneratedQuest.")
    @app_commands.describe(quest_id="The database ID of the GeneratedQuest to update.", field_to_update="Field to update (e.g., static_id, title_i18n_json, questline_id, is_repeatable).", new_value="New value for the field (use JSON for complex types; 'None' for nullable; True/False for boolean).")
    async def generated_quest_update(self, interaction: discord.Interaction, quest_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        allowed_fields = {"static_id": str, "title_i18n": dict, "description_i18n": dict, "type": (str, type(None)), "questline_id": (int, type(None)), "is_repeatable": bool, "properties_json": dict, "rewards_json": dict}
        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()
        db_field_name = field_to_update_lower
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")
        field_type_info = allowed_fields.get(db_field_name)
        if interaction.guild_id is None:
            await interaction.followup.send("This command can only be used in a guild.", ephemeral=True)
            return

        if not field_type_info:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "gq_update:error_field_not_allowed", lang_code, "Field '{f}' not allowed. Allowed: {l}")
            await interaction.followup.send(error_msg.format(f=field_to_update, l=', '.join(allowed_fields.keys())), ephemeral=True); return

        parsed_value: Any = None
        async with get_db_session() as session:
            try:
                if db_field_name == "static_id":
                    parsed_value = new_value
                    if not parsed_value: raise ValueError("static_id cannot be empty.")
                    existing_gq = await generated_quest_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=parsed_value)
                    if existing_gq and existing_gq.id != quest_id:
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:error_static_id_exists",lang_code,"Static ID '{id}' already in use.")
                        await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                elif db_field_name in ["title_i18n", "description_i18n", "properties_json", "rewards_json"]:
                    parsed_value = json.loads(new_value)
                    if not isinstance(parsed_value, dict): raise ValueError(f"{db_field_name} must be a dict.")
                elif db_field_name == "type": # Should be quest_type
                    if new_value.lower() == 'none' or new_value.lower() == 'null': parsed_value = None
                    else: parsed_value = new_value
                    db_field_name = "quest_type" # Correct field name
                elif db_field_name == "questline_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null': parsed_value = None
                    else:
                        parsed_value = int(new_value)
                        if parsed_value is not None:
                            ql = await questline_crud.get_by_id(session, id=parsed_value, guild_id=interaction.guild_id) # type: ignore
                            if not ql:
                                error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:error_questline_not_found",lang_code,"Questline ID '{id}' not found.")
                                await interaction.followup.send(error_msg.format(id=parsed_value), ephemeral=True); return
                elif db_field_name == "is_repeatable":
                    if new_value.lower() == 'true': parsed_value = True
                    elif new_value.lower() == 'false': parsed_value = False
                    else: raise ValueError("is_repeatable must be True or False.")
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:error_unknown_field",lang_code,"Unknown field for update.")
                    await interaction.followup.send(error_msg, ephemeral=True); return
            except ValueError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:error_invalid_value",lang_code,"Invalid value for {f}: {details}") # type: ignore
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return
            except json.JSONDecodeError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:error_invalid_json",lang_code,"Invalid JSON for {f}: {details}") # type: ignore
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            gq_to_update = await generated_quest_crud.get_by_id(session, id=quest_id, guild_id=interaction.guild_id) # type: ignore
            if not gq_to_update:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:error_not_found",lang_code,"GeneratedQuest ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=quest_id), ephemeral=True); return

            update_data = {db_field_name: parsed_value}
            updated_gq: Optional[Any] = None
            try:
                async with session.begin():
                    updated_gq = await update_entity(session, entity=gq_to_update, data=update_data)
                    await session.flush();
                    if updated_gq: await session.refresh(updated_gq)
            except Exception as e:
                logger.error(f"Error updating GeneratedQuest {quest_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:error_generic_update",lang_code,"Error updating GeneratedQuest {id}: {err}")
                await interaction.followup.send(error_msg.format(id=quest_id, err=str(e)), ephemeral=True); return

            if not updated_gq:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "gq_update:error_unknown_update_fail", lang_code, "GeneratedQuest update failed for an unknown reason.")
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:success",lang_code,"GeneratedQuest ID {id} updated. Field '{f}' set to '{v}'.")
            new_val_display = str(parsed_value)
            if isinstance(parsed_value, dict): new_val_display = json.dumps(parsed_value)
            await interaction.followup.send(success_msg.format(id=updated_gq.id, f=field_to_update, v=new_val_display), ephemeral=True)

    @quest_master_cmds.command(name="generated_quest_delete", description="Delete a GeneratedQuest and its associated steps & progress.")
    @app_commands.describe(quest_id="The database ID of the GeneratedQuest to delete.")
    async def generated_quest_delete(self, interaction: discord.Interaction, quest_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            await interaction.followup.send("This command can only be used in a guild.", ephemeral=True)
            return
        async with get_db_session() as session:
            gq_to_delete = await generated_quest_crud.get_by_id(session, id=quest_id, guild_id=interaction.guild_id) # type: ignore
            if not gq_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_delete:error_not_found",lang_code,"GeneratedQuest ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=quest_id), ephemeral=True); return

            gq_title_for_msg = gq_to_delete.title_i18n.get(lang_code, gq_to_delete.title_i18n.get("en", f"Quest {gq_to_delete.id}"))
            deleted_gq: Optional[Any] = None
            try:
                async with session.begin():
                    from sqlalchemy import delete # For bulk delete operation
                    await session.execute(delete(QStepModel).where(QStepModel.quest_id == quest_id))
                    await session.execute(delete(PQPModel).where(PQPModel.quest_id == quest_id, PQPModel.guild_id == interaction.guild_id)) # Added guild_id
                    deleted_gq = await generated_quest_crud.remove_by_id(session, id=quest_id, guild_id=interaction.guild_id) # type: ignore

                if deleted_gq:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"gq_delete:success",lang_code,"GeneratedQuest '{title}' (ID: {id}) and its data deleted.")
                    await interaction.followup.send(success_msg.format(title=gq_title_for_msg, id=quest_id), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_delete:error_unknown_delete_fail",lang_code,"GeneratedQuest (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=quest_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting GeneratedQuest {quest_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_delete:error_generic_delete",lang_code,"Error deleting GeneratedQuest '{title}' (ID: {id}): {err}")
                await interaction.followup.send(error_msg.format(title=gq_title_for_msg, id=quest_id, err=str(e)), ephemeral=True)

async def setup(bot: commands.Bot):
    cog = MasterQuestCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterQuestCog loaded.")
