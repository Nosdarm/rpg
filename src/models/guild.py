from sqlalchemy import BigInteger, Text, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING
from .base import Base

from typing import List

if TYPE_CHECKING:
    from .pending_conflict import PendingConflict # type: ignore
    from .story_log import StoryLog # Added for StoryLog relationship
    from .ability import Ability # Added for Ability relationship
    from .status_effect import StatusEffect, ActiveStatusEffect # Added for StatusEffect relationship
    from .combat_encounter import CombatEncounter # Added for CombatEncounter relationship

class GuildConfig(Base):
    """
    Модель конфигурации для каждой гильдии (сервера Discord).
    """
    __tablename__ = "guild_configs"

    # id гильдии Discord будет первичным ключом
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True, autoincrement=False)
    # Используем BigInteger, так как ID Discord могут быть большими.
    # autoincrement=False, так как ID присваивается Discord'ом.

    master_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    system_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    notification_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    main_language: Mapped[str] = mapped_column(Text, default="en", nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True) # Added guild name

    # Relationships
    # Ensure "PendingConflict" is imported or use forward reference if needed.
    # For now, assuming PendingConflict will be imported where GuildConfig is used or via __init__.
    pending_conflicts: Mapped[List["PendingConflict"]] = relationship(back_populates="guild")
    story_logs: Mapped[List["StoryLog"]] = relationship(back_populates="guild", cascade="all, delete-orphan")
    abilities: Mapped[List["Ability"]] = relationship(back_populates="guild", cascade="all, delete-orphan")
    status_effects: Mapped[List["StatusEffect"]] = relationship(back_populates="guild", cascade="all, delete-orphan")
    active_status_effects: Mapped[List["ActiveStatusEffect"]] = relationship(back_populates="guild", cascade="all, delete-orphan")
    combat_encounters: Mapped[List["CombatEncounter"]] = relationship(back_populates="guild", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<GuildConfig(id={self.id}, main_language='{self.main_language}')>"

# В будущем здесь могут быть другие модели, связанные с гильдией,
# или отношения с другими моделями.
# Например, если бы RuleConfig была отдельной таблицей, связанной с GuildConfig:
# from sqlalchemy.orm import relationship
# rules: Mapped[list["RuleConfig"]] = relationship(back_populates="guild")
