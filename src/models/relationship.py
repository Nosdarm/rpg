from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Text, UniqueConstraint # Removed JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
# from sqlalchemy.dialects.postgresql import JSONB # Removed direct JSONB import
from sqlalchemy import Enum as SQLAlchemyEnum
from typing import Optional, Dict, Any

from .base import Base
from .enums import RelationshipEntityType # Import the Enum
from .custom_types import JsonBForSQLite # Import custom type

# Forward declaration for type hinting
# from typing import TYPE_CHECKING
# if TYPE_CHECKING:
#     from .guild import GuildConfig
    # Entities involved in relationships (Player, Party, GeneratedNpc, GeneratedFaction)
    # are not directly linked via SQLAlchemy relationships here to keep the model generic.
    # Entity IDs are stored, and fetching related objects would be done by application logic
    # based on entity1_type/entity2_type and entity1_id/entity2_id.

class Relationship(Base):
    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_configs.id", ondelete="CASCADE"), index=True
    )
    # guild: Mapped["GuildConfig"] = relationship() # Optional

    entity1_type: Mapped[RelationshipEntityType] = mapped_column(
        SQLAlchemyEnum(RelationshipEntityType, name="relationship_entity_type_enum", create_type=False),
        nullable=False,
        index=True
    )
    entity1_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    entity2_type: Mapped[RelationshipEntityType] = mapped_column(
        SQLAlchemyEnum(RelationshipEntityType, name="relationship_entity_type_enum", create_type=False), # Use the same enum instance
        nullable=False,
        index=True
    )
    entity2_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    # Type of relationship, e.g., "personal_feeling", "faction_standing", "diplomatic_status"
    # Could also be an Enum if predefined types are desired. For now, i18n JSON for flexibility.
    relationship_type_i18n: Mapped[Optional[Dict[str, str]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {})
    # Example: {"en": "Friendly", "ru": "Дружественный"}, {"en": "Hostile", "ru": "Враждебный"}
    # Or more specific: {"en": "Ally of Convenience", "ru": "Союзник по обстоятельствам"}

    value: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    # Numerical representation of the relationship strength/status.
    # E.g., -100 (arch-enemy) to +100 (best friend/ally), or 0-10 for faction reputation levels.

    ai_metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JsonBForSQLite, nullable=True, default=lambda: {})
    # Example: {"reason_for_change": "completed_quest_X", "last_interaction_event_id": 12345}

    __table_args__ = (
        UniqueConstraint(
            'guild_id',
            'entity1_type', 'entity1_id',
            'entity2_type', 'entity2_id',
            name='uq_relationship_entities'
        ),
        # Consider adding a CHECK constraint to ensure entity1 is "less than" entity2 (e.g. by type then ID)
        # to ensure a canonical representation for each pair, e.g. (player:1, npc:5) is stored, not (npc:5, player:1).
        # This simplifies lookups as you only need to check one order.
        # For example: CHECK (entity1_type < entity2_type OR (entity1_type = entity2_type AND entity1_id < entity2_id))
        # However, this can be complex with string enums. Application logic can enforce canonical storage.
    )

    def __repr__(self) -> str:
        return (
            f"<Relationship(id={self.id}, guild_id={self.guild_id}, "
            f"e1='{self.entity1_type.value}:{self.entity1_id}', "
            f"e2='{self.entity2_type.value}:{self.entity2_id}', value={self.value})>"
        )
