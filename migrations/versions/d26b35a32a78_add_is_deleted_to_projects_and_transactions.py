"""add is_deleted to projects and transactions

Revision ID: d26b35a32a78
Revises: 985c0e5e9a64
Create Date: 2026-09-19 20:04:09.823169

"""
import sqlalchemy as sa
from alembic import op

revision = "d26b35a32a78"
down_revision = "985c0e5e9a64"
branch_labels = None
depends_on = None


def upgrade():
    # ADD COLUMN с DEFAULT — SQLite поддерживает нативно.
    # batch_alter_table не нужен и ломается на FK от transactions → projects.
    op.add_column(
        "projects",
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index("ix_projects_is_deleted", "projects", ["is_deleted"])

    op.add_column(
        "transactions",
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index("ix_transactions_is_deleted", "transactions", ["is_deleted"])


def downgrade():
    op.drop_index("ix_transactions_is_deleted", table_name="transactions")
    op.drop_column("transactions", "is_deleted")

    op.drop_index("ix_projects_is_deleted", table_name="projects")
    op.drop_column("projects", "is_deleted")
