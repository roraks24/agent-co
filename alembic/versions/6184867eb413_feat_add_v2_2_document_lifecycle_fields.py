"""feat: add V2.2 document lifecycle fields

Revision ID: 6184867eb413
Revises: b56ab54c4f90
Create Date: 2026-09-29 20:37:47.800617

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6184867eb413"
down_revision: Union[str, Sequence[str], None] = "b56ab54c4f90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add V2.2 document lifecycle fields safely."""

    op.add_column(
        "documents",
        sa.Column(
            "display_name",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "mime_type",
            sa.String(length=100),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "chunk_count",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "storage_key",
            sa.String(length=500),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "checksum_sha256",
            sa.String(length=64),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "failure_reason",
            sa.Text(),
            nullable=True,
        ),
    )

    op.execute(
        """
        UPDATE documents
        SET display_name =
            COALESCE(
                NULLIF(TRIM(original_filename), ''),
                filename
            )
        """
    )

    op.execute(
        """
        UPDATE documents
        SET mime_type =
            CASE
                WHEN LOWER(file_type) = 'pdf' THEN 'application/pdf'
                WHEN LOWER(file_type) = 'txt' THEN 'text/plain'
                WHEN LOWER(file_type) = 'md' THEN 'text/markdown'
                WHEN LOWER(file_type) = 'docx' THEN 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                ELSE 'application/octet-stream'
            END
        """
    )

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            """
            UPDATE documents
            SET storage_key = 'documents/' || id || '/' || filename
            """
        )
        op.execute(
            """
            UPDATE documents
            SET chunk_count = (
                SELECT COUNT(*)
                FROM document_chunks
                WHERE document_chunks.document_id = documents.id
            )
            """
        )
    else:
        op.execute(
            """
            UPDATE documents
            SET storage_key = CONCAT('documents/', id, '/', filename)
            """
        )
        op.execute(
            """
            UPDATE documents d
            SET chunk_count = (
                SELECT COUNT(*)
                FROM document_chunks dc
                WHERE dc.document_id = d.id
            )
            """
        )

    op.alter_column(
        "documents",
        "display_name",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    op.alter_column(
        "documents",
        "mime_type",
        existing_type=sa.String(length=100),
        nullable=False,
    )

    op.alter_column(
        "documents",
        "chunk_count",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.alter_column(
        "documents",
        "storage_key",
        existing_type=sa.String(length=500),
        nullable=False,
    )

    op.create_index(
        "ix_documents_checksum_sha256",
        "documents",
        ["checksum_sha256"],
        unique=False,
    )


def downgrade() -> None:
    """Revert V2.2 document lifecycle fields."""

    op.drop_index(
        "ix_documents_checksum_sha256",
        table_name="documents",
    )

    op.drop_column("documents", "failure_reason")
    op.drop_column("documents", "checksum_sha256")
    op.drop_column("documents", "storage_key")
    op.drop_column("documents", "chunk_count")
    op.drop_column("documents", "mime_type")
    op.drop_column("documents", "display_name")
