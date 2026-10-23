"""add conversation_id to documents

Revision ID: 855e7699a9c6
Revises: 8b09e014fdae
Create Date: 2026-10-02 15:15:50.548377

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


# revision identifiers, used by Alembic.
revision: str = '855e7699a9c6'
down_revision: Union[str, Sequence[str], None] = '8b09e014fdae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'documents',
        sa.Column('conversation_id', PG_UUID(as_uuid=True), sa.ForeignKey('conversations.id', ondelete='SET NULL'), nullable=True)
    )
    op.create_index('ix_documents_conversation_id', 'documents', ['conversation_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_documents_conversation_id', table_name='documents')
    op.drop_column('documents', 'conversation_id')
