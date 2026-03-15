from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from trial_design_explorer.config import ASSETS_DIR
from trial_design_explorer.domain import ProtocolMetadata
from trial_design_explorer.services.audit_service import current_utc_timestamp
from trial_design_explorer.services.comparison_service import (
    build_action_register,
    build_cohort_definition_table,
    build_decision_signal_table,
    build_design_differential_table,
    build_endpoint_precedent_table,
    build_protocol_benchmark_table,
    build_trial_exemplar_table,
    metrics_to_dataframe,
    recommendations_to_dataframe,
)
from trial_design_explorer.services.protocol_service import protocol_metadata_from_session


PAGE_MARGIN = 1.6 * cm
CONTENT_WIDTH = A4[0] - (2 * PAGE_MARGIN)
HEADER_COLOR = colors.HexColor("#15324A")
SUBTLE_TEXT = colors.HexColor("#5F6B7A")
BORDER_COLOR = colors.HexColor("#D5DCE3")
SOFT_FILL = colors.HexColor("#F2F6F9")
ALERT_FILL = colors.HexColor("#EDF3F7")


def _build_styles():
    base_styles = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base_styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=28,
            textColor=HEADER_COLOR,
            spaceAfter=12,
            alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base_styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=SUBTLE_TEXT,
            spaceAfter=8,
        ),
        "section": ParagraphStyle(
            "SectionTitle",
            parent=base_styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=18,
            textColor=HEADER_COLOR,
            spaceBefore=10,
            spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base_styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.6,
            leading=14,
            textColor=colors.HexColor("#22313F"),
            spaceAfter=6,
            splitLongWords=False,
        ),
        "dense": ParagraphStyle(
            "Dense",
            parent=base_styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.0,
            leading=10,
            textColor=colors.HexColor("#22313F"),
            spaceAfter=4,
            splitLongWords=False,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base_styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=11,
            textColor=SUBTLE_TEXT,
        ),
        "right_small": ParagraphStyle(
            "RightSmall",
            parent=base_styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=11,
            textColor=SUBTLE_TEXT,
            alignment=TA_RIGHT,
        ),
    }
    return styles


def _header_footer(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(BORDER_COLOR)
    canvas.line(PAGE_MARGIN, height - 1.2 * cm, width - PAGE_MARGIN, height - 1.2 * cm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(SUBTLE_TEXT)
    canvas.drawString(PAGE_MARGIN, height - 0.95 * cm, "Trial Design Explorer | Clinical Trial Planning Report")
    canvas.drawRightString(width - PAGE_MARGIN, 0.8 * cm, f"Page {doc.page}")
    canvas.drawString(PAGE_MARGIN, 0.8 * cm, "Confidential draft for planning review")
    canvas.restoreState()


def _paragraph(text: str, style) -> Paragraph:
    return Paragraph((text or "").replace("\n", "<br/>"), style)


def _section_heading(title: str, styles) -> list:
    return [_paragraph(title, styles["section"]), HRFlowable(color=BORDER_COLOR, thickness=0.6), Spacer(1, 0.15 * cm)]


def _kv_table(rows: list[tuple[str, str]], styles) -> Table:
    data = [[_paragraph("<b>Field</b>", styles["body"]), _paragraph("<b>Value</b>", styles["body"])]]
    for label, value in rows:
        data.append([_paragraph(str(label), styles["body"]), _paragraph(str(value), styles["body"])])

    table = Table(data, colWidths=[5.1 * cm, 10.9 * cm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SOFT_FILL),
                ("TEXTCOLOR", (0, 0), (-1, 0), HEADER_COLOR),
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _normalize_col_widths(col_widths: list[float] | None) -> list[float] | None:
    if not col_widths:
        return col_widths
    total = sum(col_widths)
    if total <= CONTENT_WIDTH:
        return col_widths
    scale = CONTENT_WIDTH / total
    return [width * scale for width in col_widths]


def _dataframe_table(
    dataframe: pd.DataFrame,
    styles,
    col_widths: list[float] | None = None,
    style_key: str = "body",
    compact: bool = False,
) -> Table:
    safe_df = dataframe.fillna("").astype(str)
    style = styles[style_key]
    header = [_paragraph(f"<b>{column}</b>", style) for column in safe_df.columns]
    rows = [[_paragraph(value, style) for value in row] for row in safe_df.values.tolist()]
    data = [header] + rows
    table = Table(data, colWidths=_normalize_col_widths(col_widths), repeatRows=1, hAlign="LEFT", splitByRow=1)
    padding = 4 if compact else 6
    vertical_padding = 3 if compact else 5
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SOFT_FILL),
                ("TEXTCOLOR", (0, 0), (-1, 0), HEADER_COLOR),
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), padding),
                ("RIGHTPADDING", (0, 0), (-1, -1), padding),
                ("TOPPADDING", (0, 0), (-1, -1), vertical_padding),
                ("BOTTOMPADDING", (0, 0), (-1, -1), vertical_padding),
            ]
        )
    )
    return table


def _summary_box(lines: list[str], styles) -> Table:
    paragraphs = [[_paragraph(f"- {line}", styles["body"])] for line in lines]
    table = Table(paragraphs, colWidths=[16.0 * cm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), ALERT_FILL),
                ("BOX", (0, 0), (-1, -1), 0.7, BORDER_COLOR),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _humanize_token(value: str | None) -> str:
    if not value:
        return "Not provided"
    return str(value).replace("_", " ").strip().title()


def _format_audit_timestamp(value: str | None) -> str:
    if not value:
        return "Timestamp unavailable"
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return str(value)
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def _audit_event_card(item: dict, styles) -> Table:
    action_label = _humanize_token(item.get("action"))
    title = f"{_format_audit_timestamp(item.get('timestamp'))} | {action_label}"

    meta_parts = [f"Actor: {_humanize_token(item.get('actor'))}"]
    if item.get("artifact_type"):
        meta_parts.append(f"Artifact: {_humanize_token(item.get('artifact_type'))}")
    if item.get("artifact_id"):
        meta_parts.append(f"ID: {item.get('artifact_id')}")
    metadata = item.get("metadata") or {}
    if metadata:
        metadata_text = ", ".join(f"{key}: {value}" for key, value in metadata.items())
        meta_parts.append(f"Metadata: {metadata_text}")

    rows = [
        [_paragraph(f"<b>{title}</b>", styles["body"])],
        [_paragraph(" | ".join(meta_parts), styles["small"])],
        [_paragraph(item.get("details", "No details recorded."), styles["body"])],
    ]
    table = Table(rows, colWidths=[16.0 * cm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SOFT_FILL),
                ("BOX", (0, 0), (-1, -1), 0.6, BORDER_COLOR),
                ("LINEBELOW", (0, 0), (-1, 0), 0.4, BORDER_COLOR),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _chart_title(text: str, width: float) -> Table:
    table = Table([[text]], colWidths=[width])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("TEXTCOLOR", (0, 0), (-1, -1), HEADER_COLOR),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _vertical_distribution_chart(dataframe: pd.DataFrame, category_col: str, value_col: str, title: str, bar_color=colors.HexColor("#4E79A7")):
    drawing = Drawing(7.9 * cm, 6.0 * cm)
    chart = VerticalBarChart()
    chart.x = 24
    chart.y = 28
    chart.height = 105
    chart.width = 185
    values = [float(value) for value in dataframe[value_col].tolist()] if not dataframe.empty else [0]
    chart.data = [values]
    chart.categoryAxis.categoryNames = [str(label)[:16] for label in dataframe[category_col].tolist()] if not dataframe.empty else [""]
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max(max(values) * 1.25, 10)
    chart.valueAxis.valueStep = max(round(chart.valueAxis.valueMax / 5), 1)
    chart.barLabels.nudge = 7
    chart.barLabelFormat = "%.1f"
    chart.barLabels.fontName = "Helvetica"
    chart.barLabels.fontSize = 7
    chart.bars[0].fillColor = bar_color
    chart.strokeColor = BORDER_COLOR
    chart.categoryAxis.labels.angle = 25
    chart.categoryAxis.labels.boxAnchor = "ne"
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.labels.fontSize = 7
    drawing.add(chart)
    drawing.add(String(0, 146, title, fontName="Helvetica-Bold", fontSize=9, fillColor=HEADER_COLOR))
    return drawing


def _horizontal_alignment_chart(metrics: dict, title: str):
    labels = ["Phase", "Study Type", "Allocation", "Masking", "Purpose", "Endpoint"]
    values = [
        metrics.get("phase_alignment_pct") or 0,
        metrics.get("study_type_alignment_pct") or 0,
        metrics.get("allocation_alignment_pct") or 0,
        metrics.get("masking_alignment_pct") or 0,
        metrics.get("primary_purpose_alignment_pct") or 0,
        metrics.get("endpoint_alignment_pct") or 0,
    ]
    drawing = Drawing(8.0 * cm, 6.2 * cm)
    chart = HorizontalBarChart()
    chart.x = 72
    chart.y = 28
    chart.height = 105
    chart.width = 138
    chart.data = [values]
    chart.categoryAxis.categoryNames = labels
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100
    chart.valueAxis.valueStep = 20
    chart.bars[0].fillColor = colors.HexColor("#2F6B8A")
    chart.barLabels.nudge = 5
    chart.barLabelFormat = "%.1f"
    chart.barLabels.fontName = "Helvetica"
    chart.barLabels.fontSize = 7
    chart.strokeColor = BORDER_COLOR
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.labels.fontSize = 7
    drawing.add(chart)
    drawing.add(String(0, 146, title, fontName="Helvetica-Bold", fontSize=9, fillColor=HEADER_COLOR))
    return drawing


def _two_chart_table(left_chart, right_chart) -> Table:
    table = Table([[left_chart, right_chart]], colWidths=[8.0 * cm, 8.0 * cm], hAlign="LEFT")
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return table


def _precedent_differential_chart(metrics: dict, title: str):
    alignment_rows = metrics.get("alignment_by_domain", []) if metrics else []
    if not alignment_rows:
        return _horizontal_alignment_chart({}, title)

    labels = []
    completed_values = []
    disrupted_values = []
    for row in alignment_rows:
        completed = row.get("Completed Match (%)")
        disrupted = row.get("Disrupted Match (%)")
        if completed is None and disrupted is None:
            continue
        labels.append(str(row.get("Domain", ""))[:18])
        completed_values.append(float(completed or 0))
        disrupted_values.append(float(disrupted or 0))

    if not labels:
        return _horizontal_alignment_chart({}, title)

    drawing = Drawing(16.0 * cm, 7.2 * cm)
    chart = HorizontalBarChart()
    chart.x = 92
    chart.y = 28
    chart.height = 120
    chart.width = 300
    chart.data = [completed_values, disrupted_values]
    chart.categoryAxis.categoryNames = labels
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100
    chart.valueAxis.valueStep = 20
    chart.bars[0].fillColor = colors.HexColor("#1F5B7A")
    chart.bars[1].fillColor = colors.HexColor("#C0563D")
    chart.strokeColor = BORDER_COLOR
    chart.barLabels.nudge = 5
    chart.barLabelFormat = "%.0f"
    chart.barLabels.fontName = "Helvetica"
    chart.barLabels.fontSize = 6
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.labels.fontSize = 7
    drawing.add(chart)
    drawing.add(String(0, 164, title, fontName="Helvetica-Bold", fontSize=9, fillColor=HEADER_COLOR))
    drawing.add(String(0, 151, "Blue: Completed precedent", fontName="Helvetica", fontSize=7, fillColor=SUBTLE_TEXT))
    drawing.add(String(118, 151, "Red: Disrupted precedent", fontName="Helvetica", fontSize=7, fillColor=SUBTLE_TEXT))
    return drawing


def _endpoint_split_chart(endpoint_df: pd.DataFrame, title: str):
    if endpoint_df.empty:
        return _vertical_distribution_chart(pd.DataFrame(columns=["Category", "Share"]), "Category", "Share", title)

    plot_df = endpoint_df.copy()
    for column in ["Completed Share (%)", "Disrupted Share (%)"]:
        plot_df[column] = pd.to_numeric(plot_df[column], errors="coerce").fillna(0)

    drawing = Drawing(16.0 * cm, 7.0 * cm)
    chart = VerticalBarChart()
    chart.x = 32
    chart.y = 28
    chart.height = 118
    chart.width = 300
    chart.data = [
        plot_df["Completed Share (%)"].tolist(),
        plot_df["Disrupted Share (%)"].tolist(),
    ]
    chart.categoryAxis.categoryNames = [str(value)[:14] for value in plot_df["Endpoint Category"].tolist()]
    chart.valueAxis.valueMin = 0
    peak_value = max(plot_df["Completed Share (%)"].max(), plot_df["Disrupted Share (%)"].max(), 10)
    chart.valueAxis.valueMax = max(float(peak_value) * 1.25, 10)
    chart.valueAxis.valueStep = max(round(chart.valueAxis.valueMax / 5), 1)
    chart.bars[0].fillColor = colors.HexColor("#1F5B7A")
    chart.bars[1].fillColor = colors.HexColor("#C0563D")
    chart.strokeColor = BORDER_COLOR
    chart.categoryAxis.labels.angle = 20
    chart.categoryAxis.labels.boxAnchor = "ne"
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.labels.fontSize = 7
    chart.barLabels.nudge = 5
    chart.barLabelFormat = "%.0f"
    chart.barLabels.fontName = "Helvetica"
    chart.barLabels.fontSize = 6
    drawing.add(chart)
    drawing.add(String(0, 160, title, fontName="Helvetica-Bold", fontSize=9, fillColor=HEADER_COLOR))
    drawing.add(String(0, 147, "Blue: Completed precedent", fontName="Helvetica", fontSize=7, fillColor=SUBTLE_TEXT))
    drawing.add(String(118, 147, "Red: Disrupted precedent", fontName="Helvetica", fontSize=7, fillColor=SUBTLE_TEXT))
    return drawing


def generate_protocol_report_pdf(
    file_path: str,
    protocol_meta,
    comparison_notes: str,
    audit_log: list[dict],
    top_trials_df: pd.DataFrame | None = None,
    chat_history: list[dict] | None = None,
    comparison_metrics: dict | None = None,
    recommendations: list[dict] | None = None,
) -> str:
    protocol = protocol_meta if isinstance(protocol_meta, ProtocolMetadata) else protocol_metadata_from_session(protocol_meta)
    styles = _build_styles()

    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=1.8 * cm,
        bottomMargin=1.4 * cm,
    )
    story = []

    logo_path = ASSETS_DIR / "logo.png"
    header_row = []
    if logo_path.exists():
        logo = Image(str(logo_path), width=2.0 * cm, height=2.0 * cm)
        header_row.append(logo)
    else:
        header_row.append(_paragraph("", styles["body"]))

    cover_text = [
        _paragraph("Protocol Intelligence Report", styles["title"]),
        _paragraph(
            "Structured protocol review, comparable cohort benchmarking, recommendations, and audit-ready reporting.",
            styles["subtitle"],
        ),
        _paragraph(f"Generated (UTC): {current_utc_timestamp()}", styles["small"]),
        _paragraph("Prepared for clinical development, trial design, and operational planning review.", styles["small"]),
    ]
    header_row.append(Table([[item] for item in cover_text], colWidths=[11.8 * cm]))
    header_row.append(
        Table(
            [
                [_paragraph("Classification", styles["right_small"])],
                [_paragraph("Internal review draft", styles["right_small"])],
                [_paragraph(f"File: {Path(file_path).name}", styles["right_small"])],
            ],
            colWidths=[3.0 * cm],
        )
    )
    cover = Table([header_row], colWidths=[2.2 * cm, 11.8 * cm, 3.0 * cm], hAlign="LEFT")
    cover.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.extend([cover, Spacer(1, 0.3 * cm)])

    decision_df = pd.DataFrame()
    action_register_df = pd.DataFrame()
    cohort_df = pd.DataFrame()
    benchmark_df = pd.DataFrame()
    metric_df = pd.DataFrame()
    design_diff_df = pd.DataFrame()
    endpoint_precedent_df = pd.DataFrame()
    if comparison_metrics:
        decision_df = build_decision_signal_table(protocol, comparison_metrics, recommendations or [])
        action_register_df = build_action_register(recommendations or [])
        cohort_df = build_cohort_definition_table(comparison_metrics)
        benchmark_df = build_protocol_benchmark_table(protocol, comparison_metrics)
        metric_df = metrics_to_dataframe(comparison_metrics).head(14)
        design_diff_df = build_design_differential_table(comparison_metrics)
        endpoint_precedent_df = build_endpoint_precedent_table(comparison_metrics)
        if not action_register_df.empty:
            action_register_df = action_register_df.rename(columns={"Action Type": "Action"})
        if not design_diff_df.empty:
            design_diff_df = design_diff_df.rename(
                columns={
                    "Completed Match (%)": "Completed %",
                    "Disrupted Match (%)": "Disrupted %",
                    "Net Gap (%)": "Gap %",
                }
            )
            design_diff_df = design_diff_df[
                [column for column in ["Domain", "Protocol Choice", "Completed %", "Disrupted %", "Gap %", "Signal"] if column in design_diff_df.columns]
            ]

    executive_lines = [
        f"Protocol title: {protocol.title or 'Not provided'}",
        f"Clinical focus: {protocol.condition or 'Not provided'}",
        f"Study structure: {protocol.study_type or 'Not provided'} | {protocol.phase or 'Not provided'}",
        f"Profile status: {protocol.confirmation_status.title()} with {protocol.confidence or 'undocumented'} extraction confidence",
    ]
    if comparison_metrics and comparison_metrics.get("cohort_size"):
        executive_lines.append(
            "Comparator evidence: "
            f"{comparison_metrics.get('cohort_size', 0)} matched studies | "
            f"{comparison_metrics.get('completed_cohort_size', 0)} completed | "
            f"{comparison_metrics.get('disrupted_cohort_size', 0)} disrupted."
        )
        executive_lines.append(
            "Decision posture: "
            f"{comparison_metrics.get('precedent_posture', 'Incomplete precedent signal')} "
            f"(completed fit {comparison_metrics.get('completed_design_fit_pct', 'n/a')}%, "
            f"disrupted fit {comparison_metrics.get('disrupted_design_fit_pct', 'n/a')}%)."
        )
    for action in (recommendations or [])[:2]:
        executive_lines.append(f"{action.get('Priority', 'Monitor')} priority: {action.get('Recommendation', '')}")

    story.extend(_section_heading("1. Executive Summary", styles))
    story.append(_summary_box(executive_lines, styles))
    story.append(Spacer(1, 0.35 * cm))

    if comparison_metrics:
        story.extend(_section_heading("2. Senior Decision Signals", styles))
        story.append(_dataframe_table(decision_df, styles, col_widths=[3.1 * cm, 3.0 * cm, 4.8 * cm, 5.1 * cm]))
        story.append(Spacer(1, 0.25 * cm))

        story.extend(_section_heading("3. Executive Action Register", styles))
        if action_register_df.empty:
            story.append(_paragraph("No actions were generated for this analysis run.", styles["body"]))
        else:
            story.append(
                _dataframe_table(
                    action_register_df.head(8),
                    styles,
                    col_widths=[1.7 * cm, 2.4 * cm, 1.8 * cm, 6.5 * cm, 3.6 * cm],
                    style_key="dense",
                    compact=True,
                )
            )
        story.append(Spacer(1, 0.3 * cm))

    profile_rows = [
        ("Title", protocol.title or "Not provided"),
        ("Condition", protocol.condition or "Not provided"),
        ("Sponsor", protocol.sponsor or "Not provided"),
        ("Study Type", protocol.study_type or "Not provided"),
        ("Phase", protocol.phase or "Not provided"),
        ("Planned Enrollment", protocol.sample_size or "Not provided"),
        ("Arms Count", protocol.arms_count or "Not provided"),
        ("Allocation", protocol.allocation or "Not provided"),
        ("Masking", protocol.masking or "Not provided"),
        ("Intervention Model", protocol.intervention_model or "Not provided"),
        ("Primary Purpose", protocol.primary_purpose or "Not provided"),
        ("Comparator", protocol.comparator or "Not provided"),
        ("Target Population", protocol.target_population or "Not provided"),
        ("Geography Focus", protocol.geography_focus or "Not provided"),
        ("Start Date", protocol.start_date or "Not provided"),
        ("Completion Date", protocol.completion_date or "Not provided"),
        ("Endpoint Focus", protocol.endpoint_focus or "Not provided"),
        ("Primary Endpoints", protocol.primary_endpoints or "Not provided"),
        ("Secondary Endpoints", protocol.secondary_endpoints or "Not provided"),
    ]
    story.extend(_section_heading("4. Reviewed Protocol Profile", styles))
    story.append(_kv_table(profile_rows, styles))
    story.append(Spacer(1, 0.35 * cm))

    story.extend(_section_heading("5. Comparative Narrative", styles))
    story.append(_paragraph(comparison_notes or "No comparative findings were generated for this run.", styles["body"]))
    story.append(Spacer(1, 0.2 * cm))

    if comparison_metrics:
        story.extend(_section_heading("6. Comparator Cohort Definition", styles))
        story.append(_dataframe_table(cohort_df, styles, col_widths=[6.0 * cm, 10.0 * cm]))
        story.append(Spacer(1, 0.3 * cm))

        story.extend(_section_heading("7. Success vs Disruption Benchmark", styles))
        story.append(
            _dataframe_table(
                benchmark_df,
                styles,
                col_widths=[2.2 * cm, 2.5 * cm, 4.1 * cm, 4.1 * cm, 3.1 * cm],
                style_key="dense",
                compact=True,
            )
        )
        story.append(Spacer(1, 0.3 * cm))

        story.extend(_section_heading("8. Decision Scorecard", styles))
        story.append(_dataframe_table(metric_df, styles, col_widths=[7.0 * cm, 9.0 * cm]))
        story.append(Spacer(1, 0.3 * cm))

        story.extend(_section_heading("9. Design Differential Matrix", styles))
        story.append(
            _dataframe_table(
                design_diff_df,
                styles,
                col_widths=[2.0 * cm, 3.0 * cm, 2.2 * cm, 2.2 * cm, 1.4 * cm, 5.2 * cm],
                style_key="dense",
                compact=True,
            )
        )
        story.append(Spacer(1, 0.3 * cm))

        story.extend(_section_heading("10. Key Figures", styles))
        story.append(_precedent_differential_chart(comparison_metrics, "Completed vs Disrupted Precedent by Design Domain"))
        story.append(Spacer(1, 0.2 * cm))
        if not endpoint_precedent_df.empty:
            story.append(_endpoint_split_chart(endpoint_precedent_df, "Endpoint Focus in Completed vs Disrupted Comparators"))
        story.append(Spacer(1, 0.3 * cm))

    if recommendations:
        story.extend(_section_heading("11. Recommendation Detail", styles))
        recommendation_df = recommendations_to_dataframe(recommendations).head(10)
        recommendation_df = recommendation_df[
            [column for column in ["Priority", "Category", "Recommendation", "Rationale", "Evidence"] if column in recommendation_df.columns]
        ]
        story.append(
            _dataframe_table(
                recommendation_df,
                styles,
                col_widths=[1.8 * cm, 2.5 * cm, 5.0 * cm, 4.1 * cm, 2.6 * cm],
                style_key="dense",
                compact=True,
            )
        )
        story.append(Spacer(1, 0.3 * cm))

    if top_trials_df is not None and not top_trials_df.empty:
        story.extend(_section_heading("12. Comparator Exemplars", styles))
        preview_df = build_trial_exemplar_table(top_trials_df, limit=10)
        preview_df = preview_df[
            [column for column in ["Comparator Lens", "Status", "NCT ID", "Title", "Enrollment", "Sponsor"] if column in preview_df.columns]
        ]
        column_widths = [2.3 * cm, 1.9 * cm, 1.9 * cm, 5.8 * cm, 1.6 * cm, 2.5 * cm][: len(preview_df.columns)]
        story.append(_dataframe_table(preview_df, styles, col_widths=column_widths, style_key="dense", compact=True))
        story.append(Spacer(1, 0.3 * cm))

    if chat_history:
        story.extend(_section_heading("13. Review Conversation Highlights", styles))
        for message in chat_history[-6:]:
            speaker = "Reviewer" if message.get("role") == "user" else "Assistant"
            story.append(_paragraph(f"<b>{speaker}</b> | {message.get('timestamp', 'n/a')}", styles["body"]))
            story.append(_paragraph(message.get("text", ""), styles["body"]))
            story.append(Spacer(1, 0.12 * cm))

    story.append(PageBreak())
    story.extend(_section_heading("14. Audit Trail and Provenance", styles))
    if not audit_log:
        story.append(_paragraph("No audit events were recorded.", styles["body"]))
    else:
        for event in audit_log:
            story.append(_audit_event_card(event, styles))
            story.append(Spacer(1, 0.12 * cm))

    story.append(Spacer(1, 0.3 * cm))
    story.extend(_section_heading("15. Methodology Notes", styles))
    methodology = (
        "Source trials were retrieved from ClinicalTrials.gov and normalized into a comparator cohort. "
        "This report separates completed comparators from disrupted comparators and uses those lenses to assess how the reviewed draft aligns with stronger or weaker precedent patterns. "
        "Protocol fields were derived from uploaded documents using deterministic heuristics and, when configured, an LLM-assisted structured extraction step. "
        "All outputs are intended to support expert review rather than replace clinical, statistical, operational, or regulatory judgment."
    )
    story.append(_paragraph(methodology, styles["body"]))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return file_path
