from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
# from sqlalchemy.dialects.postgresql import JSONB # Removed
from sqlalchemy import Enum as SQLAlchemyEnum, Boolean, CheckConstraint # Added CheckConstraint
import datetime # Added for PlayerQuestProgress
from typing import TYPE_CHECKING, Optional, Dict, Any, List

from .base import Base, TimestampMixin # Added TimestampMixin
from .enums import RelationshipEntityType, QuestStatus # Assuming QuestStatus is in enums
from .custom_types import JsonBForSQLite # Added

if TYPE_CHECKING:
    from .guild import GuildConfig
    from .player import Player # For PlayerQuestProgress relationship
    from .party import Party # Added for PlayerQuestProgress relationship
    from .quest import QuestStep # For GeneratedQuest relationship to current_step and PlayerQuestProgress

class Questline(Base, TimestampMixin): # Added TimestampMixin
    __tablename__ = "questlines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    static_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    title_i18n: Mapped[Dict[str, str]] = mapped_column(JsonBForSQLite, nullable=False, default=lambda: {}) # Renamed from name_i18n
    description_i18n: Mapped[Dict[str, str]] = mapped_column(JsonBForSQLite, nullable=False, default=lambda: {}) # Changed

    starting_quest_static_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_main_storyline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    required_previous_questline_static_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    properties_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {})

    quests: Mapped[List["GeneratedQuest"]] = relationship(back_populates="questline")
    __table_args__ = (UniqueConstraint("guild_id", "static_id", name="uq_questline_guild_static_id"),)
    def __repr__(self) -> str:
        return f"<Questline(id={self.id}, static_id='{self.static_id}', guild_id={self.guild_id})>"

class GeneratedQuest(Base, TimestampMixin): # Added TimestampMixin
    __tablename__ = "generated_quests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    static_id: Mapped[str] = mapped_column(Text, nullable=False, index=True) # Unique within guild
    title_i18n: Mapped[Dict[str, str]] = mapped_column(JsonBForSQLite, nullable=False, default=lambda: {}) # Changed
    description_i18n: Mapped[Dict[str, str]] = mapped_column(JsonBForSQLite, nullable=False, default=lambda: {}) # Changed
    questline_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("questlines.id", ondelete="SET NULL"), nullable=True, index=True)
    questline: Mapped[Optional["Questline"]] = relationship(back_populates="quests") # Optional
    giver_entity_type: Mapped[Optional[RelationshipEntityType]] = mapped_column(SQLAlchemyEnum(RelationshipEntityType, name="relationship_entity_type_enum", create_type=False), nullable=True)
    giver_entity_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    min_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True) # Renamed from required_level
    is_repeatable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rewards_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {}) # Changed
    properties_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {}) # Added (ai_metadata_json can be part of this or separate if needed)
    ai_metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {}) # Changed
    steps: Mapped[List["QuestStep"]] = relationship(back_populates="quest", order_by="QuestStep.step_order", cascade="all, delete-orphan")
    player_progress: Mapped[List["PlayerQuestProgress"]] = relationship(back_populates="quest", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint("guild_id", "static_id", name="uq_generated_quest_guild_static_id"),
        Index('ix_generated_quests_giver', 'guild_id', 'giver_entity_type', 'giver_entity_id'),
    )
    def __repr__(self) -> str:
        return f"<GeneratedQuest(id={self.id}, static_id='{self.static_id}', guild_id={self.guild_id})>"

class QuestStep(Base, TimestampMixin): # Added TimestampMixin
    __tablename__ = "quest_steps"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    quest_id: Mapped[int] = mapped_column(Integer, ForeignKey("generated_quests.id", ondelete="CASCADE"), nullable=False, index=True)
    quest: Mapped["GeneratedQuest"] = relationship(back_populates="steps") # Optional
    step_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title_i18n: Mapped[Dict[str, str]] = mapped_column(JsonBForSQLite, nullable=False, default=lambda: {}) # Changed
    description_i18n: Mapped[Dict[str, str]] = mapped_column(JsonBForSQLite, nullable=False, default=lambda: {}) # Changed
    required_mechanics_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {}) # Changed
    abstract_goal_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {}) # Changed
    consequences_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {}) # Changed
    next_step_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    properties_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {})
    __table_args__ = (UniqueConstraint("quest_id", "step_order", name="uq_quest_step_order"),)
    def __repr__(self) -> str:
        return f"<QuestStep(id={self.id}, quest_id={self.quest_id}, order={self.step_order})>"

class PlayerQuestProgress(Base, TimestampMixin): # Added TimestampMixin
    __tablename__ = "player_quest_progress"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True) # Own PK for this table
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    player_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("players.id", ondelete="CASCADE"), nullable=True, index=True) # Made nullable
    player: Mapped[Optional["Player"]] = relationship(back_populates="quest_progress")
    party_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("parties.id", ondelete="CASCADE"), nullable=True, index=True) # Added
    party: Mapped[Optional["Party"]] = relationship() # Added, no back_populates needed if one-way or handled elsewhere

    quest_id: Mapped[int] = mapped_column(Integer, ForeignKey("generated_quests.id", ondelete="CASCADE"), nullable=False, index=True)
    quest: Mapped["GeneratedQuest"] = relationship(back_populates="player_progress")
    current_step_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("quest_steps.id", ondelete="SET NULL"), nullable=True, index=True)
    current_step: Mapped[Optional["QuestStep"]] = relationship()
    status: Mapped[QuestStatus] = mapped_column(SQLAlchemyEnum(QuestStatus, name="quest_status_enum", create_type=False), nullable=False, default=QuestStatus.NOT_STARTED, index=True)
    progress_data_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {}) # Changed

    accepted_at: Mapped[Optional[datetime.datetime]] = mapped_column(JsonBForSQLite.DATETIME_TYPE, nullable=True) # Changed to DATETIME_TYPE for SQLite compatibility
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(JsonBForSQLite.DATETIME_TYPE, nullable=True) # Changed to DATETIME_TYPE for SQLite compatibility

    __table_args__ = (
        UniqueConstraint("guild_id", "player_id", "quest_id", name="uq_player_quest_guild"),
        UniqueConstraint("guild_id", "party_id", "quest_id", name="uq_party_quest_guild"),
        CheckConstraint("player_id IS NOT NULL OR party_id IS NOT NULL", name="cc_player_or_party_id_not_null"),
        Index('ix_player_quest_progress_player_quest', 'player_id', 'quest_id'), # Explicit combined index
        Index('ix_player_quest_progress_party_quest', 'party_id', 'quest_id'),   # Explicit combined index
    )
    def __repr__(self) -> str:
        if self.player_id:
            return f"<PlayerQuestProgress(player_id={self.player_id}, quest_id={self.quest_id}, status='{self.status.value}')>"
        elif self.party_id:
            return f"<PlayerQuestProgress(party_id={self.party_id}, quest_id={self.quest_id}, status='{self.status.value}')>"
        return f"<PlayerQuestProgress(id={self.id}, quest_id={self.quest_id}, status='{self.status.value}')>"
