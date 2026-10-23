"""remove workspace logic totally from backend

Revision ID: c0e819fa24de
Revises: 855e7699a9c6
Create Date: 2026-10-02 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


# revision identifiers, used by Alembic.
revision: str = 'c0e819fa24de'
down_revision: Union[str, Sequence[str], None] = '855e7699a9c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add user_id column to documents (nullable initially for data backfill)
    op.add_column(
        'documents',
        sa.Column('user_id', PG_UUID(as_uuid=True), nullable=True)
    )

    # 2. Backfill user_id from conversations if conversation_id is present
    op.execute(
        """
        UPDATE documents
        SET user_id = (SELECT user_id FROM conversations WHERE conversations.id = documents.conversation_id)
        WHERE documents.conversation_id IS NOT NULL AND documents.user_id IS NULL;
        """
    )

    # 3. Fallback backfill for any orphaned documents to first user in system
    op.execute(
        """
        UPDATE documents
        SET user_id = (SELECT id FROM users LIMIT 1)
        WHERE user_id IS NULL;
        """
    )

    # 4. Set user_id on documents to non-nullable, add FK constraint and index
    op.alter_column('documents', 'user_id', nullable=False)
    op.create_foreign_key(
        'documents_user_id_fkey',
        'documents',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE'
    )
    op.create_index('ix_documents_user_id', 'documents', ['user_id'], unique=False)

    # 5. Drop workspace_id from documents
    op.drop_constraint('documents_workspace_id_fkey', 'documents', type_='foreignkey')
    op.drop_column('documents', 'workspace_id')

    # 6. Drop workspace_id from conversations
    op.drop_constraint('conversations_workspace_id_fkey', 'conversations', type_='foreignkey')
    op.drop_index('ix_conversations_workspace_id', table_name='conversations')
    op.drop_column('conversations', 'workspace_id')

    # 7. Drop workspace_id from memories
    op.drop_constraint('memories_workspace_id_fkey', 'memories', type_='foreignkey')
    op.drop_index('ix_memories_workspace_id', table_name='memories')
    op.drop_column('memories', 'workspace_id')

    # 8. Drop workspace_members table
    op.drop_table('workspace_members')

    # 9. Drop workspaces table
    op.drop_table('workspaces')


def downgrade() -> None:
    # Recreate workspaces table
    op.create_table(
        'workspaces',
        sa.Column('id', PG_UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Recreate workspace_members table
    op.create_table(
        'workspace_members',
        sa.Column('workspace_id', PG_UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', PG_UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id']),
        sa.PrimaryKeyConstraint('workspace_id', 'user_id'),
    )
    # Re-add workspace_id to memories, conversations, documents
    op.add_column('memories', sa.Column('workspace_id', PG_UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('memories_workspace_id_fkey', 'memories', 'workspaces', ['workspace_id'], ['id'])
    op.create_index('ix_memories_workspace_id', 'memories', ['workspace_id'], unique=False)

    op.add_column('conversations', sa.Column('workspace_id', PG_UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('conversations_workspace_id_fkey', 'conversations', 'workspaces', ['workspace_id'], ['id'])
    op.create_index('ix_conversations_workspace_id', 'conversations', ['workspace_id'], unique=False)

    op.add_column('documents', sa.Column('workspace_id', PG_UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('documents_workspace_id_fkey', 'documents', 'workspaces', ['workspace_id'], ['id'])

    op.drop_index('ix_documents_user_id', table_name='documents')
    op.drop_constraint('documents_user_id_fkey', 'documents', type_='foreignkey')
    op.drop_column('documents', 'user_id')
