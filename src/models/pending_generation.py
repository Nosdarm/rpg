import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Integer, String, Text, ForeignKey, JSON, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession

from .base import Base
from .enums import ModerationStatus # Assuming ModerationStatus is now in enums

class PendingGeneration(Base):
    __tablename__ = "pending_generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False) # Assuming guild-specific

    # Who or what triggered this generation
    triggered_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("players.id"), nullable=True) # If triggered by a player
    # triggered_by_event_type: Mapped[Optional[str]] # If triggered by a system event

    # Context for the trigger
    trigger_context_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # AI Prompt and Response
    ai_prompt_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_ai_response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Parsed and Validated Data (if successful)
    parsed_validated_data_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    validation_issues_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True) # If validation failed

    # Moderation
    status: Mapped[ModerationStatus] = mapped_column(String, default=ModerationStatus.PENDING_MODERATION, index=True) # Using String to store enum value
    master_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True) # ID of master who reviewed
    master_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<PendingGeneration(id={self.id}, guild_id={self.guild_id}, status='{self.status.value if isinstance(self.status, ModerationStatus) else self.status}')>"
