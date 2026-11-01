"""goal contribution note

Revision ID: b3e1c9d4a2f7
Revises: 7101322892a8
Create Date: 2026-11-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b3e1c9d4a2f7'
down_revision: Union[str, Sequence[str], None] = '7101322892a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('goals_contributions', sa.Column('note', sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('goals_contributions', 'note')
