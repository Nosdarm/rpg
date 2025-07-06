from typing import TYPE_CHECKING, Dict, Any, Optional

from sqlalchemy import ForeignKey, Index, String, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .guild import Guild
    from .location import Location
    from .generated_npc import GeneratedNpc


class GlobalNpc(Base, TimestampMixin):
    __tablename__ = "global_npcs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id"), index=True)
    static_id: Mapped[str] = mapped_column(String, index=True)
    name_i18n: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False)
    description_i18n: Mapped[Optional[Dict[str, str]]] = mapped_column(JSON, nullable=True)
    current_location_id: Mapped[Optional[int]] = mapped_column(ForeignKey("locations.id"), nullable=True, index=True)
    base_npc_id: Mapped[Optional[int]] = mapped_column(ForeignKey("generated_npcs.id"), nullable=True)
    properties_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=lambda: {}, nullable=False)

    guild: Mapped["Guild"] = relationship(back_populates="global_npcs")
    current_location: Mapped[Optional["Location"]] = relationship(back_populates="global_npcs_in_location")
    base_npc: Mapped[Optional["GeneratedNpc"]] = relationship()

    __table_args__ = (
        Index("ix_global_npcs_guild_id_static_id", "guild_id", "static_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<GlobalNpc(id={self.id}, static_id='{self.static_id}', guild_id={self.guild_id})>"
