from sqlalchemy import BigInteger, Column, ForeignKey, Integer, JSON, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Enum as SQLAlchemyEnum
from typing import Optional, Dict, Any, List

from .base import Base
from .enums import RelationshipEntityType, QuestStatus # Reusing RelationshipEntityType for giver, new QuestStatus

# Forward declarations for type hinting
# from typing import TYPE_CHECKING
# if TYPE_CHECKING:
#     from .guild import GuildConfig
#     from .player import Player
#     # Potentially other entities if they can be quest givers and RelationshipEntityType is not sufficient

class Questline(Base):
    __tablename__ = "questlines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )
    static_id: Mapped[str] = mapped_column(Text, nullable=False, index=True) # Unique within a guild

    name_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, default=lambda: {})
    description_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, default=lambda: {})

    # quests: Mapped[List["GeneratedQuest"]] = relationship(back_populates="questline") # If GeneratedQuest has backref

    __table_args__ = (
        UniqueConstraint('guild_id', 'static_id', name='uq_questline_guild_static_id'),
    )
    def __repr__(self) -> str:
        return f"<Questline(id={self.id}, static_id='{self.static_id}', guild_id={self.guild_id})>"


class GeneratedQuest(Base):
    __tablename__ = "generated_quests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )
    static_id: Mapped[str] = mapped_column(Text, nullable=False, index=True) # Unique within a guild

    title_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, default=lambda: {})
    description_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, default=lambda: {})

    questline_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("questlines.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # questline: Mapped[Optional["Questline"]] = relationship(back_populates="quests") # Optional

    giver_entity_type: Mapped[Optional[RelationshipEntityType]] = mapped_column(
        SQLAlchemyEnum(RelationshipEntityType, name="relationship_entity_type_enum", create_type=False),
        nullable=True
    )
    giver_entity_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    # Index for giver: Index('ix_generated_quests_giver', 'guild_id', 'giver_entity_type', 'giver_entity_id')

    min_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rewards_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True, default=lambda: {})
    # Example: {"xp": 500, "gold": 100, "items": [{"item_static_id": "potion_health", "quantity": 3}], "faction_reputation": [{"faction_static_id": "town_guard", "change": 10}]}

    ai_metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True, default=lambda: {})
    # steps: Mapped[List["QuestStep"]] = relationship(back_populates="quest", order_by="QuestStep.step_order") # If QuestStep has backref

    __table_args__ = (
        UniqueConstraint('guild_id', 'static_id', name='uq_generated_quest_guild_static_id'),
        Index('ix_generated_quests_giver', 'guild_id', 'giver_entity_type', 'giver_entity_id'),
    )
    def __repr__(self) -> str:
        return f"<GeneratedQuest(id={self.id}, static_id='{self.static_id}', guild_id={self.guild_id})>"


class QuestStep(Base):
    __tablename__ = "quest_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    quest_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("generated_quests.id", ondelete="CASCADE"), index=True
    )
    # quest: Mapped["GeneratedQuest"] = relationship(back_populates="steps") # Optional

    # guild_id is implicitly through quest_id -> generated_quests.guild_id. Can be added explicitly if direct queries are common.
    # guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True)


    step_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    title_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, default=lambda: {})
    description_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, default=lambda: {})

    required_mechanics_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True, default=lambda: {})
    # Example: {"type": "kill", "target_npc_static_id": "goblin_shaman", "count": 3}
    #          {"type": "fetch", "item_static_id": "herbs_special", "count": 5}
    #          {"type": "goto", "location_static_id": "ancient_ruins"}
    #          {"type": "talk_to_npc", "npc_static_id": "village_elder"}

    abstract_goal_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True, default=lambda: {})
    # For LLM evaluation: {"description": "Impress the merchant guild with your trading prowess."}

    consequences_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True, default=lambda: {})
    # What happens on step completion, similar to quest rewards_json, but for a step.
    # Example: {"xp": 50, "relationship_change": {"target_npc_static_id": "village_elder", "change": 5}}

    __table_args__ = (
        UniqueConstraint('quest_id', 'step_order', name='uq_quest_step_order'),
    )
    def __repr__(self) -> str:
        return f"<QuestStep(id={self.id}, quest_id={self.quest_id}, order={self.step_order})>"


class PlayerQuestProgress(Base):
    __tablename__ = "player_quest_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True) # Own PK for this table

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    # player: Mapped["Player"] = relationship() # Optional

    quest_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("generated_quests.id", ondelete="CASCADE"), index=True
    )
    # quest: Mapped["GeneratedQuest"] = relationship() # Optional

    current_step_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("quest_steps.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # current_step: Mapped[Optional["QuestStep"]] = relationship() # Optional

    status: Mapped[QuestStatus] = mapped_column(
        SQLAlchemyEnum(QuestStatus, name="quest_status_enum", create_type=False),
        nullable=False,
        default=QuestStatus.NOT_STARTED,
        index=True
    )

    # For storing progress specific to the current step or overall quest.
    # E.g., {"goblins_killed": 1, "herbs_collected": 2}
    progress_data_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True, default=lambda: {})

    __table_args__ = (
        UniqueConstraint('guild_id', 'player_id', 'quest_id', name='uq_player_quest'),
    )

    def __repr__(self) -> str:
        return f"<PlayerQuestProgress(player_id={self.player_id}, quest_id={self.quest_id}, status='{self.status.value}')>"
