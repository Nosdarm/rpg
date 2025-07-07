import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

# Ensure story_log_crud is imported from the correct location
from src.core.crud.crud_story_log import story_log_crud
from src.bot.utils import parse_json_parameter, ensure_guild_configured_and_get_session, get_master_player_from_interaction
from src.core.crud import guild_crud, player_crud, npc_crud, party_crud, location_crud, rule_config_crud # Removed story_log_crud from here as it's specifically imported
from src.core.crud.crud_global_npc import global_npc_crud
from src.core.crud.crud_mobile_group import mobile_group_crud
from src.core.localization_utils import get_localized_text, get_localized_message_template
from src.core.report_formatter import format_story_log_entry_for_master_display # Placeholder, might need adjustment
from src.models import Player, GeneratedNpc, Party, Location, StoryLog, RuleConfig, GlobalNpc, MobileGroup, EventType, RelationshipEntityType # Added RelationshipEntityType
from src.config.settings import BOT_PREFIX

logger = logging.getLogger(__name__)

# Placeholder removed as story_log_crud is now properly imported.
# if not hasattr(story_log_crud, 'get_multi_by_guild_with_filters'):
#     logger.error("story_log_crud does not have get_multi_by_guild_with_filters. Monitoring Cog may not work correctly.")


@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
class MasterMonitoringCog(commands.GroupCog, name="master_monitor", description="Master commands for monitoring game state and history."):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()
        logger.info("MasterMonitoringCog initialized.")

    async def cog_check(self, interaction: discord.Interaction) -> bool:
        # Basic check, can be expanded (e.g., check for a specific Master role)
        return interaction.user.guild_permissions.administrator

    # --- Log Monitoring Subgroup ---
    log_group = app_commands.Group(name="log", description="Commands for monitoring StoryLog entries.")

    @log_group.command(name="view", description="View a specific StoryLog entry by its ID.")
    @app_commands.describe(log_id="The ID of the StoryLog entry to view.")
    async def log_view(self, interaction: discord.Interaction, log_id: int):
        """Views a specific StoryLog entry."""
        await interaction.response.defer(ephemeral=True)
        master_player, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player or not session:
            return

        try:
            log_entry = await story_log_crud.get(session, id=log_id, guild_id=interaction.guild_id) # type: ignore

            if not log_entry:
                error_msg = get_localized_text(
                    "master_monitor.log_view.not_found",
                    str(interaction.locale),
                    {"log_id": log_id}
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            # Formatting the log entry using the new formatter
            formatted_description = await format_story_log_entry_for_master_display(
                session=session,
                log_entry=log_entry,
                language=str(interaction.locale)
                # fallback_language can be specified if needed, defaults to "en"
            )

            embed = discord.Embed(
                title=get_localized_text(
                    "master_monitor.log_view.embed_title",
                    str(interaction.locale),
                    default="Story Log Entry Details - ID: {log_id}",
                    log_id=log_entry.id
                ),
                description=formatted_description,
                color=discord.Color.blue()
            )

            # Add some key fields that might not be in the formatted_description or are good for quick view
            embed.add_field(
                name=get_localized_text("master_monitor.log_view.field_timestamp", str(interaction.locale), default="Timestamp"),
                value=discord.utils.format_dt(log_entry.timestamp),
                inline=True
            )
            embed.add_field(
                name=get_localized_text("master_monitor.log_view.field_event_type", str(interaction.locale), default="Event Type"),
                value=log_entry.event_type.value if log_entry.event_type else get_localized_text("generic.unknown", str(interaction.locale), default="Unknown"),
                inline=True
            )

            if log_entry.turn_number is not None:
                embed.add_field(
                    name=get_localized_text("master_monitor.log_view.field_turn_number", str(interaction.locale), default="Turn"),
                    value=str(log_entry.turn_number),
                    inline=True
                )

            if log_entry.location_id:
                # Potentially fetch location name here if formatter doesn't include it prominently
                # For now, just ID is fine as formatter should handle name if relevant for the event type
                embed.add_field(
                    name=get_localized_text("master_monitor.log_view.field_location_id", str(interaction.locale), default="Location ID"),
                    value=str(log_entry.location_id),
                    inline=True
                )

            # Optionally, add raw JSON details if desired, but formatted_description should be primary
            # embed.add_field(name="Raw Details (JSON)", value=f"```json\n{discord.utils.escape_markdown(str(log_entry.details_json))[:900]}\n```", inline=False)
            # embed.add_field(name="Raw Entity IDs (JSON)", value=f"```json\n{discord.utils.escape_markdown(str(log_entry.entity_ids_json))[:900]}\n```", inline=False)

            if log_entry.narrative_i18n:
                 narrative_text = get_localized_text(log_entry.narrative_i18n, str(interaction.locale))
                 if not narrative_text and isinstance(log_entry.narrative_i18n, dict):
                     narrative_text = log_entry.narrative_i18n.get(str(interaction.locale), log_entry.narrative_i18n.get("en", "N/A"))

                 # Check if narrative text is already part of formatted_description to avoid redundancy
                 # This is a simple check; more sophisticated checks might be needed if formats vary widely.
                 if narrative_text not in formatted_description:
                    embed.add_field(
                        name=get_localized_text("master_monitor.log_view.field_narrative", str(interaction.locale), default="Narrative"),
                        value=narrative_text,
                        inline=False
                    )


            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"Error in /master_monitor log_view for guild {interaction.guild_id}: {e}")
            error_msg = get_localized_text("master_generic.error_unexpected", str(interaction.locale), {"error": str(e)})
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    # TODO: Implement /master_monitor log list - Partially done below

    @log_group.command(name="list", description="List StoryLog entries with optional filters.")
    @app_commands.describe(
        page="Page number to display.",
        limit="Number of entries per page.",
        event_type_filter="Filter by a specific event type.",
        # TODO: Add more filters like entity_id, entity_type, turn_number, timestamps
    )
    async def log_list(
        self,
        interaction: discord.Interaction,
        page: app_commands.Range[int, 1] = 1,
        limit: app_commands.Range[int, 1, 100] = 10,
        event_type_filter: Optional[EventType] = None, # Directly using EventType from models
    ):
        """Lists StoryLog entries with pagination and optional filters."""
        await interaction.response.defer(ephemeral=True)
        master_player, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player or not session:
            return

        try:
            skip = (page - 1) * limit
            total_entries = await story_log_crud.count_by_guild_with_filters(
                session,
                guild_id=interaction.guild_id,
                event_type=event_type_filter,
            )
            log_entries = await story_log_crud.get_multi_by_guild_with_filters(
                session,
                guild_id=interaction.guild_id,
                skip=skip,
                limit=limit,
                event_type=event_type_filter,
                descending=True, # Show newest first
            )

            if not log_entries:
                no_entries_msg = get_localized_text(
                    "master_monitor.log_list.no_entries",
                    str(interaction.locale),
                    {"page": page}
                )
                await interaction.followup.send(no_entries_msg, ephemeral=True)
                return

            embed = discord.Embed(
                title=get_localized_text("master_monitor.log_list.embed_title", str(interaction.locale)),
                color=discord.Color.green()
            )

            description_parts = []
            for entry in log_entries:
                # Simplified formatting for the list view
                # Ideally, use a more condensed version from report_formatter if available
                entry_line = get_localized_text(
                    "master_monitor.log_list.entry_format", # Example key: "{log_id}. {timestamp} - {event_type}: {details_preview}"
                    str(interaction.locale),
                    {
                        "log_id": entry.id,
                        "timestamp": discord.utils.format_dt(entry.timestamp, style='f'),
                        "event_type": entry.event_type.value,
                        "details_preview": str(entry.details_json)[:100] + "..." if entry.details_json and len(str(entry.details_json)) > 100 else str(entry.details_json)
                    }
                )
                description_parts.append(entry_line)

            embed.description = "\n".join(description_parts)

            total_pages = (total_entries + limit - 1) // limit
            footer_text_key = "master_monitor.log_list.footer_pagination_current" if total_pages > 0 else "master_monitor.log_list.footer_pagination_empty"
            embed.set_footer(text=get_localized_text(
                footer_text_key,
                str(interaction.locale),
                {"page": page, "total_pages": total_pages, "total_entries": total_entries}
            ))

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"Error in /master_monitor log_list for guild {interaction.guild_id}: {e}")
            error_msg = get_localized_text("master_generic.error_unexpected", str(interaction.locale), {"error": str(e)})
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    # TODO: Implement WorldState commands - Partially done below
    worldstate_group = app_commands.Group(name="worldstate", description="Commands for monitoring WorldState entries (from RuleConfig).")

    @worldstate_group.command(name="get", description="Get a specific WorldState value by its key.")
    @app_commands.describe(key="The key of the WorldState entry (e.g., 'worldstate:main_quest:status').")
    async def worldstate_get(self, interaction: discord.Interaction, key: str):
        """Gets a specific WorldState entry."""
        await interaction.response.defer(ephemeral=True)
        master_player, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player or not session:
            return

        try:
            rule_entry = await rule_config_crud.get_by_key(session, guild_id=interaction.guild_id, key=key)

            if not rule_entry:
                error_msg = get_localized_text(
                    "master_monitor.worldstate_get.not_found",
                    str(interaction.locale),
                    {"key": key}
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            embed = discord.Embed(
                title=get_localized_text("master_monitor.worldstate_get.embed_title", str(interaction.locale), {"key": key}),
                color=discord.Color.purple()
            )
            embed.add_field(
                name=get_localized_text("master_monitor.worldstate_get.field_value", str(interaction.locale)),
                value=f"```json\n{discord.utils.escape_markdown(str(rule_entry.value_json))[:1000]}\n```",
                inline=False
            )
            embed.add_field(
                name=get_localized_text("master_monitor.worldstate_get.field_description", str(interaction.locale)),
                value=rule_entry.description or get_localized_text("master_generic.na", str(interaction.locale)),
                inline=False
            )
            embed.add_field(
                name=get_localized_text("master_monitor.worldstate_get.field_last_modified", str(interaction.locale)),
                value=discord.utils.format_dt(rule_entry.updated_at),
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"Error in /master_monitor worldstate_get for guild {interaction.guild_id}: {e}")
            error_msg = get_localized_text("master_generic.error_unexpected", str(interaction.locale), {"error": str(e)})
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    @worldstate_group.command(name="list", description="List WorldState entries with optional prefix filter.")
    @app_commands.describe(
        page="Page number to display.",
        limit="Number of entries per page.",
        prefix="Filter by key prefix (e.g., 'worldstate:quests')."
    )
    async def worldstate_list(
        self,
        interaction: discord.Interaction,
        page: app_commands.Range[int, 1] = 1,
        limit: app_commands.Range[int, 1, 50] = 10,
        prefix: Optional[str] = None,
    ):
        """Lists WorldState entries with pagination and optional prefix filter."""
        await interaction.response.defer(ephemeral=True)
        master_player, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player or not session:
            return

        try:
            skip = (page - 1) * limit

            # Assuming rule_config_crud has or will have get_multi_by_guild_and_prefix and count_by_guild_and_prefix
            # If not, this needs to be implemented in rule_config_crud or handled here by fetching all and filtering.
            # For now, let's assume such methods exist or will be added to rule_config_crud.
            # If prefix is not provided, we might list all RuleConfig entries or only those starting with "worldstate:"
            effective_prefix = prefix if prefix else "worldstate:" # Default to "worldstate:" if no prefix given

            total_entries = await rule_config_crud.count_by_guild_and_prefix( # Assumed method
                session,
                guild_id=interaction.guild_id,
                prefix=effective_prefix,
            )
            rule_entries = await rule_config_crud.get_multi_by_guild_and_prefix( # Assumed method
                session,
                guild_id=interaction.guild_id,
                prefix=effective_prefix,
                skip=skip,
                limit=limit,
            )

            if not rule_entries:
                no_entries_msg = get_localized_text(
                    "master_monitor.worldstate_list.no_entries",
                    str(interaction.locale),
                    {"page": page, "prefix": effective_prefix}
                )
                await interaction.followup.send(no_entries_msg, ephemeral=True)
                return

            embed = discord.Embed(
                title=get_localized_text("master_monitor.worldstate_list.embed_title", str(interaction.locale), {"prefix": effective_prefix}),
                color=discord.Color.dark_purple()
            )

            description_parts = []
            for entry in rule_entries:
                entry_line = get_localized_text(
                    "master_monitor.worldstate_list.entry_format", # Key: "{key_display}: {value_preview}"
                    str(interaction.locale),
                    {
                        "key_display": entry.key,
                        "value_preview": str(entry.value_json)[:100] + "..." if entry.value_json and len(str(entry.value_json)) > 100 else str(entry.value_json)
                    }
                )
                description_parts.append(entry_line)

            embed.description = "\n".join(description_parts)

            total_pages = (total_entries + limit - 1) // limit
            footer_text_key = "master_monitor.worldstate_list.footer_pagination_current" if total_pages > 0 else "master_monitor.worldstate_list.footer_pagination_empty"
            embed.set_footer(text=get_localized_text(
                footer_text_key,
                str(interaction.locale),
                {"page": page, "total_pages": total_pages, "total_entries": total_entries}
            ))

            await interaction.followup.send(embed=embed, ephemeral=True)

        except AttributeError as ae: # Catch if assumed CRUD methods are missing
            logger.error(f"Missing CRUD method for RuleConfig prefix search: {ae}")
            error_msg = get_localized_text("master_generic.error_not_implemented", str(interaction.locale))
            await interaction.followup.send(error_msg, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor worldstate_list for guild {interaction.guild_id}: {e}")
            error_msg = get_localized_text("master_generic.error_unexpected", str(interaction.locale), {"error": str(e)})
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    # TODO: Implement Map commands - Partially done below
    map_group = app_commands.Group(name="map", description="Commands for monitoring map and location information.")

    @map_group.command(name="list_locations", description="List all locations in the guild.")
    @app_commands.describe(
        page="Page number to display.",
        limit="Number of entries per page.",
    )
    async def map_list_locations(
        self,
        interaction: discord.Interaction,
        page: app_commands.Range[int, 1] = 1,
        limit: app_commands.Range[int, 1, 50] = 10,
    ):
        """Lists all locations in the guild with pagination."""
        await interaction.response.defer(ephemeral=True)
        master_player, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player or not session:
            return

        try:
            skip = (page - 1) * limit
            total_entries = await location_crud.count(session, guild_id=interaction.guild_id) # Changed to .count
            locations = await location_crud.get_multi( # Changed to .get_multi
                session,
                guild_id=interaction.guild_id,
                skip=skip,
                limit=limit,
            )

            if not locations:
                no_entries_msg = get_localized_text(
                    "master_monitor.map_list_locations.no_entries",
                    str(interaction.locale),
                    {"page": page}
                )
                await interaction.followup.send(no_entries_msg, ephemeral=True)
                return

            embed = discord.Embed(
                title=get_localized_text("master_monitor.map_list_locations.embed_title", str(interaction.locale)),
                color=discord.Color.orange()
            )

            description_parts = []
            for loc in locations:
                loc_name = get_localized_text(loc.name_i18n, str(interaction.locale), loc.name_i18n.get("en", "N/A"))
                entry_line = get_localized_text(
                    "master_monitor.map_list_locations.entry_format", # Key: "{loc_id} ({loc_static_id}): {loc_name} ({loc_type})"
                    str(interaction.locale),
                    {
                        "loc_id": loc.id,
                        "loc_static_id": loc.static_id or get_localized_text("master_generic.na_short", str(interaction.locale)),
                        "loc_name": loc_name,
                        "loc_type": loc.type.value
                    }
                )
                description_parts.append(entry_line)

            embed.description = "\n".join(description_parts)

            total_pages = (total_entries + limit - 1) // limit
            footer_text_key = "master_monitor.map_list_locations.footer_pagination_current" if total_pages > 0 else "master_monitor.map_list_locations.footer_pagination_empty"
            embed.set_footer(text=get_localized_text(
                footer_text_key,
                str(interaction.locale),
                {"page": page, "total_pages": total_pages, "total_entries": total_entries}
            ))

            await interaction.followup.send(embed=embed, ephemeral=True)

        except AttributeError as ae: # Catch if assumed CRUD methods are missing
            logger.error(f"Missing CRUD method for Location listing (count_by_guild or get_multi_by_guild): {ae}")
            error_msg = get_localized_text("master_generic.error_not_implemented", str(interaction.locale))
            await interaction.followup.send(error_msg, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor map_list_locations for guild {interaction.guild_id}: {e}")
            error_msg = get_localized_text("master_generic.error_unexpected", str(interaction.locale), {"error": str(e)})
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    @map_group.command(name="view_location", description="View details of a specific location.")
    @app_commands.describe(identifier="The ID or static_id of the location.")
    async def map_view_location(self, interaction: discord.Interaction, identifier: str):
        """Views details of a specific location by its ID or static_id."""
        await interaction.response.defer(ephemeral=True)
        master_player, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player or not session:
            return

        try:
            location: Optional[Location] = None
            is_static_id = False
            if identifier.isdigit():
                location = await location_crud.get(session, id=int(identifier), guild_id=interaction.guild_id)

            if not location: # Try searching by static_id if not found by int ID or if identifier is not digit
                location = await location_crud.get_by_static_id(session, guild_id=interaction.guild_id, static_id=identifier)
                if location:
                    is_static_id = True

            if not location:
                error_msg = get_localized_text(
                    "master_monitor.map_view_location.not_found",
                    str(interaction.locale),
                    {"identifier": identifier}
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            loc_name = get_localized_text(location.name_i18n, str(interaction.locale), location.name_i18n.get("en", "N/A"))
            loc_desc = get_localized_text(location.descriptions_i18n, str(interaction.locale), location.descriptions_i18n.get("en", "N/A"))

            embed = discord.Embed(
                title=get_localized_text("master_monitor.map_view_location.embed_title", str(interaction.locale), {"location_name": loc_name}),
                description=loc_desc,
                color=discord.Color.dark_orange()
            )
            embed.add_field(name=get_localized_text("master_monitor.map_view_location.field_id", str(interaction.locale)), value=str(location.id), inline=True)
            embed.add_field(name=get_localized_text("master_monitor.map_view_location.field_static_id", str(interaction.locale)), value=location.static_id or get_localized_text("master_generic.na", str(interaction.locale)), inline=True)
            embed.add_field(name=get_localized_text("master_monitor.map_view_location.field_type", str(interaction.locale)), value=location.type.value, inline=True)

            if location.parent_location_id:
                 embed.add_field(name=get_localized_text("master_monitor.map_view_location.field_parent_id", str(interaction.locale)), value=str(location.parent_location_id), inline=True)

            embed.add_field(name=get_localized_text("master_monitor.map_view_location.field_coordinates", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(location.coordinates_json))}\n```" if location.coordinates_json else get_localized_text("master_generic.na", str(interaction.locale)), inline=False)
            embed.add_field(name=get_localized_text("master_monitor.map_view_location.field_neighbors", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(location.neighbor_locations_json))}\n```" if location.neighbor_locations_json else get_localized_text("master_generic.na", str(interaction.locale)), inline=False)
            embed.add_field(name=get_localized_text("master_monitor.map_view_location.field_generated_details", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(location.generated_details_json))[:1000]}\n```" if location.generated_details_json else get_localized_text("master_generic.na", str(interaction.locale)), inline=False)

            # TODO: Add information about players/NPCs present if needed, though this might make the embed too large.
            # Could be a separate command or an option.

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"Error in /master_monitor map_view_location for guild {interaction.guild_id}: {e}")
            error_msg = get_localized_text("master_generic.error_unexpected", str(interaction.locale), {"error": str(e)})
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    # TODO: Implement Entities commands - Partially done below for Players
    entities_group = app_commands.Group(name="entities", description="Commands for monitoring various game entities.")

    @entities_group.command(name="list_players", description="List all players in the guild.")
    @app_commands.describe(
        page="Page number to display.",
        limit="Number of entries per page.",
    )
    async def entities_list_players(
        self,
        interaction: discord.Interaction,
        page: app_commands.Range[int, 1] = 1,
        limit: app_commands.Range[int, 1, 50] = 10,
    ):
        """Lists all players in the guild with pagination."""
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session: # master_player_session is actually master_player model instance
            return

        try:
            skip = (page - 1) * limit
            # Assuming player_crud has count_by_guild and get_multi_by_guild or similar
            total_entries = await player_crud.count(session, guild_id=interaction.guild_id) # Changed to .count
            players = await player_crud.get_multi( # Changed to .get_multi
                session,
                guild_id=interaction.guild_id,
                skip=skip,
                limit=limit,
            )

            if not players:
                no_entries_msg = get_localized_text(
                    "master_monitor.entities_list_players.no_entries",
                    str(interaction.locale),
                    {"page": page}
                )
                await interaction.followup.send(no_entries_msg, ephemeral=True)
                return

            embed = discord.Embed(
                title=get_localized_text("master_monitor.entities_list_players.embed_title", str(interaction.locale)),
                color=discord.Color.gold()
            )

            description_parts = []
            for p in players:
                player_name = get_localized_text(p.name_i18n, str(interaction.locale), p.name_i18n.get("en", "N/A"))
                entry_line = get_localized_text(
                    "master_monitor.entities_list_players.entry_format", # Key: "ID: {player_db_id} (Discord: <@{player_discord_id}>) - {player_name_loc} (Lvl: {player_level})"
                    str(interaction.locale),
                    {
                        "player_db_id": p.id,
                        "player_discord_id": p.discord_user_id,
                        "player_name_loc": player_name,
                        "player_level": p.level
                    }
                )
                description_parts.append(entry_line)

            embed.description = "\n".join(description_parts)

            total_pages = (total_entries + limit - 1) // limit
            footer_text_key = "master_monitor.entities_list_players.footer_pagination_current" if total_pages > 0 else "master_monitor.entities_list_players.footer_pagination_empty"
            embed.set_footer(text=get_localized_text(
                footer_text_key,
                str(interaction.locale),
                {"page": page, "total_pages": total_pages, "total_entries": total_entries}
            ))

            await interaction.followup.send(embed=embed, ephemeral=True)

        except AttributeError as ae:
            logger.error(f"Missing CRUD method for Player listing (count_by_guild or get_multi_by_guild): {ae}")
            error_msg = get_localized_text("master_generic.error_not_implemented", str(interaction.locale))
            await interaction.followup.send(error_msg, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_list_players for guild {interaction.guild_id}: {e}")
            error_msg = get_localized_text("master_generic.error_unexpected", str(interaction.locale), {"error": str(e)})
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    @entities_group.command(name="view_player", description="View details of a specific player.")
    @app_commands.describe(player_id="The database ID of the player.")
    async def entities_view_player(self, interaction: discord.Interaction, player_id: int):
        """Views details of a specific player by their database ID."""
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session:
            return

        try:
            player = await player_crud.get(session, id=player_id, guild_id=interaction.guild_id)

            if not player:
                error_msg = get_localized_text(
                    "master_monitor.entities_view_player.not_found",
                    str(interaction.locale),
                    {"player_id": player_id}
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            player_name = get_localized_text(player.name_i18n, str(interaction.locale), player.name_i18n.get("en", "N/A"))
            player_desc = get_localized_text(player.description_i18n, str(interaction.locale), player.description_i18n.get("en", "N/A"))

            embed = discord.Embed(
                title=get_localized_text("master_monitor.entities_view_player.embed_title", str(interaction.locale), {"player_name": player_name}),
                description=player_desc,
                color=discord.Color.dark_gold()
            )
            embed.add_field(name=get_localized_text("master_monitor.entities_view_player.field_db_id", str(interaction.locale)), value=str(player.id), inline=True)
            embed.add_field(name=get_localized_text("master_monitor.entities_view_player.field_discord_user", str(interaction.locale)), value=f"<@{player.discord_user_id}> ({player.discord_user_id})", inline=True)
            embed.add_field(name=get_localized_text("master_monitor.entities_view_player.field_level", str(interaction.locale)), value=str(player.level), inline=True)
            embed.add_field(name=get_localized_text("master_monitor.entities_view_player.field_xp", str(interaction.locale)), value=str(player.xp), inline=True)
            embed.add_field(name=get_localized_text("master_monitor.entities_view_player.field_unspent_xp", str(interaction.locale)), value=str(player.unspent_xp), inline=True)
            embed.add_field(name=get_localized_text("master_monitor.entities_view_player.field_current_status", str(interaction.locale)), value=player.current_status.value if player.current_status else get_localized_text("master_generic.na", str(interaction.locale)), inline=True)

            if player.location_id:
                loc = await location_crud.get(session, id=player.location_id, guild_id=interaction.guild_id)
                loc_name_display = get_localized_text("master_generic.unknown_location", str(interaction.locale))
                if loc:
                    loc_name_display = get_localized_text(loc.name_i18n, str(interaction.locale), loc.name_i18n.get("en", f"ID: {loc.id}"))
                embed.add_field(name=get_localized_text("master_monitor.entities_view_player.field_location", str(interaction.locale)), value=f"{loc_name_display} (ID: {player.location_id})", inline=True)

            if player.party_id:
                party = await party_crud.get(session, id=player.party_id, guild_id=interaction.guild_id)
                party_name_display = get_localized_text("master_generic.unknown_party", str(interaction.locale))
                if party:
                     party_name_display = get_localized_text(party.name_i18n, str(interaction.locale), party.name_i18n.get("en", f"ID: {party.id}"))
                embed.add_field(name=get_localized_text("master_monitor.entities_view_player.field_party", str(interaction.locale)), value=f"{party_name_display} (ID: {player.party_id})", inline=True)

            embed.add_field(name=get_localized_text("master_monitor.entities_view_player.field_attributes", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(player.attributes_json))}\n```" if player.attributes_json else get_localized_text("master_generic.na", str(interaction.locale)), inline=False)
            embed.add_field(name=get_localized_text("master_monitor.entities_view_player.field_properties", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(player.properties_json))}\n```" if player.properties_json else get_localized_text("master_generic.na", str(interaction.locale)), inline=False)
            embed.add_field(name=get_localized_text("master_monitor.entities_view_player.field_created_at", str(interaction.locale)), value=discord.utils.format_dt(player.created_at), inline=True)
            embed.add_field(name=get_localized_text("master_monitor.entities_view_player.field_updated_at", str(interaction.locale)), value=discord.utils.format_dt(player.updated_at), inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_view_player for guild {interaction.guild_id}: {e}")
            error_msg = get_localized_text("master_generic.error_unexpected", str(interaction.locale), {"error": str(e)})
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    @entities_group.command(name="list_npcs", description="List all Generated NPCs in the guild.")
    @app_commands.describe(
        page="Page number to display.",
        limit="Number of entries per page.",
    )
    async def entities_list_npcs(
        self,
        interaction: discord.Interaction,
        page: app_commands.Range[int, 1] = 1,
        limit: app_commands.Range[int, 1, 50] = 10,
    ):
        """Lists all Generated NPCs in the guild with pagination."""
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session:
            return

        try:
            skip = (page - 1) * limit
            # Assuming npc_crud has count_by_guild and get_multi_by_guild or similar
            total_entries = await npc_crud.count(session, guild_id=interaction.guild_id)  # Changed to .count
            npcs = await npc_crud.get_multi( # Changed to .get_multi
                session,
                guild_id=interaction.guild_id,
                skip=skip,
                limit=limit,
            )

            if not npcs:
                no_entries_msg = get_localized_text(
                    "master_monitor.entities_list_npcs.no_entries", # New localization key
                    str(interaction.locale),
                    {"page": page}
                )
                await interaction.followup.send(no_entries_msg, ephemeral=True)
                return

            embed = discord.Embed(
                title=get_localized_text("master_monitor.entities_list_npcs.embed_title", str(interaction.locale)), # New key
                color=discord.Color.teal()
            )

            description_parts = []
            for npc_obj in npcs: # Renamed from p to npc_obj for clarity
                npc_name = get_localized_text(npc_obj.name_i18n, str(interaction.locale), npc_obj.name_i18n.get("en", "N/A"))
                entry_line = get_localized_text(
                    "master_monitor.entities_list_npcs.entry_format", # New key: "ID: {npc_db_id} (Static: {npc_static_id}) - {npc_name_loc} (Lvl: {npc_level})"
                    str(interaction.locale),
                    {
                        "npc_db_id": npc_obj.id,
                        "npc_static_id": npc_obj.static_id or get_localized_text("master_generic.na_short", str(interaction.locale)),
                        "npc_name_loc": npc_name,
                        "npc_level": npc_obj.level or get_localized_text("master_generic.na_short", str(interaction.locale))
                    }
                )
                description_parts.append(entry_line)

            embed.description = "\n".join(description_parts)

            total_pages = (total_entries + limit - 1) // limit
            footer_text_key = "master_monitor.entities_list_npcs.footer_pagination_current" if total_pages > 0 else "master_monitor.entities_list_npcs.footer_pagination_empty" # New keys
            embed.set_footer(text=get_localized_text(
                footer_text_key,
                str(interaction.locale),
                {"page": page, "total_pages": total_pages, "total_entries": total_entries}
            ))

            await interaction.followup.send(embed=embed, ephemeral=True)

        except AttributeError as ae:
            logger.error(f"Missing CRUD method for GeneratedNpc listing (count_by_guild or get_multi_by_guild): {ae}")
            error_msg = get_localized_text("master_generic.error_not_implemented", str(interaction.locale))
            await interaction.followup.send(error_msg, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_list_npcs for guild {interaction.guild_id}: {e}")
            error_msg = get_localized_text("master_generic.error_unexpected", str(interaction.locale), {"error": str(e)})
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    @entities_group.command(name="view_npc", description="View details of a specific Generated NPC.")
    @app_commands.describe(npc_id="The database ID of the Generated NPC.")
    async def entities_view_npc(self, interaction: discord.Interaction, npc_id: int):
        """Views details of a specific Generated NPC by their database ID."""
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session:
            return

        try:
            npc_obj = await npc_crud.get(session, id=npc_id, guild_id=interaction.guild_id) # Renamed from player to npc_obj

            if not npc_obj:
                error_msg = get_localized_text(
                    "master_monitor.entities_view_npc.not_found", # New key
                    str(interaction.locale),
                    {"npc_id": npc_id}
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            npc_name = get_localized_text(npc_obj.name_i18n, str(interaction.locale), npc_obj.name_i18n.get("en", "N/A"))
            npc_desc = get_localized_text(npc_obj.description_i18n, str(interaction.locale), npc_obj.description_i18n.get("en", "N/A"))

            embed = discord.Embed(
                title=get_localized_text("master_monitor.entities_view_npc.embed_title", str(interaction.locale), {"npc_name": npc_name}), # New key
                description=npc_desc,
                color=discord.Color.dark_teal()
            )
            embed.add_field(name=get_localized_text("master_monitor.entities_view_npc.field_db_id", str(interaction.locale)), value=str(npc_obj.id), inline=True) # New key
            embed.add_field(name=get_localized_text("master_monitor.entities_view_npc.field_static_id", str(interaction.locale)), value=npc_obj.static_id or get_localized_text("master_generic.na", str(interaction.locale)), inline=True) # New key
            embed.add_field(name=get_localized_text("master_monitor.entities_view_npc.field_level", str(interaction.locale)), value=str(npc_obj.level) if npc_obj.level is not None else get_localized_text("master_generic.na", str(interaction.locale)), inline=True) # New key

            if npc_obj.location_id: # Renamed from player.location_id
                loc = await location_crud.get(session, id=npc_obj.location_id, guild_id=interaction.guild_id)
                loc_name_display = get_localized_text("master_generic.unknown_location", str(interaction.locale))
                if loc:
                    loc_name_display = get_localized_text(loc.name_i18n, str(interaction.locale), loc.name_i18n.get("en", f"ID: {loc.id}"))
                embed.add_field(name=get_localized_text("master_monitor.entities_view_npc.field_location", str(interaction.locale)), value=f"{loc_name_display} (ID: {npc_obj.location_id})", inline=True) # New key

            if npc_obj.faction_id: # New field
                # Assuming faction_crud exists and has a get method
                # faction = await faction_crud.get(session, id=npc_obj.faction_id, guild_id=interaction.guild_id)
                # faction_name_display = "..."
                # embed.add_field(name=get_localized_text("master_monitor.entities_view_npc.field_faction", str(interaction.locale)), value=f"{faction_name_display} (ID: {npc_obj.faction_id})", inline=True)
                embed.add_field(name=get_localized_text("master_monitor.entities_view_npc.field_faction_id", str(interaction.locale)), value=str(npc_obj.faction_id), inline=True)


            embed.add_field(name=get_localized_text("master_monitor.entities_view_npc.field_properties", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(npc_obj.properties_json))[:1000]}\n```" if npc_obj.properties_json else get_localized_text("master_generic.na", str(interaction.locale)), inline=False) # New key, properties_json can be large
            embed.add_field(name=get_localized_text("master_monitor.entities_view_npc.field_ai_metadata", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(npc_obj.ai_metadata_json))[:1000]}\n```" if npc_obj.ai_metadata_json else get_localized_text("master_generic.na", str(interaction.locale)), inline=False) # New key
            embed.add_field(name=get_localized_text("master_monitor.entities_view_npc.field_created_at", str(interaction.locale)), value=discord.utils.format_dt(npc_obj.created_at), inline=True) # New key
            embed.add_field(name=get_localized_text("master_monitor.entities_view_npc.field_updated_at", str(interaction.locale)), value=discord.utils.format_dt(npc_obj.updated_at), inline=True) # New key

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_view_npc for guild {interaction.guild_id}: {e}")
            error_msg = get_localized_text("master_generic.error_unexpected", str(interaction.locale), {"error": str(e)})
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    @entities_group.command(name="list_parties", description="List all parties in the guild.")
    @app_commands.describe(
        page="Page number to display.",
        limit="Number of entries per page.",
    )
    async def entities_list_parties(
        self,
        interaction: discord.Interaction,
        page: app_commands.Range[int, 1] = 1,
        limit: app_commands.Range[int, 1, 50] = 10,
    ):
        """Lists all parties in the guild with pagination."""
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session:
            return

        try:
            skip = (page - 1) * limit
            total_entries = await party_crud.count(session, guild_id=interaction.guild_id) # Changed to .count
            parties = await party_crud.get_multi( # Changed to .get_multi
                session,
                guild_id=interaction.guild_id,
                skip=skip,
                limit=limit,
                load_relationships=['players', 'leader'] # Eager load players and leader
            )

            if not parties:
                no_entries_msg = get_localized_text(
                    "master_monitor.entities_list_parties.no_entries", # New key
                    str(interaction.locale),
                    {"page": page}
                )
                await interaction.followup.send(no_entries_msg, ephemeral=True)
                return

            embed = discord.Embed(
                title=get_localized_text("master_monitor.entities_list_parties.embed_title", str(interaction.locale)), # New key
                color=discord.Color.blue()
            )

            description_parts = []
            for party_obj in parties:
                party_name = get_localized_text(party_obj.name_i18n, str(interaction.locale), party_obj.name_i18n.get("en", "N/A"))
                leader_name = get_localized_text("master_generic.na_short", str(interaction.locale))
                if party_obj.leader:
                    leader_name = get_localized_text(party_obj.leader.name_i18n, str(interaction.locale), party_obj.leader.name_i18n.get("en", f"ID: {party_obj.leader_player_id}"))

                member_count = len(party_obj.players) if party_obj.players else 0

                entry_line = get_localized_text(
                    "master_monitor.entities_list_parties.entry_format", # New key: "ID: {party_db_id} - {party_name_loc} (Leader: {leader_name}, Members: {member_count})"
                    str(interaction.locale),
                    {
                        "party_db_id": party_obj.id,
                        "party_name_loc": party_name,
                        "leader_name": leader_name,
                        "member_count": member_count
                    }
                )
                description_parts.append(entry_line)

            embed.description = "\n".join(description_parts)

            total_pages = (total_entries + limit - 1) // limit
            footer_text_key = "master_monitor.entities_list_parties.footer_pagination_current" if total_pages > 0 else "master_monitor.entities_list_parties.footer_pagination_empty" # New keys
            embed.set_footer(text=get_localized_text(
                footer_text_key,
                str(interaction.locale),
                {"page": page, "total_pages": total_pages, "total_entries": total_entries}
            ))

            await interaction.followup.send(embed=embed, ephemeral=True)

        except AttributeError as ae:
            logger.error(f"Missing CRUD method for Party listing (count_by_guild or get_multi_by_guild): {ae}")
            error_msg = get_localized_text("master_generic.error_not_implemented", str(interaction.locale))
            await interaction.followup.send(error_msg, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_list_parties for guild {interaction.guild_id}: {e}")
            error_msg = get_localized_text("master_generic.error_unexpected", str(interaction.locale), {"error": str(e)})
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    @entities_group.command(name="view_party", description="View details of a specific party.")
    @app_commands.describe(party_id="The database ID of the party.")
    async def entities_view_party(self, interaction: discord.Interaction, party_id: int):
        """Views details of a specific party by its database ID."""
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session:
            return

        try:
            # Eager load players and leader relationships
            party = await party_crud.get(
                session,
                id=party_id,
                guild_id=interaction.guild_id,
                load_relationships=['players', 'leader']
            )

            if not party:
                error_msg = get_localized_text(
                    "master_monitor.entities_view_party.not_found", # New key
                    str(interaction.locale),
                    {"party_id": party_id}
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            party_name = get_localized_text(party.name_i18n, str(interaction.locale), party.name_i18n.get("en", "N/A"))

            embed = discord.Embed(
                title=get_localized_text("master_monitor.entities_view_party.embed_title", str(interaction.locale), {"party_name": party_name}), # New key
                color=discord.Color.dark_blue()
            )
            embed.add_field(name=get_localized_text("master_monitor.entities_view_party.field_db_id", str(interaction.locale)), value=str(party.id), inline=True) # New key

            leader_name_display = get_localized_text("master_generic.na", str(interaction.locale))
            if party.leader:
                leader_name = get_localized_text(party.leader.name_i18n, str(interaction.locale), party.leader.name_i18n.get("en", f"ID: {party.leader_player_id}"))
                leader_name_display = f"{leader_name} (<@{party.leader.discord_user_id}>)"
            elif party.leader_player_id: # Fallback if leader object not loaded but ID is there
                leader_name_display = f"ID: {party.leader_player_id}"

            embed.add_field(name=get_localized_text("master_monitor.entities_view_party.field_leader", str(interaction.locale)), value=leader_name_display, inline=True) # New key
            embed.add_field(name=get_localized_text("master_monitor.entities_view_party.field_current_status", str(interaction.locale)), value=party.current_turn_status.value if party.current_turn_status else get_localized_text("master_generic.na", str(interaction.locale)), inline=True) # New key

            member_list = []
            if party.players:
                for member in party.players:
                    member_name = get_localized_text(member.name_i18n, str(interaction.locale), member.name_i18n.get("en", f"ID: {member.id}"))
                    member_list.append(f"{member_name} (<@{member.discord_user_id}>, ID: {member.id})")

            members_value = "\n".join(member_list) if member_list else get_localized_text("master_generic.none", str(interaction.locale))
            if len(members_value) > 1024: # Embed field value limit
                members_value = members_value[:1020] + "..."
            embed.add_field(name=get_localized_text("master_monitor.entities_view_party.field_members", str(interaction.locale), {"count": len(member_list)}), value=members_value, inline=False) # New key

            embed.add_field(name=get_localized_text("master_monitor.entities_view_party.field_properties", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(party.properties_json))[:1000]}\n```" if party.properties_json else get_localized_text("master_generic.na", str(interaction.locale)), inline=False) # New key
            embed.add_field(name=get_localized_text("master_monitor.entities_view_party.field_created_at", str(interaction.locale)), value=discord.utils.format_dt(party.created_at), inline=True) # New key
            embed.add_field(name=get_localized_text("master_monitor.entities_view_party.field_updated_at", str(interaction.locale)), value=discord.utils.format_dt(party.updated_at), inline=True) # New key

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_view_party for guild {interaction.guild_id}: {e}")
            error_msg = get_localized_text("master_generic.error_unexpected", str(interaction.locale), {"error": str(e)})
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    @entities_group.command(name="list_global_npcs", description="List all Global NPCs in the guild.")
    @app_commands.describe(
        page="Page number to display.",
        limit="Number of entries per page.",
    )
    async def entities_list_global_npcs(
        self,
        interaction: discord.Interaction,
        page: app_commands.Range[int, 1] = 1,
        limit: app_commands.Range[int, 1, 50] = 10,
    ):
        """Lists all Global NPCs in the guild with pagination."""
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session:
            return

        try:
            skip = (page - 1) * limit
            total_entries = await global_npc_crud.count(session, guild_id=interaction.guild_id) # Changed to .count
            global_npcs = await global_npc_crud.get_multi( # Changed to .get_multi
                session,
                guild_id=interaction.guild_id,
                skip=skip,
                limit=limit,
            )

            if not global_npcs:
                no_entries_msg = get_localized_text(
                    "master_monitor.entities_list_global_npcs.no_entries", # New key
                    str(interaction.locale),
                    {"page": page}
                )
                await interaction.followup.send(no_entries_msg, ephemeral=True)
                return

            embed = discord.Embed(
                title=get_localized_text("master_monitor.entities_list_global_npcs.embed_title", str(interaction.locale)), # New key
                color=discord.Color.dark_green()
            )

            description_parts = []
            for gn_obj in global_npcs:
                gn_name = get_localized_text(gn_obj.name_i18n, str(interaction.locale), gn_obj.name_i18n.get("en", "N/A"))
                entry_line = get_localized_text(
                    "master_monitor.entities_list_global_npcs.entry_format", # New key: "ID: {gn_db_id} (Static: {gn_static_id}) - {gn_name_loc}"
                    str(interaction.locale),
                    {
                        "gn_db_id": gn_obj.id,
                        "gn_static_id": gn_obj.static_id or get_localized_text("master_generic.na_short", str(interaction.locale)),
                        "gn_name_loc": gn_name,
                    }
                )
                description_parts.append(entry_line)

            embed.description = "\n".join(description_parts)

            total_pages = (total_entries + limit - 1) // limit
            footer_text_key = "master_monitor.entities_list_global_npcs.footer_pagination_current" if total_pages > 0 else "master_monitor.entities_list_global_npcs.footer_pagination_empty" # New keys
            embed.set_footer(text=get_localized_text(
                footer_text_key,
                str(interaction.locale),
                {"page": page, "total_pages": total_pages, "total_entries": total_entries}
            ))

            await interaction.followup.send(embed=embed, ephemeral=True)

        except AttributeError as ae:
            logger.error(f"Missing CRUD method for GlobalNpc listing (count_by_guild or get_multi_by_guild): {ae}")
            error_msg = get_localized_text("master_generic.error_not_implemented", str(interaction.locale))
            await interaction.followup.send(error_msg, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_list_global_npcs for guild {interaction.guild_id}: {e}")
            error_msg = get_localized_text("master_generic.error_unexpected", str(interaction.locale), {"error": str(e)})
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    @entities_group.command(name="view_global_npc", description="View details of a specific Global NPC.")
    @app_commands.describe(global_npc_id="The database ID of the Global NPC.")
    async def entities_view_global_npc(self, interaction: discord.Interaction, global_npc_id: int):
        """Views details of a specific Global NPC by their database ID."""
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session:
            return

        try:
            gn_obj = await global_npc_crud.get(session, id=global_npc_id, guild_id=interaction.guild_id)

            if not gn_obj:
                error_msg = get_localized_text(
                    "master_monitor.entities_view_global_npc.not_found", # New key
                    str(interaction.locale),
                    {"global_npc_id": global_npc_id}
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            gn_name = get_localized_text(gn_obj.name_i18n, str(interaction.locale), gn_obj.name_i18n.get("en", "N/A"))
            gn_desc = get_localized_text(gn_obj.description_i18n, str(interaction.locale), gn_obj.description_i18n.get("en", "N/A"))

            embed = discord.Embed(
                title=get_localized_text("master_monitor.entities_view_global_npc.embed_title", str(interaction.locale), {"gn_name": gn_name}), # New key
                description=gn_desc,
                color=discord.Color.dark_green()
            )
            embed.add_field(name=get_localized_text("master_monitor.entities_view_global_npc.field_db_id", str(interaction.locale)), value=str(gn_obj.id), inline=True)
            embed.add_field(name=get_localized_text("master_monitor.entities_view_global_npc.field_static_id", str(interaction.locale)), value=gn_obj.static_id or get_localized_text("master_generic.na", str(interaction.locale)), inline=True)

            if gn_obj.current_location_id:
                loc = await location_crud.get(session, id=gn_obj.current_location_id, guild_id=interaction.guild_id)
                loc_name_display = get_localized_text("master_generic.unknown_location", str(interaction.locale))
                if loc:
                    loc_name_display = get_localized_text(loc.name_i18n, str(interaction.locale), loc.name_i18n.get("en", f"ID: {loc.id}"))
                embed.add_field(name=get_localized_text("master_monitor.entities_view_global_npc.field_location", str(interaction.locale)), value=f"{loc_name_display} (ID: {gn_obj.current_location_id})", inline=True)

            embed.add_field(name=get_localized_text("master_monitor.entities_view_global_npc.field_properties", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(gn_obj.properties_json))[:1000]}\n```" if gn_obj.properties_json else get_localized_text("master_generic.na", str(interaction.locale)), inline=False)
            embed.add_field(name=get_localized_text("master_monitor.entities_view_global_npc.field_ai_rules_override", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(gn_obj.ai_rules_override_json))[:1000]}\n```" if gn_obj.ai_rules_override_json else get_localized_text("master_generic.na", str(interaction.locale)), inline=False)
            embed.add_field(name=get_localized_text("master_monitor.entities_view_global_npc.field_created_at", str(interaction.locale)), value=discord.utils.format_dt(gn_obj.created_at), inline=True)
            embed.add_field(name=get_localized_text("master_monitor.entities_view_global_npc.field_updated_at", str(interaction.locale)), value=discord.utils.format_dt(gn_obj.updated_at), inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_view_global_npc for guild {interaction.guild_id}: {e}")
            error_msg = get_localized_text("master_generic.error_unexpected", str(interaction.locale), {"error": str(e)})
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    @entities_group.command(name="list_mobile_groups", description="List all Mobile Groups in the guild.")
    @app_commands.describe(
        page="Page number to display.",
        limit="Number of entries per page.",
    )
    async def entities_list_mobile_groups(
        self,
        interaction: discord.Interaction,
        page: app_commands.Range[int, 1] = 1,
        limit: app_commands.Range[int, 1, 50] = 10,
    ):
        """Lists all Mobile Groups in the guild with pagination."""
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session:
            return

        try:
            skip = (page - 1) * limit
            total_entries = await mobile_group_crud.count(session, guild_id=interaction.guild_id) # Changed to .count
            mobile_groups = await mobile_group_crud.get_multi( # Changed to .get_multi
                session,
                guild_id=interaction.guild_id,
                skip=skip,
                limit=limit,
            )

            if not mobile_groups:
                no_entries_msg = get_localized_text(
                    "master_monitor.entities_list_mobile_groups.no_entries", # New key
                    str(interaction.locale),
                    {"page": page}
                )
                await interaction.followup.send(no_entries_msg, ephemeral=True)
                return

            embed = discord.Embed(
                title=get_localized_text("master_monitor.entities_list_mobile_groups.embed_title", str(interaction.locale)), # New key
                color=discord.Color.purple() # Different color for distinction
            )

            description_parts = []
            for mg_obj in mobile_groups:
                mg_name = get_localized_text(mg_obj.name_i18n, str(interaction.locale), mg_obj.name_i18n.get("en", "N/A"))
                entry_line = get_localized_text(
                    "master_monitor.entities_list_mobile_groups.entry_format", # New key: "ID: {mg_db_id} (Static: {mg_static_id}) - {mg_name_loc}"
                    str(interaction.locale),
                    {
                        "mg_db_id": mg_obj.id,
                        "mg_static_id": mg_obj.static_id or get_localized_text("master_generic.na_short", str(interaction.locale)),
                        "mg_name_loc": mg_name,
                    }
                )
                description_parts.append(entry_line)

            embed.description = "\n".join(description_parts)

            total_pages = (total_entries + limit - 1) // limit
            footer_text_key = "master_monitor.entities_list_mobile_groups.footer_pagination_current" if total_pages > 0 else "master_monitor.entities_list_mobile_groups.footer_pagination_empty" # New keys
            embed.set_footer(text=get_localized_text(
                footer_text_key,
                str(interaction.locale),
                {"page": page, "total_pages": total_pages, "total_entries": total_entries}
            ))

            await interaction.followup.send(embed=embed, ephemeral=True)

        except AttributeError as ae:
            logger.error(f"Missing CRUD method for MobileGroup listing (count_by_guild or get_multi_by_guild): {ae}")
            error_msg = get_localized_text("master_generic.error_not_implemented", str(interaction.locale))
            await interaction.followup.send(error_msg, ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_list_mobile_groups for guild {interaction.guild_id}: {e}")
            error_msg = get_localized_text("master_generic.error_unexpected", str(interaction.locale), {"error": str(e)})
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    @entities_group.command(name="view_mobile_group", description="View details of a specific Mobile Group.")
    @app_commands.describe(mobile_group_id="The database ID of the Mobile Group.")
    async def entities_view_mobile_group(self, interaction: discord.Interaction, mobile_group_id: int):
        """Views details of a specific Mobile Group by its database ID."""
        await interaction.response.defer(ephemeral=True)
        master_player_session, session = await ensure_guild_configured_and_get_session(interaction)
        if not master_player_session or not session:
            return

        try:
            mg_obj = await mobile_group_crud.get(session, id=mobile_group_id, guild_id=interaction.guild_id)

            if not mg_obj:
                error_msg = get_localized_text(
                    "master_monitor.entities_view_mobile_group.not_found", # New key
                    str(interaction.locale),
                    {"mobile_group_id": mobile_group_id}
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            mg_name = get_localized_text(mg_obj.name_i18n, str(interaction.locale), mg_obj.name_i18n.get("en", "N/A"))
            mg_desc = get_localized_text(mg_obj.description_i18n, str(interaction.locale), mg_obj.description_i18n.get("en", "N/A"))

            embed = discord.Embed(
                title=get_localized_text("master_monitor.entities_view_mobile_group.embed_title", str(interaction.locale), {"mg_name": mg_name}), # New key
                description=mg_desc,
                color=discord.Color.dark_purple()
            )
            embed.add_field(name=get_localized_text("master_monitor.entities_view_mobile_group.field_db_id", str(interaction.locale)), value=str(mg_obj.id), inline=True)
            embed.add_field(name=get_localized_text("master_monitor.entities_view_mobile_group.field_static_id", str(interaction.locale)), value=mg_obj.static_id or get_localized_text("master_generic.na", str(interaction.locale)), inline=True)

            if mg_obj.current_location_id:
                loc = await location_crud.get(session, id=mg_obj.current_location_id, guild_id=interaction.guild_id)
                loc_name_display = get_localized_text("master_generic.unknown_location", str(interaction.locale))
                if loc:
                    loc_name_display = get_localized_text(loc.name_i18n, str(interaction.locale), loc.name_i18n.get("en", f"ID: {loc.id}"))
                embed.add_field(name=get_localized_text("master_monitor.entities_view_mobile_group.field_location", str(interaction.locale)), value=f"{loc_name_display} (ID: {mg_obj.current_location_id})", inline=True)

            embed.add_field(name=get_localized_text("master_monitor.entities_view_mobile_group.field_composition", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(mg_obj.composition_json))[:1000]}\n```" if mg_obj.composition_json else get_localized_text("master_generic.na", str(interaction.locale)), inline=False)
            embed.add_field(name=get_localized_text("master_monitor.entities_view_mobile_group.field_properties", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(mg_obj.properties_json))[:1000]}\n```" if mg_obj.properties_json else get_localized_text("master_generic.na", str(interaction.locale)), inline=False)
            embed.add_field(name=get_localized_text("master_monitor.entities_view_mobile_group.field_ai_rules_override", str(interaction.locale)), value=f"```json\n{discord.utils.escape_markdown(str(mg_obj.ai_rules_override_json))[:1000]}\n```" if mg_obj.ai_rules_override_json else get_localized_text("master_generic.na", str(interaction.locale)), inline=False)
            embed.add_field(name=get_localized_text("master_monitor.entities_view_mobile_group.field_created_at", str(interaction.locale)), value=discord.utils.format_dt(mg_obj.created_at), inline=True)
            embed.add_field(name=get_localized_text("master_monitor.entities_view_mobile_group.field_updated_at", str(interaction.locale)), value=discord.utils.format_dt(mg_obj.updated_at), inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"Error in /master_monitor entities_view_mobile_group for guild {interaction.guild_id}: {e}")
            error_msg = get_localized_text("master_generic.error_unexpected", str(interaction.locale), {"error": str(e)})
            await interaction.followup.send(error_msg, ephemeral=True)
        finally:
            if session:
                await session.close()

    # TODO: Implement Statistics commands

async def setup(bot: commands.Bot):
    await bot.add_cog(MasterMonitoringCog(bot))
    logger.info("MasterMonitoringCog added to bot.")
