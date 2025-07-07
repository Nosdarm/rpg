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
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return
        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            q_line = await questline_crud.get(session, id=questline_id, guild_id=interaction.guild_id)

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
                na_str_val = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available") # type: ignore
                if not data: return na_str_val
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON") # type: ignore

            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A") # type: ignore

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(q_line.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=q_line.static_id or na_value_str, inline=True)
            embed.add_field(name=await get_label("is_main", "Is Main Storyline"), value=str(q_line.is_main_storyline), inline=True)
            embed.add_field(name=await get_label("starting_quest_sid", "Starting Quest Static ID"), value=q_line.starting_quest_static_id or na_value_str, inline=True)
            embed.add_field(name=await get_label("req_prev_ql_sid", "Required Previous Questline Static ID"), value=q_line.required_previous_questline_static_id or na_value_str, inline=True)
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
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            offset = (page - 1) * limit
            questlines = await questline_crud.get_multi(session, guild_id=interaction.guild_id, skip=offset, limit=limit)
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
                na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A") # type: ignore
                embed.add_field(
                    name=field_name_template.format(ql_id=ql.id, ql_title=ql_title_display, static_id=ql.static_id or na_value_str),
                    value=field_value_template.format(is_main=str(ql.is_main_storyline), starting_sid=ql.starting_quest_static_id or na_value_str),
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
        if interaction.guild_id is None: # lang_code is defined before this block
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
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
            # JSONDecodeError is a subclass of ValueError, so this block is unreachable if ValueError is caught first.
            # except json.JSONDecodeError as e:
            #     error_msg = await get_localized_message_template(session, interaction.guild_id, "questline_create:error_invalid_json", lang_code, "Invalid JSON for i18n/properties: {details}")
            #     await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return

            ql_data_create: Dict[str, Any] = {"guild_id": interaction.guild_id, "static_id": static_id, "title_i18n": parsed_title_i18n, "description_i18n": parsed_desc_i18n or {}, "starting_quest_static_id": starting_quest_static_id, "is_main_storyline": is_main_storyline, "required_previous_questline_static_id": required_previous_questline_static_id, "properties_json": parsed_props or {}}
            created_ql: Optional[Any] = None
            try:
                async with session.begin():
                    # guild_id is already in ql_data_create and handled by CRUDBase.create
                    created_ql = await questline_crud.create(session, obj_in=ql_data_create)
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

            async def get_created_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"questline_create:label_{key}", lang_code, default) # type: ignore

            embed.add_field(name=await get_created_label("static_id", "Static ID"), value=created_ql.static_id, inline=True)
            embed.add_field(name=await get_created_label("is_main", "Is Main"), value=str(created_ql.is_main_storyline), inline=True)
            if created_ql.starting_quest_static_id:
                embed.add_field(name=await get_created_label("starting_quest_sid", "Starting Quest SID"), value=created_ql.starting_quest_static_id, inline=True)
            if created_ql.required_previous_questline_static_id:
                embed.add_field(name=await get_created_label("req_prev_ql_sid", "Requires Prev. QL SID"), value=created_ql.required_previous_questline_static_id, inline=True)
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
         if interaction.guild_id is None: # lang_code defined before
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
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
            # JSONDecodeError is a subclass of ValueError, so this block is unreachable if ValueError is caught first.
            # except json.JSONDecodeError as e:
            #     error_msg = await get_localized_message_template(session,interaction.guild_id,"questline_update:error_invalid_json",lang_code,"Invalid JSON for {f}: {details}") # type: ignore
            #     await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            ql_to_update = await questline_crud.get(session, id=questline_id, guild_id=interaction.guild_id)
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

            new_val_display_str: str
            if parsed_value is None:
                new_val_display_str = await get_localized_message_template(session, interaction.guild_id, "common:value_none", lang_code, "None") # type: ignore
            elif isinstance(parsed_value, dict):
                try:
                    json_str = json.dumps(parsed_value, indent=2, ensure_ascii=False)
                    new_val_display_str = f"```json\n{json_str[:1000]}\n```"
                    if len(json_str) > 1000: new_val_display_str += "..."
                except TypeError:
                    new_val_display_str = await get_localized_message_template(session, interaction.guild_id, "questline_update:error_serialization_new_value", lang_code, "Error displaying new value (non-serializable JSON).") # type: ignore
            else:
                new_val_display_str = str(parsed_value)

            await interaction.followup.send(success_msg.format(id=updated_ql.id, f=field_to_update, v=new_val_display_str), ephemeral=True)

    @quest_master_cmds.command(name="questline_delete", description="Delete a Questline.")
    @app_commands.describe(questline_id="The database ID of the Questline to delete.")
    async def questline_delete(self, interaction: discord.Interaction, questline_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return
        async with get_db_session() as session:
            ql_to_delete = await questline_crud.get(session, id=questline_id, guild_id=interaction.guild_id)
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
                    deleted_ql = await questline_crud.delete(session, id=questline_id, guild_id=interaction.guild_id)
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
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return
        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            gq = await generated_quest_crud.get(session, id=quest_id, guild_id=interaction.guild_id)
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

            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A") # type: ignore

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(gq.guild_id), inline=True)
            embed.add_field(name=await get_label("static_id", "Static ID"), value=gq.static_id or na_value_str, inline=True)
            embed.add_field(name=await get_label("questline_id", "Questline ID"), value=str(gq.questline_id) if gq.questline_id else na_value_str, inline=True)
            quest_type_val = (gq.properties_json.get("quest_type") if gq.properties_json else None) or na_value_str
            embed.add_field(name=await get_label("type", "Type"), value=quest_type_val, inline=True)
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
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
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
                na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A") # type: ignore
                quest_type_val = (gq_obj.properties_json.get("quest_type") if gq_obj.properties_json else None) or na_value_str
                embed.add_field(name=field_name_template.format(gq_id=gq_obj.id, gq_title=gq_title_display, static_id=gq_obj.static_id or na_value_str),
                                value=field_value_template.format(type=quest_type_val, ql_id=str(gq_obj.questline_id) if gq_obj.questline_id else na_value_str, repeatable=str(gq_obj.is_repeatable)),
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
        if interaction.guild_id is None: # lang_code defined before
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return
        async with get_db_session() as session:
            existing_gq_static = await generated_quest_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=static_id)
            if existing_gq_static:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "gq_create:error_static_id_exists", lang_code, "GeneratedQuest static_id '{id}' already exists.")
                await interaction.followup.send(error_msg.format(id=static_id), ephemeral=True); return
            if questline_id:
                ql = await questline_crud.get(session, id=questline_id, guild_id=interaction.guild_id)
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
            # JSONDecodeError is a subclass of ValueError, so this block is unreachable if ValueError is caught first.
            # except json.JSONDecodeError as e:
            #     error_msg = await get_localized_message_template(session, interaction.guild_id, "gq_create:error_invalid_json", lang_code, "Invalid JSON for i18n/properties/rewards: {details}")
            #     await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return

            final_properties = parsed_props or {}
            if quest_type:
                final_properties["quest_type"] = quest_type

            gq_data_create: Dict[str, Any] = {"guild_id": interaction.guild_id, "static_id": static_id, "title_i18n": parsed_title_i18n, "description_i18n": parsed_desc_i18n or {}, "questline_id": questline_id, "is_repeatable": is_repeatable, "properties_json": final_properties, "rewards_json": parsed_rewards or {}}
            created_gq: Optional[Any] = None
            try:
                async with session.begin():
                    # guild_id is already in gq_data_create and handled by CRUDBase.create
                    created_gq = await generated_quest_crud.create(session, obj_in=gq_data_create)
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

            async def get_created_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"gq_create:label_{key}", lang_code, default) # type: ignore
            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A") # type: ignore

            embed.add_field(name=await get_created_label("static_id", "Static ID"), value=created_gq.static_id, inline=True)
            quest_type_display = (created_gq.properties_json.get("quest_type") if created_gq.properties_json else None) or na_value_str
            embed.add_field(name=await get_created_label("type", "Type"), value=quest_type_display, inline=True)
            embed.add_field(name=await get_created_label("questline_id", "Questline ID"), value=str(created_gq.questline_id) if created_gq.questline_id else na_value_str, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_master_cmds.command(name="generated_quest_update", description="Update a specific field for a GeneratedQuest.")
    @app_commands.describe(quest_id="The database ID of the GeneratedQuest to update.", field_to_update="Field to update (e.g., static_id, title_i18n_json, quest_type, questline_id, is_repeatable).", new_value="New value for the field (use JSON for complex types; 'None' for nullable; True/False for boolean).") # Added quest_type to desc
    async def generated_quest_update(self, interaction: discord.Interaction, quest_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        # Note: "quest_type" is handled specially as it's stored in properties_json
        allowed_fields = {"static_id": str, "title_i18n": dict, "description_i18n": dict, "quest_type": (str, type(None)), "questline_id": (int, type(None)), "is_repeatable": bool, "properties_json": dict, "rewards_json": dict}
        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()
        db_field_name = field_to_update_lower
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")
        # Special handling for quest_type, as it's not a direct DB field in the updated logic
        is_updating_quest_type_in_props = (db_field_name == "quest_type")
        if not is_updating_quest_type_in_props: # Only get field_type_info if not quest_type
            field_type_info = allowed_fields.get(db_field_name)
        else: # For quest_type, we'll handle its type parsing separately
            field_type_info = allowed_fields.get("quest_type")


        if interaction.guild_id is None: # lang_code defined before
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
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
                elif is_updating_quest_type_in_props: # Handle quest_type separately
                    if new_value.lower() == 'none' or new_value.lower() == 'null': parsed_value = None
                    else: parsed_value = new_value
                    # db_field_name remains "quest_type" for the purpose of updating properties_json
                elif db_field_name == "questline_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null': parsed_value = None
                    else:
                        parsed_value = int(new_value)
                        if parsed_value is not None:
                            ql = await questline_crud.get(session, id=parsed_value, guild_id=interaction.guild_id)
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
            # JSONDecodeError is a subclass of ValueError, so this block is unreachable if ValueError is caught first.
            # except json.JSONDecodeError as e:
            #     error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:error_invalid_json",lang_code,"Invalid JSON for {f}: {details}") # type: ignore
            #     await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            gq_to_update = await generated_quest_crud.get(session, id=quest_id, guild_id=interaction.guild_id)
            if not gq_to_update:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"gq_update:error_not_found",lang_code,"GeneratedQuest ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=quest_id), ephemeral=True); return

            if is_updating_quest_type_in_props:
                current_properties = dict(gq_to_update.properties_json or {})
                if parsed_value is None: # If new_value was 'none' or 'null'
                    current_properties.pop("quest_type", None) # Remove the key if it exists
                else:
                    current_properties["quest_type"] = parsed_value
                update_data = {"properties_json": current_properties}
            else:
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

            new_val_display_str: str
            if parsed_value is None:
                new_val_display_str = await get_localized_message_template(session, interaction.guild_id, "common:value_none", lang_code, "None") # type: ignore
            elif isinstance(parsed_value, dict):
                try:
                    json_str = json.dumps(parsed_value, indent=2, ensure_ascii=False)
                    new_val_display_str = f"```json\n{json_str[:1000]}\n```"
                    if len(json_str) > 1000: new_val_display_str += "..."
                except TypeError:
                    new_val_display_str = await get_localized_message_template(session, interaction.guild_id, "gq_update:error_serialization_new_value", lang_code, "Error displaying new value (non-serializable JSON).") # type: ignore
            else:
                new_val_display_str = str(parsed_value)

            await interaction.followup.send(success_msg.format(id=updated_gq.id, f=field_to_update, v=new_val_display_str), ephemeral=True)

    @quest_master_cmds.command(name="generated_quest_delete", description="Delete a GeneratedQuest and its associated steps & progress.")
    @app_commands.describe(quest_id="The database ID of the GeneratedQuest to delete.")
    async def generated_quest_delete(self, interaction: discord.Interaction, quest_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return
        async with get_db_session() as session:
            gq_to_delete = await generated_quest_crud.get(session, id=quest_id, guild_id=interaction.guild_id)
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
                    deleted_gq = await generated_quest_crud.delete(session, id=quest_id, guild_id=interaction.guild_id)

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

    # --- QuestStep Subcommands ---
    @quest_master_cmds.command(name="quest_step_create", description="Create a new QuestStep for a GeneratedQuest.")
    @app_commands.describe(
        quest_id="Database ID of the parent GeneratedQuest.",
        step_order="Order of this step within the quest.",
        title_i18n_json="JSON for step title (e.g., {\"en\": \"Collect Herbs\", \"ru\": \"Собрать Травы\"}).",
        description_i18n_json="JSON for step description.",
        required_mechanics_json="Optional: JSON for required mechanics.",
        abstract_goal_json="Optional: JSON for abstract goal.",
        consequences_json="Optional: JSON for consequences upon completion.",
        next_step_order="Optional: Order of the next step if this one is completed.",
        properties_json="Optional: JSON for additional step properties."
    )
    async def quest_step_create(self, interaction: discord.Interaction,
                                quest_id: int,
                                step_order: int,
                                title_i18n_json: str,
                                description_i18n_json: str,
                                required_mechanics_json: Optional[str] = None,
                                abstract_goal_json: Optional[str] = None,
                                consequences_json: Optional[str] = None,
                                next_step_order: Optional[int] = None,
                                properties_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        parsed_title: Dict[str, str]; parsed_desc: Dict[str, str]
        parsed_req_mech: Optional[Dict[str, Any]] = None; parsed_abs_goal: Optional[Dict[str, Any]] = None
        parsed_conseq: Optional[Dict[str, Any]] = None; parsed_props: Optional[Dict[str, Any]] = None

        if interaction.guild_id is None: # lang_code defined before
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        async with get_db_session() as session:
            parent_quest = await generated_quest_crud.get(session, id=quest_id, guild_id=interaction.guild_id)
            if not parent_quest:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "qs_create:error_parent_quest_not_found", lang_code, "Parent GeneratedQuest with ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=quest_id), ephemeral=True); return

            existing_step_order = await quest_step_crud.get_by_quest_and_order(session, quest_id=quest_id, step_order=step_order)
            if existing_step_order:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "qs_create:error_step_order_exists", lang_code, "A QuestStep with order {order} already exists for quest ID {q_id}.")
                await interaction.followup.send(error_msg.format(order=step_order, q_id=quest_id), ephemeral=True); return
            try:
                parsed_title = json.loads(title_i18n_json)
                parsed_desc = json.loads(description_i18n_json)
                if not isinstance(parsed_title, dict) or not all(isinstance(k,str)and isinstance(v,str) for k,v in parsed_title.items()): raise ValueError("title_i18n_json must be dict str:str.")
                if not isinstance(parsed_desc, dict) or not all(isinstance(k,str)and isinstance(v,str) for k,v in parsed_desc.items()): raise ValueError("description_i18n_json must be dict str:str.")
                if required_mechanics_json: parsed_req_mech = json.loads(required_mechanics_json); assert isinstance(parsed_req_mech, dict)
                if abstract_goal_json: parsed_abs_goal = json.loads(abstract_goal_json); assert isinstance(parsed_abs_goal, dict)
                if consequences_json: parsed_conseq = json.loads(consequences_json); assert isinstance(parsed_conseq, dict)
                if properties_json: parsed_props = json.loads(properties_json); assert isinstance(parsed_props, dict)
            except (json.JSONDecodeError, ValueError, AssertionError) as e:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "qs_create:error_invalid_json", lang_code, "Invalid JSON input: {details}")
                await interaction.followup.send(error_msg.format(details=str(e)), ephemeral=True); return

            qs_data_create = {"quest_id": quest_id, "step_order": step_order, "title_i18n": parsed_title, "description_i18n": parsed_desc, "required_mechanics_json": parsed_req_mech or {}, "abstract_goal_json": parsed_abs_goal or {}, "consequences_json": parsed_conseq or {}, "next_step_order": next_step_order, "properties_json": parsed_props or {}}
            created_qs: Optional[Any] = None
            try:
                async with session.begin():
                    created_qs = await quest_step_crud.create_with_quest_id(session, obj_in=qs_data_create, quest_id=quest_id) # type: ignore
                    await session.flush();
                    if created_qs: await session.refresh(created_qs)
            except Exception as e:
                logger.error(f"Error creating QuestStep: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session, interaction.guild_id, "qs_create:error_generic_create", lang_code, "Error creating QuestStep: {error}")
                await interaction.followup.send(error_msg.format(error=str(e)), ephemeral=True); return
            if not created_qs:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "qs_create:error_unknown_fail", lang_code, "QuestStep creation failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_title = await get_localized_message_template(session, interaction.guild_id, "qs_create:success_title", lang_code, "QuestStep Created (ID: {id}) for Quest {q_id}")
            embed = discord.Embed(title=success_title.format(id=created_qs.id, q_id=created_qs.quest_id), color=discord.Color.green())

            async def get_created_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"qs_create:label_{key}", lang_code, default) # type: ignore
            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A") # type: ignore

            embed.add_field(name=await get_created_label("order", "Order"), value=str(created_qs.step_order), inline=True)
            step_title_display = created_qs.title_i18n.get(lang_code, created_qs.title_i18n.get("en", na_value_str))
            embed.add_field(name=await get_created_label("title", "Title"), value=step_title_display, inline=False)
            if created_qs.next_step_order is not None:
                embed.add_field(name=await get_created_label("next_step_order", "Next Step Order"), value=str(created_qs.next_step_order), inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_master_cmds.command(name="quest_step_view", description="View details of a specific QuestStep.")
    @app_commands.describe(quest_step_id="The database ID of the QuestStep to view.")
    async def quest_step_view(self, interaction: discord.Interaction, quest_step_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return
        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            # QuestStep doesn't have guild_id directly, it's through GeneratedQuest.
            # We need to join or fetch parent quest to verify guild_id if strictly needed by CRUD.
            # For now, assuming quest_step_crud.get handles this or we trust the ID.
            # A better approach for guild-scoped child entities is to pass parent_id and validate that.
            # However, for a simple view by ID, we might fetch and then check parent's guild_id.
            qs = await quest_step_crud.get(session, id=quest_step_id) # No guild_id here directly

            if not qs:
                not_found_msg = await get_localized_message_template(session, interaction.guild_id, "qs_view:not_found", lang_code, "QuestStep with ID {id} not found.")
                await interaction.followup.send(not_found_msg.format(id=quest_step_id), ephemeral=True); return

            # Verify guild_id through parent quest
            parent_quest = await generated_quest_crud.get(session, id=qs.quest_id, guild_id=interaction.guild_id)
            if not parent_quest:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "qs_view:error_parent_quest_mismatch", lang_code, "QuestStep ID {id} found, but its parent quest does not belong to this guild or was not found.")
                await interaction.followup.send(error_msg.format(id=quest_step_id), ephemeral=True); return


            title_template = await get_localized_message_template(session, interaction.guild_id, "qs_view:title", lang_code, "QuestStep Details (ID: {id}) for Quest {q_id}")
            qs_title_display = qs.title_i18n.get(lang_code, qs.title_i18n.get("en", f"Step {qs.step_order}"))
            embed_title = title_template.format(id=qs.id, q_id=qs.quest_id) # Add qs_title_display if needed
            embed = discord.Embed(title=embed_title, description=f"**{qs_title_display}**", color=discord.Color.blue())

            async def get_label(key: str, default: str) -> str: return await get_localized_message_template(session, interaction.guild_id, f"qs_view:label_{key}", lang_code, default) # type: ignore
            async def format_json_field(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str_val = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available") # type: ignore
                if not data: return na_str_val
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON") # type: ignore

            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A") # type: ignore

            embed.add_field(name=await get_label("quest_id", "Parent Quest ID"), value=str(qs.quest_id), inline=True)
            embed.add_field(name=await get_label("step_order", "Step Order"), value=str(qs.step_order), inline=True)
            embed.add_field(name=await get_label("next_step_order", "Next Step Order"), value=str(qs.next_step_order) if qs.next_step_order is not None else na_value_str, inline=True)

            title_i18n_str = await format_json_field(qs.title_i18n, "qs_view:value_na_json", "qs_view:error_serialization_title")
            embed.add_field(name=await get_label("title_i18n", "Title (i18n)"), value=f"```json\n{title_i18n_str[:1000]}\n```" + ("..." if len(title_i18n_str) > 1000 else ""), inline=False)
            desc_i18n_str = await format_json_field(qs.description_i18n, "qs_view:value_na_json", "qs_view:error_serialization_desc")
            embed.add_field(name=await get_label("description_i18n", "Description (i18n)"), value=f"```json\n{desc_i18n_str[:1000]}\n```" + ("..." if len(desc_i18n_str) > 1000 else ""), inline=False)
            req_mech_str = await format_json_field(qs.required_mechanics_json, "qs_view:value_na_json", "qs_view:error_serialization_req_mech")
            embed.add_field(name=await get_label("req_mech", "Required Mechanics JSON"), value=f"```json\n{req_mech_str[:1000]}\n```" + ("..." if len(req_mech_str) > 1000 else ""), inline=False)
            abs_goal_str = await format_json_field(qs.abstract_goal_json, "qs_view:value_na_json", "qs_view:error_serialization_abs_goal")
            embed.add_field(name=await get_label("abs_goal", "Abstract Goal JSON"), value=f"```json\n{abs_goal_str[:1000]}\n```" + ("..." if len(abs_goal_str) > 1000 else ""), inline=False)
            conseq_str = await format_json_field(qs.consequences_json, "qs_view:value_na_json", "qs_view:error_serialization_conseq")
            embed.add_field(name=await get_label("conseq", "Consequences JSON"), value=f"```json\n{conseq_str[:1000]}\n```" + ("..." if len(conseq_str) > 1000 else ""), inline=False)
            props_str = await format_json_field(qs.properties_json, "qs_view:value_na_json", "qs_view:error_serialization_props")
            embed.add_field(name=await get_label("properties", "Properties JSON"), value=f"```json\n{props_str[:1000]}\n```" + ("..." if len(props_str) > 1000 else ""), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_master_cmds.command(name="quest_step_list", description="List QuestSteps for a specific GeneratedQuest.")
    @app_commands.describe(quest_id="Database ID of the parent GeneratedQuest.", page="Page number.", limit="Steps per page.")
    async def quest_step_list(self, interaction: discord.Interaction, quest_id: int, page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 10: limit = 10
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        async with get_db_session() as session:
            parent_quest = await generated_quest_crud.get(session, id=quest_id, guild_id=interaction.guild_id)
            if not parent_quest:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "qs_list:error_parent_quest_not_found", lang_code, "Parent GeneratedQuest ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=quest_id), ephemeral=True); return

            offset = (page - 1) * limit
            steps = await quest_step_crud.get_multi_by_quest_id(session, quest_id=quest_id, skip=offset, limit=limit) # type: ignore
            total_steps = await quest_step_crud.get_count_by_quest_id(session, quest_id=quest_id) # type: ignore

            if not steps:
                no_steps_msg = await get_localized_message_template(session,interaction.guild_id,"qs_list:no_steps_found",lang_code,"No QuestSteps found for Quest ID {q_id} (Page {p}).")
                await interaction.followup.send(no_steps_msg.format(q_id=quest_id, p=page), ephemeral=True); return

            parent_quest_title = parent_quest.title_i18n.get(lang_code, parent_quest.title_i18n.get("en", f"Quest {quest_id}"))
            title_tmpl = await get_localized_message_template(session,interaction.guild_id,"qs_list:title",lang_code,"QuestSteps for '{pq_title}' (Page {p} of {tp})")
            total_pages = ((total_steps - 1) // limit) + 1
            embed = discord.Embed(title=title_tmpl.format(pq_title=parent_quest_title, p=page, tp=total_pages), color=discord.Color.dark_blue())
            footer_tmpl = await get_localized_message_template(session,interaction.guild_id,"qs_list:footer",lang_code,"Displaying {c} of {t} total steps.")
            embed.set_footer(text=footer_tmpl.format(c=len(steps), t=total_steps))
            name_tmpl = await get_localized_message_template(session,interaction.guild_id,"qs_list:step_name_field",lang_code,"ID: {id} | Order: {order} | {title}")
            val_tmpl = await get_localized_message_template(session,interaction.guild_id,"qs_list:step_value_field",lang_code,"Next Order: {next_order}")

            for step in steps:
                step_title = step.title_i18n.get(lang_code, step.title_i18n.get("en", "N/A")) # "N/A" for title is fine if not found
                na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A") # type: ignore
                embed.add_field(name=name_tmpl.format(id=step.id, order=step.step_order, title=step_title), value=val_tmpl.format(next_order=str(step.next_step_order) if step.next_step_order is not None else na_value_str), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_master_cmds.command(name="quest_step_update", description="Update a specific field for a QuestStep.")
    @app_commands.describe(quest_step_id="ID of the QuestStep to update.", field_to_update="Field to update (e.g., step_order, title_i18n_json, next_step_order, properties_json).", new_value="New value for the field.")
    async def quest_step_update(self, interaction: discord.Interaction, quest_step_id: int, field_to_update: str, new_value: str):
        await interaction.response.defer(ephemeral=True)
        allowed_fields = {"step_order": int, "title_i18n": dict, "description_i18n": dict, "required_mechanics_json": dict, "abstract_goal_json": dict, "consequences_json": dict, "next_step_order": (int, type(None)), "properties_json": dict}
        lang_code = str(interaction.locale)
        field_to_update_lower = field_to_update.lower()
        db_field_name = field_to_update_lower
        if field_to_update_lower.endswith("_json") and field_to_update_lower.replace("_json","") in allowed_fields:
             db_field_name = field_to_update_lower.replace("_json","")
        field_type_info = allowed_fields.get(db_field_name)
         if interaction.guild_id is None: # lang_code defined before
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        if not field_type_info:
            async with get_db_session() as temp_session: error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "qs_update:error_field_not_allowed", lang_code, "Field '{f}' not allowed. Allowed: {l}")
            await interaction.followup.send(error_msg.format(f=field_to_update, l=', '.join(allowed_fields.keys())), ephemeral=True); return

        parsed_value: Any = None
        async with get_db_session() as session:
            qs_to_update = await quest_step_crud.get(session, id=quest_step_id) # Fetch first to get parent quest_id
            if not qs_to_update:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"qs_update:error_not_found",lang_code,"QuestStep ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=quest_step_id), ephemeral=True); return
            parent_quest = await generated_quest_crud.get(session, id=qs_to_update.quest_id, guild_id=interaction.guild_id)
            if not parent_quest: # Check if parent quest belongs to the guild
                error_msg = await get_localized_message_template(session,interaction.guild_id,"qs_update:error_parent_mismatch",lang_code,"QuestStep's parent quest not in this guild.")
                await interaction.followup.send(error_msg, ephemeral=True); return
            try:
                if field_type_info == dict: parsed_value = json.loads(new_value); assert isinstance(parsed_value, dict)
                elif field_type_info == int: parsed_value = int(new_value)
                elif isinstance(field_type_info, tuple) and int in field_type_info and type(None) in field_type_info: # Optional[int]
                    if new_value.lower() == 'none' or new_value.lower() == 'null': parsed_value = None
                    else: parsed_value = int(new_value)
                else: raise ValueError(f"Unsupported type for field {db_field_name}")

                if db_field_name == "step_order" and parsed_value != qs_to_update.step_order:
                    existing_step = await quest_step_crud.get_by_quest_and_order(session, quest_id=qs_to_update.quest_id, step_order=cast(int, parsed_value))
                    if existing_step and existing_step.id != quest_step_id :
                        error_msg = await get_localized_message_template(session,interaction.guild_id,"qs_update:error_step_order_exists",lang_code,"Step order {order} already exists for this quest.")
                        await interaction.followup.send(error_msg.format(order=parsed_value), ephemeral=True); return
            except (ValueError, json.JSONDecodeError, AssertionError) as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"qs_update:error_invalid_value",lang_code,"Invalid value for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update, details=str(e)), ephemeral=True); return

            update_data = {db_field_name: parsed_value}
            updated_qs: Optional[Any] = None
            try:
                async with session.begin():
                    updated_qs = await update_entity(session, entity=qs_to_update, data=update_data)
                    await session.flush();
                    if updated_qs: await session.refresh(updated_qs)
            except Exception as e:
                logger.error(f"Error updating QuestStep {quest_step_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"qs_update:error_generic_update",lang_code,"Error updating QuestStep {id}: {err}")
                await interaction.followup.send(error_msg.format(id=quest_step_id, err=str(e)), ephemeral=True); return
            if not updated_qs:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "qs_update:error_unknown_update_fail", lang_code, "QuestStep update failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"qs_update:success",lang_code,"QuestStep ID {id} updated. Field '{f}' set to '{v}'.")

            new_val_display_str: str
            if parsed_value is None:
                new_val_display_str = await get_localized_message_template(session, interaction.guild_id, "common:value_none", lang_code, "None") # type: ignore
            elif isinstance(parsed_value, dict):
                try:
                    json_str = json.dumps(parsed_value, indent=2, ensure_ascii=False)
                    new_val_display_str = f"```json\n{json_str[:1000]}\n```"
                    if len(json_str) > 1000: new_val_display_str += "..."
                except TypeError:
                    new_val_display_str = await get_localized_message_template(session, interaction.guild_id, "qs_update:error_serialization_new_value", lang_code, "Error displaying new value (non-serializable JSON).") # type: ignore
            else:
                new_val_display_str = str(parsed_value)

            await interaction.followup.send(success_msg.format(id=updated_qs.id, f=field_to_update, v=new_val_display_str), ephemeral=True)

    @quest_master_cmds.command(name="quest_step_delete", description="Delete a QuestStep.")
    @app_commands.describe(quest_step_id="The database ID of the QuestStep to delete.")
    async def quest_step_delete(self, interaction: discord.Interaction, quest_step_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return
        async with get_db_session() as session:
            qs_to_delete = await quest_step_crud.get(session, id=quest_step_id) # Fetch without guild_id first
            if not qs_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"qs_delete:error_not_found",lang_code,"QuestStep ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=quest_step_id), ephemeral=True); return
            # Verify guild ownership through parent quest
            parent_quest = await generated_quest_crud.get(session, id=qs_to_delete.quest_id, guild_id=interaction.guild_id)
            if not parent_quest:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"qs_delete:error_parent_mismatch",lang_code,"QuestStep's parent quest not in this guild. Deletion aborted.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            qs_title_for_msg = qs_to_delete.title_i18n.get(lang_code, qs_to_delete.title_i18n.get("en", f"Step {qs_to_delete.step_order} of Quest {qs_to_delete.quest_id}"))
            # Check dependencies: PlayerQuestProgress.current_step_id
            active_progress_stmt = select(PQPModel.id).where(PQPModel.current_step_id == quest_step_id, PQPModel.guild_id == interaction.guild_id).limit(1)
            active_progress_exists = (await session.execute(active_progress_stmt)).scalar_one_or_none()
            if active_progress_exists:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"qs_delete:error_active_progress_dependency",lang_code,"Cannot delete QuestStep '{title}' (ID: {id}) as it's a current step in active player/party quest progress. Update progress first.")
                await interaction.followup.send(error_msg.format(title=qs_title_for_msg, id=quest_step_id), ephemeral=True); return

            deleted_qs: Optional[Any] = None
            try:
                async with session.begin():
                    # No guild_id in quest_step_crud.delete as it's not a direct column
                    deleted_qs = await quest_step_crud.delete(session, id=quest_step_id)
                if deleted_qs:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"qs_delete:success",lang_code,"QuestStep '{title}' (ID: {id}) deleted.")
                    await interaction.followup.send(success_msg.format(title=qs_title_for_msg, id=quest_step_id), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"qs_delete:error_unknown_delete_fail",lang_code,"QuestStep (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=quest_step_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting QuestStep {quest_step_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"qs_delete:error_generic_delete",lang_code,"Error deleting QuestStep '{title}' (ID: {id}): {err}")
                await interaction.followup.send(error_msg.format(title=qs_title_for_msg, id=quest_step_id, err=str(e)), ephemeral=True)

    # --- PlayerQuestProgress Subcommands ---
    @quest_master_cmds.command(name="progress_view", description="View details of a PlayerQuestProgress entry.")
    @app_commands.describe(progress_id="The database ID of the PlayerQuestProgress entry.")
    async def progress_view(self, interaction: discord.Interaction, progress_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        # lang_code = str(interaction.locale) # Already defined
        async with get_db_session() as session:
            # PlayerQuestProgress has guild_id, so we can use it in the get
            pqp = await player_quest_progress_crud.get(session, id=progress_id, guild_id=interaction.guild_id)
            if not pqp:
                not_found_msg = await get_localized_message_template(session, interaction.guild_id, "pqp_view:not_found", lang_code, "PlayerQuestProgress with ID {id} not found.")
                await interaction.followup.send(not_found_msg.format(id=progress_id), ephemeral=True); return

            parent_quest = await generated_quest_crud.get(session, id=pqp.quest_id, guild_id=interaction.guild_id)
            quest_title = parent_quest.title_i18n.get(lang_code, parent_quest.title_i18n.get("en", f"Quest {pqp.quest_id}")) if parent_quest else f"Quest {pqp.quest_id}"

            title_template = await get_localized_message_template(session, interaction.guild_id, "pqp_view:title", lang_code, "Quest Progress: {q_title} (Entry ID: {id})")
            embed = discord.Embed(title=title_template.format(q_title=quest_title, id=pqp.id), color=discord.Color.gold())

            async def get_label(key: str, default: str) -> str: return await get_localized_message_template(session, interaction.guild_id, f"pqp_view:label_{key}", lang_code, default) # type: ignore
            async def format_json_field(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available") # type: ignore
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON") # type: ignore

            owner_str = "N/A"
            if pqp.player_id: owner_str = f"Player ID: {pqp.player_id}"
            elif pqp.party_id: owner_str = f"Party ID: {pqp.party_id}"
            embed.add_field(name=await get_label("owner", "Owner"), value=owner_str, inline=True)
            embed.add_field(name=await get_label("quest_id", "Quest ID"), value=str(pqp.quest_id), inline=True)
            embed.add_field(name=await get_label("status", "Status"), value=pqp.status.name, inline=True) # Enum name is not typically localized here

            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A") # type: ignore

            embed.add_field(name=await get_label("current_step_id", "Current Step ID"), value=str(pqp.current_step_id) if pqp.current_step_id else na_value_str, inline=True)

            accepted_at_val = discord.utils.format_dt(pqp.accepted_at, style='F') if pqp.accepted_at else na_value_str
            embed.add_field(name=await get_label("accepted_at", "Accepted At"), value=accepted_at_val, inline=True)
            completed_at_val = discord.utils.format_dt(pqp.completed_at, style='F') if pqp.completed_at else na_value_str
            embed.add_field(name=await get_label("completed_at", "Completed At"), value=completed_at_val, inline=True)

            progress_data_str = await format_json_field(pqp.progress_data_json, "pqp_view:value_na_json", "pqp_view:error_serialization_progress")
            embed.add_field(name=await get_label("progress_data", "Progress Data JSON"), value=f"```json\n{progress_data_str[:1000]}\n```" + ("..." if len(progress_data_str) > 1000 else ""), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_master_cmds.command(name="progress_list", description="List PlayerQuestProgress entries with filters.")
    @app_commands.describe(
        player_id="Optional: Filter by Player ID.",
        party_id="Optional: Filter by Party ID.",
        quest_id="Optional: Filter by GeneratedQuest ID.",
        status="Optional: Filter by status (e.g., NOT_STARTED, IN_PROGRESS, COMPLETED, FAILED).",
        page="Page number.", limit="Entries per page."
    )
    async def progress_list(self, interaction: discord.Interaction, player_id: Optional[int] = None, party_id: Optional[int] = None, quest_id: Optional[int] = None, status: Optional[str] = None, page: int = 1, limit: int = 5):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 5: limit = 5 # Keep it small for readability
        lang_code = str(interaction.locale)
        status_enum: Optional[Any] = None # Using Any for QuestStatus enum from models.enums
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        async with get_db_session() as session:
            if status:
                from src.models.enums import QuestStatus # Local import
                try: status_enum = QuestStatus[status.upper()]
                except KeyError:
                    valid_statuses = ", ".join([s.name for s in QuestStatus])
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"pqp_list:error_invalid_status",lang_code,"Invalid status. Valid: {list}")
                    await interaction.followup.send(error_msg.format(list=valid_statuses), ephemeral=True); return

            filters = [PQPModel.guild_id == interaction.guild_id]
            if player_id is not None: filters.append(PQPModel.player_id == player_id)
            if party_id is not None: filters.append(PQPModel.party_id == party_id)
            if quest_id is not None: filters.append(PQPModel.quest_id == quest_id)
            if status_enum is not None: filters.append(PQPModel.status == status_enum)

            offset = (page - 1) * limit
            query = select(PQPModel).where(and_(*filters)).offset(offset).limit(limit).order_by(PQPModel.id.desc())
            result = await session.execute(query)
            pqp_entries = result.scalars().all()
            count_query = select(func.count(PQPModel.id)).where(and_(*filters))
            total_pqp_res = await session.execute(count_query)
            total_pqp_entries = total_pqp_res.scalar_one_or_none() or 0

            filter_parts = []
            if player_id is not None: filter_parts.append(f"Player ID: {player_id}")
            if party_id is not None: filter_parts.append(f"Party ID: {party_id}")
            if quest_id is not None: filter_parts.append(f"Quest ID: {quest_id}")
            if status_enum: filter_parts.append(f"Status: {status_enum.name}")
            filter_display = ", ".join(filter_parts) if filter_parts else "All"

            if not pqp_entries:
                no_pqp_msg = await get_localized_message_template(session,interaction.guild_id,"pqp_list:no_pqp_found",lang_code,"No Quest Progress entries for {filter} (Page {p}).")
                await interaction.followup.send(no_pqp_msg.format(filter=filter_display, p=page), ephemeral=True); return

            title_tmpl = await get_localized_message_template(session,interaction.guild_id,"pqp_list:title",lang_code,"Quest Progress List ({filter} - Page {p} of {tp})")
            total_pages = ((total_pqp_entries - 1) // limit) + 1
            embed = discord.Embed(title=title_tmpl.format(filter=filter_display, p=page, tp=total_pages), color=discord.Color.dark_gold())
            footer_tmpl = await get_localized_message_template(session,interaction.guild_id,"pqp_list:footer",lang_code,"Displaying {c} of {t} total entries.")
            embed.set_footer(text=footer_tmpl.format(c=len(pqp_entries), t=total_pqp_entries))
            name_tmpl = await get_localized_message_template(session,interaction.guild_id,"pqp_list:pqp_name_field",lang_code,"ID: {id} | Quest ID: {q_id}")
            val_tmpl = await get_localized_message_template(session,interaction.guild_id,"pqp_list:pqp_value_field",lang_code,"Owner: {owner} | Status: {status_val}, Step ID: {step_id}")

            for pqp_item in pqp_entries:
                na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A") # type: ignore
                owner_val = f"Player {pqp_item.player_id}" if pqp_item.player_id else (f"Party {pqp_item.party_id}" if pqp_item.party_id else na_value_str)
                embed.add_field(name=name_tmpl.format(id=pqp_item.id, q_id=pqp_item.quest_id), value=val_tmpl.format(owner=owner_val, status_val=pqp_item.status.name, step_id=str(pqp_item.current_step_id) if pqp_item.current_step_id else na_value_str), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @quest_master_cmds.command(name="progress_update", description="Update status or current step for a PlayerQuestProgress entry.")
    @app_commands.describe(progress_id="ID of the PlayerQuestProgress entry.", field_to_update="Field to update (status or current_step_id).", new_value="New value (QuestStatus enum name for status; integer for current_step_id; 'None' for nullable current_step_id).")
    @app_commands.choices(field_to_update=[app_commands.Choice(name="Status", value="status"), app_commands.Choice(name="Current Step ID", value="current_step_id"),])
    async def progress_update(self, interaction: discord.Interaction, progress_id: int, field_to_update: app_commands.Choice[str], new_value: str):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        db_field_name = field_to_update.value
        parsed_value: Any = None
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        async with get_db_session() as session:
            pqp_to_update = await player_quest_progress_crud.get(session, id=progress_id, guild_id=interaction.guild_id)
            if not pqp_to_update:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"pqp_update:error_not_found",lang_code,"PlayerQuestProgress ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=progress_id), ephemeral=True); return
            try:
                if db_field_name == "status":
                    from src.models.enums import QuestStatus # Local import
                    try:
                        parsed_value = QuestStatus[new_value.upper()]
                    except KeyError:
                        valid_statuses = ", ".join([s.name for s in QuestStatus])
                        error_detail_template = await get_localized_message_template(session, interaction.guild_id, "pqp_update:error_detail_invalid_status", lang_code, "Invalid QuestStatus. Use one of: {valid_options}") # type: ignore
                        raise ValueError(error_detail_template.format(valid_options=valid_statuses))
                elif db_field_name == "current_step_id":
                    if new_value.lower() == 'none' or new_value.lower() == 'null':
                        parsed_value = None
                    else:
                        parsed_value = int(new_value)
                        if parsed_value is not None:
                            step_exists = await quest_step_crud.get_by_quest_and_id(session, quest_id=pqp_to_update.quest_id, step_id=parsed_value) # type: ignore
                            if not step_exists:
                                error_detail_template = await get_localized_message_template(session, interaction.guild_id, "pqp_update:error_detail_step_not_found_for_quest", lang_code, "QuestStep ID {step_id} not found for Quest ID {quest_id}.") # type: ignore
                                raise ValueError(error_detail_template.format(step_id=parsed_value, quest_id=pqp_to_update.quest_id))
                else:
                    error_detail_template = await get_localized_message_template(session, interaction.guild_id, "pqp_update:error_detail_invalid_field", lang_code, "Invalid field_to_update selection.") # type: ignore
                    raise ValueError(error_detail_template)
            except ValueError as e:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"pqp_update:error_invalid_value",lang_code,"Invalid value for {f}: {details}")
                await interaction.followup.send(error_msg.format(f=field_to_update.name, details=str(e)), ephemeral=True); return

            update_data = {db_field_name: parsed_value}
            updated_pqp: Optional[Any] = None
            try:
                async with session.begin():
                    updated_pqp = await update_entity(session, entity=pqp_to_update, data=update_data)
                    await session.flush();
                    if updated_pqp: await session.refresh(updated_pqp)
            except Exception as e:
                logger.error(f"Error updating PlayerQuestProgress {progress_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"pqp_update:error_generic_update",lang_code,"Error updating PQP {id}: {err}")
                await interaction.followup.send(error_msg.format(id=progress_id, err=str(e)), ephemeral=True); return
            if not updated_pqp:
                error_msg = await get_localized_message_template(session, interaction.guild_id, "pqp_update:error_unknown_update_fail", lang_code, "PQP update failed.")
                await interaction.followup.send(error_msg, ephemeral=True); return

            success_msg = await get_localized_message_template(session,interaction.guild_id,"pqp_update:success",lang_code,"PQP ID {id} updated. Field '{f}' set to '{v}'.")

            new_val_display_str: str
            if parsed_value is None:
                new_val_display_str = await get_localized_message_template(session, interaction.guild_id, "common:value_none", lang_code, "None") # type: ignore
            elif db_field_name == "status": # Check if it's the enum
                new_val_display_str = parsed_value.name
            else:
                new_val_display_str = str(parsed_value)

            await interaction.followup.send(success_msg.format(id=updated_pqp.id, f=field_to_update.name, v=new_val_display_str), ephemeral=True)

    @quest_master_cmds.command(name="progress_delete", description="Delete a PlayerQuestProgress entry.")
    @app_commands.describe(progress_id="The database ID of the PlayerQuestProgress entry to delete.")
    async def progress_delete(self, interaction: discord.Interaction, progress_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(
                    temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code,
                    "This command must be used in a server."
                ) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
            return
        async with get_db_session() as session:
            pqp_to_delete = await player_quest_progress_crud.get(session, id=progress_id, guild_id=interaction.guild_id)
            if not pqp_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"pqp_delete:error_not_found",lang_code,"PlayerQuestProgress ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=progress_id), ephemeral=True); return

            owner_repr = f"Player {pqp_to_delete.player_id}" if pqp_to_delete.player_id else f"Party {pqp_to_delete.party_id}"
            deleted_pqp: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_pqp = await player_quest_progress_crud.delete(session, id=progress_id, guild_id=interaction.guild_id)
                if deleted_pqp:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"pqp_delete:success",lang_code,"PlayerQuestProgress ID {id} (Quest {q_id} for {owner}) deleted.")
                    await interaction.followup.send(success_msg.format(id=progress_id, q_id=pqp_to_delete.quest_id, owner=owner_repr), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"pqp_delete:error_unknown_delete_fail",lang_code,"PQP (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=progress_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting PlayerQuestProgress {progress_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"pqp_delete:error_generic_delete",lang_code,"Error deleting PQP ID {id}: {err}")
                await interaction.followup.send(error_msg.format(id=progress_id, err=str(e)), ephemeral=True)


async def setup(bot: commands.Bot):
    cog = MasterQuestCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterQuestCog loaded.")
