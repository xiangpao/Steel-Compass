"""add archival state to scene instances

Revision ID: 20260804_03
Revises: 20260730_02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260804_03"
down_revision = "20260730_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("scene_instances")}
    if "archived" not in columns:
        with op.batch_alter_table("scene_instances") as batch_op:
            batch_op.add_column(
                sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false())
            )
            batch_op.create_index("ix_scene_instances_archived", ["archived"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("scene_instances")}
    if "archived" in columns:
        with op.batch_alter_table("scene_instances") as batch_op:
            batch_op.drop_index("ix_scene_instances_archived")
            batch_op.drop_column("archived")
