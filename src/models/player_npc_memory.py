from sqlalchemy import BigInteger, Column, ForeignKey, Integer, JSON, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from typing import Optional, Dict, Any

from .base import Base
# Forward declaration for type hinting
# from typing import TYPE_CHECKING
# if TYPE_CHECKING:
#     from .guild import GuildConfig
#     from .player import Player
#     from .generated_npc import GeneratedNpc

class PlayerNpcMemory(Base):
    __tablename__ = "player_npc_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )
    # guild: Mapped["GuildConfig"] = relationship() # Optional

    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    # player: Mapped["Player"] = relationship() # Optional

    npc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("generated_npcs.id", ondelete="CASCADE"), index=True
    )
    # npc: Mapped["GeneratedNpc"] = relationship() # Optional

    event_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)
    # Describes the type of event or memory, e.g., "first_meeting", "completed_quest_for_npc",
    # "insulted_npc", "received_gift_from_npc". Could align with some EventType enum values or be more specific.

    memory_details_i18n: Mapped[Optional[Dict[str, str]]] = mapped_column(JSONB, nullable=True, default=lambda: {})
    # Example: {"en": "Player helped retrieve the amulet.", "ru": "Игрок помог вернуть амулет."}
    # Can also store more structured data if needed, though details_json might be better for that.

    memory_data_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True, default=lambda: {})
    # For more structured data related to the memory, e.g. {"quest_id": 12, "item_involved": 34}


    timestamp: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    ai_significance_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Optional score assigned by AI indicating the importance of this memory for future NPC behavior.

    # Consider a UniqueConstraint if a player can only have one memory of a specific event_type with an NPC.
    # However, memories are often chronological, so multiple "helped_npc" events might be valid.
    # UniqueConstraint('guild_id', 'player_id', 'npc_id', 'event_type', name='uq_player_npc_event_memory'),

    def __repr__(self) -> str:
        return (
            f"<PlayerNpcMemory(id={self.id}, player_id={self.player_id}, npc_id={self.npc_id}, "
            f"event_type='{self.event_type}', ts='{self.timestamp}')>"
        )
