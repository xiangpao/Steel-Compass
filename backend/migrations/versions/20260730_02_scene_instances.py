"""add versioned scene instances

Revision ID: 20260730_02
Revises: 20260730_01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260730_02"
down_revision = "20260730_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "scene_instances" in set(inspector.get_table_names()):
        return
    op.create_table(
        "scene_instances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("family_id", sa.String(80), nullable=False),
        sa.Column("variant_id", sa.String(80), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("template_version", sa.String(40), nullable=False),
        sa.Column("draft_state", sa.JSON(), nullable=False),
        sa.Column("stale_node_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_scene_instances_project_id", "scene_instances", ["project_id"]
    )
    op.create_index(
        "ix_scene_instances_family_id", "scene_instances", ["family_id"]
    )


def downgrade() -> None:
    if "scene_instances" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("scene_instances")
