from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import ENGINE_VERSION, SCHEMA_VERSION


class CalculationMode(str, Enum):
    QUICK = "quick"
    PROFESSIONAL = "professional"


class CalculationModule(str, Enum):
    STEEL_BEAM = "steel_beam"
    STEEL_COLUMN = "steel_column"
    PORTAL_FRAME = "portal_frame"
    CONCRETE_BEAM = "concrete_beam"
    CONCRETE_SLAB = "concrete_slab"
    CONCRETE_COLUMN = "concrete_column"
    SPREAD_FOOTING = "spread_footing"
    STRIP_FOOTING = "strip_footing"
    TIMBER_BEAM = "timber_beam"
    TIMBER_COLUMN = "timber_column"
    STEEL_BASEPLATE_ANCHOR = "steel_baseplate_anchor"


class LoadKind(str, Enum):
    SELF_WEIGHT = "self_weight"
    DEAD = "dead"
    LIVE = "live"
    WIND = "wind"
    SNOW = "snow"


class LoadDirection(str, Enum):
    GRAVITY = "gravity"
    UPLIFT = "uplift"
    X_POSITIVE = "x_positive"
    X_NEGATIVE = "x_negative"
    Y_POSITIVE = "y_positive"
    Y_NEGATIVE = "y_negative"


class Quantity(BaseModel):
    value: float
    unit: str


class LoadItem(BaseModel):
    kind: LoadKind
    value: float = Field(ge=0)
    unit: Literal["kN/m", "kN/m2", "kN"]
    source: str = Field(min_length=1, max_length=240)
    direction: LoadDirection = LoadDirection.GRAVITY
    preset_id: str | None = None
    source_reference: str | None = None
    override_reason: str | None = None
    confirmed: bool = False


class CalculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    mode: CalculationMode
    module: CalculationModule
    project_name: str = Field(default="未命名项目", min_length=1, max_length=120)
    standard_profile: Literal["CN-2024"] = "CN-2024"
    confirmed_assumptions: bool = False
    inputs: dict[str, Any] = Field(default_factory=dict)
    loads: list[LoadItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_mode_contract(self) -> "CalculationRequest":
        if self.mode is CalculationMode.QUICK and not self.confirmed_assumptions:
            raise ValueError("快算模式必须确认场景假定")
        if self.mode is CalculationMode.PROFESSIONAL:
            has_upstream_effects = bool(
                isinstance(self.inputs.get("upstream_reaction_envelopes"), list)
                and self.inputs.get("upstream_reaction_envelopes")
            )
            if not self.loads and not has_upstream_effects:
                raise ValueError("专业模式必须明确提供荷载及来源")
            if any(item.source.strip().lower() in {"", "default", "默认"} for item in self.loads):
                raise ValueError("专业模式荷载必须填写可复核来源")
            if any(
                item.preset_id
                and not item.confirmed
                and not (item.override_reason or "").strip()
                for item in self.loads
            ):
                raise ValueError("专业模式覆盖荷载目录建议值时必须填写覆盖原因")
        return self


class CalculationStep(BaseModel):
    name: str
    equation: str
    substitution: str
    result: Quantity
    reference: str


class CheckResult(BaseModel):
    name: str
    demand: Quantity
    capacity: Quantity
    utilization: float = Field(ge=0)
    passed: bool
    reference: str
    note: str | None = None
    governing_combination: str | None = None


class LoadCombinationResult(BaseModel):
    name: str
    limit_state: Literal["ULS", "SLS"]
    combination_id: str | None = None
    sls_type: Literal["standard", "frequent", "quasi_permanent"] | None = None
    leading_action: str | None = None
    factors: dict[str, float]
    factored_by_kind: dict[str, Quantity]
    directions_by_kind: dict[str, list[LoadDirection]] = Field(default_factory=dict)
    total: Quantity
    effect_components: dict[
        Literal["N", "Vx", "Vy", "Mx", "My", "T"], Quantity
    ] = Field(default_factory=dict)


class DiagramPoint(BaseModel):
    x: Quantity
    value: Quantity


class DiagramSeries(BaseModel):
    name: str
    points: list[DiagramPoint]


class CalculationWarning(BaseModel):
    severity: Literal["info", "warning", "critical"]
    code: str
    message: str


class CalculationResult(BaseModel):
    schema_version: str = SCHEMA_VERSION
    engine_version: str = ENGINE_VERSION
    trace_id: str
    project_name: str
    module: CalculationModule
    mode: CalculationMode
    status: Literal["passed", "failed", "incomplete", "not_applicable"]
    workflow_status: Literal[
        "ready", "stale", "missing_inputs", "capability_unavailable"
    ] | None = None
    engineering_status: Literal["passed", "failed", "incomplete"] | None = None
    quick_outcome: Literal["screening_passed", "screening_failed"] | None = None
    result_class: Literal["quick_estimate", "professional_check"] | None = None
    verification_status: Literal[
        "unverified", "independently_verified"
    ] = "unverified"
    standards: list[str]
    input_summary: dict[str, Quantity | str | bool]
    combinations: list[LoadCombinationResult]
    reactions: dict[str, Quantity] = Field(default_factory=dict)
    reaction_envelopes: list["ReactionEnvelope"] = Field(default_factory=list)
    diagrams: list[DiagramSeries] = Field(default_factory=list)
    steps: list[CalculationStep] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    provisional_checks: list[CheckResult] = Field(default_factory=list)
    governing_check: str | None = None
    warnings: list[CalculationWarning] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    applicability: list[str] = Field(default_factory=list)
    catalog_versions: dict[str, str] = Field(default_factory=dict)
    load_provenance: list[LoadItem] = Field(default_factory=list)
    disclaimer: str


class ReactionEnvelope(BaseModel):
    name: str
    limit_state: Literal["ULS", "SLS"]
    combination_id: str | None = None
    combination_name: str | None = None
    sls_type: Literal["standard", "frequent", "quasi_permanent"] | None = None
    leading_action: str | None = None
    direction: LoadDirection | None = None
    components: dict[Literal["N", "Vx", "Vy", "Mx", "My", "T"], Quantity]

    @model_validator(mode="after")
    def complete_six_component_contract(self) -> "ReactionEnvelope":
        """Normalize legacy 2.x partial envelopes to the six-component contract."""

        force_unit = next(
            (
                value.unit
                for key, value in self.components.items()
                if key in {"N", "Vx", "Vy"}
            ),
            "kN",
        )
        moment_unit = next(
            (
                value.unit
                for key, value in self.components.items()
                if key in {"Mx", "My", "T"}
            ),
            "kN·m",
        )
        completed = dict(self.components)
        for key in ("N", "Vx", "Vy"):
            completed.setdefault(key, Quantity(value=0, unit=force_unit))
        for key in ("Mx", "My", "T"):
            completed.setdefault(key, Quantity(value=0, unit=moment_unit))
        self.components = completed  # type: ignore[assignment]
        return self


class ScenarioTemplate(BaseModel):
    id: str
    title: str
    description: str
    module: CalculationModule
    inputs: dict[str, Any]
    loads: list[LoadItem]
    assumptions: list[str]
