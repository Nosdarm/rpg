# src/bot/commands/map_commands.py
import json
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session, transactional
from src.core.map_management import (
    add_location_master,
    remove_location_master,
    connect_locations_master,
    disconnect_locations_master
)
from src.core.world_generation import generate_new_location_via_ai
from src.config import settings # Для проверки ID Мастера/Админа

logger = logging.getLogger(__name__)

# Группа команд для Мастера, связанная с картой
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True) # Только администраторы по умолчанию
class MapMasterCog(commands.GroupCog, name="master_map", description="Master commands for map management."):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()

    async def cog_check(self, interaction: discord.Interaction) -> bool:
        # Дополнительная проверка, если default_permissions недостаточно
        # или если есть список Мастеров в конфиге
        is_admin = interaction.user.guild_permissions.administrator
        is_bot_owner = await self.bot.is_owner(interaction.user)
        # Можно добавить проверку на ID из списка MASTER_IDS в settings
        is_master = str(interaction.user.id) in (settings.MASTER_IDS or [])

        if not (is_admin or is_bot_owner or is_master):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="generate_location", description="Generate a new location using AI.")
    @app_commands.describe(
        generation_params_json="Optional JSON string with parameters for AI generation (e.g., {\"theme\": \"swamp\"}).",
        context_location_id="Optional ID of a nearby location to provide context for generation.",
        context_player_id="Optional ID of a player to provide context for generation."
    )
    async def generate_location(
        self,
        interaction: discord.Interaction,
        generation_params_json: Optional[str] = None,
        context_location_id: Optional[int] = None,
        context_player_id: Optional[int] = None
    ):
        """Generates a new location using AI."""
        assert interaction.guild_id is not None
        guild_id_int: int = interaction.guild_id

        await interaction.response.defer(ephemeral=True)

        gen_params = None
        if generation_params_json:
            try:
                gen_params = json.loads(generation_params_json)
            except json.JSONDecodeError:
                await interaction.followup.send("Invalid JSON in generation_params_json.", ephemeral=True)
                return

        async with get_db_session() as session:
            location, error = await generate_new_location_via_ai(
                session=session,
                guild_id=guild_id_int,
                generation_params=gen_params,
                location_id_context=context_location_id,
                player_id_context=context_player_id
            )

        if error:
            await interaction.followup.send(f"Error generating location: {error}", ephemeral=True)
        elif location:
            await interaction.followup.send(
                f"Successfully generated location: {location.name_i18n.get('en', location.static_id or 'N/A')} (ID: {location.id})",
                ephemeral=True
            )
        else:
            await interaction.followup.send("Unknown error during location generation.", ephemeral=True)

    @app_commands.command(name="add_location", description="Manually add a new location.")
    @app_commands.describe(location_data_json="JSON string with all location data (static_id, name_i18n, etc.).")
    async def add_location(self, interaction: discord.Interaction, location_data_json: str):
        """Manually adds a new location."""
        assert interaction.guild_id is not None
        guild_id_int: int = interaction.guild_id
        await interaction.response.defer(ephemeral=True)

        try:
            location_data = json.loads(location_data_json)
        except json.JSONDecodeError:
            await interaction.followup.send("Invalid JSON provided for location data.", ephemeral=True)
            return

        async with get_db_session() as session:
            location, error = await add_location_master(session, guild_id_int, location_data)

        if error:
            await interaction.followup.send(f"Error adding location: {error}", ephemeral=True)
        elif location:
            await interaction.followup.send(
                f"Successfully added location: {location.name_i18n.get('en', location.static_id)} (ID: {location.id})",
                ephemeral=True
            )
        else:
            await interaction.followup.send("Unknown error while adding location.", ephemeral=True)

    @app_commands.command(name="remove_location", description="Remove an existing location.")
    @app_commands.describe(location_id="The ID of the location to remove.")
    async def remove_location(self, interaction: discord.Interaction, location_id: int):
        """Removes an existing location."""
        assert interaction.guild_id is not None
        guild_id_int: int = interaction.guild_id
        await interaction.response.defer(ephemeral=True)

        async with get_db_session() as session:
            success, error = await remove_location_master(session, guild_id_int, location_id)

        if error:
            await interaction.followup.send(f"Error removing location: {error}", ephemeral=True)
        elif success:
            await interaction.followup.send(f"Successfully removed location ID: {location_id}", ephemeral=True)
        else:
            # This case implies success was False but no specific error string was returned (should be rare)
            await interaction.followup.send(f"Failed to remove location ID: {location_id}. It might not exist or belong to this guild.", ephemeral=True)


    @app_commands.command(name="connect_locations", description="Connect two locations.")
    @app_commands.describe(
        location1_id="ID of the first location.",
        location2_id="ID of the second location.",
        connection_type_json="JSON string for connection type (e.g., {\"en\": \"a path\", \"ru\": \"тропа\"})."
    )
    async def connect_locations(
        self,
        interaction: discord.Interaction,
        location1_id: int,
        location2_id: int,
        connection_type_json: str
    ):
        """Connects two locations."""
        assert interaction.guild_id is not None
        guild_id_int: int = interaction.guild_id
        await interaction.response.defer(ephemeral=True)

        try:
            connection_type = json.loads(connection_type_json)
            if not isinstance(connection_type, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in connection_type.items()):
                raise json.JSONDecodeError("Connection type must be a JSON object of string key-value pairs.", "", 0)
        except json.JSONDecodeError as e:
            await interaction.followup.send(f"Invalid JSON for connection type: {e}", ephemeral=True)
            return

        async with get_db_session() as session:
            success, error = await connect_locations_master(
                session, guild_id_int, location1_id, location2_id, connection_type
            )

        if error:
            await interaction.followup.send(f"Error connecting locations: {error}", ephemeral=True)
        elif success:
            await interaction.followup.send(f"Successfully connected locations {location1_id} and {location2_id}.", ephemeral=True)
        else:
            await interaction.followup.send(f"Failed to connect locations.", ephemeral=True) # Generic if success=False, error=None

    @app_commands.command(name="disconnect_locations", description="Disconnect two locations.")
    @app_commands.describe(
        location1_id="ID of the first location.",
        location2_id="ID of the second location."
    )
    async def disconnect_locations(
        self,
        interaction: discord.Interaction,
        location1_id: int,
        location2_id: int
    ):
        """Disconnects two locations."""
        assert interaction.guild_id is not None
        guild_id_int: int = interaction.guild_id
        await interaction.response.defer(ephemeral=True)

        async with get_db_session() as session:
            success, error = await disconnect_locations_master(
                session, guild_id_int, location1_id, location2_id
            )

        if error:
            await interaction.followup.send(f"Error disconnecting locations: {error}", ephemeral=True)
        elif success:
            await interaction.followup.send(f"Successfully disconnected locations {location1_id} and {location2_id}.", ephemeral=True)
        else:
            await interaction.followup.send(f"Failed to disconnect locations.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MapMasterCog(bot))
    logger.info("MapMasterCog loaded.")

# В src/bot/core.py нужно будет добавить 'src.bot.commands.map_commands' в список когов для загрузки.
# В src/config/settings.py нужно добавить переменную MASTER_IDS (список строк ID пользователей-мастеров).
# Пример в .env: MASTER_IDS="123456789012345678,987654321098765432" (через запятую)
# В settings.py: MASTER_IDS = os.getenv("MASTER_IDS", "").split(',') if os.getenv("MASTER_IDS") else []
