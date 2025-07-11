from sqlalchemy import BigInteger, Column, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import Index

from .base import Base


class RuleConfig(Base):
    __tablename__ = "rule_configs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(Text, index=True)
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        Index("ix_rule_configs_guild_id_key", "guild_id", "key", unique=True),
    )

    def __repr__(self) -> str:
        return f"<RuleConfig(id={self.id}, guild_id={self.guild_id}, key='{self.key}')>"
