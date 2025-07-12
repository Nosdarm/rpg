from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
# from sqlalchemy.dialects.postgresql import JSONB # Removed
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

    guild_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), nullable=True, index=True
    )

    static_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    name_i18n: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False, default=lambda: {}) # Changed
    description_i18n: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False, default=lambda: {}) # Changed

    related_attribute_i18n: Mapped[Optional[Dict[str, str]]] = mapped_column(JSON, nullable=True, default=lambda: {}) # Changed

    properties_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, default=lambda: {}) # Changed

    __table_args__ = (
        UniqueConstraint('guild_id', 'static_id', name='uq_skill_guild_static_id'),
    )

    def __repr__(self) -> str:
        return f"<Skill(id={self.id}, static_id='{self.static_id}', guild_id={self.guild_id}, name='{self.name_i18n.get('en', 'N/A')}')>"
