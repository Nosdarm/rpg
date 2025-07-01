import logging
import asyncio # Added import
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Callable, Awaitable

from .database import get_db_session, transactional # Assuming transactional might be useful here or in called functions
from ..models import Player, Party, GuildConfig # GuildConfig might be needed for guild-specific turn rules
from ..models.enums import PlayerStatus, PartyTurnStatus

logger = logging.getLogger(__name__)

# In-memory store for guild turn processing locks. Key: guild_id, Value: True if processing.
_guild_turn_processing_locks = {}

async def _start_action_processing_worker(guild_id: int, entities_to_process: list[tuple[int, str]]):
    """
    Placeholder for the actual worker that processes actions (Task 6.11).
    entities_to_process is a list of tuples: (entity_id, entity_type: "player" | "party")
    """
    logger.info(f"[TURN_CONTROLLER] Worker for Task 6.11 (Action Processing) would start now for guild_id: {guild_id}.")
    logger.info(f"[TURN_CONTROLLER] Entities to process: {entities_to_process}")
    # In a real scenario, this would likely be:
    from .action_processor import process_actions_for_guild
    asyncio.create_task(process_actions_for_guild(guild_id, entities_to_process))
    # pass # No longer just pass


@transactional # Ensures DB operations within are atomic if this function itself does them.
async def process_guild_turn_if_ready(session: AsyncSession, guild_id: int):
    """
    Checks if a guild's turn can be processed and initiates it if conditions are met.
    This function is intended to be called after a player or party ends their turn.
    """
    logger.info(f"[TURN_CONTROLLER] Checking if guild turn can be processed for guild_id: {guild_id}")

    if _guild_turn_processing_locks.get(guild_id):
        logger.info(f"[TURN_CONTROLLER] Guild {guild_id} turn is already being processed. Skipping.")
        return

    # --- Condition Check (MVP) ---
    # For MVP, we assume that if this function is called, and not already locked,
    # we can try to process. A more robust check would verify if all *expected*
    # players/parties have submitted their turns.

    # Fetch players and parties that have ended their turn and are pending resolution
    stmt_players = select(Player).where(
        Player.guild_id == guild_id,
        Player.status == PlayerStatus.TURN_ENDED_PENDING_RESOLUTION
    )
    result_players = await session.execute(stmt_players)
    players_pending = result_players.scalars().all()

    stmt_parties = select(Party).where(
        Party.guild_id == guild_id,
        Party.turn_status == PartyTurnStatus.TURN_ENDED_PENDING_RESOLUTION
    )
    result_parties = await session.execute(stmt_parties)
    parties_pending = result_parties.scalars().all()

    if not players_pending and not parties_pending:
        logger.info(f"[TURN_CONTROLLER] No players or parties pending turn resolution for guild {guild_id}. Nothing to process.")
        return

    # --- Lock and Proceed ---
    _guild_turn_processing_locks[guild_id] = True
    logger.info(f"[TURN_CONTROLLER] Acquired processing lock for guild {guild_id}.")

    entities_for_action_module = []

    try:
        # Update statuses to PROCESSING_GUILD_TURN
        for player in players_pending:
            player.status = PlayerStatus.PROCESSING_GUILD_TURN
            session.add(player)
            entities_for_action_module.append({"id": player.id, "type": "player", "discord_id": player.discord_id})
            logger.info(f"[TURN_CONTROLLER] Player {player.id} status set to PROCESSING_GUILD_TURN.")

        for party in parties_pending:
            party.turn_status = PartyTurnStatus.PROCESSING_GUILD_TURN
            session.add(party)
            entities_for_action_module.append({"id": party.id, "type": "party", "name": party.name})
            logger.info(f"[TURN_CONTROLLER] Party {party.id} status set to PROCESSING_GUILD_TURN.")

            # Also update statuses of players within these parties if not already covered
            # (though they should have been set by /end_party_turn)
            for player_id_int in party.player_ids_json:
                member_player = await session.get(Player, player_id_int)
                if member_player and member_player.status != PlayerStatus.PROCESSING_GUILD_TURN:
                    # This is a safeguard or for players who were not individually processed
                    # but whose party is now being processed.
                    member_player.status = PlayerStatus.PROCESSING_GUILD_TURN
                    session.add(member_player)
                    logger.info(f"[TURN_CONTROLLER] Player {member_player.id} (in party {party.id}) status set to PROCESSING_GUILD_TURN.")


        # The commit for status updates should happen within the @transactional scope of this function
        # or, if called by another @transactional function, as part of that outer transaction.
        # For clarity, if this is the main entry point for this logic, @transactional here is good.

        # Call the (placeholder) async worker for the Action Processing Module (Task 6.11)
        # This should not block the current flow.
        # In a real scenario, use asyncio.create_task or a proper task queue system.
        if entities_for_action_module:
            logger.info(f"[TURN_CONTROLLER] Starting action processing worker for guild {guild_id} with entities: {entities_for_action_module}")
            # For MVP, we'll call it directly and it will be a simple log.
            # In a real app, this would be:
            import asyncio # Ensure asyncio is imported at the top of the file if not already
            asyncio.create_task(_start_action_processing_worker(guild_id, entities_for_action_module))
            # await _start_action_processing_worker(guild_id, entities_for_action_module) # No longer direct await
            logger.info(f"[TURN_CONTROLLER] Action processing worker task created for guild {guild_id}.")
        else:
            logger.info(f"[TURN_CONTROLLER] No entities to send to action processing worker for guild {guild_id}.")


    except Exception as e:
        logger.error(f"[TURN_CONTROLLER] Error during guild turn processing for guild {guild_id}: {e}", exc_info=True)
        # Rollback will be handled by @transactional if an error occurs before commit
        # Reset statuses if appropriate, or handle error states
    finally:
        _guild_turn_processing_locks.pop(guild_id, None)
        logger.info(f"[TURN_CONTROLLER] Released processing lock for guild {guild_id}.")

# This function will be called by the TurnManagementCog commands
async def trigger_guild_turn_processing(guild_id: int, session_maker: Callable[[], AsyncSession]):
    """
    Entry point to be called from the Cog after a player/party ends their turn.
    Manages its own session.
    """
    async with session_maker() as session:
        # The @transactional decorator on process_guild_turn_if_ready will handle its own begin/commit/rollback
        await process_guild_turn_if_ready(session, guild_id)

logger.info("Turn Controller module loaded.")
