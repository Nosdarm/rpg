from sqlalchemy import BigInteger, Column, ForeignKey, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import Index
from typing import Optional, Dict, Any, List

from .base import Base
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
    # guild: Mapped["GuildConfig"] = relationship() # Optional

    name_i18n: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, default=lambda: {})
    # Example: {"en": "Wolf Pack Alpha", "ru": "Волчья стая Альфа"}

    current_location_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("locations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # current_location: Mapped[Optional["Location"]] = relationship() # Optional

    # Describes the composition of the group
    # Example: [{"npc_static_id": "wolf", "count": 5}, {"npc_static_id": "alpha_wolf", "count": 1}]
    # or [{"member_type": "generated_npc_id", "id": 123, "role": "leader"}, {"member_type": "template_npc_static_id", "static_id": "guard", "count": 3}]
    members_json: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=lambda: [])

    # Describes the behavior or purpose of the group
    # Example: {"en": "Patrolling the northern forests", "ru": "Патрулирует северные леса"}
    behavior_type_i18n: Mapped[Optional[Dict[str, str]]] = mapped_column(JSONB, nullable=True, default=lambda: {})

    # Defines a route if the group follows a specific path
    # Example: {"type": "patrol_points", "points": [1, 2, 5, 2], "current_target_index": 0, "loop": true}
    #          {"type": "destination", "target_location_id": 10}
    route_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True, default=lambda: {})

    # For AI control, faction allegiance, current state (e.g., "aggressive", "fleeing")
    ai_metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True, default=lambda: {})
    # Example:
    # {
    #   "faction_static_id": "bandits_redhand",
    #   "current_target_player_id": null,
    #   "state": "patrolling",
    #   "aggro_radius_meters": 30
    # }

    # May need a static_id if these groups can be predefined templates, but task implies more dynamic.
    # static_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)
    # __table_args__ = (
    #     Index("ix_mobile_groups_guild_id_static_id", "guild_id", "static_id", unique=True),
    # )

    def __repr__(self) -> str:
        return f"<MobileGroup(id={self.id}, guild_id={self.guild_id}, name='{self.name_i18n.get('en', 'N/A')}')>"
