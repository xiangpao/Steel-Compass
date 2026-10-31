"""add project custom steel sections

Revision ID: 20260811_06
Revises: 20260811_05
"""

from alembic import op
import sqlalchemy as sa


revision = "20260811_06"
down_revision = "20260811_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Databases created by Base.metadata.create_all already have the column.
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("projects")}
    if "custom_sections" in columns:
        return
    op.add_column(
        "projects",
        sa.Column("custom_sections", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("projects", "custom_sections")
