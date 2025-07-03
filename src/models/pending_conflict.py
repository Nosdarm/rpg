from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Text
# from sqlalchemy.dialects.postgresql import JSONB # Removed
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy import Enum as SQLAlchemyEnum # Renamed to avoid conflict

from .base import Base
from .enums import ConflictStatus # Import the new enum
from .guild import GuildConfig # For ForeignKey relationship
from .custom_types import JsonBForSQLite # Added

import logging
logger = logging.getLogger(__name__)

class PendingConflict(Base, AsyncAttrs):
    __tablename__ = "pending_conflicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True)

    involved_entities_json: Mapped[dict] = mapped_column(JsonBForSQLite, nullable=False, comment="List of involved entity identifiers, e.g., [{'type': 'player', 'id': 123, 'name': 'PlayerName'}]")
    conflicting_actions_json: Mapped[dict] = mapped_column(JsonBForSQLite, nullable=False, comment="List of ParsedAction objects (as dicts) that are in conflict")

    status: Mapped[ConflictStatus] = mapped_column(SQLAlchemyEnum(ConflictStatus, name="conflict_status_enum", create_type=False),
                                                 index=True,
                                                 nullable=False,
                                                 default=ConflictStatus.PENDING_MASTER_RESOLUTION)

    resolution_notes: Mapped[str] = mapped_column(Text, nullable=True, comment="Notes from auto-resolution or Master")
    resolved_action_json: Mapped[dict] = mapped_column(JsonBForSQLite, nullable=True, comment="If Master edits/chooses an action, it's stored here as a ParsedAction dict")

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    guild: Mapped["GuildConfig"] = relationship(back_populates="pending_conflicts") # Define in GuildConfig too

    def __repr__(self):
        return f"<PendingConflict(id={self.id}, guild_id={self.guild_id}, status='{self.status.value}')>"

logger.info("PendingConflict model defined.")
