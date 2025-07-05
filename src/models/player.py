from typing import Optional, Dict, Any, List, TYPE_CHECKING # Consolidated imports

from sqlalchemy import BigInteger, Column, ForeignKey, Integer, JSON, Text, Enum as SQLAlchemyEnum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import PlayerStatus # Import the PlayerStatus enum

if TYPE_CHECKING:
    from .location import Location
    from .party import Party
    from .quest import PlayerQuestProgress # Added for quest_progress relationship

class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )
    discord_id: Mapped[int] = mapped_column(BigInteger, index=True)

    name: Mapped[str] = mapped_column(Text, nullable=False)

    current_location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("locations.id"), nullable=True)
    selected_language: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="en") # Default to English

    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unspent_xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False) # Or points derived from XP
    gold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_hp: Mapped[Optional[int]] = mapped_column(Integer, nullable=True) # Current health points

    current_status: Mapped[PlayerStatus] = mapped_column(
        SQLAlchemyEnum(PlayerStatus, name="player_status_enum", create_constraint=True),
        default=PlayerStatus.IDLE,
        nullable=False
    )
    attributes_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=lambda: {}, nullable=False)

    collected_actions_json: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True) # Stores queued actions

    current_party_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("parties.id", use_alter=True, name="fk_player_current_party_id"), nullable=True)
    current_sublocation_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # New field for sub-location

    # Relationships
    location: Mapped[Optional["Location"]] = relationship(foreign_keys=[current_location_id])
    # Mypy might complain about "parties.id" if Party model is not yet defined or imported for TYPE_CHECKING.
    # It's fine for SQLAlchemy as it resolves strings at runtime.
    party: Mapped[Optional["Party"]] = relationship(foreign_keys=[current_party_id], back_populates="players", lazy="selectin") # Assuming Party.players backref
    quest_progress: Mapped[List["PlayerQuestProgress"]] = relationship(back_populates="player", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("guild_id", "discord_id", name="uq_player_guild_discord"),
        # Index("ix_players_current_location_id", "current_location_id"), # Already indexed by ForeignKey
        # Index("ix_players_current_party_id", "current_party_id"), # Already indexed by ForeignKey
    )

    def __repr__(self) -> str:
        return (f"<Player(id={self.id}, name='{self.name}', guild_id={self.guild_id}, "
                f"discord_id={self.discord_id}, level={self.level})>")
