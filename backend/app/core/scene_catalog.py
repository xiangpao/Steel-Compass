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


SCENE_CATALOG_VERSION = "3.2"
SCENE_LOAD_PACKAGE_VERSION = "3.2"


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


# ---- 3.2 快算与专业验证门控场景 -----------------------------------------
# The catalog above intentionally keeps the wider roadmap visible.  The
# following replacements promote only variants whose graph has real module
# bindings and a usable load package.  Development variants remain in the
# family so users can see the boundary without accidentally entering them.


def _roof_scene_package(
    package_id: str,
    title: str,
    target: str,
    *,
    finish_default: float = 0.50,
) -> SceneLoadPackage:
    return _package(
        package_id,
        title,
        "覆盖层、使用、正负风和雪荷载；建议值可覆盖但必须确认来源。",
        [
            _load(
                f"{package_id}-finish",
                "覆盖层及附加恒载",
                "dead",
                "reference_range",
                "kN/m2",
                "按覆盖层材料密度、厚度和构造层计算",
                target,
                minimum=0.20,
                default=finish_default,
                maximum=1.20,
                notes="结构构件自重由各构件自动计入，不能重复添加。",
            ),
            _load(
                f"{package_id}-live",
                "不上人屋面检修荷载",
                "live",
                "fixed",
                "kN/m2",
                "GB 50009-2012 第5章，按屋面类别复核",
                target,
                default=0.50,
                applicable_when="不上人屋面；集中检修荷载另行核对。",
            ),
            _load(
                f"{package_id}-wind-down",
                "向下风作用",
                "wind",
                "calculated",
                "kN/m2",
                "GB 50009-2012 第8章风荷载向导",
                target,
                default=0.50,
                direction="gravity",
                notes="快算默认值仅用于方案筛查，专业模式需地点和体型系数。",
            ),
            _load(
                f"{package_id}-wind-up",
                "风吸力 / 上拔",
                "wind",
                "calculated",
                "kN/m2",
                "GB 50009-2012 第8章风荷载向导",
                target,
                default=0.50,
                direction="uplift",
            ),
            _load(
                f"{package_id}-snow",
                "屋面雪荷载",
                "snow",
                "calculated",
                "kN/m2",
                "GB 50009-2012 第7章及表E.5",
                target,
                default=0.30,
                applicable_when="项目所在地存在雪荷载且屋面形式适用；无雪地区须选择不适用并记录依据。",
            ),
        ],
    )


BOARDWALK_GRAPH = _graph(
    "boardwalk-straight-steel-chain",
    [
        _node("deck_loads", "面层与人群荷载", "load"),
        _node("deck", "木面板", "surface", "timber_deck_panel", input_bindings={"span_m": "secondary_spacing_m", "strip_width_m": "panel_unit_width_m"}),
        _node("secondary", "钢次梁", "secondary_member", "steel_beam", input_bindings={"span_m": "primary_span_m", "tributary_width_m": "secondary_spacing_m", "reaction_conversion_spacing_m": "panel_unit_width_m"}),
        _node("primary", "钢主梁", "primary_member", "steel_beam", input_bindings={"span_m": "main_span_m", "tributary_width_m": "primary_spacing_m", "reaction_conversion_spacing_m": "secondary_spacing_m"}),
        _node("column_left", "左侧钢柱", "column_wall", "steel_column", input_bindings={"height_m": "column_height_m"}),
        _node("column_right", "右侧钢柱", "column_wall", "steel_column", input_bindings={"height_m": "column_height_m"}),
        _node("base_left", "左柱脚 / 底板锚栓", "connection", "steel_baseplate_anchor"),
        _node("base_right", "右柱脚 / 底板锚栓", "connection", "steel_baseplate_anchor"),
        _node("foundation_left", "左侧独立基础", "foundation", "spread_footing"),
        _node("foundation_right", "右侧独立基础", "foundation", "spread_footing"),
    ],
    [
        _connection("bw-0", "deck_loads", "deck", "manual"),
        _connection("bw-1", "deck", "secondary", "reaction_to_line", output_unit="kN", input_unit="kN", support="left", conversion_input_key="reaction_conversion_spacing_m", requires_source_trace=True),
        _connection("bw-2", "secondary", "primary", "reaction_to_line", output_unit="kN", input_unit="kN", support="left", conversion_input_key="reaction_conversion_spacing_m", requires_source_trace=True),
        _connection("bw-3", "primary", "column_left", "reaction_package", output_unit="kN", input_unit="kN", support="left", requires_source_trace=True),
        _connection("bw-4", "primary", "column_right", "reaction_package", output_unit="kN", input_unit="kN", support="right", requires_source_trace=True),
        _connection("bw-5", "column_left", "base_left", "reaction_package", output_unit="kN", input_unit="kN", requires_source_trace=True),
        _connection("bw-6", "column_right", "base_right", "reaction_package", output_unit="kN", input_unit="kN", requires_source_trace=True),
        _connection("bw-7", "base_left", "foundation_left", "reaction_package", output_unit="kN", input_unit="kN", requires_source_trace=True),
        _connection("bw-8", "base_right", "foundation_right", "reaction_package", output_unit="kN", input_unit="kN", requires_source_trace=True),
    ],
)

BOARDWALK_LOAD_PACKAGE = _package(
    "boardwalk-straight-loads",
    "直线栈道荷载包",
    "木面层自重、人员使用荷载、可选风雪作用。",
    [
        _load("boardwalk-finish", "木面层及铺装恒载", "dead", "reference_range", "kN/m2", "按面层和铺装构造计算", "deck", minimum=0.30, default=0.50, maximum=1.20),
        _load("boardwalk-live", "人行及观景使用荷载", "live", "fixed", "kN/m2", "GB 50009-2012；按人行平台类别复核", "deck", default=3.50),
        _load("boardwalk-snow", "栈道积雪作用", "snow", "calculated", "kN/m2", "GB 50009-2012 第7章", "deck", default=0.30, applicable_when="露天且项目所在地存在雪荷载。"),
    ],
)

CANOPY_SINGLE_GRAPH_PUBLIC = _graph(
    "canopy-single-row-steel-chain",
    [
        _node("roof_loads", "覆盖层与风雪作用", "load", quick_assumption="荷载包中的最终采用值和来源已确认。"),
        _node("secondary", "悬挑钢次梁", "secondary_member", "steel_beam", input_bindings={"span_m": "cantilever_m", "tributary_width_m": "width_m", "support": "support"}),
        _node("column", "单排钢柱", "column_wall", "steel_column", input_bindings={"height_m": "column_height_m"}),
        _node("base_connection", "柱脚 / 底板锚栓", "connection", "steel_baseplate_anchor"),
        _node("foundation", "柱下独立基础", "foundation", "spread_footing"),
    ],
    [
        _connection("cs-1", "roof_loads", "secondary", "manual"),
        _connection("cs-2", "secondary", "column", "reaction_package", output_unit="kN", input_unit="kN", requires_source_trace=True),
        _connection("cs-3", "column", "base_connection", "reaction_package", output_unit="kN", input_unit="kN", requires_source_trace=True),
        _connection("cs-4", "base_connection", "foundation", "reaction_package", output_unit="kN", input_unit="kN", requires_source_trace=True),
    ],
)

CANOPY_DOUBLE_GRAPH_PUBLIC = _graph(
    "canopy-double-row-steel-chain",
    [
        _node("roof_loads", "覆盖层与风雪作用", "load"),
        _node("secondary", "钢次梁", "secondary_member", "steel_beam", input_bindings={"span_m": "main_span_m", "tributary_width_m": "secondary_spacing_m", "reaction_conversion_spacing_m": "secondary_spacing_m"}),
        _node("primary", "双排柱横向框架", "primary_member", "portal_frame", input_bindings={"span_m": "frame_span_m", "height_m": "column_height_m", "tributary_width_m": "frame_spacing_m", "reaction_conversion_spacing_m": "secondary_spacing_m"}),
        _node("base_left", "左柱脚 / 底板锚栓", "connection", "steel_baseplate_anchor"),
        _node("base_right", "右柱脚 / 底板锚栓", "connection", "steel_baseplate_anchor"),
        _node("foundation_left", "左侧独立基础", "foundation", "spread_footing"),
        _node("foundation_right", "右侧独立基础", "foundation", "spread_footing"),
    ],
    [
        _connection("cd-1", "roof_loads", "secondary", "manual"),
        _connection("cd-2", "secondary", "primary", "reaction_to_line", output_unit="kN", input_unit="kN", support="left", conversion_input_key="reaction_conversion_spacing_m", requires_source_trace=True),
        _connection("cd-3", "primary", "base_left", "reaction_package", output_unit="kN", input_unit="kN", support="left", requires_source_trace=True),
        _connection("cd-4", "primary", "base_right", "reaction_package", output_unit="kN", input_unit="kN", support="right", requires_source_trace=True),
        _connection("cd-5", "base_left", "foundation_left", "reaction_package", output_unit="kN", input_unit="kN", requires_source_trace=True),
        _connection("cd-6", "base_right", "foundation_right", "reaction_package", output_unit="kN", input_unit="kN", requires_source_trace=True),
    ],
)

ENTRANCE_GRAPH_PUBLIC = _graph(
    "entrance-single-span-steel-chain",
    [
        _node("gate_loads", "面层、招牌与正反向风", "load"),
        _node("gate_frame", "单跨门式框架", "primary_member", "portal_frame", input_bindings={"span_m": "span_m", "height_m": "height_m", "tributary_width_m": "bay_spacing_m"}),
        _node("gate_base_left", "左柱脚 / 底板锚栓", "connection", "steel_baseplate_anchor"),
        _node("gate_base_right", "右柱脚 / 底板锚栓", "connection", "steel_baseplate_anchor"),
        _node("gate_foundation_left", "左侧独立基础", "foundation", "spread_footing"),
        _node("gate_foundation_right", "右侧独立基础", "foundation", "spread_footing"),
    ],
    [
        _connection("eg-1", "gate_loads", "gate_frame", "manual"),
        _connection("eg-2", "gate_frame", "gate_base_left", "reaction_package", output_unit="kN", input_unit="kN", support="left", requires_source_trace=True),
        _connection("eg-3", "gate_frame", "gate_base_right", "reaction_package", output_unit="kN", input_unit="kN", support="right", requires_source_trace=True),
        _connection("eg-4", "gate_base_left", "gate_foundation_left", "reaction_package", output_unit="kN", input_unit="kN", requires_source_trace=True),
        _connection("eg-5", "gate_base_right", "gate_foundation_right", "reaction_package", output_unit="kN", input_unit="kN", requires_source_trace=True),
    ],
)

SIGN_GRAPH_PUBLIC = _graph(
    "signage-single-post-steel-chain",
    [
        _node("wind_panel", "面板正负面风荷载", "load"),
        _node("post", "钢悬臂立柱", "column_wall", "steel_cantilever_post", input_bindings={"height_m": "height_m", "panel_area_m2": "panel_area_m2", "panel_cg_height_m": "panel_cg_height_m", "panel_eccentricity_m": "panel_eccentricity_m"}),
        _node("base_plate", "底板与锚栓", "connection", "steel_baseplate_anchor"),
        _node("foundation", "柱下独立基础", "foundation", "spread_footing"),
    ],
    [
        _connection("sg-1", "wind_panel", "post", "manual"),
        _connection("sg-2", "post", "base_plate", "reaction_package", output_unit="kN", input_unit="kN", requires_source_trace=True),
        _connection("sg-3", "base_plate", "foundation", "reaction_package", output_unit="kN", input_unit="kN", requires_source_trace=True),
    ],
)

WALL_GRAPH_PUBLIC = _graph(
    "constrained-masonry-wall-real-chain",
    [
        _node("wall_loads", "砌体自重与正反向风", "load"),
        _node("masonry_infill", "砌体填充墙片", "surface", "masonry_wall", input_bindings={"height_m": "height_m", "thickness_mm": "thickness_mm", "column_spacing_m": "column_spacing_m"}),
        _node("construction_columns", "钢筋混凝土构造柱", "column_wall", "concrete_column", input_bindings={"height_m": "height_m"}),
        _node("cap_beam", "顶部压顶梁 / 系梁", "primary_member", "concrete_beam", input_bindings={"span_m": "column_spacing_m", "tributary_width_m": "wall_length_m", "reaction_conversion_spacing_m": "column_spacing_m"}),
        _node("ground_beam", "地梁 / 基础梁", "primary_member", "concrete_beam", input_bindings={"span_m": "column_spacing_m", "tributary_width_m": "wall_length_m", "reaction_conversion_spacing_m": "column_spacing_m"}),
        _node("wall_foundation", "墙下条形基础", "foundation", "strip_footing"),
    ],
    [
        _connection("wm-1", "wall_loads", "masonry_infill", "manual"),
        _connection("wm-2", "masonry_infill", "construction_columns", "reaction_package", output_unit="kN", input_unit="kN", support="left", requires_source_trace=True),
        _connection("wm-3", "construction_columns", "cap_beam", "reaction_to_line", output_unit="kN", input_unit="kN", conversion_input_key="reaction_conversion_spacing_m", requires_source_trace=True),
        _connection("wm-4", "cap_beam", "ground_beam", "reaction_to_line", output_unit="kN", input_unit="kN", support="left", conversion_input_key="reaction_conversion_spacing_m", requires_source_trace=True),
        _connection("wm-5", "ground_beam", "wall_foundation", "reaction_package", output_unit="kN", input_unit="kN", support="left", requires_source_trace=True),
    ],
)

BENCH_GRAPH_PUBLIC = _graph(
    "bench-cast-in-place-chain",
    [
        _node("seat_loads", "座板自重与人员荷载", "load"),
        _node("seat_slab", "现浇座板", "surface", "concrete_slab", input_bindings={"span_m": "seat_span_m", "h_mm": "seat_thickness_mm"}),
        _node("support_beam", "支承梁 / 支腿", "primary_member", "concrete_beam", input_bindings={"span_m": "support_spacing_m", "reaction_conversion_spacing_m": "support_spacing_m"}),
        _node("bench_foundation", "条形基础 / 底板", "foundation", "strip_footing"),
    ],
    [
        _connection("bn-1", "seat_loads", "seat_slab", "manual"),
        _connection("bn-2", "seat_slab", "support_beam", "reaction_to_line", output_unit="kN", input_unit="kN", support="left", conversion_input_key="reaction_conversion_spacing_m", requires_source_trace=True),
        _connection("bn-3", "support_beam", "bench_foundation", "reaction_package", output_unit="kN", input_unit="kN", support="left", requires_source_trace=True),
    ],
)

PLANTER_GRAPH_PUBLIC = _graph(
    "rectangular-planter-chain",
    [
        _node("planter_loads", "覆土、池壁自重与侧向土压力", "load"),
        _node("planter_wall", "矩形池壁条带", "surface", "rc_wall", input_bindings={"height_m": "wall_height_m", "thickness_mm": "wall_thickness_mm", "soil_height_m": "wall_height_m", "soil_unit_weight_kn_m3": "soil_unit_weight_kn_m3", "soil_friction_angle_deg": "soil_friction_angle_deg"}),
        _node("planter_foundation", "底板 / 条形基础", "foundation", "strip_footing"),
    ],
    [
        _connection("pt-1", "planter_loads", "planter_wall", "manual"),
        _connection("pt-2", "planter_wall", "planter_foundation", "reaction_package", output_unit="kN", input_unit="kN", requires_source_trace=True),
    ],
)

RETAINING_GRAPH_PUBLIC = _graph(
    "retaining-cantilever-rc-chain",
    [
        _node("soil_water_inputs", "土压力、附加荷载、地下水与浮力", "load"),
        _node("retaining_wall", "钢筋混凝土悬臂挡土墙", "primary_member", "retaining_wall"),
        _node("soil_contact", "基底接触与地基资料", "geotechnical", quick_assumption="墙身模块已完成基础稳定筛查；地勘承载力和水位仍需项目资料确认。"),
    ],
    [
        _connection("rt-1", "soil_water_inputs", "retaining_wall", "manual"),
        _connection("rt-2", "retaining_wall", "soil_contact", "reaction_package", output_unit="kN/m", input_unit="kN/m", requires_source_trace=True),
    ],
)


def _site_wall_system_graph(
    graph_id: str, module: str, wall_label: str, foundation_label: str
) -> SceneGraphTemplate:
    return _graph(
        graph_id,
        [
            _node(
                "wall_loads",
                "墙体附加恒载与正反向风",
                "load",
                maturity="verified",
                verification_status="independently_verified",
                description="场景荷载包直接写入墙体模块的 typed load_cases。",
            ),
            _node(
                "wall_system",
                wall_label,
                "column_wall",
                module,
                input_bindings={
                    "height": "height_m",
                    "length": "length_m",
                    "support_spacing": "support_spacing_m",
                    "opening_ratio": "opening_ratio",
                },
            ),
            _node(
                "foundation_interface",
                foundation_label,
                "foundation",
                maturity="verified",
                verification_status="independently_verified",
                quick_assumption="墙体模块输出同组合底部六分量反力和基础线荷载，供基础单项计算继续使用。",
            ),
        ],
        [
            _connection("sw-1", "wall_loads", "wall_system", "manual"),
            _connection(
                "sw-2",
                "wall_system",
                "foundation_interface",
                "reaction_package",
                output_unit="kN",
                input_unit="kN",
                requires_source_trace=True,
                description="传递墙体底部同组合六分量反力及基础线荷载追踪号。",
            ),
        ],
    )


SITE_RC_WALL_GRAPH = _site_wall_system_graph(
    "site-rc-wall-real-chain-v32",
    "site_rc_wall",
    "现浇 RC 景墙墙身",
    "条形基础接口",
)
STEEL_INFILL_WALL_GRAPH = _site_wall_system_graph(
    "steel-infill-wall-real-chain-v32",
    "steel_infill_wall",
    "钢立柱与轻质填充墙",
    "柱脚与独立基础接口",
)
PLAIN_MASONRY_WALL_GRAPH = _site_wall_system_graph(
    "plain-masonry-wall-real-chain-v32",
    "plain_masonry_wall",
    "低矮纯砌体墙",
    "条形基础接口",
)

GRAVITY_RETAINING_GRAPH = _graph(
    "gravity-retaining-wall-real-chain-v32",
    [
        _node(
            "soil_water_inputs",
            "土压力、水压力、附加荷载与地下水",
            "load",
            maturity="verified",
            verification_status="independently_verified",
            description="地勘和项目水位参数输入，不作为独立荷载计算器发布。",
        ),
        _node(
            "gravity_wall",
            "重力式挡土墙墙体与底座",
            "primary_member",
            "gravity_retaining_wall",
        ),
        _node(
            "soil_contact",
            "基底接触与地基接口",
            "geotechnical",
            maturity="verified",
            verification_status="independently_verified",
            quick_assumption="重力墙核心已输出基底压力、滑移、倾覆和同组合基础反力。",
        ),
    ],
    [
        _connection("gr-1", "soil_water_inputs", "gravity_wall", "manual"),
        _connection(
            "gr-2",
            "gravity_wall",
            "soil_contact",
            "reaction_package",
            output_unit="kN/m",
            input_unit="kN/m",
            requires_source_trace=True,
        ),
    ],
)


def _base_and_foundation_nodes(
    prefix: str, supports: list[tuple[str, str]]
) -> tuple[list[SceneNode], list[SceneConnection]]:
    nodes: list[SceneNode] = []
    connections: list[SceneConnection] = []
    for suffix, _support in supports:
        base_id = f"{prefix}_base_{suffix}"
        foundation_id = f"{prefix}_foundation_{suffix}"
        nodes.extend(
            [
                _node(
                    base_id,
                    f"{suffix} 柱脚 / 底板锚栓",
                    "connection",
                    "steel_baseplate_anchor",
                ),
                _node(
                    foundation_id,
                    f"{suffix} 独立基础",
                    "foundation",
                    "spread_footing",
                ),
            ]
        )
        connections.append(
            _connection(
                f"{prefix}-{suffix}-foundation",
                base_id,
                foundation_id,
                "reaction_package",
                output_unit="kN",
                input_unit="kN",
                requires_source_trace=True,
            )
        )
    return nodes, connections


def _framed_foundation_graph(
    graph_id: str,
    load_node_id: str,
    load_label: str,
    frame_node_id: str,
    frame_label: str,
    supports: list[tuple[str, str]],
) -> SceneGraphTemplate:
    support_nodes, support_connections = _base_and_foundation_nodes(
        graph_id, supports
    )
    frame_connections = [
        _connection(
            f"{graph_id}-load-frame",
            load_node_id,
            frame_node_id,
            "manual",
        )
    ]
    for suffix, support in supports:
        frame_connections.append(
            _connection(
                f"{graph_id}-frame-{suffix}",
                frame_node_id,
                f"{graph_id}_base_{suffix}",
                "reaction_package",
                output_unit="kN",
                input_unit="kN",
                support=support,
                requires_source_trace=True,
            )
        )
    return _graph(
        graph_id,
        [
            _node(
                load_node_id,
                load_label,
                "load",
                verification_status="independently_verified",
            ),
            _node(
                frame_node_id,
                frame_label,
                "primary_member",
                "planar_frame",
            ),
            *support_nodes,
        ],
        [*frame_connections, *support_connections],
    )


def _pergola_frame_graph(
    graph_id: str, frame_label: str, supports: list[tuple[str, str]]
) -> SceneGraphTemplate:
    support_nodes, support_connections = _base_and_foundation_nodes(
        graph_id, supports
    )
    connections = [
        _connection(
            f"{graph_id}-loads-roof",
            "environment",
            "roof_members",
            "manual",
        ),
        _connection(
            f"{graph_id}-roof-frame",
            "roof_members",
            "main_frame",
            "reaction_to_line",
            output_unit="kN",
            input_unit="kN",
            support="left",
            conversion_input_key="reaction_conversion_spacing_m",
            requires_source_trace=True,
        ),
    ]
    for suffix, support in supports:
        connections.append(
            _connection(
                f"{graph_id}-frame-{suffix}",
                "main_frame",
                f"{graph_id}_base_{suffix}",
                "reaction_package",
                output_unit="kN",
                input_unit="kN",
                support=support,
                requires_source_trace=True,
            )
        )
    return _graph(
        graph_id,
        [
            _node(
                "environment",
                "覆盖层、检修、风雪作用",
                "load",
                verification_status="independently_verified",
            ),
            _node(
                "roof_members",
                "钢檩条 / 椽条",
                "secondary_member",
                "continuous_beam",
                input_bindings={
                    "reaction_conversion_spacing_m": "frame_spacing_m"
                },
            ),
            _node(
                "main_frame",
                frame_label,
                "primary_member",
                "planar_frame",
            ),
            *support_nodes,
        ],
        [*connections, *support_connections],
    )


PERGOLA_MONO_GRAPH = _pergola_frame_graph(
    "pergola-mono-pitch-chain",
    "单坡参数化平面框架",
    [("left", "left"), ("right", "right")],
)
PERGOLA_DUAL_GRAPH = _pergola_frame_graph(
    "pergola-dual-pitch-chain",
    "双坡屋脊参数化平面框架",
    [("left", "left"), ("right", "right")],
)
PERGOLA_MULTI_GRAPH = _pergola_frame_graph(
    "pergola-two-bay-unequal-chain",
    "双跨 / 不同柱高参数化平面框架",
    [("left", "left"), ("middle", "base"), ("right", "right")],
)

CANOPY_WALL_PUBLIC_GRAPH = _graph(
    "canopy-wall-anchor-chain",
    [
        _node(
            "canopy_loads",
            "覆盖层、检修、风雪作用",
            "load",
            verification_status="independently_verified",
        ),
        _node(
            "secondary_beam",
            "墙附悬挑钢梁",
            "secondary_member",
            "steel_beam",
        ),
        _node(
            "wall_anchor",
            "墙体锚栓组",
            "connection",
            "wall_anchor",
        ),
    ],
    [
        _connection(
            "canopy-wall-load-beam",
            "canopy_loads",
            "secondary_beam",
            "manual",
        ),
        _connection(
            "canopy-wall-beam-anchor",
            "secondary_beam",
            "wall_anchor",
            "reaction_package",
            output_unit="kN",
            input_unit="kN",
            requires_source_trace=True,
        ),
    ],
)

SIGN_DOUBLE_GRAPH = _framed_foundation_graph(
    "signage-double-post-chain-v32",
    "wind_panel",
    "面板自重与正负风压",
    "post",
    "双柱平面框架",
    [("left", "left"), ("right", "right")],
)
SIGN_GROUND_GRAPH = _framed_foundation_graph(
    "signage-ground-mounted-chain-v32",
    "wind_panel",
    "面板自重与正负风压",
    "post",
    "落地式钢悬臂框架",
    [("base", "base")],
)

SIGN_ECCENTRIC_GRAPH = _graph(
    "signage-eccentric-panel-chain-v32",
    [
        _node(
            "wind_panel",
            "倾斜面板自重与正负风压",
            "load",
            verification_status="independently_verified",
        ),
        _node(
            "post",
            "偏心钢悬臂立柱",
            "column_wall",
            "steel_cantilever_post",
        ),
        _node(
            "base_plate",
            "底板与锚栓组",
            "connection",
            "steel_baseplate_anchor",
        ),
        _node(
            "foundation",
            "独立基础",
            "foundation",
            "spread_footing",
        ),
    ],
    [
        _connection("sign-ecc-load-post", "wind_panel", "post", "manual"),
        _connection(
            "sign-ecc-post-base",
            "post",
            "base_plate",
            "reaction_package",
            output_unit="kN",
            input_unit="kN",
            requires_source_trace=True,
        ),
        _connection(
            "sign-ecc-base-foundation",
            "base_plate",
            "foundation",
            "reaction_package",
            output_unit="kN",
            input_unit="kN",
            requires_source_trace=True,
        ),
    ],
)

ENTRANCE_MULTI_GRAPH = _framed_foundation_graph(
    "entrance-two-bay-chain-v32",
    "gate_loads",
    "面层、招牌与正负风作用",
    "gate_frame",
    "双跨参数化门楼框架",
    [("left", "left"), ("middle", "base"), ("right", "right")],
)
ENTRANCE_ECCENTRIC_GRAPH = _framed_foundation_graph(
    "entrance-eccentric-lintel-chain-v32",
    "gate_loads",
    "偏心门楣、招牌与正负风作用",
    "gate_frame",
    "偏心门楣参数化框架",
    [("left", "left"), ("right", "right")],
)
ENTRANCE_UNEQUAL_GRAPH = _framed_foundation_graph(
    "entrance-unequal-column-chain-v32",
    "gate_loads",
    "面层、招牌与正负风作用",
    "gate_frame",
    "不同柱高参数化框架",
    [("left", "left"), ("right", "right")],
)

VIEWING_PLATFORM_GRAPH = _graph(
    "viewing-platform-two-way-chain-v32",
    [
        _node(
            "deck_loads",
            "人群、栏杆与面层作用",
            "load",
            verification_status="independently_verified",
        ),
        _node("deck", "双向混凝土平台板", "surface", "two_way_slab"),
        _node(
            "secondary",
            "钢次梁",
            "secondary_member",
            "continuous_beam",
            input_bindings={
                "reaction_conversion_spacing_m": "secondary_spacing_m"
            },
        ),
        _node(
            "primary",
            "钢主梁",
            "primary_member",
            "continuous_beam",
            input_bindings={
                "reaction_conversion_spacing_m": "primary_spacing_m"
            },
        ),
        _node(
            "platform_base_left",
            "左柱脚 / 底板锚栓",
            "connection",
            "steel_baseplate_anchor",
        ),
        _node(
            "platform_base_right",
            "右柱脚 / 底板锚栓",
            "connection",
            "steel_baseplate_anchor",
        ),
        _node(
            "platform_foundation_left",
            "左独立基础",
            "foundation",
            "spread_footing",
        ),
        _node(
            "platform_foundation_right",
            "右独立基础",
            "foundation",
            "spread_footing",
        ),
    ],
    [
        _connection("platform-load-deck", "deck_loads", "deck", "manual"),
        _connection(
            "platform-deck-secondary",
            "deck",
            "secondary",
            "reaction_to_line",
            output_unit="kN",
            input_unit="kN",
            conversion_input_key="reaction_conversion_spacing_m",
            requires_source_trace=True,
        ),
        _connection(
            "platform-secondary-primary",
            "secondary",
            "primary",
            "reaction_to_line",
            output_unit="kN",
            input_unit="kN",
            support="left",
            conversion_input_key="reaction_conversion_spacing_m",
            requires_source_trace=True,
        ),
        _connection(
            "platform-primary-left-base",
            "primary",
            "platform_base_left",
            "reaction_package",
            output_unit="kN",
            input_unit="kN",
            support="left",
            requires_source_trace=True,
        ),
        _connection(
            "platform-primary-right-base",
            "primary",
            "platform_base_right",
            "reaction_package",
            output_unit="kN",
            input_unit="kN",
            support="right",
            requires_source_trace=True,
        ),
        _connection(
            "platform-left-foundation",
            "platform_base_left",
            "platform_foundation_left",
            "reaction_package",
            output_unit="kN",
            input_unit="kN",
            requires_source_trace=True,
        ),
        _connection(
            "platform-right-foundation",
            "platform_base_right",
            "platform_foundation_right",
            "reaction_package",
            output_unit="kN",
            input_unit="kN",
            requires_source_trace=True,
        ),
    ],
)

SIGN_PUBLIC_LOAD_PACKAGE = _package(
    "signage-panel-public-loads-v32",
    "导视牌面板荷载包",
    "面板自重和正负风压；偏心距与倾角作为几何参数录入。",
    [
        _load(
            "sign-panel-dead-v32",
            "面板及安装骨架自重",
            "dead",
            "reference_range",
            "kN/m2",
            "按面板与骨架产品资料",
            "post",
            minimum=0.15,
            default=0.35,
            maximum=0.80,
        ),
        _load(
            "sign-wind-positive-v32",
            "面板正向风压",
            "wind",
            "calculated",
            "kN/m2",
            "GB 50009-2012 第 8 章",
            "post",
            default=0.60,
            direction="x_positive",
        ),
        _load(
            "sign-wind-negative-v32",
            "面板反向风压",
            "wind",
            "calculated",
            "kN/m2",
            "GB 50009-2012 第 8 章",
            "post",
            default=0.60,
            direction="x_negative",
        ),
    ],
)


POOL_PUBLIC_LOAD_PACKAGE = _package(
    "rectangular-pool-actions-v32",
    "矩形水池土水作用包",
    "内外水位、土压力、地表附加荷载和地下水浮力由水池参数生成并保存来源。",
    [
        _load(
            "pool-internal-water-v32",
            "池内水位与水压力",
            "water",
            "calculated",
            "kPa",
            "项目运行水位与水重度",
            "pool_loads",
            default=20.0,
            distribution="pressure",
            applicable_when="满池及运行水位组合。",
        ),
        _load(
            "pool-external-soil-v32",
            "池外主动土压力",
            "soil",
            "calculated",
            "kPa",
            "项目地勘土重度、内摩擦角与覆土高度",
            "pool_loads",
            default=12.0,
            distribution="pressure",
            direction="x_positive",
            applicable_when="半地下或地下池；地上池为不适用。",
        ),
        _load(
            "pool-groundwater-uplift-v32",
            "地下水浮力",
            "buoyancy",
            "calculated",
            "kPa",
            "勘察最高抗浮水位",
            "pool_loads",
            default=10.0,
            distribution="pressure",
            direction="uplift",
            applicable_when="地下水位高于池底；未知水位时专业计算不完整。",
        ),
    ],
)

BRIDGE_PUBLIC_LOAD_PACKAGE = _package(
    "pedestrian-bridge-actions-v32",
    "景观人行桥作用包",
    "桥面恒载、人群、栏杆和横向风作用；各跨分配由桥梁模块保存。",
    [
        _load(
            "bridge-finish-dead-v32",
            "桥面铺装及附加恒载",
            "dead",
            "reference_range",
            "kN/m2",
            "按桥面材料和构造层计算",
            "bridge_superstructure",
            minimum=0.30,
            default=0.80,
            maximum=2.50,
        ),
        _load(
            "bridge-crowd-v32",
            "人群荷载",
            "live",
            "fixed",
            "kN/m2",
            "项目使用类别与现行荷载标准",
            "bridge_superstructure",
            default=4.00,
        ),
        _load(
            "bridge-wind-v32",
            "桥梁横向风作用",
            "wind",
            "calculated",
            "kN/m2",
            "GB 50009-2012 风荷载向导",
            "bridge_superstructure",
            default=0.50,
            direction="x_positive",
        ),
    ],
)


def _pool_graph(graph_id: str, *, piled: bool) -> SceneGraphTemplate:
    nodes = [
        _node(
            "pool_loads",
            "内外水位、土压力与地下水",
            "load",
            verification_status="independently_verified",
        ),
        _node(
            "pool_structure",
            "RC 池壁、底板与抗浮组合",
            "surface",
            "pool_structure",
        ),
        _node(
            "antifloat_support",
            "池底支承与抗浮控制",
            "geotechnical" if piled else "foundation",
            description="复用水池模块同一结果中的基底压力和抗浮验算，不另行重复计重。",
        ),
    ]
    connections = [
        _connection(
            f"{graph_id}-loads-pool",
            "pool_loads",
            "pool_structure",
            "manual",
        ),
        _connection(
            f"{graph_id}-pool-support",
            "pool_structure",
            "antifloat_support",
            "combination_package",
            output_unit="kN",
            input_unit="kN",
            requires_source_trace=True,
        ),
    ]
    if piled:
        nodes.append(
            _node(
                "pile_cap",
                "抗浮桩群与承台",
                "foundation",
                "pile_group_cap",
            )
        )
        connections.append(
            _connection(
                f"{graph_id}-support-piles",
                "antifloat_support",
                "pile_cap",
                "combination_package",
                output_unit="kN",
                input_unit="kN",
                requires_source_trace=True,
            )
        )
    return _graph(graph_id, nodes, connections)


def _bridge_graph(
    graph_id: str,
    bridge_module: str,
    *,
    support_count: int,
    piled: bool,
) -> SceneGraphTemplate:
    if support_count not in {2, 3}:
        raise ValueError("parameterized bridge catalog supports two or three supports")
    support_specs = (
        [("left", "left"), ("right", "right")]
        if support_count == 2
        else [("left", "left"), ("middle", "base"), ("right", "right")]
    )
    support_module = "pile_group_cap" if piled else "spread_footing"
    support_label = "桩群承台" if piled else "浅基础"
    nodes = [
        _node(
            "bridge_loads",
            "桥面、人群、栏杆与横向风作用",
            "load",
            verification_status="independently_verified",
        ),
        _node(
            "bridge_superstructure",
            "参数化桥面板、纵横梁与墩台反力",
            "primary_member",
            bridge_module,
        ),
    ]
    connections = [
        _connection(
            f"{graph_id}-loads-superstructure",
            "bridge_loads",
            "bridge_superstructure",
            "manual",
        )
    ]
    for suffix, support in support_specs:
        node_id = f"support_{suffix}"
        nodes.append(
            _node(
                node_id,
                f"{suffix} {support_label}",
                "foundation",
                support_module,
            )
        )
        connections.append(
            _connection(
                f"{graph_id}-support-{suffix}",
                "bridge_superstructure",
                node_id,
                "combination_package",
                output_unit="kN",
                input_unit="kN",
                support=support,
                requires_source_trace=True,
            )
        )
    return _graph(graph_id, nodes, connections)


POOL_ABOVE_SHALLOW_GRAPH = _pool_graph("pool-above-shallow-v32", piled=False)
POOL_SEMI_SHALLOW_GRAPH = _pool_graph("pool-semi-shallow-v32", piled=False)
POOL_BURIED_SHALLOW_GRAPH = _pool_graph("pool-buried-shallow-v32", piled=False)
POOL_ABOVE_PILE_GRAPH = _pool_graph("pool-above-pile-v32", piled=True)
POOL_SEMI_PILE_GRAPH = _pool_graph("pool-semi-pile-v32", piled=True)
POOL_BURIED_PILE_GRAPH = _pool_graph("pool-buried-pile-v32", piled=True)

BRIDGE_ST_SINGLE_SHALLOW_GRAPH = _bridge_graph(
    "bridge-steel-timber-single-shallow-v32",
    "bridge_steel_timber",
    support_count=2,
    piled=False,
)
BRIDGE_ST_SINGLE_PILE_GRAPH = _bridge_graph(
    "bridge-steel-timber-single-pile-v32",
    "bridge_steel_timber",
    support_count=2,
    piled=True,
)
BRIDGE_ST_MULTI_SHALLOW_GRAPH = _bridge_graph(
    "bridge-steel-timber-two-span-shallow-v32",
    "bridge_steel_timber",
    support_count=3,
    piled=False,
)
BRIDGE_ST_MULTI_PILE_GRAPH = _bridge_graph(
    "bridge-steel-timber-two-span-pile-v32",
    "bridge_steel_timber",
    support_count=3,
    piled=True,
)
BRIDGE_RC_SINGLE_SHALLOW_GRAPH = _bridge_graph(
    "bridge-rc-single-shallow-v32",
    "bridge_rc",
    support_count=2,
    piled=False,
)
BRIDGE_RC_SINGLE_PILE_GRAPH = _bridge_graph(
    "bridge-rc-single-pile-v32",
    "bridge_rc",
    support_count=2,
    piled=True,
)
BRIDGE_RC_MULTI_SHALLOW_GRAPH = _bridge_graph(
    "bridge-rc-two-span-shallow-v32",
    "bridge_rc",
    support_count=3,
    piled=False,
)
BRIDGE_RC_MULTI_PILE_GRAPH = _bridge_graph(
    "bridge-rc-two-span-pile-v32",
    "bridge_rc",
    support_count=3,
    piled=True,
)


def _replace_public_variant(family_id: str, variant: SceneVariant) -> None:
    family = next(item for item in SCENE_FAMILIES if item.id == family_id)
    if any(item.id == variant.id for item in family.variants):
        family.variants = [
            variant if item.id == variant.id else item for item in family.variants
        ]
    else:
        family.variants.append(variant)
    family.availability = "public"
    family.maturity = "beta"
    family.default_variant_id = variant.id
    family.graph_template = variant.graph_template or family.graph_template


_replace_public_variant(
    "boardwalk-platform",
    _variant(
        "straight",
        "直线栈道（木面板+钢构）",
        "水平直线、矩形平面；木面板、钢次梁、钢主梁、钢柱、柱脚和左右独立基础。",
        ["木面板+钢构"],
        [_number("secondary_spacing_m", "次梁间距", "m", 0.6), _number("primary_span_m", "次梁跨度", "m", 3.0), _number("main_span_m", "主梁跨度", "m", 3.0), _number("primary_spacing_m", "主梁从属宽度", "m", 2.0), _number("column_height_m", "钢柱高度", "m", 2.8), _number("panel_unit_width_m", "面板计算条带宽度", "m", 1.0)],
        support_system="钢柱+独立基础",
        graph=BOARDWALK_GRAPH,
        load_package=BOARDWALK_LOAD_PACKAGE,
        missing_capabilities=["木面板连接与长期变形", "柱脚混凝土锚固破坏"],
    ),
)
_replace_public_variant(
    "canopy",
    _variant(
        "single-row",
        "单排柱钢雨棚",
        "覆盖层、悬挑钢次梁、钢柱、柱脚和独立基础。",
        ["钢"],
        [_number("cantilever_m", "悬挑长度", "m", 1.8), _number("width_m", "从属宽度", "m", 3.0), _number("column_height_m", "柱高", "m", 3.0), _choice("support", "次梁支承", ["cantilever"], "cantilever")],
        support_system="单排柱",
        roof_form="平顶",
        graph=CANOPY_SINGLE_GRAPH_PUBLIC,
        load_package=_roof_scene_package("canopy-single-row-loads", "单排柱雨棚荷载包", "secondary"),
    ),
)
_replace_public_variant(
    "canopy",
    _variant(
        "double-row",
        "双排柱钢雨棚",
        "覆盖层、钢次梁、横向门式框架、左右柱脚和独立基础。",
        ["钢"],
        [_number("main_span_m", "次梁跨度", "m", 3.0), _number("secondary_spacing_m", "次梁间距", "m", 1.0), _number("frame_span_m", "横向框架跨度", "m", 4.0), _number("column_height_m", "柱高", "m", 3.0), _number("frame_spacing_m", "框架纵向间距", "m", 3.0)],
        support_system="双排柱",
        roof_form="平顶",
        graph=CANOPY_DOUBLE_GRAPH_PUBLIC,
        load_package=_roof_scene_package("canopy-double-row-loads", "双排柱雨棚荷载包", "secondary"),
    ),
)
_replace_public_variant(
    "signage-billboard",
    _variant(
        "single-post",
        "单柱钢导视牌",
        "正负面板风压、偏心合力、钢悬臂立柱、底板锚栓和独立基础。",
        ["钢"],
        [_number("height_m", "立柱高度", "m", 2.8), _number("panel_area_m2", "面板面积", "m2", 1.5), _number("panel_cg_height_m", "面板合力高度", "m", 2.1), _number("panel_eccentricity_m", "面板偏心距", "m", 0.0)],
        support_system="单柱落地",
        graph=SIGN_GRAPH_PUBLIC,
        load_package=_package("signage-single-post-loads", "单柱导视牌荷载包", "面板自重和正负风压。", [_load("sign-panel-dead", "面板及安装构件自重", "dead", "reference_range", "kN/m2", "按面板与龙骨产品资料", "post", minimum=0.15, default=0.35, maximum=0.80), _load("sign-wind-positive", "面板正向风压", "wind", "calculated", "kN/m2", "GB 50009-2012 第8章", "post", default=0.60, direction="x_positive"), _load("sign-wind-negative", "面板反向风压", "wind", "calculated", "kN/m2", "GB 50009-2012 第8章", "post", default=0.60, direction="x_negative")]),
    ),
)
_replace_public_variant(
    "landscape-wall-fence",
    _variant(
        "constrained-masonry",
        "约束砌体景墙",
        "砌体填充、RC 构造柱、压顶梁、地梁和条形基础；直线、等高、规则分格。",
        ["砌体+混凝土"],
        [_number("height_m", "墙高", "m", 2.0), _number("thickness_mm", "墙厚", "mm", 240.0), _number("column_spacing_m", "构造柱间距", "m", 3.0), _number("wall_length_m", "代表墙长", "m", 6.0)],
        support_system="RC 构造柱+地梁+条形基础",
        graph=WALL_GRAPH_PUBLIC,
        load_package=_package("constrained-masonry-wall-loads", "约束砌体景墙荷载包", "砌体、饰面、正反向风和压顶作用。", [_load("masonry-dead", "砌体及抹灰自重", "dead", "calculated", "kN/m2", "按墙厚、重度和饰面计算", "masonry_infill", default=3.0), _load("masonry-wind-positive", "墙面正向风压", "wind", "calculated", "kN/m2", "GB 50009-2012 第8章", "masonry_infill", default=0.50, direction="x_positive"), _load("masonry-wind-negative", "墙面反向风压", "wind", "calculated", "kN/m2", "GB 50009-2012 第8章", "masonry_infill", default=0.50, direction="x_negative")]),
    ),
)
_replace_public_variant(
    "entrance-frame",
    _variant(
        "single-span",
        "钢单跨门楼",
        "面层/招牌、单跨门式框架、左右柱脚和独立基础；等高、对称。",
        ["钢"],
        [_number("span_m", "门楼跨度", "m", 5.0), _number("height_m", "柱高", "m", 3.2), _number("bay_spacing_m", "代表纵向间距", "m", 3.0)],
        support_system="双柱落地",
        graph=ENTRANCE_GRAPH_PUBLIC,
        load_package=_package("entrance-single-span-loads", "钢单跨门楼荷载包", "面层/招牌恒载和正负风。", [_load("entrance-dead", "面层及招牌恒载", "dead", "reference_range", "kN/m2", "按饰面和招牌产品资料", "gate_frame", minimum=0.30, default=0.80, maximum=2.00), _load("entrance-wind-positive", "正向风", "wind", "calculated", "kN/m2", "GB 50009-2012 第8章", "gate_frame", default=0.50, direction="x_positive"), _load("entrance-wind-negative", "反向风", "wind", "calculated", "kN/m2", "GB 50009-2012 第8章", "gate_frame", default=0.50, direction="x_negative")]),
    ),
)
_replace_public_variant(
    "bench-planter",
    _variant(
        "bench",
        "现浇坐凳",
        "现浇座板、支承梁/支腿和条形基础，按规则直线构造快算。",
        ["混凝土"],
        [_number("seat_span_m", "座板支承间距", "m", 1.2), _number("seat_thickness_mm", "座板厚度", "mm", 120.0), _number("support_spacing_m", "支腿间距", "m", 1.5)],
        support_system="支腿+条形基础",
        graph=BENCH_GRAPH_PUBLIC,
        load_package=_package("bench-cast-loads", "现浇坐凳荷载包", "座板自重和人员使用荷载。", [_load("bench-dead", "座板及饰面恒载", "dead", "reference_range", "kN/m2", "按构造层计算", "seat_slab", minimum=1.0, default=2.5, maximum=4.0), _load("bench-live", "坐凳人员使用荷载", "live", "fixed", "kN/m2", "GB 50009-2012；按人员聚集条件复核", "seat_slab", default=3.5)]),
    ),
)
_replace_public_variant(
    "bench-planter",
    _variant(
        "planter",
        "矩形树池",
        "覆土及附加荷载、RC 池壁和底板/条基；按每延米直线池壁验算。",
        ["混凝土"],
        [_number("wall_height_m", "池壁高度", "m", 0.8), _number("wall_thickness_mm", "池壁厚度", "mm", 180.0), _number("planter_length_m", "池壁代表长度", "m", 4.0), _number("soil_unit_weight_kn_m3", "种植土重度", "kN/m3", 18.0), _number("soil_friction_angle_deg", "种植土内摩擦角", "°", 30.0)],
        support_system="池壁+底板/条基",
        graph=PLANTER_GRAPH_PUBLIC,
        load_package=_package("planter-rect-loads", "矩形树池荷载包", "覆土、附加荷载和池壁侧向土压力。", [_load("planter-soil", "覆土及种植土附加恒载", "dead", "reference_range", "kN/m2", "按覆土厚度和土重度计算", "planter_wall", minimum=3.0, default=8.0, maximum=15.0), _load("planter-wind", "池壁施工阶段风荷载", "wind", "calculated", "kN/m2", "GB 50009-2012 第8章", "planter_wall", default=0.30, direction="x_positive")]),
    ),
)
_replace_public_variant(
    "retaining-facility",
    _variant(
        "cantilever-rc",
        "钢筋混凝土悬臂挡土墙",
        "水平填土、单一土层、明确地下水位的墙身、底板、稳定和基底压力快算。",
        ["混凝土"],
        [_number("retained_height_m", "挡土高度", "m", 1.5), _number("base_width_m", "底板宽度", "m", 1.6), _number("toe_length_m", "趾长", "m", 0.45), _number("stem_thickness_mm", "墙身厚度", "mm", 200.0), _number("base_thickness_m", "底板厚度", "m", 0.35), _number("soil_unit_weight_kn_m3", "土重度", "kN/m3", 18.0), _number("soil_friction_angle_deg", "土内摩擦角", "°", 30.0), _number("surcharge_kpa", "墙后附加荷载", "kPa", 0.0), _number("water_level_depth_m", "地下水深度", "m", 0.0), _number("submerged_depth_m", "基础浸没深度", "m", 0.0), _number("soil_capacity_kpa", "地基承载力", "kPa", 120.0), _number("base_friction_coefficient", "基底摩擦系数", "1", 0.35), _number("stem_moment_capacity_kn_m_per_m", "墙身弯矩快算承载力", "kN·m/m", 80.0)],
        support_system="底板+地基",
        graph=RETAINING_GRAPH_PUBLIC,
        load_package=_package("retaining-cantilever-loads", "悬臂挡土墙土水作用包", "土压力、水压力、浮力和附加荷载由墙身参数生成；专业模式必须输入勘察资料。", [_load("retaining-soil-water-source", "土水参数资料已确认", "custom", "fixed", "1", "项目地勘与水位资料；快算可按显式假定", "soil_water_inputs", default=1.0, applicable_when="挡土高度、土重度、内摩擦角和地下水位均已在设置页填写。")]),
    ),
)

_replace_public_variant(
    "landscape-wall-fence",
    _variant(
        "concrete-straight",
        "现浇混凝土景墙",
        "墙体附加恒载和正反向风直接进入现浇 RC 墙核心，并输出基础线荷载和底部六分量反力。",
        ["混凝土"],
        [
            _number("height_m", "墙高", "m", 1.8),
            _number("length_m", "代表墙长", "m", 6.0),
            _number("thickness_mm", "墙厚", "mm", 180.0),
            _number("support_spacing_m", "代表支承间距", "m", 3.0),
            _number("opening_ratio", "规则小开洞率", "1", 0.0),
        ],
        support_system="墙身固定端+条形基础接口",
        graph=SITE_RC_WALL_GRAPH,
        load_package=_package(
            "site-rc-wall-loads-v32",
            "现浇 RC 景墙荷载包",
            "墙体自重由几何和混凝土重度自动生成；目录只提供附加面层与正反向风。",
            [
                _load("rc-wall-finish", "饰面附加恒载", "dead", "reference_range", "kN/m2", "按饰面产品资料", "wall_system", minimum=0.10, default=0.25, maximum=0.60),
                _load("rc-wall-wind-positive", "正向风压", "wind", "calculated", "kN/m2", "GB 50009-2012 风荷载向导", "wall_system", default=0.50, direction="x_positive"),
                _load("rc-wall-wind-negative", "反向风压", "wind", "calculated", "kN/m2", "GB 50009-2012 风荷载向导", "wall_system", default=0.45, direction="x_negative"),
            ],
        ),
    ),
)

_replace_public_variant(
    "landscape-wall-fence",
    _variant(
        "steel-infill",
        "钢立柱轻质填充墙",
        "轻质填充面层恒载和风作用进入钢立柱体系核心，输出每根立柱底反力和基础线荷载。",
        ["钢+轻质填充"],
        [
            _number("height_m", "墙高", "m", 2.0),
            _number("length_m", "代表墙长", "m", 8.0),
            _number("support_spacing_m", "钢立柱间距", "m", 2.0),
            _number("opening_ratio", "规则小开洞率", "1", 0.0),
        ],
        support_system="钢立柱柱脚+独立基础接口",
        graph=STEEL_INFILL_WALL_GRAPH,
        load_package=_package(
            "steel-infill-wall-loads-v32",
            "钢立柱轻质填充墙荷载包",
            "填充面层恒载、正向风和反向风按立柱间距形成支承反力。",
            [
                _load("steel-infill-dead", "轻质填充面层恒载", "dead", "reference_range", "kN/m2", "按填充板及龙骨产品资料", "wall_system", minimum=0.25, default=0.45, maximum=0.80),
                _load("steel-infill-wind-positive", "正向风压", "wind", "calculated", "kN/m2", "GB 50009-2012 风荷载向导", "wall_system", default=0.65, direction="x_positive"),
                _load("steel-infill-wind-negative", "反向风压", "wind", "calculated", "kN/m2", "GB 50009-2012 风荷载向导", "wall_system", default=0.55, direction="x_negative"),
            ],
        ),
    ),
)

_replace_public_variant(
    "landscape-wall-fence",
    _variant(
        "plain-masonry",
        "低矮纯砌体景墙",
        "仅用于受限高度和规则小开洞的低墙，计算砌体弯剪、压应力、长细与基础线荷载。",
        ["砌体"],
        [
            _number("height_m", "墙高", "m", 1.0),
            _number("length_m", "代表墙长", "m", 6.0),
            _number("thickness_mm", "墙厚", "mm", 240.0),
            _number("support_spacing_m", "侧向支承间距", "m", 3.0),
            _number("opening_ratio", "规则小开洞率", "1", 0.0),
        ],
        support_system="低墙固定端+条形基础接口",
        graph=PLAIN_MASONRY_WALL_GRAPH,
        load_package=_package(
            "plain-masonry-wall-loads-v32",
            "低矮纯砌体墙荷载包",
            "砌体自重自动生成；目录记录抹灰饰面和正反向风。",
            [
                _load("plain-masonry-finish", "抹灰饰面附加恒载", "dead", "reference_range", "kN/m2", "按抹灰和饰面厚度计算", "wall_system", minimum=0.20, default=0.35, maximum=0.70),
                _load("plain-masonry-wind-positive", "正向风压", "wind", "calculated", "kN/m2", "GB 50009-2012 风荷载向导", "wall_system", default=0.45, direction="x_positive"),
                _load("plain-masonry-wind-negative", "反向风压", "wind", "calculated", "kN/m2", "GB 50009-2012 风荷载向导", "wall_system", default=0.40, direction="x_negative"),
            ],
        ),
    ),
)

_replace_public_variant(
    "retaining-facility",
    _variant(
        "gravity",
        "重力式挡土墙",
        "土水作用进入重力墙核心，完成墙体自重、滑移、倾覆、基底接触和地基压力传力链。",
        ["素混凝土/石砌体等效重力墙"],
        [
            _number("retained_height_m", "挡土高度", "m", 2.0),
            _number("base_width_m", "底座宽度", "m", 2.4),
            _number("wall_bottom_thickness_m", "墙底厚度", "m", 1.2),
            _number("wall_top_thickness_m", "墙顶厚度", "m", 0.5),
            _number("toe_projection_m", "趾部挑出", "m", 0.7),
            _number("water_depth_behind_m", "墙后水深", "m", 0.0),
        ],
        support_system="墙体底座+地基接触",
        graph=GRAVITY_RETAINING_GRAPH,
        load_package=_package(
            "gravity-retaining-loads-v32",
            "重力式挡墙土水资料包",
            "地勘参数和水位通过 typed inputs 进入墙体；本包仅保存来源和采用工况。",
            [
                _load("gravity-soil-source", "地勘土参数资料", "custom", "fixed", "1", "项目勘察资料", "soil_water_inputs", default=1.0, distribution="point"),
                _load("gravity-surcharge", "墙后附加荷载", "soil", "reference_range", "kPa", "项目使用条件", "soil_water_inputs", minimum=0.0, default=5.0, maximum=20.0, distribution="pressure", direction="x_positive"),
                _load("gravity-water-head", "墙后水位工况", "water", "project_defined", "m", "项目地下水资料", "soil_water_inputs", default=0.0, distribution="pressure", direction="x_positive"),
            ],
        ),
    ),
)

_replace_public_variant(
    "pergola-pavilion",
    _variant(
        "mono-pitch",
        "单坡钢廊架",
        "覆盖层经连续檩条传至单坡参数化平面框架，再由双柱脚传至独立基础。",
        ["钢"],
        COMMON_FRAME_PARAMETERS
        + [_number("roof_slope_deg", "屋面坡度", "°", 8.0)],
        support_system="双柱落地",
        roof_form="单坡",
        graph=PERGOLA_MONO_GRAPH,
        load_package=PERGOLA_LOAD_PACKAGE,
    ),
)
_replace_public_variant(
    "pergola-pavilion",
    _variant(
        "dual-pitch",
        "双坡钢廊架",
        "左右坡面经连续檩条传至带屋脊节点的参数化框架，再传至双柱脚与基础。",
        ["钢"],
        COMMON_FRAME_PARAMETERS
        + [_number("roof_slope_deg", "屋面坡度", "°", 15.0)],
        support_system="双柱落地",
        roof_form="双坡",
        graph=PERGOLA_DUAL_GRAPH,
        load_package=PERGOLA_LOAD_PACKAGE,
    ),
)
_replace_public_variant(
    "pergola-pavilion",
    _variant(
        "multi-bay",
        "双跨 / 不同柱高钢廊架",
        "首版固定为双跨参数化框架，支持不同柱高与三个独立柱脚、基础反力。",
        ["钢"],
        COMMON_FRAME_PARAMETERS
        + [
            _number("bay_count", "跨数", "跨", 2.0),
            _number("right_height_m", "右柱高", "m", 3.0),
        ],
        support_system="三柱落地",
        roof_form="平顶 / 非对称",
        graph=PERGOLA_MULTI_GRAPH,
        load_package=PERGOLA_LOAD_PACKAGE,
    ),
)
_replace_public_variant(
    "canopy",
    _variant(
        "wall-cantilever",
        "墙附悬挑钢雨棚",
        "覆盖层作用传至悬挑钢梁与墙体锚栓组；墙附体系不生成基础节点。",
        ["钢"],
        [
            _number("cantilever_m", "悬挑长度", "m", 1.8),
            _number("width_m", "雨棚宽度", "m", 3.0),
            _choice(
                "wall_substrate",
                "墙体基材",
                ["钢筋混凝土", "实心砌体", "未知"],
                "钢筋混凝土",
            ),
        ],
        support_system="墙体锚固",
        roof_form="平顶",
        graph=CANOPY_WALL_PUBLIC_GRAPH,
        load_package=_roof_scene_package(
            "canopy-wall-public-loads-v32",
            "墙附悬挑雨棚荷载包",
            "secondary_beam",
            finish_default=0.35,
        ),
    ),
)
_replace_public_variant(
    "signage-billboard",
    _variant(
        "double-post",
        "双柱钢导视牌",
        "正负面板风压传至双柱平面框架，并分别传至两组柱脚与独立基础。",
        ["钢"],
        [
            _number("panel_width_m", "面板宽度", "m", 2.4),
            _number("panel_height_m", "面板高度", "m", 1.2),
            _number("post_spacing_m", "柱间距", "m", 1.6),
        ],
        support_system="双柱落地",
        graph=SIGN_DOUBLE_GRAPH,
        load_package=SIGN_PUBLIC_LOAD_PACKAGE,
    ),
)
_replace_public_variant(
    "signage-billboard",
    _variant(
        "ground-mounted",
        "钢构落地式导视牌",
        "面板作用传至落地式钢悬臂框架、底板锚栓和独立基础。",
        ["钢"],
        [
            _number("panel_width_m", "面板宽度", "m", 2.0),
            _number("panel_height_m", "面板高度", "m", 1.5),
            _number("base_width_m", "底座宽度", "m", 0.8),
        ],
        support_system="钢底座落地",
        graph=SIGN_GROUND_GRAPH,
        load_package=SIGN_PUBLIC_LOAD_PACKAGE,
    ),
)
_replace_public_variant(
    "signage-billboard",
    _variant(
        "eccentric-panel",
        "偏心 / 倾斜钢导视牌",
        "按面板偏心距和倾角生成剪力、弯矩及扭矩，并传至柱脚与独立基础。",
        ["钢"],
        [
            _number("panel_width_m", "面板宽度", "m", 1.5),
            _number("eccentricity_m", "面板偏心距", "m", 0.3),
            _number("tilt_deg", "面板倾角", "°", 8.0),
        ],
        support_system="单柱落地",
        graph=SIGN_ECCENTRIC_GRAPH,
        load_package=SIGN_PUBLIC_LOAD_PACKAGE,
    ),
)
_replace_public_variant(
    "entrance-frame",
    _variant(
        "multi-span",
        "双跨钢门楼",
        "首版固定为双跨参数化门楼，三个支点分别传至柱脚与独立基础。",
        ["钢"],
        COMMON_FRAME_PARAMETERS + [_number("bay_count", "跨数", "跨", 2.0)],
        support_system="三柱落地",
        graph=ENTRANCE_MULTI_GRAPH,
        load_package=ENTRANCE_LOAD_PACKAGE,
    ),
)
_replace_public_variant(
    "entrance-frame",
    _variant(
        "eccentric-lintel",
        "偏心门楣钢门楼",
        "偏心门楣和招牌作用进入参数化平面框架，再传至双柱脚与独立基础。",
        ["钢"],
        COMMON_FRAME_PARAMETERS
        + [_number("eccentricity_m", "偏心距", "m", 0.5)],
        support_system="双柱落地",
        graph=ENTRANCE_ECCENTRIC_GRAPH,
        load_package=ENTRANCE_LOAD_PACKAGE,
    ),
)
_replace_public_variant(
    "entrance-frame",
    _variant(
        "unequal-columns",
        "不同柱高钢门楼",
        "不同柱高形成非对称参数化框架，左右反力独立传至柱脚和基础。",
        ["钢"],
        COMMON_FRAME_PARAMETERS
        + [_number("right_height_m", "右柱高", "m", 3.6)],
        support_system="双柱落地",
        graph=ENTRANCE_UNEQUAL_GRAPH,
        load_package=ENTRANCE_LOAD_PACKAGE,
    ),
)
_replace_public_variant(
    "boardwalk-platform",
    _variant(
        "viewing-platform",
        "混凝土板 + 钢梁观景平台",
        "人群与面层作用经双向板、连续次梁和主梁传至左右柱脚与独立基础。",
        ["混凝土板+钢构"],
        [
            _number("short_span_m", "平台板短跨", "m", 3.0),
            _number("long_span_m", "平台板长跨", "m", 4.5),
            _number("slab_thickness_mm", "平台板厚度", "mm", 140.0),
            _number("secondary_spacing_m", "次梁间距", "m", 1.5),
            _number("primary_spacing_m", "主梁间距", "m", 3.0),
        ],
        support_system="双柱脚+独立基础",
        graph=VIEWING_PLATFORM_GRAPH,
        load_package=BOARDWALK_LOAD_PACKAGE,
    ),
)

_POOL_PARAMETERS = [
    _number("inside_length_m", "池内净长", "m", 6.0),
    _number("inside_width_m", "池内净宽", "m", 3.0),
    _number("wall_height_m", "池壁高度", "m", 1.5),
    _number("wall_thickness_mm", "池壁厚度", "mm", 200.0),
    _number("base_thickness_mm", "底板厚度", "mm", 250.0),
    _number("internal_water_depth_m", "池内设计水深", "m", 1.2),
    _number("external_water_head_m", "池外抗浮水头", "m", 0.8),
    _number("allowable_bearing_kpa", "地基承载力", "kPa", 120.0),
]

for _variant_id, _title, _description, _graph_template, _support in (
    (
        "rect-above",
        "矩形地上水池（浅基础）",
        "地上矩形 RC 池壁、底板、满池/空池组合、裂缝、基底压力与抗浮闭环。",
        POOL_ABOVE_SHALLOW_GRAPH,
        "池底板浅基础",
    ),
    (
        "rect-semi-buried",
        "矩形半地下水池（浅基础）",
        "半地下 RC 池体同时考虑内水、外侧土水压力、空池抗浮和池底浅基础。",
        POOL_SEMI_SHALLOW_GRAPH,
        "池底板浅基础",
    ),
    (
        "rect-buried",
        "矩形地下水池（浅基础）",
        "地下 RC 池体按空池、满池及内外水位组合验算池壁、底板、抗浮和基底压力。",
        POOL_BURIED_SHALLOW_GRAPH,
        "池底板浅基础",
    ),
    (
        "rect-above-pile",
        "矩形地上水池（桩承台）",
        "池体组合反力按同一组合传入勘察承载力驱动的桩群与承台。",
        POOL_ABOVE_PILE_GRAPH,
        "池底板+桩群承台",
    ),
    (
        "rect-semi-buried-pile",
        "矩形半地下水池（桩承台）",
        "半地下池体的重力、土水和浮力组合传至抗浮桩群承台。",
        POOL_SEMI_PILE_GRAPH,
        "池底板+抗浮桩群承台",
    ),
    (
        "rect-buried-pile",
        "矩形地下水池（桩承台）",
        "地下池空池抗浮与满池组合分别传至桩群承台，不拼接不同组合效应。",
        POOL_BURIED_PILE_GRAPH,
        "池底板+抗浮桩群承台",
    ),
):
    _replace_public_variant(
        "water-feature-pool",
        _variant(
            _variant_id,
            _title,
            _description,
            ["钢筋混凝土"],
            _POOL_PARAMETERS,
            support_system=_support,
            graph=_graph_template,
            load_package=POOL_PUBLIC_LOAD_PACKAGE,
        ),
    )

_BRIDGE_PARAMETERS = [
    _number("span_length_m", "等跨跨径", "m", 6.0),
    _number("deck_width_m", "桥面净宽", "m", 2.5),
    _number("crossbeam_spacing_m", "横梁间距", "m", 1.5),
    _number("crowd_load_kpa", "人群荷载", "kPa", 4.0),
    _number("wind_load_kpa", "横向风压", "kPa", 0.5),
]

for _variant_id, _title, _description, _material, _graph_template, _support in (
    (
        "single-straight",
        "单跨钢梁 + 木桥面（浅基础）",
        "木桥面板、钢横纵梁和两端浅基础的直线人行桥。",
        "钢梁+木桥面",
        BRIDGE_ST_SINGLE_SHALLOW_GRAPH,
        "两端浅基础",
    ),
    (
        "single-steel-timber-pile",
        "单跨钢梁 + 木桥面（桩基）",
        "上部反力分别传入两端勘察承载力驱动的桩群承台。",
        "钢梁+木桥面",
        BRIDGE_ST_SINGLE_PILE_GRAPH,
        "两端桩群承台",
    ),
    (
        "multi-span",
        "双跨钢梁 + 木桥面（浅基础）",
        "首版固定为等跨双跨，三处支座分别传至浅基础。",
        "钢梁+木桥面",
        BRIDGE_ST_MULTI_SHALLOW_GRAPH,
        "三处浅基础",
    ),
    (
        "multi-steel-timber-pile",
        "双跨钢梁 + 木桥面（桩基）",
        "等跨双跨上部结构的三组支反力分别传至桩群承台。",
        "钢梁+木桥面",
        BRIDGE_ST_MULTI_PILE_GRAPH,
        "三处桩群承台",
    ),
    (
        "single-rc-shallow",
        "单跨全混凝土桥（浅基础）",
        "RC 桥面板、纵梁、墩台反力与两端浅基础的参数化直线人行桥。",
        "全混凝土",
        BRIDGE_RC_SINGLE_SHALLOW_GRAPH,
        "两端浅基础",
    ),
    (
        "single-rc-pile",
        "单跨全混凝土桥（桩基）",
        "RC 上部结构的同组合六分量反力分别传至两端桩群承台。",
        "全混凝土",
        BRIDGE_RC_SINGLE_PILE_GRAPH,
        "两端桩群承台",
    ),
    (
        "multi-rc-shallow",
        "双跨全混凝土桥（浅基础）",
        "首版固定为等跨双跨 RC 板梁桥和三处浅基础。",
        "全混凝土",
        BRIDGE_RC_MULTI_SHALLOW_GRAPH,
        "三处浅基础",
    ),
    (
        "multi-rc-pile",
        "双跨全混凝土桥（桩基）",
        "等跨双跨 RC 上部结构与三处桩群承台的完整传力链。",
        "全混凝土",
        BRIDGE_RC_MULTI_PILE_GRAPH,
        "三处桩群承台",
    ),
):
    _replace_public_variant(
        "landscape-bridge",
        _variant(
            _variant_id,
            _title,
            _description,
            [_material],
            _BRIDGE_PARAMETERS,
            support_system=_support,
            graph=_graph_template,
            load_package=BRIDGE_PUBLIC_LOAD_PACKAGE,
        ),
    )

for _family_id, _boundaries in (
    (
        "water-feature-pool",
        [
            "仅覆盖矩形、规则池壁和底板；不覆盖异形池、温度作用和不均匀沉降",
            "地下水位未知或桩承载力无勘察来源时专业结果保持 incomplete",
        ],
    ),
    (
        "landscape-bridge",
        [
            "仅覆盖直线人行梁桥；多跨首版固定为等跨双跨",
            "不覆盖车行、曲线、拱桥、索桥、复杂动力和河道冲刷",
        ],
    ),
):
    _family = next(item for item in SCENE_FAMILIES if item.id == _family_id)
    _family.boundaries = _boundaries

# Prefer the smallest complete path when opening a family with several newly
# published variants.  Other public variants remain selectable in the same
# family and development variants remain explicitly blocked.
for _family_id, _default_variant in (
    ("pergola-pavilion", "flat-single"),
    ("canopy", "single-row"),
    ("signage-billboard", "single-post"),
    ("entrance-frame", "single-span"),
    ("boardwalk-platform", "straight"),
    ("water-feature-pool", "rect-above"),
    ("landscape-bridge", "single-straight"),
    ("bench-planter", "bench"),
    ("landscape-wall-fence", "constrained-masonry"),
    ("retaining-facility", "cantilever-rc"),
):
    _family = next(item for item in SCENE_FAMILIES if item.id == _family_id)
    _family.default_variant_id = _default_variant
    _family.graph_template = next(
        item for item in _family.variants if item.id == _default_variant
    ).graph_template or _family.graph_template


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
