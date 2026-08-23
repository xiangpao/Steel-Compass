"""add immutable scene analysis snapshots

Revision ID: 20260813_07
Revises: 20260811_06
"""

from alembic import op
import sqlalchemy as sa


revision = "20260813_07"
down_revision = "20260811_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scene_analysis_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("scene_instance_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_number", sa.Integer(), nullable=False),
        sa.Column("snapshot_schema_version", sa.String(length=20), nullable=False),
        sa.Column("standard_profile", sa.String(length=40), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("report_number", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_instance_id"], ["scene_instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scene_instance_id",
            "content_hash",
            name="uq_scene_analysis_instance_content_hash",
        ),
        sa.UniqueConstraint("scene_instance_id", "snapshot_number", name="uq_scene_analysis_snapshot"),
        sa.UniqueConstraint("report_number"),
    )
    op.create_index("ix_scene_analysis_snapshots_project_id", "scene_analysis_snapshots", ["project_id"])
    op.create_index("ix_scene_analysis_snapshots_scene_instance_id", "scene_analysis_snapshots", ["scene_instance_id"])
    op.create_index("ix_scene_analysis_snapshots_content_hash", "scene_analysis_snapshots", ["content_hash"])
    op.create_index("ix_scene_analysis_snapshots_report_number", "scene_analysis_snapshots", ["report_number"])


def downgrade() -> None:
    op.drop_index("ix_scene_analysis_snapshots_report_number", table_name="scene_analysis_snapshots")
    op.drop_index("ix_scene_analysis_snapshots_content_hash", table_name="scene_analysis_snapshots")
    op.drop_index("ix_scene_analysis_snapshots_scene_instance_id", table_name="scene_analysis_snapshots")
    op.drop_index("ix_scene_analysis_snapshots_project_id", table_name="scene_analysis_snapshots")
    op.drop_table("scene_analysis_snapshots")
