from __future__ import annotations

from datetime import datetime, timezone
from copy import deepcopy
from math import sqrt
from hashlib import sha256
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..api_schemas import (
    SceneInstanceCreate,
    SceneInstanceUpdate,
    SceneInstanceView,
    SceneGeometryValidation,
    ModelValidationIssue,
    SceneConnectionsView,
    SceneAnalyzeRequest,
    SceneAnalysisPreviewView,
    SceneAnalysisView,
    SceneAnalysisSnapshotView,
    SceneRevisionCreate,
    SceneRecommendationRequest,
    SceneRecommendationView,
    FoundationCandidatesRequest,
    SceneRevisionView,
)
from ..auth import require_ready_user
from ..core import ENGINE_VERSION
from ..core.calculation_library import calculation_library
from ..core.scene_catalog import (
    SCENE_CATALOG_VERSION,
    SCENE_FAMILIES,
    get_scene_family,
    get_scene_variant,
    instantiate_scene_graph,
)
from ..core.scene_graph import downstream_node_ids, execute_scene
from ..core.scene_graph import validate_scene_site_profile
from ..core.scene_schemas import (
    SCENE_SNAPSHOT_SCHEMA_VERSION,
    SceneFamily,
    SceneRevisionResult,
)
from ..core.schemas import require_current_request_schema
from ..core.site_profile import ProjectSiteProfile
from ..core.design_profiles import (
    CustomSectionDefinition,
    CalculationTracePackage,
    ConnectionCheckPackage,
    FoundationCheckPackage,
    MemberCheckPackage,
    BucklingAnalysisPackage,
    SavedSceneAnalysisSnapshot,
    MemberGroupSpecification,
    MemberSectionOverride,
    ProjectGeotechnicalProfile,
    SceneGeometryProfile,
    SceneStructuralProfile,
    StructuralAnalysisPackage,
    RoofLoadSelectionProfile,
    DesignCandidateSet,
    STEEL_SECTIONS,
    recommend_spread_foundation,
    recommend_spread_foundation_from_reaction,
)
from ..core.pergola_loads import build_pergola_load_package
from ..core.pergola_analysis import analyze_pergola_package
from ..core.scene_foundation import calculate_scene_foundations
from ..core.scene_column_base import calculate_scene_column_bases
from ..core.scene_pedestal import calculate_scene_pedestals
from ..core.scene_steel_connection import calculate_scene_steel_connections
from ..core.geometry_topology import find_member_topology_conflicts, validate_plan_boundary
from ..database import get_db
from ..models import Project, ProjectRevision, SceneAnalysisSnapshotRecord, SceneInstance, User
from ..report import build_scene_analysis_snapshot_pdf


router = APIRouter(tags=["scene-system"])


def _owned_project(db: Session, project_id: int, user_id: int) -> Project:
    project = db.scalar(
        select(Project).where(Project.id == project_id, Project.owner_id == user_id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def _owned_scene_instance(
    db: Session, project_id: int, scene_instance_id: int, user_id: int
) -> SceneInstance:
    _owned_project(db, project_id, user_id)
    instance = db.scalar(
        select(SceneInstance).where(
            SceneInstance.id == scene_instance_id,
            SceneInstance.project_id == project_id,
        )
    )
    if instance is None:
        raise HTTPException(status_code=404, detail="场景实例不存在")
    return instance


def _family_or_404(family_id: str) -> SceneFamily:
    family = get_scene_family(family_id)
    if family is None:
        raise HTTPException(status_code=404, detail="场景族不存在")
    return family


def _validate_variant(family: SceneFamily, variant_id: str) -> None:
    variant = get_scene_variant(family, variant_id)
    if variant is None:
        raise HTTPException(status_code=422, detail="场景变体不存在")
    if family.availability != "public" or variant.availability != "public":
        raise HTTPException(status_code=409, detail="该场景仍在开发中")


def _instance_view(instance: SceneInstance) -> SceneInstanceView:
    return SceneInstanceView.model_validate(instance)


def _scene_revision_view(revision: ProjectRevision) -> SceneRevisionView:
    scene_context = revision.snapshot.get("scene_context", {})
    return SceneRevisionView(
        id=revision.id,
        project_id=revision.project_id,
        revision_number=revision.revision_number,
        snapshot_schema_version=revision.snapshot_schema_version,
        scene_instance_id=scene_context["scene_instance_id"],
        scene_result=SceneRevisionResult.model_validate(
            revision.snapshot["scene_result"]
        ),
        result_bundle=revision.result_bundle,
        catalog_versions=revision.catalog_versions,
        engine_version=revision.engine_version,
        report_number=revision.report_number,
        created_at=revision.created_at,
    )


@router.get("/scenario-families", response_model=list[SceneFamily])
def list_scene_families(
    _: User = Depends(require_ready_user),
) -> list[SceneFamily]:
    return SCENE_FAMILIES


@router.get("/scenario-families/{family_id}", response_model=SceneFamily)
def get_scene_family_detail(
    family_id: str,
    _: User = Depends(require_ready_user),
) -> SceneFamily:
    return _family_or_404(family_id)


@router.get("/calculation-library")
def get_calculation_library(
    task: str = Query(default="", max_length=80),
    material: str = Query(default="", max_length=40),
    query: str = Query(default="", max_length=80),
    _: User = Depends(require_ready_user),
) -> dict:
    return calculation_library(task=task, material=material, query=query)


@router.get(
    "/projects/{project_id}/scene-instances",
    response_model=list[SceneInstanceView],
)
def list_scene_instances(
    project_id: int,
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> list[SceneInstanceView]:
    _owned_project(db, project_id, user.id)
    instances = db.scalars(
        select(SceneInstance)
        .where(
            SceneInstance.project_id == project_id,
            *([] if include_archived else [SceneInstance.archived.is_(False)]),
        )
        .order_by(SceneInstance.updated_at.desc())
    ).all()
    return [_instance_view(item) for item in instances]


@router.post(
    "/projects/{project_id}/scene-instances",
    response_model=SceneInstanceView,
    status_code=status.HTTP_201_CREATED,
)
def create_scene_instance(
    project_id: int,
    payload: SceneInstanceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> SceneInstanceView:
    project = _owned_project(db, project_id, user.id)
    if payload.mode.value != "quick":
        raise HTTPException(status_code=422, detail="新建场景统一采用方案筛查模式")
    family = _family_or_404(payload.family_id)
    _validate_variant(family, payload.variant_id)
    instance = SceneInstance(
        project_id=project.id,
        family_id=family.id,
        variant_id=payload.variant_id,
        title=payload.title,
        mode=payload.mode.value,
        template_version=SCENE_CATALOG_VERSION,
        draft_state=payload.draft_state,
        stale_node_ids=[],
    )
    project.updated_at = datetime.now(timezone.utc)
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return _instance_view(instance)


@router.patch(
    "/projects/{project_id}/scene-instances/{scene_instance_id}",
    response_model=SceneInstanceView,
)
def update_scene_instance(
    project_id: int,
    scene_instance_id: int,
    payload: SceneInstanceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> SceneInstanceView:
    instance = _owned_scene_instance(
        db, project_id, scene_instance_id, user.id
    )
    family = _family_or_404(instance.family_id)
    if payload.variant_id is not None:
        old_graph = instantiate_scene_graph(family, instance.variant_id)
        _validate_variant(family, payload.variant_id)
        if payload.variant_id != instance.variant_id:
            instance.variant_id = payload.variant_id
            new_graph = instantiate_scene_graph(family, payload.variant_id)
            instance.stale_node_ids = [
                node.id
                for node in [*old_graph.nodes, *new_graph.nodes]
                if node.applicability != "not_applicable"
            ]
    if payload.title is not None:
        instance.title = payload.title
    if payload.mode is not None:
        if payload.mode.value != "quick":
            raise HTTPException(status_code=422, detail="重新计算统一采用方案筛查模式")
        instance.mode = "quick"
    if payload.draft_state is not None:
        instance.draft_state = payload.draft_state
    if payload.archived is not None:
        instance.archived = payload.archived
    if payload.changed_node_ids:
        has_saved_result = any(
            item.snapshot.get("scene_context", {}).get("scene_instance_id")
            == instance.id
            for item in db.scalars(
                select(ProjectRevision).where(
                    ProjectRevision.project_id == project_id
                )
            ).all()
        )
        if has_saved_result:
            instance.stale_node_ids = list(
                dict.fromkeys(
                    [
                        *instance.stale_node_ids,
                        *downstream_node_ids(
                            family,
                            payload.changed_node_ids,
                            instance.variant_id,
                        ),
                    ]
                )
            )
    instance.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(instance)
    return _instance_view(instance)


@router.get(
    "/projects/{project_id}/scene-instances/{scene_instance_id}/geometry",
    response_model=SceneGeometryProfile | None,
)
def get_scene_geometry(
    project_id: int,
    scene_instance_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> SceneGeometryProfile | None:
    instance = _owned_scene_instance(db, project_id, scene_instance_id, user.id)
    value = (instance.draft_state or {}).get("geometry_profile")
    return SceneGeometryProfile.model_validate(value) if value else None


@router.put(
    "/projects/{project_id}/scene-instances/{scene_instance_id}/geometry",
    response_model=SceneGeometryProfile,
)
def update_scene_geometry(
    project_id: int,
    scene_instance_id: int,
    payload: SceneGeometryProfile,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> SceneGeometryProfile:
    instance = _owned_scene_instance(db, project_id, scene_instance_id, user.id)
    instance.draft_state = {
        **(instance.draft_state or {}),
        "geometry_profile": payload.model_dump(mode="json"),
        "last_analysis_package": None,
        "last_analysis_snapshot": None,
        "last_analysis_snapshot_id": None,
        "foundation_candidate_sets": {},
    }
    family = _family_or_404(instance.family_id)
    graph = instantiate_scene_graph(family, instance.variant_id)
    instance.stale_node_ids = [
        node.id for node in graph.nodes if node.applicability != "not_applicable"
    ]
    instance.updated_at = datetime.now(timezone.utc)
    db.commit()
    return payload


@router.get(
    "/projects/{project_id}/scene-instances/{scene_instance_id}/connections",
    response_model=SceneConnectionsView,
)
def get_scene_connections(
    project_id: int,
    scene_instance_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> SceneConnectionsView:
    geometry = get_scene_geometry(project_id, scene_instance_id, db, user)
    if geometry is None:
        return SceneConnectionsView()
    return SceneConnectionsView(types=geometry.connection_types, instances=geometry.connection_instances)


@router.put(
    "/projects/{project_id}/scene-instances/{scene_instance_id}/connections",
    response_model=SceneConnectionsView,
)
def update_scene_connections(
    project_id: int,
    scene_instance_id: int,
    payload: SceneConnectionsView,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> SceneConnectionsView:
    instance = _owned_scene_instance(db, project_id, scene_instance_id, user.id)
    raw_geometry = (instance.draft_state or {}).get("geometry_profile")
    if raw_geometry is None:
        raise HTTPException(status_code=422, detail="请先保存 Geometry 2.3 模型")
    geometry = SceneGeometryProfile.model_validate(raw_geometry)
    if geometry.profile_version != "2.3":
        raise HTTPException(status_code=422, detail="连接接口只允许修改 Geometry 2.3；旧模型请另存为新版")
    updated = geometry.model_copy(update={"connection_types": payload.types, "connection_instances": payload.instances})
    validated = SceneGeometryProfile.model_validate(updated.model_dump(mode="json"))
    instance.draft_state = {
        **(instance.draft_state or {}),
        "geometry_profile": validated.model_dump(mode="json"),
        "last_analysis_package": None,
        "last_analysis_snapshot": None,
        "last_analysis_snapshot_id": None,
        "foundation_candidate_sets": {},
    }
    instance.updated_at = datetime.now(timezone.utc)
    db.commit()
    return payload


@router.post(
    "/projects/{project_id}/scene-instances/{scene_instance_id}/validate-model",
    response_model=SceneGeometryValidation,
)
def validate_scene_geometry(
    project_id: int,
    scene_instance_id: int,
    payload: SceneGeometryProfile,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> SceneGeometryValidation:
    _owned_scene_instance(db, project_id, scene_instance_id, user.id)
    adjacency: dict[str, set[str]] = {node.id: set() for node in payload.nodes}
    for member in payload.members:
        adjacency[member.start_node_id].add(member.end_node_id)
        adjacency[member.end_node_id].add(member.start_node_id)
    pending = [payload.nodes[0].id]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        pending.extend(adjacency[current] - visited)
    connected = len(visited) == len(payload.nodes)
    warnings: list[str] = []
    errors: list[str] = []
    issues: list[ModelValidationIssue] = []
    if not connected:
        message = "模型包含互不连接的构件组，请检查缺柱、悬挑或局部偏移节点。"
        warnings.append(message)
        issues.append(ModelValidationIssue(code="disconnected_model", severity="error", message=message, object_kind="model"))
    if not payload.roof_surfaces:
        message = "尚未定义屋面分区；不会生成屋面面荷载。"
        warnings.append(message)
        issues.append(ModelValidationIssue(code="missing_roof_surface", severity="warning", message=message, object_kind="model"))
    coordinates = [(node.x_m, node.y_m, node.z_m) for node in payload.nodes]
    if len(coordinates) != len(set(coordinates)):
        errors.append("模型包含坐标完全相同的重复节点。")
    node_by_id = {node.id: node for node in payload.nodes}
    for member in payload.members:
        start, end = node_by_id[member.start_node_id], node_by_id[member.end_node_id]
        if (start.x_m, start.y_m, start.z_m) == (end.x_m, end.y_m, end.z_m):
            message = f"杆件 {member.id} 为零长度杆件。"
            errors.append(message)
            issues.append(ModelValidationIssue(code="zero_length_member", severity="error", message=message, object_kind="member", object_id=member.id, location=(start.x_m, start.y_m, start.z_m)))
    for conflict in find_member_topology_conflicts(payload.nodes, payload.members):
        first_id, second_id = conflict["member_ids"]
        if conflict["code"] == "overlapping_members":
            message = f"杆件 {first_id} 与 {second_id} 完全重叠。"
        else:
            message = f"杆件 {first_id} 与 {second_id} 相交但没有共同节点，请在交点拆分并连接。"
        errors.append(message)
        issues.append(ModelValidationIssue(
            code=str(conflict["code"]),
            severity="error",
            message=message,
            object_kind="member",
            object_id=str(first_id),
            location=conflict["location"],
        ))
    connected_node_ids = {node_id for member in payload.members for node_id in (member.start_node_id, member.end_node_id)}
    for node in payload.nodes:
        if node.id not in connected_node_ids:
            message = f"节点 {node.id} 未连接任何杆件。"
            errors.append(message)
            issues.append(ModelValidationIssue(code="isolated_node", severity="error", message=message, object_kind="node", object_id=node.id, location=(node.x_m, node.y_m, node.z_m)))
    support_count = (
        len(payload.supports)
        if payload.profile_version in {"2.0", "2.1", "2.2", "2.3"}
        else sum(node.support != "none" for node in payload.nodes)
    )
    if support_count == 0:
        message = "模型没有支承；移除柱后请确认剩余结构具有稳定传力路径。"
        errors.append(message)
        issues.append(ModelValidationIssue(code="missing_support", severity="error", message=message, object_kind="model"))
    if payload.profile_version in {"2.2", "2.3"}:
        foundation_support_ids = {item.support_id for item in payload.foundation_instances}
        for support in payload.supports:
            if support.foundation_id and support.id not in foundation_support_ids:
                node = node_by_id[support.node_id]
                message = f"支承 {support.id} 声明了基础但没有绑定基础实例。"
                errors.append(message)
                issues.append(ModelValidationIssue(code="unbound_foundation", severity="error", message=message, object_kind="support", object_id=support.id, location=(node.x_m, node.y_m, node.z_m)))
        for connection in payload.connection_instances:
            if connection.status != "defined":
                node = node_by_id[connection.node_id]
                message = connection.message or f"连接 {connection.mark} 尚未完整定义。"
                errors.append(message)
                issues.append(ModelValidationIssue(code="incomplete_connection", severity="error", message=message, object_kind="connection", object_id=connection.id, location=(node.x_m, node.y_m, node.z_m)))
        connections_by_node: dict[str, list] = {}
        for item in payload.connection_instances:
            if item.status == "defined":
                connections_by_node.setdefault(item.node_id, []).append(item)
        members_by_node: dict[str, list] = {node.id: [] for node in payload.nodes}
        for member in payload.members:
            members_by_node[member.start_node_id].append(member)
            members_by_node[member.end_node_id].append(member)
        for node_id, members in members_by_node.items():
            roles = {item.role for item in members}
            groups = {item.group_id for item in members}
            requires_connection = "column" in roles and len(roles) > 1 or len(groups) > 1
            assigned_member_ids = {
                member_id
                for connection in connections_by_node.get(node_id, [])
                for member_id in connection.member_ids
            }
            missing_member_ids = sorted(
                item.id for item in members if item.id not in assigned_member_ids
            )
            if requires_connection and missing_member_ids:
                node = node_by_id[node_id]
                message = f"节点 {node_id} 汇交不同构件类型，但尚未分配连接实例。"
                errors.append(message)
                issues.append(ModelValidationIssue(code="missing_connection_assignment", severity="error", message=message, object_kind="connection", object_id=node_id, location=(node.x_m, node.y_m, node.z_m)))
        column_base_members = {item.column_member_id for item in payload.column_bases}
        for member in payload.members:
            if member.role != "column" or member.id in column_base_members:
                continue
            node = node_by_id[member.start_node_id]
            message = f"柱 {member.id} 尚未绑定柱脚总成。"
            errors.append(message)
            issues.append(ModelValidationIssue(code="missing_column_base", severity="error", message=message, object_kind="member", object_id=member.id, location=(node.x_m, node.y_m, node.z_m)))
    if payload.plan_boundary is not None:
        try:
            validate_plan_boundary(payload.plan_boundary)
        except ValueError as exc:
            errors.append(str(exc))
    warnings.extend(errors)
    return SceneGeometryValidation(
        valid=connected and not errors,
        node_count=len(payload.nodes),
        member_count=len(payload.members),
        support_count=support_count,
        roof_surface_count=len(payload.roof_surfaces),
        connected=connected,
        warnings=warnings,
        issues=issues,
    )


def _structural_profile_from_saved_geometry(
    geometry: SceneGeometryProfile,
    stage: str,
    custom_sections: list[CustomSectionDefinition],
) -> SceneStructuralProfile:
    catalog_ids = {item.id for item in STEEL_SECTIONS}
    custom_ids = {item.id for item in custom_sections}
    type_by_id = {item.id: item for item in geometry.member_types}
    member_by_id = {item.id: item for item in geometry.members}
    node_by_id = {item.id: item for item in geometry.nodes}
    groups: list[MemberGroupSpecification] = []
    for member_type in geometry.member_types:
        group_members = [item for item in geometry.members if item.group_id == member_type.id]
        if not group_members:
            continue
        lengths = []
        for member in group_members:
            start, end = node_by_id[member.start_node_id], node_by_id[member.end_node_id]
            lengths.append(sqrt((start.x_m - end.x_m) ** 2 + (start.y_m - end.y_m) ** 2 + (start.z_m - end.z_m) ** 2))
        section_id = member_type.section_id
        if section_id not in catalog_ids and section_id not in custom_ids:
            raise HTTPException(status_code=422, detail={
                "code": "unsaved_member_section",
                "message": f"构件类型 {member_type.title} 的截面 {section_id} 不在标准目录或项目截面库中。",
                "object_id": member_type.id,
            })
        groups.append(MemberGroupSpecification(
            group_id=member_type.id,
            role=member_type.role,
            material_grade=member_type.material_grade,
            section_catalog_id=section_id if section_id in catalog_ids else None,
            custom_section_id=section_id if section_id in custom_ids else None,
            strong_axis_unbraced_length_m=max(lengths),
            weak_axis_unbraced_length_m=max(lengths),
        ))
    overrides: list[MemberSectionOverride] = []
    for assignment in geometry.member_instances:
        if not assignment.override_section_id:
            continue
        if assignment.override_section_id not in catalog_ids and assignment.override_section_id not in custom_ids:
            raise HTTPException(status_code=422, detail={
                "code": "unsaved_member_override_section",
                "message": f"构件 {assignment.mark} 的覆盖截面尚未保存到项目截面库。",
                "object_id": assignment.member_id,
            })
        member = member_by_id[assignment.member_id]
        member_type = type_by_id[assignment.member_type_id]
        overrides.append(MemberSectionOverride(
            member_id=member.id,
            material_grade=member_type.material_grade,
            section_id=assignment.override_section_id,
            orientation=member_type.orientation,
            source="user_locked",
        ))
    return SceneStructuralProfile(
        profile_version="3.0",
        stage=stage,
        member_groups=groups,
        member_overrides=overrides,
        geometry=geometry,
        catalog_versions={"geometry": geometry.profile_version, "standards": "CN-2026.7"},
    )


def _governing_support_reactions(solver_result: dict[str, object]) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    governing: dict[str, dict[str, float]] = {}
    sources: dict[str, str] = {}
    results = solver_result.get("combination_results") or solver_result.get("case_results") or {}
    for result_id, result in results.items():
        for node_id, reaction in result.get("support_reactions", {}).items():
            current = governing.setdefault(node_id, {})
            current.setdefault("_cases", []).append({
                "combination_id": str(result_id),
                "limit_state": "SLS" if str(result_id).startswith("SLS-") else "ULS",
                "reaction": {key: float(value) for key, value in reaction.items()},
            })
            for key, raw_value in reaction.items():
                value = float(raw_value)
                if key not in current or abs(value) > abs(current[key]):
                    current[key] = value
                    sources[f"{node_id}:{key}"] = str(result_id)
    return governing, sources


def _governing_member_forces(solver_result: dict[str, object]) -> dict[str, dict[str, object]]:
    governing: dict[str, dict[str, object]] = {}
    results = solver_result.get("combination_results") or solver_result.get("case_results") or {}
    for result_id, result in results.items():
        for member_id, forces in result.get("member_end_forces", {}).items():
            current = governing.setdefault(member_id, {
                "start_node_id": forces["start_node_id"],
                "end_node_id": forces["end_node_id"],
                "start": {},
                "end": {},
                "cases": [],
                "component_sources": {},
                "force_basis": "member-local-axis",
                "verification_status": "unverified",
            })
            current["cases"].append({
                "combination_id": str(result_id),
                "limit_state": "SLS" if str(result_id).startswith("SLS-") else "ULS",
                "start": {key: float(value) for key, value in forces["start"].items()},
                "end": {key: float(value) for key, value in forces["end"].items()},
            })
            for end in ("start", "end"):
                for key, raw_value in forces[end].items():
                    value = float(raw_value)
                    existing = current[end].get(key)
                    if existing is None or abs(value) > abs(float(existing)):
                        current[end][key] = value
                        current["component_sources"][f"{end}:{key}"] = str(result_id)
    return governing


def _canonical_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _analysis_snapshot_view(record: SceneAnalysisSnapshotRecord) -> SceneAnalysisSnapshotView:
    return SceneAnalysisSnapshotView(
        id=record.id,
        project_id=record.project_id,
        scene_instance_id=record.scene_instance_id,
        snapshot_number=record.snapshot_number,
        snapshot_schema_version=record.snapshot_schema_version,
        standard_profile=record.standard_profile,
        content_hash=record.content_hash,
        report_number=record.report_number,
        created_at=record.created_at,
        snapshot=SavedSceneAnalysisSnapshot.model_validate(record.snapshot),
    )


def _roof_selection_or_422(payload: SceneAnalyzeRequest) -> RoofLoadSelectionProfile:
    if payload.roof_load_selection is None:
        raise HTTPException(status_code=422, detail={
            "code": "missing_roof_load_selection",
            "message": "请先选择屋面构造和检修/使用类别。",
        })
    return payload.roof_load_selection


@router.post(
    "/projects/{project_id}/scene-instances/{scene_instance_id}/analysis-preview",
    response_model=SceneAnalysisPreviewView,
)
def preview_saved_scene_analysis(
    project_id: int,
    scene_instance_id: int,
    payload: SceneAnalyzeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> SceneAnalysisPreviewView:
    project = _owned_project(db, project_id, user.id)
    instance = _owned_scene_instance(db, project_id, scene_instance_id, user.id)
    raw_geometry = (instance.draft_state or {}).get("geometry_profile")
    if raw_geometry is None:
        return SceneAnalysisPreviewView(ready=False, missing_inputs=["Geometry 2.3模型"])
    geometry = SceneGeometryProfile.model_validate(raw_geometry)
    site_profile = ProjectSiteProfile.model_validate(project.site_profile) if project.site_profile else None
    package = build_pergola_load_package(geometry, site_profile, payload.roof_load_selection)
    return SceneAnalysisPreviewView(
        ready=not package.missing_inputs,
        missing_inputs=list(package.missing_inputs),
        load_cases=[item.model_dump(mode="json") for item in package.cases],
        combinations=[item.model_dump(mode="json") for item in package.combinations],
        assumptions=list(package.assumptions),
    )


@router.post(
    "/projects/{project_id}/scene-instances/{scene_instance_id}/analyze",
    response_model=SceneAnalysisView,
)
def analyze_saved_scene(
    project_id: int,
    scene_instance_id: int,
    payload: SceneAnalyzeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> SceneAnalysisView:
    project = _owned_project(db, project_id, user.id)
    instance = _owned_scene_instance(db, project_id, scene_instance_id, user.id)
    raw_geometry = (instance.draft_state or {}).get("geometry_profile")
    if raw_geometry is None:
        raise HTTPException(status_code=422, detail={"code": "missing_saved_geometry", "message": "请先保存 Geometry 2.3 模型。"})
    geometry = SceneGeometryProfile.model_validate(raw_geometry)
    if geometry.profile_version != "2.3":
        raise HTTPException(status_code=422, detail={"code": "readonly_legacy_geometry", "message": "旧模型只读；请另存为 Geometry 2.3 后计算。"})
    validation = validate_scene_geometry(project_id, scene_instance_id, geometry, db, user)
    blocking = [item for item in validation.issues if item.severity == "error"]
    if blocking:
        raise HTTPException(status_code=422, detail={
            "code": "invalid_saved_model",
            "message": "模型校验未通过，不能开始分析。",
            "issues": [item.model_dump(mode="json") for item in blocking],
        })
    family = _family_or_404(instance.family_id)
    variant = get_scene_variant(family, instance.variant_id)
    if variant is None:
        raise HTTPException(status_code=422, detail="场景变体不存在")
    site_profile = ProjectSiteProfile.model_validate(project.site_profile) if project.site_profile else None
    validate_scene_site_profile(variant, site_profile)
    roof_selection = _roof_selection_or_422(payload)
    load_package = build_pergola_load_package(geometry, site_profile, roof_selection)
    if load_package.missing_inputs:
        raise HTTPException(status_code=422, detail={
            "code": "incomplete_analysis_inputs",
            "message": "项目条件或屋面荷载条件未完成。",
            "missing_inputs": list(load_package.missing_inputs),
        })
    custom_sections = [CustomSectionDefinition.model_validate(item) for item in (project.custom_sections or [])]
    structural_profile = _structural_profile_from_saved_geometry(geometry, payload.stage, custom_sections)
    solver_result = analyze_pergola_package(structural_profile, load_package, custom_sections)
    governing_reactions, reaction_sources = _governing_support_reactions(solver_result)
    reactions = [
        {"support_node_id": node_id, **{key: value for key, value in values.items() if key != "_cases"}, "component_sources": {
            key: reaction_sources.get(f"{node_id}:{key}") for key in values if key != "_cases"
        }}
        for node_id, values in governing_reactions.items()
    ]
    balance = [
        {
            "case": result_id,
            "residual_kn": result["load_balance_kn"],
            "balanced": max(abs(value) for value in result["load_balance_kn"]) < 1e-6,
        }
        for result_id, result in (solver_result.get("combination_results") or {}).items()
    ]
    member_check_data = solver_result["member_checks"]
    structural = StructuralAnalysisPackage(
        status=("failed" if member_check_data["status"] == "failed" else "complete"),
        load_cases=[item.model_dump(mode="json") for item in load_package.cases],
        combinations=[item.model_dump(mode="json") for item in load_package.combinations],
        reactions=reactions,
        member_checks=member_check_data["items"],
        balance_checks=balance,
        missing_inputs=[],
    )
    member_checks = MemberCheckPackage.model_validate(member_check_data)
    buckling_values = sorted(
        value
        for result in (solver_result.get("combination_results") or {}).values()
        for value in result.get("elastic_buckling_factors", [])
        if value > 0
    )
    buckling_analysis = BucklingAnalysisPackage(
        status=("failed" if buckling_values and buckling_values[0] <= 1.0 else "complete" if buckling_values else "incomplete"),
        factors=buckling_values[:10],
        controlling_mode=1 if buckling_values else None,
        missing_inputs=[] if buckling_values else ["当前组合没有形成可识别的受压几何刚度模态"],
    )
    if buckling_analysis.status == "failed":
        structural.status = "failed"
    column_base_items = calculate_scene_column_bases(
        geometry,
        governing_reactions,
        custom_sections,
        project_name=project.name,
    )
    steel_connection_items = calculate_scene_steel_connections(
        geometry,
        _governing_member_forces(solver_result),
        custom_sections,
    )
    calculated_connections_by_id = {
        item.get("connection_id"): item
        for item in [*column_base_items, *steel_connection_items]
        if item.get("connection_id")
    }
    connection_items = []
    for connection in geometry.connection_instances:
        base_item = calculated_connections_by_id.get(connection.id)
        connection_items.append(
            {**base_item, "mark": connection.mark}
            if base_item is not None
            else {
                "connection_id": connection.id,
                "mark": connection.mark,
                "status": "not_calculated",
                "verification_status": "unverified",
                "issue_code": "connection_family_not_implemented",
            }
        )
    linked_connection_ids = set(calculated_connections_by_id)
    connection_items.extend(
        item
        for item in [*column_base_items, *steel_connection_items]
        if item.get("connection_id") not in linked_connection_ids
    )
    connection_checks = ConnectionCheckPackage(
        status=(
            "failed"
            if any(item.get("status") == "failed" for item in connection_items)
            else "incomplete"
            if any(item.get("status") not in {"complete", "failed"} for item in connection_items)
            else "complete"
        ),
        items=connection_items,
        unsupported_connection_ids=[
            str(item["connection_id"])
            for item in connection_items
            if item.get("issue_code") == "connection_family_not_implemented"
        ],
    )
    geotechnical = (
        ProjectGeotechnicalProfile.model_validate(project.geotechnical_profile)
        if project.geotechnical_profile
        else None
    )
    foundation_items = calculate_scene_foundations(
        geometry,
        governing_reactions,
        geotechnical,
        project_name=project.name,
    )
    pedestal_items = calculate_scene_pedestals(
        geometry,
        governing_reactions,
    )
    pedestal_by_foundation = {
        item["foundation_id"]: item for item in pedestal_items
    }
    for foundation_item in foundation_items:
        pedestal_item = pedestal_by_foundation.get(foundation_item["foundation_id"])
        if pedestal_item is None:
            continue
        foundation_item["pedestal_check"] = pedestal_item
        if pedestal_item["status"] == "failed":
            foundation_item["status"] = "failed"
    foundation_checks = FoundationCheckPackage(
        status=(
            "failed"
            if any(item["status"] == "failed" for item in foundation_items)
            else "incomplete"
        ),
        items=foundation_items,
        reaction_source_ids=[item["support_node_id"] for item in reactions],
    )
    trace = CalculationTracePackage(
        input_sources=[{"kind": "saved_geometry", "version": geometry.profile_version}, {"kind": "project_site_profile", "catalog_versions": site_profile.catalog_versions if site_profile else {}}],
        formulas=[
            {"topic": "load_combinations", "source": "GB 50009-2012；GB 55002-2021；GB/T 50011-2010（2024年版）"},
            {"topic": "steel_members", "source": "GB 55006-2021；GB 50017-2017"},
            {"topic": "foundation", "source": "GB 55003-2021；GB 50007-2011；22G101-3"},
        ],
        unsupported_capabilities=[
            "焊接矩形管节点屈服线/刚度精细模型",
            "基础沉降计算需要勘察变形参数",
        ],
    )
    statuses = [structural.status, connection_checks.status, foundation_checks.status]
    workflow_status = "failed" if "failed" in statuses else "incomplete" if "incomplete" in statuses or buckling_analysis.status == "incomplete" else "ready"
    analysis_payload = {
        "workflow_status": workflow_status,
        "model_validation": validation.model_dump(mode="json"),
        "structural_analysis": structural.model_dump(mode="json"),
        "member_checks": member_checks.model_dump(mode="json"),
        "buckling_analysis": buckling_analysis.model_dump(mode="json"),
        "connection_checks": connection_checks.model_dump(mode="json"),
        "foundation_checks": foundation_checks.model_dump(mode="json"),
        "trace": trace.model_dump(mode="json"),
        "solver_result": solver_result,
    }
    snapshot_basis = {
        "geometry": geometry.model_dump(mode="json"),
        "site_profile": site_profile.model_dump(mode="json") if site_profile else {},
        "geotechnical_profile": geotechnical.model_dump(mode="json") if geotechnical else None,
        "roof_load_selection": roof_selection.model_dump(mode="json"),
        "load_cases": [item.model_dump(mode="json") for item in load_package.cases],
        "combinations": [item.model_dump(mode="json") for item in load_package.combinations],
        "analysis": analysis_payload,
    }
    snapshot = SavedSceneAnalysisSnapshot(
        geometry=geometry,
        site_profile=snapshot_basis["site_profile"],
        geotechnical_profile=snapshot_basis["geotechnical_profile"],
        roof_load_selection=roof_selection,
        load_cases=snapshot_basis["load_cases"],
        combinations=list(load_package.combinations),
        analysis=analysis_payload,
        created_at=datetime.now(timezone.utc).isoformat(),
        content_hash=_canonical_hash(snapshot_basis),
    )
    snapshot_record = db.scalar(
        select(SceneAnalysisSnapshotRecord).where(
            SceneAnalysisSnapshotRecord.scene_instance_id == scene_instance_id,
            SceneAnalysisSnapshotRecord.content_hash == snapshot.content_hash
        )
    )
    if snapshot_record is None:
        next_snapshot = (
            db.scalar(
                select(func.max(SceneAnalysisSnapshotRecord.snapshot_number)).where(
                    SceneAnalysisSnapshotRecord.scene_instance_id == scene_instance_id
                )
            )
            or 0
        ) + 1
        snapshot_record = SceneAnalysisSnapshotRecord(
            project_id=project_id,
            scene_instance_id=scene_instance_id,
            snapshot_number=next_snapshot,
            snapshot_schema_version="4.0",
            standard_profile="CN-2026.7",
            content_hash=snapshot.content_hash,
            snapshot=snapshot.model_dump(mode="json"),
            report_number=f"SC-{project_id:06d}-A{scene_instance_id:04d}-{next_snapshot:03d}",
        )
        db.add(snapshot_record)
        db.flush()
    package = SceneAnalysisView(
        workflow_status=workflow_status,
        model_validation=validation,
        structural_analysis=structural,
        member_checks=member_checks,
        buckling_analysis=buckling_analysis,
        connection_checks=connection_checks,
        foundation_checks=foundation_checks,
        trace=trace,
        solver_result=solver_result,
        snapshot=snapshot,
    )
    instance.draft_state = {
        **(instance.draft_state or {}),
        "last_analysis_package": package.model_dump(mode="json"),
        "last_analysis_snapshot": snapshot.model_dump(mode="json"),
        "last_analysis_snapshot_id": snapshot_record.id,
    }
    instance.updated_at = datetime.now(timezone.utc)
    db.commit()
    return package


@router.get(
    "/projects/{project_id}/scene-instances/{scene_instance_id}/analysis-snapshots",
    response_model=list[SceneAnalysisSnapshotView],
)
def list_scene_analysis_snapshots(
    project_id: int,
    scene_instance_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> list[SceneAnalysisSnapshotView]:
    _owned_scene_instance(db, project_id, scene_instance_id, user.id)
    records = db.scalars(
        select(SceneAnalysisSnapshotRecord)
        .where(
            SceneAnalysisSnapshotRecord.project_id == project_id,
            SceneAnalysisSnapshotRecord.scene_instance_id == scene_instance_id,
        )
        .order_by(SceneAnalysisSnapshotRecord.snapshot_number.desc())
    ).all()
    return [_analysis_snapshot_view(record) for record in records]


@router.get(
    "/projects/{project_id}/scene-instances/{scene_instance_id}/analysis-snapshots/{snapshot_id}",
    response_model=SceneAnalysisSnapshotView,
)
def get_scene_analysis_snapshot(
    project_id: int,
    scene_instance_id: int,
    snapshot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> SceneAnalysisSnapshotView:
    _owned_scene_instance(db, project_id, scene_instance_id, user.id)
    record = db.scalar(
        select(SceneAnalysisSnapshotRecord).where(
            SceneAnalysisSnapshotRecord.id == snapshot_id,
            SceneAnalysisSnapshotRecord.project_id == project_id,
            SceneAnalysisSnapshotRecord.scene_instance_id == scene_instance_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="分析快照不存在")
    return _analysis_snapshot_view(record)


@router.get(
    "/projects/{project_id}/scene-instances/{scene_instance_id}/analysis-snapshots/{snapshot_id}/report.pdf"
)
def download_scene_analysis_snapshot_report(
    project_id: int,
    scene_instance_id: int,
    snapshot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> Response:
    record = get_scene_analysis_snapshot(project_id, scene_instance_id, snapshot_id, db, user)
    pdf = build_scene_analysis_snapshot_pdf(record.snapshot.model_dump(mode="json"), record.report_number)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{record.report_number}.pdf"'},
    )


@router.post(
    "/projects/{project_id}/scene-instances/{scene_instance_id}/recommendations",
    response_model=SceneRecommendationView,
)
def recommend_scene_design(
    project_id: int,
    scene_instance_id: int,
    payload: SceneRecommendationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> SceneRecommendationView:
    project = _owned_project(db, project_id, user.id)
    instance = _owned_scene_instance(db, project_id, scene_instance_id, user.id)
    graph = instantiate_scene_graph(_family_or_404(instance.family_id), instance.variant_id)
    target = next((node for node in graph.nodes if node.id == payload.target_node_id), None)
    if target is None or target.role != "foundation":
        raise HTTPException(status_code=422, detail="推荐目标必须是当前场景的基础节点")
    if target.calculation_module != "spread_footing":
        raise HTTPException(status_code=422, detail="本版仅开放独立基础离散推荐；其他体系保留明确边界")
    if not project.geotechnical_profile:
        raise HTTPException(status_code=422, detail="请先保存项目地勘资料或区域参考土质档")
    geotechnical = ProjectGeotechnicalProfile.model_validate(project.geotechnical_profile)
    return SceneRecommendationView.model_validate(
        recommend_spread_foundation(
            node_id=target.id,
            vertical_kn=payload.vertical_kn,
            moment_kn_m=payload.moment_kn_m,
            bearing_capacity_kpa=geotechnical.bearing_capacity_kpa,
            max_plan_m=payload.max_plan_m,
        ).model_dump(mode="json")
    )


@router.post(
    "/projects/{project_id}/scene-instances/{scene_instance_id}/foundation-candidates",
    response_model=SceneRecommendationView,
)
def recommend_foundation_from_saved_analysis(
    project_id: int,
    scene_instance_id: int,
    payload: FoundationCandidatesRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> SceneRecommendationView:
    project = _owned_project(db, project_id, user.id)
    instance = _owned_scene_instance(db, project_id, scene_instance_id, user.id)
    raw_geometry = (instance.draft_state or {}).get("geometry_profile")
    snapshot_id = (instance.draft_state or {}).get("last_analysis_snapshot_id")
    if raw_geometry is None or snapshot_id is None:
        raise HTTPException(status_code=422, detail={
            "code": "missing_saved_analysis",
            "message": "请先保存 Geometry 2.2 并完成服务端分析；基础候选不接受手填柱脚反力。",
        })
    snapshot_record = db.scalar(
        select(SceneAnalysisSnapshotRecord).where(
            SceneAnalysisSnapshotRecord.id == int(snapshot_id),
            SceneAnalysisSnapshotRecord.project_id == project_id,
            SceneAnalysisSnapshotRecord.scene_instance_id == scene_instance_id,
        )
    )
    if snapshot_record is None:
        raise HTTPException(status_code=422, detail={
            "code": "missing_saved_analysis",
            "message": "分析快照不存在或不属于当前场景，请重新分析。",
        })
    geometry = SceneGeometryProfile.model_validate(raw_geometry)
    foundation = next((item for item in geometry.foundation_instances if item.id == payload.foundation_instance_id), None)
    if foundation is None:
        raise HTTPException(status_code=422, detail={"code": "unknown_foundation_instance", "object_id": payload.foundation_instance_id})
    foundation_type = next(item for item in geometry.foundation_types if item.id == foundation.foundation_type_id)
    support = next(item for item in geometry.supports if item.id == foundation.support_id)
    solver_result = snapshot_record.snapshot.get("analysis", {}).get("solver_result", {})
    reactions, _ = _governing_support_reactions(solver_result)
    reaction = reactions.get(support.node_id)
    if reaction is None:
        raise HTTPException(status_code=422, detail={
            "code": "missing_foundation_reaction",
            "message": f"基础 {foundation.mark} 对应支承节点 {support.node_id} 没有分析反力。",
            "object_id": foundation.id,
        })
    if not project.geotechnical_profile:
        raise HTTPException(status_code=422, detail={"code": "missing_geotechnical_profile", "message": "请先保存项目地勘资料或方案土质档。"})
    geotechnical = ProjectGeotechnicalProfile.model_validate(project.geotechnical_profile)
    reaction_cases = [item for item in reaction.get("_cases", []) if item.get("limit_state") == "ULS"]
    if not reaction_cases:
        reaction_cases = [{
            "combination_id": "ULS-LEGACY-ENVELOPE",
            "reaction": {key: value for key, value in reaction.items() if key != "_cases"},
        }]
    candidates: list[tuple[str, DesignCandidateSet]] = []
    for reaction_case in reaction_cases:
        candidates.append((
            str(reaction_case["combination_id"]),
            recommend_spread_foundation_from_reaction(
                foundation_instance_id=foundation.id,
                reaction={key: float(value) for key, value in reaction_case["reaction"].items()},
                bearing_capacity_kpa=geotechnical.bearing_capacity_kpa,
                initial_length_m=foundation_type.length_m,
                initial_width_m=foundation_type.width_m,
                initial_thickness_mm=foundation_type.thickness_mm,
                pedestal=foundation_type.pedestal,
                base_friction_coefficient=payload.base_friction_coefficient,
                max_plan_m=payload.max_plan_m,
            ),
        ))
    failed_candidates = [(case_id, item) for case_id, item in candidates if not item.converged]
    if failed_candidates:
        controlling_id, failed_candidate = failed_candidates[0]
        candidate = failed_candidate.model_copy(update={
            "failure_reason": f"组合 {controlling_id}：{failed_candidate.failure_reason}",
            "governing_check": f"全部ULS组合逐项试算；{controlling_id} 控制",
        })
    else:
        controlling_id, controlling_candidate = max(
            candidates,
            key=lambda item: (
                float(item[1].recommended.get("length_m", 0))
                * float(item[1].recommended.get("width_m", 0))
                * float(item[1].recommended.get("thickness_mm", 0))
                if item[1].recommended else 0
            ),
        )
        recommended = {**(controlling_candidate.recommended or {}), "controlling_combination_id": controlling_id}
        alternatives = [
            {**(item.recommended or {}), "combination_id": case_id}
            for case_id, item in candidates
            if case_id != controlling_id and item.recommended
        ][-2:]
        iterations = [
            {**iteration, "combination_id": case_id}
            for case_id, item in candidates
            for iteration in item.iterations
        ]
        candidate = controlling_candidate.model_copy(update={
            "recommended": recommended,
            "alternatives": alternatives,
            "iterations": iterations,
            "governing_check": f"全部ULS组合逐项试算；{controlling_id} 控制",
        })
    stored_candidates = dict((instance.draft_state or {}).get("foundation_candidate_sets", {}))
    stored_candidates[foundation.id] = candidate.model_dump(mode="json")
    instance.draft_state = {**(instance.draft_state or {}), "foundation_candidate_sets": stored_candidates}
    instance.updated_at = datetime.now(timezone.utc)
    db.commit()
    return SceneRecommendationView.model_validate(candidate.model_dump(mode="json"))


@router.post(
    "/projects/{project_id}/scene-instances/{scene_instance_id}/duplicate",
    response_model=SceneInstanceView,
    status_code=status.HTTP_201_CREATED,
)
def duplicate_scene_instance(
    project_id: int,
    scene_instance_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> SceneInstanceView:
    project = _owned_project(db, project_id, user.id)
    source = _owned_scene_instance(db, project_id, scene_instance_id, user.id)
    duplicate = SceneInstance(
        project_id=project.id,
        family_id=source.family_id,
        variant_id=source.variant_id,
        title=f"{source.title}（副本）",
        mode="quick",
        template_version=source.template_version,
        draft_state=deepcopy(source.draft_state),
        stale_node_ids=list(source.stale_node_ids),
        archived=False,
    )
    project.updated_at = datetime.now(timezone.utc)
    db.add(duplicate)
    db.flush()
    source_revisions = db.scalars(
        select(ProjectRevision)
        .where(ProjectRevision.project_id == project_id)
        .order_by(ProjectRevision.revision_number.desc())
    ).all()
    latest = next(
        (
            item
            for item in source_revisions
            if item.snapshot.get("scene_context", {}).get("scene_instance_id")
            == source.id
        ),
        None,
    )
    if latest is not None:
        current_revision = db.scalar(
            select(func.max(ProjectRevision.revision_number)).where(
                ProjectRevision.project_id == project.id
            )
        )
        next_revision = (current_revision or 0) + 1
        copied_snapshot = deepcopy(latest.snapshot)
        copied_snapshot["scene_context"]["scene_instance_id"] = duplicate.id
        copied_snapshot["scene_context"]["title"] = duplicate.title
        db.add(
            ProjectRevision(
                project_id=project.id,
                revision_number=next_revision,
                snapshot_schema_version=latest.snapshot_schema_version,
                snapshot=copied_snapshot,
                result_bundle=deepcopy(latest.result_bundle),
                catalog_versions=deepcopy(latest.catalog_versions),
                engine_version=latest.engine_version,
                report_number=f"SC-{project.id:06d}-R{next_revision:03d}",
            )
        )
    db.commit()
    db.refresh(duplicate)
    return _instance_view(duplicate)


@router.get(
    "/projects/{project_id}/scene-revisions",
    response_model=list[SceneRevisionView],
)
def list_scene_revisions(
    project_id: int,
    scene_instance_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> list[SceneRevisionView]:
    _owned_project(db, project_id, user.id)
    if scene_instance_id is not None:
        _owned_scene_instance(db, project_id, scene_instance_id, user.id)
    revisions = db.scalars(
        select(ProjectRevision)
        .where(ProjectRevision.project_id == project_id)
        .order_by(ProjectRevision.revision_number.desc())
    ).all()
    scene_revisions = [
        item
        for item in revisions
        if "scene_context" in item.snapshot
        and (
            scene_instance_id is None
            or item.snapshot["scene_context"].get("scene_instance_id")
            == scene_instance_id
        )
    ]
    return [_scene_revision_view(item) for item in scene_revisions]


@router.post(
    "/projects/{project_id}/scene-revisions",
    response_model=SceneRevisionView,
    status_code=status.HTTP_201_CREATED,
)
def create_scene_revision(
    project_id: int,
    payload: SceneRevisionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> SceneRevisionView:
    project = _owned_project(db, project_id, user.id)
    instance = _owned_scene_instance(
        db, project_id, payload.scene_instance_id, user.id
    )
    family = _family_or_404(instance.family_id)
    if instance.mode == "professional":
        raise HTTPException(
            status_code=409,
            detail="旧专业记录仅供读取；请复制为方案筛查后重新计算",
        )
    if any(item.calculation.mode.value != "quick" for item in payload.node_calculations):
        raise HTTPException(
            status_code=422,
            detail="场景节点计算模式必须与场景实例一致",
        )
    for item in payload.node_calculations:
        require_current_request_schema(item.calculation)
    scene_result = execute_scene(
        family=family,
        variant_id=instance.variant_id,
        mode=instance.mode,
        node_calculations=payload.node_calculations,
        stale_node_ids=instance.stale_node_ids,
        load_cases=payload.load_cases,
        site_profile=(
            ProjectSiteProfile.model_validate(project.site_profile)
            if project.site_profile
            else None
        ),
        geotechnical_profile=(
            ProjectGeotechnicalProfile.model_validate(project.geotechnical_profile)
            if project.geotechnical_profile
            else None
        ),
        structural_profile=payload.structural_profile,
        custom_sections=[
            CustomSectionDefinition.model_validate(item)
            for item in (project.custom_sections or [])
        ],
        strict_site_conditions=True,
    )
    calculation_results = {
        node_id: node_result.calculation_result
        for node_id, node_result in scene_result.node_results.items()
        if node_result.calculation_result is not None
    }
    current_revision = db.scalar(
        select(func.max(ProjectRevision.revision_number)).where(
            ProjectRevision.project_id == project.id
        )
    )
    next_revision = (current_revision or 0) + 1
    report_number = f"SC-{project.id:06d}-R{next_revision:03d}"
    revision = ProjectRevision(
        project_id=project.id,
        revision_number=next_revision,
        snapshot_schema_version=SCENE_SNAPSHOT_SCHEMA_VERSION,
        snapshot={
            "scene_context": {
                "scene_instance_id": instance.id,
                "family_id": instance.family_id,
                "variant_id": instance.variant_id,
                "title": instance.title,
                "mode": instance.mode,
                "template_version": instance.template_version,
                "draft_state": instance.draft_state,
            },
            "scene_graph": instantiate_scene_graph(
                family, instance.variant_id
            ).model_dump(mode="json"),
            "scene_result": scene_result.model_dump(mode="json"),
            "site_profile": deepcopy(project.site_profile),
            "geotechnical_profile": deepcopy(project.geotechnical_profile),
            "structural_profile": (
                payload.structural_profile.model_dump(mode="json")
                if payload.structural_profile
                else None
            ),
            "load_cases": [
                item.model_dump(mode="json") for item in scene_result.load_cases
            ],
            "node_calculations": [
                item.model_dump(mode="json") for item in payload.node_calculations
            ],
        },
        result_bundle={
            key: value.model_dump(mode="json")
            for key, value in calculation_results.items()
        },
        catalog_versions=scene_result.catalog_versions,
        engine_version=(
            next(iter(calculation_results.values())).engine_version
            if calculation_results
            else ENGINE_VERSION
        ),
        report_number=report_number,
    )
    instance.stale_node_ids = scene_result.stale_node_ids
    instance.updated_at = datetime.now(timezone.utc)
    project.updated_at = datetime.now(timezone.utc)
    db.add(revision)
    db.commit()
    db.refresh(revision)
    return _scene_revision_view(revision)
