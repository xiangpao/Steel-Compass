from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("STEEL_COMPASS_DATABASE_URL", "sqlite:///./test_api.db")
os.environ.setdefault("STEEL_COMPASS_COOKIE_SECURE", "false")
os.environ.setdefault("STEEL_COMPASS_BOOTSTRAP_ADMIN_USERNAME", "admin")
os.environ.setdefault("STEEL_COMPASS_BOOTSTRAP_ADMIN_PASSWORD", "ChangeMe-12345")
Path("test_api.db").unlink(missing_ok=True)

from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_invited_user_project_version_report_and_owner_isolation() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "ChangeMe-12345"},
        )
        assert login.status_code == 200
        response = client.get("/api/v1/scenarios")
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "password_change_required"

        changed = client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "ChangeMe-12345",
                "new_password": "Admin-Changed-12345",
            },
        )
        assert changed.status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401

        assert (
            client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "Admin-Changed-12345"},
            ).status_code
            == 200
        )
        scenarios = client.get("/api/v1/scenarios")
        assert scenarios.status_code == 200
        materials = client.get("/api/v2/catalogs/materials")
        assert materials.status_code == 200
        material_ids = {item["id"] for item in materials.json()["items"]}
        assert {"HPB300", "HRB400", "HRBF500", "RRB400", "HRB600"} <= material_ids
        load_presets = client.get("/api/v2/catalogs/load-presets").json()["items"]
        assert load_presets
        assert {
            "recommended_min",
            "recommended_default",
            "recommended_max",
            "adopted_value",
            "source_reference",
            "direction",
            "application_target",
        } <= load_presets[0].keys()
        assert any(
            item["value_type"] == "project_defined" for item in load_presets
        )
        climate = client.get(
            "/api/v2/catalogs/climate-locations", params={"query": "北京"}
        )
        assert climate.status_code == 200
        assert climate.json()["items"][0]["wind_kpa"]["50"] == 0.45
        scenario = scenarios.json()[0]
        calculation = {
            "schema_version": "3.2",
            "mode": "quick",
            "module": scenario["module"],
            "project_name": scenario["title"],
            "standard_profile": "CN-2024",
            "confirmed_assumptions": True,
            "inputs": scenario["inputs"],
            "loads": scenario["loads"],
        }

        project = client.post(
            "/api/v1/projects",
            json={"name": "API 集成测试", "description": "版本不可变"},
        )
        assert project.status_code == 201
        project_id = project.json()["id"]

        families = client.get("/api/v2/scenario-families")
        assert families.status_code == 200
        assert len(families.json()) == 10
        assert {item["id"] for item in families.json()} >= {
            "pergola-pavilion",
            "signage-billboard",
            "water-feature-pool",
        }
        assert {
            item["id"]
            for item in families.json()
            if item["availability"] == "public"
        } == {
            "pergola-pavilion",
            "canopy",
            "signage-billboard",
            "landscape-wall-fence",
            "entrance-frame",
                "boardwalk-platform",
                "bench-planter",
                "water-feature-pool",
                "landscape-bridge",
                "retaining-facility",
        }
        canopy_family = next(
            item for item in families.json() if item["id"] == "canopy"
        )
        wall_canopy = next(
            item
            for item in canopy_family["variants"]
            if item["id"] == "wall-cantilever"
        )
        assert all(
            node["role"] != "foundation"
            for node in wall_canopy["graph_template"]["nodes"]
        )
        assert wall_canopy["load_package"]["items"][0][
            "recommended_default"
        ] == 0.35
        gravity_scene = client.post(
            f"/api/v2/projects/{project_id}/scene-instances",
            json={
                "family_id": "retaining-facility",
                "variant_id": "gravity",
                "title": "未开放水池",
                "mode": "quick",
            },
        )
        assert gravity_scene.status_code == 201
        gravity_scene_id = gravity_scene.json()["id"]
        library = client.get(
            "/api/v2/calculation-library",
            params={"task": "superstructure", "material": "steel"},
        )
        assert library.status_code == 200
        assert {item["module"] for item in library.json()["items"]} >= {
            "steel_beam",
            "steel_column",
            "portal_frame",
            "planar_truss",
            "steel_infill_wall",
        }
        steel_beam_item = next(
            item
            for item in library.json()["items"]
            if item["module"] == "steel_beam"
        )
        assert "廊架檩条" in steel_beam_item["presets"]

        scene_instance = client.post(
            f"/api/v2/projects/{project_id}/scene-instances",
            json={
                "family_id": "pergola-pavilion",
                "variant_id": "flat-single",
                "title": "钢单跨廊架方案 A",
                "mode": "quick",
                "draft_state": {"wizard_step": 3, "panel_width_m": 1.2},
            },
        )
        assert scene_instance.status_code == 201, scene_instance.text
        instance_data = scene_instance.json()
        updated_instance = client.patch(
            (
                f"/api/v2/projects/{project_id}/scene-instances/"
                f"{instance_data['id']}"
            ),
            json={
                "draft_state": {"wizard_step": 4, "panel_width_m": 1.5},
                "changed_node_ids": ["environment"],
            },
        )
        assert updated_instance.status_code == 200, updated_instance.text
        assert updated_instance.json()["stale_node_ids"] == []
        scene_revision = client.post(
            f"/api/v2/projects/{project_id}/scene-revisions",
            json={
                "scene_instance_id": instance_data["id"],
                "node_calculations": [],
                "confirmed_input_nodes": ["environment"],
            },
        )
        assert scene_revision.status_code == 201, scene_revision.text
        scene_result = scene_revision.json()["scene_result"]
        assert scene_result["status"] == "incomplete"
        assert scene_result["engineering_status"] is None
        assert scene_result["quick_outcome"] is None
        assert scene_result["workflow_status"] == "missing_inputs"
        assert scene_result["result_class"] == "quick_estimate"
        assert scene_result["verification_status"] == "unverified"
        assert scene_result["load_cases"]
        assert scene_result["completed_nodes"] == 1
        assert scene_result["total_required_nodes"] == 7
        assert "左柱脚 / 底板锚栓" in scene_result["missing_nodes"]
        assert scene_revision.json()["snapshot_schema_version"] == "3.2"
        stale_after_result = client.patch(
            (
                f"/api/v2/projects/{project_id}/scene-instances/"
                f"{instance_data['id']}"
            ),
            json={"changed_node_ids": ["environment"]},
        )
        assert stale_after_result.json()["stale_node_ids"] == [
            "roof_members",
            "main_frame",
            "base_left",
            "base_right",
            "foundation_left",
            "foundation_right",
        ]
        revisions = client.get(
            f"/api/v2/projects/{project_id}/scene-revisions",
            params={"scene_instance_id": instance_data["id"]},
        )
        assert revisions.status_code == 200
        assert [item["id"] for item in revisions.json()] == [
            scene_revision.json()["id"]
        ]
        duplicated_instance = client.post(
            (
                f"/api/v2/projects/{project_id}/scene-instances/"
                f"{instance_data['id']}/duplicate"
            )
        )
        assert duplicated_instance.status_code == 201
        duplicate_data = duplicated_instance.json()
        assert duplicate_data["title"] == "钢单跨廊架方案 A（副本）"
        duplicate_revisions = client.get(
            f"/api/v2/projects/{project_id}/scene-revisions",
            params={"scene_instance_id": duplicate_data["id"]},
        )
        assert duplicate_revisions.status_code == 200
        assert len(duplicate_revisions.json()) == 1
        assert duplicate_revisions.json()[0]["report_number"] != scene_revision.json()[
            "report_number"
        ]
        archived = client.patch(
            (
                f"/api/v2/projects/{project_id}/scene-instances/"
                f"{duplicate_data['id']}"
            ),
            json={"title": "方案 B", "archived": True},
        )
        assert archived.status_code == 200
        assert archived.json()["archived"] is True
        visible_instances = client.get(
            f"/api/v2/projects/{project_id}/scene-instances"
        ).json()
        assert {item["id"] for item in visible_instances} == {
            gravity_scene_id,
            instance_data["id"],
        }
        all_instances = client.get(
            f"/api/v2/projects/{project_id}/scene-instances",
            params={"include_archived": True},
        ).json()
        assert {item["id"] for item in all_instances} == {
            gravity_scene_id,
            instance_data["id"],
            duplicate_data["id"],
        }
        scene_report = client.get(
            (
                f"/api/v2/projects/{project_id}/revisions/"
                f"{scene_revision.json()['id']}/report.pdf"
            )
        )
        assert scene_report.status_code == 200
        assert scene_report.content.startswith(b"%PDF")

        version = client.post(
            f"/api/v1/projects/{project_id}/versions",
            json={"calculation": calculation},
        )
        assert version.status_code == 201
        version_data = version.json()
        assert version_data["version_number"] == 1
        assert version_data["calculation_result"]["trace_id"]

        report = client.get(
            f"/api/v1/projects/{project_id}/versions/{version_data['id']}/report.pdf"
        )
        assert report.status_code == 200
        assert report.headers["content-type"] == "application/pdf"
        assert report.content.startswith(b"%PDF")

        foundation_scenario = next(
            item for item in scenarios.json() if item["module"] == "spread_footing"
        )
        foundation_calculation = {
            "schema_version": "3.2",
            "mode": "quick",
            "module": foundation_scenario["module"],
            "project_name": foundation_scenario["title"],
            "standard_profile": "CN-2024",
            "confirmed_assumptions": True,
            "inputs": foundation_scenario["inputs"],
            "loads": foundation_scenario["loads"],
        }
        revision = client.post(
            f"/api/v2/projects/{project_id}/revisions",
            json={
                "calculations": [
                    {
                        "node_id": "beam",
                        "label": "上部钢梁",
                        "calculation": calculation,
                    },
                    {
                        "node_id": "footing",
                        "label": "独立基础",
                        "calculation": foundation_calculation,
                    },
                ],
                "connections": [
                    {
                        "source_node_id": "beam",
                        "target_node_id": "footing",
                        "support": "left",
                    }
                ],
            },
        )
        assert revision.status_code == 201, revision.text
        revision_data = revision.json()
        footing_input = revision_data["snapshot"]["calculations"][1]["calculation"]
        assert footing_input["inputs"]["reaction_source_node_id"] == "beam"
        assert revision_data["result_bundle"]["footing"]["trace_id"]
        revision_report = client.get(
            f"/api/v2/projects/{project_id}/revisions/{revision_data['id']}/report.pdf"
        )
        assert revision_report.status_code == 200
        assert revision_report.content.startswith(b"%PDF")

        invited = client.post(
            "/api/v1/auth/users",
            json={
                "username": "guest",
                "display_name": "受邀成员",
                "temporary_password": "Guest-Temp-12345",
                "is_admin": False,
            },
        )
        assert invited.status_code == 201
        assert client.post("/api/v1/auth/logout").status_code == 204

        assert (
            client.post(
                "/api/v1/auth/login",
                json={"username": "guest", "password": "Guest-Temp-12345"},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/auth/change-password",
                json={
                    "current_password": "Guest-Temp-12345",
                    "new_password": "Guest-Changed-12345",
                },
            ).status_code
            == 204
        )
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"username": "guest", "password": "Guest-Changed-12345"},
            ).status_code
            == 200
        )
        assert client.get("/api/v1/projects").json() == []
        assert client.get(f"/api/v1/projects/{project_id}").status_code == 404
