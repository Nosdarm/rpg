from typing import Optional, List, Dict, Any, TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, Text, Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import PartyTurnStatus

if TYPE_CHECKING:
    from .location import Location
    from .player import Player
    from backend.models.guild import GuildConfig

class Party(Base):
    __tablename__ = "parties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True, nullable=False
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    leader_player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), nullable=False)
    player_ids_json: Mapped[List[int]] = mapped_column(JSONB, default=list, nullable=False)

    current_location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("locations.id"), nullable=True)

    turn_status: Mapped[PartyTurnStatus] = mapped_column(
        SQLAlchemyEnum(PartyTurnStatus, name="party_turn_status_enum", create_constraint=True),
        default=PartyTurnStatus.IDLE,
        nullable=False,
    )

    properties_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Relationships
    guild_config: Mapped["GuildConfig"] = relationship(back_populates="parties")
    leader: Mapped["Player"] = relationship(foreign_keys=[leader_player_id])
    current_location: Mapped[Optional["Location"]] = relationship(foreign_keys=[current_location_id])
    members: Mapped[List["Player"]] = relationship(
        back_populates="party",
        primaryjoin="foreign(Player.current_party_id) == Party.id",
    )

    def __repr__(self) -> str:
        return (
            f"<Party(id={self.id}, name='{self.name}', guild_id={self.guild_id}, "
            f"member_count={len(self.player_ids_json) if self.player_ids_json else 0})>"
        )
