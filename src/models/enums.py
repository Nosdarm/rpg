import enum

class PlayerStatus(enum.Enum):
    """
    Represents the current status of a player character.
    """
    UNKNOWN = "unknown"            # Default or error state
    IDLE = "idle"                  # Player is in a safe area, not actively doing much
    EXPLORING = "exploring"        # Player is actively moving around, looking for content
    COMBAT = "combat"              # Player is engaged in combat
    DIALOGUE = "dialogue"          # Player is in a conversation with an NPC
    TRADING = "trading"            # Player is interacting with a shop or another player for trade
    MENU = "menu"                  # Player is interacting with a game menu (e.g., inventory, stats)
    AWAY = "away"                  # Player is AFK or otherwise temporarily inactive
    DEAD = "dead"                  # Player character is incapacitated
    AWAITING_MODERATION = "awaiting_moderation" # Player action requires GM approval
    PROCESSING_ACTION = "processing_action" # Player's action is currently being processed by the system

class PartyTurnStatus(enum.Enum):
    """
    Represents the current turn status of a party in turn-based gameplay.
    """
    UNKNOWN = "unknown"            # Default or error state
    ACTIVE_TURN = "active_turn"    # It's this party's turn to act
    PROCESSING_ACTIONS = "processing_actions" # The system is resolving actions for this party's turn
    WAITING_FOR_MEMBERS = "waiting_for_members" # Waiting for all party members to submit their actions
    TURN_ENDED = "turn_ended"      # Party has finished their turn, awaiting next cycle
    AWAITING_MODERATION = "awaiting_moderation" # Party actions/turn outcome requires GM approval
    IDLE = "idle"                  # Party is not in active turn-based gameplay (e.g., exploring)

# Example of how these might be used in a model:
# from sqlalchemy import Enum as SQLAlchemyEnum
# from sqlalchemy.orm import Mapped, mapped_column
# from .base import Base # Assuming Base is your declarative base
#
# class Player(Base):
#     __tablename__ = "players"
#     # ... other columns
#     status: Mapped[PlayerStatus] = mapped_column(SQLAlchemyEnum(PlayerStatus), default=PlayerStatus.IDLE)

# class Party(Base):
#     __tablename__ = "parties"
#     # ... other columns
#     turn_status: Mapped[PartyTurnStatus] = mapped_column(SQLAlchemyEnum(PartyTurnStatus), default=PartyTurnStatus.IDLE)

import logging
logger = logging.getLogger(__name__)
logger.info("Game-specific Enums (PlayerStatus, PartyTurnStatus) defined.")
