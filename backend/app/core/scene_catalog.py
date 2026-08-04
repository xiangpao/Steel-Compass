from __future__ import annotations

from .scene_schemas import (
    SceneCapability,
    SceneConnection,
    SceneFamily,
    SceneGraphTemplate,
    SceneLoadItem,
    SceneLoadPackage,
    SceneNode,
    SceneParameter,
    SceneVariant,
)


SCENE_CATALOG_VERSION = "CN-SCENE-2026.2"
SCENE_LOAD_PACKAGE_VERSION = "CN-SCENE-LOAD-2026.2"


def _number(
    key: str, label: str, unit: str, default: float, *, required: bool = True
) -> SceneParameter:
    return SceneParameter(
        key=key,
        label=label,
        value_type="number",
        unit=unit,
        default=default,
        required=required,
    )


def _choice(
    key: str, label: str, options: list[str], default: str
) -> SceneParameter:
    return SceneParameter(
        key=key,
        label=label,
        value_type="choice",
        options=options,
        default=default,
    )


def _node(
    node_id: str,
    label: str,
    role: str,
    module: str | None = None,
    *,
    maturity: str = "beta",
    applicability: str = "required",
    verification_status: str = "unverified",
    quick_assumption: str | None = None,
    description: str = "",
    input_bindings: dict[str, str] | None = None,
) -> SceneNode:
    return SceneNode(
        id=node_id,
        label=label,
        role=role,
        calculation_module=module,
        required=applicability == "required",
        applicability=applicability,
        maturity=maturity,
        verification_status=verification_status,
        quick_assumption=quick_assumption,
        description=description,
        input_bindings=input_bindings or {},
    )


def _connection(
    connection_id: str,
    source: str,
    target: str,
    transfer: str,
    *,
    output_unit: str | None = None,
    input_unit: str | None = None,
    support: str = "base",
    conversion_input_key: str | None = None,
    requires_source_trace: bool = False,
    description: str = "",
) -> SceneConnection:
    return SceneConnection(
        id=connection_id,
        source_node_id=source,
        target_node_id=target,
        transfer=transfer,
        output_unit=output_unit,
        input_unit=input_unit,
        support=support,
        conversion_input_key=conversion_input_key,
        requires_source_trace=requires_source_trace,
        description=description,
    )


def _graph(
    graph_id: str,
    nodes: list[SceneNode],
    connections: list[SceneConnection],
) -> SceneGraphTemplate:
    return SceneGraphTemplate(
        id=graph_id,
        version=SCENE_CATALOG_VERSION,
        nodes=nodes,
        connections=connections,
    )


def _load(
    load_id: str,
    label: str,
    kind: str,
    value_type: str,
    unit: str,
    source: str,
    target: str,
    *,
    minimum: float | None = None,
    default: float | None = None,
    maximum: float | None = None,
    distribution: str = "area",
    direction: str = "gravity",
    applicable_when: str = "当前场景默认适用；采用前须确认项目条件。",
    notes: str = "",
) -> SceneLoadItem:
    return SceneLoadItem(
        id=load_id,
        label=label,
        kind=kind,
        value_type=value_type,
        recommended_min=minimum,
        recommended_default=default,
        recommended_max=maximum,
        adopted_value=default,
        unit=unit,
        source_reference=source,
        applicable_when=applicable_when,
        distribution=distribution,
        direction=direction,
        application_target=target,
        confirmed=False,
        notes=notes,
    )


def _package(
    package_id: str, title: str, description: str, items: list[SceneLoadItem]
) -> SceneLoadPackage:
    return SceneLoadPackage(
        id=package_id,
        version=SCENE_LOAD_PACKAGE_VERSION,
        title=title,
        description=description,
        items=items,
    )


def _variant(
    variant_id: str,
    title: str,
    description: str,
    material_systems: list[str],
    parameters: list[SceneParameter],
    *,
    support_system: str,
    graph: SceneGraphTemplate,
    load_package: SceneLoadPackage,
    roof_form: str | None = None,
    availability: str = "public",
    capabilities: list[SceneCapability] | None = None,
    missing_capabilities: list[str] | None = None,
) -> SceneVariant:
    return SceneVariant(
        id=variant_id,
        title=title,
        description=description,
        material_systems=material_systems,
        parameters=parameters,
        availability=availability,
        support_system=support_system,
        roof_form=roof_form,
        graph_template=graph,
        load_package=load_package,
        capabilities=capabilities
        or [
            SceneCapability(
                material_system=material,
                support_system=support_system,
                graph_template_id=graph.id if availability == "public" else None,
                availability=availability,
                missing_capabilities=missing_capabilities or [],
            )
            for material in material_systems
        ],
        missing_capabilities=missing_capabilities or [],
    )


COMMON_FRAME_PARAMETERS = [
    _number("span_m", "跨度", "m", 4.0),
    _number("height_m", "柱高", "m", 3.0),
    _number("bay_spacing_m", "开间", "m", 3.0),
    _number("roof_width_m", "顶面宽度", "m", 3.0),
]

STEEL_SINGLE_SPAN_PERGOLA_PARAMETERS = [
    _number("span_m", "横向跨度", "m", 4.0),
    _number("height_m", "等高柱高度", "m", 3.0),
    _number("frame_spacing_m", "纵向框架间距", "m", 3.0),
    _number("purlin_spacing_m", "檩条间距", "m", 1.0),
    _choice("roof_form", "顶面形式", ["平顶"], "平顶"),
    _choice("support_system", "支承形式", ["双柱刚接落地"], "双柱刚接落地"),
]


ROOF_LOADS = [
    _load(
        "roof-finish",
        "覆盖层及附加恒载",
        "dead",
        "reference_range",
        "kN/m2",
        "按覆盖层材料密度、厚度和构造层计算",
        "roof_members",
        minimum=0.20,
        default=0.50,
        maximum=1.20,
        notes="结构构件自重由引擎自动计算，不应在此重复添加。",
    ),
    _load(
        "roof-maintenance",
        "不上人屋面检修荷载",
        "live",
        "fixed",
        "kN/m2",
        "GB 50009-2012 第5章；须按实际屋面类别核对",
        "roof_members",
        default=0.50,
        applicable_when="不上人屋面；集中检修荷载另行核对。",
    ),
    _load(
        "roof-wind-down",
        "向下风作用",
        "wind",
        "calculated",
        "kN/m2",
        "GB 50009-2012 第8章风荷载向导",
        "roof_members",
        direction="gravity",
        notes="由基本风压、体型系数、高度和地面粗糙度计算。",
    ),
    _load(
        "roof-wind-uplift",
        "风吸力 / 上拔",
        "wind",
        "calculated",
        "kN/m2",
        "GB 50009-2012 第8章风荷载向导",
        "roof_members",
        direction="uplift",
        notes="与向下风作用分为不同方向工况。",
    ),
    _load(
        "roof-snow",
        "屋面雪荷载",
        "snow",
        "calculated",
        "kN/m2",
        "GB 50009-2012 第7章及表 E.5",
        "roof_members",
        applicable_when="项目所在地存在雪荷载且屋面形式适用。",
    ),
]


PERGOLA_LOAD_PACKAGE = _package(
    "pergola-roof-default",
    "廊架 / 景亭场景荷载包",
    "顶面构造、检修、正负风和雪荷载；所有建议值可见且需确认。",
    ROOF_LOADS,
)

CANOPY_LOAD_PACKAGE = _package(
    "canopy-roof-default",
    "雨棚场景荷载包",
    "轻型覆盖层、检修、向下风、风吸力和雪荷载。",
    [
        ROOF_LOADS[0].model_copy(
            update={
                "id": "canopy-finish",
                "recommended_min": 0.15,
                "recommended_default": 0.35,
                "recommended_max": 0.80,
                "adopted_value": 0.35,
                "application_target": "secondary_beam",
            },
            deep=True,
        ),
        *[
            item.model_copy(
                update={"application_target": "secondary_beam"}, deep=True
            )
            for item in ROOF_LOADS[1:]
        ],
    ],
)

SIGN_LOAD_PACKAGE = _package(
    "sign-panel-default",
    "导视 / 广告牌场景荷载包",
    "面板自重、正负向风和偏心扭矩；不包含屋面检修荷载。",
    [
        _load(
            "panel-dead",
            "面板及安装构件自重",
            "dead",
            "reference_range",
            "kN/m2",
            "按面板、龙骨和连接件产品资料计算",
            "post",
            minimum=0.15,
            default=0.35,
            maximum=0.80,
        ),
        _load(
            "panel-wind-positive",
            "面板正向风压",
            "wind",
            "calculated",
            "kN/m2",
            "GB 50009-2012 第8章风荷载向导",
            "post",
            direction="x_positive",
        ),
        _load(
            "panel-wind-negative",
            "面板反向风压",
            "wind",
            "calculated",
            "kN/m2",
            "GB 50009-2012 第8章风荷载向导",
            "post",
            direction="x_negative",
        ),
        _load(
            "panel-eccentricity",
            "面板偏心作用",
            "dead",
            "calculated",
            "kN.m",
            "由面板重心、迎风中心与柱轴偏心距计算",
            "post",
            distribution="point",
            direction="torsion",
            applicable_when="面板中心与立柱轴线不重合。",
        ),
    ],
)

ENTRANCE_LOAD_PACKAGE = _package(
    "entrance-frame-default",
    "门楼 / 入口构架场景荷载包",
    "面层与招牌恒载、横向正负风和可选检修荷载。",
    [
        _load(
            "gate-finish",
            "门楣面层及招牌恒载",
            "dead",
            "reference_range",
            "kN/m2",
            "按饰面、基层和招牌产品资料计算",
            "gate_frame",
            minimum=0.30,
            default=0.80,
            maximum=2.00,
        ),
        _load(
            "gate-wind-positive",
            "入口构架正向风",
            "wind",
            "calculated",
            "kN/m2",
            "GB 50009-2012 第8章风荷载向导",
            "gate_frame",
            direction="x_positive",
        ),
        _load(
            "gate-wind-negative",
            "入口构架反向风",
            "wind",
            "calculated",
            "kN/m2",
            "GB 50009-2012 第8章风荷载向导",
            "gate_frame",
            direction="x_negative",
        ),
    ],
)

WALL_LOAD_PACKAGE = _package(
    "constrained-masonry-wall-default",
    "约束砌体景墙荷载包",
    "砌体及饰面自重、正反向风和可选顶部线荷载。",
    [
        _load(
            "masonry-dead",
            "砌体及抹灰自重",
            "dead",
            "calculated",
            "kN/m",
            "按砌块重度、墙厚、墙高和饰面厚度计算",
            "wall_foundation",
            distribution="line",
        ),
        _load(
            "wall-wind-positive",
            "墙面正向风压",
            "wind",
            "calculated",
            "kN/m2",
            "GB 50009-2012 第8章风荷载向导",
            "wall_foundation",
            direction="x_positive",
        ),
        _load(
            "wall-wind-negative",
            "墙面反向风压",
            "wind",
            "calculated",
            "kN/m2",
            "GB 50009-2012 第8章风荷载向导",
            "wall_foundation",
            direction="x_negative",
        ),
        _load(
            "wall-top-line",
            "压顶附加线荷载",
            "dead",
            "reference_range",
            "kN/m",
            "按压顶、灯具及附属构件产品资料计算",
            "wall_foundation",
            minimum=0.20,
            default=0.50,
            maximum=1.50,
            distribution="line",
        ),
    ],
)


def _steel_single_span_pergola_graph() -> SceneGraphTemplate:
    return _graph(
        "pergola-flat-single-steel-chain",
        [
            _node(
                "environment",
                "顶面恒载、活载与风雪",
                "load",
                maturity="beta",
                verification_status="unverified",
            ),
            _node(
                "roof_members",
                "钢檩条",
                "secondary_member",
                "steel_beam",
                input_bindings={
                    "span_m": "frame_spacing_m",
                    "tributary_width_m": "purlin_spacing_m",
                },
            ),
            _node(
                "main_frame",
                "横向门式框架",
                "primary_member",
                "portal_frame",
                input_bindings={
                    "span_m": "span_m",
                    "height_m": "height_m",
                    "purlin_spacing_m": "purlin_spacing_m",
                },
            ),
            _node("base_left", "左柱脚 / 底板锚栓", "connection", "steel_baseplate_anchor"),
            _node("base_right", "右柱脚 / 底板锚栓", "connection", "steel_baseplate_anchor"),
            _node("foundation_left", "左侧基础", "foundation", "spread_footing"),
            _node("foundation_right", "右侧基础", "foundation", "spread_footing"),
        ],
        [
            _connection("c1", "environment", "roof_members", "area_to_line", output_unit="kN/m", input_unit="kN/m"),
            _connection(
                "c2",
                "roof_members",
                "main_frame",
                "reaction_to_line",
                output_unit="kN",
                input_unit="kN",
                support="left",
                conversion_input_key="purlin_spacing_m",
                requires_source_trace=True,
                description="代表性檩条支座反力按檩条间距换算为横向框架梁线荷载。",
            ),
            _connection("c3", "main_frame", "base_left", "reaction_package", output_unit="kN", input_unit="kN", support="left", requires_source_trace=True),
            _connection("c4", "main_frame", "base_right", "reaction_package", output_unit="kN", input_unit="kN", support="right", requires_source_trace=True),
            _connection("c5", "base_left", "foundation_left", "reaction_package", output_unit="kN", input_unit="kN", requires_source_trace=True),
            _connection("c6", "base_right", "foundation_right", "reaction_package", output_unit="kN", input_unit="kN", requires_source_trace=True),
        ],
    )


def _wall_canopy_graph() -> SceneGraphTemplate:
    return _graph(
        "canopy-wall-cantilever-chain",
        [
            _node("environment", "覆盖层与风雪作用", "load", maturity="verified", verification_status="independently_verified"),
            _node("secondary_beam", "次梁 / 悬挑构件", "secondary_member", "steel_beam"),
            _node("wall_substrate", "墙体基材与边界", "column_wall", quick_assumption="快算仅确认基材类别和可锚固厚度，不评价既有墙体承载力。"),
            _node("wall_anchor", "墙体锚栓组", "connection", quick_assumption="快算按理想固定端传力；锚栓拉剪、边距和基材破坏须专项复核。"),
        ],
        [
            _connection("c1", "environment", "secondary_beam", "area_to_line", output_unit="kN/m", input_unit="kN/m"),
            _connection("c2", "secondary_beam", "wall_substrate", "reaction_package", output_unit="kN", input_unit="kN"),
            _connection("c3", "wall_substrate", "wall_anchor", "combination_package", output_unit="kN", input_unit="kN"),
        ],
    )


def _column_canopy_graph(graph_id: str) -> SceneGraphTemplate:
    return _graph(
        graph_id,
        [
            _node("environment", "覆盖层与风雪作用", "load", maturity="verified", verification_status="independently_verified"),
            _node("secondary_beam", "次梁", "secondary_member", "steel_beam"),
            _node("primary_system", "主梁 / 平面框架", "primary_member", "portal_frame"),
            _node("column", "支承立柱", "column_wall", "steel_column"),
            _node("base_connection", "柱脚与锚栓", "connection", quick_assumption="快算按固定柱脚传递反力；底板、锚栓和混凝土局部承压须专项复核。"),
            _node("foundation", "柱下独立基础", "foundation", "spread_footing"),
        ],
        [
            _connection("c1", "environment", "secondary_beam", "area_to_line", output_unit="kN/m", input_unit="kN/m"),
            _connection("c2", "secondary_beam", "primary_system", "reaction_package", output_unit="kN", input_unit="kN"),
            _connection("c3", "primary_system", "column", "reaction_package", output_unit="kN", input_unit="kN"),
            _connection("c4", "column", "base_connection", "reaction_package", output_unit="kN", input_unit="kN"),
            _connection("c5", "base_connection", "foundation", "reaction_package", output_unit="kN", input_unit="kN"),
        ],
    )


SIGN_GRAPH = _graph(
    "signage-complete-chain",
    [
        _node("wind_panel", "面板自重与正反向风", "load", maturity="verified", verification_status="independently_verified"),
        _node("post", "立柱", "column_wall", "steel_column"),
        _node("base_plate", "底板与锚栓", "connection", quick_assumption="快算按固定柱脚传力；底板和锚栓仅作反力接口，须专项复核。"),
        _node("foundation", "柱下独立基础", "foundation", "spread_footing"),
    ],
    [
        _connection("c1", "wind_panel", "post", "manual", output_unit="kN", input_unit="kN"),
        _connection("c2", "post", "base_plate", "reaction_package", output_unit="kN", input_unit="kN"),
        _connection("c3", "base_plate", "foundation", "reaction_package", output_unit="kN", input_unit="kN"),
    ],
)


WALL_GRAPH = _graph(
    "constrained-masonry-landscape-wall-chain",
    [
        _node("wall_loads", "墙体自重与正反向风", "load", maturity="verified", verification_status="independently_verified"),
        _node("masonry_infill", "砌体填充墙", "surface", quick_assumption="快算按构造柱间单向墙片分配面外风荷载；开洞和转角须复核。"),
        _node("construction_columns", "钢筋混凝土构造柱", "column_wall", quick_assumption="快算按构造柱间距分配墙片反力，不替代砌体结构专项设计。"),
        _node("cap_beam", "顶部压顶梁 / 系梁", "primary_member", quick_assumption="快算仅计入顶部约束与线荷载传递。"),
        _node("ground_beam", "地梁 / 基础梁", "primary_member", quick_assumption="快算按均匀传力至基础，不评价纵向不均匀沉降。"),
        _node("wall_foundation", "条形基础", "foundation", "strip_footing"),
    ],
    [
        _connection("c1", "wall_loads", "masonry_infill", "manual", output_unit="kN/m", input_unit="kN/m"),
        _connection("c2", "masonry_infill", "construction_columns", "reaction_package", output_unit="kN/m", input_unit="kN/m"),
        _connection("c3", "masonry_infill", "cap_beam", "reaction_package", output_unit="kN/m", input_unit="kN/m"),
        _connection("c4", "construction_columns", "ground_beam", "reaction_package", output_unit="kN/m", input_unit="kN/m"),
        _connection("c5", "cap_beam", "ground_beam", "reaction_package", output_unit="kN/m", input_unit="kN/m"),
        _connection("c6", "ground_beam", "wall_foundation", "reaction_package", output_unit="kN/m", input_unit="kN/m"),
    ],
)


ENTRANCE_GRAPH = _graph(
    "entrance-frame-complete-chain",
    [
        _node("gate_loads", "面层、招牌与正反向风", "load", maturity="verified", verification_status="independently_verified"),
        _node("gate_frame", "横梁 / 平面框架", "primary_member", "portal_frame"),
        _node("gate_base", "柱脚与锚栓", "connection", quick_assumption="快算按固定柱脚传力；底板和锚栓须专项复核。"),
        _node("gate_foundation", "柱下独立基础", "foundation", "spread_footing"),
    ],
    [
        _connection("c1", "gate_loads", "gate_frame", "manual", output_unit="kN/m", input_unit="kN/m"),
        _connection("c2", "gate_frame", "gate_base", "reaction_package", output_unit="kN", input_unit="kN"),
        _connection("c3", "gate_base", "gate_foundation", "reaction_package", output_unit="kN", input_unit="kN", support="left"),
    ],
)


def _development_graph(graph_id: str, load_label: str, body_label: str) -> SceneGraphTemplate:
    return _graph(
        graph_id,
        [
            _node("loads", load_label, "load", maturity="planned"),
            _node("body", body_label, "primary_member", maturity="planned"),
            _node("foundation", "基础 / 地基", "foundation", maturity="planned"),
        ],
        [
            _connection("c1", "loads", "body", "manual"),
            _connection("c2", "body", "foundation", "reaction_package"),
        ],
    )


PERGOLA_FLAT_GRAPH = _steel_single_span_pergola_graph()
PERGOLA_SLOPED_DEVELOPMENT_GRAPH = _development_graph(
    "pergola-sloped-development-chain", "坡顶荷载", "坡顶钢/木构架"
)
PERGOLA_MULTI_DEVELOPMENT_GRAPH = _development_graph(
    "pergola-multi-bay-development-chain", "多跨顶面荷载", "多跨及不同柱高构架"
)
CANOPY_WALL_GRAPH = _wall_canopy_graph()
CANOPY_SINGLE_GRAPH = _column_canopy_graph("canopy-single-row-chain")
CANOPY_DOUBLE_GRAPH = _column_canopy_graph("canopy-double-row-chain")


SCENE_FAMILIES: list[SceneFamily] = [
    SceneFamily(
        id="pergola-pavilion",
        title="廊架 / 景亭",
        description="顶面、檩条/椽条、主梁/刚架、柱脚和基础的完整传力链。",
        icon="pergola",
        maturity="beta",
        availability="public",
        default_variant_id="flat-single",
        variants=[
            _variant(
                "flat-single",
                "平顶单跨（等高钢构）",
                "一个代表性纵向单元：钢檩条、横向门式框架、左右柱脚及独立基础。",
                ["钢"],
                STEEL_SINGLE_SPAN_PERGOLA_PARAMETERS,
                support_system="双柱刚接落地",
                roof_form="平顶",
                graph=PERGOLA_FLAT_GRAPH,
                load_package=PERGOLA_LOAD_PACKAGE,
                capabilities=[
                    SceneCapability(
                        material_system="钢",
                        support_system="双柱刚接落地",
                        graph_template_id=PERGOLA_FLAT_GRAPH.id,
                        availability="public",
                    ),
                    SceneCapability(
                        material_system="木",
                        support_system="双柱落地",
                        availability="development",
                        missing_capabilities=["木框架", "木柱脚", "木构件多级反力传递"],
                    ),
                    SceneCapability(
                        material_system="钢木混合",
                        support_system="双柱落地",
                        availability="development",
                        missing_capabilities=["钢木连接", "木构件反力包", "混合体系验证"],
                    ),
                ],
            ),
            _variant(
                "mono-pitch",
                "单坡",
                "斜梁几何和坡向风雪映射尚未实现。",
                ["钢", "木", "钢木混合"],
                COMMON_FRAME_PARAMETERS + [_number("roof_slope_deg", "屋面坡度", "°", 8.0)],
                support_system="双柱落地",
                roof_form="单坡",
                graph=PERGOLA_SLOPED_DEVELOPMENT_GRAPH,
                load_package=PERGOLA_LOAD_PACKAGE,
                availability="development",
                missing_capabilities=["单坡框架几何", "坡向风雪作用", "斜梁反力映射"],
            ),
            _variant(
                "dual-pitch",
                "双坡",
                "双坡屋脊节点和分坡荷载映射尚未实现。",
                ["钢", "木", "钢木混合"],
                COMMON_FRAME_PARAMETERS + [_number("roof_slope_deg", "屋面坡度", "°", 15.0)],
                support_system="双柱落地",
                roof_form="双坡",
                graph=PERGOLA_SLOPED_DEVELOPMENT_GRAPH.model_copy(update={"id": "pergola-dual-pitch-development-chain"}, deep=True),
                load_package=PERGOLA_LOAD_PACKAGE,
                availability="development",
                missing_capabilities=["双坡框架几何", "屋脊节点", "分坡风雪作用"],
            ),
            _variant(
                "multi-bay",
                "多跨 / 不同柱高",
                "连续多跨、不同柱高和非对称反力分配尚未实现。",
                ["钢", "木", "钢木混合"],
                COMMON_FRAME_PARAMETERS + [_number("bay_count", "跨数", "跨", 2.0), _number("right_height_m", "右柱高", "m", 3.0)],
                support_system="多柱落地",
                roof_form="平顶",
                graph=PERGOLA_MULTI_DEVELOPMENT_GRAPH,
                load_package=PERGOLA_LOAD_PACKAGE,
                availability="development",
                missing_capabilities=["参数化多跨框架", "不同柱高", "非对称支座反力"],
            ),
        ],
        graph_template=PERGOLA_FLAT_GRAPH,
        boundaries=["不支持任意三维自由建模", "连接按快算假定闭合时必须在报告中列明待复核项"],
    ),
    SceneFamily(
        id="canopy",
        title="雨棚",
        description="墙附悬挑和柱支承雨棚采用不同的条件化传力链。",
        icon="canopy",
        maturity="beta",
        availability="public",
        default_variant_id="wall-cantilever",
        variants=[
            _variant("wall-cantilever", "墙附悬挑", "墙体与锚栓真实验算尚未实现。", ["钢"], [_number("cantilever_m", "悬挑长度", "m", 1.8), _number("width_m", "雨棚宽度", "m", 3.0), _choice("wall_substrate", "墙体基材", ["钢筋混凝土", "实心砌体", "其他/待鉴定"], "钢筋混凝土")], support_system="墙体锚固", roof_form="平顶", graph=CANOPY_WALL_GRAPH, load_package=CANOPY_LOAD_PACKAGE, availability="development", missing_capabilities=["既有墙体承载力", "锚栓组", "墙体基材破坏"]),
            _variant("single-row", "单排柱", "柱脚锚栓和单排框架传力尚未闭合。", ["钢", "木"], COMMON_FRAME_PARAMETERS, support_system="单排柱", roof_form="平顶", graph=CANOPY_SINGLE_GRAPH, load_package=CANOPY_LOAD_PACKAGE, availability="development", missing_capabilities=["单排框架", "柱脚锚栓", "材料体系映射"]),
            _variant("double-row", "双排柱", "双排框架和材料体系尚未真实映射。", ["钢", "木"], COMMON_FRAME_PARAMETERS, support_system="双排柱", roof_form="平顶", graph=CANOPY_DOUBLE_GRAPH, load_package=CANOPY_LOAD_PACKAGE, availability="development", missing_capabilities=["双排框架", "柱脚锚栓", "材料体系映射"]),
        ],
        graph_template=CANOPY_WALL_GRAPH,
        boundaries=["墙附式必须提供墙体基材和锚固资料", "墙附式不生成基础节点或基础输入"],
    ),
    SceneFamily(
        id="signage-billboard",
        title="导视 / 广告牌",
        description="面板荷载、立柱、底板锚栓和基础的完整传力链。",
        icon="sign",
        maturity="beta",
        availability="public",
        default_variant_id="single-post",
        variants=[
            _variant("single-post", "单柱", "面板至柱脚锚栓的真实传力尚未闭合。", ["钢"], [_number("panel_width_m", "面板宽度", "m", 1.2), _number("panel_height_m", "面板高度", "m", 0.8), _number("post_height_m", "立柱高度", "m", 2.5)], support_system="单柱落地", graph=SIGN_GRAPH, load_package=SIGN_LOAD_PACKAGE, availability="development", missing_capabilities=["面板风荷载转柱内力", "底板锚栓", "组合一致反力"]),
            _variant("double-post", "双柱", "双柱分配模型尚未实现。", ["钢"], [_number("panel_width_m", "面板宽度", "m", 2.4), _number("panel_height_m", "面板高度", "m", 1.2), _number("post_spacing_m", "柱间距", "m", 1.6)], support_system="双柱落地", graph=SIGN_GRAPH.model_copy(update={"id": "signage-double-post-chain"}, deep=True), load_package=SIGN_LOAD_PACKAGE, availability="development", missing_capabilities=["双柱荷载分配", "底板锚栓", "双基础反力"]),
            _variant("ground-mounted", "落地式", "落地底座体系尚未实现。", ["钢", "混凝土"], [_number("panel_width_m", "面板宽度", "m", 2.0), _number("panel_height_m", "面板高度", "m", 1.5)], support_system="底座落地", graph=SIGN_GRAPH.model_copy(update={"id": "signage-ground-mounted-chain"}, deep=True), load_package=SIGN_LOAD_PACKAGE, availability="development", missing_capabilities=["落地底座", "混凝土构件", "抗倾覆传力"]),
            _variant("eccentric-panel", "偏心 / 倾斜面板", "偏心、倾斜和扭矩传递尚未实现。", ["钢"], [_number("panel_width_m", "面板宽度", "m", 1.5), _number("eccentricity_m", "面板偏心距", "m", 0.3), _number("tilt_deg", "面板倾角", "°", 8.0)], support_system="单柱落地", graph=SIGN_GRAPH.model_copy(update={"id": "signage-eccentric-chain"}, deep=True), load_package=SIGN_LOAD_PACKAGE, availability="development", missing_capabilities=["偏心面板", "倾斜风作用", "扭矩传递"]),
        ],
        graph_template=SIGN_GRAPH,
        boundaries=["底板与锚栓快算仅传递反力，不替代连接设计", "桩基不在首批公开范围"],
    ),
    SceneFamily(
        id="landscape-wall-fence",
        title="景墙 / 围墙",
        description="默认采用砌体填充、钢筋混凝土构造柱、压顶/系梁、地梁和基础。",
        icon="wall",
        maturity="beta",
        availability="public",
        default_variant_id="constrained-masonry",
        variants=[
            _variant("constrained-masonry", "约束砌体景墙", "墙片、构造柱和地梁尚无真实构件验算。", ["砌体+混凝土"], [_number("height_m", "墙高", "m", 2.0), _number("thickness_mm", "墙厚", "mm", 240.0), _number("column_spacing_m", "构造柱间距", "m", 3.0)], support_system="地梁+条形基础", graph=WALL_GRAPH, load_package=WALL_LOAD_PACKAGE, availability="development", missing_capabilities=["砌体墙片", "构造柱", "地梁及压顶梁"]),
            _variant("concrete-straight", "现浇混凝土墙", "现浇墙面外受弯与裂缝验算尚未实现。", ["混凝土"], [_number("height_m", "墙高", "m", 2.0), _number("thickness_mm", "墙厚", "mm", 200.0)], support_system="条形基础", graph=WALL_GRAPH.model_copy(update={"id": "rc-landscape-wall-chain"}, deep=True), load_package=WALL_LOAD_PACKAGE, availability="development", missing_capabilities=["混凝土墙", "裂缝验算", "墙基传力"]),
            _variant("steel-infill", "钢立柱轻质填充墙", "填充面层至钢柱和独立基础的传力尚未实现。", ["钢", "钢木混合"], [_number("height_m", "墙高", "m", 2.4), _number("post_spacing_m", "柱间距", "m", 2.0)], support_system="立柱独立基础", graph=WALL_GRAPH.model_copy(update={"id": "steel-infill-wall-chain"}, deep=True), load_package=WALL_LOAD_PACKAGE, availability="development", missing_capabilities=["轻质面层", "钢柱脚", "独立基础链"]),
            _variant("plain-masonry", "纯砌体低墙（专业）", "砌体稳定与构造适用范围尚未映射。", ["砌体"], [_number("height_m", "墙高", "m", 1.2), _number("thickness_mm", "墙厚", "mm", 240.0)], support_system="条形基础", graph=WALL_GRAPH.model_copy(update={"id": "plain-masonry-wall-chain"}, deep=True), load_package=WALL_LOAD_PACKAGE, availability="development", missing_capabilities=["砌体稳定", "构造限制", "规范适用范围"]),
        ],
        graph_template=WALL_GRAPH,
        boundaries=["不覆盖纵向不均匀沉降、复杂开洞和复杂地基梁效应", "纯砌体仅限专业人员核定的适用范围"],
    ),
    SceneFamily(
        id="entrance-frame",
        title="门楼 / 入口构架",
        description="面层和招牌作用传至横梁/框架、柱脚和基础。",
        icon="gate",
        maturity="beta",
        availability="public",
        default_variant_id="single-span",
        variants=[
            _variant("single-span", "单跨门楼", "面层、柱脚锚栓和材料体系尚未形成真实闭环。", ["钢", "混凝土"], COMMON_FRAME_PARAMETERS, support_system="双柱落地", graph=ENTRANCE_GRAPH, load_package=ENTRANCE_LOAD_PACKAGE, availability="development", missing_capabilities=["面层荷载映射", "柱脚锚栓", "混凝土框架"]),
            _variant("multi-span", "多跨门楼", "多跨模型尚未实现。", ["钢", "混凝土"], COMMON_FRAME_PARAMETERS + [_number("bay_count", "跨数", "跨", 2.0)], support_system="多柱落地", graph=ENTRANCE_GRAPH.model_copy(update={"id": "entrance-multi-span-chain"}, deep=True), load_package=ENTRANCE_LOAD_PACKAGE, availability="development", missing_capabilities=["多跨框架", "多支座反力", "柱脚锚栓"]),
            _variant("eccentric-lintel", "偏心门楣", "偏心扭矩传递尚未实现。", ["钢"], COMMON_FRAME_PARAMETERS + [_number("eccentricity_m", "偏心距", "m", 0.5)], support_system="双柱落地", graph=ENTRANCE_GRAPH.model_copy(update={"id": "entrance-eccentric-chain"}, deep=True), load_package=ENTRANCE_LOAD_PACKAGE, availability="development", missing_capabilities=["偏心门楣", "扭矩传递", "柱脚锚栓"]),
            _variant("unequal-columns", "不同柱高", "非对称框架几何尚未实现。", ["钢"], COMMON_FRAME_PARAMETERS + [_number("right_height_m", "右柱高", "m", 3.6)], support_system="双柱落地", graph=ENTRANCE_GRAPH.model_copy(update={"id": "entrance-unequal-column-chain"}, deep=True), load_package=ENTRANCE_LOAD_PACKAGE, availability="development", missing_capabilities=["不同柱高", "非对称框架", "柱脚锚栓"]),
        ],
        graph_template=ENTRANCE_GRAPH,
        boundaries=["偏心和不同柱高按参数化二维模型处理", "连接快算假定必须在报告中列明"],
    ),
]


DEVELOPMENT_DEPENDENCIES = {
    "boardwalk-platform": [
        "木面板单向分配",
        "钢次梁与主梁多级反力包",
        "钢柱脚与独立基础",
    ],
    "water-feature-pool": [
        "水压力与土压力",
        "地下水浮力与抗浮组合",
        "钢筋混凝土池壁",
        "池底板与地基接触",
    ],
}


for family_id, title, description, icon, variants, load_label, body_label in [
    ("boardwalk-platform", "栈道 / 平台", "面层至基础的完整平台链路。", "platform", [("straight", "直线栈道"), ("viewing-platform", "观景平台")], "面层与使用荷载", "板、梁与柱墩"),
    ("bench-planter", "坐凳 / 树池", "坐凳和树池将拆分为不同传力链。", "bench", [("bench", "坐凳"), ("planter", "树池")], "使用荷载 / 覆土", "座板 / 池壁"),
    ("water-feature-pool", "水景池体", "池壁、底板、抗浮与地基的整体计算。", "pool", [("rect-above", "矩形地上池"), ("rect-buried", "矩形地下池")], "水土压力与浮力", "池壁与底板"),
    ("landscape-bridge", "小型景观桥", "人行桥面至桥台、墩柱和基础。", "bridge", [("single-straight", "单跨直桥"), ("multi-span", "参数化多跨")], "桥面与人群荷载", "桥面与纵横梁"),
    ("retaining-facility", "挡土设施", "土水压力至墙身和基础。", "retaining", [("cantilever-rc", "钢筋混凝土悬臂式"), ("gravity", "重力式")], "土水压力与附加荷载", "墙身 / 挡板"),
]:
    graph = _development_graph(f"{family_id}-development-chain", load_label, body_label)
    package = _package(
        f"{family_id}-development-loads",
        f"{title}荷载包（开发中）",
        "数据结构已预留，未完成验证前不可创建场景实例。",
        [],
    )
    SCENE_FAMILIES.append(
        SceneFamily(
            id=family_id,
            title=title,
            description=description,
            icon=icon,
            maturity="planned",
            availability="development",
            default_variant_id=variants[0][0],
            variants=[
                _variant(
                    variant_id,
                    variant_title,
                    (
                        "首版限定为水平直线、木面板、钢次梁/主梁、钢柱、柱脚和独立基础。"
                        if family_id == "boardwalk-platform" and variant_id == "straight"
                        else "该变体正在开发，当前仅展示范围。"
                    ),
                    (["木面板+钢构"] if family_id == "boardwalk-platform" and variant_id == "straight" else ["待定"]),
                    [],
                    support_system="待验证",
                    graph=graph.model_copy(
                        update={"id": f"{family_id}-{variant_id}-development-chain"},
                        deep=True,
                    ),
                    load_package=package,
                    availability="development",
                    missing_capabilities=DEVELOPMENT_DEPENDENCIES.get(
                        family_id, ["完整计算图", "规范映射", "独立验证"]
                    ),
                )
                for variant_id, variant_title in variants
            ],
            graph_template=graph,
            boundaries=[
                "当前仅展示规划范围，不允许创建实例或输出结论",
                "依赖：" + "、".join(
                    DEVELOPMENT_DEPENDENCIES.get(
                        family_id, ["完整计算图", "规范映射", "独立验证"]
                    )
                ),
            ],
        )
    )


SCENE_FAMILIES_BY_ID = {item.id: item for item in SCENE_FAMILIES}


def get_scene_family(family_id: str) -> SceneFamily | None:
    return SCENE_FAMILIES_BY_ID.get(family_id)


def get_scene_variant(family: SceneFamily, variant_id: str) -> SceneVariant | None:
    return next((item for item in family.variants if item.id == variant_id), None)


def instantiate_scene_graph(
    family: SceneFamily, variant_id: str
) -> SceneGraphTemplate:
    variant = get_scene_variant(family, variant_id)
    if variant is None:
        raise KeyError(variant_id)
    return (variant.graph_template or family.graph_template).model_copy(deep=True)
