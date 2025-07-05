from typing import Optional, List, Dict, Any, TYPE_CHECKING

from sqlalchemy import BigInteger, Column, ForeignKey, Integer, JSON, Text, Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import PartyTurnStatus # Import the PartyTurnStatus enum

if TYPE_CHECKING:
    from .location import Location
    from .player import Player # For relationship back_populates


class Party(Base):
    __tablename__ = "parties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)

    # Stores a list of Player primary key IDs.
    player_ids_json: Mapped[Optional[List[int]]] = mapped_column(JSON, nullable=True)
    leader_player_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("players.id", name="fk_party_leader_player_id", use_alter=True), nullable=True, index=True)

    current_location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("locations.id"), nullable=True)

    turn_status: Mapped[PartyTurnStatus] = mapped_column(
        SQLAlchemyEnum(PartyTurnStatus, name="party_turn_status_enum", create_constraint=True),
        default=PartyTurnStatus.IDLE,
        nullable=False
    )

    # Relationships
    location: Mapped[Optional["Location"]] = relationship(foreign_keys=[current_location_id])

    # This establishes the other side of the Player.party relationship
    # Players in this party can be accessed via this relationship.
    # If player_ids_json is the source of truth, this relationship might be more for convenience
    # or could be managed dynamically based on player_ids_json.
    # For now, defining it to match Player.party's back_populates.
    players: Mapped[List["Player"]] = relationship(back_populates="party", primaryjoin="Player.current_party_id == Party.id", lazy="selectin")
    leader: Mapped[Optional["Player"]] = relationship(foreign_keys=[leader_player_id], lazy="selectin")


    def __repr__(self) -> str:
        return (f"<Party(id={self.id}, name='{self.name}', guild_id={self.guild_id}, "
                f"member_count={len(self.player_ids_json) if self.player_ids_json else 0})>")
