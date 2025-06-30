from sqlalchemy import BigInteger, Column, ForeignKey, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import Index, UniqueConstraint
from typing import Optional, Dict, Any

from .base import Base
# Forward declaration for type hinting
# from typing import TYPE_CHECKING
# if TYPE_CHECKING:
#     from .guild import GuildConfig

class Ability(Base):
    __tablename__ = "abilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # guild_id is nullable because some abilities might be global templates,
    # while others could be guild-specific custom abilities.
    guild_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # guild: Mapped[Optional["GuildConfig"]] = relationship() # Optional

    static_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    # This ID is used to uniquely reference the ability, e.g., "fireball_lvl1", "heal_minor"
    # Uniqueness should be per guild if guild_id is not null, or global if guild_id is null.

    name_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, default=lambda: {})
    description_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, default=lambda: {})

    effects_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=lambda: {})
    # Example:
    # {
    #   "cost": {"resource": "mana", "amount": 10},
    #   "target": "enemy_single", # "self", "ally_single", "enemy_area", "ally_area"
    #   "range_meters": 15,
    #   "effects": [
    #     {"type": "damage", "damage_type": "fire", "amount_dice": "3d6", "bonus": 5},
    #     {"type": "apply_status", "status_static_id": "burning", "duration_turns": 3, "chance_percent": 75}
    #   ],
    #   "animation_hint": "fireball_explosion",
    #   "sound_hint": "fireball_whoosh"
    # }

    # Uniqueness: static_id should be unique globally if guild_id is NULL.
    # If guild_id is NOT NULL, static_id should be unique for that guild.
    # This can be handled by two separate unique constraints with conditions (PostgreSQL specific)
    # or by ensuring application logic maintains this.
    # A simpler approach is a composite unique constraint on (guild_id, static_id)
    # where NULL guild_id is treated as a distinct value (if DB supports it, e.g. PostgreSQL's NULLS NOT DISTINCT).
    # For broader compatibility, often two partial unique indexes are used or application layer enforcement.
    # Let's use a standard UniqueConstraint and note that for global abilities (guild_id IS NULL),
    # the application or DB admin must ensure static_id is globally unique among them.
    __table_args__ = (
        UniqueConstraint('guild_id', 'static_id', name='uq_ability_guild_static_id'),
        # To make static_id globally unique when guild_id IS NULL, a partial index would be:
        # Index('ix_ability_global_static_id', 'static_id', unique=True, postgresql_where=Column('guild_id').is_(None)),
        # For now, the UniqueConstraint above will enforce uniqueness for specific guilds, and for all entries where guild_id is NULL together.
    )

    def __repr__(self) -> str:
        return f"<Ability(id={self.id}, static_id='{self.static_id}', guild_id={self.guild_id}, name='{self.name_i18n.get('en', 'N/A')}')>"
