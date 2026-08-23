"""add project geotechnical profile

Revision ID: 20260811_05
Revises: 20260809_04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260811_05"
down_revision = "20260809_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("projects")}
    if "geotechnical_profile" not in columns:
        with op.batch_alter_table("projects") as batch_op:
            batch_op.add_column(sa.Column("geotechnical_profile", sa.JSON(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("projects")}
    if "geotechnical_profile" in columns:
        with op.batch_alter_table("projects") as batch_op:
            batch_op.drop_column("geotechnical_profile")
