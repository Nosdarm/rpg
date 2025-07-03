from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Text, DateTime, func # Removed JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
# from sqlalchemy.dialects.postgresql import JSONB # Removed
from sqlalchemy import Enum as SQLAlchemyEnum
from typing import Optional, Dict, Any

from .base import Base
from .enums import EventType # Import the Enum
from .custom_types import JsonBForSQLite # Added

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .guild import GuildConfig
    from .location import Location

class StoryLog(Base):
    __tablename__ = "story_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )
    guild: Mapped["GuildConfig"] = relationship(back_populates="story_logs")

    timestamp: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    event_type: Mapped[EventType] = mapped_column(
        SQLAlchemyEnum(EventType, name="event_type_enum", create_type=False), # Assuming event_type_enum is globally managed or this model is part of its first definition
        nullable=False,
        index=True
    )

    location_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("locations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    location: Mapped[Optional["Location"]] = relationship() # One-way relationship, no back_populates needed unless Location tracks logs

    # JSONB to store references to entities involved in the event.
    # Example: {"player_ids": [1, 2], "npc_ids": [101], "item_ids": [50]}
    entity_ids_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {})

    # JSONB for structured details of the event, useful for programmatic access or rollback scenarios.
    # Can also store i18n keys or simple non-translated details.
    details_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {})
    # Example:
    # For COMBAT_ACTION: {"attacker_id": 1, "target_id": 101, "ability_used": "fireball", "damage_dealt": 25}
    # For ITEM_ACQUIRED: {"item_id": 50, "quantity": 1, "source": "chest"}

    # JSONB for human-readable, potentially AI-generated narrative text describing the event.
    # This would store different language versions.
    # Renamed from ai_narrative_i18n to narrative_i18n to be more general
    narrative_i18n: Mapped[Optional[Dict[str, str]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {})
    # Example: {"en": "The goblin shrieks as the fireball engulfs it!", "ru": "Гоблин визжит, охваченный огненным шаром!"}


    def __repr__(self) -> str:
        return f"<StoryLog(id={self.id}, guild_id={self.guild_id}, type='{self.event_type.value}', ts='{self.timestamp}')>"
