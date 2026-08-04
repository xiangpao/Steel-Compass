from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .core.scene_schemas import (
    SceneLoadItem,
    SceneNodeCalculation,
    SceneRevisionResult,
)
from .core.schemas import CalculationMode, CalculationRequest, CalculationResult


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=256)


class CreateUserRequest(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=3, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    temporary_password: str = Field(min_length=10, max_length=256)
    is_admin: bool = False


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    is_admin: bool
    must_change_password: bool


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


class ProjectView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    version_count: int = 0


class VersionCreate(BaseModel):
    calculation: CalculationRequest


class VersionView(BaseModel):
    id: int
    project_id: int
    version_number: int
    calculation_input: dict
    calculation_result: CalculationResult
    engine_version: str
    report_number: str
    created_at: datetime


class RevisionNodeCreate(BaseModel):
    node_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    calculation: CalculationRequest


class RevisionConnectionCreate(BaseModel):
    source_node_id: str
    target_node_id: str
    support: str = Field(default="base", pattern=r"^(base|left|right)$")


class RevisionCreate(BaseModel):
    calculations: list[RevisionNodeCreate] = Field(min_length=1, max_length=50)
    connections: list[RevisionConnectionCreate] = Field(default_factory=list, max_length=100)


class RevisionView(BaseModel):
    id: int
    project_id: int
    revision_number: int
    snapshot_schema_version: str
    snapshot: dict
    result_bundle: dict[str, CalculationResult]
    catalog_versions: dict[str, str]
    engine_version: str
    report_number: str
    created_at: datetime


class SceneInstanceCreate(BaseModel):
    family_id: str = Field(pattern=r"^[a-z0-9-]+$", max_length=80)
    variant_id: str = Field(pattern=r"^[a-z0-9-]+$", max_length=80)
    title: str = Field(min_length=1, max_length=120)
    mode: CalculationMode = CalculationMode.QUICK
    draft_state: dict = Field(default_factory=dict)


class SceneInstanceUpdate(BaseModel):
    variant_id: str | None = Field(
        default=None, pattern=r"^[a-z0-9-]+$", max_length=80
    )
    title: str | None = Field(default=None, min_length=1, max_length=120)
    mode: CalculationMode | None = None
    draft_state: dict | None = None
    changed_node_ids: list[str] = Field(default_factory=list, max_length=50)


class SceneInstanceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    family_id: str
    variant_id: str
    title: str
    mode: str
    template_version: str
    draft_state: dict
    stale_node_ids: list[str]
    created_at: datetime
    updated_at: datetime


class SceneRevisionCreate(BaseModel):
    scene_instance_id: int
    node_calculations: list[SceneNodeCalculation] = Field(
        default_factory=list, max_length=50
    )
    confirmed_input_nodes: list[str] = Field(default_factory=list, max_length=50)
    load_cases: list[SceneLoadItem] = Field(default_factory=list, max_length=100)


class SceneRevisionView(BaseModel):
    id: int
    project_id: int
    revision_number: int
    snapshot_schema_version: str
    scene_instance_id: int
    scene_result: SceneRevisionResult
    result_bundle: dict[str, CalculationResult]
    catalog_versions: dict[str, str]
    engine_version: str
    report_number: str
    created_at: datetime
