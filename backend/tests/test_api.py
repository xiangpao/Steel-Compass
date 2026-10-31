from __future__ import annotations

import os
import pytest
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
        climate_regions = client.get("/api/v2/catalogs/climate-regions")
        assert climate_regions.status_code == 200
        assert {item["id"] for item in climate_regions.json()["items"]} == {
            "zhejiang_coastal", "zhejiang_inland", "zhejiang_mountain", "manual"
        }
        seismic_profiles = client.get("/api/v2/catalogs/seismic-design-profiles")
        assert seismic_profiles.status_code == 200
        assert len(seismic_profiles.json()["items"]) == 6
        assert client.get("/api/v2/catalogs/steel-sections").status_code == 200
        assert client.get("/api/v2/catalogs/geotechnical-hints").status_code == 200
        assert client.get("/api/v2/catalogs/foundation-systems").status_code == 200
        assert client.get("/api/v2/catalogs/steel-grades").status_code == 200
        assert client.get("/api/v2/catalogs/roof-assemblies").status_code == 200
        assert client.get("/api/v2/catalogs/rebar").status_code == 200
        assert client.get("/api/v2/catalogs/soil-presets").status_code == 200
        assert client.get("/api/v2/catalogs/foundation-forms").status_code == 200
        verification_sources = client.get("/api/v2/catalogs/pergola-verification-sources")
        assert verification_sources.status_code == 200
        covered_standards = " ".join(
            item["standard"] for item in verification_sources.json()["formula_sources"]
        )
        assert all(code in covered_standards for code in ("GB 55006", "GB 50017", "GB 50009", "GB 55002", "GB/T 50011", "GB 55003", "GB 50007", "GB 55008", "GB/T 50010", "22G101-3"))
        scenario = scenarios.json()[0]
        calculation = {
            "schema_version": "3.3",
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
            json={
                "name": "API 集成测试",
                "description": "版本不可变",
                    "site_profile": {
                    "region_preset": "zhejiang_inland",
                    "recurrence_period_years": 50,
                    "basic_wind_pressure_kpa": 0.45,
                    "basic_snow_pressure_kpa": 0.55,
                    "climate_source_reference": "GB 50009-2012 表 E.5",
                    "terrain_category": "B",
                    "structure_shape": "open_frame",
                    "roof_form": "flat",
                        "seismic_level": "7_010g",
                    },
                    "geotechnical_profile": {
                        "stage": "scheme_estimate",
                        "regional_hint_id": "zj-inland-alluvial",
                        "confirmed_soil_class": "可塑黏性土",
                        "bearing_capacity_kpa": 100,
                        "bearing_capacity_source": "区域参考档，用户确认",
                        "groundwater": {
                            "condition": "no_influence",
                            "source": "现场资料确认无影响",
                        },
                    },
            },
        )
        assert project.status_code == 201
        project_id = project.json()["id"]
        calculated_section = client.post(
            "/api/v2/catalogs/custom-section-properties",
            json={
                "id": "project-rhs-calculated",
                "name": "项目矩形管",
                "family": "RHS",
                "dimensions": {"h_mm": 200, "b_mm": 100, "t_mm": 6},
            },
        )
        assert calculated_section.status_code == 200, calculated_section.text
        assert calculated_section.json()["area_mm2"] == pytest.approx(3456)
        custom_sections = client.put(
            f"/api/v2/projects/{project_id}/custom-sections",
            json={"items": [{
                "id": "project-rhs-1", "name": "Project RHS", "family": "RHS",
                "dimensions": {"h_mm": 180, "b_mm": 100, "t_mm": 6},
                "area_mm2": 3216, "iy_mm4": 15000000, "iz_mm4": 6500000,
                "torsion_mm4": 9000000, "self_weight_kn_m": 0.252,
                "source_reference": "project geometry calculation",
            }]},
        )
        assert custom_sections.status_code == 200, custom_sections.text
        assert client.get(f"/api/v2/projects/{project_id}/custom-sections").json()["items"][0]["id"] == "project-rhs-1"
        assert client.get(f"/api/v2/projects/{project_id}/site-profile").json()["seismic_level"] == "7_010g"
        duplicate_project = client.post(f"/api/v2/projects/{project_id}/duplicate")
        assert duplicate_project.status_code == 200
        assert duplicate_project.json()["site_profile"]["region_preset"] == "zhejiang_inland"
        assert duplicate_project.json()["geotechnical_profile"]["bearing_capacity_kpa"] == 100

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
        analysis_instance = client.post(
            f"/api/v2/projects/{project_id}/scene-instances",
            json={
                "family_id": "pergola-pavilion",
                "variant_id": "guided-grid",
                    "title": "Geometry 2.3 分析接口测试",
                "mode": "quick",
            },
        )
        assert analysis_instance.status_code == 201, analysis_instance.text
        analysis_instance_id = analysis_instance.json()["id"]
        analysis_geometry = {
                "profile_version": "2.3",
            "layout_mode": "custom_grid",
            "nodes": [
                {"id": "B1", "x_m": 0, "y_m": 0, "z_m": 0},
                {"id": "T1", "x_m": 0, "y_m": 0, "z_m": 3},
                {"id": "B2", "x_m": 4, "y_m": 0, "z_m": 0},
                    {"id": "T2", "x_m": 4, "y_m": 0, "z_m": 3},
                    {"id": "T3", "x_m": 4, "y_m": 1, "z_m": 3},
            ],
            "members": [
                {"id": "C1", "start_node_id": "B1", "end_node_id": "T1", "role": "column", "group_id": "columns"},
                {"id": "C2", "start_node_id": "B2", "end_node_id": "T2", "role": "column", "group_id": "columns"},
                    {"id": "M1", "start_node_id": "T1", "end_node_id": "T2", "role": "beam", "group_id": "beams"},
                    {"id": "M2", "start_node_id": "T2", "end_node_id": "T3", "role": "beam", "group_id": "beams"},
            ],
            "member_types": [
                {"id": "columns", "mark_prefix": "C", "title": "柱", "role": "column", "material_grade": "Q355B", "section_id": "shs-150x6"},
                {"id": "beams", "mark_prefix": "M", "title": "主梁", "role": "beam", "material_grade": "Q355B", "section_id": "rhs-200x100x6"},
            ],
            "member_instances": [
                {"member_id": "C1", "member_type_id": "columns", "mark": "C01"},
                {"member_id": "C2", "member_type_id": "columns", "mark": "C02"},
                    {"member_id": "M1", "member_type_id": "beams", "mark": "M01"},
                    {"member_id": "M2", "member_type_id": "beams", "mark": "M02"},
            ],
            "supports": [
                {"id": "S1", "node_id": "B1", "restraint": "fixed", "foundation_id": "FI1"},
                {"id": "S2", "node_id": "B2", "restraint": "fixed", "foundation_id": "FI2"},
            ],
            "foundation_types": [
                    {"id": "fa", "mark": "F-A", "title": "等厚基础", "form_id": "spread-prismatic", "length_m": 1.8, "width_m": 1.5, "thickness_mm": 450, "embedment_m": 1.1, "concrete_grade": "C30", "rebar_grade": "HRB400", "bottom_x": "Phi14@150", "bottom_y": "Phi12@150", "cover_mm": 50, "pedestal": {"enabled": True, "auto_enabled": True, "length_mm": 500, "width_mm": 500, "clear_height_mm": 650, "top_elevation_m": 0, "bottom_elevation_m": -0.65, "concrete_grade": "C30", "cover_mm": 40, "longitudinal_bar_count_x": 2, "longitudinal_bar_count_y": 2, "longitudinal_bar_diameter_mm": 16, "stirrup_diameter_mm": 8, "stirrup_spacing_mm": 150, "confinement_spacing_mm": 90, "dowel_anchorage_mm": 700, "splice_type": "lap", "top_local_reinforcement": True}}
            ],
            "foundation_instances": [
                {"id": "FI1", "support_id": "S1", "foundation_type_id": "fa", "mark": "F-A-01", "column_member_id": "C1"},
                {"id": "FI2", "support_id": "S2", "foundation_type_id": "fa", "mark": "F-A-02", "column_member_id": "C2"},
            ],
            "connection_types": [
                {"id": "base", "mark": "J-A", "title": "柱脚", "family": "column_base", "behavior": "rigid"},
                {"id": "frame", "mark": "J-B", "title": "矩形管梁柱全周焊接节点", "family": "beam_column", "behavior": "rigid", "supported_section_families": ["SHS", "RHS"], "parameters": {"connection_form": "rhs_full_perimeter_weld", "weld_throat_mm": 8, "stiffener_thickness_mm": 8}},
            ],
            "connection_instances": [
                {"id": "J1", "mark": "J-A-01", "connection_type_id": "base", "node_id": "B1", "member_ids": ["C1"], "status": "defined"},
                {"id": "J2", "mark": "J-A-02", "connection_type_id": "base", "node_id": "B2", "member_ids": ["C2"], "status": "defined"},
                {"id": "J3", "mark": "J-B-01", "connection_type_id": "frame", "node_id": "T1", "member_ids": ["C1", "M1"], "status": "defined"},
                    {"id": "J4", "mark": "J-B-02", "connection_type_id": "frame", "node_id": "T2", "member_ids": ["C2", "M1"], "status": "defined"},
                    {"id": "J5", "mark": "J-B-03", "connection_type_id": "frame", "node_id": "T2", "member_ids": ["C2", "M2"], "status": "defined"},
            ],
                "column_bases": [
                    {"id": "CB1", "column_member_id": "C1", "support_id": "S1", "connection_instance_id": "J1", "base_plate_length_mm": 360, "base_plate_width_mm": 360, "base_plate_thickness_mm": 24, "anchor_grade": "5.8", "anchor_diameter_mm": 24, "anchor_count": 4, "anchor_embedment_mm": 600, "anchor_spacing_mm": 260, "anchor_edge_mm": 50, "anchor_head_diameter_mm": 60, "weld_throat_mm": 8, "concrete_bearing_capacity_mpa": 10},
                        {"id": "CB2", "column_member_id": "C2", "support_id": "S2", "connection_instance_id": "J2", "base_plate_length_mm": 360, "base_plate_width_mm": 360, "base_plate_thickness_mm": 24, "anchor_grade": "5.8", "anchor_diameter_mm": 24, "anchor_count": 4, "anchor_embedment_mm": 600, "anchor_spacing_mm": 260, "anchor_edge_mm": 50, "anchor_head_diameter_mm": 60, "weld_throat_mm": 8, "concrete_bearing_capacity_mpa": 10},
                ],
                "roof_surfaces": [
                    {"id": "R1", "node_ids": ["T1", "T2", "T3"], "form": "flat", "load_path_group_ids": ["beams"], "load_direction_deg": 0}
                ],
                "roof_load_zones": [
                    {"id": "Z1", "surface_id": "R1", "boundary_node_ids": ["T1", "T2", "T3"], "roof_assembly_id": "steel-panel", "load_path_group_ids": ["beams"], "load_direction_deg": 0}
                ],
                "source": "API analysis test",
        }
        saved_analysis_geometry = client.put(
            f"/api/v2/projects/{project_id}/scene-instances/{analysis_instance_id}/geometry",
            json=analysis_geometry,
        )
        assert saved_analysis_geometry.status_code == 200, saved_analysis_geometry.text
        analysis_response = client.post(
            f"/api/v2/projects/{project_id}/scene-instances/{analysis_instance_id}/analyze",
            json={
                "stage": "scheme_estimate",
                "roof_load_selection": {
                    "roof_assembly_id": "steel-panel",
                    "maintenance_category": "maintenance",
                },
                "load_cases": [{
                    "id": "analysis-dead",
                    "label": "分析测试恒载",
                    "kind": "dead",
                    "value_type": "project_defined",
                    "adopted_value": 0.5,
                    "unit": "kN/m2",
                    "source_reference": "API test fixture",
                    "applicable_when": "test",
                    "distribution": "area",
                    "direction": "gravity",
                    "application_target": "roof_members",
                }],
            },
        )
        assert analysis_response.status_code == 200, analysis_response.text
        analysis_package = analysis_response.json()
        assert analysis_package["workflow_status"] == "incomplete"
        assert analysis_package["structural_analysis"]["status"] == "complete"
        assert len(analysis_package["structural_analysis"]["reactions"]) == 2
        assert analysis_package["structural_analysis"]["balance_checks"][0]["balanced"] is True
        assert analysis_package["connection_checks"]["status"] == "incomplete"
        assert analysis_package["connection_checks"]["items"][0]["checks"]
        assert analysis_package["connection_checks"]["items"][0]["verification_status"] == "unverified"
        beam_column_check = next(item for item in analysis_package["connection_checks"]["items"] if item["connection_id"] == "J3")
        assert beam_column_check["checks"]
        assert beam_column_check["beam_member_id"] == "M1"
        assert analysis_package["foundation_checks"]["items"][0]["status"] in {"incomplete", "failed"}
        assert analysis_package["foundation_checks"]["items"][0]["checks"]
        assert analysis_package["foundation_checks"]["items"][0]["support_node_id"] == "B1"
        assert analysis_package["foundation_checks"]["items"][0]["verification_status"] == "unverified"
        assert analysis_package["foundation_checks"]["items"][0]["pedestal_check"]["checks"]
        assert analysis_package["foundation_checks"]["items"][0]["pedestal_check"]["verification_status"] == "unverified"
        assert "基础沉降计算需要分层压缩参数、经验系数和允许值" in analysis_package["trace"]["unsupported_capabilities"]
        assert "外部YJK/PKPM数值对照证据尚未导入" in analysis_package["trace"]["unsupported_capabilities"]
        snapshots = client.get(
            f"/api/v2/projects/{project_id}/scene-instances/{analysis_instance_id}/analysis-snapshots"
        )
        assert snapshots.status_code == 200, snapshots.text
        assert len(snapshots.json()) == 1
        assert "snapshot" not in snapshots.json()[0]
        assert snapshots.json()[0]["id"] == analysis_package["snapshot_id"]
        snapshot_record = client.get(
            f"/api/v2/projects/{project_id}/scene-instances/{analysis_instance_id}/analysis-snapshots/{analysis_package['snapshot_id']}"
        ).json()
        listed = client.get(f"/api/v2/projects/{project_id}/scene-instances").json()
        listed_draft = next(item for item in listed if item["id"] == analysis_instance_id)["draft_state"]
        assert listed_draft["last_analysis_package"] is None
        assert listed_draft["last_analysis_snapshot_id"] == analysis_package["snapshot_id"]
        assert snapshot_record["snapshot"]["snapshot_schema_version"] == "4.0"
        assert snapshot_record["snapshot"]["standard_profile"] == "CN-2026.7"
        assert len(snapshot_record["snapshot"]["content_hash"]) == 64
        snapshot_id = snapshot_record["id"]
        report = client.get(
            f"/api/v2/projects/{project_id}/scene-instances/{analysis_instance_id}/analysis-snapshots/{snapshot_id}/report.pdf"
        )
        assert report.status_code == 200, report.text
        assert report.headers["content-type"] == "application/pdf"
        assert report.content.startswith(b"%PDF")
        foundation_candidates = client.post(
            f"/api/v2/projects/{project_id}/scene-instances/{analysis_instance_id}/foundation-candidates",
            json={"foundation_instance_id": "FI1"},
        )
        assert foundation_candidates.status_code == 200, foundation_candidates.text
        foundation_candidate = foundation_candidates.json()
        assert foundation_candidate["converged"] is True
        assert foundation_candidate["target_node_id"] == "FI1"
        assert foundation_candidate["recommended"]["column_reaction_n_kn"] > 0
        assert "冲切" in foundation_candidate["recommended"]["pending_checks"]

        resaved_analysis_geometry = client.put(
            f"/api/v2/projects/{project_id}/scene-instances/{analysis_instance_id}/geometry",
            json=analysis_geometry,
        )
        assert resaved_analysis_geometry.status_code == 200
        stale_foundation_candidates = client.post(
            f"/api/v2/projects/{project_id}/scene-instances/{analysis_instance_id}/foundation-candidates",
            json={"foundation_instance_id": "FI1"},
        )
        assert stale_foundation_candidates.status_code == 422
        assert stale_foundation_candidates.json()["detail"]["code"] == "missing_saved_analysis"
        geometry = {
            "layout_mode": "custom_grid",
            "axes": [
                {"id": "X", "direction": "x", "positions_m": [0, 4]},
                {"id": "Y", "direction": "y", "positions_m": [0, 3]},
            ],
            "nodes": [
                {"id": "B1", "x_m": 0, "y_m": 0, "z_m": 0, "support": "fixed"},
                {"id": "T1", "x_m": 0, "y_m": 0, "z_m": 3},
            ],
            "members": [{"id": "C1", "start_node_id": "B1", "end_node_id": "T1", "role": "column", "group_id": "columns"}],
            "roof_surfaces": [],
            "source": "API guided grid test",
        }
        saved_geometry = client.put(
            f"/api/v2/projects/{project_id}/scene-instances/{gravity_scene_id}/geometry",
            json=geometry,
        )
        assert saved_geometry.status_code == 200, saved_geometry.text
        validation = client.post(
            f"/api/v2/projects/{project_id}/scene-instances/{gravity_scene_id}/validate-model",
            json=geometry,
        )
        assert validation.status_code == 200, validation.text
        assert validation.json()["valid"] is True
        recommendation = client.post(
            f"/api/v2/projects/{project_id}/scene-instances/{instance_data['id']}/recommendations",
            json={"target_node_id": "foundation_left", "vertical_kn": 200, "moment_kn_m": 20},
        )
        assert recommendation.status_code == 200, recommendation.text
        assert recommendation.json()["converged"] is True
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
        assert scene_result["result_class"] == "scheme_estimate"
        assert scene_result["verification_status"] == "unverified"
        assert scene_result["load_cases"]
        assert scene_result["site_profile"]["region_preset"] == "zhejiang_inland"
        assert scene_result["seismic_action_package"]["actions"][0]["design_situation"] == "seismic"
        assert scene_result["completed_nodes"] == 1
        assert scene_result["total_required_nodes"] == 7
        assert "左柱脚 / 底板锚栓" in scene_result["missing_nodes"]
        assert scene_revision.json()["snapshot_schema_version"] == "3.9"
        assert set(scene_result["applied_conditions"]) == {"wind", "snow", "seismic"}
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
            analysis_instance_id,
        }
        all_instances = client.get(
            f"/api/v2/projects/{project_id}/scene-instances",
            params={"include_archived": True},
        ).json()
        assert {item["id"] for item in all_instances} == {
            gravity_scene_id,
            instance_data["id"],
            analysis_instance_id,
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
            "schema_version": "3.3",
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


def test_login_failures_are_rate_limited() -> None:
    from app.routers import auth_routes

    auth_routes._login_failures.clear()
    with TestClient(app) as limited:
        for _ in range(auth_routes._LOGIN_MAX_FAILURES):
            assert limited.post("/api/v1/auth/login", json={"username": "nobody", "password": "wrong"}).status_code == 401
        blocked = limited.post("/api/v1/auth/login", json={"username": "nobody", "password": "wrong"})
        assert blocked.status_code == 429
    auth_routes._login_failures.clear()
