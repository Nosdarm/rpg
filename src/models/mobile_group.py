from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
# from sqlalchemy.dialects.postgresql import JSONB # Removed
from sqlalchemy.schema import Index
from typing import Optional, Dict, Any, List

from .base import Base
from .custom_types import JsonBForSQLite # Added

# Forward declaration for type hinting
# from typing import TYPE_CHECKING
# if TYPE_CHECKING:
#     from .guild import GuildConfig
#     from .location import Location

class MobileGroup(Base):
    __tablename__ = "mobile_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )

    name_i18n: Mapped[Dict[str, str]] = mapped_column(JsonBForSQLite, nullable=False, default=lambda: {}) # Changed

    current_location_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("locations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    members_json: Mapped[List[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=False, default=lambda: []) # Changed
    behavior_type_i18n: Mapped[Optional[Dict[str, str]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {}) # Changed
    route_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {}) # Changed
    ai_metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {}) # Changed

    def __repr__(self) -> str:
        return f"<MobileGroup(id={self.id}, guild_id={self.guild_id}, name='{self.name_i18n.get('en', 'N/A')}')>"
