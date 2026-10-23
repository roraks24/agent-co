"""add password_hash to users table

Revision ID: 8b09e014fdae
Revises: 6184867eb413
Create Date: 2026-10-01 18:44:56.038898

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b09e014fdae'
down_revision: Union[str, Sequence[str], None] = '6184867eb413'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('password_hash', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'password_hash')
