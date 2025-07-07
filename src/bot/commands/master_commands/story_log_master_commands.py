import logging
import json
from typing import Dict, Any, Optional, cast
from datetime import datetime # Added for casting

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, and_

from src.models.story_log import StoryLog # Import model
from src.core.crud_base_definitions import CRUDBase # Use base CRUD for simple models
from src.core.database import get_db_session
from src.core.localization_utils import get_localized_message_template
from src.models.enums import EventType as EventTypeEnum # For validation

logger = logging.getLogger(__name__)

class MasterStoryLogCog(commands.Cog, name="Master Story Log Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.story_log_crud_instance = CRUDBase(StoryLog) # Initialize CRUD for StoryLog
        logger.info("MasterStoryLogCog initialized.")

    story_log_master_cmds = app_commands.Group(
        name="master_story_log",
        description="Master commands for viewing Story Log entries.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    @story_log_master_cmds.command(name="view", description="View details of a specific Story Log entry.")
    @app_commands.describe(log_id="The database ID of the Story Log entry to view.")
    async def story_log_view(self, interaction: discord.Interaction, log_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            # Use the initialized CRUD instance
            log_entry = await self.story_log_crud_instance.get_by_id(session, id=log_id, guild_id=interaction.guild_id)

            if not log_entry or log_entry.guild_id != interaction.guild_id: # Explicitly check guild_id if get_by_id doesn't filter
                not_found_msg = await get_localized_message_template(
                    session, interaction.guild_id, "story_log_view:not_found", lang_code,
                    "Story Log entry with ID {id} not found."
                )
                await interaction.followup.send(not_found_msg.format(id=log_id), ephemeral=True)
                return

            title_template = await get_localized_message_template(
                session, interaction.guild_id, "story_log_view:title", lang_code,
                "Story Log Entry (ID: {id})"
            )
            embed_title = title_template.format(id=log_entry.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.blue())

            async def get_label(key: str, default: str) -> str: return await get_localized_message_template(session, interaction.guild_id, f"story_log_view:label_{key}", lang_code, default)
            async def format_json_field_helper(data: Optional[Dict[Any, Any]], default_na_key: str, error_key: str) -> str:
                na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
                if not data: return na_str
                try: return json.dumps(data, indent=2, ensure_ascii=False)
                except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")


            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(log_entry.guild_id), inline=True)
            embed.add_field(name=await get_label("event_type", "Event Type"), value=log_entry.event_type.value if log_entry.event_type else na_value_str, inline=True)
            turn_number_val = getattr(log_entry, 'turn_number', None)
            embed.add_field(name=await get_label("turn_number", "Turn Number"), value=str(turn_number_val) if turn_number_val is not None else na_value_str, inline=True)

            timestamp_val = discord.utils.format_dt(log_entry.timestamp, style='F') if log_entry.timestamp else na_value_str
            embed.add_field(name=await get_label("timestamp", "Timestamp"), value=timestamp_val, inline=False)

            short_desc_i18n = getattr(log_entry, 'short_description_i18n', {})
            short_desc_display = short_desc_i18n.get(lang_code, short_desc_i18n.get("en", na_value_str)) if short_desc_i18n else na_value_str
            embed.add_field(name=await get_label("short_description", "Short Description"), value=short_desc_display[:1020], inline=False)


            details_str = await format_json_field_helper(log_entry.details_json, "story_log_view:value_na_json", "story_log_view:error_serialization_details")
            embed.add_field(name=await get_label("details_json", "Details JSON"), value=f"```json\n{details_str[:1000]}\n```" + ("..." if len(details_str) > 1000 else ""), inline=False)

            entities_str = await format_json_field_helper(log_entry.entity_ids_json, "story_log_view:value_na_json", "story_log_view:error_serialization_entities")
            embed.add_field(name=await get_label("entity_ids_json", "Entity IDs JSON"), value=f"```json\n{entities_str[:1000]}\n```" + ("..." if len(entities_str) > 1000 else ""), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @story_log_master_cmds.command(name="list", description="List Story Log entries with filters.")
    @app_commands.describe(
        event_type="Optional: Filter by EventType (e.g., PLAYER_ACTION, COMBAT_START).",
        turn_number="Optional: Filter by turn number.",
        page="Page number.",
        limit="Entries per page."
    )
    async def story_log_list(self, interaction: discord.Interaction,
                             event_type: Optional[str] = None,
                             turn_number: Optional[int] = None,
                             page: int = 1, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 5: limit = 5 # Max 5 for embed clarity
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        # lang_code = str(interaction.locale) # Already defined
        event_type_enum_val: Optional[EventTypeEnum] = None

        async with get_db_session() as session:
            if event_type:
                try: event_type_enum_val = EventTypeEnum[event_type.upper()]
                except KeyError:
                    valid_types = ", ".join([et.name for et in EventTypeEnum])
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"story_log_list:error_invalid_event_type",lang_code,"Invalid event_type. Valid: {list}")
                    await interaction.followup.send(error_msg.format(list=valid_types), ephemeral=True); return

            filters = [self.story_log_crud_instance.model.guild_id == interaction.guild_id]
            if event_type_enum_val:
                filters.append(self.story_log_crud_instance.model.event_type == event_type_enum_val)
            if turn_number is not None:
                # Assuming 'turn_number' is a valid attribute on the model for filtering
                filters.append(self.story_log_crud_instance.model.turn_number == turn_number)

            offset = (page - 1) * limit
            query = select(self.story_log_crud_instance.model).where(and_(*filters)).offset(offset).limit(limit).order_by(self.story_log_crud_instance.model.timestamp.desc(), self.story_log_crud_instance.model.id.desc())
            result = await session.execute(query)
            log_entries = result.scalars().all()

            count_query = select(func.count(self.story_log_crud_instance.model.id)).where(and_(*filters))
            total_logs_res = await session.execute(count_query)
            total_logs = total_logs_res.scalar_one_or_none() or 0

            filter_parts = []
            # Локализация названий фильтров
            event_filter_label = await get_localized_message_template(session, interaction.guild_id, "story_log_list:filter_event", lang_code, "Event")
            turn_filter_label = await get_localized_message_template(session, interaction.guild_id, "story_log_list:filter_turn", lang_code, "Turn")
            all_filter_str = await get_localized_message_template(session, interaction.guild_id, "common:filter_all", lang_code, "All")

            if event_type_enum_val: filter_parts.append(f"{event_filter_label}: {event_type_enum_val.name}")
            if turn_number is not None: filter_parts.append(f"{turn_filter_label}: {turn_number}")
            filter_display = ", ".join(filter_parts) if filter_parts else all_filter_str

            if not log_entries:
                no_logs_msg = await get_localized_message_template(session,interaction.guild_id,"story_log_list:no_logs_found",lang_code,"No Story Log entries for {filter} (Page {p}).")
                await interaction.followup.send(no_logs_msg.format(filter=filter_display, p=page), ephemeral=True); return

            title_tmpl = await get_localized_message_template(session,interaction.guild_id,"story_log_list:title",lang_code,"Story Log List ({filter} - Page {p} of {tp})")
            total_pages = ((total_logs - 1) // limit) + 1
            embed = discord.Embed(title=title_tmpl.format(filter=filter_display, p=page, tp=total_pages), color=discord.Color.dark_blue())

            footer_tmpl = await get_localized_message_template(session,interaction.guild_id,"story_log_list:footer",lang_code,"Displaying {c} of {t} total log entries.")
            embed.set_footer(text=footer_tmpl.format(c=len(log_entries), t=total_logs))

            name_tmpl = await get_localized_message_template(session,interaction.guild_id,"story_log_list:log_name_field",lang_code,"ID: {id} | {event_type_val} (Turn: {tn})")
            val_tmpl = await get_localized_message_template(session,interaction.guild_id,"story_log_list:log_value_field",lang_code,"{desc} (@ {ts})")

            for entry in log_entries:
                na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")
                no_desc_str = await get_localized_message_template(session, interaction.guild_id, "story_log_list:no_description", lang_code, "No description")
                no_ts_str = await get_localized_message_template(session, interaction.guild_id, "story_log_list:no_timestamp", lang_code, "No timestamp")

                short_desc_i18n = getattr(entry, 'short_description_i18n', {})
                desc_short = short_desc_i18n.get(lang_code, short_desc_i18n.get("en", no_desc_str)) if short_desc_i18n else no_desc_str
                ts_formatted = discord.utils.format_dt(cast(datetime, entry.timestamp), style='R') if entry.timestamp else no_ts_str # Added cast
                turn_number_val = getattr(entry, 'turn_number', None)
                embed.add_field(
                    name=name_tmpl.format(id=entry.id, event_type_val=entry.event_type.value if entry.event_type else na_value_str, tn=str(turn_number_val) if turn_number_val is not None else na_value_str),
                    value=val_tmpl.format(desc=desc_short[:200] + ("..." if len(desc_short) > 200 else ""), ts=ts_formatted),
                    inline=False
                )
            await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    cog = MasterStoryLogCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterStoryLogCog loaded.")
