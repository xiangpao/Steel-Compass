"""add project site profile

Revision ID: 20260809_04
Revises: 20260804_03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260809_04"
down_revision = "20260804_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("projects")}
    if "site_profile" not in columns:
        with op.batch_alter_table("projects") as batch_op:
            batch_op.add_column(sa.Column("site_profile", sa.JSON(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("projects")}
    if "site_profile" in columns:
        with op.batch_alter_table("projects") as batch_op:
            batch_op.drop_column("site_profile")
