from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .schemas import CalculationMode, CalculationRequest, CalculationResult


SceneMaturity = Literal["verified", "beta", "planned"]
SceneAvailability = Literal["public", "development"]
SceneApplicability = Literal["required", "optional", "not_applicable"]
WorkflowStatus = Literal[
    "ready", "stale", "missing_inputs", "capability_unavailable"
]
EngineeringStatus = Literal["passed", "failed", "incomplete"]
VerificationStatus = Literal["unverified", "independently_verified"]
SceneNodeStatus = Literal[
    "completed", "passed", "failed", "incomplete", "not_applicable"
]


class SceneCapability(BaseModel):
    material_system: str
    support_system: str
    graph_template_id: str | None = None
    availability: SceneAvailability = "public"
    missing_capabilities: list[str] = Field(default_factory=list)


class SceneParameter(BaseModel):
    key: str
    label: str
    value_type: Literal["number", "choice", "boolean", "text"]
    unit: str | None = None
    default: Any = None
    options: list[str] = Field(default_factory=list)
    required: bool = True


class SceneNode(BaseModel):
    id: str
    label: str
    role: Literal[
        "load",
        "surface",
        "secondary_member",
        "primary_member",
        "column_wall",
        "connection",
        "foundation",
        "geotechnical",
    ]
    calculation_module: str | None = None
    required: bool = True
    applicability: SceneApplicability = "required"
    maturity: SceneMaturity = "beta"
    verification_status: VerificationStatus = "unverified"
    quick_assumption: str | None = None
    description: str = ""
    input_bindings: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def synchronize_applicability(self) -> "SceneNode":
        if self.applicability == "not_applicable":
            self.required = False
        elif not self.required and self.applicability == "required":
            self.applicability = "optional"
        return self


class SceneConnection(BaseModel):
    id: str
    source_node_id: str
    target_node_id: str
    transfer: Literal[
        "area_to_line",
        "line_to_reaction",
        "reaction_to_line",
        "reaction_package",
        "combination_package",
        "manual",
    ]
    output_unit: str | None = None
    input_unit: str | None = None
    support: Literal["base", "left", "right"] = "base"
    conversion_input_key: str | None = None
    requires_source_trace: bool = False
    description: str = ""


class SceneGraphTemplate(BaseModel):
    id: str
    version: str
    nodes: list[SceneNode]
    connections: list[SceneConnection]


class SceneLoadItem(BaseModel):
    id: str
    label: str
    kind: Literal[
        "self_weight",
        "dead",
        "live",
        "wind",
        "snow",
        "soil",
        "water",
        "buoyancy",
        "temperature",
        "custom",
    ]
    value_type: Literal[
        "fixed", "reference_range", "calculated", "project_defined"
    ]
    recommended_min: float | None = None
    recommended_default: float | None = None
    recommended_max: float | None = None
    adopted_value: float | None = Field(default=None, ge=0)
    unit: str
    source_reference: str
    applicable_when: str
    distribution: Literal["point", "line", "area", "pressure"]
    direction: str
    application_target: str
    override_reason: str | None = None
    notes: str = ""

    @model_validator(mode="after")
    def validate_recommendation_range(self) -> "SceneLoadItem":
        values = [
            value
            for value in (
                self.recommended_min,
                self.recommended_default,
                self.recommended_max,
            )
            if value is not None
        ]
        if any(value < 0 for value in values):
            raise ValueError("荷载建议值不能小于零")
        if values and values != sorted(values):
            raise ValueError("荷载建议值必须满足最小值 <= 推荐值 <= 最大值")
        if self.value_type == "fixed" and self.recommended_default is None:
            raise ValueError("固定值荷载必须提供推荐值")
        if self.value_type == "reference_range" and (
            self.recommended_min is None or self.recommended_max is None
        ):
            raise ValueError("参考范围荷载必须提供上下限")
        if self.value_type == "project_defined" and self.adopted_value is None:
            raise ValueError("项目自定义荷载必须填写采用值")
        return self


class SceneLoadPackage(BaseModel):
    id: str
    version: str
    title: str
    description: str
    items: list[SceneLoadItem]


class SceneVariant(BaseModel):
    id: str
    title: str
    description: str
    material_systems: list[str]
    parameters: list[SceneParameter]
    availability: SceneAvailability = "public"
    support_system: str
    roof_form: str | None = None
    graph_template: SceneGraphTemplate | None = None
    load_package: SceneLoadPackage | None = None
    capabilities: list[SceneCapability] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_capability_matrix(self) -> "SceneVariant":
        public_materials = {
            item.material_system
            for item in self.capabilities
            if item.availability == "public"
        }
        if self.availability == "public":
            if not public_materials:
                raise ValueError("公开场景变体必须至少声明一个可计算材料体系")
            if public_materials != set(self.material_systems):
                raise ValueError("material_systems 只能列出当前可计算的材料体系")
            if any(
                item.graph_template_id is None
                for item in self.capabilities
                if item.availability == "public"
            ):
                raise ValueError("公开能力必须绑定计算图")
        elif public_materials:
            raise ValueError("开发中场景变体不得包含公开计算能力")
        return self


class SceneFamily(BaseModel):
    id: str
    title: str
    description: str
    icon: str
    maturity: SceneMaturity
    availability: SceneAvailability = "public"
    default_variant_id: str
    variants: list[SceneVariant]
    graph_template: SceneGraphTemplate
    boundaries: list[str] = Field(default_factory=list)


class SceneNodeCalculation(BaseModel):
    node_id: str
    calculation: CalculationRequest


class SceneNodeResult(BaseModel):
    node_id: str
    label: str
    status: SceneNodeStatus
    maturity: SceneMaturity
    applicability: SceneApplicability = "required"
    workflow_status: WorkflowStatus = "missing_inputs"
    engineering_status: EngineeringStatus | None = None
    quick_outcome: Literal["screening_passed", "screening_failed"] | None = None
    verification_status: VerificationStatus = "unverified"
    calculation_result: CalculationResult | None = None
    message: str | None = None
    stale: bool = False

    @model_validator(mode="before")
    @classmethod
    def populate_legacy_statuses(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        result = dict(data)
        status = result.get("status", "incomplete")
        result.setdefault(
            "workflow_status",
            "ready"
            if status in {"completed", "passed", "failed", "not_applicable"}
            else "missing_inputs",
        )
        result.setdefault(
            "engineering_status",
            "failed" if status == "failed" else "passed"
            if status in {"completed", "passed", "not_applicable"}
            else "incomplete",
        )
        return result


class SceneRevisionResult(BaseModel):
    scene_family_id: str
    scene_variant_id: str
    mode: CalculationMode
    status: EngineeringStatus
    workflow_status: WorkflowStatus = "missing_inputs"
    engineering_status: EngineeringStatus | None = None
    quick_outcome: Literal["screening_passed", "screening_failed"] | None = None
    result_class: Literal["quick_estimate", "professional_check"] | None = None
    verification_status: VerificationStatus = "unverified"
    graph_template_id: str | None = None
    load_cases: list[SceneLoadItem] = Field(default_factory=list)
    completed_nodes: int
    total_required_nodes: int
    node_results: dict[str, SceneNodeResult]
    missing_nodes: list[str]
    stale_node_ids: list[str]
    control_path: list[str]
    warnings: list[str]
    catalog_versions: dict[str, str]

    @model_validator(mode="before")
    @classmethod
    def populate_legacy_contract(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        result = dict(data)
        engineering_status = result.get(
            "engineering_status", result.get("status", "incomplete")
        )
        result["engineering_status"] = engineering_status
        result.setdefault("status", engineering_status)
        result.setdefault(
            "workflow_status",
            "ready"
            if engineering_status in {"passed", "failed"}
            else "missing_inputs",
        )
        mode = result.get("mode")
        mode_value = getattr(mode, "value", mode)
        result.setdefault(
            "result_class",
            "quick_estimate" if mode_value == "quick" else "professional_check",
        )
        return result
