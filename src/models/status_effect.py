from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    Enum as SQLAlchemyEnum
)
# from sqlalchemy.dialects.postgresql import JSONB # Removed
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.sqltypes import TIMESTAMP

from .base import Base
from .custom_types import JsonBForSQLite # Added
from .enums import StatusEffectCategory # type: ignore[reportMissingImports] # Import the actual enum

if TYPE_CHECKING:
    from .guild import GuildConfig


class StatusEffect(Base):
    __tablename__ = "status_effects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[Optional[int]] = mapped_column( # Changed to Optional[int] and nullable=True
        BigInteger, ForeignKey("guild_configs.id"), index=True, nullable=True
    )
    static_id: Mapped[str] = mapped_column(Text, index=True, nullable=False)
    name_i18n: Mapped[Dict[str, str]] = mapped_column(
        JsonBForSQLite, nullable=False, default=dict
    )
    description_i18n: Mapped[Dict[str, str]] = mapped_column(
        JsonBForSQLite, nullable=False, default=dict
    )
    properties_json: Mapped[Dict[str, Any]] = mapped_column(
        JsonBForSQLite, nullable=False, default=dict
    )  # e.g. {"modifiers": {"strength": -1}, "duration_turns": 5, "tick_effects": ["deal_damage_1d4_fire"]}

    category: Mapped[StatusEffectCategory] = mapped_column(
        SQLAlchemyEnum(StatusEffectCategory, name="status_effect_category_enum", create_constraint=True),
        nullable=False,
        default=StatusEffectCategory.NEUTRAL
    )

    # Relationships
    guild: Mapped["GuildConfig"] = relationship(back_populates="status_effects")

    __table_args__ = (
        UniqueConstraint("guild_id", "static_id", name="uq_status_effect_guild_static_id"),
    )

    def __repr__(self) -> str:
        return f"<StatusEffect(id={self.id}, static_id='{self.static_id}', guild_id={self.guild_id})>"


class ActiveStatusEffect(Base):
    __tablename__ = "active_status_effects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False) # ID of the Player, NPC, etc.
    entity_type: Mapped[str] = mapped_column(Text, index=True, nullable=False) # "player", "npc", "party_member_npc"
    status_effect_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("status_effects.id"), nullable=False
    )
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id"), index=True, nullable=False
    )
    applied_at: Mapped[TIMESTAMP] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    duration_turns: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    remaining_turns: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_ability_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True) # ID of the ability that applied this status
    source_entity_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True) # ID of the entity (Player, NPC) that caused this status
    source_entity_type: Mapped[Optional[str]] = mapped_column(Text, index=True, nullable=True) # "player", "npc" - type of the source entity
    custom_properties_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JsonBForSQLite, nullable=True
    ) # For overriding or adding properties to this specific instance

    # Relationships
    status_effect: Mapped["StatusEffect"] = relationship()
    guild: Mapped["GuildConfig"] = relationship(back_populates="active_status_effects")

    def __repr__(self) -> str:
        return f"<ActiveStatusEffect(id={self.id}, status_effect_id={self.status_effect_id}, entity_id={self.entity_id}, entity_type='{self.entity_type}', guild_id={self.guild_id})>"
