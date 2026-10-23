"""add_name_to_users

Revision ID: 47830d97fbcc
Revises: c0e819fa24de
Create Date: 2026-10-02 23:52:43.171972

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '47830d97fbcc'
down_revision: Union[str, Sequence[str], None] = 'c0e819fa24de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add name column to users table."""
    op.add_column('users', sa.Column('name', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema: drop name column from users table."""
    op.drop_column('users', 'name')
