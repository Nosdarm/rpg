from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Text, String # Added String
from sqlalchemy.orm import Mapped, mapped_column, relationship
# from sqlalchemy.dialects.postgresql import JSONB # Removed
from sqlalchemy.schema import Index
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from .base import Base, TimestampMixin # Added TimestampMixin
from .custom_types import JsonBForSQLite # Added

# Forward declaration for type hinting
if TYPE_CHECKING:
    from .guild import GuildConfig
    from .location import Location # Added for relationship
    from .global_npc import GlobalNpc


class MobileGroup(Base, TimestampMixin): # Inherit from TimestampMixin
    __tablename__ = "mobile_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    static_id: Mapped[str] = mapped_column(String, index=True, nullable=False) # Added unique=True later if globally unique

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )

    name_i18n: Mapped[Dict[str, str]] = mapped_column(JsonBForSQLite, nullable=False, default=lambda: {})

    description_i18n: Mapped[Optional[Dict[str, str]]] = mapped_column(JsonBForSQLite, nullable=True) # Added

    current_location_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("locations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    leader_global_npc_id: Mapped[Optional[int]] = mapped_column( # Added
        Integer, ForeignKey("global_npcs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    members_definition_json: Mapped[List[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=False, default=lambda: []) # Renamed members_json

    behavior_type_i18n: Mapped[Optional[Dict[str, str]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {})
    route_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {})
    ai_metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {})

    properties_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {}) # Added

    # Relationships
    guild_config: Mapped["GuildConfig"] = relationship(back_populates="mobile_groups")
    current_location: Mapped[Optional["Location"]] = relationship(back_populates="mobile_groups_in_location")
    # leader_global_npc: Mapped[Optional["GlobalNpc"]] = relationship(foreign_keys=[leader_global_npc_id]) # This would be for a direct leader FK
    members: Mapped[List["GlobalNpc"]] = relationship(
        back_populates="mobile_group",
        foreign_keys="[GlobalNpc.mobile_group_id]"
    )


    __table_args__ = (
        Index("ix_mobile_groups_guild_id_static_id", "guild_id", "static_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<MobileGroup(id={self.id}, static_id='{self.static_id}', guild_id={self.guild_id})>"
