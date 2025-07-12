from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Text, DateTime, func, JSON
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional, Dict, Any

from .base import Base

# Forward declaration for type hinting
# from typing import TYPE_CHECKING
# if TYPE_CHECKING:
#     from .guild import GuildConfig
#     from .party import Party
#     from .generated_npc import GeneratedNpc

class PartyNpcMemory(Base):
    __tablename__ = "party_npc_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )

    party_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("parties.id", ondelete="CASCADE"), index=True
    )

    npc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("generated_npcs.id", ondelete="CASCADE"), index=True
    )

    event_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)

    memory_details_i18n: Mapped[Optional[Dict[str, str]]] = mapped_column(JSON, nullable=True, default=lambda: {})
    memory_data_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, default=lambda: {})

    timestamp: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    ai_significance_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships (optional, can be added if needed for direct ORM-based access)
    # guild = relationship("GuildConfig", back_populates="party_npc_memories")
    # party = relationship("Party", back_populates="npc_memories")
    # npc = relationship("GeneratedNpc", back_populates="party_memories")


    def __repr__(self) -> str:
        return (
            f"<PartyNpcMemory(id={self.id}, party_id={self.party_id}, npc_id={self.npc_id}, "
            f"event_type='{self.event_type}', ts='{self.timestamp}')>"
        )
