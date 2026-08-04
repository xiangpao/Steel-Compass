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
        Paragraph(f"模式：{'方案快算' if result.mode.value == 'quick' else '专业计算 Beta'}", body),
        Paragraph(f"模块：{escape(result.module.value)}", body),
        Paragraph(f"计算引擎：{escape(result.engine_version)}", body),
        Paragraph(f"追踪编号：{escape(result.trace_id)}", body),
        Spacer(1, 4 * mm),
        Paragraph(
            f"控制结论：{status_labels[result.status]}",
            heading,
        ),
        Paragraph(escape(result.disclaimer), body),
        Paragraph("规范基线", heading),
    ]
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
            f"模式：{'方案快算' if scene_result.mode.value == 'quick' else '专业计算 Beta'}",
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
            "缺少勘察资料的节点均不得解释为已通过；专业模式仍需具备资格的专业人员复核。",
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
