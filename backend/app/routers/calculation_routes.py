from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth import require_ready_user
from ..api_schemas import CustomSectionCreateRequest
from ..core import STANDARD_PROFILE
from ..core.catalogs import climate_catalog, load_catalog, material_catalog
from ..core.engine import calculate
from ..core.scenarios import SCENARIOS
from ..core.schemas import (
    CalculationRequest,
    CalculationResult,
    ScenarioTemplate,
    require_current_request_schema,
)
from ..core.standards import standard_profile
from ..core.standard_trace import pergola_verification_source_catalog
from ..core.site_profile import climate_region_catalog, seismic_design_catalog
from ..core.design_profiles import (
    calculate_custom_section,
    foundation_form_catalog,
    foundation_system_catalog,
    geotechnical_hint_catalog,
    rebar_catalog,
    roof_assembly_catalog,
    soil_preset_catalog,
    steel_grade_catalog,
    steel_section_catalog,
)
from ..models import User


router = APIRouter(tags=["calculations"])


@router.get("/scenarios", response_model=list[ScenarioTemplate])
def list_scenarios(_: User = Depends(require_ready_user)) -> list[ScenarioTemplate]:
    return SCENARIOS


@router.post("/calculate", response_model=CalculationResult)
def run_calculation(
    payload: CalculationRequest,
    _: User = Depends(require_ready_user),
) -> CalculationResult:
    require_current_request_schema(payload)
    return calculate(payload)


@router.get("/standards")
def standards(_: User = Depends(require_ready_user)) -> dict:
    return standard_profile(STANDARD_PROFILE)


@router.get("/catalogs/materials")
def materials(_: User = Depends(require_ready_user)) -> dict:
    return material_catalog()


@router.get("/catalogs/load-presets")
def load_presets(_: User = Depends(require_ready_user)) -> dict:
    return load_catalog()


@router.get("/catalogs/climate-locations")
def climate_locations(
    query: str = Query(default="", max_length=80),
    _: User = Depends(require_ready_user),
) -> dict:
    return climate_catalog(query)


@router.get("/catalogs/climate-regions")
def climate_regions(_: User = Depends(require_ready_user)) -> dict:
    return climate_region_catalog()


@router.get("/catalogs/seismic-design-profiles")
def seismic_profiles(_: User = Depends(require_ready_user)) -> dict:
    return seismic_design_catalog()


@router.get("/catalogs/steel-sections")
def steel_sections(_: User = Depends(require_ready_user)) -> dict:
    return steel_section_catalog()


@router.post("/catalogs/custom-section-properties")
def custom_section_properties(
    payload: CustomSectionCreateRequest,
    _: User = Depends(require_ready_user),
) -> dict:
    return calculate_custom_section(payload, section_id=payload.id).model_dump(mode="json")


@router.get("/catalogs/geotechnical-hints")
def geotechnical_hints(_: User = Depends(require_ready_user)) -> dict:
    return geotechnical_hint_catalog()


@router.get("/catalogs/foundation-systems")
def foundation_systems(_: User = Depends(require_ready_user)) -> dict:
    return foundation_system_catalog()


@router.get("/catalogs/steel-grades")
def steel_grades(_: User = Depends(require_ready_user)) -> dict:
    return steel_grade_catalog()


@router.get("/catalogs/roof-assemblies")
def roof_assemblies(_: User = Depends(require_ready_user)) -> dict:
    return roof_assembly_catalog()


@router.get("/catalogs/rebar")
def rebar(_: User = Depends(require_ready_user)) -> dict:
    return rebar_catalog()


@router.get("/catalogs/soil-presets")
def soil_presets(_: User = Depends(require_ready_user)) -> dict:
    return soil_preset_catalog()


@router.get("/catalogs/foundation-forms")
def foundation_forms(_: User = Depends(require_ready_user)) -> dict:
    return foundation_form_catalog()


@router.get("/catalogs/pergola-verification-sources")
def pergola_verification_sources(_: User = Depends(require_ready_user)) -> dict:
    return pergola_verification_source_catalog()
