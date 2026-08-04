"""baseline existing schema and add project revisions

Revision ID: 20260730_01
Revises:
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260730_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(80), nullable=False),
            sa.Column("display_name", sa.String(120), nullable=False),
            sa.Column("password_hash", sa.String(512), nullable=False),
            sa.Column("is_admin", sa.Boolean(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("must_change_password", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("username"),
        )
        op.create_index("ix_users_username", "users", ["username"], unique=True)
    if "login_sessions" not in existing:
        op.create_table(
            "login_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index(
            "ix_login_sessions_token_hash",
            "login_sessions",
            ["token_hash"],
            unique=True,
        )
        op.create_index(
            "ix_login_sessions_expires_at",
            "login_sessions",
            ["expires_at"],
        )
    if "projects" not in existing:
        op.create_table(
            "projects",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("owner_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_projects_owner_id", "projects", ["owner_id"])
    if "project_versions" not in existing:
        op.create_table(
            "project_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("calculation_input", sa.JSON(), nullable=False),
            sa.Column("calculation_result", sa.JSON(), nullable=False),
            sa.Column("engine_version", sa.String(40), nullable=False),
            sa.Column("report_number", sa.String(80), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("project_id", "version_number", name="uq_project_version"),
            sa.UniqueConstraint("report_number"),
        )
        op.create_index(
            "ix_project_versions_project_id", "project_versions", ["project_id"]
        )
        op.create_index(
            "ix_project_versions_report_number",
            "project_versions",
            ["report_number"],
            unique=True,
        )
    if "project_revisions" not in existing:
        op.create_table(
            "project_revisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("revision_number", sa.Integer(), nullable=False),
            sa.Column("snapshot_schema_version", sa.String(20), nullable=False),
            sa.Column("snapshot", sa.JSON(), nullable=False),
            sa.Column("result_bundle", sa.JSON(), nullable=False),
            sa.Column("catalog_versions", sa.JSON(), nullable=False),
            sa.Column("engine_version", sa.String(40), nullable=False),
            sa.Column("report_number", sa.String(80), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "project_id", "revision_number", name="uq_project_revision"
            ),
            sa.UniqueConstraint("report_number"),
        )
        op.create_index(
            "ix_project_revisions_project_id", "project_revisions", ["project_id"]
        )
        op.create_index(
            "ix_project_revisions_report_number",
            "project_revisions",
            ["report_number"],
            unique=True,
        )


def downgrade() -> None:
    if "project_revisions" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("project_revisions")

