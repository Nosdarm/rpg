from sqlalchemy import BigInteger, Text, Column
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base

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

    # Relationships
    # Ensure "PendingConflict" is imported or use forward reference if needed.
    # For now, assuming PendingConflict will be imported where GuildConfig is used or via __init__.
    pending_conflicts: Mapped[list["PendingConflict"]] = relationship(back_populates="guild")

    def __repr__(self) -> str:
        return f"<GuildConfig(id={self.id}, main_language='{self.main_language}')>"

# В будущем здесь могут быть другие модели, связанные с гильдией,
# или отношения с другими моделями.
# Например, если бы RuleConfig была отдельной таблицей, связанной с GuildConfig:
# from sqlalchemy.orm import relationship
# rules: Mapped[list["RuleConfig"]] = relationship(back_populates="guild")
