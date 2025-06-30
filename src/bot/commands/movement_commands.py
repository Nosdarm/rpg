import logging
import discord
from discord.ext import commands
from discord import app_commands # Required for slash commands

from src.core.movement_logic import handle_move_action

logger = logging.getLogger(__name__)

class MovementCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="move", description="Move your character to a connected location.")
    @app_commands.describe(target_location_static_id="The static ID of the location you want to move to.")
    async def move_command(
        self,
        interaction: discord.Interaction,
        target_location_static_id: str,
    ):
        """
        Allows the player to move to a specified location if it's a valid neighbor.
        """
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server (guild).", ephemeral=True
            )
            return

        if interaction.user is None:
            # Should not happen with slash commands from a guild context
            await interaction.response.send_message(
                "Could not identify the user.", ephemeral=True
            )
            return

        guild_id = interaction.guild.id
        player_discord_id = interaction.user.id

        await interaction.response.defer(ephemeral=False) # Acknowledge interaction, thinking...

        try:
            success, message = await handle_move_action(
                guild_id=guild_id,
                player_discord_id=player_discord_id,
                target_location_static_id=target_location_static_id,
            )

            if success:
                await interaction.followup.send(f"✅ {message}")
            else:
                await interaction.followup.send(f"❌ {message}")

        except Exception as e:
            logger.exception(
                f"Error processing /move command for player {player_discord_id} in guild {guild_id} "
                f"to {target_location_static_id}: {e}"
            )
            await interaction.followup.send(
                "An unexpected server error occurred while trying to move. Please try again later.",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(MovementCog(bot))
    logger.info("MovementCog loaded.")
