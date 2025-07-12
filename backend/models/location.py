import enum
from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Text, Enum as SQLAlchemyEnum, JSON
# JSONB import is removed as we use custom type
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import Index
from typing import Optional, Dict, List, Any, Union, TYPE_CHECKING # Added TYPE_CHECKING

from .base import Base

if TYPE_CHECKING:
    from .guild import GuildConfig # GuildConfig will be referenced by ForeignKey as string 'guild_configs.id'
    from .player import Player # For players_present relationship
    from .generated_npc import GeneratedNpc # For npcs_present relationship
    # Add imports for new global entities if not already present
    from .global_npc import GlobalNpc
    from .mobile_group import MobileGroup
    from .global_event import GlobalEvent


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
    guild: Mapped["GuildConfig"] = relationship(back_populates="locations")

    parent_location_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("locations.id", name="fk_location_parent_id", use_alter=True), nullable=True, index=True
    )
    static_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True) # Unique within a guild

    name_i18n: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False, default=lambda: {})
    descriptions_i18n: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False, default=lambda: {}) # Reverted to plural

    type: Mapped[LocationType] = mapped_column(SQLAlchemyEnum(LocationType), nullable=False, default=LocationType.GENERIC)

    coordinates_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    # Updated to allow either List or Dict for older format compatibility
    neighbor_locations_json: Mapped[Optional[Union[List[Dict[str, Any]], Dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    generated_details_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ai_metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    properties_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Hierarchical relationships
    parent_location: Mapped[Optional["Location"]] = relationship(
        back_populates="child_locations", remote_side="Location.id" # Use string for remote_side
    )
    child_locations: Mapped[List["Location"]] = relationship(
        back_populates="parent_location", cascade="all, delete-orphan"
    )

    # Relationships for entities present in the location
    players_present: Mapped[List["Player"]] = relationship(back_populates="location") # Corrected from current_location to location
    npcs_present: Mapped[List["GeneratedNpc"]] = relationship(back_populates="current_location")
    global_npcs_in_location: Mapped[List["GlobalNpc"]] = relationship(back_populates="current_location")
    mobile_groups_in_location: Mapped[List["MobileGroup"]] = relationship(back_populates="current_location")
    global_events_in_location: Mapped[List["GlobalEvent"]] = relationship(back_populates="location")


    __table_args__ = (
        Index("ix_locations_guild_id_static_id", "guild_id", "static_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<Location(id={self.id}, guild_id={self.guild_id}, static_id='{self.static_id}', name='{self.name_i18n.get('en', 'N/A')}')>"
