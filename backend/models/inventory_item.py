from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Text, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
# from sqlalchemy.dialects.postgresql import JSONB # Удалено
from sqlalchemy import Enum as SQLAlchemyEnum
from typing import Optional, Dict, Any

from .base import Base
from .enums import OwnerEntityType
from .item import Item

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .player import Player

class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )
    # guild: Mapped["GuildConfig"] = relationship() # Optional

    owner_entity_type: Mapped[OwnerEntityType] = mapped_column(
        SQLAlchemyEnum(OwnerEntityType, name="owner_entity_type_enum", create_type=False),
        nullable=False,
        index=True
    )
    owner_entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # Note: owner_entity_id refers to the ID in the respective owner's table (players.id, generated_npcs.id etc.)
    # No direct ForeignKey constraint here to keep it generic, rely on application logic or DB triggers if strictness needed.

    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    item: Mapped["Item"] = relationship()
    player_owner: Mapped["Player"] = relationship(
        back_populates="inventory_items",
        primaryjoin="foreign(InventoryItem.owner_entity_id) == Player.id",
        overlaps="inventory_items",
    )

    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    equipped_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)
    # e.g., "main_hand", "off_hand", "armor_body", "armor_head", "ring_1", "consumable_slot_1"
    # NULL if not equipped. Application logic ensures only equippable items can have non-null status.

    instance_specific_properties_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True, default=lambda: {}
    )
    # Example:
    # {"durability": 95, "custom_name": "Bob's Sword of Slaying", "bound_to_player": 123}
    # If this is null or empty, items are typically stackable by item_id.
    # If it has values, it might represent a unique instance.

    __table_args__ = (
        # This constraint ensures that for a given owner in a guild,
        # an item (item_id) with specific instance properties is unique.
        # If instance_specific_properties_json is NULL, then multiple entries for the same item_id can exist
        # for the same owner if they are considered different "stacks" (e.g. if this table only tracks unique instances).
        # However, typically, if instance_specific_properties_json is NULL or empty, quantity should be updated on the existing row.
        # The exact constraint depends on how stackability vs unique instances is handled.
        # A simpler constraint if items are always unique instances or always stackable by item_id could be used.
        # For now, let's assume one row per (owner, item_id, instance_properties_content_hash - if possible or rely on app logic for stacking)
        # A practical approach for stacking: query for existing item_id with matching instance_properties (or null), then update quantity or insert.
        # The unique constraint below is more about preventing exact duplicates if instance_specific_properties are part of the key.
        # For JSONB comparison in unique constraints, it can be tricky. Often application logic handles stacking.
        # Let's make a simpler unique constraint for now, assuming application handles stacking logic.
        # UniqueConstraint('guild_id', 'owner_entity_type', 'owner_entity_id', 'item_id', 'instance_specific_properties_json', name='uq_inventory_item_instance'),
        # For simplicity, let's assume one inventory entry per item_id for an owner, and instance_properties just add detail.
        # Stacking should be handled by application logic (increment quantity). If an item has unique instance_properties, it's a new row.
        # This means an owner can have:
        # 1. Potion X, Qty 5, props {}
        # 2. Sword Y, Qty 1, props {"ench": "fire"}
        # 3. Sword Y, Qty 1, props {"ench": "ice"}
        # The following constraint makes sense if instance_specific_properties_json = {} is treated as one class of stackable items
        # and any non-empty JSON makes it unique. Postgres can't directly unique JSON content easily in a constraint.
        # We'll rely on application logic for perfect stacking & uniqueness of instances.
        # A basic constraint to prevent fully identical rows might be:
        UniqueConstraint('guild_id', 'owner_entity_type', 'owner_entity_id', 'item_id', name='uq_inventory_owner_item'),
        # This means an owner can only have one "stack" of a particular item_id.
        # If items can have unique enchantments that make them different *types* of the same base item,
        # then 'item_id' alone isn't enough for uniqueness for stacking.
        # The plan said: "UniqueConstraint for (guild_id, owner_entity_type, owner_entity_id, item_id, instance_specific_properties_json)"
        # This is hard with JSONB.
        # A common pattern is to have item_id for the base item, and if instance_specific_properties_json is NOT NULL/empty,
        # it's a unique instance and quantity is usually 1. If it IS NULL/empty, items are stackable.
        # Let's stick to the simpler UniqueConstraint and assume app logic for instance distinction.
    )

    def __repr__(self) -> str:
        return f"<InventoryItem(id={self.id}, owner='{self.owner_entity_type.value}:{self.owner_entity_id}', item_id={self.item_id}, quantity={self.quantity})>"
