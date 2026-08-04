from __future__ import annotations

from datetime import datetime, timezone
from copy import deepcopy

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..api_schemas import (
    SceneInstanceCreate,
    SceneInstanceUpdate,
    SceneInstanceView,
    SceneRevisionCreate,
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
from ..core.scene_schemas import SceneFamily, SceneRevisionResult
from ..database import get_db
from ..models import Project, ProjectRevision, SceneInstance, User


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
        instance.mode = payload.mode.value
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
        mode=source.mode,
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
    if any(
        item.calculation.mode.value != instance.mode
        for item in payload.node_calculations
    ):
        raise HTTPException(
            status_code=422,
            detail="场景节点计算模式必须与场景实例一致",
        )
    scene_result = execute_scene(
        family=family,
        variant_id=instance.variant_id,
        mode=instance.mode,
        node_calculations=payload.node_calculations,
        confirmed_input_nodes=payload.confirmed_input_nodes,
        stale_node_ids=instance.stale_node_ids,
        load_cases=payload.load_cases,
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
        snapshot_schema_version="3.1",
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
