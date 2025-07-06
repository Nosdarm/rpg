import logging
import json
from typing import Dict, Any, Optional

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

        async with get_db_session() as session:
            lang_code = str(interaction.locale)
            # Use the initialized CRUD instance
            log_entry = await self.story_log_crud_instance.get_by_id_and_guild(session, id=log_id, guild_id=interaction.guild_id)

            if not log_entry:
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

            embed.add_field(name=await get_label("guild_id", "Guild ID"), value=str(log_entry.guild_id), inline=True)
            embed.add_field(name=await get_label("event_type", "Event Type"), value=log_entry.event_type.value if log_entry.event_type else "N/A", inline=True)
            embed.add_field(name=await get_label("turn_number", "Turn Number"), value=str(log_entry.turn_number) if log_entry.turn_number is not None else "N/A", inline=True)

            timestamp_val = discord.utils.format_dt(log_entry.timestamp, style='F') if log_entry.timestamp else "N/A"
            embed.add_field(name=await get_label("timestamp", "Timestamp"), value=timestamp_val, inline=False)

            embed.add_field(name=await get_label("short_description", "Short Description"), value=log_entry.short_description_i18n.get(lang_code, log_entry.short_description_i18n.get("en", "N/A"))[:1020], inline=False)

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
        if limit > 5: limit = 5

        lang_code = str(interaction.locale)
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
                filters.append(self.story_log_crud_instance.model.turn_number == turn_number)

            offset = (page - 1) * limit
            query = select(self.story_log_crud_instance.model).where(and_(*filters)).offset(offset).limit(limit).order_by(self.story_log_crud_instance.model.timestamp.desc(), self.story_log_crud_instance.model.id.desc())
            result = await session.execute(query)
            log_entries = result.scalars().all()

            count_query = select(func.count(self.story_log_crud_instance.model.id)).where(and_(*filters))
            total_logs_res = await session.execute(count_query)
            total_logs = total_logs_res.scalar_one_or_none() or 0

            filter_parts = []
            if event_type_enum_val: filter_parts.append(f"Event: {event_type_enum_val.name}")
            if turn_number is not None: filter_parts.append(f"Turn: {turn_number}")
            filter_display = ", ".join(filter_parts) if filter_parts else "All"

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
                desc_short = entry.short_description_i18n.get(lang_code, entry.short_description_i18n.get("en", "No description"))
                ts_formatted = discord.utils.format_dt(entry.timestamp, style='R') if entry.timestamp else "No timestamp"
                embed.add_field(
                    name=name_tmpl.format(id=entry.id, event_type_val=entry.event_type.value if entry.event_type else "N/A", tn=entry.turn_number if entry.turn_number is not None else "N/A"),
                    value=val_tmpl.format(desc=desc_short[:200] + ("..." if len(desc_short) > 200 else ""), ts=ts_formatted),
                    inline=False
                )
            await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    cog = MasterStoryLogCog(bot)
    await bot.add_cog(cog)
    logger.info("MasterStoryLogCog loaded.")
