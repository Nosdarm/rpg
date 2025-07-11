import datetime # Add this import
from typing import TYPE_CHECKING, Dict, Any, Optional

from sqlalchemy import ForeignKey, Index, String, JSON, Text, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .guild import GuildConfig
    from .location import Location


class GlobalEvent(Base, TimestampMixin):
    __tablename__ = "global_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(ForeignKey("guild_configs.id"), index=True)
    static_id: Mapped[str] = mapped_column(String, index=True)
    name_i18n: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False)
    description_i18n: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False) # Was Optional, made it required as per design
    event_type: Mapped[str] = mapped_column(Text, index=True, nullable=False)
    location_id: Mapped[Optional[int]] = mapped_column(ForeignKey("locations.id"), nullable=True, index=True)
    trigger_time: Mapped[Optional[datetime.datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    expiration_time: Mapped[Optional[datetime.datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, index=True, default="pending", nullable=False)
    properties_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=lambda: {}, nullable=False)

    guild: Mapped["GuildConfig"] = relationship(back_populates="global_events")
    location: Mapped[Optional["Location"]] = relationship(back_populates="global_events_in_location")

    __table_args__ = (
        Index("ix_global_events_guild_id_static_id", "guild_id", "static_id", unique=True),
        Index("ix_global_events_status_trigger_time", "status", "trigger_time"),
    )

    def __repr__(self) -> str:
        return f"<GlobalEvent(id={self.id}, static_id='{self.static_id}', type='{self.event_type}', guild_id={self.guild_id})>"
