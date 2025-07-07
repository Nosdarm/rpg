import logging
import json
from typing import Dict, Any, Optional, List, cast
from datetime import datetime # Added for casting

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, and_ # Added func for count

from src.core.crud.crud_player_npc_memory import crud_player_npc_memory
from src.core.crud.crud_player import player_crud # For fetching names
from src.core.crud.crud_npc import npc_crud # For fetching names
from src.core.database import get_db_session
from src.core.localization_utils import get_localized_message_template
from src.models.player_npc_memory import PlayerNpcMemory # For type hinting

logger = logging.getLogger(__name__)

class MasterMemoryCog(commands.Cog, name="Master Memory Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MasterMemoryCog initialized.")

    memory_master_cmds = app_commands.Group(
        name="master_memory",
        description="Master commands for managing Player-NPC Memories.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    async def _format_json_field_helper(self, interaction: discord.Interaction, data: Optional[Dict[Any, Any]], lang_code: str, default_na_key: str, error_key: str) -> str:
        async with get_db_session() as session:
            na_str = await get_localized_message_template(session, interaction.guild_id, default_na_key, lang_code, "Not available")
            if not data: return na_str
            try: return json.dumps(data, indent=2, ensure_ascii=False)
            except TypeError: return await get_localized_message_template(session, interaction.guild_id, error_key, lang_code, "Error serializing JSON")

    @memory_master_cmds.command(name="view", description="View details of a specific Player-NPC Memory entry.")
    @app_commands.describe(memory_id="The database ID of the PlayerNpcMemory entry to view.")
    async def memory_view(self, interaction: discord.Interaction, memory_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale) # Defined early
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        # lang_code = str(interaction.locale) # Already defined
        async with get_db_session() as session:
            memory_entry = await crud_player_npc_memory.get(session, id=memory_id, guild_id=interaction.guild_id)

            if not memory_entry:
                not_found_msg = await get_localized_message_template(session, interaction.guild_id, "memory_view:not_found", lang_code, "Memory entry ID {id} not found.")
                await interaction.followup.send(not_found_msg.format(id=memory_id), ephemeral=True); return

            player_name = f"Player {memory_entry.player_id}"
            npc_name = f"NPC {memory_entry.npc_id}"
            player = await player_crud.get(session, id=memory_entry.player_id, guild_id=interaction.guild_id)
            if player: player_name = player.name
            npc = await npc_crud.get(session, id=memory_entry.npc_id, guild_id=interaction.guild_id)
            if npc: npc_name = npc.name_i18n.get(lang_code, npc.name_i18n.get("en", f"NPC {memory_entry.npc_id}"))

            title_template = await get_localized_message_template(session, interaction.guild_id, "memory_view:title", lang_code, "Memory: {p_name} <> {n_name} (ID: {id})")
            embed_title = title_template.format(p_name=player_name, n_name=npc_name, id=memory_entry.id)
            embed = discord.Embed(title=embed_title, color=discord.Color.light_grey())

            async def get_label(key: str, default: str) -> str:
                return await get_localized_message_template(session, interaction.guild_id, f"memory_view:label_{key}", lang_code, default)


            na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")

            embed.add_field(name=await get_label("player_id", "Player ID"), value=str(memory_entry.player_id), inline=True)
            embed.add_field(name=await get_label("npc_id", "NPC ID"), value=str(memory_entry.npc_id), inline=True)
            embed.add_field(name=await get_label("event_type", "Event Type"), value=memory_entry.event_type or na_value_str, inline=True)
            embed.add_field(name=await get_label("significance", "AI Significance"), value=str(memory_entry.ai_significance_score) if memory_entry.ai_significance_score is not None else na_value_str, inline=True)

            ts_val = discord.utils.format_dt(cast(datetime, memory_entry.timestamp), style='F') if memory_entry.timestamp else na_value_str
            embed.add_field(name=await get_label("timestamp", "Timestamp"), value=ts_val, inline=False)

            details_i18n_str = await self._format_json_field_helper(interaction, memory_entry.memory_details_i18n, lang_code, "memory_view:value_na", "memory_view:error_json")
            embed.add_field(name=await get_label("details_i18n", "Details (i18n)"), value=f"```json\n{details_i18n_str[:1000]}\n```", inline=False)
            data_json_str = await self._format_json_field_helper(interaction, memory_entry.memory_data_json, lang_code, "memory_view:value_na", "memory_view:error_json")
            embed.add_field(name=await get_label("data_json", "Data JSON"), value=f"```json\n{data_json_str[:1000]}\n```", inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

    @memory_master_cmds.command(name="list", description="List Player-NPC Memory entries with filters.")
    @app_commands.describe(
        player_id="Optional: Filter by Player ID.",
        npc_id="Optional: Filter by NPC ID.",
        event_type="Optional: Filter by event type.",
        page="Page number.", limit="Entries per page."
    )
    async def memory_list(self, interaction: discord.Interaction,
                          player_id: Optional[int] = None,
                          npc_id: Optional[int] = None,
                          event_type: Optional[str] = None,
                          page: int = 1, limit: int = 5):
        await interaction.response.defer(ephemeral=True)
        if page < 1: page = 1
        if limit < 1: limit = 1
        if limit > 5: limit = 5
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            conditions = [PlayerNpcMemory.guild_id == interaction.guild_id]
            if player_id is not None: conditions.append(PlayerNpcMemory.player_id == player_id)
            if npc_id is not None: conditions.append(PlayerNpcMemory.npc_id == npc_id)
            if event_type: conditions.append(PlayerNpcMemory.event_type.ilike(f"%{event_type}%"))

            offset = (page - 1) * limit
            query = select(PlayerNpcMemory).where(and_(*conditions)).offset(offset).limit(limit).order_by(PlayerNpcMemory.timestamp.desc())
            result = await session.execute(query)
            mem_entries = result.scalars().all()

            total_mem_entries = await crud_player_npc_memory.get_count_for_filters(session, guild_id=interaction.guild_id, player_id=player_id, npc_id=npc_id, event_type=event_type)

            filter_parts = []
            # Локализация названий фильтров
            player_id_filter_label = await get_localized_message_template(session, interaction.guild_id, "memory_list:filter_player_id", lang_code, "Player ID")
            npc_id_filter_label = await get_localized_message_template(session, interaction.guild_id, "memory_list:filter_npc_id", lang_code, "NPC ID")
            event_filter_label = await get_localized_message_template(session, interaction.guild_id, "memory_list:filter_event", lang_code, "Event")
            all_filter_label = await get_localized_message_template(session, interaction.guild_id, "common:filter_all", lang_code, "All")

            if player_id is not None: filter_parts.append(f"{player_id_filter_label}: {player_id}")
            if npc_id is not None: filter_parts.append(f"{npc_id_filter_label}: {npc_id}")
            if event_type: filter_parts.append(f"{event_filter_label}: {event_type}")
            filter_display = ", ".join(filter_parts) if filter_parts else all_filter_label

            if not mem_entries:
                no_mem_msg = await get_localized_message_template(session,interaction.guild_id,"memory_list:no_entries_found",lang_code,"No Memory entries for {filter} (Page {p}).")
                await interaction.followup.send(no_mem_msg.format(filter=filter_display, p=page), ephemeral=True); return

            title_tmpl = await get_localized_message_template(session,interaction.guild_id,"memory_list:title",lang_code,"Memory List ({filter} - Page {p} of {tp})")
            total_pages = ((total_mem_entries - 1) // limit) + 1
            embed = discord.Embed(title=title_tmpl.format(filter=filter_display, p=page, tp=total_pages), color=discord.Color.dark_grey())
            footer_tmpl = await get_localized_message_template(session,interaction.guild_id,"memory_list:footer",lang_code,"Displaying {c} of {t} total entries.")
            embed.set_footer(text=footer_tmpl.format(c=len(mem_entries), t=total_mem_entries))
            name_tmpl = await get_localized_message_template(session,interaction.guild_id,"memory_list:entry_name_field",lang_code,"ID: {id} | Player {p_id} <> NPC {n_id}")
            val_tmpl = await get_localized_message_template(session,interaction.guild_id,"memory_list:entry_value_field",lang_code,"Event: {e_type} (@ {ts})")

            for entry in mem_entries:
                na_value_str = await get_localized_message_template(session, interaction.guild_id, "common:value_na", lang_code, "N/A")
                ts_formatted = discord.utils.format_dt(cast(datetime, entry.timestamp), style='R') if entry.timestamp else na_value_str # Added cast
                embed.add_field(
                    name=name_tmpl.format(id=entry.id, p_id=entry.player_id, n_id=entry.npc_id),
                    value=val_tmpl.format(e_type=entry.event_type or na_value_str, ts=ts_formatted),
                    inline=False
                )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @memory_master_cmds.command(name="delete", description="Delete a Player-NPC Memory entry.")
    @app_commands.describe(memory_id="The database ID of the PlayerNpcMemory entry to delete.")
    async def memory_delete(self, interaction: discord.Interaction, memory_id: int):
        await interaction.response.defer(ephemeral=True)
        lang_code = str(interaction.locale)
        if interaction.guild_id is None:
            async with get_db_session() as temp_session:
                error_msg = await get_localized_message_template(temp_session, interaction.guild_id, "common:error_guild_only_command", lang_code, "This command must be used in a server.")
            await interaction.followup.send(error_msg, ephemeral=True); return

        async with get_db_session() as session:
            memory_to_delete = await crud_player_npc_memory.get(session, id=memory_id, guild_id=interaction.guild_id)
            if not memory_to_delete:
                error_msg = await get_localized_message_template(session,interaction.guild_id,"memory_delete:error_not_found",lang_code,"Memory entry ID {id} not found.")
                await interaction.followup.send(error_msg.format(id=memory_id), ephemeral=True); return

            entry_repr = f"Player {memory_to_delete.player_id} <> NPC {memory_to_delete.npc_id}, Event: {memory_to_delete.event_type or 'N/A'}"
            deleted_entry: Optional[Any] = None
            try:
                async with session.begin():
                    deleted_entry = await crud_player_npc_memory.delete(session, id=memory_id, guild_id=interaction.guild_id)
                if deleted_entry:
                    success_msg = await get_localized_message_template(session,interaction.guild_id,"memory_delete:success",lang_code,"Memory entry ID {id} ({repr}) deleted.")
                    await interaction.followup.send(success_msg.format(id=memory_id, repr=entry_repr), ephemeral=True)
                else:
                    error_msg = await get_localized_message_template(session,interaction.guild_id,"memory_delete:error_unknown_fail",lang_code,"Memory entry (ID: {id}) found but not deleted.")
                    await interaction.followup.send(error_msg.format(id=memory_id), ephemeral=True)
            except Exception as e:
                logger.error(f"Error deleting Memory entry {memory_id}: {e}", exc_info=True)
                error_msg = await get_localized_message_template(session,interaction.guild_id,"memory_delete:error_generic_delete",lang_code,"Error deleting Memory ID {id}: {err}")
                await interaction.followup.send(error_msg.format(id=memory_id, err=str(e)), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(MasterMemoryCog(bot))
    logger.info("MasterMemoryCog loaded.")
