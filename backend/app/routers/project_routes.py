from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..api_schemas import (
    CustomSectionCreateRequest,
    ProjectCustomSections,
    ProjectCreate,
    ProjectView,
    VersionCreate,
    VersionView,
    RevisionCreate,
    RevisionView,
)
from ..core.design_profiles import CustomSectionCreate, CustomSectionDefinition, calculate_custom_section
from ..auth import require_ready_user
from ..core.engine import calculate
from ..core import SCHEMA_VERSION
from ..core.schemas import CalculationResult, require_current_request_schema
from ..core.schemas import CalculationModule, LoadItem, LoadKind
from ..database import get_db
from ..models import Project, ProjectRevision, ProjectVersion, SceneInstance, User
from ..core.scene_schemas import SceneRevisionResult
from ..core.site_profile import ProjectSiteProfile
from ..core.design_profiles import ProjectGeotechnicalProfile
from ..report import (
    build_calculation_pdf,
    build_project_pdf,
    build_scene_project_pdf,
)


router = APIRouter(prefix="/projects", tags=["projects"])


def _invalidate_project_analysis(db: Session, project: Project) -> None:
    """Invalidate mutable pointers only; historical analysis snapshots stay intact."""
    from ..core.scene_catalog import get_scene_family, instantiate_scene_graph
    for instance in db.scalars(select(SceneInstance).where(SceneInstance.project_id == project.id)):
        instance.draft_state = {**(instance.draft_state or {}), "last_analysis_package": None,
            "last_analysis_snapshot": None, "last_analysis_snapshot_id": None, "foundation_candidate_sets": {}}
        family = get_scene_family(instance.family_id)
        if family:
            try:
                graph = instantiate_scene_graph(family, instance.variant_id)
            except KeyError:
                # Historical variants remain readable even after catalog changes.
                pass
            else:
                instance.stale_node_ids = [n.id for n in graph.nodes if n.applicability != "not_applicable"]
        instance.updated_at = datetime.now(timezone.utc)


def _owned_project(db: Session, project_id: int, user_id: int) -> Project:
    project = db.scalar(
        select(Project).where(Project.id == project_id, Project.owner_id == user_id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def _lock_project_numbering(db: Session, project_id: int) -> None:
    """Serialize number allocation per project (row lock; no-op on SQLite).

    Version, revision, report and snapshot numbers are max+1 within a project;
    without the lock two concurrent saves read the same max and one fails on
    the unique constraint after its calculation already ran.
    """
    db.execute(select(Project.id).where(Project.id == project_id).with_for_update())


def _project_view(project: Project) -> ProjectView:
    return ProjectView(
        id=project.id,
        name=project.name,
        description=project.description,
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
        created_at=project.created_at,
        updated_at=project.updated_at,
        version_count=len(project.versions) + len(project.revisions),
    )


def _version_view(version: ProjectVersion) -> VersionView:
    return VersionView(
        id=version.id,
        project_id=version.project_id,
        version_number=version.version_number,
        calculation_input=version.calculation_input,
        calculation_result=CalculationResult.model_validate(version.calculation_result),
        engine_version=version.engine_version,
        report_number=version.report_number,
        created_at=version.created_at,
    )


def _revision_view(revision: ProjectRevision) -> RevisionView:
    return RevisionView(
        id=revision.id,
        project_id=revision.project_id,
        revision_number=revision.revision_number,
        snapshot_schema_version=revision.snapshot_schema_version,
        snapshot=revision.snapshot,
        result_bundle={
            key: CalculationResult.model_validate(value)
            for key, value in revision.result_bundle.items()
        },
        catalog_versions=revision.catalog_versions,
        engine_version=revision.engine_version,
        report_number=revision.report_number,
        created_at=revision.created_at,
    )


def _reaction_value(
    result: CalculationResult, support: str, suffix: str
) -> float | None:
    candidates = (
        [f"{support}_{suffix}"] if support in {"left", "right"} else []
    ) + [f"base_{suffix}", suffix]
    for key in candidates:
        quantity = result.reactions.get(key)
        if quantity is not None:
            return quantity.value
    return None


def _apply_connections(
    calculation,
    node_id: str,
    connections,
    results: dict[str, CalculationResult],
):
    incoming = next(
        (item for item in connections if item.target_node_id == node_id), None
    )
    if incoming is None:
        return calculation
    source = results.get(incoming.source_node_id)
    if source is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_connection_order",
                "message": "连接源节点必须排在基础节点之前",
            },
        )
    if calculation.module is not CalculationModule.SPREAD_FOOTING:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unsupported_connection_target",
                "message": "首期反力连接仅支持柱下独立基础",
            },
        )
    vertical = _reaction_value(source, incoming.support, "vertical")
    if vertical is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "missing_source_reaction",
                "message": "源节点没有可传递的竖向反力",
            },
        )
    horizontal = _reaction_value(source, incoming.support, "horizontal") or 0.0
    moment = _reaction_value(source, incoming.support, "moment") or 0.0
    updated_inputs = {
        **calculation.inputs,
        "horizontal_x_kn": horizontal,
        "moment_y_kn_m": moment,
        "uplift_kn": abs(vertical) if vertical < 0 else calculation.inputs.get("uplift_kn", 0),
        "reaction_source_node_id": incoming.source_node_id,
    }
    return calculation.model_copy(
        update={
            "inputs": updated_inputs,
            "loads": [
                LoadItem(
                    kind=LoadKind.DEAD,
                    value=max(vertical, 0),
                    unit="kN",
                    source=f"项目节点 {incoming.source_node_id} 的 {incoming.support} 支座反力",
                    source_reference=f"trace:{source.trace_id}",
                )
            ],
        },
        deep=True,
    )


@router.get("", response_model=list[ProjectView])
def list_projects(
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> list[ProjectView]:
    projects = db.scalars(
        select(Project)
        .where(Project.owner_id == user.id)
        .order_by(Project.updated_at.desc())
    ).all()
    return [_project_view(item) for item in projects]


@router.post("", response_model=ProjectView, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> ProjectView:
    project = Project(
        owner_id=user.id,
        name=payload.name,
        description=payload.description,
        site_profile=(payload.site_profile.model_dump(mode="json") if payload.site_profile else None),
        geotechnical_profile=(payload.geotechnical_profile.model_dump(mode="json") if payload.geotechnical_profile else None),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_view(project)


@router.get("/{project_id}", response_model=ProjectView)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> ProjectView:
    return _project_view(_owned_project(db, project_id, user.id))


@router.get("/{project_id}/site-profile", response_model=ProjectSiteProfile | None)
def get_project_site_profile(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> ProjectSiteProfile | None:
    project = _owned_project(db, project_id, user.id)
    return ProjectSiteProfile.model_validate(project.site_profile) if project.site_profile else None


@router.put("/{project_id}/site-profile", response_model=ProjectSiteProfile)
def update_project_site_profile(
    project_id: int,
    payload: ProjectSiteProfile,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> ProjectSiteProfile:
    project = _owned_project(db, project_id, user.id)
    # A scene-specific editor may intentionally omit fields that are hidden for
    # its current variant.  Merge those edits into the complete project profile
    # instead of erasing climate/seismic data previously collected by another
    # scene.
    existing = (
        ProjectSiteProfile.model_validate(project.site_profile).model_dump(
            mode="json"
        )
        if project.site_profile
        else {}
    )
    incoming = payload.model_dump(mode="json", exclude_unset=True)
    if "catalog_versions" in incoming:
        incoming["catalog_versions"] = {
            **existing.get("catalog_versions", {}),
            **incoming["catalog_versions"],
        }
    if "completed_conditions" in incoming:
        incoming["completed_conditions"] = list(
            dict.fromkeys(
                [
                    *existing.get("completed_conditions", []),
                    *incoming["completed_conditions"],
                ]
            )
        )
    updated = ProjectSiteProfile.model_validate({**existing, **incoming})
    if project.site_profile != updated.model_dump(mode="json"):
        _invalidate_project_analysis(db, project)
    project.site_profile = updated.model_dump(mode="json")
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    return updated


@router.get(
    "/{project_id}/geotechnical-profile",
    response_model=ProjectGeotechnicalProfile | None,
)
def get_project_geotechnical_profile(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> ProjectGeotechnicalProfile | None:
    project = _owned_project(db, project_id, user.id)
    return (
        ProjectGeotechnicalProfile.model_validate(project.geotechnical_profile)
        if project.geotechnical_profile
        else None
    )


@router.put(
    "/{project_id}/geotechnical-profile",
    response_model=ProjectGeotechnicalProfile,
)
def update_project_geotechnical_profile(
    project_id: int,
    payload: ProjectGeotechnicalProfile,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> ProjectGeotechnicalProfile:
    project = _owned_project(db, project_id, user.id)
    project.geotechnical_profile = payload.model_dump(mode="json")
    _invalidate_project_analysis(db, project)
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    return payload


@router.get("/{project_id}/custom-sections", response_model=ProjectCustomSections)
def get_project_custom_sections(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> ProjectCustomSections:
    project = _owned_project(db, project_id, user.id)
    return ProjectCustomSections(items=project.custom_sections or [])


@router.put("/{project_id}/custom-sections", response_model=ProjectCustomSections)
def update_project_custom_sections(
    project_id: int,
    payload: ProjectCustomSections,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> ProjectCustomSections:
    project = _owned_project(db, project_id, user.id)
    project.custom_sections = [item.model_dump(mode="json") for item in payload.items]
    _invalidate_project_analysis(db, project)
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    return payload


@router.post("/{project_id}/custom-sections", response_model=ProjectCustomSections)
def create_project_custom_section(
    project_id: int,
    payload: CustomSectionCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> ProjectCustomSections:
    project = _owned_project(db, project_id, user.id)
    current = list(project.custom_sections or [])
    if any(item.get("id") == payload.id for item in current):
        raise HTTPException(status_code=409, detail="自定义截面编号已存在")
    section = calculate_custom_section(payload, section_id=payload.id)
    current.append(section.model_dump(mode="json"))
    project.custom_sections = current
    _invalidate_project_analysis(db, project)
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    return ProjectCustomSections(items=current)


@router.post(
    "/{project_id}/custom-sections/{section_id}/revisions",
    response_model=CustomSectionDefinition,
)
def revise_project_custom_section(
    project_id: int,
    section_id: str,
    payload: CustomSectionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> CustomSectionDefinition:
    project = _owned_project(db, project_id, user.id)
    current = list(project.custom_sections or [])
    previous = [item for item in current if item.get("id") == section_id or item.get("supersedes_id") == section_id]
    if not previous:
        raise HTTPException(status_code=404, detail="待修订的自定义截面不存在")
    revision = max(int(item.get("revision", 1)) for item in previous) + 1
    revised_id = f"{section_id}.r{revision}"
    section = calculate_custom_section(payload, section_id=revised_id).model_copy(update={"revision": revision})
    record = section.model_dump(mode="json")
    record["supersedes_id"] = section_id
    current.append(record)
    project.custom_sections = current
    _invalidate_project_analysis(db, project)
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    return section


@router.post("/{project_id}/duplicate", response_model=ProjectView)
def duplicate_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> ProjectView:
    source = _owned_project(db, project_id, user.id)
    duplicate = Project(
        owner_id=user.id,
        name=f"{source.name}（副本）",
        description=source.description,
        site_profile=deepcopy(source.site_profile),
        geotechnical_profile=deepcopy(source.geotechnical_profile),
        custom_sections=deepcopy(source.custom_sections),
    )
    db.add(duplicate)
    db.flush()
    if source.versions:
        latest = source.versions[-1]
        db.add(
            ProjectVersion(
                project_id=duplicate.id,
                version_number=1,
                calculation_input=latest.calculation_input,
                calculation_result=latest.calculation_result,
                engine_version=latest.engine_version,
                report_number=f"SC-{duplicate.id:06d}-V001",
            )
        )
    db.commit()
    db.refresh(duplicate)
    return _project_view(duplicate)


@router.get("/{project_id}/versions", response_model=list[VersionView])
def list_versions(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> list[VersionView]:
    project = _owned_project(db, project_id, user.id)
    return [_version_view(item) for item in project.versions]


@router.post(
    "/{project_id}/versions",
    response_model=VersionView,
    status_code=status.HTTP_201_CREATED,
)
def create_version(
    project_id: int,
    payload: VersionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> VersionView:
    project = _owned_project(db, project_id, user.id)
    require_current_request_schema(payload.calculation)
    result = calculate(payload.calculation)
    _lock_project_numbering(db, project.id)
    current_version = db.scalar(
        select(func.max(ProjectVersion.version_number)).where(
            ProjectVersion.project_id == project.id
        )
    )
    next_version = (current_version or 0) + 1
    report_number = f"SC-{project.id:06d}-V{next_version:03d}"
    version = ProjectVersion(
        project_id=project.id,
        version_number=next_version,
        calculation_input=payload.calculation.model_dump(mode="json"),
        calculation_result=result.model_dump(mode="json"),
        engine_version=result.engine_version,
        report_number=report_number,
    )
    project.updated_at = datetime.now(timezone.utc)
    db.add(version)
    db.commit()
    db.refresh(version)
    return _version_view(version)


@router.get("/{project_id}/versions/{version_id}/report.pdf")
def download_report(
    project_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> Response:
    _owned_project(db, project_id, user.id)
    version = db.scalar(
        select(ProjectVersion).where(
            ProjectVersion.id == version_id,
            ProjectVersion.project_id == project_id,
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="项目版本不存在")
    result = CalculationResult.model_validate(version.calculation_result)
    pdf = build_calculation_pdf(result, version.report_number)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{version.report_number}.pdf"'
        },
    )


@router.get("/{project_id}/revisions", response_model=list[RevisionView])
def list_revisions(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> list[RevisionView]:
    project = _owned_project(db, project_id, user.id)
    return [_revision_view(item) for item in project.revisions]


@router.post(
    "/{project_id}/revisions",
    response_model=RevisionView,
    status_code=status.HTTP_201_CREATED,
)
def create_revision(
    project_id: int,
    payload: RevisionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> RevisionView:
    project = _owned_project(db, project_id, user.id)
    node_ids = [item.node_id for item in payload.calculations]
    if len(node_ids) != len(set(node_ids)):
        raise HTTPException(status_code=422, detail="计算节点编号不得重复")
    valid_ids = set(node_ids)
    if any(
        item.source_node_id not in valid_ids or item.target_node_id not in valid_ids
        for item in payload.connections
    ):
        raise HTTPException(status_code=422, detail="连接引用了不存在的计算节点")

    results: dict[str, CalculationResult] = {}
    snapshot_nodes: list[dict] = []
    for node in payload.calculations:
        require_current_request_schema(node.calculation)
        calculation = _apply_connections(
            node.calculation,
            node.node_id,
            payload.connections,
            results,
        )
        result = calculate(calculation)
        results[node.node_id] = result
        snapshot_nodes.append(
            {
                "node_id": node.node_id,
                "label": node.label,
                "calculation": calculation.model_dump(mode="json"),
            }
        )

    _lock_project_numbering(db, project.id)
    current_revision = db.scalar(
        select(func.max(ProjectRevision.revision_number)).where(
            ProjectRevision.project_id == project.id
        )
    )
    next_revision = (current_revision or 0) + 1
    report_number = f"SC-{project.id:06d}-R{next_revision:03d}"
    catalog_versions = {
        key: value
        for result in results.values()
        for key, value in result.catalog_versions.items()
    }
    revision = ProjectRevision(
        project_id=project.id,
        revision_number=next_revision,
        snapshot_schema_version=SCHEMA_VERSION,
        snapshot={
            "calculations": snapshot_nodes,
            "connections": [item.model_dump(mode="json") for item in payload.connections],
            "site_profile": deepcopy(project.site_profile),
        },
        result_bundle={
            key: value.model_dump(mode="json") for key, value in results.items()
        },
        catalog_versions=catalog_versions,
        engine_version=next(iter(results.values())).engine_version,
        report_number=report_number,
    )
    project.updated_at = datetime.now(timezone.utc)
    db.add(revision)
    db.commit()
    db.refresh(revision)
    return _revision_view(revision)


@router.get("/{project_id}/revisions/{revision_id}/report.pdf")
def download_revision_report(
    project_id: int,
    revision_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_ready_user),
) -> Response:
    _owned_project(db, project_id, user.id)
    revision = db.scalar(
        select(ProjectRevision).where(
            ProjectRevision.id == revision_id,
            ProjectRevision.project_id == project_id,
        )
    )
    if revision is None:
        raise HTTPException(status_code=404, detail="项目修订不存在")
    results = [
        CalculationResult.model_validate(value)
        for value in revision.result_bundle.values()
    ]
    if revision.snapshot.get("scene_result"):
        scene_context = revision.snapshot.get("scene_context", {})
        pdf = build_scene_project_pdf(
            SceneRevisionResult.model_validate(revision.snapshot["scene_result"]),
            results,
            revision.report_number,
            scene_context.get("title", "完整场景"),
            scene_context,
        )
    else:
        pdf = build_project_pdf(results, revision.report_number)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{revision.report_number}.pdf"'
        },
    )
