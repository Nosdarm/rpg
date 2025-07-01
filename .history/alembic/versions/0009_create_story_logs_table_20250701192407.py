"""create_story_logs_table

Revision ID: 0009
Revises: 0008_add_player_sublocation
Create Date: 2025-07-01 15:56:33.212715

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008_add_player_sublocation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define the ENUM type and its values for event_type
event_type_enum_name = "eventtype" # Name used in StoryLog model is "event_type_enum", but PG default is tablename_columnname_enum or just columnname_enum.
                                   # The model used "event_type_enum". Let's stick to what the model expects if create_type=False.
                                   # However, the previous migration 16526fb0e6c7... might have already created it with a specific name.
                                   # For robustness, let's use the name "eventtype" as it's a common practice for Alembic-managed enums.
                                   # If "event_type_enum" was already created by a (now missing) migration, this might cause issues.
                                   # Given the uncertainty, I will use "eventtype" and assume it's a new type for this migration.
                                   # If StoryLog model expects "event_type_enum", that name should be used for the type in PG.
                                   # The model definition `SQLAlchemyEnum(EventType, name="event_type_enum", create_type=False)` means it expects a PG type named "event_type_enum".
event_type_enum_name_actual = "event_type_enum" # Aligning with model's expectation.

event_type_values = [
    "player_action", "npc_action", "system_event", "combat_start", "combat_action",
    "combat_end", "movement", "dialogue_start", "dialogue_line", "dialogue_end",
    "quest_accepted", "quest_step_completed", "quest_completed", "quest_failed",
    "item_acquired", "item_used", "item_dropped", "trade_initiated", "trade_completed",
    "level_up", "xp_gained", "relationship_change", "faction_change",
    "world_state_change", "master_command", "error_event"
]
eventtype_enum = postgresql.ENUM(*event_type_values, name=event_type_enum_name_actual, create_type=False)


def upgrade() -> None:
    """Upgrade schema."""
    # The ENUM type event_type_enum is expected to be created by a previous migration (e.g., initial schema).
    # eventtype_enum.create(op.get_bind(), checkfirst=True) # Removed redundant creation

    # The story_logs table and its indexes are created in the initial schema migration (4a069d44a15c_initial_schema.py).
    # Therefore, the following operations are redundant in this migration.
    # op.create_table(
    #     "story_logs",
    #     sa.Column("id", sa.Integer(), primary_key=True, index=True),
    #     sa.Column("guild_id", sa.BigInteger(), nullable=False, index=True),
    #     sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    #     sa.Column("location_id", sa.Integer(), nullable=True, index=True),
    #     sa.Column("event_type", eventtype_enum, nullable=False, index=True),
    #     sa.Column("entity_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    #     sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True), # Corrected to nullable=True to match model
    #     sa.Column("narrative_i18n", postgresql.JSONB(astext_type=sa.Text()), nullable=True), # Added from existing model

    #     sa.ForeignKeyConstraint(["guild_id"], ["guild_configs.id"], name=op.f("fk_story_logs_guild_id_guild_configs"), ondelete="CASCADE"),
    #     sa.ForeignKeyConstraint(["location_id"], ["locations.id"], name=op.f("fk_story_logs_location_id_locations"), ondelete="SET NULL"),
    # )
    # op.create_index(op.f("ix_story_logs_guild_id"), "story_logs", ["guild_id"], unique=False)
    # op.create_index(op.f("ix_story_logs_location_id"), "story_logs", ["location_id"], unique=False)
    # op.create_index(op.f("ix_story_logs_event_type"), "story_logs", ["event_type"], unique=False)
    # op.create_index(op.f("ix_story_logs_timestamp"), "story_logs", ["timestamp"], unique=False)
    pass # This migration is now effectively a no-op regarding schema changes for story_logs.


def downgrade() -> None:
    """Downgrade schema."""
    # Correspondingly, if upgrade does nothing for story_logs, downgrade should also do nothing.
    # op.drop_index(op.f("ix_story_logs_timestamp"), table_name="story_logs")
    # op.drop_index(op.f("ix_story_logs_event_type"), table_name="story_logs")
    # op.drop_index(op.f("ix_story_logs_location_id"), table_name="story_logs")
    # op.drop_index(op.f("ix_story_logs_guild_id"), table_name="story_logs")
    # op.drop_table("story_logs")
    pass # This migration is now effectively a no-op regarding schema changes for story_logs.

    # Drop the ENUM type - Removed: This migration does not own the ENUM creation.
    # eventtype_enum.drop(op.get_bind(), checkfirst=True)
