from sqlalchemy import BigInteger, Column, ForeignKey, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import Index, UniqueConstraint
from typing import Optional, Dict, Any, List

from .base import Base
# Forward declaration for type hinting
# from typing import TYPE_CHECKING
# if TYPE_CHECKING:
#     from .guild import GuildConfig
#     from .item import Item
#     from .skill import Skill

class CraftingRecipe(Base):
    __tablename__ = "crafting_recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # guild_id is nullable because some recipes might be global/common,
    # while others could be guild-specific or player-discovered.
    guild_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # guild: Mapped[Optional["GuildConfig"]] = relationship() # Optional

    static_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    # Unique identifier for the recipe, e.g., "potion_healing_basic", "sword_iron_common"
    # Uniqueness considerations similar to Ability/Skill models.

    name_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, default=lambda: {})
    description_i18n: Mapped[Optional[Dict[str, str]]] = mapped_column(JSONB, nullable=True, default=lambda: {})

    result_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="CASCADE")
        # If an item is deleted, recipes producing it might become invalid or be deleted too.
        # ondelete="CASCADE" might be too aggressive if recipes should persist even if an item is removed (e.g. for historical reasons or if item is temporarily unavailable).
        # Consider ondelete="SET NULL" or ondelete="RESTRICT" if recipes should not be auto-deleted. For now, CASCADE for simplicity.
    )
    # result_item: Mapped["Item"] = relationship(foreign_keys=[result_item_id]) # Optional

    result_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # List of ingredients, each specifying item_id and quantity.
    # Example: [{"item_static_id": "herb_common", "quantity": 3}, {"item_static_id": "water_flask", "quantity": 1}]
    # Storing static_id might be more resilient to item ID changes if items are frequently recreated, but FK to items.id is cleaner for DB integrity.
    # Let's assume item_id is used here.
    ingredients_json: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=lambda: [])
    # Example: [{"item_id": 123, "quantity": 3}, {"item_id": 456, "quantity": 1}]


    required_skill_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("skills.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # required_skill: Mapped[Optional["Skill"]] = relationship() # Optional

    required_skill_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Other properties, e.g., crafting station required, time to craft, blueprint item required to unlock.
    properties_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True, default=lambda: {})
    # Example:
    # {
    #   "crafting_station_type": "anvil", // "alchemy_lab", "workbench"
    #   "time_to_craft_seconds": 60,
    #   "unlock_condition": {"type": "blueprint_item", "item_static_id": "recipe_scroll_potion_healing"}
    # }

    __table_args__ = (
        UniqueConstraint('guild_id', 'static_id', name='uq_crafting_recipe_guild_static_id'),
        # Index('ix_crafting_recipe_global_static_id', 'static_id', unique=True, postgresql_where=Column('guild_id').is_(None)),
    )

    def __repr__(self) -> str:
        return f"<CraftingRecipe(id={self.id}, static_id='{self.static_id}', guild_id={self.guild_id}, name='{self.name_i18n.get('en', 'N/A')}')>"
