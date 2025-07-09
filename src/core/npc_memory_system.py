import logging
from typing import Optional, Dict, Any, Union, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func # Added for func.now()

from ..models.player_npc_memory import PlayerNpcMemory
from ..models.party_npc_memory import PartyNpcMemory
from .crud.crud_player_npc_memory import crud_player_npc_memory
from .crud.crud_party_npc_memory import crud_party_npc_memory
# Placeholder for future imports like Player, Party, GeneratedNpc for validation
# from ..models.player import Player
# from ..models.party import Party
# from ..models.generated_npc import GeneratedNpc
# from .crud.crud_player import player_crud
# from .crud.crud_party import party_crud
# from .crud.crud_npc import npc_crud


logger = logging.getLogger(__name__)

async def add_to_npc_memory(
    session: AsyncSession,
    guild_id: int,
    npc_id: int,
    event_type: str,
    details: Dict[str, Any],
    player_id: Optional[int] = None,
    party_id: Optional[int] = None
) -> Union[PlayerNpcMemory, PartyNpcMemory, None]:
    """
    Adds a memory entry for an NPC regarding a player or a party.
    One of player_id or party_id must be provided.
    """
    """
    Adds a memory entry for an NPC regarding a player or a party.
    One of player_id or party_id must be provided.
    The 'details' dict will be stored in the 'memory_data_json' field.
    """
    logger.debug(
        f"Adding NPC memory: guild_id={guild_id}, npc_id={npc_id}, event_type='{event_type}', "
        f"player_id={player_id}, party_id={party_id}, details={details}"
    )

    if player_id and party_id:
        logger.error("add_to_npc_memory called with both player_id and party_id. Aborting.")
        # Consider raising ValueError for clearer error handling by caller
        return None
    if not player_id and not party_id:
        logger.error("add_to_npc_memory called with neither player_id nor party_id. Aborting.")
        # Consider raising ValueError
        return None

    # TODO: Optional: Validate existence of guild_id, npc_id, player_id/party_id
    # This might involve querying player_crud, party_crud, npc_crud, guild_crud.
    # For now, we assume valid IDs are passed.

    timestamp = func.now() # Using SQLAlchemy func for server-side timestamp if possible, or datetime.utcnow()

    try:
        if player_id:
            memory_obj_in = {
                "guild_id": guild_id,
                "player_id": player_id,
                "npc_id": npc_id,
                "event_type": event_type,
                "memory_data_json": details,
                "memory_details_i18n": {}, # Default to empty for now
                "timestamp": timestamp,
            }
            created_memory = await crud_player_npc_memory.create(session, obj_in=memory_obj_in) # type: ignore
            logger.info(f"PlayerNpcMemory created (ID: {created_memory.id}) for player {player_id}, NPC {npc_id}.")
            return created_memory
        elif party_id:
            memory_obj_in = {
                "guild_id": guild_id,
                "party_id": party_id,
                "npc_id": npc_id,
                "event_type": event_type,
                "memory_data_json": details,
                "memory_details_i18n": {}, # Default to empty for now
                "timestamp": timestamp,
            }
            created_memory = await crud_party_npc_memory.create(session, obj_in=memory_obj_in) # type: ignore
            logger.info(f"PartyNpcMemory created (ID: {created_memory.id}) for party {party_id}, NPC {npc_id}.")
            return created_memory
    except Exception as e:
        logger.error(f"Error creating NPC memory entry: {e}", exc_info=True)
        # Depending on transaction management, session.rollback() might be needed here if not handled by a decorator
        return None

    return None # Should not be reached if logic is correct

async def get_npc_memory(
    session: AsyncSession,
    guild_id: int,
    npc_id: int,
    player_id: Optional[int] = None,
    party_id: Optional[int] = None,
    limit: int = 100
) -> Sequence[Union[PlayerNpcMemory, PartyNpcMemory]]:
    """
    Retrieves memory entries for an NPC regarding a player or a party.
    One of player_id or party_id must be provided.
    """
    """
    Retrieves memory entries for an NPC regarding a player or a party.
    One of player_id or party_id must be provided.
    Results are ordered by timestamp descending (newest first).
    """
    logger.debug(
        f"Getting NPC memory: guild_id={guild_id}, npc_id={npc_id}, "
        f"player_id={player_id}, party_id={party_id}, limit={limit}"
    )

    if player_id and party_id:
        logger.error("get_npc_memory called with both player_id and party_id. Aborting.")
        # Consider raising ValueError
        return []
    if not player_id and not party_id:
        logger.error("get_npc_memory called with neither player_id nor party_id. Aborting.")
        # Consider raising ValueError
        return []

    try:
        if player_id:
            memories = await crud_player_npc_memory.get_multi_by_player_and_npc(
                session,
                guild_id=guild_id,
                player_id=player_id,
                npc_id=npc_id,
                limit=limit
            )
            return memories
        elif party_id:
            memories = await crud_party_npc_memory.get_multi_by_party_and_npc(
                session,
                guild_id=guild_id,
                party_id=party_id,
                npc_id=npc_id,
                limit=limit
            )
            return memories
    except Exception as e:
        logger.error(f"Error retrieving NPC memory entries: {e}", exc_info=True)
        return []

    return [] # Should not be reached

logger.info("NPC Memory System module loaded.")
