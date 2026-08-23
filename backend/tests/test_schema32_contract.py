from io import BytesIO

from pypdf import PdfReader

from app.api_schemas import SceneRevisionCreate
from app.core.scene_schemas import SceneLoadItem
from app.core.foundation import _groundwater_depth, _groundwater_inputs_complete
from app.core.schemas import (
    CalculationMode,
    CalculationModule,
    CalculationRequest,
    CalculationResult,
    LoadItem,
    LoadKind,
    TypedInputValue,
    TypedModuleInputs,
)
from app.core.standards import standard_profile
from app.report import build_calculation_pdf


def test_schema32_request_needs_no_confirmation_fields() -> None:
    request = CalculationRequest(
        schema_version="3.3",
        mode=CalculationMode.QUICK,
        module=CalculationModule.STEEL_BEAM,
        typed_inputs=TypedModuleInputs(
            module=CalculationModule.STEEL_BEAM,
            values={"span_m": TypedInputValue(value=3.0, unit="m")},
        ),
        loads=[
            LoadItem(
                kind=LoadKind.DEAD,
                value=1.0,
                unit="kN/m",
                source="project input",
            )
        ],
    )

    dumped = request.model_dump(mode="json")
    assert "confirmed_assumptions" not in dumped
    assert "confirmed" not in dumped["loads"][0]
    assert "confirmed_input_nodes" not in SceneRevisionCreate.model_json_schema()[
        "properties"
    ]


def test_schema32_defaults_to_versioned_standard_profile_and_reads_legacy() -> None:
    current = CalculationRequest(
        schema_version="3.3",
        mode=CalculationMode.QUICK,
        module=CalculationModule.STEEL_BEAM,
    )
    legacy = CalculationRequest(
        schema_version="3.1",
        standard_profile="CN-2024",
        mode=CalculationMode.QUICK,
        module=CalculationModule.STEEL_BEAM,
    )

    assert current.standard_profile == "CN-2026.6"
    assert legacy.standard_profile == "CN-2024"

    profile = standard_profile()
    assert profile["profile"] == "CN-2026.6"
    assert profile["mapping_status"] == "module_scoped"
    assert any(item["code"] == "GB 55003-2021" for item in profile["standards"])


def test_scene_load_serialization_drops_legacy_confirmation() -> None:
    item = SceneLoadItem.model_validate(
        {
            "id": "dead-1",
            "label": "dead load",
            "kind": "dead",
            "value_type": "fixed",
            "recommended_default": 1.0,
            "adopted_value": 1.0,
            "unit": "kN/m2",
            "source_reference": "project input",
            "applicable_when": "always",
            "distribution": "area",
            "direction": "gravity",
            "application_target": "roof",
            "confirmed": True,
        }
    )

    assert "confirmed" not in item.model_dump(mode="json")


def _foundation_request(**inputs: object) -> CalculationRequest:
    return CalculationRequest(
        schema_version="3.3",
        mode=CalculationMode.PROFESSIONAL,
        module=CalculationModule.SPREAD_FOOTING,
        inputs=dict(inputs),
        loads=[
            LoadItem(
                kind=LoadKind.DEAD,
                value=100,
                unit="kN",
                source="project load schedule",
            )
        ],
    )


def test_groundwater_condition_replaces_confirmation_boolean() -> None:
    dry = _foundation_request(
        groundwater_condition="no_influence",
        groundwater_source="geotechnical report p.12",
        soil_source="geotechnical report p.8",
    )
    dry_known, dry_depth = _groundwater_depth(dry)
    assert dry_known is True
    assert dry_depth is None
    assert _groundwater_inputs_complete(dry, dry_known, dry_depth, "report")

    known = _foundation_request(
        groundwater_condition="known_water_table",
        water_table_depth_m=1.2,
        groundwater_source="monitoring record",
        soil_source="geotechnical report",
    )
    known_flag, known_depth = _groundwater_depth(known)
    assert known_flag is True
    assert known_depth == 1.2
    assert _groundwater_inputs_complete(known, known_flag, known_depth, "report")

    unknown = _foundation_request(
        groundwater_condition="unknown",
        groundwater_source="",
        soil_source="geotechnical report",
    )
    unknown_flag, unknown_depth = _groundwater_depth(unknown)
    assert unknown_flag is False
    assert unknown_depth is None
    assert not _groundwater_inputs_complete(
        unknown, unknown_flag, unknown_depth, "report"
    )


def _result(schema_version: str) -> CalculationResult:
    return CalculationResult(
        schema_version=schema_version,
        trace_id="schema32-trace",
        project_name="schema32",
        module=CalculationModule.STEEL_BEAM,
        mode=CalculationMode.QUICK,
        status="passed",
        standards=[],
        input_summary={},
        combinations=[],
        checks=[],
        disclaimer="LEGACY_DISCLAIMER_MARKER",
    )


def _pdf_text(result: CalculationResult) -> str:
    pdf = build_calculation_pdf(result, "SCHEMA32")
    return "".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)


def test_new_pdf_omits_generic_disclaimer_but_legacy_pdf_remains_readable() -> None:
    current = _result("3.3")
    assert "disclaimer" not in current.model_dump(mode="json")
    assert "LEGACY_DISCLAIMER_MARKER" not in _pdf_text(current)
    assert "LEGACY_DISCLAIMER_MARKER" in _pdf_text(_result("3.1"))
