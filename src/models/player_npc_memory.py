from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
# from sqlalchemy.dialects.postgresql import JSONB # Removed
from typing import Optional, Dict, Any

from .base import Base
from .custom_types import JsonBForSQLite # Added

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

    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id", ondelete="CASCADE"), index=True
    )

    npc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("generated_npcs.id", ondelete="CASCADE"), index=True
    )

    event_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)

    memory_details_i18n: Mapped[Optional[Dict[str, str]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {}) # Changed
    memory_data_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {}) # Changed


    timestamp: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    ai_significance_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<PlayerNpcMemory(id={self.id}, player_id={self.player_id}, npc_id={self.npc_id}, "
            f"event_type='{self.event_type}', ts='{self.timestamp}')>"
        )
