from __future__ import annotations

from uuid import uuid4

from .baseplate import calculate_steel_baseplate_anchor
from .advanced import (
    calculate_masonry_wall,
    calculate_rc_wall,
    calculate_retaining_wall,
    calculate_steel_cantilever_post,
    calculate_timber_deck_panel,
)
from .concrete import calculate_concrete_column, calculate_concrete_member
from .errors import CalculationInputError
from .frame import calculate_portal_frame
from .foundation import calculate_spread_footing, calculate_strip_footing
from .infrastructure import (
    calculate_bridge_rc,
    calculate_bridge_steel_timber,
    calculate_pile_group_cap,
    calculate_pool_structure,
    calculate_gravity_retaining_wall,
)
from .load_environment_api import (
    calculate_load_combinations,
    calculate_soil_water_action_package,
    calculate_wind_snow_guide,
)
from .nextgen import (
    calculate_continuous_beam,
    calculate_planar_frame,
    calculate_planar_truss,
    calculate_timber_connection,
    calculate_two_way_slab,
    calculate_wall_anchor,
)
from .site_wall_api import (
    calculate_plain_masonry_wall,
    calculate_site_rc_wall,
    calculate_steel_infill_wall,
)
from .schemas import (
    CalculationMode,
    CalculationModule,
    CalculationRequest,
    CalculationResult,
    CalculationWarning,
    LoadDirection,
)
from .steel import calculate_steel_beam, calculate_steel_column
from .timber import calculate_timber_beam, calculate_timber_column


# A module may move to independently_verified only when its immutable hand
# benchmark, independent script and standard mapping are all committed.  No
# current module meets that publication gate yet.
MODULE_VERIFICATION = {
    module: "unverified" for module in CalculationModule
}


def _apply_result_contract(
    request: CalculationRequest, result: CalculationResult
) -> CalculationResult:
    verification = MODULE_VERIFICATION[request.module]
    result.verification_status = verification  # type: ignore[assignment]
    result.result_class = (
        "quick_estimate"
        if request.mode is CalculationMode.QUICK
        else "professional_check"
    )

    hard_failure = any(not check.passed for check in result.checks)
    critical_warning = any(
        warning.severity == "critical" for warning in result.warnings
    )
    result.workflow_status = "ready"
    if request.mode is CalculationMode.QUICK:
        result.quick_outcome = (
            "screening_failed"
            if hard_failure or critical_warning
            else "screening_passed"
        )
        result.engineering_status = None
        if result.status not in {"incomplete", "not_applicable"}:
            result.status = "failed" if hard_failure or critical_warning else "passed"
    else:
        result.quick_outcome = None
        if verification != "independently_verified":
            # Failed checks remain useful screening evidence, but an unverified
            # method must not emit a formal engineering failure or pass.
            result.provisional_checks = [
                check.model_copy(deep=True)
                for check in result.checks
                if not check.passed
            ]
            result.status = "incomplete"
            result.engineering_status = "incomplete"
            result.workflow_status = "capability_unavailable"
        elif hard_failure:
            result.status = "failed"
            result.engineering_status = "failed"
        elif critical_warning or result.status == "incomplete":
            result.status = "incomplete"
            result.engineering_status = "incomplete"
        elif result.status != "not_applicable":
            result.status = "passed"
            result.engineering_status = "passed"

    if (
        request.mode is CalculationMode.PROFESSIONAL
        and verification != "independently_verified"
        and not any(
            warning.code == "independent_verification_pending"
            for warning in result.warnings
        )
    ):
        result.warnings.append(
            CalculationWarning(
                severity="critical",
                code="independent_verification_pending",
                message="该模块尚未完成手算、独立脚本及规范映射验收，专业模式不得形成通过结论。",
            )
        )
    return result


def _validate_load_directions(request: CalculationRequest) -> None:
    """Reject load directions that the selected solver cannot resolve."""

    one_dimensional_modules = {
        CalculationModule.STEEL_BEAM,
        CalculationModule.STEEL_COLUMN,
        CalculationModule.CONCRETE_BEAM,
        CalculationModule.CONCRETE_SLAB,
        CalculationModule.CONCRETE_COLUMN,
        CalculationModule.SPREAD_FOOTING,
        CalculationModule.STRIP_FOOTING,
        CalculationModule.TIMBER_BEAM,
        CalculationModule.TIMBER_COLUMN,
        CalculationModule.STEEL_BASEPLATE_ANCHOR,
        CalculationModule.TIMBER_DECK_PANEL,
    }
    if request.module not in one_dimensional_modules:
        return
    invalid = [
        item
        for item in request.loads
        if item.direction
        not in {LoadDirection.GRAVITY, LoadDirection.UPLIFT}
    ]
    if invalid:
        raise CalculationInputError(
            "unsupported_load_direction",
            "当前模块只接受重力或上拔方向；水平作用必须传给可解析该方向的刚架或反力包。",
            field="loads",
            details={
                "module": request.module.value,
                "directions": sorted({item.direction.value for item in invalid}),
            },
        )


def calculate(request: CalculationRequest) -> CalculationResult:
    trace_id = str(uuid4())
    _validate_load_directions(request)
    handlers = {
        CalculationModule.STEEL_BEAM: calculate_steel_beam,
        CalculationModule.STEEL_COLUMN: calculate_steel_column,
        CalculationModule.PORTAL_FRAME: calculate_portal_frame,
        CalculationModule.CONCRETE_BEAM: calculate_concrete_member,
        CalculationModule.CONCRETE_SLAB: calculate_concrete_member,
        CalculationModule.CONCRETE_COLUMN: calculate_concrete_column,
        CalculationModule.SPREAD_FOOTING: calculate_spread_footing,
        CalculationModule.STRIP_FOOTING: calculate_strip_footing,
        CalculationModule.TIMBER_BEAM: calculate_timber_beam,
        CalculationModule.TIMBER_COLUMN: calculate_timber_column,
        CalculationModule.STEEL_BASEPLATE_ANCHOR: calculate_steel_baseplate_anchor,
        CalculationModule.TIMBER_DECK_PANEL: calculate_timber_deck_panel,
        CalculationModule.STEEL_CANTILEVER_POST: calculate_steel_cantilever_post,
        CalculationModule.MASONRY_WALL: calculate_masonry_wall,
        CalculationModule.RC_WALL: calculate_rc_wall,
        CalculationModule.RETAINING_WALL: calculate_retaining_wall,
        CalculationModule.CONTINUOUS_BEAM: calculate_continuous_beam,
        CalculationModule.PLANAR_FRAME: calculate_planar_frame,
        CalculationModule.PLANAR_TRUSS: calculate_planar_truss,
        CalculationModule.TWO_WAY_SLAB: calculate_two_way_slab,
        CalculationModule.TIMBER_CONNECTION: calculate_timber_connection,
        CalculationModule.WALL_ANCHOR: calculate_wall_anchor,
        CalculationModule.POOL_STRUCTURE: calculate_pool_structure,
        CalculationModule.PILE_GROUP_CAP: calculate_pile_group_cap,
        CalculationModule.BRIDGE_STEEL_TIMBER: calculate_bridge_steel_timber,
        CalculationModule.BRIDGE_RC: calculate_bridge_rc,
        CalculationModule.GRAVITY_RETAINING_WALL: calculate_gravity_retaining_wall,
        CalculationModule.SITE_RC_WALL: calculate_site_rc_wall,
        CalculationModule.STEEL_INFILL_WALL: calculate_steel_infill_wall,
        CalculationModule.PLAIN_MASONRY_WALL: calculate_plain_masonry_wall,
        CalculationModule.LOAD_COMBINATIONS: calculate_load_combinations,
        CalculationModule.WIND_SNOW_GUIDE: calculate_wind_snow_guide,
        CalculationModule.SOIL_WATER_ACTIONS: calculate_soil_water_action_package,
    }
    result = handlers[request.module](request, trace_id)
    result.load_provenance = [item.model_copy(deep=True) for item in request.loads]
    result.catalog_versions.setdefault("schema", request.schema_version)
    return _apply_result_contract(request, result)
