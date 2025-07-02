from sqlalchemy import BigInteger, Column, ForeignKey, Integer, JSON, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import Index, UniqueConstraint
from sqlalchemy import Enum as SQLAlchemyEnum
from typing import Optional, Dict, Any

from .base import Base
from .enums import RelationshipEntityType # Reusing for entities that can have statuses

# Forward declaration for type hinting
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .guild import GuildConfig
#     from .ability import Ability # Not directly needed for StatusEffect relationship itself
    # Entities (Player, Npc, etc.)

class StatusEffect(Base):
    """
    Defines a type of status effect (buff, debuff, condition).
    """
    __tablename__ = "status_effects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # guild_id is nullable for global/template status effects.
    guild_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    guild: Mapped[Optional["GuildConfig"]] = relationship(back_populates="status_effects")

    static_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    # Unique identifier, e.g., "poisoned_lvl1", "blessed_might", "stunned"

    name_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, default=lambda: {})
    description_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, default=lambda: {})

    effects_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=lambda: {})
    # Example:
    # {
    #   "type": "debuff", # "buff", "neutral_condition"
    #   "duration_type": "turns", # "seconds", "permanent_while_active"
    #   "max_duration": 5, # if applicable
    #   "modifiers": [
    #     {"stat": "dexterity", "change_absolute": -2},
    #     {"stat": "damage_over_time", "damage_type": "poison", "amount_dice": "1d4", "interval_turns": 1}
    #   ],
    #   "behavior_flags": ["prevents_spellcasting", "visible_on_char_sheet"],
    #   "dispellable": true,
    #   "stackable": false, # or {"max_stacks": 3}
    #   "icon_hint": "status_poisoned_icon"
    # }

    __table_args__ = (
        UniqueConstraint('guild_id', 'static_id', name='uq_status_effect_guild_static_id'),
        # Index('ix_status_effect_global_static_id', 'static_id', unique=True, postgresql_where=Column('guild_id').is_(None)),
    )

    def __repr__(self) -> str:
        return f"<StatusEffect(id={self.id}, static_id='{self.static_id}', guild_id={self.guild_id}, name='{self.name_i18n.get('en', 'N/A')}')>"


class ActiveStatusEffect(Base):
    """
    Represents an instance of a StatusEffect applied to an entity.
    """
    __tablename__ = "active_status_effects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # guild_id where this active status exists. Necessary for partitioning.
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )

    entity_type: Mapped[RelationshipEntityType] = mapped_column(
        SQLAlchemyEnum(RelationshipEntityType, name="relationship_entity_type_enum", create_type=False), # Reusing existing enum
        nullable=False,
        index=True
    )
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # Refers to Player.id, GeneratedNpc.id, etc.

    status_effect_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("status_effects.id", ondelete="CASCADE"), index=True
    )
    status_effect: Mapped["StatusEffect"] = relationship()

    applied_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    duration_turns: Mapped[Optional[int]] = mapped_column(Integer, nullable=True) # Original duration if turn-based
    remaining_turns: Mapped[Optional[int]] = mapped_column(Integer, nullable=True) # Current remaining turns

    # If applied by an ability, store its ID for reference (e.g., for dispelling logic)
    source_ability_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("abilities.id", ondelete="SET NULL"), nullable=True
    )
    # source_ability: Mapped[Optional["Ability"]] = relationship()

    # For instance-specific data, e.g., if a status effect has variable potency based on application
    data_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True, default=lambda: {})
    # Example: {"applied_by_player_id": 123, "initial_damage_roll": 15}

    __table_args__ = (
        # An entity should generally not have multiple instances of the exact same status_effect_id active
        # unless the status is stackable and handled by multiple rows (less common) or within data_json.
        # This constraint assumes one active instance per status_effect type on an entity.
        UniqueConstraint('guild_id', 'entity_type', 'entity_id', 'status_effect_id', name='uq_active_status_entity_effect'),
        Index("ix_active_status_effects_entity", "guild_id", "entity_type", "entity_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<ActiveStatusEffect(id={self.id}, entity='{self.entity_type.value}:{self.entity_id}', "
            f"status_effect_id={self.status_effect_id}, remaining_turns={self.remaining_turns})>"
        )
