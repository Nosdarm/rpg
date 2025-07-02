import logging
from typing import TYPE_CHECKING, Optional, Dict, Any, List

from sqlalchemy import BigInteger, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import UniqueConstraint

from .base import Base

if TYPE_CHECKING:
    from .guild import GuildConfig

logger = logging.getLogger(__name__)

class Ability(Base):
    """
    Represents an ability that can be used by entities in the game.
    Abilities can be global (guild_id is NULL) or guild-specific.
    """
    __tablename__ = "abilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    static_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, default=lambda: {})
    description_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, default=lambda: {})
    properties_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=lambda: {})
    # Example for properties_json:
    # {
    #   "cost": {"resource": "mana", "amount": 10},
    #   "target_type": "enemy_single", # "self", "ally_single", "enemy_area", "ally_area", "none"
    #   "range_meters": 15, # Optional, applies if target_type is not "self" or "none"
    #   "effects": [
    #     {"type": "damage", "damage_type": "fire", "amount_dice": "3d6", "bonus": 5},
    #     {"type": "apply_status", "status_static_id": "burning", "duration_turns": 3, "chance_percent": 75},
    #     {"type": "heal", "amount_dice": "2d8", "bonus": 10},
    #     {"type": "resource_change", "resource": "mana", "amount": -5} // cost can also be an effect
    #   ],
    #   "requirements": { // Optional
    #       "level": 5,
    #       "attributes": {"strength": 12},
    #       "skills": {"fire_magic": 2}
    #   },
    #   "animation_hint": "fireball_explosion", // Optional
    #   "sound_hint": "fireball_whoosh" // Optional
    # }

    # --- Relationships ---
    guild: Mapped[Optional["GuildConfig"]] = relationship(back_populates="abilities")

    __table_args__ = (
        UniqueConstraint('guild_id', 'static_id', name='uq_ability_guild_static_id'),
        # Note: For true global static_id uniqueness (where guild_id IS NULL),
        # a partial index is typically needed in PostgreSQL:
        # Index('ix_ability_global_static_id', 'static_id', unique=True, postgresql_where=Column('guild_id').is_(None))
        # The UniqueConstraint on (guild_id, static_id) handles uniqueness for guild-specific abilities
        # and for all global abilities (guild_id IS NULL) as a group.
        # If multiple global abilities need the same static_id, this constraint alone is not sufficient without partial indexes.
        # For this model, we assume static_id for global abilities must be globally unique.
    )

    def __repr__(self) -> str:
        name_en = self.name_i18n.get('en', self.static_id) if self.name_i18n else self.static_id
        return (
            f"<Ability(id={self.id}, static_id='{self.static_id}', "
            f"guild_id={self.guild_id}, name='{name_en}')>"
        )

logger.info("Ability model defined")
