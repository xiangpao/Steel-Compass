from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.auth import require_ready_user
from app.core.errors import CalculationInputError
from app.core.schemas import (
    CalculationMode,
    CalculationModule,
    CalculationRequest,
    TypedInputValue,
    TypedModuleInputs,
)
from app.routers.calculation_routes import router


def q(value: float, unit: str) -> dict[str, float | str]:
    return {"value": value, "unit": unit}


@pytest.fixture()
def client() -> Iterator[TestClient]:
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v2")
    test_app.dependency_overrides[require_ready_user] = lambda: object()

    @test_app.exception_handler(CalculationInputError)
    async def handle_input_error(
        _: Request, exc: CalculationInputError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})

    with TestClient(test_app) as api:
        yield api


def _request(module: str, typed_inputs: dict) -> dict:
    return {
        "schema_version": "3.3",
        "mode": "quick",
        "module": module,
        "project_name": f"nextgen-{module}",
        "standard_profile": "CN-2024",
        "typed_inputs": typed_inputs,
        "loads": [],
    }


def _continuous() -> dict:
    return {
        "module": "continuous_beam",
        "combination_id": "ULS-1",
        "combination_name": "ULS 均布荷载",
        "limit_state": "ULS",
        "nodes": ["A", "B"],
        "spans": [
            {
                "id": "S1",
                "start": "A",
                "end": "B",
                "length": q(4, "m"),
                "elastic_modulus": q(200, "GPa"),
                "inertia": q(80_000_000, "mm4"),
                "uniform_load_local_y": q(-5, "kN/m"),
                "moment_capacity": q(200, "kN·m"),
                "shear_capacity": q(200, "kN"),
            }
        ],
        "supports": [
            {"node": "A", "vertical": True, "rotation": False},
            {"node": "B", "vertical": True, "rotation": False},
        ],
        "nodal_loads": [],
        "deflection_limit": q(30, "mm"),
    }


def _frame() -> dict:
    return {
        "module": "planar_frame",
        "combination_id": "ULS-1",
        "combination_name": "ULS 节点荷载",
        "limit_state": "ULS",
        "nodes": [
            {"id": "A", "x": q(0, "m"), "y": q(0, "m")},
            {"id": "B", "x": q(0, "m"), "y": q(3, "m")},
        ],
        "members": [
            {
                "id": "C1",
                "start": "A",
                "end": "B",
                "area": q(5000, "mm2"),
                "inertia": q(80_000_000, "mm4"),
                "elastic_modulus": q(200, "GPa"),
                "axial_capacity": q(1000, "kN"),
                "shear_capacity": q(300, "kN"),
                "moment_capacity": q(300, "kN·m"),
            }
        ],
        "restraints": [{"node": "A", "ux": True, "uy": True, "rz": True}],
        "nodal_loads": [
            {
                "node": "B",
                "force_x": q(5, "kN"),
                "force_y": q(-10, "kN"),
                "moment_z": q(0, "kN·m"),
            }
        ],
        "uniform_loads": [],
        "displacement_limit": q(30, "mm"),
    }


def _truss() -> dict:
    member = lambda id_, start, end: {
        "id": id_,
        "start": start,
        "end": end,
        "area": q(2000, "mm2"),
        "elastic_modulus": q(200, "GPa"),
        "axial_capacity": q(500, "kN"),
    }
    return {
        "module": "planar_truss",
        "combination_id": "ULS-1",
        "combination_name": "ULS 节点荷载",
        "limit_state": "ULS",
        "nodes": [
            {"id": "A", "x": q(0, "m"), "y": q(0, "m")},
            {"id": "B", "x": q(4, "m"), "y": q(0, "m")},
            {"id": "C", "x": q(2, "m"), "y": q(3, "m")},
        ],
        "members": [member("AB", "A", "B"), member("AC", "A", "C"), member("BC", "B", "C")],
        "restraints": [
            {"node": "A", "ux": True, "uy": True},
            {"node": "B", "ux": False, "uy": True},
        ],
        "nodal_loads": [
            {"node": "C", "force_x": q(0, "kN"), "force_y": q(-10, "kN")}
        ],
        "displacement_limit": q(20, "mm"),
    }


def _slab() -> dict:
    return {
        "module": "two_way_slab",
        "combination_id": "ULS-1",
        "combination_name": "ULS 面荷载",
        "limit_state": "ULS",
        "short_span": q(4, "m"),
        "long_span": q(5, "m"),
        "thickness": q(180, "mm"),
        "elastic_modulus": q(30, "GPa"),
        "uniform_load": q(5, "kN/m2"),
        "support_condition": "four_edges_simply_supported",
        "poisson_ratio": 0.2,
        "short_direction_moment_capacity": q(80, "kN·m/m"),
        "long_direction_moment_capacity": q(80, "kN·m/m"),
        "deflection_limit": q(25, "mm"),
    }


def _effect() -> dict:
    return {
        "combination_id": "ULS-1",
        "combination_name": "ULS 风主导",
        "limit_state": "ULS",
        "axial": q(-20, "kN"),
        "shear_x": q(5, "kN"),
        "shear_y": q(0, "kN"),
        "moment_x": q(2, "kN·m"),
        "moment_y": q(1, "kN·m"),
        "torsion": q(0, "kN·m"),
    }


def _positions() -> list[dict]:
    return [
        {"x": q(-75, "mm"), "y": q(-75, "mm")},
        {"x": q(75, "mm"), "y": q(-75, "mm")},
        {"x": q(75, "mm"), "y": q(75, "mm")},
        {"x": q(-75, "mm"), "y": q(75, "mm")},
    ]


def _timber_connection() -> dict:
    return {
        "module": "timber_connection",
        "post_width": q(180, "mm"),
        "post_depth": q(180, "mm"),
        "plate_width": q(300, "mm"),
        "plate_depth": q(300, "mm"),
        "fastener_diameter": q(12, "mm"),
        "fastener_positions": _positions(),
        "connector_standoff": q(40, "mm"),
        "effects": [_effect()],
        "bearing_design_capacity": q(200, "kN"),
        "fastener_tension_design_capacity": q(30, "kN"),
        "fastener_shear_design_capacity": q(20, "kN"),
        "connector_bending_design_capacity": q(1, "kN·m"),
        "minimum_spacing": q(48, "mm"),
        "minimum_edge_distance": q(48, "mm"),
    }


def _wall_anchor() -> dict:
    return {
        "module": "wall_anchor",
        "plate_width": q(300, "mm"),
        "plate_height": q(300, "mm"),
        "plate_thickness": q(14, "mm"),
        "rebar_count": q(4, "1"),
        "rebar_rows": q(2, "1"),
        "rebar_diameter": q(16, "mm"),
        "rebar_fy": q(360, "MPa"),
        "rebar_length": q(600, "mm"),
        "bent_rebar_count": q(0, "1"),
        "bent_rebar_diameter": q(0, "mm"),
        "bent_rebar_angle": q(45, "deg"),
        "concrete_fc": q(14.3, "MPa"),
        "concrete_ft": q(1.43, "MPa"),
        "edge_distance_x": q(60, "mm"),
        "edge_distance_y": q(60, "mm"),
        "n_design": q(20, "kN"),
        "m_design": q(10, "kN*m"),
        "v_design": q(30, "kN"),
    }


CASES = [
    ("continuous_beam", _continuous),
    ("planar_frame", _frame),
    ("planar_truss", _truss),
    ("two_way_slab", _slab),
    ("timber_connection", _timber_connection),
    ("wall_anchor", _wall_anchor),
]


@pytest.mark.parametrize(("module", "factory"), CASES)
def test_new_modules_run_through_calculation_api(
    client: TestClient, module: str, factory
) -> None:
    response = client.post("/api/v2/calculate", json=_request(module, factory()))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["module"] == module
    assert result["verification_status"] == "unverified"
    if module != "wall_anchor":
        assert result["combinations"]
    assert result["checks"]
    assert result["steps"]
    assert result["applicability"]
    assert result["schema_version"] == "3.3"
    if module == "wall_anchor":
        assert any("GB 50010" in standard for standard in result["standards"])


def test_openapi_exposes_module_discriminator() -> None:
    schema = CalculationRequest.model_json_schema()
    typed = schema["properties"]["typed_inputs"]["anyOf"][0]
    assert typed["discriminator"]["propertyName"] == "module"
    mapping = typed["discriminator"]["mapping"]
    assert {module for module, _ in CASES} <= mapping.keys()
    assert mapping["continuous_beam"].endswith("ContinuousBeamInputs")
    assert mapping["wall_anchor"].endswith("WallAnchorInputs")


def test_invalid_nested_unit_returns_structured_422(client: TestClient) -> None:
    typed = _continuous()
    typed["spans"][0]["length"] = q(4, "kg")
    response = client.post(
        "/api/v2/calculate", json=_request("continuous_beam", typed)
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_unit"
    assert error["field"] == "spans.S1.length"


def test_new_module_cannot_use_legacy_values_shape(client: TestClient) -> None:
    response = client.post(
        "/api/v2/calculate",
        json=_request(
            "continuous_beam",
            {"module": "continuous_beam", "values": {"span_m": q(4, "m")}},
        ),
    )
    assert response.status_code == 422


def test_existing_schema32_typed_values_and_schema31_read_remain_compatible() -> None:
    current = CalculationRequest(
        schema_version="3.3",
        mode=CalculationMode.QUICK,
        module=CalculationModule.STEEL_BEAM,
        typed_inputs=TypedModuleInputs(
            module=CalculationModule.STEEL_BEAM,
            values={"span_m": TypedInputValue(value=4, unit="m")},
        ),
        loads=[],
    )
    assert current.inputs["span_m"] == 4
    assert current.typed_inputs is not None

    legacy = CalculationRequest(
        schema_version="3.1",
        mode=CalculationMode.QUICK,
        module=CalculationModule.STEEL_BEAM,
        inputs={"span_m": 4},
        loads=[],
    )
    assert legacy.schema_version == "3.1"
    assert legacy.inputs["span_m"] == 4
