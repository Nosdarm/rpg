from sqlalchemy import BigInteger, Column, ForeignKey, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import Index
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from .base import Base
from .enums import OwnerEntityType # Added for relationship
from .inventory_item import InventoryItem # Ensure full import for relationship

# Forward declaration for type hinting if GuildConfig or Location were complex types

if TYPE_CHECKING:
#     from .guild import GuildConfig
    from .location import Location # Ensure Location is imported for the relationship
    from .generated_faction import GeneratedFaction # For type hinting relationship
    pass # InventoryItem is now fully imported

class GeneratedNpc(Base):
    __tablename__ = "generated_npcs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )
    # guild: Mapped["GuildConfig"] = relationship() # Optional: if direct access to GuildConfig object needed

    static_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True) # Unique within a guild

    name_i18n: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False, default=lambda: {})
    description_i18n: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False, default=lambda: {})

    current_location_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("locations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # current_location: Mapped[Optional["Location"]] = relationship() # Optional: if direct access to Location object needed

    npc_type_i18n: Mapped[Optional[Dict[str, str]]] = mapped_column(JSON, nullable=True, default=lambda: {}) # e.g., {"en": "Merchant", "ru": "Торговец"}

    properties_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, default=lambda: {})
    # Example:
    # {
    #   "stats": {"strength": 10, "dexterity": 12, ...},
    #   "abilities": ["ability_static_id_1", "ability_static_id_2"],
    #   "inventory_id": "some_inventory_ref_or_embedded_list",
    #   "faction_id": "faction_static_id_1",
    #   "status": "idle"
    # }

    ai_metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, default=lambda: {})
    # Example:
    # {
    #   "prompt_used": "generate a grumpy merchant...",
    #   "generation_model": "gpt-4",
    #   "temperament": "grumpy",
    #   "dialogue_style": "curt"
    # }
    faction_id: Mapped[Optional[int]] = mapped_column(ForeignKey("generated_factions.id", name="fk_generated_npc_faction_id"), nullable=True, index=True)

    # Relationships
    inventory_items: Mapped[List["InventoryItem"]] = relationship(
        primaryjoin=f"and_(GeneratedNpc.id==InventoryItem.owner_entity_id, InventoryItem.owner_entity_type=='{OwnerEntityType.GENERATED_NPC.value}')",
        foreign_keys=[InventoryItem.owner_entity_id, InventoryItem.owner_entity_type], # type: ignore[list-arg]
        cascade="all, delete-orphan",
        lazy="selectin",
        overlaps="inventory_items"  # Added to address SAWarning
    )
    current_location: Mapped[Optional["Location"]] = relationship(back_populates="npcs_present")
    faction: Mapped[Optional["GeneratedFaction"]] = relationship(
        back_populates="members",
        foreign_keys=[faction_id] # Explicitly specify the foreign key
    )


    __table_args__ = (
        Index("ix_generated_npcs_guild_id_static_id", "guild_id", "static_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<GeneratedNpc(id={self.id}, guild_id={self.guild_id}, static_id='{self.static_id}', name='{self.name_i18n.get('en', 'N/A')}')>"
