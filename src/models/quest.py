from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
# from sqlalchemy.dialects.postgresql import JSONB # Removed
from sqlalchemy import Enum as SQLAlchemyEnum
from typing import TYPE_CHECKING, Optional, Dict, Any, List

from .base import Base
from .enums import RelationshipEntityType, QuestStatus # Assuming QuestStatus is in enums
from .custom_types import JsonBForSQLite # Added

if TYPE_CHECKING:
    from .guild import GuildConfig
    from .player import Player # For PlayerQuestProgress relationship
    from .quest import QuestStep # For GeneratedQuest relationship to current_step and PlayerQuestProgress

class Questline(Base):
    __tablename__ = "questlines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    static_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name_i18n: Mapped[Dict[str, str]] = mapped_column(JsonBForSQLite, nullable=False, default=lambda: {}) # Changed
    description_i18n: Mapped[Dict[str, str]] = mapped_column(JsonBForSQLite, nullable=False, default=lambda: {}) # Changed
    quests: Mapped[List["GeneratedQuest"]] = relationship(back_populates="questline")
    __table_args__ = (UniqueConstraint("guild_id", "static_id", name="uq_questline_guild_static_id"),)
    def __repr__(self) -> str:
        return f"<Questline(id={self.id}, static_id='{self.static_id}', guild_id={self.guild_id})>"

class GeneratedQuest(Base):
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
    min_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rewards_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {}) # Changed
    ai_metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {}) # Changed
    steps: Mapped[List["QuestStep"]] = relationship(back_populates="quest", order_by="QuestStep.step_order", cascade="all, delete-orphan")
    player_progress: Mapped[List["PlayerQuestProgress"]] = relationship(back_populates="quest", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint("guild_id", "static_id", name="uq_generated_quest_guild_static_id"),
        Index('ix_generated_quests_giver', 'guild_id', 'giver_entity_type', 'giver_entity_id'),
    )
    def __repr__(self) -> str:
        return f"<GeneratedQuest(id={self.id}, static_id='{self.static_id}', guild_id={self.guild_id})>"

class QuestStep(Base):
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
    __table_args__ = (UniqueConstraint("quest_id", "step_order", name="uq_quest_step_order"),)
    def __repr__(self) -> str:
        return f"<QuestStep(id={self.id}, quest_id={self.quest_id}, order={self.step_order})>"

class PlayerQuestProgress(Base):
    __tablename__ = "player_quest_progress"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True) # Own PK for this table
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)
    player: Mapped["Player"] = relationship(back_populates="quest_progress") # Optional
    quest_id: Mapped[int] = mapped_column(Integer, ForeignKey("generated_quests.id", ondelete="CASCADE"), nullable=False, index=True)
    quest: Mapped["GeneratedQuest"] = relationship(back_populates="player_progress") # Optional
    current_step_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("quest_steps.id", ondelete="SET NULL"), nullable=True, index=True)
    current_step: Mapped[Optional["QuestStep"]] = relationship() # Optional, no back_populates needed for one-way to current_step
    status: Mapped[QuestStatus] = mapped_column(SQLAlchemyEnum(QuestStatus, name="quest_status_enum", create_type=False), nullable=False, default=QuestStatus.NOT_STARTED, index=True)
    progress_data_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {}) # Changed
    __table_args__ = (UniqueConstraint("guild_id", "player_id", "quest_id", name="uq_player_quest"),)
    def __repr__(self) -> str:
        return f"<PlayerQuestProgress(player_id={self.player_id}, quest_id={self.quest_id}, status='{self.status.value}')>"
