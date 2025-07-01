import discord
from discord import app_commands
from discord.ext import commands
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session, transactional
from src.core.player_utils import get_player_by_discord_id
from src.core.party_utils import get_party # Renamed from get_party_by_id as it doesn't exist
from src.models import Player, Party
from src.models.enums import PlayerStatus, PartyTurnStatus
# Import for turn_controller placeholder - will be created in next step
# from src.core.turn_controller import process_guild_turn_if_ready (or similar name)

logger = logging.getLogger(__name__)

class TurnManagementCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="end_turn", description="Signal that you have completed your actions for this turn.")
    @app_commands.guild_only()
    async def end_turn_command(self, interaction: discord.Interaction):
        """
        Allows a player to signal they have finished their turn.
        """
        assert interaction.guild_id is not None, "guild_id should not be None in a guild_only command"
        guild_id: int = interaction.guild_id
        player_discord_id = interaction.user.id
        session_maker = get_db_session

        async with session_maker() as session:
            async with session.begin():
                player = await get_player_by_discord_id(session, guild_id=guild_id, discord_id=player_discord_id)

                if not player:
                    await interaction.response.send_message("You are not currently registered as a player in this game. Use `/start`.", ephemeral=True)
                    return

                if player.current_party_id:
                    await interaction.response.send_message("You are in a party. Use `/end_party_turn` to end the turn for your party.", ephemeral=True)
                    return

                if player.current_status not in [PlayerStatus.EXPLORING, PlayerStatus.COMBAT]: # Add other active states if needed
                    await interaction.response.send_message(f"You cannot end your turn while your status is '{player.current_status.value}'.", ephemeral=True)
                    return

                player.current_status = PlayerStatus.TURN_ENDED_PENDING_RESOLUTION
                session.add(player)
                await session.commit() # Commit status change first

            # Call the core logic to check if the guild turn can be processed
            # This will be implemented in src.core.turn_controller
            try:
                from src.core.turn_controller import trigger_guild_turn_processing
                await trigger_guild_turn_processing(guild_id, session_maker)
                logger.info(f"Guild turn processing initiated for guild {guild_id} after player {player.name} ended turn.")
            except ImportError:
                logger.error("turn_controller or trigger_guild_turn_processing not found. Placeholder action for end_turn.")
            except Exception as e:
                logger.error(f"Error initiating guild turn processing for guild {guild_id} (called from end_turn): {e}", exc_info=True)


        await interaction.response.send_message("You have ended your turn. Waiting for other actions to resolve.", ephemeral=True)
        logger.info(f"Player {interaction.user.name} (Discord ID: {player_discord_id}) ended their turn in guild {guild_id}.")

    @app_commands.command(name="end_party_turn", description="Signal that your party has completed its actions for this turn.")
    @app_commands.guild_only()
    async def end_party_turn_command(self, interaction: discord.Interaction):
        """
        Allows a player in a party to signal their party has finished its turn.
        """
        assert interaction.guild_id is not None, "guild_id should not be None in a guild_only command"
        guild_id: int = interaction.guild_id
        player_discord_id = interaction.user.id
        session_maker = get_db_session

        async with session_maker() as session:
            async with session.begin():
                player = await get_player_by_discord_id(session, guild_id=guild_id, discord_id=player_discord_id)

                if not player:
                    await interaction.response.send_message("You are not currently registered as a player in this game. Use `/start`.", ephemeral=True)
                    return

                if not player.current_party_id:
                    await interaction.response.send_message("You are not currently in a party. Use `/end_turn` if you are playing solo.", ephemeral=True)
                    return

                party = await get_party(session, guild_id=guild_id, party_id=player.current_party_id) # Use the existing get_party function
                if not party:
                    # This case should ideally not happen if player.current_party_id is set
                    logger.error(f"Player {player.name} has current_party_id {player.current_party_id} but party not found in guild {guild_id}.")
                    await interaction.response.send_message("Error: Your party could not be found. Please contact an admin.", ephemeral=True)
                    return

                # TODO: Implement RuleConfig check for who can end party turn (e.g., leader_only or any_member)
                # For MVP, any member can end the party turn.

                if party.turn_status not in [PartyTurnStatus.AWAITING_PARTY_ACTION, PartyTurnStatus.IDLE]: # IDLE if they weren't in a turn sequence but initiated one
                     await interaction.response.send_message(f"The party cannot end its turn while its status is '{party.turn_status.value}'.", ephemeral=True)
                     return

                party.turn_status = PartyTurnStatus.TURN_ENDED_PENDING_RESOLUTION
                session.add(party)

                # Update status for all players in the party
                for member_player_id_int in (party.player_ids_json or []): # Assuming player_ids_json stores integer IDs
                    member_player = await session.get(Player, member_player_id_int) # Fetch by PK
                    if member_player and member_player.guild_id == guild_id : # Ensure player belongs to the same guild
                        member_player.current_status = PlayerStatus.TURN_ENDED_PENDING_RESOLUTION
                        session.add(member_player)
                    elif member_player:
                        logger.warning(f"Player {member_player_id_int} in party {party.id} but from different guild {member_player.guild_id} vs {guild_id}")
                    else:
                        logger.warning(f"Player ID {member_player_id_int} listed in party {party.id} not found.")

                await session.commit() # Commit status changes

            # Call the core logic to check if the guild turn can be processed
            try:
                from src.core.turn_controller import trigger_guild_turn_processing
                await trigger_guild_turn_processing(guild_id, session_maker)
                logger.info(f"Guild turn processing initiated for guild {guild_id} after party {party.name} ended turn.")
            except ImportError:
                logger.error("turn_controller or trigger_guild_turn_processing not found. Placeholder action for end_party_turn.")
            except Exception as e:
                logger.error(f"Error initiating guild turn processing for guild {guild_id} (called from end_party_turn): {e}", exc_info=True)

        await interaction.response.send_message(f"Your party '{party.name}' has ended its turn. Waiting for other actions to resolve.", ephemeral=True)
        logger.info(f"Player {interaction.user.name} (Discord ID: {player_discord_id}) ended the turn for party {party.name} (ID: {party.id}) in guild {guild_id}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(TurnManagementCog(bot))
    logger.info("TurnManagementCog loaded.")
