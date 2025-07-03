import enum
from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Text, Enum as SQLAlchemyEnum
# JSONB import is removed as we use custom type
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import Index
from typing import Optional, Dict, List, Any, Union

from .base import Base
from .custom_types import JsonBForSQLite # Import custom type
# from .guild import GuildConfig # GuildConfig will be referenced by ForeignKey as string 'guild_configs.id'


class LocationType(enum.Enum):
    GENERIC = "generic"
    TOWN = "town"
    CITY = "city"
    VILLAGE = "village"
    FOREST = "forest"
    MOUNTAIN = "mountain"
    CAVE = "cave"
    DUNGEON = "dungeon"
    SHOP = "shop"
    TAVERN = "tavern"
    ROAD = "road"
    PORT = "port"
    # Add more types as needed


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )

    # Optional: Link to GuildConfig object, if direct access is often needed.
    # guild: Mapped["GuildConfig"] = relationship(back_populates="locations") # Assuming GuildConfig has a 'locations' backref

    static_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True) # Unique within a guild

    name_i18n: Mapped[Dict[str, str]] = mapped_column(JsonBForSQLite, nullable=False, default=lambda: {})
    descriptions_i18n: Mapped[Dict[str, str]] = mapped_column(JsonBForSQLite, nullable=False, default=lambda: {})

    type: Mapped[LocationType] = mapped_column(SQLAlchemyEnum(LocationType), nullable=False, default=LocationType.GENERIC)

    coordinates_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True)
    # Updated to allow either List or Dict for older format compatibility
    neighbor_locations_json: Mapped[Optional[Union[List[Dict[str, Any]], Dict[str, Any]]]] = mapped_column(JsonBForSQLite, nullable=True)
    generated_details_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True)
    ai_metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True)

    __table_args__ = (
        Index("ix_locations_guild_id_static_id", "guild_id", "static_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<Location(id={self.id}, guild_id={self.guild_id}, static_id='{self.static_id}', name='{self.name_i18n.get('en', 'N/A')}')>"
