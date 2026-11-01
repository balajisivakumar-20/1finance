"""user google sub

Revision ID: c7a4e2f19b30
Revises: b3e1c9d4a2f7
Create Date: 2026-11-01 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c7a4e2f19b30'
down_revision: Union[str, Sequence[str], None] = 'b3e1c9d4a2f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('google_sub', sa.String(length=64), nullable=True))
    op.create_unique_constraint('users_google_sub_key', 'users', ['google_sub'])


def downgrade() -> None:
    op.drop_constraint('users_google_sub_key', 'users', type_='unique')
    op.drop_column('users', 'google_sub')
