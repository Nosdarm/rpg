import json
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db_session, transactional # transactional may not be needed here directly
from backend.core.world_generation import generate_location
from backend.core.map_management import (
    add_location_master,
    remove_location_master,
    connect_locations_master,
    disconnect_locations_master
)
from backend.models.location import LocationType # For validation/conversion
# Import the decorator for admin checks
from .master_ai_commands import is_administrator

logger = logging.getLogger(__name__)

class MasterMapCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    master_map_group = app_commands.Group(
        name="master_map",
        description="Master commands for map and location management.",
        guild_only=True
    )

    @master_map_group.command(name="generate_ai_location", description="Generate a new location using AI.")
    @app_commands.describe(
        context_json="Optional JSON string for AI generation context (e.g., {\"theme\": \"dark_forest\"}). Renamed from generation_params_json.",
        parent_location_id="Optional ID of the parent location to connect the new location to.",
        connection_details_i18n_json="Optional JSON for connection type to parent (e.g., {\"en\": \"a hidden passage\"}).",
        context_location_id="Optional ID of a nearby location to provide broader context to AI.",
        context_player_id="Optional Player ID for context.",
        context_party_id="Optional Party ID for context."
    )
    @is_administrator()
    async def generate_ai_location_cmd(self, interaction: discord.Interaction,
                                       context_json: Optional[str] = None, # Renamed
                                       parent_location_id: Optional[int] = None,
                                       connection_details_i18n_json: Optional[str] = None,
                                       context_location_id: Optional[int] = None,
                                       context_player_id: Optional[int] = None,
                                       context_party_id: Optional[int] = None):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None: # Should be caught by guild_only
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        gen_context = None
        if context_json:
            try:
                gen_context = json.loads(context_json)
            except json.JSONDecodeError:
                await interaction.followup.send("Invalid JSON string for generation context.", ephemeral=True)
                return

        conn_details = None
        if connection_details_i18n_json:
            try:
                conn_details = json.loads(connection_details_i18n_json)
                if not isinstance(conn_details, dict):
                    raise json.JSONDecodeError("Connection details must be a JSON object.", connection_details_i18n_json, 0)
            except json.JSONDecodeError as e:
                await interaction.followup.send(f"Invalid JSON for connection_details_i18n: {e}", ephemeral=True)
                return

        async with get_db_session() as session:
            location, error = await generate_location(
                session=session,
                guild_id=interaction.guild_id,
                context=gen_context, # Pass renamed context
                parent_location_id=parent_location_id,
                connection_details_i18n=conn_details,
                location_id_context=context_location_id,
                player_id_context=context_player_id,
                party_id_context=context_party_id
            )

        if error:
            await interaction.followup.send(f"Error generating location: {error}", ephemeral=True)
        elif location:
            await interaction.followup.send(f"Successfully generated location: {location.name_i18n.get('en', 'N/A')} (ID: {location.id})", ephemeral=True)
        else:
            await interaction.followup.send("Unknown error during location generation.", ephemeral=True)

    @master_map_group.command(name="add_manual_location", description="Manually add a new location.")
    @app_commands.describe(
        static_id="Unique static ID for the location (e.g., 'town_square').",
        name_i18n_json="JSON string for names (e.g., {\"en\": \"Town Square\", \"ru\": \"Городская площадь\"}).",
        descriptions_i18n_json="JSON string for descriptions.",
        location_type_str="Type of location (e.g., TOWN, FOREST - see LocationType enum).",
        coordinates_json="Optional JSON for coordinates (e.g., {\"x\": 1, \"y\": 1}).",
        neighbor_locations_json="Optional JSON for neighbors (e.g., [{\"id\": 2, \"type_i18n\": {\"en\": \"path\"}}]).",
        generated_details_json="Optional JSON for additional details."
    )
    @is_administrator()
    async def add_manual_location_cmd(self, interaction: discord.Interaction,
                                      static_id: str,
                                      name_i18n_json: str,
                                      descriptions_i18n_json: str,
                                      location_type_str: str, # Changed name to avoid conflict with enum
                                      coordinates_json: Optional[str] = None,
                                      neighbor_locations_json: Optional[str] = None,
                                      generated_details_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None: # Should be caught by guild_only
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        try:
            name_i18n = json.loads(name_i18n_json)
            descriptions_i18n = json.loads(descriptions_i18n_json)

            # Validate and convert location_type_str to LocationType enum member
            try:
                loc_type_enum_member = LocationType[location_type_str.upper()]
            except KeyError:
                valid_types = ", ".join([lt.name for lt in LocationType])
                await interaction.followup.send(f"Invalid location_type: '{location_type_str}'. Valid types are: {valid_types}", ephemeral=True)
                return

            coords = json.loads(coordinates_json) if coordinates_json else {}
            neighbors = json.loads(neighbor_locations_json) if neighbor_locations_json else []
            details = json.loads(generated_details_json) if generated_details_json else {}

            location_data = {
                "static_id": static_id,
                "name_i18n": name_i18n,
                "descriptions_i18n": descriptions_i18n,
                "type": loc_type_enum_member, # Pass the enum member to the API
                "coordinates_json": coords,
                "neighbor_locations_json": neighbors,
                "generated_details_json": details
            }
        except json.JSONDecodeError as e:
            await interaction.followup.send(f"Invalid JSON string provided: {e}", ephemeral=True)
            return
        except Exception as e: # Catch other potential errors during parsing
            await interaction.followup.send(f"Error parsing parameters: {e}", ephemeral=True)
            return

        async with get_db_session() as session:
            location, error = await add_location_master(session, interaction.guild_id, location_data)

        if error:
            await interaction.followup.send(f"Error adding location: {error}", ephemeral=True)
        elif location:
            await interaction.followup.send(f"Successfully added location: {location.static_id} (ID: {location.id})", ephemeral=True)
        else:
            await interaction.followup.send("Unknown error while adding location.", ephemeral=True)

    @master_map_group.command(name="remove_location", description="Remove a location.")
    @app_commands.describe(location_id="ID of the location to remove.")
    @is_administrator()
    async def remove_location_cmd(self, interaction: discord.Interaction, location_id: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None: # Should be caught by guild_only
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            success, error = await remove_location_master(session, interaction.guild_id, location_id)

        if error:
            await interaction.followup.send(f"Error removing location: {error}", ephemeral=True)
        elif success:
            await interaction.followup.send(f"Successfully removed location ID: {location_id}", ephemeral=True)
        else: # Should ideally not happen if error is None
            await interaction.followup.send("Failed to remove location for an unknown reason.", ephemeral=True)

    @master_map_group.command(name="connect_locations", description="Connect two locations.")
    @app_commands.describe(
        location_id_1="ID of the first location.",
        location_id_2="ID of the second location.",
        connection_type_i18n_json="Optional JSON for connection type (e.g., {\"en\": \"a path\", \"ru\": \"тропа\"})."
    )
    @is_administrator()
    async def connect_locations_cmd(self, interaction: discord.Interaction,
                                    location_id_1: int, location_id_2: int,
                                    connection_type_i18n_json: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None: # Should be caught by guild_only
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        conn_type = {"en": "a connection", "ru": "связь"} # Default connection type
        if connection_type_i18n_json:
            try:
                conn_type = json.loads(connection_type_i18n_json)
                if not isinstance(conn_type, dict): # Basic validation
                    raise json.JSONDecodeError("Connection type must be a JSON object.", connection_type_i18n_json, 0)
            except json.JSONDecodeError:
                await interaction.followup.send("Invalid JSON string for connection_type_i18n.", ephemeral=True)
                return

        async with get_db_session() as session:
            success, error = await connect_locations_master(session, interaction.guild_id, location_id_1, location_id_2, conn_type)

        if error:
            await interaction.followup.send(f"Error connecting locations: {error}", ephemeral=True)
        elif success:
            await interaction.followup.send(f"Successfully connected locations {location_id_1} and {location_id_2}.", ephemeral=True)
        else:
            await interaction.followup.send("Failed to connect locations.", ephemeral=True)

    @master_map_group.command(name="disconnect_locations", description="Disconnect two locations.")
    @app_commands.describe(location_id_1="ID of the first location.", location_id_2="ID of the second location.")
    @is_administrator()
    async def disconnect_locations_cmd(self, interaction: discord.Interaction, location_id_1: int, location_id_2: int):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None: # Should be caught by guild_only
            await interaction.followup.send("This command must be used in a guild.", ephemeral=True)
            return

        async with get_db_session() as session:
            success, error = await disconnect_locations_master(session, interaction.guild_id, location_id_1, location_id_2)

        if error:
            await interaction.followup.send(f"Error disconnecting locations: {error}", ephemeral=True)
        elif success:
            await interaction.followup.send(f"Successfully disconnected locations {location_id_1} and {location_id_2}.", ephemeral=True)
        else:
            await interaction.followup.send("Failed to disconnect locations.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MasterMapCog(bot))
    logger.info("MasterMapCog loaded.")
