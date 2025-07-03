from typing import TYPE_CHECKING, Dict, Any, List # Added List
from sqlalchemy import BigInteger, ForeignKey, Text, UniqueConstraint # Removed Integer
# from sqlalchemy.dialects.postgresql import JSONB # Removed direct JSONB import
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .custom_types import JsonBForSQLite # Import custom type

if TYPE_CHECKING:
    from .guild import GuildConfig


class Ability(Base):
    """
    Represents an ability that can be used by entities in the game.
    Abilities are strictly guild-scoped in this iteration.
    """
    __tablename__ = "abilities"

    id: Mapped[int] = mapped_column(primary_key=True, index=True) # Integer is fine for PK
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), nullable=False, index=True) # Changed to nullable=False, added ondelete
    static_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    name_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, server_default='{}')
    description_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, server_default='{}')
    properties_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default='{}')
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


    # Relationships
    guild: Mapped["GuildConfig"] = relationship(back_populates="abilities") # Kept as GuildConfig, will be non-optional due to nullable=False guild_id

    __table_args__ = (
        UniqueConstraint("guild_id", "static_id", name="uq_ability_guild_static_id"),
    )

    def __repr__(self) -> str:
        name_en = self.name_i18n.get('en', self.static_id) if self.name_i18n else self.static_id
        return (
            f"<Ability(id={self.id}, static_id='{self.static_id}', "
            f"guild_id={self.guild_id}, name='{name_en}')>"
        )
