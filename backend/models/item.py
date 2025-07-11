from sqlalchemy import BigInteger, Column, ForeignKey, Integer, JSON, Text, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import Index
from typing import Optional, Dict, Any

from .base import Base
# Forward declaration for type hinting
# from typing import TYPE_CHECKING
# if TYPE_CHECKING:
#     from .guild import GuildConfig

class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )
    # guild: Mapped["GuildConfig"] = relationship() # Optional

    static_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True) # Unique within a guild

    name_i18n: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False, default=lambda: {})
    description_i18n: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False, default=lambda: {})

    item_type_i18n: Mapped[Optional[Dict[str, str]]] = mapped_column(JSON, nullable=True, default=lambda: {})
    # e.g., {"en": "Weapon", "ru": "Оружие"}, {"en": "Potion", "ru": "Зелье"}

    item_category_i18n: Mapped[Optional[Dict[str, str]]] = mapped_column(JSON, nullable=True, default=lambda: {})
    # e.g. {"en": "One-Handed Sword", "ru": "Одноручный меч"}, {"en": "Healing Potion", "ru": "Лечебное зелье"}

    base_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True) # Using Integer for simplicity, Numeric if decimals needed

    properties_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, default=lambda: {})
    # Example:
    # For a weapon: {"damage": "1d6", "damage_type": "slashing", "weight": 5, "requires_strength": 12}
    # For a potion: {"effect": "heal", "amount": "2d4+2", "duration_seconds": 0}
    # For armor: {"armor_class": 15, "type": "medium", "weight": 20}

    slot_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)
    # e.g., "weapon", "shield", "armor", "helmet", "gloves", "boots", "ring", "amulet", "consumable"

    is_stackable: Mapped[bool] = mapped_column(default=True, nullable=False)

    __table_args__ = (
        Index("ix_items_guild_id_static_id", "guild_id", "static_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<Item(id={self.id}, guild_id={self.guild_id}, static_id='{self.static_id}', name='{self.name_i18n.get('en', 'N/A')}')>"
