from __future__ import annotations

from datetime import date
from math import ceil, hypot, pi, sqrt
from typing import Literal

from pydantic import BaseModel, Field, model_validator


DESIGN_CATALOG_VERSION = "CN-2026.7"
STEEL_SECTION_CATALOG_VERSION = "steel-sections-2026.2-unverified"
GEOTECHNICAL_HINT_CATALOG_VERSION = "zhejiang-geotech-2026.1-unverified"
FOUNDATION_SYSTEM_CATALOG_VERSION = "foundation-systems-2026.2-unverified"
ROOF_ASSEMBLY_CATALOG_VERSION = "roof-assemblies-2026.1-unverified"
SOIL_PRESET_CATALOG_VERSION = "soil-presets-2026.1-unverified"
REBAR_CATALOG_VERSION = "rebar-2026.1-unverified"
STEEL_GRADE_CATALOG_VERSION = "steel-grades-2026.1-unverified"
FOUNDATION_FORM_CATALOG_VERSION = "foundation-forms-2026.1-unverified"


class GridAxisDefinition(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    direction: Literal["x", "y"]
    positions_m: list[float] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_positions(self) -> "GridAxisDefinition":
        if len(set(self.positions_m)) != len(self.positions_m):
            raise ValueError("轴网坐标不得重复")
        if self.positions_m != sorted(self.positions_m):
            raise ValueError("轴网坐标必须按从小到大排列")
        return self


class StructuralNode(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=80)
    x_m: float = Field(ge=-1000, le=1000)
    y_m: float = Field(ge=-1000, le=1000)
    z_m: float = Field(ge=-100, le=1000)
    support: Literal["none", "pinned", "fixed"] = "none"
    column_top: bool = False


class StructuralMember(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=80)
    start_node_id: str
    end_node_id: str
    role: Literal["column", "beam", "purlin", "truss_chord", "truss_web", "brace"]
    group_id: str = Field(min_length=1, max_length=80)
    behavior: Literal["frame", "truss"] = "frame"
    end_release: Literal["rigid", "pinned"] = "rigid"
    start_release: "MemberEndRelease | None" = None
    end_release_dofs: "MemberEndRelease | None" = None
    rigid_offset: "RigidEndOffset | None" = None
    design_parameters: "MemberDesignParameters | None" = None


class MemberEndRelease(BaseModel):
    ux: bool = False
    uy: bool = False
    uz: bool = False
    rx: bool = False
    ry: bool = False
    rz: bool = False


class RigidEndOffset(BaseModel):
    start_m: float = Field(default=0, ge=0, le=10)
    end_m: float = Field(default=0, ge=0, le=10)


class MemberDesignParameters(BaseModel):
    local_axis_rotation_deg: float = Field(default=0, ge=-360, le=360)
    effective_length_factor_y: float = Field(default=1.0, gt=0, le=3)
    effective_length_factor_z: float = Field(default=1.0, gt=0, le=3)
    unbraced_length_y_m: float | None = Field(default=None, gt=0, le=100)
    unbraced_length_z_m: float | None = Field(default=None, gt=0, le=100)
    deflection_limit_ratio: float = Field(default=250, ge=100, le=1000)
    utilization_limit: float = Field(default=0.85, gt=0, le=1)


class SupportAssignment(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=80)
    node_id: str = Field(min_length=1, max_length=80)
    restraint: Literal["pinned", "fixed", "spring"]
    foundation_id: str | None = Field(default=None, max_length=80)
    restrained_dofs: list[Literal["ux", "uy", "uz", "rx", "ry", "rz"]] = Field(default_factory=list)
    spring_stiffness: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_spring(self) -> "SupportAssignment":
        if self.restraint == "spring" and not self.spring_stiffness:
            raise ValueError("弹簧支承必须填写至少一个自由度刚度")
        return self


class BoundaryPoint(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=80)
    x_m: float = Field(ge=-1000, le=1000)
    y_m: float = Field(ge=-1000, le=1000)


class BoundarySegment(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=80)
    start_point_id: str
    end_point_id: str
    kind: Literal["line", "arc"] = "line"
    arc_mid_x_m: float | None = None
    arc_mid_y_m: float | None = None

    @model_validator(mode="after")
    def validate_arc(self) -> "BoundarySegment":
        if self.start_point_id == self.end_point_id:
            raise ValueError("屋面边界线段起点和终点不得相同")
        if self.kind == "arc" and (self.arc_mid_x_m is None or self.arc_mid_y_m is None):
            raise ValueError("圆弧边界必须提供弧上第三点")
        return self


class PlanBoundaryProfile(BaseModel):
    outer_points: list[BoundaryPoint] = Field(min_length=3, max_length=160)
    outer_segments: list[BoundarySegment] = Field(min_length=3, max_length=160)
    source: str = Field(default="用户二维图面定义", min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_closed_boundary(self) -> "PlanBoundaryProfile":
        point_ids = {item.id for item in self.outer_points}
        if len(point_ids) != len(self.outer_points):
            raise ValueError("屋面边界点编号不得重复")
        if any(item.start_point_id not in point_ids or item.end_point_id not in point_ids for item in self.outer_segments):
            raise ValueError("屋面边界线段引用了不存在的点")
        starts = {item.start_point_id for item in self.outer_segments}
        ends = {item.end_point_id for item in self.outer_segments}
        if starts != point_ids or ends != point_ids:
            raise ValueError("屋面边界必须形成单一闭合环")
        return self


class RoofElevationRule(BaseModel):
    kind: Literal["flat", "single_slope", "double_slope", "node_elevations"] = "flat"
    datum_height_m: float = Field(default=3.0, gt=0, le=100)
    slope_deg: float | None = Field(default=None, ge=0, le=45)
    direction_deg: float | None = Field(default=None, ge=0, lt=360)
    ridge_start: tuple[float, float] | None = None
    ridge_end: tuple[float, float] | None = None
    opposite_slope_deg: float | None = Field(default=None, ge=0, le=45)

    @model_validator(mode="after")
    def validate_rule(self) -> "RoofElevationRule":
        if self.kind == "single_slope" and (self.slope_deg is None or self.direction_deg is None):
            raise ValueError("单坡屋面必须填写坡度和出坡方向")
        if self.kind == "double_slope" and (
            self.slope_deg is None
            or self.opposite_slope_deg is None
            or self.ridge_start is None
            or self.ridge_end is None
            or self.ridge_start == self.ridge_end
        ):
            raise ValueError("双坡屋面必须填写屋脊线和两侧坡度")
        return self


class RoofSurface(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    node_ids: list[str] = Field(min_length=3, max_length=40)
    form: Literal["flat", "single_slope", "double_slope", "faceted"]
    load_path_group_ids: list[str] = Field(default_factory=list, max_length=40)
    load_direction_deg: float | None = Field(default=None, ge=0, lt=360)
    opening_ids: list[str] = Field(default_factory=list, max_length=40)


class RoofOpening(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=80)
    surface_id: str = Field(min_length=1, max_length=80)
    node_ids: list[str] = Field(min_length=3, max_length=40)


class RoofLoadZone(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=80)
    surface_id: str = Field(min_length=1, max_length=80)
    boundary_node_ids: list[str] = Field(min_length=3, max_length=80)
    roof_assembly_id: str = Field(min_length=1, max_length=80)
    load_path_group_ids: list[str] = Field(min_length=1, max_length=40)
    load_direction_deg: float | None = Field(default=None, ge=0, lt=360)


class MemberLoadAssignment(BaseModel):
    case_id: str = Field(min_length=1, max_length=80)
    member_id: str = Field(min_length=1, max_length=80)
    direction: Literal["global_x", "global_y", "global_z", "local_y", "local_z"]
    start_kn_m: float = Field(ge=-1000, le=1000)
    end_kn_m: float = Field(ge=-1000, le=1000)
    tributary_area_m2: float = Field(ge=0, le=100000)
    source_zone_id: str | None = Field(default=None, max_length=80)


class DesignLoadCombination(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    design_situation: Literal["persistent", "seismic"]
    factors: dict[str, float] = Field(min_length=1, max_length=30)
    source_reference: str = Field(min_length=1, max_length=400)
    catalog_version: str = Field(default="load-combinations-CN-2026.7-unverified")


class ModelObjectMark(BaseModel):
    object_id: str = Field(min_length=1, max_length=80)
    object_kind: Literal["node", "member", "support", "foundation", "roof_surface"]
    mark: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=120)


class MemberTypeDefinition(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=80)
    mark_prefix: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=80)
    role: Literal["column", "beam", "purlin", "truss_chord", "truss_web", "brace"]
    material_grade: str = Field(min_length=1, max_length=40)
    section_id: str = Field(min_length=1, max_length=100)
    orientation: Literal["strong_axis", "weak_axis"] = "strong_axis"
    end_release: Literal["rigid", "pinned"] = "rigid"


class MemberInstanceAssignment(BaseModel):
    member_id: str = Field(min_length=1, max_length=80)
    member_type_id: str = Field(min_length=1, max_length=80)
    mark: str = Field(min_length=1, max_length=40)
    override_section_id: str | None = Field(default=None, max_length=100)
    source: Literal["type", "instance_override"] = "type"


class PedestalProfile(BaseModel):
    enabled: bool = False
    auto_enabled: bool = True
    override_reason: str | None = Field(default=None, max_length=400)
    length_mm: float | None = Field(default=None, ge=150, le=3000)
    width_mm: float | None = Field(default=None, ge=150, le=3000)
    clear_height_mm: float | None = Field(default=None, ge=100, le=5000)
    top_elevation_m: float | None = Field(default=None, ge=-100, le=1000)
    bottom_elevation_m: float | None = Field(default=None, ge=-100, le=1000)
    concrete_grade: str | None = Field(default=None, max_length=20)
    cover_mm: float | None = Field(default=None, ge=20, le=150)
    longitudinal_bar_count_x: int | None = Field(default=None, ge=2, le=20)
    longitudinal_bar_count_y: int | None = Field(default=None, ge=2, le=20)
    longitudinal_bar_diameter_mm: float | None = Field(default=None, ge=10, le=40)
    stirrup_diameter_mm: float | None = Field(default=None, ge=6, le=20)
    stirrup_spacing_mm: float | None = Field(default=None, ge=50, le=400)
    confinement_spacing_mm: float | None = Field(default=None, ge=50, le=300)
    dowel_anchorage_mm: float | None = Field(default=None, ge=100, le=5000)
    splice_type: Literal["none", "lap", "mechanical", "welded"] = "none"
    top_local_reinforcement: bool = False

    @model_validator(mode="after")
    def validate_enabled(self) -> "PedestalProfile":
        required = (
            self.length_mm,
            self.width_mm,
            self.clear_height_mm,
            self.concrete_grade,
            self.cover_mm,
            self.longitudinal_bar_count_x,
            self.longitudinal_bar_count_y,
            self.longitudinal_bar_diameter_mm,
            self.stirrup_diameter_mm,
            self.stirrup_spacing_mm,
            self.dowel_anchorage_mm,
        )
        if self.enabled and any(value is None for value in required):
            raise ValueError("启用短柱时必须填写几何、混凝土、纵筋、箍筋和锚固参数")
        if self.enabled and self.top_elevation_m is not None and self.bottom_elevation_m is not None:
            expected = (self.top_elevation_m - self.bottom_elevation_m) * 1000
            if abs(expected - float(self.clear_height_mm or 0)) > 5:
                raise ValueError("短柱净高必须与顶、底标高一致")
        if not self.auto_enabled and self.override_reason is None:
            raise ValueError("覆盖短柱自动判断时必须填写原因")
        return self


class FoundationStep(BaseModel):
    length_m: float = Field(ge=0.3, le=30)
    width_m: float = Field(ge=0.3, le=30)
    height_mm: float = Field(ge=100, le=2000)


class FoundationTypeDefinition(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=80)
    mark: str = Field(pattern=r"^F-[A-Z]+$", min_length=3, max_length=20)
    title: str = Field(min_length=1, max_length=80)
    form_id: str = Field(min_length=1, max_length=80)
    length_m: float = Field(ge=0.5, le=30)
    width_m: float = Field(ge=0.5, le=30)
    thickness_mm: float = Field(ge=200, le=5000)
    embedment_m: float = Field(ge=0, le=20)
    concrete_grade: str = Field(min_length=2, max_length=20)
    rebar_grade: str = Field(min_length=3, max_length=30)
    bottom_x: str = Field(min_length=3, max_length=40)
    bottom_y: str = Field(min_length=3, max_length=40)
    top_x: str | None = Field(default=None, min_length=3, max_length=40)
    top_y: str | None = Field(default=None, min_length=3, max_length=40)
    cover_mm: float | None = Field(default=None, ge=35, le=150)
    steps: list[FoundationStep] = Field(default_factory=list, max_length=3)
    tapered_top_length_m: float | None = Field(default=None, ge=0.15, le=30)
    tapered_top_width_m: float | None = Field(default=None, ge=0.15, le=30)
    tapered_height_mm: float | None = Field(default=None, ge=100, le=3000)
    pedestal: PedestalProfile | None = None

    @model_validator(mode="after")
    def validate_optional_shape_geometry(self) -> "FoundationTypeDefinition":
        for step in self.steps:
            if step.length_m >= self.length_m or step.width_m >= self.width_m:
                raise ValueError("基础台阶平面尺寸必须小于基础底板尺寸")
        taper_values = (
            self.tapered_top_length_m,
            self.tapered_top_width_m,
            self.tapered_height_mm,
        )
        if any(value is not None for value in taper_values) and any(value is None for value in taper_values):
            raise ValueError("锥形基础顶台长、宽和坡面高度必须同时填写")
        if self.tapered_top_length_m is not None and (
            self.tapered_top_length_m >= self.length_m
            or float(self.tapered_top_width_m or 0) >= self.width_m
        ):
            raise ValueError("锥形基础顶台尺寸必须小于基础底板尺寸")
        return self


class FoundationInstanceAssignment(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=80)
    support_id: str = Field(min_length=1, max_length=80)
    foundation_type_id: str = Field(min_length=1, max_length=80)
    mark: str = Field(pattern=r"^F-[A-Z]+-\d{2,}$", min_length=6, max_length=40)
    column_member_id: str | None = Field(default=None, max_length=80)


class WorkPlaneDefinition(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    kind: Literal["plan", "x_elevation", "y_elevation"]
    elevation_m: float | None = Field(default=None, ge=-100, le=1000)


class DoubleSlopeRoofRule(BaseModel):
    ridge_direction_deg: float = Field(ge=0, lt=360)
    ridge_offset_ratio: float = Field(default=0.5, ge=0, le=1)
    left_slope_deg: float = Field(ge=0, le=45)
    right_slope_deg: float = Field(ge=0, le=45)


class ConnectionTypeDefinition(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=80)
    mark: str = Field(pattern=r"^J-[A-Z]+$", min_length=3, max_length=20)
    title: str = Field(min_length=1, max_length=100)
    family: Literal["beam_column", "secondary_beam", "beam_splice", "brace", "column_base"]
    behavior: Literal["rigid", "pinned", "semi_rigid"]
    supported_section_families: list[str] = Field(default_factory=list)
    parameters: dict[str, float | str | bool] = Field(default_factory=dict)
    verification_status: Literal["unverified", "independently_verified"] = "unverified"


class ConnectionInstanceAssignment(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=80)
    mark: str = Field(pattern=r"^J-[A-Z]+-\d{2,}$", min_length=6, max_length=40)
    connection_type_id: str = Field(min_length=1, max_length=80)
    node_id: str = Field(min_length=1, max_length=80)
    member_ids: list[str] = Field(min_length=1, max_length=12)
    status: Literal["defined", "unsupported", "incomplete"] = "incomplete"
    message: str | None = Field(default=None, max_length=300)


class AnchorSpringProfile(BaseModel):
    """Elastic tension-only anchor stiffness; coordinates relative to plate centre."""

    x_m: float = Field(allow_inf_nan=False)
    y_m: float = Field(allow_inf_nan=False)
    stiffness_kn_m: float = Field(gt=0, allow_inf_nan=False)


class ColumnBaseAssembly(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    column_member_id: str = Field(min_length=1, max_length=80)
    support_id: str = Field(min_length=1, max_length=80)
    connection_instance_id: str | None = Field(default=None, max_length=80)
    base_plate_length_mm: float = Field(ge=100, le=3000)
    base_plate_width_mm: float = Field(ge=100, le=3000)
    base_plate_thickness_mm: float = Field(ge=6, le=200)
    anchor_grade: str = Field(min_length=1, max_length=40)
    anchor_diameter_mm: float = Field(ge=10, le=100)
    anchor_count: int = Field(ge=2, le=32)
    anchor_embedment_mm: float = Field(ge=100, le=3000)
    anchor_spacing_mm: float | None = Field(default=None, ge=60, le=1800)
    anchor_edge_mm: float | None = Field(default=None, ge=20, le=500)
    anchor_head_diameter_mm: float | None = Field(default=None, ge=20, le=300)
    anchor_supplementary_reinforcement_area_mm2: float | None = Field(default=None, ge=0, le=20000)
    anchor_cracked_concrete: bool = True
    weld_throat_mm: float | None = Field(default=None, ge=3, le=40)
    concrete_bearing_capacity_mpa: float | None = Field(default=None, ge=1, le=60)
    grout_thickness_mm: float = Field(default=30, ge=0, le=200)
    contact_stiffness_kn_m3: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    contact_model_source: str | None = Field(default=None, min_length=1, max_length=1000)
    anchor_springs: list[AnchorSpringProfile] = Field(default_factory=list, max_length=32)
    continuous_perimeter_weld: bool | None = None

    @model_validator(mode="after")
    def validate_contact_parameters(self) -> "ColumnBaseAssembly":
        if self.contact_model_source is not None and not self.contact_model_source.strip():
            raise ValueError("接触模型来源不得为空白")
        if self.anchor_springs:
            if len(self.anchor_springs) != self.anchor_count:
                raise ValueError("锚栓弹簧数量必须与实际锚栓数量相同")
            positions = {(a.x_m, a.y_m) for a in self.anchor_springs}
            if len(positions) != len(self.anchor_springs):
                raise ValueError("锚栓坐标不得重复")
            if any(abs(a.x_m) >= self.base_plate_length_mm / 2000
                   or abs(a.y_m) >= self.base_plate_width_mm / 2000 for a in self.anchor_springs):
                raise ValueError("锚栓坐标必须位于底板内部")
        return self


class SceneGeometryProfile(BaseModel):
    profile_version: Literal["1.0", "2.0", "2.1", "2.2", "2.3"] = "1.0"
    layout_mode: Literal["preset", "custom_grid", "free_plan"] = "preset"
    axes: list[GridAxisDefinition] = Field(default_factory=list, max_length=20)
    nodes: list[StructuralNode] = Field(min_length=2, max_length=200)
    members: list[StructuralMember] = Field(min_length=1, max_length=400)
    roof_surfaces: list[RoofSurface] = Field(default_factory=list, max_length=80)
    supports: list[SupportAssignment] = Field(default_factory=list, max_length=200)
    plan_boundary: PlanBoundaryProfile | None = None
    roof_elevation: RoofElevationRule | None = None
    object_marks: list[ModelObjectMark] = Field(default_factory=list, max_length=800)
    member_types: list[MemberTypeDefinition] = Field(default_factory=list, max_length=80)
    member_instances: list[MemberInstanceAssignment] = Field(default_factory=list, max_length=400)
    foundation_types: list[FoundationTypeDefinition] = Field(default_factory=list, max_length=80)
    foundation_instances: list[FoundationInstanceAssignment] = Field(default_factory=list, max_length=200)
    work_planes: list[WorkPlaneDefinition] = Field(default_factory=list, max_length=80)
    double_slope_rule: DoubleSlopeRoofRule | None = None
    connection_types: list[ConnectionTypeDefinition] = Field(default_factory=list, max_length=80)
    connection_instances: list[ConnectionInstanceAssignment] = Field(default_factory=list, max_length=800)
    column_bases: list[ColumnBaseAssembly] = Field(default_factory=list, max_length=200)
    roof_openings: list[RoofOpening] = Field(default_factory=list, max_length=80)
    roof_load_zones: list[RoofLoadZone] = Field(default_factory=list, max_length=160)
    source: str = Field(default="用户引导式轴网", min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_connectivity(self) -> "SceneGeometryProfile":
        node_ids = [item.id for item in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("空间模型节点编号不得重复")
        member_ids = [item.id for item in self.members]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("空间模型杆件编号不得重复")
        known = set(node_ids)
        for member in self.members:
            if member.start_node_id not in known or member.end_node_id not in known:
                raise ValueError(f"杆件 {member.id} 引用了不存在的节点")
            if member.start_node_id == member.end_node_id:
                raise ValueError(f"杆件 {member.id} 起点与终点不得相同")
        for surface in self.roof_surfaces:
            if not set(surface.node_ids).issubset(known):
                raise ValueError(f"屋面分区 {surface.id} 引用了不存在的节点")
        for support in self.supports:
            if support.node_id not in known:
                raise ValueError(f"支承 {support.id} 引用了不存在的节点")
        if self.profile_version in {"2.1", "2.2", "2.3"}:
            member_type_ids = {item.id for item in self.member_types}
            member_id_set = set(member_ids)
            if any(item.member_id not in member_id_set for item in self.member_instances):
                raise ValueError("构件实例引用了不存在的杆件")
            if any(item.member_type_id not in member_type_ids for item in self.member_instances):
                raise ValueError("构件实例引用了不存在的构件类型")
            support_ids = {item.id for item in self.supports}
            foundation_type_ids = {item.id for item in self.foundation_types}
            if any(item.support_id not in support_ids for item in self.foundation_instances):
                raise ValueError("基础实例引用了不存在的支承")
            if any(item.foundation_type_id not in foundation_type_ids for item in self.foundation_instances):
                raise ValueError("基础实例引用了不存在的基础类型")
            if self.roof_elevation and self.roof_elevation.kind == "double_slope" and self.double_slope_rule is None:
                raise ValueError("2.1 双坡屋面必须提供独立的屋脊方向规则")
            if self.profile_version in {"2.2", "2.3"}:
                connection_type_ids = {item.id for item in self.connection_types}
                support_ids = {item.id for item in self.supports}
                for item in self.connection_instances:
                    if item.connection_type_id not in connection_type_ids:
                        raise ValueError(f"连接实例 {item.id} 引用了不存在的连接类型")
                    if item.node_id not in known or not set(item.member_ids).issubset(member_id_set):
                        raise ValueError(f"连接实例 {item.id} 引用了不存在的节点或构件")
                for item in self.column_bases:
                    if item.column_member_id not in member_id_set or item.support_id not in support_ids:
                        raise ValueError(f"柱脚总成 {item.id} 引用了不存在的柱或支承")
            if self.profile_version == "2.3":
                surface_ids = {item.id for item in self.roof_surfaces}
                opening_ids = {item.id for item in self.roof_openings}
                for opening in self.roof_openings:
                    if opening.surface_id not in surface_ids or not set(opening.node_ids).issubset(known):
                        raise ValueError(f"屋面开洞 {opening.id} 引用了不存在的分区或节点")
                for surface in self.roof_surfaces:
                    if not set(surface.opening_ids).issubset(opening_ids):
                        raise ValueError(f"屋面分区 {surface.id} 引用了不存在的开洞")
                for zone in self.roof_load_zones:
                    if zone.surface_id not in surface_ids or not set(zone.boundary_node_ids).issubset(known):
                        raise ValueError(f"屋面荷载区 {zone.id} 引用了不存在的分区或节点")
        if self.profile_version == "1.0" and not any(item.support != "none" for item in self.nodes):
            raise ValueError("空间模型至少需要一个支承节点")
        return self


class ToolOperationDraft(BaseModel):
    tool: Literal["node", "beam", "column", "support", "boundary", "arc", "measure"]
    step: str = Field(min_length=1, max_length=80)
    point_ids: list[str] = Field(default_factory=list, max_length=200)
    preview: dict[str, object] = Field(default_factory=dict)
    committed: bool = False


class RoofLoadSelectionProfile(BaseModel):
    roof_assembly_id: str = Field(min_length=1, max_length=80)
    maintenance_category: Literal["not_applicable", "maintenance", "walkway_equipment", "occupied", "custom"]
    maintenance_load_kn_m2: float | None = Field(default=None, ge=0, le=20)
    concentrated_maintenance_check_required: bool = False
    custom_basis: str | None = Field(default=None, max_length=400)

    @model_validator(mode="after")
    def validate_custom_load(self) -> "RoofLoadSelectionProfile":
        if self.maintenance_category in {"walkway_equipment", "occupied", "custom"} and self.maintenance_load_kn_m2 is None:
            raise ValueError("所选屋面使用类别必须填写采用荷载")
        if self.maintenance_category == "custom" and not (self.custom_basis or "").strip():
            raise ValueError("自定义检修荷载必须填写依据和原因")
        return self


class StructuralAnalysisPackage(BaseModel):
    status: Literal["complete", "incomplete", "failed"]
    verification_status: Literal["unverified", "independently_verified"] = "unverified"
    load_cases: list[dict[str, object]] = Field(default_factory=list)
    combinations: list[dict[str, object]] = Field(default_factory=list)
    reactions: list[dict[str, object]] = Field(default_factory=list)
    member_checks: list[dict[str, object]] = Field(default_factory=list)
    balance_checks: list[dict[str, object]] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)


class MemberCheckPackage(BaseModel):
    status: Literal["complete", "incomplete", "failed"]
    items: list[dict[str, object]] = Field(default_factory=list)
    controlling_member_ids: list[str] = Field(default_factory=list)


class BucklingAnalysisPackage(BaseModel):
    status: Literal["complete", "incomplete", "failed"]
    factors: list[float] = Field(default_factory=list)
    controlling_mode: int | None = None
    missing_inputs: list[str] = Field(default_factory=list)


class VerificationEvidence(BaseModel):
    method: Literal["analytic", "hand_calculation", "independent_solver", "commercial_reference"]
    reference: str = Field(min_length=1, max_length=400)
    result: Literal["pass", "fail", "pending"]
    tolerance: str | None = Field(default=None, max_length=120)


class SavedSceneAnalysisSnapshot(BaseModel):
    snapshot_schema_version: Literal["4.0"] = "4.0"
    standard_profile: Literal["CN-2026.7"] = "CN-2026.7"
    geometry: SceneGeometryProfile
    site_profile: dict[str, object]
    geotechnical_profile: dict[str, object] | None = None
    custom_sections: list[dict[str, object]] = Field(default_factory=list)
    roof_load_selection: RoofLoadSelectionProfile
    load_cases: list[dict[str, object]] = Field(default_factory=list)
    combinations: list[DesignLoadCombination] = Field(default_factory=list)
    analysis: dict[str, object]
    created_at: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ConnectionCheckPackage(BaseModel):
    status: Literal["complete", "incomplete", "failed"]
    items: list[dict[str, object]] = Field(default_factory=list)
    unsupported_connection_ids: list[str] = Field(default_factory=list)


class FoundationCheckPackage(BaseModel):
    status: Literal["complete", "incomplete", "failed"]
    items: list[dict[str, object]] = Field(default_factory=list)
    reaction_source_ids: list[str] = Field(default_factory=list)


class CalculationTracePackage(BaseModel):
    snapshot_schema_version: Literal["3.9", "4.0"] = "4.0"
    standard_profile: Literal["CN-2026.6", "CN-2026.7"] = "CN-2026.7"
    input_sources: list[dict[str, object]] = Field(default_factory=list)
    formulas: list[dict[str, object]] = Field(default_factory=list)
    user_overrides: list[dict[str, object]] = Field(default_factory=list)
    unsupported_capabilities: list[str] = Field(default_factory=list)


class MemberGroupSpecification(BaseModel):
    group_id: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=1, max_length=80)
    material_grade: str = Field(min_length=1, max_length=40)
    section_catalog_id: str | None = Field(default=None, max_length=100)
    custom_section_id: str | None = Field(default=None, max_length=100)
    strong_axis_unbraced_length_m: float = Field(gt=0, le=100)
    weak_axis_unbraced_length_m: float = Field(gt=0, le=100)
    effective_length_factor_y: float = Field(default=1.0, gt=0, le=3)
    effective_length_factor_z: float = Field(default=1.0, gt=0, le=3)

    @model_validator(mode="after")
    def validate_section_source(self) -> "MemberGroupSpecification":
        if bool(self.section_catalog_id) == bool(self.custom_section_id):
            raise ValueError("构件组必须且只能选择目录截面或项目自定义截面")
        return self


class CustomSectionDefinition(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    family: Literal["SHS", "RHS", "CHS", "H", "I", "C", "L", "2L"]
    dimensions: dict[str, float]
    area_mm2: float = Field(gt=0)
    iy_mm4: float = Field(gt=0)
    iz_mm4: float = Field(gt=0)
    torsion_mm4: float = Field(gt=0)
    self_weight_kn_m: float = Field(gt=0)
    theoretical_mass_kg_m: float | None = Field(default=None, gt=0)
    radius_y_mm: float | None = Field(default=None, gt=0)
    radius_z_mm: float | None = Field(default=None, gt=0)
    corner_radius_mm: float | None = Field(default=None, ge=0)
    revision: int = Field(default=1, ge=1)
    source_type: Literal["catalog", "manufacturer", "user_geometry"] = "user_geometry"
    property_trace: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    source_reference: str = Field(min_length=1, max_length=400)


class CustomSectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    family: Literal["SHS", "RHS", "CHS", "H", "I"]
    dimensions: dict[str, float]
    material_density_kg_m3: float = Field(default=7850, ge=1000, le=20000)
    corner_radius_mm: float | None = Field(default=None, ge=0, le=500)
    source_type: Literal["manufacturer", "user_geometry"] = "user_geometry"
    source_reference: str = Field(default="用户按实测或厂家资料输入", min_length=1, max_length=400)


def calculate_custom_section(payload: CustomSectionCreate, *, section_id: str) -> CustomSectionDefinition:
    """Calculate standard parametric steel-section properties from geometry.

    The API deliberately does not accept user-supplied area or inertia values.
    This prevents a name-only custom section from silently entering a scene.
    """

    dimensions = {key: float(value) for key, value in payload.dimensions.items()}

    def require(*names: str) -> list[float]:
        values: list[float] = []
        for name in names:
            value = dimensions.get(name)
            if value is None or value <= 0:
                raise ValueError(f"自定义截面必须填写正数尺寸 {name}")
            values.append(value)
        return values

    if payload.family in {"SHS", "RHS"}:
        h, b, t = require("h_mm", "b_mm", "t_mm")
        if 2 * t >= min(h, b):
            raise ValueError("矩形管壁厚必须小于截面短边的一半")
        inner_h, inner_b = h - 2 * t, b - 2 * t
        area = b * h - inner_b * inner_h
        iy = (b * h**3 - inner_b * inner_h**3) / 12
        iz = (h * b**3 - inner_h * inner_b**3) / 12
        mid_h, mid_b = h - t, b - t
        torsion = 4 * (mid_h * mid_b) ** 2 / (2 * (mid_h + mid_b) / t)
    elif payload.family == "CHS":
        diameter, t = require("diameter_mm", "t_mm")
        if 2 * t >= diameter:
            raise ValueError("圆管壁厚必须小于外径的一半")
        inner = diameter - 2 * t
        area = pi * (diameter**2 - inner**2) / 4
        iy = iz = pi * (diameter**4 - inner**4) / 64
        torsion = 2 * iy
    else:
        h, b, tw, tf = require("h_mm", "b_mm", "tw_mm", "tf_mm")
        if 2 * tf >= h or tw >= b:
            raise ValueError("H/I形截面的翼缘或腹板尺寸不合理")
        web_h = h - 2 * tf
        area = 2 * b * tf + web_h * tw
        iy = (b * h**3 - (b - tw) * web_h**3) / 12
        iz = 2 * tf * b**3 / 12 + web_h * tw**3 / 12
        torsion = (2 * b * tf**3 + web_h * tw**3) / 3

    theoretical_mass = area * 1e-6 * payload.material_density_kg_m3
    self_weight = theoretical_mass * 9.80665 / 1000
    family_formula = {
        "SHS": "A = B×H - (B-2t)×(H-2t)",
        "RHS": "A = B×H - (B-2t)×(H-2t)",
        "CHS": "A = π/4 × [D²-(D-2t)²]",
        "H": "A = 2×B×tf + (H-2tf)×tw",
        "I": "A = 2×B×tf + (H-2tf)×tw",
    }[payload.family]
    return CustomSectionDefinition(
        id=section_id,
        name=payload.name.strip(),
        family=payload.family,
        dimensions=dimensions,
        area_mm2=round(area, 3),
        iy_mm4=round(iy, 3),
        iz_mm4=round(iz, 3),
        torsion_mm4=round(torsion, 3),
        self_weight_kn_m=round(self_weight, 5),
        theoretical_mass_kg_m=round(theoretical_mass, 5),
        radius_y_mm=round(sqrt(iy / area), 3),
        radius_z_mm=round(sqrt(iz / area), 3),
        corner_radius_mm=payload.corner_radius_mm,
        source_type=payload.source_type,
        property_trace=[
            family_formula,
            f"A = {area:.3f} mm²",
            f"m = A×10⁻⁶×{payload.material_density_kg_m3:g} = {theoretical_mass:.5f} kg/m",
            f"w = m×9.80665÷1000 = {self_weight:.5f} kN/m",
        ],
        assumptions=([] if payload.corner_radius_mm is not None else ["未计圆角和制造公差，按锐角理论截面计算"]),
        source_reference=payload.source_reference.strip(),
    )


class MemberSectionOverride(BaseModel):
    member_id: str = Field(min_length=1, max_length=80)
    material_grade: str = Field(min_length=1, max_length=40)
    section_id: str = Field(min_length=1, max_length=100)
    orientation: Literal["strong_axis", "weak_axis"] = "strong_axis"
    source: str = Field(default="用户单根构件覆盖", min_length=1, max_length=240)


class AnalysisMemberMapping(BaseModel):
    analysis_member_id: str
    source_member_id: str
    section_id: str
    assignment_scope: Literal["group", "member_override"]


class RoofAssemblyLayer(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    thickness_mm: float | None = Field(default=None, gt=0, le=1000)
    unit_weight_kn_m3: float | None = Field(default=None, gt=0, le=100)
    surface_weight_kn_m2: float = Field(ge=0, le=20)


class RoofAssembly(BaseModel):
    id: str
    title: str
    cover_type: Literal["none", "louver", "glass", "aluminum", "steel", "polycarbonate", "timber", "custom"]
    layers: list[RoofAssemblyLayer]
    total_dead_load_kn_m2: float = Field(ge=0, le=20)
    reference_range_kn_m2: tuple[float, float]
    source_reference: str
    verification_status: Literal["unverified", "independently_verified"] = "unverified"


class FoundationReinforcementProfile(BaseModel):
    bottom_x_diameter_mm: float = Field(ge=6, le=40)
    bottom_x_spacing_mm: float = Field(ge=50, le=400)
    bottom_y_diameter_mm: float = Field(ge=6, le=40)
    bottom_y_spacing_mm: float = Field(ge=50, le=400)
    top_local_diameter_mm: float | None = Field(default=None, ge=6, le=40)
    top_local_spacing_mm: float | None = Field(default=None, ge=50, le=400)


class PedestalSpecification(BaseModel):
    enabled: bool = False
    length_mm: float | None = Field(default=None, ge=150, le=3000)
    width_mm: float | None = Field(default=None, ge=150, le=3000)
    height_mm: float | None = Field(default=None, ge=100, le=5000)
    longitudinal_bar_count: int | None = Field(default=None, ge=4, le=40)
    longitudinal_bar_diameter_mm: float | None = Field(default=None, ge=10, le=40)
    stirrup_diameter_mm: float | None = Field(default=None, ge=6, le=20)
    stirrup_spacing_mm: float | None = Field(default=None, ge=50, le=400)

    @model_validator(mode="after")
    def validate_enabled_dimensions(self) -> "PedestalSpecification":
        required = (
            self.length_mm,
            self.width_mm,
            self.height_mm,
            self.longitudinal_bar_count,
            self.longitudinal_bar_diameter_mm,
            self.stirrup_diameter_mm,
            self.stirrup_spacing_mm,
        )
        if self.enabled and any(item is None for item in required):
            raise ValueError("启用短柱时必须填写短柱尺寸、纵筋和箍筋")
        return self


class SurfaceExposureProfile(BaseModel):
    vertical_enclosure: Literal["none", "open_members", "perforated_panel", "solid_panel"]
    top_cover: Literal["none", "louver_grid", "permeable_cover", "solid_roof"]
    vertical_open_ratio: float | None = Field(default=None, ge=0, le=1)
    top_open_ratio: float | None = Field(default=None, ge=0, le=1)
    roof_form: Literal["flat", "single_slope", "double_slope", "other"] | None = None
    roof_slope_deg: float | None = Field(default=None, ge=0, le=90)
    source: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_applicable_geometry(self) -> "SurfaceExposureProfile":
        if self.vertical_enclosure in {"open_members", "perforated_panel"} and self.vertical_open_ratio is None:
            raise ValueError("格栅、杆件或穿孔板必须填写竖向开孔率")
        if self.top_cover in {"louver_grid", "permeable_cover"} and self.top_open_ratio is None:
            raise ValueError("百叶、格栅或透水覆盖必须填写顶部开孔率")
        if self.top_cover == "solid_roof" and self.roof_form is None:
            raise ValueError("实体屋盖必须选择屋面形式")
        if self.top_cover == "none" and (self.roof_form is not None or self.roof_slope_deg is not None):
            raise ValueError("无顶部覆盖时不得填写屋面形式或坡度")
        return self


class MemberSpecification(BaseModel):
    node_id: str = Field(min_length=1, max_length=80)
    member_role: str = Field(min_length=1, max_length=80)
    material_grade: str = Field(min_length=1, max_length=40)
    section_catalog_id: str = Field(min_length=1, max_length=100)
    section_type: Literal["SHS", "RHS", "CHS", "H", "I"]
    section_name: str = Field(min_length=1, max_length=120)
    orientation: Literal["strong_axis", "weak_axis"] = "strong_axis"
    effective_length_m: float = Field(gt=0, le=100)
    unbraced_length_m: float = Field(gt=0, le=100)
    selection_source: Literal["recommended", "user_locked"]
    override_reason: str | None = Field(default=None, max_length=400)

    @model_validator(mode="after")
    def require_override_reason(self) -> "MemberSpecification":
        if self.selection_source == "user_locked" and not (self.override_reason or "").strip():
            raise ValueError("锁定构件截面时必须填写调整原因")
        return self


class SectionCatalogEntry(BaseModel):
    id: str
    family: Literal["SHS", "RHS", "CHS", "H", "I", "C", "L", "2L"]
    designation: str
    dimensions: dict[str, float]
    area_mm2: float = Field(gt=0)
    self_weight_kn_m: float = Field(gt=0)
    material_grades: list[str]
    source_reference: str
    verification_status: Literal["unverified", "independently_verified"] = "unverified"


class GroundwaterDesignProfile(BaseModel):
    condition: Literal["no_influence", "known_levels", "unknown"]
    construction_level_m: float | None = None
    service_level_m: float | None = None
    antifloat_level_m: float | None = None
    source: str = Field(min_length=1, max_length=400)
    observation_date: date | None = None

    @model_validator(mode="after")
    def validate_levels(self) -> "GroundwaterDesignProfile":
        if self.condition == "known_levels" and any(
            value is None
            for value in (self.construction_level_m, self.service_level_m, self.antifloat_level_m)
        ):
            raise ValueError("已知地下水条件必须填写施工期、正常使用和抗浮设计水位标高")
        return self


class SettlementLayer(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    thickness_m: float = Field(gt=0, le=100)
    compression_modulus_mpa: float = Field(gt=0, le=1000)
    unit_weight_kn_m3: float = Field(gt=0, le=35)
    source: str = Field(min_length=1, max_length=400)


class ProjectGeotechnicalProfile(BaseModel):
    profile_version: Literal["1.0", "1.1"] = "1.0"
    stage: Literal["scheme_estimate", "project_check"]
    regional_hint_id: str | None = None
    confirmed_soil_class: str = Field(min_length=1, max_length=120)
    bearing_capacity_kpa: float = Field(gt=0, le=5000)
    bearing_capacity_source: str = Field(min_length=1, max_length=400)
    deformation_modulus_mpa: float | None = Field(default=None, gt=0, le=1000)
    compression_modulus_mpa: float | None = Field(default=None, gt=0, le=1000)
    settlement_layers: list[SettlementLayer] = Field(default_factory=list, max_length=30)
    settlement_correction_factor: float | None = Field(default=None, gt=0, le=3)
    settlement_limit_mm: float | None = Field(default=None, gt=0, le=500)
    groundwater: GroundwaterDesignProfile
    base_friction_coefficient: float | None = Field(default=None, gt=0, le=1)
    report_name: str | None = Field(default=None, max_length=240)
    report_date: date | None = None
    catalog_versions: dict[str, str] = Field(
        default_factory=lambda: {"geotechnical_hints": GEOTECHNICAL_HINT_CATALOG_VERSION}
    )

    @model_validator(mode="after")
    def validate_stage(self) -> "ProjectGeotechnicalProfile":
        if self.stage == "scheme_estimate" and not self.regional_hint_id:
            raise ValueError("方案测算必须选择区域地勘提示并确认土质档")
        if self.stage == "project_check":
            if not (self.report_name or "").strip() or self.report_date is None:
                raise ValueError("工程校核必须填写勘察报告名称和日期")
            if (
                self.deformation_modulus_mpa is None
                and self.compression_modulus_mpa is None
                and not self.settlement_layers
            ):
                raise ValueError("工程校核必须提供至少一种沉降计算参数")
            if self.settlement_layers and (
                self.settlement_correction_factor is None or self.settlement_limit_mm is None
            ):
                raise ValueError("分层沉降计算必须填写沉降经验系数和允许沉降值")
            if self.groundwater.condition == "unknown":
                raise ValueError("工程校核不得使用未知地下水条件")
        return self


class RegionalGeotechnicalHint(BaseModel):
    id: str
    title: str
    region_scope: str
    geomorphology: str
    soil_class: str
    bearing_capacity_range_kpa: tuple[float, float]
    conservative_scheme_value_kpa: float
    groundwater_background: str
    source_reference: str
    verification_status: Literal["unverified", "independently_verified"] = "unverified"


class FoundationOption(BaseModel):
    id: str
    title: str
    category: Literal["spread", "strip", "combined", "eccentric_tie", "mat", "pile_cap"]
    suitable_scene_families: list[str]
    availability: Literal["public", "advanced", "planned"]
    boundaries: list[str]
    source_reference: str


class FoundationDesignSpecification(BaseModel):
    node_id: str
    foundation_system_id: str
    selection_source: Literal["recommended", "user_locked"]
    length_m: float = Field(ge=0.5, le=30)
    width_m: float = Field(ge=0.5, le=30)
    thickness_mm: float = Field(ge=200, le=5000)
    embedment_m: float = Field(ge=0, le=20)
    concrete_grade: str = Field(min_length=2, max_length=20)
    rebar_grade: str = Field(min_length=3, max_length=30)
    bar_diameter_mm: float = Field(ge=6, le=40)
    bar_spacing_mm: float = Field(ge=50, le=400)
    plan_shape: Literal["rectangular"] = "rectangular"
    section_shape: Literal["prismatic", "stepped", "tapered"] = "prismatic"
    left_projection_m: float | None = Field(default=None, ge=0.1, le=15)
    right_projection_m: float | None = Field(default=None, ge=0.1, le=15)
    front_projection_m: float | None = Field(default=None, ge=0.1, le=15)
    back_projection_m: float | None = Field(default=None, ge=0.1, le=15)
    steps: list[FoundationStep] = Field(default_factory=list, max_length=3)
    tapered_top_length_m: float | None = Field(default=None, ge=0.15, le=10)
    tapered_top_width_m: float | None = Field(default=None, ge=0.15, le=10)
    pedestal: PedestalSpecification | None = None
    reinforcement: FoundationReinforcementProfile | None = None
    group_id: str | None = Field(default=None, max_length=80)
    override_reason: str | None = Field(default=None, max_length=400)

    @model_validator(mode="after")
    def require_override_reason(self) -> "FoundationDesignSpecification":
        if self.selection_source == "user_locked" and not (self.override_reason or "").strip():
            raise ValueError("锁定基础尺寸时必须填写调整原因")
        if self.section_shape == "stepped" and not self.steps:
            raise ValueError("阶形基础必须填写 1 至 3 级台阶")
        if self.section_shape == "tapered" and (
            self.tapered_top_length_m is None or self.tapered_top_width_m is None
        ):
            raise ValueError("锥形基础必须填写顶台尺寸")
        return self


class DesignCandidateSet(BaseModel):
    target_node_id: str
    candidate_type: Literal["member", "foundation"]
    recommended: dict[str, object] | None
    alternatives: list[dict[str, object]] = Field(default_factory=list)
    iterations: list[dict[str, object]] = Field(default_factory=list)
    governing_check: str | None = None
    converged: bool
    failure_reason: str | None = None
    catalog_version: str


class SceneStructuralProfile(BaseModel):
    profile_version: Literal["1.0", "2.0", "3.0"] = "3.0"
    stage: Literal["scheme_estimate", "project_check"]
    exposure: SurfaceExposureProfile | None = None
    members: list[MemberSpecification] = Field(default_factory=list)
    member_groups: list[MemberGroupSpecification] = Field(default_factory=list)
    member_overrides: list[MemberSectionOverride] = Field(default_factory=list)
    foundations: list[FoundationDesignSpecification] = Field(default_factory=list)
    geometry: SceneGeometryProfile | None = None
    roof_assembly: RoofAssembly | None = None
    catalog_versions: dict[str, str] = Field(
        default_factory=lambda: {
            "steel_sections": STEEL_SECTION_CATALOG_VERSION,
            "foundation_systems": FOUNDATION_SYSTEM_CATALOG_VERSION,
        }
    )


def _section(entry_id: str, family: str, name: str, dims: dict[str, float]) -> SectionCatalogEntry:
    # The exact rolled/cold-formed product mass must be checked against the
    # selected supplier.  This geometric area is intentionally traceable and
    # therefore remains unverified.
    if family == "SHS":
        b, t = dims["b_mm"], dims["t_mm"]
        area = b * b - (b - 2 * t) ** 2
    elif family == "RHS":
        h, b, t = dims["h_mm"], dims["b_mm"], dims["t_mm"]
        area = b * h - (b - 2 * t) * (h - 2 * t)
    elif family == "CHS":
        d, t = dims["diameter_mm"], dims["t_mm"]
        area = 3.141592653589793 * (d * d - (d - 2 * t) ** 2) / 4
    else:
        h, b, tw, tf = dims["h_mm"], dims["b_mm"], dims["tw_mm"], dims["tf_mm"]
        area = 2 * b * tf + (h - 2 * tf) * tw
    return SectionCatalogEntry(
        id=entry_id,
        family=family,  # type: ignore[arg-type]
        designation=name,
        dimensions=dims,
        area_mm2=round(area, 2),
        self_weight_kn_m=round(area * 1e-6 * 78.5, 4),
        material_grades=["Q235B", "Q355B"],
        source_reference="GB/T 6728、GB/T 11263 几何系列候选；采用前核对供货资料",
    )


STEEL_SECTIONS = [
    _section("shs-100x4", "SHS", "方管 100×100×4", {"b_mm": 100, "t_mm": 4}),
    _section("shs-150x6", "SHS", "方管 150×150×6", {"b_mm": 150, "t_mm": 6}),
    _section("shs-200x8", "SHS", "方管 200×200×8", {"b_mm": 200, "t_mm": 8}),
    _section("rhs-150x100x5", "RHS", "矩形管 150×100×5", {"h_mm": 150, "b_mm": 100, "t_mm": 5}),
    _section("rhs-200x100x6", "RHS", "矩形管 200×100×6", {"h_mm": 200, "b_mm": 100, "t_mm": 6}),
    _section("rhs-300x150x8", "RHS", "矩形管 300×150×8", {"h_mm": 300, "b_mm": 150, "t_mm": 8}),
    _section("chs-114x5", "CHS", "圆管 Φ114×5", {"diameter_mm": 114, "t_mm": 5}),
    _section("chs-168x6", "CHS", "圆管 Φ168×6", {"diameter_mm": 168, "t_mm": 6}),
    _section("h-200x200x8x12", "H", "H 200×200×8×12", {"h_mm": 200, "b_mm": 200, "tw_mm": 8, "tf_mm": 12}),
    _section("h-300x200x8x12", "H", "H 300×200×8×12", {"h_mm": 300, "b_mm": 200, "tw_mm": 8, "tf_mm": 12}),
    _section("i-250x125x8x12", "I", "工字形 250×125×8×12", {"h_mm": 250, "b_mm": 125, "tw_mm": 8, "tf_mm": 12}),
]


GEOTECHNICAL_HINTS = [
    RegionalGeotechnicalHint(id="zj-coastal-soft-clay", title="浙江沿海平原—软黏土参考档", region_scope="宁波、温州、台州、嘉兴、绍兴等沿海或冲海积平原地貌参考", geomorphology="冲海积平原", soil_class="软塑至流塑黏性土", bearing_capacity_range_kpa=(60, 100), conservative_scheme_value_kpa=60, groundwater_background="地下水通常较浅且季节变化明显，必须由用户确认项目水位边界", source_reference="区域工程地质公开资料线索；目录尚未完成逐城市复核"),
    RegionalGeotechnicalHint(id="zj-inland-alluvial", title="浙江内陆平原—一般黏性土参考档", region_scope="杭州、金华、衢州等河湖相或冲洪积平原地貌参考", geomorphology="冲洪积/湖积平原", soil_class="可塑黏性土或中密粉土", bearing_capacity_range_kpa=(100, 180), conservative_scheme_value_kpa=100, groundwater_background="水位受河网、场地回填和季节影响，不以城市名称直接确定", source_reference="区域工程地质公开资料线索；目录尚未完成逐城市复核"),
    RegionalGeotechnicalHint(id="zj-mountain-residual", title="浙江山地丘陵—残积土参考档", region_scope="丽水、衢州、金华等山地丘陵地貌参考，不含填方边坡和岩溶", geomorphology="山地丘陵/残坡积地貌", soil_class="可塑至硬塑残积土", bearing_capacity_range_kpa=(160, 280), conservative_scheme_value_kpa=160, groundwater_background="坡地裂隙水和局部上层滞水差异大，城市资料包不能替代场地调查", source_reference="区域工程地质公开资料线索；目录尚未完成逐城市复核"),
]


FOUNDATION_OPTIONS = [
    FoundationOption(id="spread", title="柱下独立基础", category="spread", suitable_scene_families=["pergola-pavilion", "canopy", "signage-billboard", "entrance-frame", "boardwalk-platform"], availability="public", boundaries=["规则单柱或柱距较大的浅基础", "偏心或净距不足时应改用联合/拉梁方案"], source_reference="GB 55003-2021；GB 50007-2011"),
    FoundationOption(id="strip", title="条形基础", category="strip", suitable_scene_families=["landscape-wall-fence", "bench-planter"], availability="public", boundaries=["连续墙体或线性支承"], source_reference="GB 55003-2021；GB 50007-2011"),
    FoundationOption(id="combined", title="联合基础", category="combined", suitable_scene_families=["pergola-pavilion", "signage-billboard", "entrance-frame"], availability="advanced", boundaries=["相邻柱基础重叠或边界限制", "当前仅提供选型提示，计算模块待验证"], source_reference="GB 50007-2011"),
    FoundationOption(id="eccentric-tie", title="偏心基础＋拉梁", category="eccentric_tie", suitable_scene_families=["pergola-pavilion", "entrance-frame"], availability="advanced", boundaries=["临近红线或偏心柱", "地梁承担协调作用，不作为地基基础类型"], source_reference="GB 50007-2011"),
    FoundationOption(id="mat", title="规则整板/筏板", category="mat", suitable_scene_families=["water-feature-pool", "pergola-pavilion"], availability="planned", boundaries=["仅规则矩形池体或密集多柱场景", "异形大型地下结构不支持"], source_reference="GB 55003-2021；GB 50007-2011"),
    FoundationOption(id="pile-cap", title="桩承台", category="pile_cap", suitable_scene_families=["water-feature-pool", "landscape-bridge", "boardwalk-platform"], availability="planned", boundaries=["不得由城市土质自动推算单桩承载力", "必须依据勘察和试桩/设计资料"], source_reference="GB 55003-2021；JGJ 94-2008"),
]


STEEL_GRADES = [
    {"id": "Q235B", "title": "Q235B", "nominal_yield_mpa": 235, "thickness_mapping_required": True},
    {"id": "Q355B", "title": "Q355B", "nominal_yield_mpa": 355, "thickness_mapping_required": True},
    {"id": "Q390", "title": "Q390（待验证）", "nominal_yield_mpa": 390, "thickness_mapping_required": True},
    {"id": "Q420", "title": "Q420（待验证）", "nominal_yield_mpa": 420, "thickness_mapping_required": True},
    {"id": "Q460", "title": "Q460（待验证）", "nominal_yield_mpa": 460, "thickness_mapping_required": True},
]

REBAR_ITEMS = [
    {"grade": grade, "diameters_mm": [6, 8, 10, 12, 14, 16, 18, 20, 22, 25, 28, 32]}
    for grade in ["HPB300", "HRB400", "HRB500"]
]

ROOF_ASSEMBLIES = [
    RoofAssembly(id="none", title="无顶部覆盖", cover_type="none", layers=[], total_dead_load_kn_m2=0, reference_range_kn_m2=(0, 0), source_reference="无覆盖时不生成屋面恒载、检修荷载和屋面雪荷载"),
    RoofAssembly(id="louver-light", title="轻型金属百叶/格栅", cover_type="louver", layers=[RoofAssemblyLayer(name="金属百叶及连接件", surface_weight_kn_m2=0.15)], total_dead_load_kn_m2=0.15, reference_range_kn_m2=(0.10, 0.30), source_reference="方案参考范围；应按厂家构造与实际用量复核"),
    RoofAssembly(id="glass-canopy", title="夹层玻璃屋盖", cover_type="glass", layers=[RoofAssemblyLayer(name="夹层玻璃", thickness_mm=12.76, unit_weight_kn_m3=25, surface_weight_kn_m2=0.32), RoofAssemblyLayer(name="连接及密封构造", surface_weight_kn_m2=0.08)], total_dead_load_kn_m2=0.40, reference_range_kn_m2=(0.35, 0.75), source_reference="方案参考范围；玻璃厚度与支承体系须专项复核"),
    RoofAssembly(id="aluminum-panel", title="铝板轻型屋盖", cover_type="aluminum", layers=[RoofAssemblyLayer(name="铝板、龙骨及连接件", surface_weight_kn_m2=0.25)], total_dead_load_kn_m2=0.25, reference_range_kn_m2=(0.20, 0.45), source_reference="方案参考范围；按深化构造复核"),
    RoofAssembly(id="steel-panel", title="压型钢板屋盖", cover_type="steel", layers=[RoofAssemblyLayer(name="压型钢板及连接件", surface_weight_kn_m2=0.18)], total_dead_load_kn_m2=0.18, reference_range_kn_m2=(0.12, 0.35), source_reference="方案参考范围；按板型和檩条体系复核"),
    RoofAssembly(id="polycarbonate", title="阳光板屋盖", cover_type="polycarbonate", layers=[RoofAssemblyLayer(name="阳光板、龙骨及连接件", surface_weight_kn_m2=0.16)], total_dead_load_kn_m2=0.16, reference_range_kn_m2=(0.10, 0.30), source_reference="方案参考范围；按厂家构造复核"),
    RoofAssembly(id="timber-cover", title="木构覆盖", cover_type="timber", layers=[RoofAssemblyLayer(name="木面层及连接件", surface_weight_kn_m2=0.35)], total_dead_load_kn_m2=0.35, reference_range_kn_m2=(0.25, 0.70), source_reference="方案参考范围；按树种、含水率和实际厚度复核"),
]

SOIL_PRESETS = [
    {"id": "fill", "title": "填土", "bearing_range_kpa": [60, 100], "scheme_value_kpa": 60, "risk": "均匀性和压实质量不确定，宜谨慎采用"},
    {"id": "soft-clay", "title": "软塑黏土", "bearing_range_kpa": [60, 100], "scheme_value_kpa": 60, "risk": "沉降通常控制，方案值不能代替勘察"},
    {"id": "plastic-clay", "title": "可塑黏土", "bearing_range_kpa": [100, 180], "scheme_value_kpa": 100, "risk": "需核对含水状态和压缩性"},
    {"id": "silt", "title": "粉土", "bearing_range_kpa": [100, 180], "scheme_value_kpa": 100, "risk": "地下水与振动条件可能显著影响"},
    {"id": "loose-sand", "title": "松散砂土", "bearing_range_kpa": [80, 140], "scheme_value_kpa": 80, "risk": "需核对液化与地下水条件"},
    {"id": "medium-sand", "title": "中密砂土", "bearing_range_kpa": [160, 260], "scheme_value_kpa": 160, "risk": "需核对密实度和液化判别"},
    {"id": "dense-sand", "title": "密实砂土", "bearing_range_kpa": [240, 400], "scheme_value_kpa": 240, "risk": "实际采用值仍以勘察报告为准"},
    {"id": "strong-weathered-rock", "title": "强风化岩", "bearing_range_kpa": [300, 800], "scheme_value_kpa": 300, "risk": "风化差异大，应确认持力层连续性"},
    {"id": "medium-weathered-rock", "title": "中风化岩", "bearing_range_kpa": [800, 3000], "scheme_value_kpa": 800, "risk": "需核对岩体完整性和嵌岩条件"},
]

FOUNDATION_FORMS = [
    {"id": "spread-stepped", "title": "阶形独立基础", "section_shape": "stepped", "step_count_range": [1, 3], "supports_pedestal": True},
    {"id": "spread-tapered", "title": "锥形独立基础", "section_shape": "tapered", "supports_pedestal": True},
    {"id": "spread-prismatic", "title": "等厚独立基础", "section_shape": "prismatic", "supports_pedestal": True},
    {"id": "combined", "title": "双柱联合基础", "section_shape": "prismatic", "supports_pedestal": True, "availability": "advanced"},
    {"id": "eccentric-tie", "title": "偏心独立基础＋拉梁", "section_shape": "stepped", "supports_pedestal": True, "availability": "advanced"},
    {"id": "spread-grade-beam", "title": "独立基础＋联系梁", "section_shape": "stepped", "supports_pedestal": True, "availability": "advanced"},
]


def steel_section_catalog() -> dict[str, object]:
    return {"version": STEEL_SECTION_CATALOG_VERSION, "items": [item.model_dump(mode="json") for item in STEEL_SECTIONS]}


def geotechnical_hint_catalog() -> dict[str, object]:
    return {"version": GEOTECHNICAL_HINT_CATALOG_VERSION, "notice": "区域参考不是项目勘察值；必须由用户确认实际土质和地下水边界。", "items": [item.model_dump(mode="json") for item in GEOTECHNICAL_HINTS]}


def foundation_system_catalog() -> dict[str, object]:
    return {"version": FOUNDATION_SYSTEM_CATALOG_VERSION, "items": [item.model_dump(mode="json") for item in FOUNDATION_OPTIONS]}


def steel_grade_catalog() -> dict[str, object]:
    return {"version": STEEL_GRADE_CATALOG_VERSION, "verification_status": "unverified", "items": STEEL_GRADES}


def rebar_catalog() -> dict[str, object]:
    return {"version": REBAR_CATALOG_VERSION, "verification_status": "unverified", "items": REBAR_ITEMS}


def roof_assembly_catalog() -> dict[str, object]:
    return {"version": ROOF_ASSEMBLY_CATALOG_VERSION, "items": [item.model_dump(mode="json") for item in ROOF_ASSEMBLIES]}


def soil_preset_catalog() -> dict[str, object]:
    return {"version": SOIL_PRESET_CATALOG_VERSION, "notice": "仅用于方案测算，不能代替项目勘察值。", "items": SOIL_PRESETS}


def foundation_form_catalog() -> dict[str, object]:
    return {"version": FOUNDATION_FORM_CATALOG_VERSION, "verification_status": "unverified", "items": FOUNDATION_FORMS}


def recommend_spread_foundation(
    *,
    node_id: str,
    vertical_kn: float,
    moment_kn_m: float,
    bearing_capacity_kpa: float,
    max_plan_m: float = 6.0,
) -> DesignCandidateSet:
    """Produce a transparent scheme-level starting candidate.

    This is not a substitute for the foundation module checks.  It sizes the
    plan area for average pressure and the middle-third rule, then returns the
    discrete iterations so the full scene calculation can verify it.
    """
    if vertical_kn <= 0 or bearing_capacity_kpa <= 0:
        return DesignCandidateSet(target_node_id=node_id, candidate_type="foundation", recommended=None, converged=False, failure_reason="竖向压力和地基承载力必须大于零", catalog_version=FOUNDATION_SYSTEM_CATALOG_VERSION)
    target_area = vertical_kn / (0.85 * bearing_capacity_kpa)
    eccentricity = abs(moment_kn_m) / vertical_kn
    minimum_width = max(0.5, 6 * eccentricity)
    # Start from a compact rectangle instead of deriving one very long side
    # from the minimum middle-third width.  A small aspect-ratio bias makes the
    # candidate genuinely rectangular when moment is present, while retaining
    # a stable search for axial-load-dominated foundations.
    aspect_ratio = 1.0 + min(1.0, 6 * eccentricity / max(sqrt(target_area), 0.5))
    width = ceil(max(minimum_width, sqrt(target_area / aspect_ratio)) * 10) / 10
    length = ceil(max(0.5, sqrt(target_area * aspect_ratio)) * 10) / 10
    iterations: list[dict[str, object]] = []
    while max(length, width) <= max_plan_m + 1e-9:
        thickness = max(300, ceil((max(length, width) * 1000 / 10) / 50) * 50)
        q_average = vertical_kn / (length * width)
        middle_third_ok = eccentricity <= width / 6
        utilization = q_average / bearing_capacity_kpa
        iteration = {
            "length_m": round(length, 1),
            "width_m": round(width, 1),
            "thickness_mm": thickness,
            "bearing_utilization": round(utilization, 4),
            "middle_third_ok": middle_third_ok,
        }
        iterations.append(iteration)
        if utilization <= 0.85 and middle_third_ok:
            return DesignCandidateSet(target_node_id=node_id, candidate_type="foundation", recommended=iteration, alternatives=iterations[-3:-1], iterations=iterations, governing_check="地基平均压力/偏心中三分之一", converged=True, catalog_version=FOUNDATION_SYSTEM_CATALOG_VERSION)
        if length <= width:
            length = round(length + 0.1, 10)
        else:
            width = round(width + 0.1, 10)
    return DesignCandidateSet(target_node_id=node_id, candidate_type="foundation", recommended=None, alternatives=iterations[-2:], iterations=iterations, governing_check="地基平均压力/偏心中三分之一", converged=False, failure_reason=f"达到场景尺寸上限 {max_plan_m:.1f}m 仍不满足；未自动切换桩基", catalog_version=FOUNDATION_SYSTEM_CATALOG_VERSION)


def recommend_spread_foundation_from_reaction(
    *,
    foundation_instance_id: str,
    reaction: dict[str, float],
    bearing_capacity_kpa: float,
    initial_length_m: float,
    initial_width_m: float,
    initial_thickness_mm: float,
    pedestal: PedestalProfile | None = None,
    base_friction_coefficient: float = 0.30,
    max_plan_m: float = 6.0,
) -> DesignCandidateSet:
    """Size a rectangular scheme candidate from one saved support reaction.

    The reaction is the analysis-engine six-component support result.  The
    search checks biaxial soil pressure and scheme-level sliding, while
    deliberately leaving punching, bending and reinforcement as pending full
    foundation-module checks.
    """

    vertical = float(reaction.get("fz_kn", 0.0))
    horizontal = hypot(float(reaction.get("fx_kn", 0.0)), float(reaction.get("fy_kn", 0.0)))
    moment_x = abs(float(reaction.get("mx_kn_m", 0.0)))
    moment_y = abs(float(reaction.get("my_kn_m", 0.0)))
    if vertical <= 0:
        return DesignCandidateSet(
            target_node_id=foundation_instance_id,
            candidate_type="foundation",
            recommended=None,
            converged=False,
            governing_check="柱脚竖向反力",
            failure_reason="该柱脚没有向下压力或处于上拔状态，浅基础平面候选不能仅按承压生成。",
            catalog_version=FOUNDATION_SYSTEM_CATALOG_VERSION,
        )
    length = ceil(max(0.5, initial_length_m) * 10) / 10
    width = ceil(max(0.5, initial_width_m) * 10) / 10
    thickness = ceil(max(200.0, initial_thickness_mm) / 50) * 50
    pedestal_weight = 0.0
    if pedestal and pedestal.enabled:
        pedestal_weight = (
            float(pedestal.length_mm) / 1000
            * float(pedestal.width_mm) / 1000
            * float(pedestal.clear_height_mm) / 1000
            * 25.0
        )
    iterations: list[dict[str, object]] = []
    while max(length, width) <= max_plan_m + 1e-9:
        thickness = max(thickness, ceil(max(length, width) * 100 / 50) * 50)
        footing_weight = length * width * thickness / 1000 * 25.0
        effective_vertical = vertical + footing_weight + pedestal_weight
        average_pressure = effective_vertical / (length * width)
        qmax = average_pressure * (
            1 + 6 * moment_y / effective_vertical / length + 6 * moment_x / effective_vertical / width
        )
        qmin = average_pressure * (
            1 - 6 * moment_y / effective_vertical / length - 6 * moment_x / effective_vertical / width
        )
        sliding_ratio = (
            base_friction_coefficient * effective_vertical / horizontal
            if horizontal > 1e-9
            else 999.0
        )
        bearing_ok = qmax <= bearing_capacity_kpa
        contact_ok = qmin >= 0
        sliding_ok = sliding_ratio >= 1.30
        iteration = {
            "length_m": round(length, 1),
            "width_m": round(width, 1),
            "thickness_mm": thickness,
            "column_reaction_n_kn": round(vertical, 4),
            "column_reaction_v_kn": round(horizontal, 4),
            "column_reaction_mx_kn_m": round(moment_x, 4),
            "column_reaction_my_kn_m": round(moment_y, 4),
            "footing_self_weight_kn": round(footing_weight, 4),
            "pedestal_self_weight_kn": round(pedestal_weight, 4),
            "qmax_kpa": round(qmax, 4),
            "qmin_kpa": round(qmin, 4),
            "bearing_utilization": round(qmax / bearing_capacity_kpa, 4),
            "sliding_ratio": round(sliding_ratio, 4),
            "bearing_ok": bearing_ok,
            "full_contact_ok": contact_ok,
            "sliding_ok": sliding_ok,
            "pending_checks": ["冲切", "双向剪切", "弯曲", "X/Y配筋", "锚固", "沉降资料完整性"],
        }
        iterations.append(iteration)
        if bearing_ok and contact_ok and sliding_ok:
            return DesignCandidateSet(
                target_node_id=foundation_instance_id,
                candidate_type="foundation",
                recommended=iteration,
                alternatives=iterations[-3:-1],
                iterations=iterations,
                governing_check="双向偏心地基压力＋抗滑（其余构件验算待完成）",
                converged=True,
                catalog_version=FOUNDATION_SYSTEM_CATALOG_VERSION,
            )
        x_score = 6 * moment_y / effective_vertical / length
        y_score = 6 * moment_x / effective_vertical / width
        if not sliding_ok:
            if length <= width:
                length = round(length + 0.1, 10)
            else:
                width = round(width + 0.1, 10)
        elif x_score >= y_score:
            length = round(length + 0.1, 10)
        else:
            width = round(width + 0.1, 10)
    return DesignCandidateSet(
        target_node_id=foundation_instance_id,
        candidate_type="foundation",
        recommended=None,
        alternatives=iterations[-2:],
        iterations=iterations,
        governing_check="双向偏心地基压力＋抗滑",
        converged=False,
        failure_reason=f"达到场景尺寸上限 {max_plan_m:.1f}m 仍不满足；不会自动切换桩基。",
        catalog_version=FOUNDATION_SYSTEM_CATALOG_VERSION,
    )
