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

class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # guild_id is nullable because some skills might be global templates,
    # while others could be guild-specific custom skills.
    guild_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # guild: Mapped[Optional["GuildConfig"]] = relationship() # Optional

    static_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    # This ID is used to uniquely reference the skill, e.g., "swordsmanship", "alchemy_novice"
    # Uniqueness considerations similar to Ability model (global if guild_id is NULL, per-guild otherwise).

    name_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, default=lambda: {})
    description_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, default=lambda: {})

    # Could store the primary attribute(s) this skill is related to, for reference or calculations.
    # e.g., {"en": "Dexterity", "ru": "Ловкость"} or ["dexterity", "intelligence"]
    related_attribute_i18n: Mapped[Optional[Dict[str, str]]] = mapped_column(JSONB, nullable=True, default=lambda: {})

    # Other properties for the skill definition if needed, e.g., prerequisites, max level.
    properties_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True, default=lambda: {})
    # Example:
    # {
    #   "max_level": 5,
    #   "synergies_with": ["skill_static_id_X", "skill_static_id_Y"],
    #   "category": "combat" # or "crafting", "social", etc.
    # }

    # Players/NPCs would have their skill levels stored in a separate association table (e.g., PlayerSkillLevels)
    # or as part of their own properties_json if skills are not deeply queryable by level across entities.
    # For schema finalization, defining the Skill itself is the first step.
    # An EntitySkillLink table might look like:
    #   entity_id, entity_type, skill_id, guild_id, current_level, current_xp

    __table_args__ = (
        UniqueConstraint('guild_id', 'static_id', name='uq_skill_guild_static_id'),
        # Similar to Ability, for global skills (guild_id IS NULL), application or DB admin must ensure static_id is globally unique.
        # Index('ix_skill_global_static_id', 'static_id', unique=True, postgresql_where=Column('guild_id').is_(None)),
    )

    def __repr__(self) -> str:
        return f"<Skill(id={self.id}, static_id='{self.static_id}', guild_id={self.guild_id}, name='{self.name_i18n.get('en', 'N/A')}')>"
