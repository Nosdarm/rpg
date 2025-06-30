import enum
from sqlalchemy import BigInteger, Column, ForeignKey, Integer, JSON, Text, Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import Index

from .base import Base
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

    name_i18n: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False, default=lambda: {})
    descriptions_i18n: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False, default=lambda: {})

    type: Mapped[LocationType] = mapped_column(SQLAlchemyEnum(LocationType), nullable=False, default=LocationType.GENERIC)

    coordinates_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    neighbor_locations_json: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True) # List of {location_id: int, connection_type_i18n: Dict[str,str]}
    generated_details_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ai_metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_locations_guild_id_static_id", "guild_id", "static_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<Location(id={self.id}, guild_id={self.guild_id}, static_id='{self.static_id}', name='{self.name_i18n.get('en', 'N/A')}')>"
