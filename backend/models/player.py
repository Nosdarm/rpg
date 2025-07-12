from typing import Optional, Dict, Any, List, TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, Text, Enum as SQLAlchemyEnum, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import PlayerStatus, OwnerEntityType
from .inventory_item import InventoryItem

if TYPE_CHECKING:
    from .location import Location
    from .party import Party
    from .quest import PlayerQuestProgress
    from backend.models.guild import GuildConfig

class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    discord_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)

    name: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, default="en", nullable=False)

    current_location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("locations.id"), nullable=True)
    current_party_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("parties.id", use_alter=True, name="fk_player_current_party_id"), nullable=True)

    current_status: Mapped[PlayerStatus] = mapped_column(
        SQLAlchemyEnum(PlayerStatus, name="player_status_enum", create_constraint=True),
        default=PlayerStatus.IDLE,
        nullable=False,
    )

    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    gold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hp: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    unspent_xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    attributes_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    collected_actions_json: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, nullable=True)

    # Relationships
    guild_config: Mapped["GuildConfig"] = relationship(back_populates="players")
    location: Mapped[Optional["Location"]] = relationship(foreign_keys=[current_location_id])
    party: Mapped[Optional["Party"]] = relationship(back_populates="members", foreign_keys=[current_party_id])
    inventory_items: Mapped[List["InventoryItem"]] = relationship(
        primaryjoin=f"and_(Player.id==InventoryItem.owner_entity_id, InventoryItem.owner_entity_type=='{OwnerEntityType.PLAYER.value}')",
        foreign_keys=[InventoryItem.owner_entity_id, InventoryItem.owner_entity_type],
        back_populates="player_owner",
        cascade="all, delete-orphan",
    )
    quest_progress: Mapped[List["PlayerQuestProgress"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("guild_id", "discord_user_id", name="uq_player_guild_discord"),
    )

    def __repr__(self) -> str:
        return (
            f"<Player(id={self.id}, name='{self.name}', guild_id={self.guild_id}, "
            f"discord_user_id={self.discord_user_id}, level={self.level})>"
        )
