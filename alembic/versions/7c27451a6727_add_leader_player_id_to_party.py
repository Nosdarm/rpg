"""add_leader_player_id_to_party

Revision ID: 7c27451a6727
Revises: b3920fb77c09
Create Date: 2025-07-03 19:58:47.258867

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c27451a6727'
down_revision: Union[str, Sequence[str], None] = 'b3920fb77c09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('parties', sa.Column('leader_player_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_parties_leader_player_id'), 'parties', ['leader_player_id'], unique=False)
    op.create_foreign_key(
        "fk_party_leader_player_id",  # Constraint name, matches what's in model
        'parties', 'players',
        ['leader_player_id'], ['id'],
        ondelete="SET NULL" # Or "CASCADE" or None depending on desired behavior
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_party_leader_player_id", 'parties', type_='foreignkey')
    op.drop_index(op.f('ix_parties_leader_player_id'), table_name='parties')
    op.drop_column('parties', 'leader_player_id')
