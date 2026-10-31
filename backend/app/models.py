from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(512))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sessions: Mapped[list["LoginSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(back_populates="owner")


class LoginSession(Base):
    __tablename__ = "login_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="sessions")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    site_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    geotechnical_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    custom_sections: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    owner: Mapped[User] = relationship(back_populates="projects")
    versions: Mapped[list["ProjectVersion"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectVersion.version_number",
    )
    revisions: Mapped[list["ProjectRevision"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectRevision.revision_number",
    )
    scene_instances: Mapped[list["SceneInstance"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="SceneInstance.updated_at",
    )


class ProjectVersion(Base):
    __tablename__ = "project_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "version_number", name="uq_project_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    calculation_input: Mapped[dict] = mapped_column(JSON)
    calculation_result: Mapped[dict] = mapped_column(JSON)
    engine_version: Mapped[str] = mapped_column(String(40))
    report_number: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="versions")


class ProjectRevision(Base):
    __tablename__ = "project_revisions"
    __table_args__ = (
        UniqueConstraint("project_id", "revision_number", name="uq_project_revision"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer)
    # Scene revisions only: copy of snapshot["scene_context"]["scene_instance_id"]
    # so lookups need not load every snapshot. No FK: historical rows may name
    # instances that no longer exist.
    scene_instance_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    snapshot_schema_version: Mapped[str] = mapped_column(String(20), default="1.0")
    snapshot: Mapped[dict] = mapped_column(JSON)
    result_bundle: Mapped[dict] = mapped_column(JSON)
    catalog_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    engine_version: Mapped[str] = mapped_column(String(40))
    report_number: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="revisions")


class SceneInstance(Base):
    __tablename__ = "scene_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[str] = mapped_column(String(80), index=True)
    variant_id: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(120))
    mode: Mapped[str] = mapped_column(String(20), default="quick")
    template_version: Mapped[str] = mapped_column(String(40))
    draft_state: Mapped[dict] = mapped_column(JSON, default=dict)
    stale_node_ids: Mapped[list] = mapped_column(JSON, default=list)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="scene_instances")


class SceneAnalysisSnapshotRecord(Base):
    __tablename__ = "scene_analysis_snapshots"
    __table_args__ = (
        UniqueConstraint("scene_instance_id", "snapshot_number", name="uq_scene_analysis_snapshot"),
        UniqueConstraint(
            "scene_instance_id",
            "content_hash",
            name="uq_scene_analysis_instance_content_hash",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    scene_instance_id: Mapped[int] = mapped_column(
        ForeignKey("scene_instances.id", ondelete="CASCADE"), index=True
    )
    snapshot_number: Mapped[int] = mapped_column(Integer)
    snapshot_schema_version: Mapped[str] = mapped_column(String(20), default="4.0")
    standard_profile: Mapped[str] = mapped_column(String(40), default="CN-2026.7")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    report_number: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
