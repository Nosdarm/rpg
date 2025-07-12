from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import Index
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from .base import Base
from ..core.database import JsonBForSQLite
# Forward declaration for type hinting
if TYPE_CHECKING:
#     from .guild import GuildConfig # Not strictly needed if only using guild_id
    from .generated_npc import GeneratedNpc # For relationship

class GeneratedFaction(Base):
    __tablename__ = "generated_factions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )
    # guild: Mapped["GuildConfig"] = relationship() # Optional

    static_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True) # Unique within a guild

    name_i18n: Mapped[Dict[str, str]] = mapped_column(JsonBForSQLite, nullable=False, default=lambda: {})
    description_i18n: Mapped[Dict[str, str]] = mapped_column(JsonBForSQLite, nullable=False, default=lambda: {})
    ideology_i18n: Mapped[Optional[Dict[str, str]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {}) # e.g., {"en": "Seeks balance", "ru": "Ищет равновесие"}

    leader_npc_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("generated_npcs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # leader_npc: Mapped[Optional["GeneratedNpc"]] = relationship() # Optional

    resources_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {})
    # Example:
    # {
    #   "wealth": 10000,
    #   "manpower": 500,
    #   "influence_points": 75
    # }

    ai_metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {})
    # Example:
    # {
    #   "archetype": "shadowy cabal",
    #   "goals": ["control trade routes", "undermine rival faction X"]
    # }

    # Relationships
    members: Mapped[List["GeneratedNpc"]] = relationship(
        back_populates="faction",
        foreign_keys="GeneratedNpc.faction_id"  # Specify the foreign key on the GeneratedNpc table
    )


    __table_args__ = (
        Index("ix_generated_factions_guild_id_static_id", "guild_id", "static_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<GeneratedFaction(id={self.id}, guild_id={self.guild_id}, static_id='{self.static_id}', name='{self.name_i18n.get('en', 'N/A')}')>"
