import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.crud.crud_story_log import story_log_crud
from backend.bot.utils import parse_json_parameter, ensure_guild_configured_and_get_session, get_master_player_from_interaction
from backend.core.crud import guild_crud, player_crud, npc_crud, party_crud, location_crud, rule_config_crud
from backend.core.crud.crud_global_npc import global_npc_crud
from backend.core.crud.crud_mobile_group import mobile_group_crud
from backend.core.localization_utils import get_localized_text, get_localized_master_message
from backend.core.report_formatter import format_story_log_entry_for_master_display
from backend.models import Player, GeneratedNpc, Party, Location, StoryLog, RuleConfig, GlobalNpc, MobileGroup, EventType, RelationshipEntityType
from backend.config.settings import settings

logger = logging.getLogger(__name__)

@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
class MasterMonitoringCog(commands.GroupCog, name="master_monitor", description="Master commands for monitoring game state and history."): # type: ignore[call-arg]
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()
        logger.info("MasterMonitoringCog initialized.")

    def cog_check(self, ctx: commands.Context) -> bool:
        if not isinstance(ctx, discord.Interaction):
            logger.warning(f"cog_check received unexpected type for ctx: {type(ctx)}")
            return False
        if ctx.guild is None:
            return False
        if isinstance(ctx.user, discord.Member):
            user_permissions = ctx.user.guild_permissions
            return user_permissions.administrator
        else:
            member = ctx.guild.get_member(ctx.user.id)
            if member:
                return member.guild_permissions.administrator
            return False

    log_group = app_commands.Group(name="log", description="Commands for monitoring StoryLog entries.")

    @log_group.command(name="view", description="View a specific StoryLog entry by its ID.")
    @app_commands.describe(log_id="The ID of the StoryLog entry to view.")
    async def log_view(self, interaction: discord.Interaction, log_id: int):
        await interaction.response.defer(ephemeral=True)
        master_player, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player or not session:
            return

        try:
            log_entry = await story_log_crud.get(session, id=log_id, guild_id=interaction.guild_id) # type: ignore[arg-type]

            if not log_entry:
                error_msg = await get_localized_master_message(
                    session,
                    interaction.guild_id, # type: ignore
                    "master_monitor.log_view.not_found",
                    default_template="Log entry with ID {log_id} not found.",
                    locale=str(interaction.locale),
                    log_id=log_id
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            formatted_description = await format_story_log_entry_for_master_display(
                session=session,
                log_entry=log_entry,
                language=str(interaction.locale)
            )

            embed = discord.Embed(
                title=await get_localized_master_message(
                    session,
                    interaction.guild_id, # type: ignore
                    "master_monitor.log_view.embed_title",
                    default_template="Story Log Entry Details - ID: {log_id}",
                    locale=str(interaction.locale),
                    log_id=log_entry.id
                ),
                description=formatted_description,
                color=discord.Color.blue()
            )
            embed.add_field(
                name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.log_view.field_timestamp", "Timestamp", str(interaction.locale)), # type: ignore
                value=discord.utils.format_dt(log_entry.timestamp), # type: ignore[arg-type]
                inline=True
            )
            embed.add_field(
                name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.log_view.field_event_type", "Event Type", str(interaction.locale)), # type: ignore
                value=log_entry.event_type.value if log_entry.event_type else await get_localized_master_message(session, interaction.guild_id, "generic.unknown", "Unknown", str(interaction.locale)), # type: ignore
                inline=True
            )
            if log_entry.turn_number is not None:
                embed.add_field(
                    name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.log_view.field_turn_number", "Turn", str(interaction.locale)), # type: ignore
                    value=str(log_entry.turn_number),
                    inline=True
                )
            if log_entry.location_id:
                embed.add_field(
                    name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.log_view.field_location_id", "Location ID", str(interaction.locale)), # type: ignore
                    value=str(log_entry.location_id),
                    inline=True
                )
            if log_entry.narrative_i18n:
                 narrative_text = get_localized_text(log_entry.narrative_i18n, str(interaction.locale))
                 if not narrative_text and isinstance(log_entry.narrative_i18n, dict): # type: ignore
                     narrative_text = log_entry.narrative_i18n.get(str(interaction.locale), log_entry.narrative_i18n.get("en", "N/A"))
                 if narrative_text not in formatted_description: # type: ignore
                    embed.add_field(
                        name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.log_view.field_narrative", "Narrative", str(interaction.locale)), # type: ignore
                        value=narrative_text, # type: ignore
                        inline=False
                    )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor log_view for guild {interaction.guild_id}: {e}")
            error_msg = await get_localized_master_message(
                session,
                interaction.guild_id, # type: ignore
                "master_generic.error_unexpected",
                default_template="An unexpected error occurred: {error}",
                locale=str(interaction.locale),
                error=str(e)
            )
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    @log_group.command(name="list", description="List StoryLog entries with optional filters.")
    @app_commands.describe(
        page="Page number to display.",
        limit="Number of entries per page.",
        event_type_filter="Filter by a specific event type.",
    )
    @app_commands.choices(event_type_filter=[
        app_commands.Choice(name="Player Action", value="PLAYER_ACTION"),
        app_commands.Choice(name="NPC Action", value="NPC_ACTION"),
        app_commands.Choice(name="System Event", value="SYSTEM_EVENT"),
        app_commands.Choice(name="Combat Start", value="COMBAT_START"),
        app_commands.Choice(name="Combat Action", value="COMBAT_ACTION"),
        app_commands.Choice(name="Combat End", value="COMBAT_END"),
        app_commands.Choice(name="Movement", value="MOVEMENT"),
        app_commands.Choice(name="Dialogue Start", value="DIALOGUE_START"),
        app_commands.Choice(name="Dialogue Line", value="DIALOGUE_LINE"),
        app_commands.Choice(name="Dialogue End", value="DIALOGUE_END"),
        app_commands.Choice(name="World Event Quests Generated", value="WORLD_EVENT_QUESTS_GENERATED"),
        app_commands.Choice(name="Quest Accepted", value="QUEST_ACCEPTED"),
        app_commands.Choice(name="Quest Step Completed", value="QUEST_STEP_COMPLETED"),
        app_commands.Choice(name="Quest Completed", value="QUEST_COMPLETED"),
        app_commands.Choice(name="Quest Failed", value="QUEST_FAILED"),
        app_commands.Choice(name="Item Acquired", value="ITEM_ACQUIRED"),
        app_commands.Choice(name="Item Used", value="ITEM_USED"),
        app_commands.Choice(name="Item Dropped", value="ITEM_DROPPED"),
        app_commands.Choice(name="Trade Initiated", value="TRADE_INITIATED"),
        app_commands.Choice(name="Trade Completed", value="TRADE_COMPLETED"),
        app_commands.Choice(name="Trade Item Bought", value="TRADE_ITEM_BOUGHT"),
        app_commands.Choice(name="Trade Item Sold", value="TRADE_ITEM_SOLD"),
        app_commands.Choice(name="Level Up", value="LEVEL_UP"),
        app_commands.Choice(name="XP Gained", value="XP_GAINED"),
        app_commands.Choice(name="Relationship Change", value="RELATIONSHIP_CHANGE"),
    ])
    async def log_list(
        self,
        interaction: discord.Interaction,
        page: app_commands.Range[int, 1] = 1,
        limit: app_commands.Range[int, 1, 100] = 10,
        event_type_filter: Optional[app_commands.Choice[str]] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        master_player, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player or not session:
            return
        processed_event_type: Optional[EventType] = None
        if event_type_filter:
            try:
                processed_event_type = EventType[event_type_filter.value.upper()]
            except KeyError:
                error_msg = await get_localized_master_message(
                    session, # type: ignore
                    interaction.guild_id, # type: ignore[arg-type]
                    "master_monitor.log_list.invalid_event_type",
                    default_template="Invalid event type: '{input_event_type}'. Please use a valid event type name (e.g., PLAYER_ACTION, COMBAT_START).",
                    locale=str(interaction.locale),
                    input_event_type=event_type_filter.name
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                if session: await session.close()
                return
        try:
            skip = (page - 1) * limit
            total_entries = await story_log_crud.count_by_guild_with_filters(
                session, guild_id=interaction.guild_id, event_type=processed_event_type, # type: ignore
            )
            log_entries = await story_log_crud.get_multi_by_guild_with_filters(
                session, guild_id=interaction.guild_id, skip=skip, limit=limit, event_type=processed_event_type, descending=True, # type: ignore
            )
            if not log_entries:
                no_entries_msg = await get_localized_master_message(
                    session, interaction.guild_id, "master_monitor.log_list.no_entries", default_template="No log entries found on page {page}.", locale=str(interaction.locale), page=page # type: ignore
                )
                await interaction.followup.send(no_entries_msg, ephemeral=True)
                return
            embed = discord.Embed(
                title=await get_localized_master_message(session, interaction.guild_id, "master_monitor.log_list.embed_title", "Story Log Entries", str(interaction.locale)), color=discord.Color.green() # type: ignore
            )
            description_parts = []
            for entry in log_entries:
                entry_line = await get_localized_master_message(
                    session, interaction.guild_id, "master_monitor.log_list.entry_format", default_template="{log_id}. {timestamp} - {event_type}: {details_preview}", locale=str(interaction.locale), log_id=entry.id, timestamp=discord.utils.format_dt(entry.timestamp, style='f'), event_type=entry.event_type.value, details_preview=str(entry.details_json)[:100] + "..." if entry.details_json and len(str(entry.details_json)) > 100 else str(entry.details_json) # type: ignore
                )
                description_parts.append(entry_line)
            embed.description = "\n".join(description_parts)
            total_pages = (total_entries + limit - 1) // limit
            footer_text_key = "master_monitor.log_list.footer_pagination_current" if total_pages > 0 else "master_monitor.log_list.footer_pagination_empty"
            embed.set_footer(text=await get_localized_master_message(
                session, interaction.guild_id, footer_text_key, default_template="Page {page}/{total_pages} ({total_entries} entries)" if total_pages > 0 else "No entries found.", locale=str(interaction.locale), page=page, total_pages=total_pages, total_entries=total_entries # type: ignore
            ))
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor log_list for guild {interaction.guild_id}: {e}")
            error_msg = await get_localized_master_message(
                session, interaction.guild_id, "master_generic.error_unexpected", default_template="An unexpected error occurred: {error}", locale=str(interaction.locale), error=str(e) # type: ignore
            )
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session: await session.close()

    worldstate_group = app_commands.Group(name="worldstate", description="Commands for monitoring WorldState entries (from RuleConfig).")

    @worldstate_group.command(name="get", description="Get a specific WorldState value by its key.")
    @app_commands.describe(key="The key of the WorldState entry (e.g., 'worldstate:main_quest:status').")
    async def worldstate_get(self, interaction: discord.Interaction, key: str):
        await interaction.response.defer(ephemeral=True)
        master_player, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player or not session: return
        try:
            rule_entry = await rule_config_crud.get_by_key(session, guild_id=interaction.guild_id, key=key) # type: ignore
            if not rule_entry:
                error_msg = await get_localized_master_message(session, interaction.guild_id, "master_monitor.worldstate_get.not_found", default_template="WorldState entry with key '{key}' not found.", locale=str(interaction.locale), key=key) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)
                return
            embed = discord.Embed(title=await get_localized_master_message(session, interaction.guild_id, "master_monitor.worldstate_get.embed_title", "WorldState Entry: {key}", str(interaction.locale), key=key), color=discord.Color.purple()) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.worldstate_get.field_value", "Value", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(rule_entry.value_json))[:1000]}\n```", inline=False) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.worldstate_get.field_description", "Description", str(interaction.locale)), value=rule_entry.description or na_text, inline=False) # type: ignore
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor worldstate_get for guild {interaction.guild_id}: {e}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_unexpected", default_template="An unexpected error occurred: {error}", locale=str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session: await session.close()

    @worldstate_group.command(name="list", description="List WorldState entries with optional prefix filter.")
    @app_commands.describe(page="Page number to display.", limit="Number of entries per page.", prefix="Filter by key prefix (e.g., 'worldstate:quests').")
    async def worldstate_list(self, interaction: discord.Interaction, page: app_commands.Range[int, 1] = 1, limit: app_commands.Range[int, 1, 50] = 10, prefix: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        master_player, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player or not session: return
        try:
            skip = (page - 1) * limit
            effective_prefix = prefix if prefix else "worldstate:"
            total_entries = await rule_config_crud.count_by_guild_and_prefix(session, guild_id=interaction.guild_id, prefix=effective_prefix) # type: ignore
            rule_entries = await rule_config_crud.get_multi_by_guild_and_prefix(session, guild_id=interaction.guild_id, prefix=effective_prefix, skip=skip, limit=limit) # type: ignore
            if not rule_entries:
                no_entries_msg = await get_localized_master_message(session, interaction.guild_id, "master_monitor.worldstate_list.no_entries", default_template="No WorldState entries found on page {page} with prefix '{prefix}'.", locale=str(interaction.locale), page=page, prefix=effective_prefix) # type: ignore
                await interaction.followup.send(no_entries_msg, ephemeral=True)
                return
            embed = discord.Embed(title=await get_localized_master_message(session, interaction.guild_id, "master_monitor.worldstate_list.embed_title", "WorldState Entries (Prefix: {prefix})", str(interaction.locale), prefix=effective_prefix), color=discord.Color.dark_purple()) # type: ignore
            description_parts = []
            for entry in rule_entries:
                value_preview_str = "None"
                if entry.value_json is not None: # Check if value_json is not None
                    value_preview_str = str(entry.value_json)
                    if len(value_preview_str) > 100:
                        value_preview_str = value_preview_str[:100] + "..."

                entry_line = await get_localized_master_message(session, interaction.guild_id, "master_monitor.worldstate_list.entry_format", default_template="{key_display}: {value_preview}", locale=str(interaction.locale), key_display=entry.key, value_preview=value_preview_str) # type: ignore
                description_parts.append(entry_line)
            embed.description = "\n".join(description_parts)
            total_pages = (total_entries + limit - 1) // limit
            footer_text_key = "master_monitor.worldstate_list.footer_pagination_current" if total_pages > 0 else "master_monitor.worldstate_list.footer_pagination_empty"
            embed.set_footer(text=await get_localized_master_message(session, interaction.guild_id, footer_text_key, default_template="Page {page}/{total_pages} ({total_entries} entries)" if total_pages > 0 else "No entries found with this prefix.", locale=str(interaction.locale), page=page, total_pages=total_pages, total_entries=total_entries)) # type: ignore
            await interaction.followup.send(embed=embed, ephemeral=True)
        except AttributeError as ae:
            logger.error(f"Missing CRUD method for RuleConfig prefix search: {ae}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_not_implemented", "This feature is not fully implemented yet.", str(interaction.locale)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor worldstate_list for guild {interaction.guild_id}: {e}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_unexpected", default_template="An unexpected error occurred: {error}", locale=str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session: await session.close()

    map_group = app_commands.Group(name="map", description="Commands for monitoring map and location information.")

    @map_group.command(name="list_locations", description="List all locations in the guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of entries per page.")
    async def map_list_locations(self, interaction: discord.Interaction, page: app_commands.Range[int, 1] = 1, limit: app_commands.Range[int, 1, 50] = 10):
        await interaction.response.defer(ephemeral=True)
        master_player, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player or not session: return
        try:
            skip = (page - 1) * limit
            total_entries = await location_crud.count(session, guild_id=interaction.guild_id) # type: ignore
            locations = await location_crud.get_multi(session, guild_id=interaction.guild_id, skip=skip, limit=limit) # type: ignore
            if not locations:
                no_entries_msg = await get_localized_master_message(session, interaction.guild_id, "master_monitor.map_list_locations.no_entries", default_template="No locations found on page {page}.", locale=str(interaction.locale), page=page) # type: ignore
                await interaction.followup.send(no_entries_msg, ephemeral=True)
                return
            embed = discord.Embed(title=await get_localized_master_message(session, interaction.guild_id, "master_monitor.map_list_locations.embed_title", "Locations", str(interaction.locale)), color=discord.Color.orange()) # type: ignore
            description_parts = []
            for loc in locations:
                loc_name = get_localized_text(loc.name_i18n, str(interaction.locale), loc.name_i18n.get("en", "N/A"))
                loc_static_id_display = loc.static_id or await get_localized_master_message(session, interaction.guild_id, "master_generic.na_short", "N/A", str(interaction.locale)) # type: ignore
                entry_line = await get_localized_master_message(session, interaction.guild_id, "master_monitor.map_list_locations.entry_format", default_template="{loc_id} ({loc_static_id}): {loc_name} ({loc_type})", locale=str(interaction.locale), loc_id=loc.id, loc_static_id=loc_static_id_display, loc_name=loc_name, loc_type=loc.type.value) # type: ignore
                description_parts.append(entry_line)
            embed.description = "\n".join(description_parts)
            total_pages = (total_entries + limit - 1) // limit
            footer_text_key = "master_monitor.map_list_locations.footer_pagination_current" if total_pages > 0 else "master_monitor.map_list_locations.footer_pagination_empty"
            embed.set_footer(text=await get_localized_master_message(session, interaction.guild_id, footer_text_key, default_template="Page {page}/{total_pages} ({total_entries} entries)" if total_pages > 0 else "No locations found.", locale=str(interaction.locale), page=page, total_pages=total_pages, total_entries=total_entries)) # type: ignore
            await interaction.followup.send(embed=embed, ephemeral=True)
        except AttributeError as ae:
            logger.error(f"Missing CRUD method for Location listing (count_by_guild or get_multi_by_guild): {ae}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_not_implemented", "This feature is not fully implemented yet.", str(interaction.locale)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor map_list_locations for guild {interaction.guild_id}: {e}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_unexpected", default_template="An unexpected error occurred: {error}", locale=str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session: await session.close()

    @map_group.command(name="view_location", description="View details of a specific location.")
    @app_commands.describe(identifier="The ID or static_id of the location.")
    async def map_view_location(self, interaction: discord.Interaction, identifier: str):
        await interaction.response.defer(ephemeral=True)
        master_player, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player or not session: return
        try:
            location: Optional[Location] = None
            if identifier.isdigit():
                location = await location_crud.get(session, id=int(identifier), guild_id=interaction.guild_id) # type: ignore
            if not location:
                location = await location_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=identifier) # type: ignore
            if not location:
                error_msg = await get_localized_master_message(session, interaction.guild_id, "master_monitor.map_view_location.not_found", default_template="Location with identifier '{identifier}' not found.", locale=str(interaction.locale), identifier=identifier) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)
                return
            loc_name = get_localized_text(location.name_i18n, str(interaction.locale), location.name_i18n.get("en", "N/A"))
            loc_desc = get_localized_text(location.descriptions_i18n, str(interaction.locale), location.descriptions_i18n.get("en", "N/A"))
            embed = discord.Embed(title=await get_localized_master_message(session, interaction.guild_id, "master_monitor.map_view_location.embed_title", "Location Details: {location_name}", str(interaction.locale), location_name=loc_name), description=loc_desc, color=discord.Color.dark_orange()) # type: ignore
            na_text = await get_localized_master_message(session, interaction.guild_id, "master_generic.na", "N/A", str(interaction.locale)) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.map_view_location.field_id", "ID", str(interaction.locale)), value=str(location.id), inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.map_view_location.field_static_id", "Static ID", str(interaction.locale)), value=location.static_id or na_text, inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.map_view_location.field_type", "Type", str(interaction.locale)), value=location.type.value, inline=True) # type: ignore
            if location.parent_location_id:
                 embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.map_view_location.field_parent_id", "Parent ID", str(interaction.locale)), value=str(location.parent_location_id), inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.map_view_location.field_coordinates", "Coordinates", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(location.coordinates_json))}\n```" if location.coordinates_json else na_text, inline=False) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.map_view_location.field_neighbors", "Neighbors", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(location.neighbor_locations_json))}\n```" if location.neighbor_locations_json else na_text, inline=False) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.map_view_location.field_generated_details", "Generated Details", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(location.generated_details_json))[:1000]}\n```" if location.generated_details_json else na_text, inline=False) # type: ignore
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor map_view_location for guild {interaction.guild_id}: {e}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_unexpected", default_template="An unexpected error occurred: {error}", locale=str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session: await session.close()

    entities_group = app_commands.Group(name="entities", description="Commands for monitoring various game entities.")

    @entities_group.command(name="list_players", description="List all players in the guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of entries per page.")
    async def entities_list_players(self, interaction: discord.Interaction, page: app_commands.Range[int, 1] = 1, limit: app_commands.Range[int, 1, 50] = 10):
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session: return
        try:
            skip = (page - 1) * limit
            total_entries = await player_crud.count(session, guild_id=interaction.guild_id) # type: ignore
            players = await player_crud.get_multi(session, guild_id=interaction.guild_id, skip=skip, limit=limit) # type: ignore
            if not players:
                no_entries_msg = await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_list_players.no_entries", default_template="No players found on page {page}.", locale=str(interaction.locale), page=page) # type: ignore
                await interaction.followup.send(no_entries_msg, ephemeral=True)
                return
            embed = discord.Embed(title=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_list_players.embed_title", "Players", str(interaction.locale)), color=discord.Color.gold()) # type: ignore
            description_parts = []
            for p in players:
                player_name_loc = p.name
                entry_line = await get_localized_master_message(
                    session, interaction.guild_id, "master_monitor.entities_list_players.entry_format", default_template="ID: {player_db_id} (Discord: <@{player_discord_id}>) - {player_name_loc} (Lvl: {player_level})", locale=str(interaction.locale), player_db_id=p.id, player_discord_id=p.discord_id, player_name_loc=player_name_loc, player_level=p.level # type: ignore
                )
                description_parts.append(entry_line)
            embed.description = "\n".join(description_parts)
            total_pages = (total_entries + limit - 1) // limit
            footer_text_key = "master_monitor.entities_list_players.footer_pagination_current" if total_pages > 0 else "master_monitor.entities_list_players.footer_pagination_empty"
            embed.set_footer(text=await get_localized_master_message(session, interaction.guild_id, footer_text_key, default_template="Page {page}/{total_pages} ({total_entries} entries)" if total_pages > 0 else "No players found.", locale=str(interaction.locale), page=page, total_pages=total_pages, total_entries=total_entries)) # type: ignore
            await interaction.followup.send(embed=embed, ephemeral=True)
        except AttributeError as ae:
            logger.error(f"Missing CRUD method for Player listing (count_by_guild or get_multi_by_guild): {ae}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_not_implemented", "This feature is not fully implemented yet.", str(interaction.locale)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_list_players for guild {interaction.guild_id}: {e}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_unexpected", default_template="An unexpected error occurred: {error}", locale=str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session: await session.close()

    @entities_group.command(name="view_player", description="View details of a specific player.")
    @app_commands.describe(player_id="The database ID of the player.")
    async def entities_view_player(self, interaction: discord.Interaction, player_id: int):
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session: return
        try:
            player = await player_crud.get(session, id=player_id, guild_id=interaction.guild_id) # type: ignore
            if not player:
                error_msg = await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_player.not_found", default_template="Player with ID {player_id} not found.", locale=str(interaction.locale), player_id=player_id) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)
                return
            player_name_loc = player.name
            na_text = await get_localized_master_message(session, interaction.guild_id, "master_generic.na", "N/A", str(interaction.locale)) # type: ignore
            embed = discord.Embed(
                title=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_player.embed_title", "Player Details: {player_name}", str(interaction.locale), player_name=player_name_loc), # type: ignore
                description=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_player.no_description", "No description available.", str(interaction.locale)), color=discord.Color.dark_gold() # type: ignore
            )
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_player.field_db_id", "DB ID", str(interaction.locale)), value=str(player.id), inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_player.field_discord_user", "Discord User", str(interaction.locale)), value=f"<@{player.discord_id}> ({player.discord_id})", inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_player.field_level", "Level", str(interaction.locale)), value=str(player.level), inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_player.field_xp", "XP", str(interaction.locale)), value=str(player.xp), inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_player.field_unspent_xp", "Unspent XP", str(interaction.locale)), value=str(player.unspent_xp), inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_player.field_current_status", "Status", str(interaction.locale)), value=player.current_status.value if player.current_status else na_text, inline=True) # type: ignore
            if player.current_location_id:
                loc = await location_crud.get(session, id=player.current_location_id, guild_id=interaction.guild_id)
                loc_name_display = await get_localized_master_message(session, interaction.guild_id, "master_generic.unknown_location", "Unknown Location", str(interaction.locale)) # type: ignore
                if loc:
                    loc_name_display = get_localized_text(loc.name_i18n, str(interaction.locale), loc.name_i18n.get("en", f"ID: {loc.id}"))
                embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_player.field_location", "Location", str(interaction.locale)), value=f"{loc_name_display} (ID: {player.current_location_id})", inline=True) # type: ignore
            if player.current_party_id:
                party = await party_crud.get(session, id=player.current_party_id, guild_id=interaction.guild_id)
                party_name_display = await get_localized_master_message(session, interaction.guild_id, "master_generic.unknown_party", "Unknown Party", str(interaction.locale)) # type: ignore
                if party:
                     party_name_display = party.name
                embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_player.field_party", "Party", str(interaction.locale)), value=f"{party_name_display} (ID: {player.current_party_id})", inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_player.field_attributes", "Attributes", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(player.attributes_json))}\n```" if player.attributes_json else na_text, inline=False) # type: ignore
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_view_player for guild {interaction.guild_id}: {e}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_unexpected", default_template="An unexpected error occurred: {error}", locale=str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session: await session.close()

    @entities_group.command(name="list_npcs", description="List all Generated NPCs in the guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of entries per page.")
    async def entities_list_npcs(self, interaction: discord.Interaction, page: app_commands.Range[int, 1] = 1, limit: app_commands.Range[int, 1, 50] = 10):
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session: return
        try:
            skip = (page - 1) * limit
            total_entries = await npc_crud.count(session, guild_id=interaction.guild_id) # type: ignore
            npcs = await npc_crud.get_multi(session, guild_id=interaction.guild_id, skip=skip, limit=limit) # type: ignore
            if not npcs:
                no_entries_msg = await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_list_npcs.no_entries", default_template="No NPCs found on page {page}.", locale=str(interaction.locale), page=page) # type: ignore
                await interaction.followup.send(no_entries_msg, ephemeral=True)
                return
            embed = discord.Embed(title=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_list_npcs.embed_title", "Generated NPCs", str(interaction.locale)), color=discord.Color.teal()) # type: ignore
            description_parts = []
            for npc_obj in npcs:
                npc_name = get_localized_text(npc_obj.name_i18n, str(interaction.locale), npc_obj.name_i18n.get("en", "N/A"))
                na_short_text = await get_localized_master_message(session, interaction.guild_id, "master_generic.na_short", "N/A", str(interaction.locale)) # type: ignore
                npc_static_id_display = npc_obj.static_id or na_short_text
                entry_line = await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_list_npcs.entry_format", default_template="ID: {npc_db_id} (Static: {npc_static_id}) - {npc_name_loc}", locale=str(interaction.locale), npc_db_id=npc_obj.id, npc_static_id=npc_static_id_display, npc_name_loc=npc_name) # type: ignore
                description_parts.append(entry_line)
            embed.description = "\n".join(description_parts)
            total_pages = (total_entries + limit - 1) // limit
            footer_text_key = "master_monitor.entities_list_npcs.footer_pagination_current" if total_pages > 0 else "master_monitor.entities_list_npcs.footer_pagination_empty"
            embed.set_footer(text=await get_localized_master_message(session, interaction.guild_id, footer_text_key, default_template="Page {page}/{total_pages} ({total_entries} entries)" if total_pages > 0 else "No NPCs found.", locale=str(interaction.locale), page=page, total_pages=total_pages, total_entries=total_entries)) # type: ignore
            await interaction.followup.send(embed=embed, ephemeral=True)
        except AttributeError as ae:
            logger.error(f"Missing CRUD method for GeneratedNpc listing (count_by_guild or get_multi_by_guild): {ae}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_not_implemented", "This feature is not fully implemented yet.", str(interaction.locale)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_list_npcs for guild {interaction.guild_id}: {e}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_unexpected", default_template="An unexpected error occurred: {error}", locale=str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session: await session.close()

    @entities_group.command(name="view_npc", description="View details of a specific Generated NPC.")
    @app_commands.describe(npc_id="The database ID of the Generated NPC.")
    async def entities_view_npc(self, interaction: discord.Interaction, npc_id: int):
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session: return
        try:
            npc_obj = await npc_crud.get(session, id=npc_id, guild_id=interaction.guild_id) # type: ignore
            if not npc_obj:
                error_msg = await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_npc.not_found", default_template="NPC with ID {npc_id} not found.", locale=str(interaction.locale), npc_id=npc_id) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)
                return
            npc_name = get_localized_text(npc_obj.name_i18n, str(interaction.locale), npc_obj.name_i18n.get("en", "N/A"))
            npc_desc = get_localized_text(npc_obj.description_i18n, str(interaction.locale), npc_obj.description_i18n.get("en", "N/A"))
            na_text = await get_localized_master_message(session, interaction.guild_id, "master_generic.na", "N/A", str(interaction.locale)) # type: ignore
            embed = discord.Embed(title=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_npc.embed_title", "NPC Details: {npc_name}", str(interaction.locale), npc_name=npc_name), description=npc_desc, color=discord.Color.dark_teal()) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_npc.field_db_id", "DB ID", str(interaction.locale)), value=str(npc_obj.id), inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_npc.field_static_id", "Static ID", str(interaction.locale)), value=npc_obj.static_id or na_text, inline=True) # type: ignore
            if npc_obj.current_location_id:
                loc = await location_crud.get(session, id=npc_obj.current_location_id, guild_id=interaction.guild_id)
                loc_name_display = await get_localized_master_message(session, interaction.guild_id, "master_generic.unknown_location", "Unknown Location", str(interaction.locale)) # type: ignore
                if loc:
                    loc_name_display = get_localized_text(loc.name_i18n, str(interaction.locale), loc.name_i18n.get("en", f"ID: {loc.id}"))
                embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_npc.field_location", "Location", str(interaction.locale)), value=f"{loc_name_display} (ID: {npc_obj.current_location_id})", inline=True) # type: ignore
            if npc_obj.faction_id:
                embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_npc.field_faction_id", "Faction ID", str(interaction.locale)), value=str(npc_obj.faction_id), inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_npc.field_properties", "Properties", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(npc_obj.properties_json))[:1000]}\n```" if npc_obj.properties_json else na_text, inline=False) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_npc.field_ai_metadata", "AI Metadata", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(npc_obj.ai_metadata_json))[:1000]}\n```" if npc_obj.ai_metadata_json else na_text, inline=False) # type: ignore
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_view_npc for guild {interaction.guild_id}: {e}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_unexpected", default_template="An unexpected error occurred: {error}", locale=str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session: await session.close()

    @entities_group.command(name="list_parties", description="List all parties in the guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of entries per page.")
    async def entities_list_parties(self, interaction: discord.Interaction, page: app_commands.Range[int, 1] = 1, limit: app_commands.Range[int, 1, 50] = 10):
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session: return
        try:
            skip = (page - 1) * limit
            total_entries = await party_crud.count(session, guild_id=interaction.guild_id) # type: ignore
            parties = await party_crud.get_multi(session, guild_id=interaction.guild_id, skip=skip, limit=limit) # type: ignore
            if not parties:
                no_entries_msg = await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_list_parties.no_entries", default_template="No parties found on page {page}.", locale=str(interaction.locale), page=page) # type: ignore
                await interaction.followup.send(no_entries_msg, ephemeral=True)
                return
            embed = discord.Embed(title=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_list_parties.embed_title", "Parties", str(interaction.locale)), color=discord.Color.blue()) # type: ignore
            description_parts = []
            for party_obj in parties:
                party_name = party_obj.name
                leader_name = await get_localized_master_message(session, interaction.guild_id, "master_generic.na_short", "N/A", str(interaction.locale)) # type: ignore
                if party_obj.leader:
                    leader_name = party_obj.leader.name
                member_count = len(party_obj.players) if party_obj.players else 0
                entry_line = await get_localized_master_message(
                    session, interaction.guild_id, "master_monitor.entities_list_parties.entry_format", default_template="ID: {party_db_id} - {party_name_loc} (Leader: {leader_name}, Members: {member_count})", locale=str(interaction.locale), party_db_id=party_obj.id, party_name_loc=party_name, leader_name=leader_name, member_count=member_count # type: ignore
                )
                description_parts.append(entry_line)
            embed.description = "\n".join(description_parts)
            total_pages = (total_entries + limit - 1) // limit
            footer_text_key = "master_monitor.entities_list_parties.footer_pagination_current" if total_pages > 0 else "master_monitor.entities_list_parties.footer_pagination_empty"
            embed.set_footer(text=await get_localized_master_message(session, interaction.guild_id, footer_text_key, default_template="Page {page}/{total_pages} ({total_entries} entries)" if total_pages > 0 else "No parties found.", locale=str(interaction.locale), page=page, total_pages=total_pages, total_entries=total_entries)) # type: ignore
            await interaction.followup.send(embed=embed, ephemeral=True)
        except AttributeError as ae:
            logger.error(f"Missing CRUD method for Party listing (count_by_guild or get_multi_by_guild): {ae}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_not_implemented", "This feature is not fully implemented yet.", str(interaction.locale)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_list_parties for guild {interaction.guild_id}: {e}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_unexpected", default_template="An unexpected error occurred: {error}", locale=str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session: await session.close()

    @entities_group.command(name="view_party", description="View details of a specific party.")
    @app_commands.describe(party_id="The database ID of the party.")
    async def entities_view_party(self, interaction: discord.Interaction, party_id: int):
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session: return
        try:
            party = await party_crud.get(session, id=party_id, guild_id=interaction.guild_id) # type: ignore
            if not party:
                error_msg = await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_party.not_found", default_template="Party with ID {party_id} not found.", locale=str(interaction.locale), party_id=party_id) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)
                return
            party_name_loc = party.name
            na_text = await get_localized_master_message(session, interaction.guild_id, "master_generic.na", "N/A", str(interaction.locale)) # type: ignore
            embed = discord.Embed(title=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_party.embed_title", "Party Details: {party_name}", str(interaction.locale), party_name=party_name_loc), color=discord.Color.dark_blue()) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_party.field_db_id", "DB ID", str(interaction.locale)), value=str(party.id), inline=True) # type: ignore
            leader_name_display = na_text
            if party.leader:
                leader_name_loc = party.leader.name
                leader_name_display = f"{leader_name_loc} (<@{party.leader.discord_id}>)"
            elif party.leader_player_id:
                leader_name_display = f"ID: {party.leader_player_id}"
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_party.field_leader", "Leader", str(interaction.locale)), value=leader_name_display, inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_party.field_current_status", "Status", str(interaction.locale)), value=party.current_turn_status.value if party.current_turn_status else na_text, inline=True) # type: ignore
            member_list = []
            if party.players:
                for member in party.players:
                    member_name_loc = member.name
                    member_list.append(f"{member_name_loc} (<@{member.discord_id}>, ID: {member.id})")
            members_value = "\n".join(member_list) if member_list else await get_localized_master_message(session, interaction.guild_id, "master_generic.none", "None", str(interaction.locale)) # type: ignore
            if len(members_value) > 1024: members_value = members_value[:1020] + "..."
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_party.field_members", "Members ({count})", str(interaction.locale), count=len(member_list)), value=members_value, inline=False) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_party.field_properties", "Properties", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(party.properties_json))[:1000]}\n```" if party.properties_json else na_text, inline=False) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_party.field_created_at", "Created At", str(interaction.locale)), value=discord.utils.format_dt(party.created_at), inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_party.field_updated_at", "Updated At", str(interaction.locale)), value=discord.utils.format_dt(party.updated_at), inline=True) # type: ignore
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_view_party for guild {interaction.guild_id}: {e}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_unexpected", default_template="An unexpected error occurred: {error}", locale=str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session: await session.close()

    @entities_group.command(name="list_global_npcs", description="List all Global NPCs in the guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of entries per page.")
    async def entities_list_global_npcs(self, interaction: discord.Interaction, page: app_commands.Range[int, 1] = 1, limit: app_commands.Range[int, 1, 50] = 10):
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session: return
        try:
            skip = (page - 1) * limit
            total_entries = await global_npc_crud.count(session, guild_id=interaction.guild_id) # type: ignore
            global_npcs = await global_npc_crud.get_multi(session, guild_id=interaction.guild_id, skip=skip, limit=limit) # type: ignore
            if not global_npcs:
                no_entries_msg = await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_list_global_npcs.no_entries", default_template="No Global NPCs found on page {page}.", locale=str(interaction.locale), page=page) # type: ignore
                await interaction.followup.send(no_entries_msg, ephemeral=True)
                return
            embed = discord.Embed(title=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_list_global_npcs.embed_title", "Global NPCs", str(interaction.locale)), color=discord.Color.dark_green()) # type: ignore
            description_parts = []
            for gn_obj in global_npcs:
                gn_name = get_localized_text(gn_obj.name_i18n, str(interaction.locale), gn_obj.name_i18n.get("en", "N/A"))
                gn_static_id_display = gn_obj.static_id or await get_localized_master_message(session, interaction.guild_id, "master_generic.na_short", "N/A", str(interaction.locale)) # type: ignore
                entry_line = await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_list_global_npcs.entry_format", default_template="ID: {gn_db_id} (Static: {gn_static_id}) - {gn_name_loc}", locale=str(interaction.locale), gn_db_id=gn_obj.id, gn_static_id=gn_static_id_display, gn_name_loc=gn_name) # type: ignore
                description_parts.append(entry_line)
            embed.description = "\n".join(description_parts)
            total_pages = (total_entries + limit - 1) // limit
            footer_text_key = "master_monitor.entities_list_global_npcs.footer_pagination_current" if total_pages > 0 else "master_monitor.entities_list_global_npcs.footer_pagination_empty"
            embed.set_footer(text=await get_localized_master_message(session, interaction.guild_id, footer_text_key, default_template="Page {page}/{total_pages} ({total_entries} entries)" if total_pages > 0 else "No Global NPCs found.", locale=str(interaction.locale), page=page, total_pages=total_pages, total_entries=total_entries)) # type: ignore
            await interaction.followup.send(embed=embed, ephemeral=True)
        except AttributeError as ae:
            logger.error(f"Missing CRUD method for GlobalNpc listing (count_by_guild or get_multi_by_guild): {ae}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_not_implemented", "This feature is not fully implemented yet.", str(interaction.locale)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_list_global_npcs for guild {interaction.guild_id}: {e}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_unexpected", default_template="An unexpected error occurred: {error}", locale=str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session: await session.close()

    @entities_group.command(name="view_global_npc", description="View details of a specific Global NPC.")
    @app_commands.describe(global_npc_id="The database ID of the Global NPC.")
    async def entities_view_global_npc(self, interaction: discord.Interaction, global_npc_id: int):
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session: return
        try:
            gn_obj = await global_npc_crud.get(session, id=global_npc_id, guild_id=interaction.guild_id) # type: ignore
            if not gn_obj:
                error_msg = await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_global_npc.not_found", default_template="Global NPC with ID {global_npc_id} not found.", locale=str(interaction.locale), global_npc_id=global_npc_id) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)
                return
            gn_name = get_localized_text(gn_obj.name_i18n, str(interaction.locale))
            if not gn_name: gn_name = gn_obj.static_id
            na_text = await get_localized_master_message(session, interaction.guild_id, "master_generic.na", "N/A", str(interaction.locale)) # type: ignore
            gn_desc = get_localized_text(gn_obj.description_i18n, str(interaction.locale)) if gn_obj.description_i18n else na_text
            embed = discord.Embed(title=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_global_npc.embed_title", "Global NPC Details: {gn_name}", str(interaction.locale), gn_name=gn_name), description=gn_desc, color=discord.Color.dark_green()) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_global_npc.field_db_id", "DB ID", str(interaction.locale)), value=str(gn_obj.id), inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_global_npc.field_static_id", "Static ID", str(interaction.locale)), value=gn_obj.static_id or na_text, inline=True) # type: ignore
            if gn_obj.current_location_id:
                loc = await location_crud.get(session, id=gn_obj.current_location_id, guild_id=interaction.guild_id)
                loc_name_display = await get_localized_master_message(session, interaction.guild_id, "master_generic.unknown_location", "Unknown Location", str(interaction.locale)) # type: ignore
                if loc:
                    assert loc is not None # Help Pyright understand loc is not None here
                    current_name_i18n = loc.name_i18n # This should be Dict[str, str]
                    loc_name_display_primary = get_localized_text(current_name_i18n, str(interaction.locale))

                    if loc_name_display_primary:
                        loc_name_display = loc_name_display_primary
                    else: # Fallback if primary language text is empty
                        # loc.name_i18n is Dict[str,str] by model definition
                        loc_name_display_en = None # Initialize
                        if current_name_i18n: # Explicitly check if current_name_i18n is not None
                            assert current_name_i18n is not None # For Pyright's benefit, though model makes it non-nullable
                            loc_name_display_en = current_name_i18n.get("en") # type: ignore[reportOptionalMemberAccess]
                        if loc_name_display_en:
                            loc_name_display = loc_name_display_en
                        elif loc.static_id: # Further fallback to static_id
                            loc_name_display = loc.static_id
                        else: # Ultimate fallback
                            loc_name_display = f"ID: {loc.id}"
                embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_global_npc.field_location", "Location", str(interaction.locale)), value=f"{loc_name_display} (ID: {gn_obj.current_location_id})", inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_global_npc.field_properties", "Properties", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(gn_obj.properties_json))[:1000]}\n```" if gn_obj.properties_json else na_text, inline=False) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_global_npc.field_ai_rules_override", "AI Rules Override", str(interaction.locale)), value=na_text, inline=False) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_global_npc.field_created_at", "Created At", str(interaction.locale)), value=discord.utils.format_dt(gn_obj.created_at), inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_global_npc.field_updated_at", "Updated At", str(interaction.locale)), value=discord.utils.format_dt(gn_obj.updated_at), inline=True) # type: ignore
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_view_global_npc for guild {interaction.guild_id}: {e}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_unexpected", default_template="An unexpected error occurred: {error}", locale=str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session: await session.close()

    @entities_group.command(name="list_mobile_groups", description="List all Mobile Groups in the guild.")
    @app_commands.describe(page="Page number to display.", limit="Number of entries per page.")
    async def entities_list_mobile_groups(self, interaction: discord.Interaction, page: app_commands.Range[int, 1] = 1, limit: app_commands.Range[int, 1, 50] = 10):
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session: return
        try:
            skip = (page - 1) * limit
            total_entries = await mobile_group_crud.count(session, guild_id=interaction.guild_id) # type: ignore
            mobile_groups = await mobile_group_crud.get_multi(session, guild_id=interaction.guild_id, skip=skip, limit=limit) # type: ignore
            if not mobile_groups:
                no_entries_msg = await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_list_mobile_groups.no_entries", default_template="No Mobile Groups found on page {page}.", locale=str(interaction.locale), page=page) # type: ignore
                await interaction.followup.send(no_entries_msg, ephemeral=True)
                return
            embed = discord.Embed(title=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_list_mobile_groups.embed_title", "Mobile Groups", str(interaction.locale)), color=discord.Color.purple()) # type: ignore
            description_parts = []
            for mg_obj in mobile_groups:
                mg_name = get_localized_text(mg_obj.name_i18n, str(interaction.locale), mg_obj.name_i18n.get("en", "N/A"))
                mg_static_id_display = mg_obj.static_id or await get_localized_master_message(session, interaction.guild_id, "master_generic.na_short", "N/A", str(interaction.locale)) # type: ignore
                entry_line = await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_list_mobile_groups.entry_format", default_template="ID: {mg_db_id} (Static: {mg_static_id}) - {mg_name_loc}", locale=str(interaction.locale), mg_db_id=mg_obj.id, mg_static_id=mg_static_id_display, mg_name_loc=mg_name) # type: ignore
                description_parts.append(entry_line)
            embed.description = "\n".join(description_parts)
            total_pages = (total_entries + limit - 1) // limit
            footer_text_key = "master_monitor.entities_list_mobile_groups.footer_pagination_current" if total_pages > 0 else "master_monitor.entities_list_mobile_groups.footer_pagination_empty"
            embed.set_footer(text=await get_localized_master_message(session, interaction.guild_id, footer_text_key, default_template="Page {page}/{total_pages} ({total_entries} entries)" if total_pages > 0 else "No Mobile Groups found.", locale=str(interaction.locale), page=page, total_pages=total_pages, total_entries=total_entries)) # type: ignore
            await interaction.followup.send(embed=embed, ephemeral=True)
        except AttributeError as ae:
            logger.error(f"Missing CRUD method for MobileGroup listing (count_by_guild or get_multi_by_guild): {ae}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_not_implemented", "This feature is not fully implemented yet.", str(interaction.locale)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_list_mobile_groups for guild {interaction.guild_id}: {e}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_unexpected", default_template="An unexpected error occurred: {error}", locale=str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session: await session.close()

    @entities_group.command(name="view_mobile_group", description="View details of a specific Mobile Group.")
    @app_commands.describe(mobile_group_id="The database ID of the Mobile Group.")
    async def entities_view_mobile_group(self, interaction: discord.Interaction, mobile_group_id: int):
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session: return
        try:
            mg_obj = await mobile_group_crud.get(session, id=mobile_group_id, guild_id=interaction.guild_id) # type: ignore
            if not mg_obj:
                error_msg = await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_mobile_group.not_found", default_template="Mobile Group with ID {mobile_group_id} not found.", locale=str(interaction.locale), mobile_group_id=mobile_group_id) # type: ignore
                await interaction.followup.send(error_msg, ephemeral=True)
                return
            mg_name = get_localized_text(mg_obj.name_i18n, str(interaction.locale), mg_obj.name_i18n.get("en", "N/A"))
            mg_desc = get_localized_text(mg_obj.description_i18n, str(interaction.locale), mg_obj.description_i18n.get("en", "N/A"))
            na_text = await get_localized_master_message(session, interaction.guild_id, "master_generic.na", "N/A", str(interaction.locale)) # type: ignore
            embed = discord.Embed(title=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_mobile_group.embed_title", "Mobile Group Details: {mg_name}", str(interaction.locale), mg_name=mg_name), description=mg_desc, color=discord.Color.dark_purple()) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_mobile_group.field_db_id", "DB ID", str(interaction.locale)), value=str(mg_obj.id), inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_mobile_group.field_static_id", "Static ID", str(interaction.locale)), value=mg_obj.static_id or na_text, inline=True) # type: ignore
            if mg_obj.current_location_id:
                loc = await location_crud.get(session, id=mg_obj.current_location_id, guild_id=interaction.guild_id)
                loc_name_display = await get_localized_master_message(session, interaction.guild_id, "master_generic.unknown_location", "Unknown Location", str(interaction.locale)) # type: ignore
                if loc:
                    loc_name_display = get_localized_text(loc.name_i18n, str(interaction.locale), loc.name_i18n.get("en", f"ID: {loc.id}"))
                embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_mobile_group.field_location", "Location", str(interaction.locale)), value=f"{loc_name_display} (ID: {mg_obj.current_location_id})", inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_mobile_group.field_composition", "Composition (Members Definition)", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(mg_obj.members_definition_json))[:1000]}\n```" if mg_obj.members_definition_json else na_text, inline=False) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_mobile_group.field_properties", "Properties", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(mg_obj.properties_json))[:1000]}\n```" if mg_obj.properties_json else na_text, inline=False) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_mobile_group.field_ai_rules_override", "AI Rules Override", str(interaction.locale)), value=na_text, inline=False) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_mobile_group.field_ai_metadata", "AI Metadata", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(mg_obj.ai_metadata_json))[:1000]}\n```" if mg_obj.ai_metadata_json else na_text, inline=False) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_mobile_group.field_created_at", "Created At", str(interaction.locale)), value=discord.utils.format_dt(mg_obj.created_at), inline=True) # type: ignore
            embed.add_field(name=await get_localized_master_message(session, interaction.guild_id, "master_monitor.entities_view_mobile_group.field_updated_at", "Updated At", str(interaction.locale)), value=discord.utils.format_dt(mg_obj.updated_at), inline=True) # type: ignore
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_view_mobile_group for guild {interaction.guild_id}: {e}")
            error_msg = await get_localized_master_message(session, interaction.guild_id, "master_generic.error_unexpected", default_template="An unexpected error occurred: {error}", locale=str(interaction.locale), error=str(e)) # type: ignore
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session: await session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(MasterMonitoringCog(bot))
    logger.info("MasterMonitoringCog added to bot.")


