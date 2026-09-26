from __future__ import annotations

from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.graphics.shapes import Circle, Drawing, Line, Rect, String
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from pypdf import PdfReader, PdfWriter

from .core.schemas import CalculationResult
from .core.scene_schemas import SceneRevisionResult


pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


def build_calculation_pdf(result: CalculationResult, report_number: str) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Steel-Compass {report_number}",
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "ChineseBody",
        parent=styles["BodyText"],
        fontName="STSong-Light",
        fontSize=9,
        leading=14,
    )
    title = ParagraphStyle(
        "ChineseTitle",
        parent=styles["Title"],
        fontName="STSong-Light",
        fontSize=18,
        leading=24,
        alignment=TA_CENTER,
    )
    heading = ParagraphStyle(
        "ChineseHeading",
        parent=styles["Heading2"],
        fontName="STSong-Light",
        fontSize=12,
        leading=18,
        spaceBefore=10,
    )
    status_labels = {
        "passed": "当前输入与适用范围内通过",
        "failed": "当前输入或适用范围内不通过",
        "incomplete": "资料不完整，禁止形成通过结论",
        "not_applicable": "超出当前模块适用范围",
    }
    story = [
        Paragraph("Steel-Compass V2 结构计算报告", title),
        Spacer(1, 6 * mm),
        Paragraph(f"报告编号：{escape(report_number)}", body),
        Paragraph(f"项目：{escape(result.project_name)}", body),
        Paragraph(f"定位：{'方案筛查' if result.mode.value == 'quick' else '历史专业记录（只读）'}", body),
        Paragraph(f"模块：{escape(result.module.value)}", body),
        Paragraph(f"计算引擎：{escape(result.engine_version)}", body),
        Paragraph(f"追踪编号：{escape(result.trace_id)}", body),
        Spacer(1, 4 * mm),
        Paragraph(
            f"控制结论：{status_labels[result.status]}",
            heading,
        ),
        Paragraph("规范基线", heading),
    ]
    if result.schema_version not in {"3.2", "3.3"} and result.disclaimer:
        story.insert(-1, Paragraph(escape(result.disclaimer), body))
    story.extend(Paragraph(f"• {escape(item)}", body) for item in result.standards)
    if result.catalog_versions:
        story.append(Paragraph("版本追溯", heading))
        version_rows = [["目录/对象", "版本"]]
        version_rows.extend(
            [escape(name), escape(version)]
            for name, version in sorted(result.catalog_versions.items())
        )
        version_table = Table(
            version_rows, colWidths=[55 * mm, 105 * mm], repeatRows=1
        )
        version_table.setStyle(_table_style())
        story.append(version_table)
    if result.load_provenance:
        story.append(Paragraph("荷载来源与采用值", heading))
        load_rows = [["类别", "采用值", "方向", "来源", "预设/覆盖说明"]]
        for load in result.load_provenance:
            provenance = load.preset_id or "自定义"
            if load.override_reason:
                provenance = f"{provenance}；覆盖原因：{load.override_reason}"
            load_rows.append(
                [
                    escape(load.kind.value),
                    f"{load.value:.4g} {escape(load.unit)}",
                    escape(load.direction.value),
                    escape(
                        "；".join(
                            item
                            for item in (load.source, load.source_reference)
                            if item
                        )
                    ),
                    escape(provenance),
                ]
            )
        load_table = Table(
            load_rows,
            colWidths=[22 * mm, 26 * mm, 25 * mm, 48 * mm, 43 * mm],
            repeatRows=1,
        )
        load_table.setStyle(_table_style())
        story.append(load_table)
    story.append(Paragraph("输入摘要", heading))
    input_rows = [["参数", "数值"]]
    for key, value in result.input_summary.items():
        if isinstance(value, str):
            display = value
        elif isinstance(value, bool):
            display = "是" if value else "否"
        else:
            display = f"{value.value:.4g} {value.unit}"
        input_rows.append([escape(key), escape(display)])
    input_table = Table(input_rows, colWidths=[55 * mm, 105 * mm], repeatRows=1)
    input_table.setStyle(_table_style())
    story.append(input_table)
    story.append(Paragraph("验算汇总", heading))
    check_rows = [["验算项", "需求", "能力/限值", "利用率", "结论"]]
    for item in result.checks:
        check_rows.append(
            [
                escape(item.name),
                f"{item.demand.value:.4g} {escape(item.demand.unit)}",
                f"{item.capacity.value:.4g} {escape(item.capacity.unit)}",
                f"{item.utilization * 100:.1f}%",
                "通过" if item.passed else "不通过",
            ]
        )
    checks_table = Table(
        check_rows,
        colWidths=[38 * mm, 34 * mm, 34 * mm, 24 * mm, 24 * mm],
        repeatRows=1,
    )
    checks_table.setStyle(_table_style())
    story.append(checks_table)
    story.append(PageBreak())
    story.append(Paragraph("计算步骤与条文来源", heading))
    for index, step in enumerate(result.steps, 1):
        story.extend(
            [
                Paragraph(f"{index}. {escape(step.name)}", heading),
                Paragraph(f"公式：{escape(step.equation)}", body),
                Paragraph(f"代入：{escape(step.substitution)}", body),
                Paragraph(
                    f"结果：{step.result.value:.6g} {escape(step.result.unit)}", body
                ),
                Paragraph(f"来源：{escape(step.reference)}", body),
            ]
        )
    story.append(Paragraph("假定与适用范围", heading))
    story.extend(Paragraph(f"• {escape(item)}", body) for item in result.assumptions)
    story.extend(Paragraph(f"• {escape(item)}", body) for item in result.applicability)
    if result.warnings:
        story.append(Paragraph("警告", heading))
        story.extend(
            Paragraph(f"• [{escape(item.severity)}] {escape(item.message)}", body)
            for item in result.warnings
        )
    document.build(story)
    return buffer.getvalue()


def build_project_pdf(
    results: list[CalculationResult], report_number: str
) -> bytes:
    writer = PdfWriter()
    for index, result in enumerate(results, 1):
        part = build_calculation_pdf(result, f"{report_number}-N{index:02d}")
        reader = PdfReader(BytesIO(part))
        for page in reader.pages:
            writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def build_scene_project_pdf(
    scene_result: SceneRevisionResult,
    results: list[CalculationResult],
    report_number: str,
    project_title: str,
    scene_context: dict | None = None,
) -> bytes:
    cover_buffer = BytesIO()
    document = SimpleDocTemplate(
        cover_buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Steel-Compass {report_number}",
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "SceneChineseBody",
        parent=styles["BodyText"],
        fontName="STSong-Light",
        fontSize=9,
        leading=14,
    )
    title = ParagraphStyle(
        "SceneChineseTitle",
        parent=styles["Title"],
        fontName="STSong-Light",
        fontSize=18,
        leading=24,
        alignment=TA_CENTER,
    )
    heading = ParagraphStyle(
        "SceneChineseHeading",
        parent=styles["Heading2"],
        fontName="STSong-Light",
        fontSize=12,
        leading=18,
        spaceBefore=10,
    )
    status_label = {
        "passed": "当前输入和适用范围内完整通过",
        "failed": "存在不满足节点",
        "incomplete": "场景计算链不完整，禁止形成整体通过结论",
    }[scene_result.status]
    scene_context = scene_context or {}
    draft_state = scene_context.get("draft_state", {})
    story = [
        Paragraph("Steel-Compass V2 完整场景计算报告", title),
        Spacer(1, 6 * mm),
        Paragraph(f"报告编号：{escape(report_number)}", body),
        Paragraph(f"场景 / 方案：{escape(project_title)}", body),
        Paragraph(
            f"场景族：{escape(scene_result.scene_family_id)}；"
            f"变体：{escape(scene_result.scene_variant_id)}",
            body,
        ),
        Paragraph(
            f"定位：{'方案筛查' if scene_result.mode.value == 'quick' else '历史专业记录（只读）'}",
            body,
        ),
        Paragraph(f"整体状态：{status_label}", heading),
        Paragraph(
            f"工作流状态：{escape(scene_result.workflow_status)}；"
            f"结果类型：{escape(scene_result.result_class or '')}；"
            f"验证状态：{escape(scene_result.verification_status)}",
            body,
        ),
        Paragraph(
            f"已完成 {scene_result.completed_nodes} / "
            f"{scene_result.total_required_nodes} 个必选节点。",
            body,
        ),
        Paragraph("传力链与节点状态", heading),
    ]
    geometry = draft_state.get("geometry", {})
    project_rows = [
        ["项目输入", "保存值"],
        ["材料体系", str(draft_state.get("material_system") or "未记录")],
        ["支承 / 基础", str(draft_state.get("foundation_type") or "不适用或未记录")],
        [
            "地基承载力",
            (
                f"{draft_state.get('allowable_bearing_kpa')} kPa"
                if draft_state.get("allowable_bearing_kpa") not in (None, "")
                else "不适用或未记录"
            ),
        ],
        ["几何参数", "；".join(f"{key}={value}" for key, value in geometry.items()) or "未记录"],
    ]
    project_table = Table(project_rows, colWidths=[40 * mm, 120 * mm], repeatRows=1)
    project_table.setStyle(_table_style())
    story.extend([Paragraph("保存输入摘要", heading), project_table])
    node_rows = [["节点", "成熟度", "状态", "说明"]]
    for node_result in scene_result.node_results.values():
        node_rows.append(
            [
                escape(node_result.label),
                escape(node_result.maturity),
                escape(node_result.status),
                escape(node_result.message or ("结果已过期" if node_result.stale else "")),
            ]
        )
    node_table = Table(
        node_rows,
        colWidths=[42 * mm, 24 * mm, 28 * mm, 66 * mm],
        repeatRows=1,
    )
    node_table.setStyle(_table_style())
    story.append(node_table)
    story.append(Paragraph("未覆盖与不可用结论", heading))
    if scene_result.missing_nodes:
        story.extend(
            Paragraph(f"• {escape(item)}", body)
            for item in scene_result.missing_nodes
        )
    else:
        story.append(Paragraph("无缺失必选节点。", body))
    story.append(Paragraph("场景荷载采用值", heading))
    load_rows = [["荷载", "建议 / 采用值", "方向与目标", "来源"]]
    for item in scene_result.load_cases:
        recommendation = (
            f"{item.recommended_min:g}–{item.recommended_max:g}"
            if item.recommended_min is not None
            and item.recommended_max is not None
            and item.recommended_min != item.recommended_max
            else f"{item.recommended_default:g}"
            if item.recommended_default is not None
            else "按参数计算"
        )
        adopted = (
            f"{item.adopted_value:g} {item.unit}"
            if item.adopted_value is not None
            else "未填写"
        )
        load_rows.append(
            [
                escape(item.label),
                escape(f"建议 {recommendation}；采用 {adopted}"),
                escape(f"{item.direction} → {item.application_target}"),
                escape(item.source_reference),
            ]
        )
    if len(load_rows) == 1:
        load_rows.append(["无", "—", "—", "—"])
    load_table = Table(
        load_rows,
        colWidths=[34 * mm, 46 * mm, 35 * mm, 45 * mm],
        repeatRows=1,
    )
    load_table.setStyle(_table_style())
    story.append(load_table)
    if scene_result.site_profile:
        profile = scene_result.site_profile
        applied_conditions = set(scene_result.applied_conditions)
        if not applied_conditions:
            # Schema 3.3 and earlier reports have no applied_conditions field.
            applied_conditions = set(profile.get("completed_conditions", []))
        story.append(Paragraph("项目条件采用值", heading))
        profile_rows = []
        if {"wind", "snow"} & applied_conditions:
            profile_rows.extend(
                [
                    ["地区档", escape(str(profile.get("region_preset", "—")))],
                    ["重现期", escape(f"{profile.get('recurrence_period_years', '—')} 年")],
                ]
            )
        if "wind" in applied_conditions:
            profile_rows.append(
                ["基本风压", escape(f"{profile.get('basic_wind_pressure_kpa', '—')} kPa")]
            )
        if "snow" in applied_conditions:
            profile_rows.append(
                ["基本雪压", escape(f"{profile.get('basic_snow_pressure_kpa', '—')} kPa")]
            )
        if "seismic" in applied_conditions:
            profile_rows.append(["地震档", escape(str(profile.get("seismic_level", "—")))])
        if {"wind", "snow"} & applied_conditions:
            profile_rows.append(
                ["资料来源", escape(str(profile.get("climate_source_reference", "—")))]
            )
        profile_rows.append(["用户覆盖原因", escape(str(profile.get("override_reason") or "无"))])
        profile_table = Table(profile_rows, colWidths=[45 * mm, 115 * mm])
        profile_table.setStyle(_table_style())
        story.append(profile_table)
    if scene_result.geotechnical_profile:
        geotechnical = scene_result.geotechnical_profile
        groundwater = geotechnical.get("groundwater", {})
        story.append(Paragraph("地勘与地下水采用值", heading))
        geotechnical_rows = [
            ["资料阶段", escape(str(geotechnical.get("stage", "—")))],
            ["土质档", escape(str(geotechnical.get("confirmed_soil_class", "—")))],
            ["地基承载力", escape(f"{geotechnical.get('bearing_capacity_kpa', '—')} kPa")],
            ["承载力来源", escape(str(geotechnical.get("bearing_capacity_source", "—")))],
            ["沉降参数", escape(str(geotechnical.get("deformation_modulus_mpa") or geotechnical.get("compression_modulus_mpa") or "资料不足"))],
            ["施工/使用/抗浮水位", escape(f"{groundwater.get('construction_level_m', '—')} / {groundwater.get('service_level_m', '—')} / {groundwater.get('antifloat_level_m', '—')} m")],
            ["地下水来源", escape(str(groundwater.get("source", "—")))],
        ]
        geotechnical_table = Table(geotechnical_rows, colWidths=[45 * mm, 115 * mm])
        geotechnical_table.setStyle(_table_style())
        story.append(geotechnical_table)
    if scene_result.structural_profile:
        structural = scene_result.structural_profile
        story.append(Paragraph("构件与基础明确选型", heading))
        design_rows = [["对象", "材料/体系", "规格或尺寸", "来源"]]
        for member in structural.get("members", []):
            design_rows.append([
                escape(f"{member.get('node_id')} / {member.get('member_role')}"),
                escape(str(member.get("material_grade", "—"))),
                escape(str(member.get("section_name", "—"))),
                escape(str(member.get("selection_source", "—"))),
            ])
        for foundation in structural.get("foundations", []):
            pedestal = foundation.get("pedestal") or {}
            pedestal_text = (
                f"；短柱 {pedestal.get('length_mm')}×{pedestal.get('width_mm')}×{pedestal.get('height_mm')}mm"
                if pedestal.get("enabled")
                else "；无短柱"
            )
            design_rows.append([
                escape(str(foundation.get("node_id", "—"))),
                escape(str(foundation.get("foundation_system_id", "—"))),
                escape(f"{foundation.get('length_m')}×{foundation.get('width_m')}m，厚 {foundation.get('thickness_mm')}mm，埋深 {foundation.get('embedment_m')}m；{foundation.get('concrete_grade')} / {foundation.get('rebar_grade')} Φ{foundation.get('bar_diameter_mm')}@{foundation.get('bar_spacing_mm')}{pedestal_text}"),
                escape(str(foundation.get("selection_source", "—"))),
            ])
        design_table = Table(design_rows, colWidths=[35 * mm, 35 * mm, 55 * mm, 35 * mm], repeatRows=1)
        design_table.setStyle(_table_style())
        story.append(design_table)
        geometry = structural.get("geometry") or {}
        connection_types = {item.get("id"): item for item in geometry.get("connection_types", [])}
        if geometry.get("connection_instances") or geometry.get("column_bases"):
            story.append(Paragraph("连接、柱脚与锚栓", heading))
            connection_rows = [["编号", "类型", "关联对象", "状态/规格"]]
            for item in geometry.get("connection_instances", []):
                connection_type = connection_types.get(item.get("connection_type_id"), {})
                connection_rows.append([
                    escape(str(item.get("mark", "—"))),
                    escape(str(connection_type.get("title", item.get("connection_type_id", "—")))),
                    escape(f"节点 {item.get('node_id')} / {', '.join(item.get('member_ids', []))}"),
                    escape(str(item.get("status", "未计算"))),
                ])
            for item in geometry.get("column_bases", []):
                connection_rows.append([
                    escape(str(item.get("id", "—"))),
                    "柱脚底板与锚栓",
                    escape(f"柱 {item.get('column_member_id')} / 支承 {item.get('support_id')}"),
                    escape(f"底板 {item.get('base_plate_length_mm')}×{item.get('base_plate_width_mm')}×{item.get('base_plate_thickness_mm')}mm；{item.get('anchor_count')}-M{item.get('anchor_diameter_mm')}，锚固 {item.get('anchor_embedment_mm')}mm"),
                ])
            connection_table = Table(connection_rows, colWidths=[25 * mm, 40 * mm, 45 * mm, 50 * mm], repeatRows=1)
            connection_table.setStyle(_table_style())
            story.append(connection_table)
    if scene_result.space_frame_analysis:
        analysis = scene_result.space_frame_analysis
        story.append(Paragraph("参数化三维杆系分析", heading))
        analysis_rows = [
            ["求解器", escape(str(analysis.get("solver", "—")))],
            ["模型规模", escape(f"{analysis.get('node_count', 0)} 节点 / {analysis.get('member_count', 0)} 杆件")],
            ["屋面面积", escape(f"{analysis.get('roof_area_m2', 0)} m²")],
            ["最大空间位移", escape(f"{analysis.get('maximum_translation_mm', 0)} mm")],
            ["支座反力组", escape(str(len(analysis.get("support_reactions", {}))))],
            ["荷载范围", escape(str(analysis.get("load_scope", "—")))],
        ]
        analysis_table = Table(analysis_rows, colWidths=[45 * mm, 115 * mm])
        analysis_table.setStyle(_table_style())
        story.append(analysis_table)
    if scene_result.seismic_action_package:
        seismic = scene_result.seismic_action_package
        story.append(Paragraph("等效地震作用（方案筛查）", heading))
        seismic_rows = [
            ["重力荷载代表值 G_eq", escape(f"{seismic.get('gravity_representative_value_kn', 0):g} kN")],
            ["地震影响系数 alpha1", escape(f"{seismic.get('alpha1', 0):g}")],
            ["水平地震作用 F_Ek", escape(f"±{seismic.get('f_ek_kn', 0):g} kN（X/Y）")],
            ["公式", escape(str(seismic.get("formula", "F_Ek = alpha1 * G_eq")))],
            ["来源", escape(str(seismic.get("source_reference", "—")))],
        ]
        seismic_table = Table(seismic_rows, colWidths=[55 * mm, 105 * mm])
        seismic_table.setStyle(_table_style())
        story.append(seismic_table)
    story.append(Paragraph("版本追溯", heading))
    version_rows = [["目录/对象", "版本"]]
    version_rows.extend(
        [escape(name), escape(version)]
        for name, version in sorted(scene_result.catalog_versions.items())
    )
    version_table = Table(
        version_rows, colWidths=[55 * mm, 105 * mm], repeatRows=1
    )
    version_table.setStyle(_table_style())
    story.append(version_table)
    story.append(Paragraph("适用范围与警告", heading))
    story.extend(
        Paragraph(f"• {escape(item)}", body) for item in scene_result.warnings
    )
    story.append(
        Paragraph(
            "本报告中的场景整体结论以完整传力链为前提。人工输入、规划中节点和"
            "缺少勘察资料的节点均不得解释为已通过。本报告面向非结构设计人员进行方案筛查，不可直接用于施工图或送审。",
            body,
        )
    )
    document.build(story)

    writer = PdfWriter()
    for page in PdfReader(BytesIO(cover_buffer.getvalue())).pages:
        writer.add_page(page)
    for index, result in enumerate(results, 1):
        part = build_calculation_pdf(result, f"{report_number}-N{index:02d}")
        for page in PdfReader(BytesIO(part)).pages:
            writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def build_scene_analysis_snapshot_pdf(snapshot: dict, report_number: str) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Steel-Compass {report_number}",
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle("SnapshotBody", parent=styles["BodyText"], fontName="STSong-Light", fontSize=8, leading=12)
    title = ParagraphStyle("SnapshotTitle", parent=styles["Title"], fontName="STSong-Light", fontSize=17, leading=23, alignment=TA_CENTER)
    heading = ParagraphStyle("SnapshotHeading", parent=styles["Heading2"], fontName="STSong-Light", fontSize=11, leading=16, spaceBefore=8)
    cell_style = ParagraphStyle("SnapshotCell", parent=body, wordWrap="CJK", splitLongWords=True)
    def wrapped_table(rows, **kwargs):
        return Table([[Paragraph(escape(str(value)), cell_style) for value in row] for row in rows], **kwargs)
    analysis = snapshot.get("analysis", {})
    structural = analysis.get("structural_analysis", {})
    story = [
        Paragraph("Steel-Compass 亭廊结构分析计算书", title),
        Spacer(1, 4 * mm),
        Paragraph(f"报告编号：{escape(report_number)}", body),
        Paragraph(f"快照：Schema {escape(str(snapshot.get('snapshot_schema_version', '4.0')))} / {escape(str(snapshot.get('standard_profile', 'CN-2026.7')))}", body),
        Paragraph(f"内容哈希：{escape(str(snapshot.get('content_hash', '—')))}", body),
        Paragraph(f"工作流状态：{escape(str(analysis.get('workflow_status', 'incomplete')))}", body),
        Paragraph("验证状态：未完成独立工程核验。此报告用于方案筛查，未计算或超出能力的项目不得解释为通过。", body),
        Paragraph("项目条件与屋面构造", heading),
    ]
    site = snapshot.get("site_profile", {})
    roof = snapshot.get("roof_load_selection", {})
    condition_rows = [
        ["地区档", str(site.get("region_preset", "—"))],
        ["基本风压 / 雪压", f"{site.get('basic_wind_pressure_kpa', '—')} / {site.get('basic_snow_pressure_kpa', '—')} kPa"],
        ["地震档", str(site.get("seismic_level", "—"))],
        ["屋面构造", str(roof.get("roof_assembly_id", "—"))],
        ["检修/使用类别", str(roof.get("maintenance_category", "—"))],
    ]
    geotechnical = snapshot.get("geotechnical_profile") or {}
    condition_rows.extend([
        ["地基阶段 / 持力层", f"{geotechnical.get('stage', '—')} / {geotechnical.get('confirmed_soil_class', '—')}"],
        ["地基承载力", f"{geotechnical.get('bearing_capacity_kpa', '—')} kPa"],
        ["沉降分层 / 允许值", f"{len(geotechnical.get('settlement_layers', []))} 层 / {geotechnical.get('settlement_limit_mm') if geotechnical.get('settlement_limit_mm') is not None else '未提供'} mm"],
    ])
    table = wrapped_table(condition_rows, colWidths=[48 * mm, 122 * mm])
    table.setStyle(_table_style())
    story.append(table)
    story.append(Paragraph("结构简图", heading))
    schematic_table = Table(
        [[*_scene_geometry_schematics(snapshot)]],
        colWidths=[42 * mm, 42 * mm, 42 * mm, 42 * mm],
    )
    schematic_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#A8B7BC")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D7E0E3")),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(schematic_table)

    story.append(Paragraph("荷载工况与组合", heading))
    load_rows = [["工况", "类别", "采用值", "方向", "来源"]]
    for item in snapshot.get("load_cases", []):
        load_rows.append([
            str(item.get("label", item.get("id", "—"))),
            str(item.get("kind", "—")),
            f"{item.get('adopted_value', '—')} {item.get('unit', '')}",
            str(item.get("direction", "—")),
            str(item.get("source_reference", "—")),
        ])
    table = wrapped_table(load_rows, colWidths=[32 * mm, 20 * mm, 25 * mm, 25 * mm, 68 * mm], repeatRows=1)
    table.setStyle(_table_style())
    story.append(table)
    combo_rows = [["组合", "设计状况", "系数"]]
    for item in snapshot.get("combinations", []):
        factors = "；".join(f"{key}×{value:g}" for key, value in item.get("factors", {}).items())
        combo_rows.append([str(item.get("id", "—")), str(item.get("design_situation", "—")), factors])
    combo_table = wrapped_table(combo_rows, colWidths=[45 * mm, 30 * mm, 95 * mm], repeatRows=1)
    combo_table.setStyle(_table_style())
    story.append(combo_table)

    story.append(Paragraph("整体分析与支座反力", heading))
    solver = analysis.get("solver_result", {})
    summary_rows = [
        ["最大平动", f"{solver.get('maximum_translation_mm', '—')} mm"],
        ["荷载平衡最大残差", f"{solver.get('maximum_balance_residual_kn', '—')} kN"],
        ["荷载平衡", "满足" if solver.get("balanced") else "不满足/未完成"],
        ["最低弹性屈曲系数", str((analysis.get("buckling_analysis", {}).get("factors") or ["—"])[0])],
    ]
    summary_table = wrapped_table(summary_rows, colWidths=[58 * mm, 112 * mm])
    summary_table.setStyle(_table_style())
    story.append(summary_table)
    reaction_rows = [["支承节点", "Fx", "Fy", "Fz", "Mx", "My", "Mz", "控制组合来源"]]
    for item in structural.get("reactions", []):
        sources = [f"{key}: {value}" for key, value in item.get("component_sources", {}).items() if value]
        reaction_rows.append([
            str(item.get("support_node_id", "—")),
            f"{item.get('fx_kn', 0):.3f}", f"{item.get('fy_kn', 0):.3f}", f"{item.get('fz_kn', 0):.3f}",
            f"{item.get('mx_kn_m', 0):.3f}", f"{item.get('my_kn_m', 0):.3f}", f"{item.get('mz_kn_m', 0):.3f}",
            "；".join(sources) or "—",
        ])
    story.append(Paragraph("以下为分量包络，各分量可能由不同组合控制；不得拼接为同一组合反力。力单位 kN，力矩单位 kN·m。", body))
    reaction_table = wrapped_table(reaction_rows, colWidths=[22 * mm, 17 * mm, 17 * mm, 17 * mm, 17 * mm, 17 * mm, 17 * mm, 46 * mm], repeatRows=1)
    reaction_table.setStyle(_table_style())
    story.append(reaction_table)

    story.append(PageBreak())
    story.append(Paragraph("构件验算", heading))
    member_rows = [["构件", "材料/截面", "控制组合", "利用率", "结论"]]
    for item in analysis.get("member_checks", {}).get("items", []):
        member_rows.append([
            str(item.get("member_id", "—")),
            f"{item.get('material_grade', '—')} / {item.get('section_id', '—')}",
            str(item.get("controlling_case", "—")),
            str(item["utilization"]) if item.get("utilization") is not None else "未计算",
            "；".join(filter(None, [str(item.get("status", "—")), item.get("reason")])),
        ])
    member_table = wrapped_table(member_rows, colWidths=[25 * mm, 48 * mm, 45 * mm, 25 * mm, 27 * mm], repeatRows=1)
    member_table.setStyle(_table_style())
    story.append(member_table)

    def append_check_details(section_title: str, objects: list[dict]) -> None:
        rows = [["对象", "验算项目", "需求", "承载/限值", "利用率", "结论", "依据"]]
        for item in objects:
            object_id = item.get("mark") or item.get("member_id") or item.get("connection_id") or item.get("foundation_id") or "—"
            for check in item.get("checks", []):
                demand = check.get("demand", {})
                capacity = check.get("capacity", {})
                rows.append([
                    str(object_id), str(check.get("name", "—")),
                    f"{demand.get('value', '—')} {demand.get('unit', '')}",
                    f"{capacity.get('value', '—')} {capacity.get('unit', '')}",
                    f"{check.get('utilization', '—')}",
                    "满足" if check.get("passed") else "不满足",
                    str(check.get("reference", "—")),
                ])
        if len(rows) == 1:
            return
        story.append(Paragraph(section_title, heading))
        detail_table = wrapped_table(rows, colWidths=[18 * mm, 35 * mm, 25 * mm, 25 * mm, 18 * mm, 18 * mm, 31 * mm], repeatRows=1)
        detail_table.setStyle(_table_style())
        story.append(detail_table)

    append_check_details("构件逐项验算", analysis.get("member_checks", {}).get("items", []))

    for section_title, package_key in (("连接与柱脚", "connection_checks"), ("短柱、基础与地基", "foundation_checks")):
        story.append(Paragraph(section_title, heading))
        rows = [["对象", "状态", "控制/说明"]]
        for item in analysis.get(package_key, {}).get("items", []):
            object_id = item.get("mark") or item.get("connection_id") or item.get("foundation_id") or "—"
            checks = item.get("checks", [])
            summary = "；".join(str(check.get("name", check.get("id", ""))) for check in checks[:4]) or str(item.get("issue_code", "—"))
            rows.append([str(object_id), str(item.get("status", "—")), summary])
        package_table = wrapped_table(rows, colWidths=[35 * mm, 28 * mm, 107 * mm], repeatRows=1)
        package_table.setStyle(_table_style())
        story.append(package_table)
        append_check_details(f"{section_title}逐项验算", analysis.get(package_key, {}).get("items", []))
        if package_key == "foundation_checks":
            pedestal_objects = [
                item["pedestal_check"]
                for item in analysis.get(package_key, {}).get("items", [])
                if item.get("pedestal_check")
            ]
            append_check_details("短柱逐项验算", pedestal_objects)
            settlement_objects = []
            shape_objects = []
            for item in analysis.get(package_key, {}).get("items", []):
                settlement = item.get("settlement_check")
                if settlement:
                    settlement_objects.append({
                        "foundation_id": item.get("foundation_id"),
                        "checks": [settlement],
                    })
                for level in item.get("detailed_shape_checks", []):
                    shape_objects.append({
                        "foundation_id": f"{item.get('mark', item.get('foundation_id', '—'))} · {level.get('level', '转换截面')}",
                        "checks": level.get("checks", []),
                    })
            append_check_details("地基沉降逐项验算", settlement_objects)
            append_check_details("阶形/锥形基础转换截面验算", shape_objects)

    trace = analysis.get("trace", {})
    story.append(Paragraph("规范、假定与未完成能力", heading))
    for formula in trace.get("formulas", []):
        story.append(Paragraph(f"• {escape(str(formula.get('topic', '依据')))}：{escape(str(formula.get('source', '—')))}", body))
    for item in trace.get("unsupported_capabilities", []):
        story.append(Paragraph(f"• 未完成：{escape(str(item))}", body))
    story.append(Paragraph("计算书由不可变分析快照生成。任何显示为未计算、资料不足或不支持的项目均不得解释为通过。", body))
    document.build(story)
    return buffer.getvalue()


def _scene_geometry_schematics(snapshot: dict) -> tuple[Drawing, Drawing, Drawing, Drawing]:
    geometry = snapshot.get("geometry", {})
    nodes = {item.get("id"): item for item in geometry.get("nodes", [])}
    members = geometry.get("members", [])

    def make_view(title: str, projection) -> Drawing:
        width = 40 * mm
        height = 43 * mm
        drawing = Drawing(width, height)
        drawing.add(String(4, height - 10, title, fontName="STSong-Light", fontSize=7, fillColor=colors.HexColor("#17333B")))
        projected = {node_id: projection(node) for node_id, node in nodes.items()}
        values = list(projected.values()) or [(0.0, 0.0)]
        min_x = min(item[0] for item in values)
        max_x = max(item[0] for item in values)
        min_y = min(item[1] for item in values)
        max_y = max(item[1] for item in values)
        scale = min((width - 18) / max(max_x - min_x, 1.0), (height - 22) / max(max_y - min_y, 1.0))

        def point(value: tuple[float, float]) -> tuple[float, float]:
            return 9 + (value[0] - min_x) * scale, 6 + (value[1] - min_y) * scale

        label_boxes = []
        for member in members:
            start = projected.get(member.get("start_node_id"))
            end = projected.get(member.get("end_node_id"))
            if start is None or end is None:
                continue
            x1, y1 = point(start)
            x2, y2 = point(end)
            color = colors.HexColor("#B45309") if member.get("role") == "column" else colors.HexColor("#176879")
            drawing.add(Line(x1, y1, x2, y2, strokeColor=color, strokeWidth=1.2))
            label = str(member.get("id", ""))
            lx, ly = (x1 + x2) / 2 + 1, (y1 + y2) / 2 + 1
            box = (lx, ly, lx + len(label) * 2.5, ly + 6)
            overlaps = any(box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1] for b in label_boxes)
            if not overlaps and box[2] < width - 2:
                drawing.add(String(lx, ly, label, fontSize=4.5, fillColor=colors.HexColor("#40545B")))
                label_boxes.append(box)
        for node_id, projected_point in projected.items():
            x, y = point(projected_point)
            drawing.add(Circle(x, y, 1.4, fillColor=colors.white, strokeColor=colors.HexColor("#17333B"), strokeWidth=0.6))
        if title == "平面":
            support_nodes = {
                item.get("id"): nodes.get(item.get("node_id"))
                for item in geometry.get("supports", [])
            }
            foundation_types = {item.get("id"): item for item in geometry.get("foundation_types", [])}
            for foundation in geometry.get("foundation_instances", []):
                support = support_nodes.get(foundation.get("support_id"))
                foundation_type = foundation_types.get(foundation.get("foundation_type_id"), {})
                if not support:
                    continue
                x, y = point(projection(support))
                rect_width = max(float(foundation_type.get("length_m", 0.5)) * scale, 4)
                rect_height = max(float(foundation_type.get("width_m", 0.5)) * scale, 4)
                drawing.add(Rect(x - rect_width / 2, y - rect_height / 2, rect_width, rect_height, strokeColor=colors.HexColor("#6B7280"), fillColor=None, strokeWidth=0.5))
                drawing.add(String(x + 2, y - 7, str(foundation.get("mark", "")), fontName="STSong-Light", fontSize=4.5))
        return drawing

    return (
        make_view("平面", lambda item: (float(item.get("x_m", 0)), float(item.get("y_m", 0)))),
        make_view("X立面", lambda item: (float(item.get("x_m", 0)), float(item.get("z_m", 0)))),
        make_view("Y立面", lambda item: (float(item.get("y_m", 0)), float(item.get("z_m", 0)))),
        make_view(
            "轴测",
            lambda item: (
                float(item.get("x_m", 0)) - 0.45 * float(item.get("y_m", 0)),
                float(item.get("z_m", 0)) + 0.28 * float(item.get("y_m", 0)),
            ),
        ),
    )


def _table_style() -> TableStyle:
    return TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7EDF0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#17333B")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#A8B7BC")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )
