"""Regression tests for API hardening: query shape, draft validation, 4xx edge paths."""
from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import require_ready_user
from app.config import Settings
from app.core.errors import CalculationInputError
from app.database import Base, get_db
from app.models import (
    ProjectRevision,
    ProjectVersion,
    SceneAnalysisSnapshotRecord,
    SceneInstance,
    User,
)
from app.routers import project_routes, scene_routes

SITE_PROFILE = {
    "region_preset": "zhejiang_inland",
    "recurrence_period_years": 50,
    "basic_wind_pressure_kpa": 0.45,
    "basic_snow_pressure_kpa": 0.55,
    "climate_source_reference": "GB 50009-2012 表 E.5",
    "terrain_category": "B",
    "structure_shape": "open_frame",
    "roof_form": "flat",
    "seismic_level": "7_010g",
}
SIMPLE_GEOMETRY = {
    "layout_mode": "custom_grid",
    "nodes": [
        {"id": "B1", "x_m": 0, "y_m": 0, "z_m": 0, "support": "fixed"},
        {"id": "T1", "x_m": 0, "y_m": 0, "z_m": 3},
    ],
    "members": [{"id": "C1", "start_node_id": "B1", "end_node_id": "T1", "role": "column", "group_id": "columns"}],
    "roof_surfaces": [],
    "source": "hardening test",
}
TRANSIENT_KEYS = {"last_analysis_package", "last_analysis_snapshot", "last_analysis_snapshot_id", "foundation_candidate_sets"}


@pytest.fixture()
def env() -> Iterator[SimpleNamespace]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    with Session() as db:
        user = User(username="owner", display_name="owner", password_hash="unused", must_change_password=False)
        db.add(user)
        db.commit()
        user_id = user.id
    statements: list[str] = []
    event.listen(engine, "before_cursor_execute", lambda *args: statements.append(args[2]))

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(project_routes.router, prefix="/api/v2")
    app.include_router(scene_routes.router, prefix="/api/v2")
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_ready_user] = lambda: SimpleNamespace(id=user_id)

    @app.exception_handler(CalculationInputError)
    async def handle_input_error(_: Request, exc: CalculationInputError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, Session=Session, statements=statements, user_id=user_id)
    engine.dispose()


def _project(env, **fields) -> int:
    response = env.client.post("/api/v2/projects", json={"name": "hardening", **fields})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _instance(env, project_id: int, variant_id: str = "flat-single", draft_state: dict | None = None) -> int:
    response = env.client.post(f"/api/v2/projects/{project_id}/scene-instances", json={
        "family_id": "pergola-pavilion", "variant_id": variant_id, "title": "方案", "mode": "quick",
        "draft_state": draft_state or {},
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _set_instance(env, instance_id: int, **fields) -> None:
    with env.Session() as db:
        instance = db.get(SceneInstance, instance_id)
        for key, value in fields.items():
            setattr(instance, key, value)
        db.commit()


def _scene_revision(env, project_id: int, instance_id: int) -> dict:
    response = env.client.post(f"/api/v2/projects/{project_id}/scene-revisions", json={
        "scene_instance_id": instance_id, "node_calculations": [], "confirmed_input_nodes": ["environment"],
    })
    assert response.status_code == 201, response.text
    return response.json()


def _legacy_scene_revision(env, project_id: int, instance_id: int, number: int, draft_state: dict) -> int:
    """A row shaped like revisions written before the scene_instance_id column."""
    template = _scene_revision_row(env, project_id)
    with env.Session() as db:
        snapshot = {**template.snapshot, "scene_context": {
            **template.snapshot["scene_context"], "scene_instance_id": instance_id, "draft_state": draft_state,
        }}
        row = ProjectRevision(
            project_id=project_id, revision_number=number, snapshot_schema_version=template.snapshot_schema_version,
            snapshot=snapshot, result_bundle={}, catalog_versions={}, engine_version="legacy",
            report_number=f"LEGACY-{project_id}-{number}", scene_instance_id=instance_id,
        )
        db.add(row)
        db.commit()
        return row.id


def _scene_revision_row(env, project_id: int) -> ProjectRevision:
    with env.Session() as db:
        return db.scalars(
            select(ProjectRevision).where(ProjectRevision.project_id == project_id).order_by(ProjectRevision.id)
        ).first()


# --- Task 1: COUNT queries and indexed scene revision lookups -----------------

def test_project_listing_counts_without_loading_revision_json(env):
    project_id = _project(env)
    with env.Session() as db:
        db.add_all([
            ProjectVersion(project_id=project_id, version_number=1, calculation_input={}, calculation_result={},
                           engine_version="x", report_number="V-1"),
            ProjectRevision(project_id=project_id, revision_number=1, snapshot={"big": "x" * 100}, result_bundle={},
                            engine_version="x", report_number="R-1"),
            ProjectRevision(project_id=project_id, revision_number=2, snapshot={}, result_bundle={},
                            engine_version="x", report_number="R-2"),
        ])
        db.commit()
    env.statements.clear()
    listed = env.client.get("/api/v2/projects").json()
    single = env.client.get(f"/api/v2/projects/{project_id}").json()
    assert listed[0]["version_count"] == single["version_count"] == 3
    loaded_json = [sql for sql in env.statements if "snapshot" in sql or "calculation_result" in sql]
    assert loaded_json == []


def test_scene_revision_lookups_filter_by_indexed_column(env):
    project_id = _project(env, site_profile=SITE_PROFILE)
    first = _instance(env, project_id)
    second = _instance(env, project_id)
    revision = _scene_revision(env, project_id, first)
    with env.Session() as db:
        assert db.get(ProjectRevision, revision["id"]).scene_instance_id == first

    env.statements.clear()
    patched = env.client.patch(f"/api/v2/projects/{project_id}/scene-instances/{first}",
                               json={"changed_node_ids": ["environment"]})
    assert patched.status_code == 200, patched.text
    assert patched.json()["stale_node_ids"]
    assert not [sql for sql in env.statements if "project_revisions.snapshot" in sql]

    listed = env.client.get(f"/api/v2/projects/{project_id}/scene-revisions", params={"scene_instance_id": first})
    assert [item["id"] for item in listed.json()] == [revision["id"]]
    assert env.client.get(f"/api/v2/projects/{project_id}/scene-revisions",
                          params={"scene_instance_id": second}).json() == []
    assert [item["id"] for item in env.client.get(f"/api/v2/projects/{project_id}/scene-revisions").json()] == [revision["id"]]


# --- Task 2: revision snapshots drop server-owned caches -----------------------

def test_scene_revision_snapshot_strips_transient_draft_keys(env):
    project_id = _project(env, site_profile=SITE_PROFILE)
    instance_id = _instance(env, project_id)
    _set_instance(env, instance_id, draft_state={
        "material_system": "steel", "geometry": {"span_m": 4}, "user_note": "keep",
        "last_analysis_package": {"huge": "x" * 1000}, "last_analysis_snapshot": {"huge": True},
        "last_analysis_snapshot_id": 7, "foundation_candidate_sets": {"FI1": {"cached": True}},
    })
    revision = _scene_revision(env, project_id, instance_id)
    with env.Session() as db:
        draft = db.get(ProjectRevision, revision["id"]).snapshot["scene_context"]["draft_state"]
    assert not TRANSIENT_KEYS & draft.keys()
    assert draft == {"material_system": "steel", "geometry": {"span_m": 4}, "user_note": "keep"}
    report = env.client.get(f"/api/v2/projects/{project_id}/revisions/{revision['id']}/report.pdf")
    assert report.status_code == 200 and report.content.startswith(b"%PDF")


def test_duplicate_copies_stripped_draft_and_leaves_source_revision_untouched(env):
    project_id = _project(env, site_profile=SITE_PROFILE)
    source_id = _instance(env, project_id)
    _scene_revision(env, project_id, source_id)
    legacy_draft = {"material_system": "steel", "last_analysis_package": {"old": True}, "foundation_candidate_sets": {"a": 1}}
    legacy_id = _legacy_scene_revision(env, project_id, source_id, 2, legacy_draft)
    with env.Session() as db:
        before = db.get(ProjectRevision, legacy_id).snapshot

    duplicate = env.client.post(f"/api/v2/projects/{project_id}/scene-instances/{source_id}/duplicate")
    assert duplicate.status_code == 201, duplicate.text
    duplicate_id = duplicate.json()["id"]
    with env.Session() as db:
        assert db.get(ProjectRevision, legacy_id).snapshot == before
        copy = db.scalar(select(ProjectRevision).where(ProjectRevision.scene_instance_id == duplicate_id))
    assert copy.revision_number == 3
    assert copy.snapshot["scene_context"]["scene_instance_id"] == duplicate_id
    assert copy.snapshot["scene_context"]["draft_state"] == {"material_system": "steel"}


# --- Task 3: PATCH validates geometry, marks stale and bounds size ------------

def test_patch_rejects_invalid_geometry_profile_without_saving(env):
    project_id = _project(env)
    instance_id = _instance(env, project_id, draft_state={"user_note": "before"})
    broken = {**SIMPLE_GEOMETRY, "members": [{"id": "C1", "start_node_id": "B1", "end_node_id": "MISSING",
                                              "role": "column", "group_id": "columns"}]}
    response = env.client.patch(f"/api/v2/projects/{project_id}/scene-instances/{instance_id}",
                                json={"draft_state": {"geometry_profile": broken}})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_geometry_profile"
    with env.Session() as db:
        assert db.get(SceneInstance, instance_id).draft_state["user_note"] == "before"
    assert env.client.get(f"/api/v2/projects/{project_id}/scene-instances/{instance_id}/geometry").status_code == 200


def test_create_rejects_invalid_geometry_profile(env):
    project_id = _project(env)
    response = env.client.post(f"/api/v2/projects/{project_id}/scene-instances", json={
        "family_id": "pergola-pavilion", "variant_id": "flat-single", "title": "方案",
        "draft_state": {"geometry_profile": {"nodes": []}},
    })
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_geometry_profile"


def test_patch_geometry_change_marks_saved_result_stale_like_put(env):
    project_id = _project(env, site_profile=SITE_PROFILE)
    instance_id = _instance(env, project_id)
    _scene_revision(env, project_id, instance_id)
    _set_instance(env, instance_id, stale_node_ids=[])
    patched = env.client.patch(f"/api/v2/projects/{project_id}/scene-instances/{instance_id}",
                               json={"draft_state": {"geometry_profile": SIMPLE_GEOMETRY}})
    assert patched.status_code == 200, patched.text
    put = env.client.put(f"/api/v2/projects/{project_id}/scene-instances/{instance_id}/geometry", json=SIMPLE_GEOMETRY)
    assert put.status_code == 200
    with env.Session() as db:
        after_put = db.get(SceneInstance, instance_id).stale_node_ids
    assert patched.json()["stale_node_ids"] and set(patched.json()["stale_node_ids"]) == set(after_put)
    # The stored geometry is the validated, normalized model.
    assert patched.json()["draft_state"]["geometry_profile"]["profile_version"] == "1.0"
    # Re-saving the same model is not a change.
    _set_instance(env, instance_id, stale_node_ids=[])
    same = env.client.patch(f"/api/v2/projects/{project_id}/scene-instances/{instance_id}",
                            json={"draft_state": {"geometry_profile": SIMPLE_GEOMETRY}})
    assert same.json()["stale_node_ids"] == []


def test_patch_rejects_oversized_draft_state(env):
    project_id = _project(env)
    instance_id = _instance(env, project_id)
    response = env.client.patch(f"/api/v2/projects/{project_id}/scene-instances/{instance_id}",
                                json={"draft_state": {"blob": "x" * (scene_routes.MAX_DRAFT_STATE_BYTES + 1)}})
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "draft_state_too_large"


def test_corrupt_stored_geometry_returns_422_not_500(env):
    project_id = _project(env)
    instance_id = _instance(env, project_id)
    _set_instance(env, instance_id, draft_state={"geometry_profile": {"nodes": "corrupt"}})
    base = f"/api/v2/projects/{project_id}/scene-instances/{instance_id}"
    geometry = env.client.get(f"{base}/geometry")
    assert geometry.status_code == 422
    assert geometry.json()["detail"]["code"] == "invalid_saved_geometry"
    analyze = env.client.post(f"{base}/analyze", json={"stage": "scheme_estimate"})
    assert analyze.status_code == 422
    assert analyze.json()["detail"]["code"] == "invalid_saved_geometry"


# --- Task 4: removed catalog variants and dangling foundation references ------

def test_removed_variant_can_switch_away_and_recommendation_is_422(env):
    project_id = _project(env)
    instance_id = _instance(env, project_id)
    _set_instance(env, instance_id, variant_id="retired-variant")
    base = f"/api/v2/projects/{project_id}/scene-instances/{instance_id}"
    recommendation = env.client.post(f"{base}/recommendations",
                                     json={"target_node_id": "foundation_left", "vertical_kn": 100})
    assert recommendation.status_code == 422
    assert recommendation.json()["detail"]["code"] == "unknown_scene_variant"
    switched = env.client.patch(base, json={"variant_id": "flat-single"})
    assert switched.status_code == 200, switched.text
    assert switched.json()["variant_id"] == "flat-single"


@pytest.mark.parametrize(("dangling", "code"), [
    ({"foundation_type_id": "missing-type"}, "unknown_foundation_type"),
    ({"support_id": "missing-support"}, "unknown_foundation_support"),
])
def test_foundation_candidates_with_dangling_reference_is_422(env, dangling, code):
    project_id = _project(env)
    instance_id = _instance(env, project_id)
    foundation_type = {"id": "fa", "mark": "F-A", "title": "基础", "form_id": "spread-prismatic", "length_m": 1.8,
                       "width_m": 1.5, "thickness_mm": 450, "embedment_m": 1.1, "concrete_grade": "C30",
                       "rebar_grade": "HRB400", "bottom_x": "Phi14@150", "bottom_y": "Phi12@150", "cover_mm": 50}
    # Geometry 2.0 does not cross-check foundation references at validation time.
    geometry = {**SIMPLE_GEOMETRY, "profile_version": "2.0",
                "supports": [{"id": "S1", "node_id": "B1", "restraint": "fixed"}],
                "foundation_types": [foundation_type],
                "foundation_instances": [{"id": "FI1", "support_id": "S1", "foundation_type_id": "fa",
                                          "mark": "F-A-01", **dangling}]}
    with env.Session() as db:
        record = SceneAnalysisSnapshotRecord(project_id=project_id, scene_instance_id=instance_id, snapshot_number=1,
                                             content_hash="0" * 64, snapshot={"analysis": {"solver_result": {}}},
                                             report_number=f"SNAP-{code}")
        db.add(record)
        db.commit()
        _set_instance(env, instance_id, draft_state={"geometry_profile": geometry, "last_analysis_snapshot_id": record.id})
    response = env.client.post(f"/api/v2/projects/{project_id}/scene-instances/{instance_id}/foundation-candidates",
                               json={"foundation_instance_id": "FI1"})
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == code


def test_bootstrap_rejects_short_admin_password_with_clear_error(monkeypatch):
    from app import main

    engine = create_engine("sqlite://", poolclass=StaticPool)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(main, "get_settings", lambda: Settings(
        bootstrap_admin_username="admin", bootstrap_admin_password="short"))
    with pytest.raises(main.BootstrapConfigError, match="STEEL_COMPASS_BOOTSTRAP_ADMIN_PASSWORD"):
        main.bootstrap_database()
    engine.dispose()


# --- Task 5: a lost numbering race is a clean 409 ------------------------------

def test_version_number_conflict_returns_409(env, monkeypatch):
    project_id = _project(env)
    with env.Session() as db:
        db.add(ProjectVersion(project_id=project_id, version_number=1, calculation_input={}, calculation_result={},
                              engine_version="x", report_number=f"SC-{project_id:06d}-V001"))
        db.commit()
    # Simulate SQLite's ignored FOR UPDATE: a concurrent writer already took number 1.
    monkeypatch.setattr(project_routes, "_next_number", lambda *args: 1)
    from app.core.scenarios import SCENARIOS
    template = SCENARIOS[0]
    response = env.client.post(f"/api/v2/projects/{project_id}/versions", json={"calculation": {
        "schema_version": "3.3", "mode": "quick", "module": template.module.value, "project_name": "race",
        "standard_profile": "CN-2024", "confirmed_assumptions": True,
        "inputs": template.inputs, "loads": [item.model_dump(mode="json") for item in template.loads],
    }})
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "numbering_conflict"


def test_scene_revision_number_conflict_returns_409(env, monkeypatch):
    project_id = _project(env, site_profile=SITE_PROFILE)
    instance_id = _instance(env, project_id)
    _scene_revision(env, project_id, instance_id)
    monkeypatch.setattr(scene_routes, "_next_number", lambda *args: 1)
    response = env.client.post(f"/api/v2/projects/{project_id}/scene-revisions", json={
        "scene_instance_id": instance_id, "node_calculations": [], "confirmed_input_nodes": ["environment"],
    })
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "numbering_conflict"


# --- Task 6: production cookie policy ------------------------------------------

def test_production_requires_secure_cookie_except_local_http():
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(environment="production", cookie_secure=False, frontend_origin="https://steel.example.com")
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(environment="production", cookie_secure=False, frontend_origin="http://192.168.1.20")
    # Documented local Docker flow (.env.example): http://127.0.0.1 with COOKIE_SECURE=false.
    Settings(environment="production", cookie_secure=False, frontend_origin="http://127.0.0.1")
    Settings(environment="production", cookie_secure=False, frontend_origin="http://localhost:3000")
    Settings(environment="production", cookie_secure=True, frontend_origin="https://steel.example.com")
    Settings(environment="production", cookie_secure=False, allow_insecure_cookie=True,
             frontend_origin="http://192.168.1.20")
    Settings(environment="development", cookie_secure=False, frontend_origin="https://steel.example.com")
