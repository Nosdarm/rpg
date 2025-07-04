from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import Integer, BigInteger, String, ForeignKey, Enum as SQLAlchemyEnum, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base
from .enums import CombatStatus
from .custom_types import JsonBForSQLite # Import the custom type

if TYPE_CHECKING:
    from .guild import GuildConfig
    from .location import Location


class CombatEncounter(Base):
    """
    Represents the state of an active combat encounter within a guild.
    """
    __tablename__ = "combat_encounters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guild_configs.id"), index=True)
    location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("locations.id"), nullable=True)

    status: Mapped[CombatStatus] = mapped_column(SQLAlchemyEnum(CombatStatus, name="combat_status_enum", create_type=True), default=CombatStatus.PENDING_START)

    # ID of the entity whose turn it currently is.
    # Could be Player.id, GeneratedNpc.id, or potentially Party.id if parties act as a single unit in some contexts.
    # The type of entity can be inferred from participants_json or a separate field if needed.
    current_turn_entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_turn_entity_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # E.g., "player", "npc", "party"

    # JSONB fields for flexible data storage
    turn_order_json: Mapped[Optional[dict]] = mapped_column(JsonBForSQLite, nullable=True) # E.g., {"order": [{"id": 123, "type": "player"}, {"id": 45, "type": "npc"}], "current_index": 0}
    rules_config_snapshot_json: Mapped[Optional[dict]] = mapped_column(JsonBForSQLite, nullable=True) # Snapshot of RuleConfig relevant to this combat

    # participants_json: Could store a list of participant details.
    # E.g., {"entities": [{"id": 123, "type": "player", "team": "A", "initial_hp": 100, "current_hp": 80, "status_effects": []}, ...]}
    participants_json: Mapped[Optional[dict]] = mapped_column(JsonBForSQLite, nullable=True)

    # combat_log_json: Could store a chronological log of actions and events specific to this combat.
    # E.g., {"entries": [{"turn": 1, "actor_id": 123, "action": "attack", "target_id": 45, "damage": 10, "timestamp": "..."}]}
    combat_log_json: Mapped[Optional[dict]] = mapped_column(JsonBForSQLite, nullable=True)

    # Relationships
    guild: Mapped["GuildConfig"] = relationship(back_populates="combat_encounters")
    location: Mapped[Optional["Location"]] = relationship() # No back_populates needed if Location doesn't need to list combats directly

    def __repr__(self) -> str:
        return f"<CombatEncounter(id={self.id}, guild_id={self.guild_id}, status='{self.status.value}')>"
