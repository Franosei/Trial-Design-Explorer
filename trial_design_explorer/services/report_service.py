"""
Report service: generate a detailed, boardroom-ready PDF report.

Improvements over the previous version:
  - Rich narrative paragraphs for every section (not just bullet lines)
  - Embedded matplotlib charts (radar, enrollment box-plot, duration comparison,
    endpoint distribution, posture gauge) via BytesIO → ReportLab Image
  - PubMed literature evidence section with traceable citations
  - Colour-coded signal indicators in tables
  - Wider content area usage and better spacing
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Optional

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
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
from trial_design_explorer.services.chart_service import (
    generate_alignment_heatmap,
    generate_duration_comparison_chart,
    generate_endpoint_distribution_chart,
    generate_enrollment_benchmark_chart,
    generate_posture_gauge,
    generate_radar_chart,
    generate_sponsor_donut,
)
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


# ── Layout constants ───────────────────────────────────────────────────────────
PAGE_MARGIN   = 1.5 * cm
CONTENT_WIDTH = A4[0] - (2 * PAGE_MARGIN)

# ── Brand colours ──────────────────────────────────────────────────────────────
HEADER_COLOR  = colors.HexColor("#15324A")
TEAL_COLOR    = colors.HexColor("#1F5B7A")
RED_COLOR     = colors.HexColor("#C0563D")
AMBER_COLOR   = colors.HexColor("#F5A623")
SUBTLE_TEXT   = colors.HexColor("#5F6B7A")
BORDER_COLOR  = colors.HexColor("#D5DCE3")
SOFT_FILL     = colors.HexColor("#F2F6F9")
ALERT_FILL    = colors.HexColor("#EDF3F7")
SUCCESS_FILL  = colors.HexColor("#D6EAD9")
RISK_FILL     = colors.HexColor("#FCECEA")
BODY_TEXT     = colors.HexColor("#22313F")


# ── Style sheet ────────────────────────────────────────────────────────────────

def _build_styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("ReportTitle", parent=base["Title"],
                                fontName="Helvetica-Bold", fontSize=24, leading=30,
                                textColor=HEADER_COLOR, spaceAfter=10, alignment=TA_LEFT),
        "subtitle": ParagraphStyle("ReportSubtitle", parent=base["BodyText"],
                                   fontName="Helvetica", fontSize=10, leading=14,
                                   textColor=SUBTLE_TEXT, spaceAfter=6),
        "section": ParagraphStyle("SectionTitle", parent=base["Heading2"],
                                  fontName="Helvetica-Bold", fontSize=13, leading=18,
                                  textColor=HEADER_COLOR, spaceBefore=12, spaceAfter=8),
        "subsection": ParagraphStyle("SubSectionTitle", parent=base["Heading3"],
                                     fontName="Helvetica-Bold", fontSize=10.5, leading=15,
                                     textColor=TEAL_COLOR, spaceBefore=8, spaceAfter=5),
        "body": ParagraphStyle("Body", parent=base["BodyText"],
                               fontName="Helvetica", fontSize=9.5, leading=14,
                               textColor=BODY_TEXT, spaceAfter=6, splitLongWords=False),
        "body_indented": ParagraphStyle("BodyIndented", parent=base["BodyText"],
                                        fontName="Helvetica", fontSize=9.5, leading=14,
                                        textColor=BODY_TEXT, spaceAfter=5,
                                        leftIndent=12, splitLongWords=False),
        "dense": ParagraphStyle("Dense", parent=base["BodyText"],
                                fontName="Helvetica", fontSize=8.0, leading=10,
                                textColor=BODY_TEXT, spaceAfter=4, splitLongWords=False),
        "small": ParagraphStyle("Small", parent=base["BodyText"],
                                fontName="Helvetica", fontSize=8.2, leading=11,
                                textColor=SUBTLE_TEXT),
        "caption": ParagraphStyle("Caption", parent=base["BodyText"],
                                  fontName="Helvetica-Oblique", fontSize=8, leading=10,
                                  textColor=SUBTLE_TEXT, alignment=TA_CENTER, spaceAfter=6),
        "right_small": ParagraphStyle("RightSmall", parent=base["BodyText"],
                                      fontName="Helvetica", fontSize=8.2, leading=11,
                                      textColor=SUBTLE_TEXT, alignment=TA_RIGHT),
        "callout": ParagraphStyle("Callout", parent=base["BodyText"],
                                  fontName="Helvetica-Bold", fontSize=10, leading=14,
                                  textColor=HEADER_COLOR, spaceAfter=6,
                                  leftIndent=8, borderPad=4),
    }


# ── Page decorators ────────────────────────────────────────────────────────────

def _header_footer(canvas, doc):
    canvas.saveState()
    width, height = A4
    # Top rule
    canvas.setStrokeColor(BORDER_COLOR)
    canvas.line(PAGE_MARGIN, height - 1.2 * cm, width - PAGE_MARGIN, height - 1.2 * cm)
    # Top text
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(SUBTLE_TEXT)
    canvas.drawString(PAGE_MARGIN, height - 0.9 * cm,
                      "Trial Design Explorer | Clinical Trial Planning Intelligence Report")
    canvas.drawRightString(width - PAGE_MARGIN, height - 0.9 * cm, current_utc_timestamp())
    # Bottom rule
    canvas.line(PAGE_MARGIN, 0.95 * cm, width - PAGE_MARGIN, 0.95 * cm)
    canvas.drawRightString(width - PAGE_MARGIN, 0.6 * cm, f"Page {doc.page}")
    canvas.drawString(PAGE_MARGIN, 0.6 * cm, "Confidential draft — for planning review only")
    canvas.restoreState()


# ── Primitive builders ─────────────────────────────────────────────────────────

def _p(text: str, style) -> Paragraph:
    return Paragraph((text or "N/A").replace("\n", "<br/>"), style)


def _section(title: str, styles) -> list:
    return [_p(title, styles["section"]),
            HRFlowable(color=TEAL_COLOR, thickness=0.8, spaceBefore=2, spaceAfter=4)]


def _subsection(title: str, styles) -> list:
    return [_p(title, styles["subsection"])]


def _kv_table(rows: list[tuple[str, str]], styles) -> Table:
    data = [[_p("<b>Field</b>", styles["body"]), _p("<b>Value</b>", styles["body"])]]
    for label, value in rows:
        # Truncate any unexpectedly long value so a single cell never exceeds page height
        v = str(value)
        if len(v) > 400:
            v = v[:397] + "…"
        data.append([_p(str(label), styles["body"]), _p(v, styles["body"])])
    tbl = Table(data, colWidths=[5.0 * cm, 11.5 * cm], hAlign="LEFT", splitByRow=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), SOFT_FILL),
        ("TEXTCOLOR", (0, 0), (-1, 0), HEADER_COLOR),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT_FILL]),
    ]))
    return tbl


def _normalize_col_widths(col_widths, max_width=None) -> list:
    if not col_widths:
        return col_widths
    max_w = max_width or CONTENT_WIDTH
    total = sum(col_widths)
    if total <= max_w:
        return col_widths
    scale = max_w / total
    return [w * scale for w in col_widths]


def _df_table(df: pd.DataFrame, styles, col_widths=None,
              style_key: str = "body", compact: bool = False,
              signal_col: Optional[str] = None) -> Table:
    safe_df = df.fillna("").astype(str)
    s = styles[style_key]
    header = [_p(f"<b>{c}</b>", s) for c in safe_df.columns]
    rows = [[_p(v, s) for v in row] for row in safe_df.values.tolist()]
    data = [header] + rows
    tbl = Table(data, colWidths=_normalize_col_widths(col_widths),
                repeatRows=1, hAlign="LEFT", splitByRow=1)
    pad = 3 if compact else 5
    vpad = 3 if compact else 5

    # Base style
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), SOFT_FILL),
        ("TEXTCOLOR", (0, 0), (-1, 0), HEADER_COLOR),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), vpad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), vpad),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT_FILL]),
    ]

    # Colour signal column if present
    if signal_col and signal_col in safe_df.columns:
        sig_idx = list(safe_df.columns).index(signal_col)
        for ri, row in enumerate(safe_df.itertuples(index=False), start=1):
            val = str(getattr(row, signal_col.replace(" ", "_"), ""))
            if "Completed" in val:
                style_cmds.append(("BACKGROUND", (sig_idx, ri), (sig_idx, ri), SUCCESS_FILL))
            elif "Disrupted" in val or "Elevated" in val:
                style_cmds.append(("BACKGROUND", (sig_idx, ri), (sig_idx, ri), RISK_FILL))

    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def _summary_box(lines: list[str], styles) -> Table:
    paras = [[_p(f"• {line}", styles["body"])] for line in lines]
    tbl = Table(paras, colWidths=[CONTENT_WIDTH - 0.4 * cm], hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ALERT_FILL),
        ("BOX", (0, 0), (-1, -1), 0.8, TEAL_COLOR),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return tbl


def _callout_box(text: str, styles, fill=ALERT_FILL, border=TEAL_COLOR) -> Table:
    tbl = Table([[_p(text, styles["callout"])]], colWidths=[CONTENT_WIDTH - 0.4 * cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fill),
        ("BOX", (0, 0), (-1, -1), 1.0, border),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return tbl


def _chart_image(buf: BytesIO, width_cm: float, height_cm: float,
                 caption: str, styles) -> list:
    buf.seek(0)
    img = Image(buf, width=width_cm * cm, height=height_cm * cm)
    return [img, _p(caption, styles["caption"]), Spacer(1, 0.2 * cm)]


def _humanize(value: str | None) -> str:
    if not value:
        return "Not provided"
    return str(value).replace("_", " ").strip().title()


def _fmt_ts(value: str | None) -> str:
    if not value:
        return "Timestamp unavailable"
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return parsed.strftime("%Y-%m-%d %H:%M UTC") if not pd.isna(parsed) else str(value)


def _audit_card(item: dict, styles) -> Table:
    action_label = _humanize(item.get("action"))
    title = f"{_fmt_ts(item.get('timestamp'))} | {action_label}"
    meta_parts = [f"Actor: {_humanize(item.get('actor'))}"]
    if item.get("artifact_type"):
        meta_parts.append(f"Artifact: {_humanize(item.get('artifact_type'))}")
    if item.get("artifact_id"):
        meta_parts.append(f"ID: {item.get('artifact_id')}")
    meta = item.get("metadata") or {}
    if meta:
        meta_parts.append(f"Metadata: {', '.join(f'{k}: {v}' for k, v in meta.items())}")
    rows = [
        [_p(f"<b>{title}</b>", styles["body"])],
        [_p(" | ".join(meta_parts), styles["small"])],
        [_p(item.get("details", "No details recorded."), styles["body"])],
    ]
    tbl = Table(rows, colWidths=[CONTENT_WIDTH - 0.2 * cm], hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), SOFT_FILL),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("LINEBELOW", (0, 0), (-1, 0), 0.4, BORDER_COLOR),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return tbl


# ── Narrative generators ───────────────────────────────────────────────────────

def _executive_narrative(protocol: ProtocolMetadata, metrics: dict,
                          recommendations: list[dict]) -> str:
    """Rich paragraph narrative for the executive summary section."""
    cond = protocol.condition or "the target condition"
    phase = protocol.phase or "an unspecified phase"
    study_type = protocol.study_type or "study"
    cohort = metrics.get("cohort_size", 0)
    completed = metrics.get("completed_cohort_size", 0)
    disrupted = metrics.get("disrupted_cohort_size", 0)
    c_fit = metrics.get("completed_design_fit_pct")
    d_fit = metrics.get("disrupted_design_fit_pct")
    posture = metrics.get("precedent_posture", "Incomplete precedent signal")
    evidence = metrics.get("evidence_strength", "Limited")
    gap = metrics.get("precedent_gap_pct")

    lines = []
    lines.append(
        f"This report provides a structured benchmarking assessment of the reviewed "
        f"{phase} {study_type} protocol targeting {cond}.  The analysis draws on a matched "
        f"cohort of <b>{cohort} precedent studies</b> retrieved from the ClinicalTrials.gov "
        f"registry, of which <b>{completed} reached completion</b> and "
        f"<b>{disrupted} were disrupted</b> (terminated, suspended, or withdrawn).  "
        f"Evidence strength for this cohort is rated <b>{evidence}</b>."
    )

    if c_fit is not None and d_fit is not None:
        direction = ("materially stronger alignment with completed precedent"
                     if gap is not None and gap >= 10
                     else ("notable alignment with disrupted precedent"
                           if gap is not None and gap <= -10
                           else "a mixed precedent posture"))
        lines.append(
            f"Across the seven design domains assessed, the reviewed draft shows "
            f"<b>{direction}</b>.  The completed-precedent fit score is "
            f"<b>{c_fit}%</b> compared to a disrupted-precedent fit of "
            f"<b>{d_fit}%</b>, yielding a net precedent gap of "
            f"<b>{gap if gap is not None else 'N/A'}%</b>.  "
            f"The overall posture classification is: <b>{posture}</b>."
        )

    missing = metrics.get("missing_core_fields", [])
    if missing:
        lines.append(
            f"The following core design fields remain unspecified or incomplete, "
            f"which reduces the reliability of the benchmark: "
            f"<b>{', '.join(missing)}</b>.  These should be resolved before using "
            f"this report for governance or regulatory discussion."
        )

    high_priority = [r for r in (recommendations or []) if r.get("Priority") == "High"]
    if high_priority:
        lines.append(
            f"The analysis has surfaced <b>{len(high_priority)} high-priority action(s)</b> "
            f"requiring attention before design lock: "
            + "; ".join(f"{r.get('Category', '')} — {r.get('Recommendation', '')}"
                        for r in high_priority[:2])
            + ("." if not high_priority[0].get("Recommendation", "").endswith(".") else "")
        )

    lines.append(
        "All outputs are intended to support expert review and should be interpreted alongside "
        "clinical, statistical, operational, and regulatory judgment.  No finding in this "
        "report constitutes a regulatory opinion or approval recommendation."
    )
    return "<br/><br/>".join(lines)


def _posture_narrative(metrics: dict) -> str:
    c_fit = metrics.get("completed_design_fit_pct")
    d_fit = metrics.get("disrupted_design_fit_pct")
    posture = metrics.get("precedent_posture", "Incomplete precedent signal")
    gap = metrics.get("precedent_gap_pct")
    cohort = metrics.get("cohort_size", 0)

    if c_fit is None or d_fit is None:
        return ("Precedent posture cannot be determined because the comparator "
                "cohort does not contain sufficient completed and disrupted studies.")

    if gap is not None and gap >= 15:
        direction_text = (
            f"The draft is demonstrably closer to completed-trial precedent (fit {c_fit}%) "
            f"than to disrupted-trial precedent (fit {d_fit}%), a net advantage of {gap}%.  "
            f"This posture is favourable and the design team should preserve the current "
            f"choices that are driving this alignment."
        )
    elif gap is not None and gap <= -15:
        direction_text = (
            f"The draft is closer to disrupted-trial precedent (fit {d_fit}%) "
            f"than to completed-trial precedent (fit {c_fit}%), a deficit of {abs(gap)}%.  "
            f"This is a meaningful risk signal.  The team should review the domain-level "
            f"breakdown to identify which design choices are driving the pattern."
        )
    else:
        direction_text = (
            f"The draft sits in a mixed precedent zone (completed fit {c_fit}% vs disrupted "
            f"fit {d_fit}%).  There is no strong directional signal, which means execution "
            f"quality, operational planning, and individual domain choices will carry more "
            f"decision weight than the aggregate posture."
        )

    return (
        f"Overall precedent posture: <b>{posture}</b> — based on {cohort} matched studies.  "
        f"{direction_text}"
    )


def _domain_narrative(metrics: dict) -> str:
    rows = metrics.get("alignment_by_domain", [])
    if not rows:
        return "Domain-level alignment data is not available."

    risk_domains = [r for r in rows
                    if r.get("Completed Match (%)") is not None
                    and r.get("Disrupted Match (%)") is not None
                    and float(r.get("Completed Match (%)") or 0) + 10
                    < float(r.get("Disrupted Match (%)") or 0)]
    strong_domains = [r for r in rows
                      if r.get("Completed Match (%)") is not None
                      and r.get("Disrupted Match (%)") is not None
                      and float(r.get("Completed Match (%)") or 0)
                      - float(r.get("Disrupted Match (%)") or 0) >= 20]

    parts = []
    if strong_domains:
        names = ", ".join(r["Domain"] for r in strong_domains)
        parts.append(
            f"<b>Strong alignment with completed precedent</b> was observed in: {names}.  "
            "These domains represent anchors in the design — the team should preserve these "
            "choices and reference the supporting comparator trials in the design rationale."
        )
    if risk_domains:
        for r in risk_domains:
            c = r.get("Completed Match (%)")
            d = r.get("Disrupted Match (%)")
            context = r.get("Why It Matters", "")
            parts.append(
                f"<b>{r['Domain']}</b> shows a risk signal: completed match {c}% vs disrupted "
                f"match {d}%.  {context}  The team should review this domain explicitly before "
                f"design lock."
            )
    if not parts:
        parts.append(
            "No domains showed extreme divergence between completed and disrupted precedent.  "
            "The design alignment is broadly balanced, though individual domain values should "
            "still be reviewed against the specific design rationale."
        )
    return "<br/><br/>".join(parts)


def _enrollment_narrative(protocol: ProtocolMetadata, metrics: dict) -> str:
    target = metrics.get("enrollment_target")
    c_p25 = metrics.get("completed_enrollment_p25")
    c_p75 = metrics.get("completed_enrollment_p75")
    c_med = metrics.get("completed_enrollment_median")
    d_p25 = metrics.get("disrupted_enrollment_p25")
    d_p75 = metrics.get("disrupted_enrollment_p75")
    d_med = metrics.get("disrupted_enrollment_median")

    if target is None or c_med is None:
        return ("Enrollment benchmarking data is insufficient.  The protocol's planned "
                "enrollment may not have been extracted, or the comparator cohort is too thin.")

    def fmt(v):
        return f"{int(v):,}" if v is not None else "n/a"

    position_text = ""
    if c_p25 is not None and c_p75 is not None:
        if target > c_p75:
            position_text = (
                f"the protocol target of {fmt(target)} sits <b>above the upper bound</b> of "
                f"the completed-trial interquartile range ({fmt(c_p25)}–{fmt(c_p75)}).  "
                "Targets in this range require strong justification of site capacity, "
                "eligibility criteria, and recruitment strategy."
            )
        elif target < c_p25:
            position_text = (
                f"the protocol target of {fmt(target)} sits <b>below the lower bound</b> of "
                f"the completed-trial interquartile range ({fmt(c_p25)}–{fmt(c_p75)}).  "
                "A smaller target may be appropriate, but the team should document why "
                "the reduced enrollment is sufficient to support the stated decision."
            )
        else:
            position_text = (
                f"the protocol target of {fmt(target)} falls <b>within the completed-trial "
                f"IQR ({fmt(c_p25)}–{fmt(c_p75)})</b>, which is a neutral signal.  "
                "Execution and site selection will be the primary feasibility levers."
            )

    return (
        f"Enrollment benchmarking shows that {position_text}  "
        f"Completed-trial median enrollment was {fmt(c_med)}.  "
        f"Disrupted trials had a median of {fmt(d_med)} (IQR {fmt(d_p25)}–{fmt(d_p75)}), "
        f"suggesting that enrollment sizing alone is not a reliable differentiator between "
        f"successful and disrupted studies — operational and design factors matter more."
    )


def _pubmed_narrative(articles: list) -> str:
    if not articles:
        return ("No peer-reviewed literature was retrieved for this analysis.  "
                "PubMed evidence enrichment requires a condition to be specified and "
                "an available internet connection at report generation time.")
    n = len(articles)
    return (
        f"<b>{n} peer-reviewed article(s)</b> were retrieved from PubMed/MEDLINE via the "
        "NCBI E-utilities free API to provide literature context for this trial design.  "
        "All citations below are fully traceable — each entry includes the PubMed ID (PMID), "
        "authors, journal, year of publication, and the query used to retrieve it.  "
        "The abstract excerpts are provided to help the reviewer judge relevance quickly.  "
        "Full articles can be accessed at pubmed.ncbi.nlm.nih.gov/[PMID]."
    )


# ── Main PDF generator ─────────────────────────────────────────────────────────

def generate_protocol_report_pdf(
    file_path: str,
    protocol_meta,
    comparison_notes: str,
    audit_log: list[dict],
    top_trials_df: Optional[pd.DataFrame] = None,
    chat_history: Optional[list[dict]] = None,
    comparison_metrics: Optional[dict] = None,
    recommendations: Optional[list[dict]] = None,
    pubmed_articles: Optional[list] = None,
) -> str:
    protocol = (
        protocol_meta if isinstance(protocol_meta, ProtocolMetadata)
        else protocol_metadata_from_session(protocol_meta)
    )
    styles = _build_styles()
    metrics = comparison_metrics or {}
    recs = recommendations or []

    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
        topMargin=1.8 * cm, bottomMargin=1.5 * cm,
    )
    story = []

    # Pre-build comparison tables
    decision_df = pd.DataFrame()
    action_df   = pd.DataFrame()
    cohort_df   = pd.DataFrame()
    benchmark_df = pd.DataFrame()
    metric_df   = pd.DataFrame()
    design_diff_df = pd.DataFrame()
    endpoint_df = pd.DataFrame()

    if metrics:
        decision_df    = build_decision_signal_table(protocol, metrics, recs)
        action_df      = build_action_register(recs)
        cohort_df      = build_cohort_definition_table(metrics)
        benchmark_df   = build_protocol_benchmark_table(protocol, metrics)
        metric_df      = metrics_to_dataframe(metrics).head(16)
        design_diff_df = build_design_differential_table(metrics)
        endpoint_df    = build_endpoint_precedent_table(metrics)

        if not action_df.empty and "Action Type" in action_df.columns:
            action_df = action_df.rename(columns={"Action Type": "Action"})
        if not design_diff_df.empty:
            design_diff_df = design_diff_df.rename(columns={
                "Completed Match (%)": "Completed %",
                "Disrupted Match (%)": "Disrupted %",
                "Net Gap (%)": "Gap %",
            })
            keep = ["Domain", "Protocol Choice", "Completed %", "Disrupted %", "Gap %", "Signal"]
            design_diff_df = design_diff_df[[c for c in keep if c in design_diff_df.columns]]

    # ── Cover ─────────────────────────────────────────────────────────────────
    logo_path = ASSETS_DIR / "logo.png"
    logo_cell = Image(str(logo_path), width=2.0 * cm, height=2.0 * cm) if logo_path.exists() \
        else _p("", styles["body"])

    cover_text = [
        _p("Protocol Intelligence Report", styles["title"]),
        _p("Structured benchmarking, decision-grade analysis, PubMed evidence enrichment, "
           "and audit-ready reporting for clinical trial design review.", styles["subtitle"]),
        _p(f"Generated (UTC): {current_utc_timestamp()}", styles["small"]),
        _p("Prepared for clinical development, trial design, and operational planning review.",
           styles["small"]),
    ]
    header_row = [
        logo_cell,
        Table([[item] for item in cover_text], colWidths=[11.5 * cm]),
        Table([
            [_p("Classification", styles["right_small"])],
            [_p("Internal review draft", styles["right_small"])],
            [_p(f"File: {Path(file_path).name}", styles["right_small"])],
        ], colWidths=[3.0 * cm]),
    ]
    cover = Table([header_row], colWidths=[2.2 * cm, 11.5 * cm, 3.0 * cm], hAlign="LEFT")
    cover.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.extend([cover, Spacer(1, 0.4 * cm)])

    # ── 1. Executive Summary ──────────────────────────────────────────────────
    story.extend(_section("1. Executive Summary", styles))
    story.append(_p(_executive_narrative(protocol, metrics, recs), styles["body"]))
    story.append(Spacer(1, 0.3 * cm))

    if metrics:
        kpi_rows = [
            ("Matched cohort", f"{metrics.get('cohort_size', 0)} studies"),
            ("Completed comparators", str(metrics.get("completed_cohort_size", 0))),
            ("Disrupted comparators", str(metrics.get("disrupted_cohort_size", 0))),
            ("Evidence strength", str(metrics.get("evidence_strength", "Limited"))),
            ("Completed design fit", f"{metrics.get('completed_design_fit_pct', 'n/a')}%"),
            ("Disrupted design fit", f"{metrics.get('disrupted_design_fit_pct', 'n/a')}%"),
            ("Net precedent gap", f"{metrics.get('precedent_gap_pct', 'n/a')}%"),
            ("Overall posture", str(metrics.get("precedent_posture", "Incomplete"))),
        ]
        story.append(_kv_table(kpi_rows, styles))
        story.append(Spacer(1, 0.3 * cm))

    # Posture gauge chart
    if metrics.get("completed_design_fit_pct") is not None:
        gauge_buf = generate_posture_gauge(metrics, width_in=5.0, height_in=3.2)
        story.extend(_chart_image(gauge_buf, 13.0, 4.5,
                                  "Figure 1. Overall Precedent Posture Gauge — "
                                  "net gap between completed and disrupted design fit.",
                                  styles))

    # ── 2. Decision Signals ───────────────────────────────────────────────────
    if metrics:
        story.extend(_section("2. Senior Decision Signals", styles))
        story.append(_p(
            "The following table summarises the five critical decision areas assessed in this "
            "benchmark.  Each signal should be reviewed by the senior design team before "
            "moving to protocol finalisation or governance submission.",
            styles["body"]))
        story.append(Spacer(1, 0.15 * cm))
        story.append(_df_table(decision_df, styles,
                               col_widths=[3.0 * cm, 3.2 * cm, 4.8 * cm, 5.5 * cm],
                               signal_col="Signal"))
        story.append(Spacer(1, 0.3 * cm))

    # ── 3. Action Register ────────────────────────────────────────────────────
    story.extend(_section("3. Executive Action Register", styles))
    story.append(_p(
        "Actions are prioritised as <b>High</b> (requires resolution before sign-off), "
        "<b>Medium</b> (should be addressed before governance), "
        "<b>Monitor</b> (watch as evidence evolves), or "
        "<b>Preserve</b> (design choice is well-supported — maintain it).  "
        f"This run generated <b>{len(recs)} action(s)</b>.",
        styles["body"]))
    story.append(Spacer(1, 0.15 * cm))
    if action_df.empty:
        story.append(_p("No actions were generated for this analysis run.", styles["body"]))
    else:
        story.append(_df_table(
            action_df.head(10), styles,
            col_widths=[1.6 * cm, 2.4 * cm, 1.8 * cm, 6.2 * cm, 4.5 * cm],
            style_key="dense", compact=True, signal_col="Priority"))
    story.append(Spacer(1, 0.3 * cm))

    # ── 4. Protocol Profile ───────────────────────────────────────────────────
    story.extend(_section("4. Reviewed Protocol Profile", styles))
    story.append(_p(
        "The following fields were extracted from the uploaded protocol document and "
        f"reviewed by the study team.  Extraction confidence: "
        f"<b>{protocol.confidence or 'undocumented'}</b>.  "
        f"Profile status: <b>{protocol.confirmation_status.title()}</b>.",
        styles["body"]))
    story.append(Spacer(1, 0.15 * cm))

    # Compact structured fields go in a table (short single-line values only)
    compact_rows = [
        ("Condition",            protocol.condition or "Not provided"),
        ("Sponsor",              protocol.sponsor or "Not provided"),
        ("Study Type",           protocol.study_type or "Not provided"),
        ("Phase",                protocol.phase or "Not provided"),
        ("Planned Enrollment",   protocol.sample_size or "Not provided"),
        ("Arms Count",           protocol.arms_count or "Not provided"),
        ("Allocation",           protocol.allocation or "Not provided"),
        ("Masking",              protocol.masking or "Not provided"),
        ("Intervention Model",   protocol.intervention_model or "Not provided"),
        ("Primary Purpose",      protocol.primary_purpose or "Not provided"),
        ("Geography Focus",      protocol.geography_focus or "Not provided"),
        ("Start Date",           protocol.start_date or "Not provided"),
        ("Completion Date",      protocol.completion_date or "Not provided"),
        ("Endpoint Focus",       protocol.endpoint_focus or "Not provided"),
    ]

    # Protocol title rendered as a heading (can be long)
    if protocol.title:
        story.append(_p(f"<b>Protocol Title:</b>  {protocol.title}", styles["body"]))
        story.append(Spacer(1, 0.1 * cm))

    story.append(_kv_table(compact_rows, styles))
    story.append(Spacer(1, 0.3 * cm))

    # Long free-text fields rendered as flowing paragraphs — cannot go in table cells
    # because ReportLab cannot paginate within a single table row.
    def _long_field_block(label: str, text: str | None) -> None:
        if not text or str(text).strip().lower() in ("not provided", "none", "null", ""):
            return
        story.append(_p(f"<b>{label}</b>", styles["body"]))
        story.append(Spacer(1, 0.05 * cm))
        story.append(_p(str(text).strip(), styles["body"]))
        story.append(Spacer(1, 0.2 * cm))

    _long_field_block("Primary Endpoints", protocol.primary_endpoints)
    _long_field_block("Secondary Endpoints", protocol.secondary_endpoints)
    _long_field_block("Target Population & Eligibility Criteria", protocol.target_population)
    _long_field_block("Intervention Description", protocol.intervention_description)
    _long_field_block("Comparator / Control Arm", protocol.comparator)

    # ── 5. Precedent Posture ──────────────────────────────────────────────────
    if metrics:
        story.extend(_section("5. Precedent Posture Analysis", styles))
        story.append(_p(_posture_narrative(metrics), styles["body"]))
        story.append(Spacer(1, 0.2 * cm))

    # ── 6. Design Domain Alignment ────────────────────────────────────────────
    if metrics:
        story.extend(_section("6. Design Domain Alignment", styles))
        story.append(_p(_domain_narrative(metrics), styles["body"]))
        story.append(Spacer(1, 0.2 * cm))

        radar_buf = generate_radar_chart(metrics, width_in=7.0, height_in=5.5)
        story.extend(_chart_image(radar_buf, 13.0, 7.5,
                                  "Figure 2. Design Domain Alignment Radar — "
                                  "completed precedent (teal filled) vs disrupted precedent (red dashed).  "
                                  "Larger filled area = stronger alignment with successful trials.",
                                  styles))
        story.append(Spacer(1, 0.15 * cm))

        heatmap_buf = generate_alignment_heatmap(metrics, width_in=9.0, height_in=3.2)
        story.extend(_chart_image(heatmap_buf, 13.0, 4.2,
                                  "Figure 3. Domain Alignment Risk Signal Summary — "
                                  "green = closer to completed precedent; red = closer to disrupted.",
                                  styles))

    # ── 7. Design Differential Matrix ─────────────────────────────────────────
    if metrics and not design_diff_df.empty:
        story.extend(_section("7. Design Differential Matrix", styles))
        story.append(_p(
            "This matrix shows, domain by domain, the match rate the protocol has with "
            "completed and disrupted precedent, the net gap between them, and the signal "
            "classification.  The 'Why It Matters' context helps reviewers prioritise "
            "which gaps need explicit narrative justification.",
            styles["body"]))
        story.append(Spacer(1, 0.15 * cm))
        story.append(_df_table(
            design_diff_df, styles,
            col_widths=[2.0 * cm, 3.0 * cm, 2.1 * cm, 2.1 * cm, 1.5 * cm, 5.8 * cm],
            style_key="dense", compact=True, signal_col="Signal"))
        story.append(Spacer(1, 0.3 * cm))

    # ── 8. Enrollment Benchmark ───────────────────────────────────────────────
    if metrics:
        story.extend(_section("8. Enrollment Benchmark", styles))
        story.append(_p(_enrollment_narrative(protocol, metrics), styles["body"]))
        story.append(Spacer(1, 0.2 * cm))

        enroll_buf = generate_enrollment_benchmark_chart(metrics, width_in=8.0, height_in=4.0)
        story.extend(_chart_image(enroll_buf, 13.0, 5.0,
                                  "Figure 4. Enrollment Benchmark — IQR boxes show 25th–75th percentile "
                                  "range; centre line is the median; amber dashed = protocol target.",
                                  styles))

        story.append(Spacer(1, 0.15 * cm))
        duration_buf = generate_duration_comparison_chart(metrics, width_in=8.0, height_in=3.5)
        story.extend(_chart_image(duration_buf, 13.0, 4.5,
                                  "Figure 5. Planned Duration vs Precedent Cohort Ranges — "
                                  "amber dashed line = protocol planned duration.",
                                  styles))

    # ── 9. Cohort Definition ──────────────────────────────────────────────────
    if metrics and not cohort_df.empty:
        story.extend(_section("9. Comparator Cohort Definition", styles))
        story.append(_p(
            "The following table describes how the comparator cohort was constructed.  "
            "Only studies matching the clinical condition specified in the protocol were "
            "included.  Status classification (completed vs disrupted) follows ClinicalTrials.gov "
            "status fields.",
            styles["body"]))
        story.append(Spacer(1, 0.15 * cm))
        story.append(_df_table(cohort_df, styles, col_widths=[7.0 * cm, 9.5 * cm]))
        story.append(Spacer(1, 0.3 * cm))

    # ── 10. Success vs Disruption Benchmark ───────────────────────────────────
    if metrics and not benchmark_df.empty:
        story.extend(_section("10. Success vs Disruption Benchmark", styles))
        story.append(_p(
            "This table presents, for each design parameter, the protocol's value alongside "
            "the comparable range from completed and disrupted trials.  The signal column "
            "classifies the protocol's position relative to completed-trial precedent.",
            styles["body"]))
        story.append(Spacer(1, 0.15 * cm))
        story.append(_df_table(
            benchmark_df, styles,
            col_widths=[2.2 * cm, 2.5 * cm, 4.3 * cm, 4.3 * cm, 3.2 * cm],
            style_key="dense", compact=True, signal_col="Signal"))
        story.append(Spacer(1, 0.3 * cm))

    # ── 11. Decision Scorecard ────────────────────────────────────────────────
    if metrics and not metric_df.empty:
        story.extend(_section("11. Decision Scorecard", styles))
        story.append(_p(
            "Quantitative scorecard of all computed metrics.  These numbers underpin the "
            "signals and recommendations in this report.  Any metric showing 'Not available' "
            "reflects a data gap in either the protocol or the comparator cohort.",
            styles["body"]))
        story.append(Spacer(1, 0.15 * cm))
        story.append(_df_table(metric_df, styles, col_widths=[8.0 * cm, 8.5 * cm]))
        story.append(Spacer(1, 0.3 * cm))

    # ── 12. Endpoint Evidence ─────────────────────────────────────────────────
    if metrics:
        story.extend(_section("12. Endpoint Category Evidence", styles))
        story.append(_p(
            "Endpoint category distribution reveals what types of evidence completed and "
            "disrupted trials have relied upon in this condition.  The protocol's current "
            "endpoint focus is highlighted.  Aligning with completed-trial endpoint patterns "
            "is associated with stronger design credibility.",
            styles["body"]))
        story.append(Spacer(1, 0.2 * cm))

        ep_buf = generate_endpoint_distribution_chart(metrics, width_in=9.0, height_in=4.5)
        story.extend(_chart_image(ep_buf, 13.0, 5.5,
                                  "Figure 6. Endpoint Category Distribution — completed precedent (teal) "
                                  "vs disrupted precedent (red).  Amber shading = protocol endpoint focus.",
                                  styles))

        if not endpoint_df.empty:
            story.append(_df_table(endpoint_df, styles,
                                   col_widths=[4.0 * cm, 3.5 * cm, 3.5 * cm, 2.5 * cm],
                                   style_key="dense", compact=True))
        story.append(Spacer(1, 0.3 * cm))

    # ── 13. PubMed Literature Evidence ────────────────────────────────────────
    story.extend(_section("13. PubMed Literature Evidence", styles))
    story.append(_p(_pubmed_narrative(pubmed_articles or []), styles["body"]))
    story.append(Spacer(1, 0.2 * cm))

    if pubmed_articles:
        pub_rows = []
        for art in pubmed_articles:
            a = art if isinstance(art, dict) else art.to_dict()
            pub_rows.append({
                "PMID": a.get("pmid", ""),
                "Authors": (a.get("authors", "").split(",")[0] + " et al.")[:35],
                "Year": a.get("year", ""),
                "Journal": a.get("journal", "")[:35],
                "Title": a.get("title", "")[:75],
                "Endpoint Focus": _classify_endpoint_from_abstract(a.get("abstract", "")),
            })
        pub_df = pd.DataFrame(pub_rows)
        story.append(_df_table(pub_df, styles,
                               col_widths=[1.5 * cm, 3.0 * cm, 1.0 * cm, 3.0 * cm, 6.5 * cm, 1.5 * cm],
                               style_key="dense", compact=True))
        story.append(Spacer(1, 0.15 * cm))

        # Abstract excerpts for top articles
        story.extend(_subsection("Abstract Excerpts", styles))
        for art in pubmed_articles[:4]:
            a = art if isinstance(art, dict) else art.to_dict()
            citation = (
                f"<b>{a.get('title', '')} </b> — "
                f"{a.get('authors', '')} | {a.get('journal', '')} ({a.get('year', '')})  "
                f"PMID: {a.get('pmid', '')}  |  Query: {a.get('query_used', '')}"
            )
            story.append(_callout_box(citation, styles))
            if a.get("abstract"):
                story.append(_p(a["abstract"], styles["body_indented"]))
            story.append(Spacer(1, 0.15 * cm))
    story.append(Spacer(1, 0.2 * cm))

    # ── 14. Comparative Narrative ─────────────────────────────────────────────
    story.extend(_section("14. Comparative Narrative", styles))
    story.append(_p(
        comparison_notes or "No comparative narrative was generated for this run.",
        styles["body"]))
    story.append(Spacer(1, 0.2 * cm))

    # ── 15. Recommendation Detail ──────────────────────────────────────────────
    if recs:
        story.extend(_section("15. Recommendation Detail", styles))
        story.append(_p(
            "Full detail on all recommendations generated by this analysis run.  "
            "Each recommendation includes a rationale derived from the precedent data "
            "and a specific evidence statement referencing the underlying statistics.",
            styles["body"]))
        story.append(Spacer(1, 0.15 * cm))
        rec_df = recommendations_to_dataframe(recs).head(12)
        rec_df = rec_df[[c for c in ["Priority", "Category", "Recommendation",
                                      "Rationale", "Evidence"] if c in rec_df.columns]]
        story.append(_df_table(rec_df, styles,
                               col_widths=[1.8 * cm, 2.5 * cm, 5.0 * cm, 4.0 * cm, 3.2 * cm],
                               style_key="dense", compact=True, signal_col="Priority"))
        story.append(Spacer(1, 0.3 * cm))

    # ── 16. Comparator Exemplars ──────────────────────────────────────────────
    if top_trials_df is not None and not top_trials_df.empty:
        story.extend(_section("16. Comparator Exemplars", styles))
        story.append(_p(
            "The table below lists representative studies from the matched cohort, "
            "separated by comparator lens (completed precedent, disrupted precedent, "
            "active context).  These studies can be reviewed directly on ClinicalTrials.gov "
            "using the NCT ID provided.",
            styles["body"]))
        story.append(Spacer(1, 0.15 * cm))
        preview_df = build_trial_exemplar_table(top_trials_df, limit=12)
        cols = [c for c in ["Comparator Lens", "Status", "NCT ID", "Title", "Enrollment", "Sponsor"]
                if c in preview_df.columns]
        col_ws = [2.2 * cm, 2.0 * cm, 2.0 * cm, 5.8 * cm, 1.5 * cm, 3.0 * cm][:len(cols)]
        story.append(_df_table(preview_df[cols], styles, col_widths=col_ws,
                               style_key="dense", compact=True))
        story.append(Spacer(1, 0.3 * cm))

    # ── 17. Review Conversation ───────────────────────────────────────────────
    if chat_history:
        story.extend(_section("17. Review Conversation Highlights", styles))
        story.append(_p(
            "The following is a record of the interactive review session conducted "
            "during this analysis run.  All questions and responses are included "
            "in the audit trail.",
            styles["body"]))
        story.append(Spacer(1, 0.15 * cm))
        for message in chat_history[-6:]:
            speaker = "Reviewer" if message.get("role") == "user" else "Assistant"
            story.append(_p(f"<b>{speaker}</b> | {message.get('timestamp', 'n/a')}",
                            styles["body"]))
            story.append(_p(message.get("text", ""), styles["body_indented"]))
            story.append(Spacer(1, 0.1 * cm))

    # ── 18. Audit Trail ───────────────────────────────────────────────────────
    story.append(PageBreak())
    story.extend(_section("18. Audit Trail and Provenance", styles))
    story.append(_p(
        "Every action taken in this session is recorded below with a UTC timestamp, "
        "actor, artifact type, and full detail string.  This trail supports governance "
        "review, regulatory readiness, and reproducibility audits.",
        styles["body"]))
    story.append(Spacer(1, 0.2 * cm))
    if not audit_log:
        story.append(_p("No audit events were recorded.", styles["body"]))
    else:
        for event in audit_log:
            story.append(_audit_card(event, styles))
            story.append(Spacer(1, 0.1 * cm))

    # ── 19. Methodology Notes ─────────────────────────────────────────────────
    story.append(Spacer(1, 0.3 * cm))
    story.extend(_section("19. Methodology Notes", styles))
    methodology = (
        "Source trials were retrieved from the ClinicalTrials.gov public registry (API v2) "
        "and normalised into a comparator cohort filtered to the protocol's clinical condition.  "
        "Trials were classified as <b>completed</b> (status: COMPLETED) or "
        "<b>disrupted</b> (status: TERMINATED, SUSPENDED, or WITHDRAWN) and used as two "
        "distinct analytical lenses.  Design alignment was assessed across seven domains: "
        "Phase, Study Type, Allocation, Masking, Intervention Model, Primary Purpose, and "
        "Endpoint Focus.  Alignment scores represent the proportion of comparator trials "
        "sharing the protocol's design choice in each domain.<br/><br/>"
        "Protocol fields were extracted using deterministic heuristic parsing and, where "
        "configured, an LLM-assisted structured extraction step.  PubMed evidence was "
        "retrieved via the NCBI E-utilities API (free access, no key required) using a "
        "condition-and-design-context query.  All LLM calls are logged with model name and "
        "confidence metadata.<br/><br/>"
        "All outputs in this report are intended to support expert review and informed "
        "decision-making.  They do not constitute a regulatory opinion, clinical recommendation, "
        "or approval decision.  The report should be reviewed alongside clinical, statistical, "
        "operational, and regulatory expertise appropriate to the development programme."
    )
    story.append(_p(methodology, styles["body"]))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return file_path


def _classify_endpoint_from_abstract(abstract: str) -> str:
    text = (abstract or "").lower()
    if any(w in text for w in ["mortality", "survival", "response", "remission", "efficacy"]):
        return "Efficacy"
    if any(w in text for w in ["adverse", "safety", "tolerability", "toxicity"]):
        return "Safety"
    if any(w in text for w in ["quality of life", "pain", "fatigue", "patient reported"]):
        return "Patient Reported"
    if any(w in text for w in ["biomarker", "cytokine", "protein", "gene"]):
        return "Biomarker"
    return "General"
