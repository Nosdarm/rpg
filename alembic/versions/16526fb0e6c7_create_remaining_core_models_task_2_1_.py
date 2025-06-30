"""create_remaining_core_models_task_2_1_manual

Revision ID: 16526fb0e6c7
Revises: 0004
Create Date: 2025-06-30 23:30:07.429933

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Import Enums from the project
try:
    from src.models.enums import (
        OwnerEntityType, EventType, RelationshipEntityType, QuestStatus
    )
except ImportError:
    # Fallback for environments where src might not be in PYTHONPATH directly for Alembic
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parents[2])) # Adds project root
    from src.models.enums import (
        OwnerEntityType, EventType, RelationshipEntityType, QuestStatus
    )

# revision identifiers, used by Alembic.
revision: str = '16526fb0e6c7'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### Manually created migration ###

    # Create ENUM types for PostgreSQL
    # The 'create_type=True' argument for postgresql.ENUM is important for new types.
    # For existing types managed by SQLAlchemy's Enum, it might not be needed if checkfirst=True handles it.
    # However, for clarity and ensuring creation, it's good to be explicit.
    op.execute("CREATE TYPE owner_entity_type_enum AS ENUM ('PLAYER', 'GENERATED_NPC', 'PARTY', 'LOCATION_CONTAINER')")
    op.execute("CREATE TYPE event_type_enum AS ENUM ('PLAYER_ACTION', 'NPC_ACTION', 'SYSTEM_EVENT', 'COMBAT_START', 'COMBAT_ACTION', 'COMBAT_END', 'MOVEMENT', 'DIALOGUE_START', 'DIALOGUE_LINE', 'DIALOGUE_END', 'QUEST_ACCEPTED', 'QUEST_STEP_COMPLETED', 'QUEST_COMPLETED', 'QUEST_FAILED', 'ITEM_ACQUIRED', 'ITEM_USED', 'ITEM_DROPPED', 'TRADE_INITIATED', 'TRADE_COMPLETED', 'LEVEL_UP', 'XP_GAINED', 'RELATIONSHIP_CHANGE', 'FACTION_CHANGE', 'WORLD_STATE_CHANGE', 'MASTER_COMMAND', 'ERROR_EVENT')")
    op.execute("CREATE TYPE relationship_entity_type_enum AS ENUM ('PLAYER', 'PARTY', 'GENERATED_NPC', 'GENERATED_FACTION')")
    op.execute("CREATE TYPE quest_status_enum AS ENUM ('NOT_STARTED', 'ACTIVE', 'COMPLETED', 'FAILED', 'ABANDONED')")


    # Table: generated_npcs
    op.create_table('generated_npcs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=False),
        sa.Column('static_id', sa.Text(), nullable=True),
        sa.Column('name_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('description_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('current_location_id', sa.Integer(), nullable=True),
        sa.Column('npc_type_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('properties_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('ai_metadata_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], name=op.f('fk_generated_npcs_guild_id_guild_configs'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['current_location_id'], ['locations.id'], name=op.f('fk_generated_npcs_current_location_id_locations'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_generated_npcs'))
    )
    op.create_index(op.f('ix_generated_npcs_id'), 'generated_npcs', ['id'], unique=False)
    op.create_index(op.f('ix_generated_npcs_guild_id'), 'generated_npcs', ['guild_id'], unique=False)
    op.create_index(op.f('ix_generated_npcs_static_id'), 'generated_npcs', ['static_id'], unique=False)
    op.create_index(op.f('ix_generated_npcs_current_location_id'), 'generated_npcs', ['current_location_id'], unique=False)
    op.create_index('ix_generated_npcs_guild_id_static_id', 'generated_npcs', ['guild_id', 'static_id'], unique=True)

    # Table: generated_factions
    op.create_table('generated_factions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=False),
        sa.Column('static_id', sa.Text(), nullable=True),
        sa.Column('name_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('description_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('ideology_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('leader_npc_id', sa.Integer(), nullable=True),
        sa.Column('resources_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('ai_metadata_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], name=op.f('fk_generated_factions_guild_id_guild_configs'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['leader_npc_id'], ['generated_npcs.id'], name=op.f('fk_generated_factions_leader_npc_id_generated_npcs'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_generated_factions'))
    )
    op.create_index(op.f('ix_generated_factions_id'), 'generated_factions', ['id'], unique=False)
    op.create_index(op.f('ix_generated_factions_guild_id'), 'generated_factions', ['guild_id'], unique=False)
    op.create_index(op.f('ix_generated_factions_static_id'), 'generated_factions', ['static_id'], unique=False)
    op.create_index(op.f('ix_generated_factions_leader_npc_id'), 'generated_factions', ['leader_npc_id'], unique=False)
    op.create_index('ix_generated_factions_guild_id_static_id', 'generated_factions', ['guild_id', 'static_id'], unique=True)

    # Table: items
    op.create_table('items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=False),
        sa.Column('static_id', sa.Text(), nullable=True),
        sa.Column('name_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('description_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('item_type_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('item_category_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('base_value', sa.Integer(), nullable=True),
        sa.Column('properties_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], name=op.f('fk_items_guild_id_guild_configs'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_items'))
    )
    op.create_index(op.f('ix_items_id'), 'items', ['id'], unique=False)
    op.create_index(op.f('ix_items_guild_id'), 'items', ['guild_id'], unique=False)
    op.create_index(op.f('ix_items_static_id'), 'items', ['static_id'], unique=False)
    op.create_index('ix_items_guild_id_static_id', 'items', ['guild_id', 'static_id'], unique=True)

    # Table: inventory_items
    op.create_table('inventory_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=False),
        sa.Column('owner_entity_type', sa.Enum('PLAYER', 'GENERATED_NPC', 'PARTY', 'LOCATION_CONTAINER', name='owner_entity_type_enum'), nullable=False),
        sa.Column('owner_entity_id', sa.BigInteger(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), server_default=sa.text('1'), nullable=False),
        sa.Column('instance_specific_properties_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], name=op.f('fk_inventory_items_guild_id_guild_configs'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_inventory_items_item_id_items'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_inventory_items')),
        sa.UniqueConstraint('guild_id', 'owner_entity_type', 'owner_entity_id', 'item_id', name='uq_inventory_owner_item')
    )
    op.create_index(op.f('ix_inventory_items_id'), 'inventory_items', ['id'], unique=False)
    op.create_index(op.f('ix_inventory_items_guild_id'), 'inventory_items', ['guild_id'], unique=False)
    op.create_index(op.f('ix_inventory_items_owner_entity_type'), 'inventory_items', ['owner_entity_type'], unique=False)
    op.create_index(op.f('ix_inventory_items_owner_entity_id'), 'inventory_items', ['owner_entity_id'], unique=False)
    op.create_index(op.f('ix_inventory_items_item_id'), 'inventory_items', ['item_id'], unique=False)

    # Table: story_logs
    op.create_table('story_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('event_type', sa.Enum('PLAYER_ACTION', 'NPC_ACTION', 'SYSTEM_EVENT', 'COMBAT_START', 'COMBAT_ACTION', 'COMBAT_END', 'MOVEMENT', 'DIALOGUE_START', 'DIALOGUE_LINE', 'DIALOGUE_END', 'QUEST_ACCEPTED', 'QUEST_STEP_COMPLETED', 'QUEST_COMPLETED', 'QUEST_FAILED', 'ITEM_ACQUIRED', 'ITEM_USED', 'ITEM_DROPPED', 'TRADE_INITIATED', 'TRADE_COMPLETED', 'LEVEL_UP', 'XP_GAINED', 'RELATIONSHIP_CHANGE', 'FACTION_CHANGE', 'WORLD_STATE_CHANGE', 'MASTER_COMMAND', 'ERROR_EVENT', name='event_type_enum'), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=True),
        sa.Column('entity_ids_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('details_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('narrative_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], name=op.f('fk_story_logs_guild_id_guild_configs'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], name=op.f('fk_story_logs_location_id_locations'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_story_logs'))
    )
    op.create_index(op.f('ix_story_logs_id'), 'story_logs', ['id'], unique=False)
    op.create_index(op.f('ix_story_logs_guild_id'), 'story_logs', ['guild_id'], unique=False)
    op.create_index(op.f('ix_story_logs_timestamp'), 'story_logs', ['timestamp'], unique=False)
    op.create_index(op.f('ix_story_logs_event_type'), 'story_logs', ['event_type'], unique=False)
    op.create_index(op.f('ix_story_logs_location_id'), 'story_logs', ['location_id'], unique=False)

    # Table: relationships
    op.create_table('relationships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=False),
        sa.Column('entity1_type', sa.Enum('PLAYER', 'PARTY', 'GENERATED_NPC', 'GENERATED_FACTION', name='relationship_entity_type_enum'), nullable=False),
        sa.Column('entity1_id', sa.BigInteger(), nullable=False),
        sa.Column('entity2_type', sa.Enum('PLAYER', 'PARTY', 'GENERATED_NPC', 'GENERATED_FACTION', name='relationship_entity_type_enum'), nullable=False),
        sa.Column('entity2_id', sa.BigInteger(), nullable=False),
        sa.Column('relationship_type_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('value', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('ai_metadata_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], name=op.f('fk_relationships_guild_id_guild_configs'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_relationships')),
        sa.UniqueConstraint('guild_id', 'entity1_type', 'entity1_id', 'entity2_type', 'entity2_id', name='uq_relationship_entities')
    )
    op.create_index(op.f('ix_relationships_id'), 'relationships', ['id'], unique=False)
    op.create_index(op.f('ix_relationships_guild_id'), 'relationships', ['guild_id'], unique=False)
    op.create_index(op.f('ix_relationships_entity1_type'), 'relationships', ['entity1_type'], unique=False)
    op.create_index(op.f('ix_relationships_entity1_id'), 'relationships', ['entity1_id'], unique=False)
    op.create_index(op.f('ix_relationships_entity2_type'), 'relationships', ['entity2_type'], unique=False)
    op.create_index(op.f('ix_relationships_entity2_id'), 'relationships', ['entity2_id'], unique=False)
    op.create_index(op.f('ix_relationships_value'), 'relationships', ['value'], unique=False)

    # Table: player_npc_memories
    op.create_table('player_npc_memories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('npc_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.Text(), nullable=True),
        sa.Column('memory_details_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('memory_data_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('ai_significance_score', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], name=op.f('fk_player_npc_memories_guild_id_guild_configs'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], name=op.f('fk_player_npc_memories_player_id_players'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['npc_id'], ['generated_npcs.id'], name=op.f('fk_player_npc_memories_npc_id_generated_npcs'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_player_npc_memories'))
    )
    op.create_index(op.f('ix_player_npc_memories_id'), 'player_npc_memories', ['id'], unique=False)
    op.create_index(op.f('ix_player_npc_memories_guild_id'), 'player_npc_memories', ['guild_id'], unique=False)
    op.create_index(op.f('ix_player_npc_memories_player_id'), 'player_npc_memories', ['player_id'], unique=False)
    op.create_index(op.f('ix_player_npc_memories_npc_id'), 'player_npc_memories', ['npc_id'], unique=False)
    op.create_index(op.f('ix_player_npc_memories_event_type'), 'player_npc_memories', ['event_type'], unique=False)
    op.create_index(op.f('ix_player_npc_memories_timestamp'), 'player_npc_memories', ['timestamp'], unique=False)

    # Table: abilities
    op.create_table('abilities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=True),
        sa.Column('static_id', sa.Text(), nullable=False),
        sa.Column('name_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('description_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('effects_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], name=op.f('fk_abilities_guild_id_guild_configs'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_abilities')),
        sa.UniqueConstraint('guild_id', 'static_id', name='uq_ability_guild_static_id')
    )
    op.create_index(op.f('ix_abilities_id'), 'abilities', ['id'], unique=False)
    op.create_index(op.f('ix_abilities_guild_id'), 'abilities', ['guild_id'], unique=False)
    op.create_index(op.f('ix_abilities_static_id'), 'abilities', ['static_id'], unique=False)

    # Table: skills
    op.create_table('skills',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=True),
        sa.Column('static_id', sa.Text(), nullable=False),
        sa.Column('name_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('description_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('related_attribute_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('properties_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], name=op.f('fk_skills_guild_id_guild_configs'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_skills')),
        sa.UniqueConstraint('guild_id', 'static_id', name='uq_skill_guild_static_id')
    )
    op.create_index(op.f('ix_skills_id'), 'skills', ['id'], unique=False)
    op.create_index(op.f('ix_skills_guild_id'), 'skills', ['guild_id'], unique=False)
    op.create_index(op.f('ix_skills_static_id'), 'skills', ['static_id'], unique=False)

    # Table: status_effects
    op.create_table('status_effects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=True),
        sa.Column('static_id', sa.Text(), nullable=False),
        sa.Column('name_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('description_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('effects_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], name=op.f('fk_status_effects_guild_id_guild_configs'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_status_effects')),
        sa.UniqueConstraint('guild_id', 'static_id', name='uq_status_effect_guild_static_id')
    )
    op.create_index(op.f('ix_status_effects_id'), 'status_effects', ['id'], unique=False)
    op.create_index(op.f('ix_status_effects_guild_id'), 'status_effects', ['guild_id'], unique=False)
    op.create_index(op.f('ix_status_effects_static_id'), 'status_effects', ['static_id'], unique=False)

    # Table: active_status_effects
    op.create_table('active_status_effects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=False),
        sa.Column('entity_type', sa.Enum('PLAYER', 'PARTY', 'GENERATED_NPC', 'GENERATED_FACTION', name='relationship_entity_type_enum'), nullable=False),
        sa.Column('entity_id', sa.BigInteger(), nullable=False),
        sa.Column('status_effect_id', sa.Integer(), nullable=False),
        sa.Column('applied_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('duration_turns', sa.Integer(), nullable=True),
        sa.Column('remaining_turns', sa.Integer(), nullable=True),
        sa.Column('source_ability_id', sa.Integer(), nullable=True),
        sa.Column('data_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], name=op.f('fk_active_status_effects_guild_id_guild_configs'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['status_effect_id'], ['status_effects.id'], name=op.f('fk_active_status_effects_status_effect_id_status_effects'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_ability_id'], ['abilities.id'], name=op.f('fk_active_status_effects_source_ability_id_abilities'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_active_status_effects')),
        sa.UniqueConstraint('guild_id', 'entity_type', 'entity_id', 'status_effect_id', name='uq_active_status_entity_effect')
    )
    op.create_index(op.f('ix_active_status_effects_id'), 'active_status_effects', ['id'], unique=False)
    op.create_index(op.f('ix_active_status_effects_guild_id'), 'active_status_effects', ['guild_id'], unique=False)
    op.create_index(op.f('ix_active_status_effects_entity_type'), 'active_status_effects', ['entity_type'], unique=False)
    op.create_index(op.f('ix_active_status_effects_entity_id'), 'active_status_effects', ['entity_id'], unique=False)
    op.create_index(op.f('ix_active_status_effects_status_effect_id'), 'active_status_effects', ['status_effect_id'], unique=False)
    op.create_index('ix_active_status_effects_entity', 'active_status_effects', ['guild_id', 'entity_type', 'entity_id'], unique=False)

    # Table: questlines
    op.create_table('questlines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=False),
        sa.Column('static_id', sa.Text(), nullable=False),
        sa.Column('name_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('description_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], name=op.f('fk_questlines_guild_id_guild_configs'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_questlines')),
        sa.UniqueConstraint('guild_id', 'static_id', name='uq_questline_guild_static_id')
    )
    op.create_index(op.f('ix_questlines_id'), 'questlines', ['id'], unique=False)
    op.create_index(op.f('ix_questlines_guild_id'), 'questlines', ['guild_id'], unique=False)
    op.create_index(op.f('ix_questlines_static_id'), 'questlines', ['static_id'], unique=False)

    # Table: generated_quests
    op.create_table('generated_quests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=False),
        sa.Column('static_id', sa.Text(), nullable=False),
        sa.Column('title_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('description_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('questline_id', sa.Integer(), nullable=True),
        sa.Column('giver_entity_type', sa.Enum('PLAYER', 'PARTY', 'GENERATED_NPC', 'GENERATED_FACTION', name='relationship_entity_type_enum'), nullable=True),
        sa.Column('giver_entity_id', sa.BigInteger(), nullable=True),
        sa.Column('min_level', sa.Integer(), nullable=True),
        sa.Column('rewards_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('ai_metadata_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], name=op.f('fk_generated_quests_guild_id_guild_configs'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['questline_id'], ['questlines.id'], name=op.f('fk_generated_quests_questline_id_questlines'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_generated_quests')),
        sa.UniqueConstraint('guild_id', 'static_id', name='uq_generated_quest_guild_static_id')
    )
    op.create_index(op.f('ix_generated_quests_id'), 'generated_quests', ['id'], unique=False)
    op.create_index(op.f('ix_generated_quests_guild_id'), 'generated_quests', ['guild_id'], unique=False)
    op.create_index(op.f('ix_generated_quests_static_id'), 'generated_quests', ['static_id'], unique=False)
    op.create_index(op.f('ix_generated_quests_questline_id'), 'generated_quests', ['questline_id'], unique=False)
    op.create_index('ix_generated_quests_giver', 'generated_quests', ['guild_id', 'giver_entity_type', 'giver_entity_id'], unique=False)

    # Table: quest_steps
    op.create_table('quest_steps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('quest_id', sa.Integer(), nullable=False),
        sa.Column('step_order', sa.Integer(), server_default=sa.text('1'), nullable=False),
        sa.Column('title_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('description_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('required_mechanics_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('abstract_goal_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('consequences_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.ForeignKeyConstraint(['quest_id'], ['generated_quests.id'], name=op.f('fk_quest_steps_quest_id_generated_quests'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_quest_steps')),
        sa.UniqueConstraint('quest_id', 'step_order', name='uq_quest_step_order')
    )
    op.create_index(op.f('ix_quest_steps_id'), 'quest_steps', ['id'], unique=False)
    op.create_index(op.f('ix_quest_steps_quest_id'), 'quest_steps', ['quest_id'], unique=False)

    # Table: player_quest_progress
    op.create_table('player_quest_progress',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('quest_id', sa.Integer(), nullable=False),
        sa.Column('current_step_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.Enum('NOT_STARTED', 'ACTIVE', 'COMPLETED', 'FAILED', 'ABANDONED', name='quest_status_enum'), server_default='NOT_STARTED', nullable=False),
        sa.Column('progress_data_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], name=op.f('fk_player_quest_progress_guild_id_guild_configs'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], name=op.f('fk_player_quest_progress_player_id_players'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['quest_id'], ['generated_quests.id'], name=op.f('fk_player_quest_progress_quest_id_generated_quests'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['current_step_id'], ['quest_steps.id'], name=op.f('fk_player_quest_progress_current_step_id_quest_steps'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_player_quest_progress')),
        sa.UniqueConstraint('guild_id', 'player_id', 'quest_id', name='uq_player_quest')
    )
    op.create_index(op.f('ix_player_quest_progress_id'), 'player_quest_progress', ['id'], unique=False)
    op.create_index(op.f('ix_player_quest_progress_guild_id'), 'player_quest_progress', ['guild_id'], unique=False)
    op.create_index(op.f('ix_player_quest_progress_player_id'), 'player_quest_progress', ['player_id'], unique=False)
    op.create_index(op.f('ix_player_quest_progress_quest_id'), 'player_quest_progress', ['quest_id'], unique=False)
    op.create_index(op.f('ix_player_quest_progress_current_step_id'), 'player_quest_progress', ['current_step_id'], unique=False)
    op.create_index(op.f('ix_player_quest_progress_status'), 'player_quest_progress', ['status'], unique=False)

    # Table: mobile_groups
    op.create_table('mobile_groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=False),
        sa.Column('name_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('current_location_id', sa.Integer(), nullable=True),
        sa.Column('members_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('behavior_type_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('route_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('ai_metadata_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], name=op.f('fk_mobile_groups_guild_id_guild_configs'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['current_location_id'], ['locations.id'], name=op.f('fk_mobile_groups_current_location_id_locations'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_mobile_groups'))
    )
    op.create_index(op.f('ix_mobile_groups_id'), 'mobile_groups', ['id'], unique=False)
    op.create_index(op.f('ix_mobile_groups_guild_id'), 'mobile_groups', ['guild_id'], unique=False)
    op.create_index(op.f('ix_mobile_groups_current_location_id'), 'mobile_groups', ['current_location_id'], unique=False)

    # Table: crafting_recipes
    op.create_table('crafting_recipes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=True),
        sa.Column('static_id', sa.Text(), nullable=False),
        sa.Column('name_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('description_i18n', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('result_item_id', sa.Integer(), nullable=False),
        sa.Column('result_quantity', sa.Integer(), server_default=sa.text('1'), nullable=False),
        sa.Column('ingredients_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('required_skill_id', sa.Integer(), nullable=True),
        sa.Column('required_skill_level', sa.Integer(), nullable=True),
        sa.Column('properties_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], name=op.f('fk_crafting_recipes_guild_id_guild_configs'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['result_item_id'], ['items.id'], name=op.f('fk_crafting_recipes_result_item_id_items'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['required_skill_id'], ['skills.id'], name=op.f('fk_crafting_recipes_required_skill_id_skills'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_crafting_recipes')),
        sa.UniqueConstraint('guild_id', 'static_id', name='uq_crafting_recipe_guild_static_id')
    )
    op.create_index(op.f('ix_crafting_recipes_id'), 'crafting_recipes', ['id'], unique=False)
    op.create_index(op.f('ix_crafting_recipes_guild_id'), 'crafting_recipes', ['guild_id'], unique=False)
    op.create_index(op.f('ix_crafting_recipes_static_id'), 'crafting_recipes', ['static_id'], unique=False)
    op.create_index(op.f('ix_crafting_recipes_result_item_id'), 'crafting_recipes', ['result_item_id'], unique=False)
    op.create_index(op.f('ix_crafting_recipes_required_skill_id'), 'crafting_recipes', ['required_skill_id'], unique=False)

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### Manually created migration ###
    op.drop_table('crafting_recipes')
    op.drop_table('mobile_groups')
    op.drop_table('player_quest_progress')
    op.drop_table('quest_steps')
    op.drop_table('generated_quests')
    op.drop_table('questlines')
    op.drop_table('active_status_effects')
    op.drop_table('status_effects')
    op.drop_table('skills')
    op.drop_table('abilities')
    op.drop_table('player_npc_memories')
    op.drop_table('relationships')
    op.drop_table('story_logs')
    op.drop_table('inventory_items')
    op.drop_table('items')
    op.drop_table('generated_factions')
    op.drop_table('generated_npcs')

    # Drop ENUM types
    op.execute("DROP TYPE quest_status_enum")
    op.execute("DROP TYPE relationship_entity_type_enum")
    op.execute("DROP TYPE event_type_enum")
    op.execute("DROP TYPE owner_entity_type_enum")
    # ### end Alembic commands ###
