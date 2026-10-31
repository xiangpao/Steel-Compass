from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .core.scene_schemas import (
    SceneLoadItem,
    SceneNodeCalculation,
    SceneRevisionResult,
)
from .core.schemas import CalculationMode, CalculationRequest, CalculationResult
from .core.site_profile import ProjectSiteProfile
from .core.design_profiles import (
    CustomSectionCreate,
    CustomSectionDefinition,
    ConnectionInstanceAssignment,
    ConnectionTypeDefinition,
    CalculationTracePackage,
    ConnectionCheckPackage,
    DesignCandidateSet,
    FoundationCheckPackage,
    MemberCheckPackage,
    BucklingAnalysisPackage,
    SavedSceneAnalysisSnapshot,
    ProjectGeotechnicalProfile,
    RoofLoadSelectionProfile,
    SceneGeometryProfile,
    SceneStructuralProfile,
    StructuralAnalysisPackage,
)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
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
    site_profile: ProjectSiteProfile | None = None
    geotechnical_profile: ProjectGeotechnicalProfile | None = None


class ProjectView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    site_profile: ProjectSiteProfile | None = None
    geotechnical_profile: ProjectGeotechnicalProfile | None = None
    created_at: datetime
    updated_at: datetime
    version_count: int = 0


class ProjectCustomSections(BaseModel):
    items: list[CustomSectionDefinition] = Field(default_factory=list, max_length=100)


class CustomSectionCreateRequest(CustomSectionCreate):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=100)


class ModelValidationIssue(BaseModel):
    code: str
    severity: Literal["warning", "error"]
    message: str
    object_kind: Literal["model", "node", "member", "support", "foundation", "roof_surface", "connection"]
    object_id: str | None = None
    location: tuple[float, float, float] | None = None


class SceneGeometryValidation(BaseModel):
    valid: bool
    node_count: int
    member_count: int
    support_count: int
    roof_surface_count: int
    connected: bool
    warnings: list[str] = Field(default_factory=list)
    issues: list[ModelValidationIssue] = Field(default_factory=list)


class SceneConnectionsView(BaseModel):
    types: list[ConnectionTypeDefinition] = Field(default_factory=list, max_length=80)
    instances: list[ConnectionInstanceAssignment] = Field(default_factory=list, max_length=800)


class SceneAnalyzeRequest(BaseModel):
    stage: Literal["scheme_estimate", "project_check"] = "scheme_estimate"
    load_cases: list[SceneLoadItem] = Field(default_factory=list, max_length=100)
    roof_load_selection: RoofLoadSelectionProfile | None = None


class SceneAnalysisPreviewView(BaseModel):
    ready: bool
    missing_inputs: list[str] = Field(default_factory=list)
    load_cases: list[dict[str, object]] = Field(default_factory=list)
    combinations: list[dict[str, object]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class SceneAnalysisView(BaseModel):
    workflow_status: Literal["ready", "incomplete", "failed"]
    model_validation: SceneGeometryValidation
    structural_analysis: StructuralAnalysisPackage
    member_checks: MemberCheckPackage | None = None
    buckling_analysis: BucklingAnalysisPackage | None = None
    connection_checks: ConnectionCheckPackage
    foundation_checks: FoundationCheckPackage
    trace: CalculationTracePackage
    solver_result: dict[str, object] | None = None
    snapshot: SavedSceneAnalysisSnapshot | None = None
    snapshot_id: int | None = None


class SceneAnalysisSnapshotSummary(BaseModel):
    id: int
    project_id: int
    scene_instance_id: int
    snapshot_number: int
    snapshot_schema_version: str
    standard_profile: str
    content_hash: str
    report_number: str
    created_at: datetime


class SceneAnalysisSnapshotView(BaseModel):
    id: int
    project_id: int
    scene_instance_id: int
    snapshot_number: int
    snapshot_schema_version: str
    standard_profile: str
    content_hash: str
    report_number: str
    created_at: datetime
    snapshot: SavedSceneAnalysisSnapshot


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
    archived: bool | None = None
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
    archived: bool
    created_at: datetime
    updated_at: datetime


class SceneRevisionCreate(BaseModel):
    scene_instance_id: int
    node_calculations: list[SceneNodeCalculation] = Field(
        default_factory=list, max_length=50
    )
    load_cases: list[SceneLoadItem] = Field(default_factory=list, max_length=100)
    structural_profile: SceneStructuralProfile | None = None


class SceneRecommendationRequest(BaseModel):
    target_node_id: str = Field(min_length=1, max_length=80)
    vertical_kn: float = Field(gt=0, le=1_000_000)
    moment_kn_m: float = Field(default=0, ge=-1_000_000, le=1_000_000)
    max_plan_m: float = Field(default=6.0, ge=0.5, le=30)


class SceneRecommendationView(DesignCandidateSet):
    pass


class FoundationCandidatesRequest(BaseModel):
    foundation_instance_id: str = Field(min_length=1, max_length=80)
    max_plan_m: float = Field(default=6.0, ge=0.5, le=30)
    # Ignored since 2026-11-01: sizing uses the project geotechnical profile's
    # base_friction_coefficient. Kept so older clients are not rejected.
    base_friction_coefficient: float | None = Field(default=None, gt=0, le=1, deprecated=True)


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
