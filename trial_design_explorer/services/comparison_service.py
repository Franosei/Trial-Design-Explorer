import re
import textwrap
from datetime import datetime, timezone

import pandas as pd

from trial_design_explorer.config import DEFAULT_CONDITION
from trial_design_explorer.domain import (
    CohortSummary,
    ComparisonResult,
    DesignRecommendation,
    DomainAlignmentResult,
    DurationBenchmark,
    EnrollmentBenchmark,
    EvidenceBundle,
    ProtocolMetadata,
    RegistryTrialRef,
)


COMPLETED_STATUSES = {"COMPLETED"}
RISK_STATUSES = {"TERMINATED", "SUSPENDED", "WITHDRAWN"}
ACTIVE_STATUSES = {
    "RECRUITING",
    "NOT_YET_RECRUITING",
    "ENROLLING_BY_INVITATION",
    "ACTIVE_NOT_RECRUITING",
}

ALIGNMENT_DOMAINS = [
    {"label": "Phase", "metric_key": "phase_alignment_pct", "column": "Phase", "attr": "phase"},
    {"label": "Study Type", "metric_key": "study_type_alignment_pct", "column": "Study Type", "attr": "study_type"},
    {"label": "Allocation", "metric_key": "allocation_alignment_pct", "column": "Allocation", "attr": "allocation"},
    {"label": "Masking", "metric_key": "masking_alignment_pct", "column": "Masking", "attr": "masking"},
    {
        "label": "Intervention Model",
        "metric_key": "intervention_model_alignment_pct",
        "column": "Intervention Model",
        "attr": "intervention_model",
    },
    {
        "label": "Primary Purpose",
        "metric_key": "primary_purpose_alignment_pct",
        "column": "Primary Purpose",
        "attr": "primary_purpose",
    },
    {
        "label": "Endpoint Focus",
        "metric_key": "endpoint_alignment_pct",
        "column": "Primary Outcome",
        "attr": "endpoint_focus",
        "mode": "endpoint",
    },
]

DOMAIN_CONTEXT = {
    "Phase": {
        "why_it_matters": "Phase determines the development maturity and the expected depth of evidence.",
        "negative_action": "Clarify the phase strategy and align the supporting evidence package with that development step.",
        "positive_action": "Keep the phase framing and use precedent studies to support it.",
    },
    "Study Type": {
        "why_it_matters": "Study type changes how decision-makers interpret trial evidence and fit-for-purpose value.",
        "negative_action": "Pressure-test whether the study type is the strongest route for the program decision.",
        "positive_action": "Preserve the study type because it aligns with stronger historical precedent.",
    },
    "Allocation": {
        "why_it_matters": "Allocation strategy affects comparability, bias control, and governance confidence.",
        "negative_action": "Revisit the allocation strategy or document why the current choice remains defensible.",
        "positive_action": "Keep the allocation strategy and anchor the rationale in comparator evidence.",
    },
    "Masking": {
        "why_it_matters": "Masking shapes bias control, endpoint credibility, and operational burden.",
        "negative_action": "Reassess the masking plan and explicitly document any trade-off between feasibility and evidence credibility.",
        "positive_action": "Maintain the masking strategy and reference similar completed trials in the design rationale.",
    },
    "Intervention Model": {
        "why_it_matters": "Intervention structure affects execution complexity and comparability to prior studies.",
        "negative_action": "Challenge the intervention model and confirm it is not introducing avoidable execution risk.",
        "positive_action": "Retain the intervention model because it aligns with more successful historical precedent.",
    },
    "Primary Purpose": {
        "why_it_matters": "Primary purpose anchors endpoint expectations and how the study intent is judged.",
        "negative_action": "Tighten the primary purpose framing so the design and endpoint package read as coherent.",
        "positive_action": "Preserve the primary purpose framing because it fits the stronger precedent cohort.",
    },
    "Endpoint Focus": {
        "why_it_matters": "Endpoint focus determines what decision the trial can credibly support.",
        "negative_action": "Rework the endpoint package or strengthen the narrative for why a weaker precedent pattern is appropriate.",
        "positive_action": "Keep the endpoint focus and use comparator trials to support its relevance.",
    },
}

PRIORITY_ORDER = {"High": 0, "Medium": 1, "Monitor": 2, "Preserve": 3}


def classify_sponsor_type(name: str | None) -> str:
    if not isinstance(name, str):
        return "Unknown"

    label = name.lower()
    academic_keywords = ["university", "college", "institute", "hospital", "nhs", "school", "center", "centre", "clinic"]
    return "Academic" if any(keyword in label for keyword in academic_keywords) else "Industry"


def classify_endpoint_category(text: str | None) -> str:
    if not isinstance(text, str) or not text.strip():
        return "Unspecified"

    value = text.lower()
    if any(keyword in value for keyword in ["mortality", "survival", "remission", "progression", "response", "efficacy"]):
        return "Efficacy"
    if any(keyword in value for keyword in ["adverse", "toxicity", "safety", "tolerability", "serious adverse"]):
        return "Safety"
    if any(keyword in value for keyword in ["quality of life", "pain", "fatigue", "symptom", "patient reported", "disability", "function"]):
        return "Patient Reported"
    if any(keyword in value for keyword in ["biomarker", "gene", "rna", "protein", "marker", "cytokine"]):
        return "Biomarker"
    if any(keyword in value for keyword in ["hospital stay", "readmission", "cost", "resource", "utilization", "icu"]):
        return "Utilization"
    if any(keyword in value for keyword in ["recruitment", "retention", "dropout", "feasibility", "adherence"]):
        return "Operational"
    return "Other"


def _parse_int(value) -> int | None:
    if value in (None, "", "N/A"):
        return None
    if isinstance(value, (int, float)) and not pd.isna(value):
        return int(value)
    text = str(value).replace(",", "").strip().lower()
    range_match = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)", text)
    if range_match:
        low = int(range_match.group(1))
        high = int(range_match.group(2))
        return int(round((low + high) / 2))
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else None


def _series_alignment_share(series: pd.Series, protocol_value: str | None) -> float | None:
    if not protocol_value or series.empty:
        return None

    target = protocol_value.strip().lower()
    normalized = series.fillna("").astype(str).str.lower()
    matches = normalized.str.contains(target, regex=False)
    if matches.empty:
        return None
    return round(matches.mean() * 100, 1)


def _percentile_rank(series: pd.Series, protocol_value: int | None) -> float | None:
    if protocol_value is None or series.empty:
        return None
    less_equal = (series <= protocol_value).mean() * 100
    return round(float(less_equal), 1)


def _normalize_status(value: str | None) -> str:
    if not value:
        return "UNKNOWN"
    return str(value).strip().upper().replace(" ", "_")


def _display_status(status: str) -> str:
    return status.replace("_", " ").title()


def _alignment_series(frame: pd.DataFrame, domain: dict) -> pd.Series:
    if frame is None or frame.empty:
        return pd.Series(dtype=str)
    if domain.get("mode") == "endpoint":
        return frame["Primary Outcome"].fillna("").astype(str).apply(classify_endpoint_category)
    return frame[domain["column"]].fillna("").astype(str)


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame is None or frame.empty or column not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").dropna()


def _duration_series(frame: pd.DataFrame) -> pd.Series:
    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    start_dates = pd.to_datetime(frame["Start Date"], errors="coerce")
    end_dates = pd.to_datetime(frame["Completion Date"], errors="coerce")
    return ((end_dates - start_dates).dt.days / 30).dropna()


def _list_length_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame is None or frame.empty or column not in frame.columns:
        return pd.Series(dtype=float)
    return frame[column].apply(lambda value: len(value) if isinstance(value, list) else 0)


def _country_count_series(frame: pd.DataFrame) -> pd.Series:
    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    return frame["Locations"].apply(
        lambda locs: len({loc.get("country") for loc in locs if isinstance(loc, dict) and loc.get("country")}) if isinstance(locs, list) else 0
    )


def _subset_by_status(trials_df: pd.DataFrame, allowed_statuses: set[str]) -> pd.DataFrame:
    if trials_df is None or trials_df.empty:
        return pd.DataFrame(columns=trials_df.columns if trials_df is not None else [])
    normalized = trials_df["Status"].fillna("").astype(str).apply(_normalize_status)
    return trials_df[normalized.isin(allowed_statuses)].copy()


def _summarize_numeric_series(series: pd.Series) -> dict:
    if series.empty:
        return {"median": None, "p25": None, "p75": None}
    return {
        "median": round(float(series.median()), 1),
        "p25": round(float(series.quantile(0.25)), 1),
        "p75": round(float(series.quantile(0.75)), 1),
    }


def _protocol_duration_months(protocol_meta: ProtocolMetadata) -> float | None:
    start = pd.to_datetime(protocol_meta.start_date, errors="coerce")
    end = pd.to_datetime(protocol_meta.completion_date, errors="coerce")
    if pd.isna(start) or pd.isna(end):
        return None
    return round(float((end - start).days / 30), 1)


def _build_domain_alignment_row(
    protocol_meta: ProtocolMetadata,
    domain: dict,
    overall_df: pd.DataFrame,
    completed_df: pd.DataFrame,
    disrupted_df: pd.DataFrame,
) -> dict:
    protocol_value = getattr(protocol_meta, domain["attr"], None)
    if domain["attr"] == "endpoint_focus" and not protocol_value:
        protocol_value = classify_endpoint_category(protocol_meta.primary_endpoints or protocol_meta.secondary_endpoints)

    overall_share = _series_alignment_share(_alignment_series(overall_df, domain), protocol_value)
    completed_share = _series_alignment_share(_alignment_series(completed_df, domain), protocol_value)
    disrupted_share = _series_alignment_share(_alignment_series(disrupted_df, domain), protocol_value)
    gap = round(float(completed_share - disrupted_share), 1) if completed_share is not None and disrupted_share is not None else None

    return {
        "Domain": domain["label"],
        "Protocol Choice": protocol_value or "Not provided",
        "Overall Match (%)": overall_share,
        "Completed Match (%)": completed_share,
        "Disrupted Match (%)": disrupted_share,
        "Net Gap (%)": gap,
        "Signal": _precedent_signal(completed_share, disrupted_share, protocol_value),
        "Why It Matters": DOMAIN_CONTEXT[domain["label"]]["why_it_matters"],
    }


def _average(values: list[float | None]) -> float | None:
    populated = [value for value in values if value is not None]
    if not populated:
        return None
    return round(float(sum(populated) / len(populated)), 1)


def _status_distribution(status_series: pd.Series) -> dict:
    if status_series.empty:
        return {}
    distribution = status_series.value_counts(normalize=True).mul(100).round(1).to_dict()
    return {_display_status(status): float(share) for status, share in distribution.items()}


def _share_of_statuses(status_series: pd.Series, statuses: set[str]) -> float | None:
    if status_series.empty:
        return None
    return round(float(status_series.isin(statuses).mean() * 100), 1)


def _evidence_strength(total_count: int, completed_count: int, disrupted_count: int) -> str:
    if total_count >= 100 and completed_count >= 25 and disrupted_count >= 8:
        return "Strong"
    if total_count >= 40 and completed_count >= 10 and disrupted_count >= 4:
        return "Moderate"
    return "Limited"


def _posture_label(completed_fit: float | None, disrupted_fit: float | None) -> str:
    if completed_fit is None or disrupted_fit is None:
        return "Incomplete precedent signal"
    gap = completed_fit - disrupted_fit
    if gap >= 15:
        return "Closer to completed precedent"
    if gap <= -15:
        return "Closer to disrupted precedent"
    return "Mixed precedent posture"


def build_protocol_comparison_metrics(protocol_meta: ProtocolMetadata, trials_df: pd.DataFrame) -> dict:
    metrics = {
        "condition": protocol_meta.condition or DEFAULT_CONDITION,
        "cohort_size": 0,
        "completed_cohort_size": 0,
        "disrupted_cohort_size": 0,
        "active_cohort_size": 0,
        "evidence_strength": "Limited",
        "phase_alignment_pct": None,
        "study_type_alignment_pct": None,
        "allocation_alignment_pct": None,
        "masking_alignment_pct": None,
        "intervention_model_alignment_pct": None,
        "primary_purpose_alignment_pct": None,
        "endpoint_alignment_pct": None,
        "design_alignment_index": None,
        "completed_design_fit_pct": None,
        "disrupted_design_fit_pct": None,
        "precedent_gap_pct": None,
        "precedent_posture": "Incomplete precedent signal",
        "enrollment_target": _parse_int(protocol_meta.sample_size),
        "protocol_duration_months": _protocol_duration_months(protocol_meta),
        "enrollment_median": None,
        "enrollment_p25": None,
        "enrollment_p75": None,
        "enrollment_percentile": None,
        "completed_enrollment_median": None,
        "completed_enrollment_p25": None,
        "completed_enrollment_p75": None,
        "disrupted_enrollment_median": None,
        "disrupted_enrollment_p25": None,
        "disrupted_enrollment_p75": None,
        "duration_median_months": None,
        "duration_p25_months": None,
        "duration_p75_months": None,
        "completed_duration_median_months": None,
        "completed_duration_p25_months": None,
        "completed_duration_p75_months": None,
        "disrupted_duration_median_months": None,
        "disrupted_duration_p25_months": None,
        "disrupted_duration_p75_months": None,
        "site_count_median": None,
        "country_count_median": None,
        "risk_status_share_pct": None,
        "completed_share_pct": None,
        "recruiting_share_pct": None,
        "active_share_pct": None,
        "industry_share_pct": None,
        "academic_share_pct": None,
        "protocol_endpoint_focus": protocol_meta.endpoint_focus or classify_endpoint_category(protocol_meta.primary_endpoints),
        "status_distribution": {},
        "status_distribution_raw": {},
        "sponsor_type_distribution": {},
        "endpoint_category_distribution": {},
        "completed_endpoint_distribution": {},
        "disrupted_endpoint_distribution": {},
        "alignment_by_domain": [],
        "missing_core_fields": [],
    }

    if trials_df is None or trials_df.empty:
        return metrics

    normalized_statuses = trials_df["Status"].fillna("Unknown").astype(str).apply(_normalize_status)
    completed_df = trials_df[normalized_statuses.isin(COMPLETED_STATUSES)].copy()
    disrupted_df = trials_df[normalized_statuses.isin(RISK_STATUSES)].copy()
    active_df = trials_df[normalized_statuses.isin(ACTIVE_STATUSES)].copy()

    metrics["cohort_size"] = int(len(trials_df))
    metrics["completed_cohort_size"] = int(len(completed_df))
    metrics["disrupted_cohort_size"] = int(len(disrupted_df))
    metrics["active_cohort_size"] = int(len(active_df))
    metrics["evidence_strength"] = _evidence_strength(
        metrics["cohort_size"],
        metrics["completed_cohort_size"],
        metrics["disrupted_cohort_size"],
    )

    alignment_rows = [
        _build_domain_alignment_row(protocol_meta, domain, trials_df, completed_df, disrupted_df)
        for domain in ALIGNMENT_DOMAINS
    ]
    metrics["alignment_by_domain"] = alignment_rows
    for domain, row in zip(ALIGNMENT_DOMAINS, alignment_rows):
        metrics[domain["metric_key"]] = row["Overall Match (%)"]

    design_scores = [row["Overall Match (%)"] for row in alignment_rows if row["Overall Match (%)"] is not None]
    completed_scores = [row["Completed Match (%)"] for row in alignment_rows if row["Completed Match (%)"] is not None]
    disrupted_scores = [row["Disrupted Match (%)"] for row in alignment_rows if row["Disrupted Match (%)"] is not None]
    metrics["design_alignment_index"] = _average(design_scores)
    metrics["completed_design_fit_pct"] = _average(completed_scores)
    metrics["disrupted_design_fit_pct"] = _average(disrupted_scores)
    if metrics["completed_design_fit_pct"] is not None and metrics["disrupted_design_fit_pct"] is not None:
        metrics["precedent_gap_pct"] = round(
            float(metrics["completed_design_fit_pct"] - metrics["disrupted_design_fit_pct"]),
            1,
        )
    metrics["precedent_posture"] = _posture_label(
        metrics["completed_design_fit_pct"],
        metrics["disrupted_design_fit_pct"],
    )
    metrics["missing_core_fields"] = [
        row["Domain"] for row in alignment_rows if row["Protocol Choice"] in {"Not provided", "Unspecified"}
    ]

    enrollments = _numeric_series(trials_df, "Enrollment")
    completed_enrollments = _numeric_series(completed_df, "Enrollment")
    disrupted_enrollments = _numeric_series(disrupted_df, "Enrollment")
    for prefix, summary in (
        ("", _summarize_numeric_series(enrollments)),
        ("completed_", _summarize_numeric_series(completed_enrollments)),
        ("disrupted_", _summarize_numeric_series(disrupted_enrollments)),
    ):
        metrics[f"{prefix}enrollment_median"] = summary["median"]
        metrics[f"{prefix}enrollment_p25"] = summary["p25"]
        metrics[f"{prefix}enrollment_p75"] = summary["p75"]
    metrics["enrollment_percentile"] = _percentile_rank(enrollments, metrics["enrollment_target"])

    durations = _duration_series(trials_df)
    completed_durations = _duration_series(completed_df)
    disrupted_durations = _duration_series(disrupted_df)
    for prefix, summary in (
        ("", _summarize_numeric_series(durations)),
        ("completed_", _summarize_numeric_series(completed_durations)),
        ("disrupted_", _summarize_numeric_series(disrupted_durations)),
    ):
        metrics[f"{prefix}duration_median_months"] = summary["median"]
        metrics[f"{prefix}duration_p25_months"] = summary["p25"]
        metrics[f"{prefix}duration_p75_months"] = summary["p75"]

    site_counts = _list_length_series(trials_df, "Locations")
    if not site_counts.empty:
        metrics["site_count_median"] = round(float(site_counts.median()), 1)

    country_counts = _country_count_series(trials_df)
    if not country_counts.empty:
        metrics["country_count_median"] = round(float(country_counts.median()), 1)

    metrics["status_distribution_raw"] = normalized_statuses.value_counts(normalize=True).mul(100).round(1).to_dict()
    metrics["status_distribution"] = _status_distribution(normalized_statuses)
    metrics["risk_status_share_pct"] = _share_of_statuses(normalized_statuses, RISK_STATUSES)
    metrics["completed_share_pct"] = _share_of_statuses(normalized_statuses, COMPLETED_STATUSES)
    metrics["recruiting_share_pct"] = round(float(metrics["status_distribution"].get("Recruiting", 0.0)), 1)
    metrics["active_share_pct"] = _share_of_statuses(normalized_statuses, ACTIVE_STATUSES)

    sponsor_types = trials_df["Sponsor"].apply(classify_sponsor_type)
    sponsor_distribution = sponsor_types.value_counts(normalize=True).mul(100).round(1).to_dict()
    metrics["sponsor_type_distribution"] = sponsor_distribution
    metrics["industry_share_pct"] = round(float(sponsor_distribution.get("Industry", 0.0)), 1)
    metrics["academic_share_pct"] = round(float(sponsor_distribution.get("Academic", 0.0)), 1)

    endpoint_categories = trials_df["Primary Outcome"].fillna("").astype(str).apply(classify_endpoint_category)
    completed_endpoint_categories = completed_df["Primary Outcome"].fillna("").astype(str).apply(classify_endpoint_category)
    disrupted_endpoint_categories = disrupted_df["Primary Outcome"].fillna("").astype(str).apply(classify_endpoint_category)
    endpoint_distribution = endpoint_categories.value_counts(normalize=True).mul(100).round(1).to_dict()
    metrics["endpoint_category_distribution"] = endpoint_distribution
    metrics["completed_endpoint_distribution"] = completed_endpoint_categories.value_counts(normalize=True).mul(100).round(1).to_dict()
    metrics["disrupted_endpoint_distribution"] = disrupted_endpoint_categories.value_counts(normalize=True).mul(100).round(1).to_dict()

    protocol_endpoint_focus = metrics["protocol_endpoint_focus"]
    if protocol_endpoint_focus and protocol_endpoint_focus != "Unspecified":
        metrics["endpoint_alignment_pct"] = round(float(endpoint_distribution.get(protocol_endpoint_focus, 0.0)), 1)

    return metrics


def build_protocol_recommendations(protocol_meta: ProtocolMetadata, metrics: dict) -> list[dict]:
    recommendations: list[dict] = []

    def add(priority: str, category: str, action_type: str, recommendation: str, rationale: str, evidence: str) -> None:
        recommendations.append(
            {
                "Priority": priority,
                "Category": category,
                "Action Type": action_type,
                "Recommendation": recommendation,
                "Rationale": rationale,
                "Evidence": evidence,
            }
        )

    missing_fields = metrics.get("missing_core_fields", [])
    if missing_fields:
        add(
            "High",
            "Protocol completeness",
            "Clarify",
            "Finalize the missing core design fields before using this draft for governance review or external discussion.",
            "Key design fields are still unspecified, which weakens benchmark interpretation and report defensibility.",
            f"Missing or unspecified fields: {', '.join(missing_fields)}.",
        )

    completed_fit = metrics.get("completed_design_fit_pct")
    disrupted_fit = metrics.get("disrupted_design_fit_pct")
    if completed_fit is not None and disrupted_fit is not None:
        if completed_fit + 5 < disrupted_fit:
            add(
                "High",
                "Overall design posture",
                "Challenge",
                "Rework the draft so it aligns more closely with completed-trial precedent before sign-off.",
                "Across the available design fields, the current draft is behaving more like disrupted precedent than completed precedent.",
                f"Completed fit {completed_fit}% versus disrupted fit {disrupted_fit}%.",
            )
        elif completed_fit - disrupted_fit >= 15:
            add(
                "Preserve",
                "Overall design posture",
                "Preserve",
                "Maintain the current design posture and use the completed comparator cohort as the primary justification set.",
                "The reviewed draft aligns materially better with completed precedent than with disrupted precedent.",
                f"Completed fit {completed_fit}% versus disrupted fit {disrupted_fit}%.",
            )

    enrollment_target = metrics.get("enrollment_target")
    completed_p25 = metrics.get("completed_enrollment_p25")
    completed_p75 = metrics.get("completed_enrollment_p75")
    disrupted_p25 = metrics.get("disrupted_enrollment_p25")
    disrupted_p75 = metrics.get("disrupted_enrollment_p75")
    if enrollment_target is not None and completed_p25 is not None and completed_p75 is not None:
        if enrollment_target > completed_p75:
            add(
                "High",
                "Enrollment feasibility",
                "Challenge",
                "Pressure-test the enrollment plan, site footprint, and eligibility burden before locking the target.",
                "The planned enrollment sits above the upper end of the completed-trial benchmark range, which can create avoidable feasibility risk.",
                (
                    f"Protocol target {enrollment_target}; completed-trial IQR {completed_p25} to {completed_p75}; "
                    f"disrupted-trial IQR {_format_range(disrupted_p25, disrupted_p75) or 'not available'}."
                ),
            )
        elif enrollment_target < completed_p25:
            add(
                "Medium",
                "Enrollment credibility",
                "Clarify",
                "Confirm that the smaller enrollment target still supports the endpoint claims and decision ambition.",
                "A target below the completed-trial range can be appropriate, but it usually needs a stronger explanation of what decision the study is meant to support.",
                f"Protocol target {enrollment_target}; completed-trial IQR {completed_p25} to {completed_p75}.",
            )
        elif disrupted_p25 is not None and disrupted_p75 is not None and disrupted_p25 <= enrollment_target <= disrupted_p75:
            add(
                "Monitor",
                "Enrollment posture",
                "Monitor",
                "Keep the enrollment target under active review as comparator evidence evolves.",
                "The target sits inside both completed and disrupted benchmark ranges, so execution quality and site strategy will matter more than the number alone.",
                (
                    f"Protocol target {enrollment_target}; completed-trial IQR {completed_p25} to {completed_p75}; "
                    f"disrupted-trial IQR {disrupted_p25} to {disrupted_p75}."
                ),
            )

    for row in sorted(
        metrics.get("alignment_by_domain", []),
        key=lambda item: item.get("Net Gap (%)") if item.get("Net Gap (%)") is not None else 999,
    ):
        completed_share = row.get("Completed Match (%)")
        disrupted_share = row.get("Disrupted Match (%)")
        domain = row["Domain"]
        context = DOMAIN_CONTEXT[domain]
        if row["Protocol Choice"] in {"Not provided", "Unspecified"}:
            continue
        if completed_share is not None and disrupted_share is not None and completed_share + 10 < disrupted_share:
            add(
                "High" if domain in {"Allocation", "Masking", "Primary Purpose"} else "Medium",
                domain,
                "Challenge",
                context["negative_action"],
                context["why_it_matters"],
                f"Completed match {completed_share}% versus disrupted match {disrupted_share}%.",
            )
        elif completed_share is not None and disrupted_share is not None and completed_share - disrupted_share >= 20:
            add(
                "Preserve",
                domain,
                "Preserve",
                context["positive_action"],
                context["why_it_matters"],
                f"Completed match {completed_share}% versus disrupted match {disrupted_share}%.",
            )

    if metrics.get("evidence_strength") == "Limited":
        add(
            "Monitor",
            "Evidence strength",
            "Monitor",
            "Treat the benchmark output as directional until the comparator evidence base is broadened.",
            "The matched cohort is still thin for a strong success-versus-disruption readout.",
            (
                f"Total matched studies {metrics.get('cohort_size', 0)}; completed {metrics.get('completed_cohort_size', 0)}; "
                f"disrupted {metrics.get('disrupted_cohort_size', 0)}."
            ),
        )

    if not recommendations:
        add(
            "Monitor",
            "Overall review",
            "Monitor",
            "No strong design outlier was detected in the current benchmark snapshot.",
            "The reviewed draft does not currently show a clear signal that it is behaving materially worse than historical precedent.",
            "Continue with clinical, statistical, operational, and regulatory review before final sign-off.",
        )

    deduped: list[dict] = []
    seen = set()
    for item in recommendations:
        key = (item["Category"], item["Recommendation"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return sorted(deduped, key=lambda item: (PRIORITY_ORDER.get(item["Priority"], 99), item["Category"]))


def metrics_to_dataframe(metrics: dict) -> pd.DataFrame:
    rows = [
        ("Matched cohort size", metrics.get("cohort_size")),
        ("Completed comparator count", metrics.get("completed_cohort_size")),
        ("Disrupted comparator count", metrics.get("disrupted_cohort_size")),
        ("Evidence strength", metrics.get("evidence_strength")),
        ("Completed precedent fit (%)", metrics.get("completed_design_fit_pct")),
        ("Disrupted precedent fit (%)", metrics.get("disrupted_design_fit_pct")),
        ("Net precedent gap (%)", metrics.get("precedent_gap_pct")),
        ("Overall posture", metrics.get("precedent_posture")),
        ("Enrollment target", metrics.get("enrollment_target")),
        ("Completed enrollment IQR", _format_range(metrics.get("completed_enrollment_p25"), metrics.get("completed_enrollment_p75"))),
        ("Disrupted enrollment IQR", _format_range(metrics.get("disrupted_enrollment_p25"), metrics.get("disrupted_enrollment_p75"))),
        ("Protocol planned duration (months)", metrics.get("protocol_duration_months")),
        ("Completed median duration (months)", metrics.get("completed_duration_median_months")),
        ("Disrupted median duration (months)", metrics.get("disrupted_duration_median_months")),
        ("Median site count", metrics.get("site_count_median")),
        ("Median country count", metrics.get("country_count_median")),
        ("Risk-status share (%)", metrics.get("risk_status_share_pct")),
        ("Completed share (%)", metrics.get("completed_share_pct")),
        ("Active share (%)", metrics.get("active_share_pct")),
        ("Industry sponsor share (%)", metrics.get("industry_share_pct")),
        ("Academic sponsor share (%)", metrics.get("academic_share_pct")),
        ("Protocol endpoint focus", metrics.get("protocol_endpoint_focus")),
    ]
    dataframe = pd.DataFrame(rows, columns=["Metric", "Value"])
    dataframe = dataframe[dataframe["Value"].notna()].copy()
    dataframe["Value"] = dataframe["Value"].astype(str)
    return dataframe


def recommendations_to_dataframe(recommendations: list[dict]) -> pd.DataFrame:
    if not recommendations:
        return pd.DataFrame(columns=["Priority", "Category", "Action Type", "Recommendation", "Rationale", "Evidence"])
    dataframe = pd.DataFrame(recommendations).fillna("")
    ordered_columns = ["Priority", "Category", "Action Type", "Recommendation", "Rationale", "Evidence"]
    available_columns = [column for column in ordered_columns if column in dataframe.columns]
    remaining_columns = [column for column in dataframe.columns if column not in available_columns]
    return dataframe[available_columns + remaining_columns].astype(str)


def build_protocol_benchmark_table(protocol_meta: ProtocolMetadata, metrics: dict) -> pd.DataFrame:
    rows = [
        {
            "Domain": "Enrollment",
            "Protocol Draft": protocol_meta.sample_size or "Not provided",
            "Completed Precedent": _format_benchmark(
                metrics.get("completed_enrollment_median"),
                metrics.get("completed_enrollment_p25"),
                metrics.get("completed_enrollment_p75"),
            ),
            "Disrupted Precedent": _format_benchmark(
                metrics.get("disrupted_enrollment_median"),
                metrics.get("disrupted_enrollment_p25"),
                metrics.get("disrupted_enrollment_p75"),
            ),
            "Signal": _numeric_position_signal(
                metrics.get("enrollment_target"),
                metrics.get("completed_enrollment_p25"),
                metrics.get("completed_enrollment_p75"),
            ),
        },
        {
            "Domain": "Planned Duration",
            "Protocol Draft": _fmt_months(metrics.get("protocol_duration_months")),
            "Completed Precedent": _format_benchmark(
                metrics.get("completed_duration_median_months"),
                metrics.get("completed_duration_p25_months"),
                metrics.get("completed_duration_p75_months"),
                suffix=" mo",
            ),
            "Disrupted Precedent": _format_benchmark(
                metrics.get("disrupted_duration_median_months"),
                metrics.get("disrupted_duration_p25_months"),
                metrics.get("disrupted_duration_p75_months"),
                suffix=" mo",
            ),
            "Signal": _numeric_position_signal(
                metrics.get("protocol_duration_months"),
                metrics.get("completed_duration_p25_months"),
                metrics.get("completed_duration_p75_months"),
                unit="duration",
            ),
        },
    ]
    for row in metrics.get("alignment_by_domain", []):
        rows.append(
            {
                "Domain": row["Domain"],
                "Protocol Draft": row["Protocol Choice"],
                "Completed Precedent": _fmt_pct(row["Completed Match (%)"]),
                "Disrupted Precedent": _fmt_pct(row["Disrupted Match (%)"]),
                "Signal": row["Signal"],
            }
        )
    dataframe = pd.DataFrame(rows).fillna("Not available")
    return dataframe.astype(str)


def build_decision_signal_table(protocol_meta: ProtocolMetadata, metrics: dict, recommendations: list[dict]) -> pd.DataFrame:
    signals = [
        {
            "Decision Area": "Evidence base",
            "Signal": metrics.get("evidence_strength", "Limited"),
            "Implication": "Confidence is highest when completed and disrupted comparators are both adequately represented.",
            "Evidence": (
                f"{metrics.get('cohort_size', 0)} total studies | "
                f"{metrics.get('completed_cohort_size', 0)} completed | "
                f"{metrics.get('disrupted_cohort_size', 0)} disrupted."
            ),
        },
        {
            "Decision Area": "Overall posture",
            "Signal": metrics.get("precedent_posture", "Incomplete precedent signal"),
            "Implication": "This is the clearest top-line read on whether the draft is behaving more like successful or disrupted precedent.",
            "Evidence": (
                f"Completed fit {_fmt_pct(metrics.get('completed_design_fit_pct'))} | "
                f"Disrupted fit {_fmt_pct(metrics.get('disrupted_design_fit_pct'))}."
            ),
        },
        {
            "Decision Area": "Enrollment plan",
            "Signal": _numeric_position_signal(
                metrics.get("enrollment_target"),
                metrics.get("completed_enrollment_p25"),
                metrics.get("completed_enrollment_p75"),
            ),
            "Implication": "Enrollment targets outside the completed range need stronger feasibility justification.",
            "Evidence": (
                f"Target {protocol_meta.sample_size or 'n/a'} | Completed IQR "
                f"{_format_range(metrics.get('completed_enrollment_p25'), metrics.get('completed_enrollment_p75')) or 'n/a'}."
            ),
        },
        {
            "Decision Area": "Execution exposure",
            "Signal": _risk_signal(metrics.get("risk_status_share_pct")),
            "Implication": "Higher disruption prevalence should trigger more explicit mitigation planning.",
            "Evidence": f"Disrupted-status share {_fmt_pct(metrics.get('risk_status_share_pct'))}.",
        },
        {
            "Decision Area": "Protocol completeness",
            "Signal": "Complete" if not metrics.get("missing_core_fields") else "Specification gaps remain",
            "Implication": "Missing design fields make the benchmark less trustworthy and reduce report defensibility.",
            "Evidence": ", ".join(metrics.get("missing_core_fields", [])) or "No missing core fields detected.",
        },
    ]

    if recommendations:
        first_recommendation = recommendations[0]
        signals.append(
            {
                "Decision Area": "Lead action",
                "Signal": first_recommendation.get("Priority", "Monitor"),
                "Implication": first_recommendation.get("Recommendation", ""),
                "Evidence": first_recommendation.get("Evidence", ""),
            }
        )

    return pd.DataFrame(signals).fillna("").astype(str)


def build_distribution_dataframe(distribution: dict, label_name: str, value_name: str = "Share (%)", top_n: int = 6) -> pd.DataFrame:
    if not distribution:
        return pd.DataFrame(columns=[label_name, value_name])
    rows = [{label_name: key, value_name: value} for key, value in distribution.items()]
    dataframe = pd.DataFrame(rows).sort_values(value_name, ascending=False).head(top_n)
    dataframe[value_name] = dataframe[value_name].astype(float)
    return dataframe


def build_design_differential_table(metrics: dict) -> pd.DataFrame:
    if not metrics.get("alignment_by_domain"):
        return pd.DataFrame(
            columns=[
                "Domain",
                "Protocol Choice",
                "Completed Match (%)",
                "Disrupted Match (%)",
                "Net Gap (%)",
                "Signal",
                "Why It Matters",
            ]
        )
    return pd.DataFrame(metrics["alignment_by_domain"]).fillna("Not available").astype(str)


def build_cohort_definition_table(metrics: dict) -> pd.DataFrame:
    rows = [
        {"Metric": "Clinical condition", "Value": metrics.get("condition", DEFAULT_CONDITION)},
        {"Metric": "Matched trial count", "Value": metrics.get("cohort_size", 0)},
        {"Metric": "Completed comparators", "Value": metrics.get("completed_cohort_size", 0)},
        {"Metric": "Disrupted comparators", "Value": metrics.get("disrupted_cohort_size", 0)},
        {"Metric": "Active comparators", "Value": metrics.get("active_cohort_size", 0)},
        {"Metric": "Evidence strength", "Value": metrics.get("evidence_strength", "Limited")},
        {"Metric": "Risk-status share", "Value": _fmt_pct(metrics.get("risk_status_share_pct"))},
        {"Metric": "Median site count", "Value": metrics.get("site_count_median", "Not available")},
        {"Metric": "Median country count", "Value": metrics.get("country_count_median", "Not available")},
    ]
    return pd.DataFrame(rows).astype(str)


def build_endpoint_precedent_table(metrics: dict, top_n: int = 6) -> pd.DataFrame:
    categories = set(metrics.get("completed_endpoint_distribution", {})) | set(metrics.get("disrupted_endpoint_distribution", {}))
    rows = []
    for category in categories:
        rows.append(
            {
                "Endpoint Category": category,
                "Completed Share (%)": metrics.get("completed_endpoint_distribution", {}).get(category, 0.0),
                "Disrupted Share (%)": metrics.get("disrupted_endpoint_distribution", {}).get(category, 0.0),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["Endpoint Category", "Completed Share (%)", "Disrupted Share (%)", "Net Gap (%)"])
    dataframe = pd.DataFrame(rows)
    dataframe["Net Gap (%)"] = (dataframe["Completed Share (%)"] - dataframe["Disrupted Share (%)"]).round(1)
    return dataframe.sort_values(["Completed Share (%)", "Net Gap (%)"], ascending=[False, False]).head(top_n).astype(str)


def build_action_register(recommendations: list[dict]) -> pd.DataFrame:
    if not recommendations:
        return pd.DataFrame(columns=["Priority", "Category", "Action Type", "Recommendation", "Evidence"])
    dataframe = recommendations_to_dataframe(recommendations)
    columns = [column for column in ["Priority", "Category", "Action Type", "Recommendation", "Evidence"] if column in dataframe.columns]
    return dataframe[columns].astype(str)


def build_trial_exemplar_table(trials_df: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    if trials_df is None or trials_df.empty:
        return pd.DataFrame(columns=["Comparator Lens", "Status", "NCT ID", "Title", "Phase", "Enrollment", "Sponsor"])

    normalized = trials_df["Status"].fillna("").astype(str).apply(_normalize_status)
    completed_df = trials_df[normalized.isin(COMPLETED_STATUSES)].copy()
    disrupted_df = trials_df[normalized.isin(RISK_STATUSES)].copy()
    active_df = trials_df[normalized.isin(ACTIVE_STATUSES)].copy()

    selected_frames = []
    if not completed_df.empty:
        frame = completed_df.head(4).copy()
        frame["Comparator Lens"] = "Completed Precedent"
        selected_frames.append(frame)
    if not disrupted_df.empty:
        frame = disrupted_df.head(4).copy()
        frame["Comparator Lens"] = "Disrupted Precedent"
        selected_frames.append(frame)
    if not active_df.empty and len(selected_frames) < 3:
        frame = active_df.head(2).copy()
        frame["Comparator Lens"] = "Active Context"
        selected_frames.append(frame)

    result = pd.concat(selected_frames, ignore_index=True) if selected_frames else trials_df.head(limit).copy()
    if "Comparator Lens" not in result.columns:
        result["Comparator Lens"] = "Matched Cohort"
    result["Status"] = result["Status"].fillna("").astype(str).apply(lambda value: _display_status(_normalize_status(value)))

    columns = [column for column in ["Comparator Lens", "Status", "NCT ID", "Title", "Phase", "Enrollment", "Sponsor"] if column in result.columns]
    return result[columns].head(limit).fillna("").astype(str)


def compare_protocol_to_trials(protocol_meta: ProtocolMetadata, trials_df: pd.DataFrame) -> str:
    metrics = build_protocol_comparison_metrics(protocol_meta, trials_df)
    if metrics["cohort_size"] == 0:
        return "No matched trials were available for comparison."

    lines = [
        (
            f"Matched {metrics['cohort_size']} studies for {metrics['condition']}, including "
            f"{metrics['completed_cohort_size']} completed comparators and {metrics['disrupted_cohort_size']} disrupted comparators."
        ),
        (
            f"Top-line posture: {metrics['precedent_posture']} "
            f"(completed fit {_fmt_pct(metrics.get('completed_design_fit_pct'))}; "
            f"disrupted fit {_fmt_pct(metrics.get('disrupted_design_fit_pct'))})."
        ),
    ]

    if metrics.get("enrollment_target") is not None:
        lines.append(
            "Enrollment position: "
            + _numeric_position_signal(
                metrics.get("enrollment_target"),
                metrics.get("completed_enrollment_p25"),
                metrics.get("completed_enrollment_p75"),
            )
            + ". "
            + (
                f"Protocol target {metrics['enrollment_target']} | completed-trial IQR "
                f"{_format_range(metrics.get('completed_enrollment_p25'), metrics.get('completed_enrollment_p75')) or 'not available'} | "
                f"disrupted-trial IQR {_format_range(metrics.get('disrupted_enrollment_p25'), metrics.get('disrupted_enrollment_p75')) or 'not available'}."
            )
        )

    strongest_negative = None
    for row in metrics.get("alignment_by_domain", []):
        gap = row.get("Net Gap (%)")
        if gap is None:
            continue
        if strongest_negative is None or gap < strongest_negative["Net Gap (%)"]:
            strongest_negative = row
    if strongest_negative is not None:
        lines.append(
            (
                f"Most important design differential: {strongest_negative['Domain']} shows "
                f"{_fmt_pct(strongest_negative.get('Completed Match (%)'))} completed-trial match versus "
                f"{_fmt_pct(strongest_negative.get('Disrupted Match (%)'))} disrupted-trial match."
            )
        )

    recommendations = build_protocol_recommendations(protocol_meta, metrics)
    headline = recommendations[0]
    lines.append("Lead action: " + textwrap.shorten(headline["Recommendation"], width=160, placeholder="..."))
    lines.append(
        "Interpretation note: this output is intended to support senior design review, not replace clinical, statistical, operational, or regulatory judgment."
    )
    return "\n".join(lines)


def _format_range(low, high) -> str | None:
    if low is None or high is None:
        return None
    if low == high:
        return str(low)
    return f"{low} to {high}"


def _format_benchmark(median, low, high, suffix: str = "") -> str:
    if median is None or low is None or high is None:
        return "Not available"
    return f"Median {median}{suffix} | IQR {low} to {high}{suffix}"


def _fmt_pct(value) -> str:
    if value is None:
        return "Not available"
    return f"{value}%"


def _fmt_months(value) -> str:
    if value is None:
        return "Not provided"
    return f"{value} mo"


def _precedent_signal(completed_share, disrupted_share, protocol_value: str | None) -> str:
    if not protocol_value or protocol_value in {"Not provided", "Unspecified"}:
        return "Protocol field not specified"
    if completed_share is None and disrupted_share is None:
        return "Insufficient matched evidence"
    if completed_share is not None and disrupted_share is not None:
        gap = completed_share - disrupted_share
        if gap >= 15:
            return "Closer to completed precedent"
        if gap <= -15:
            return "Closer to disrupted precedent"
        if max(completed_share, disrupted_share) < 20:
            return "Weak precedent signal"
        return "Mixed precedent"
    if completed_share is not None and completed_share >= 20:
        return "Seen in completed precedent"
    if disrupted_share is not None and disrupted_share >= 20:
        return "Seen in disrupted precedent"
    return "Weak precedent signal"


def _risk_signal(value) -> str:
    if value is None:
        return "Insufficient evidence"
    if value >= 15:
        return "Elevated disruption exposure"
    if value >= 7:
        return "Moderate disruption exposure"
    return "Lower observed disruption exposure"


def _numeric_position_signal(value, low, high, unit: str = "enrollment") -> str:
    if value is None or low is None or high is None:
        return "Insufficient evidence"
    if value > high:
        return "Above completed-trial range" if unit == "enrollment" else "Longer than completed-trial range"
    if value < low:
        return "Below completed-trial range" if unit == "enrollment" else "Shorter than completed-trial range"
    return "Within completed-trial range"


# ── Typed comparison result builder ──────────────────────────────────────────


def _trial_refs_for_domain(
    frame: pd.DataFrame,
    domain: dict,
    protocol_value: str | None,
    max_refs: int = 5,
) -> list[RegistryTrialRef]:
    """Extract RegistryTrialRef objects from matching rows for a domain."""
    if frame is None or frame.empty or not protocol_value:
        return []
    series = _alignment_series(frame, domain)
    target = protocol_value.strip().lower()
    matching = frame[series.str.lower().str.contains(target, regex=False, na=False)]
    refs = []
    for _, row in matching.head(max_refs).iterrows():
        nct_id = str(row.get("NCT ID", "")).strip()
        if not nct_id:
            continue
        enrollment_raw = row.get("Enrollment")
        try:
            enrollment = int(enrollment_raw) if enrollment_raw not in (None, "", "nan") else None
        except (ValueError, TypeError):
            enrollment = None
        refs.append(RegistryTrialRef(
            nct_id=nct_id,
            title=str(row.get("Title", ""))[:120],
            status=str(row.get("Status", "")),
            phase=str(row.get("Phase", "")) or None,
            enrollment=enrollment,
            sponsor=str(row.get("Sponsor", ""))[:60] or None,
            start_date=str(row.get("Start Date", "")) or None,
            completion_date=str(row.get("Completion Date", "")) or None,
            primary_outcome=str(row.get("Primary Outcome", ""))[:120] or None,
        ))
    return refs


def _build_domain_evidence(
    domain_label: str,
    completed_match: float | None,
    disrupted_match: float | None,
    signal: str,
    completed_refs: list[RegistryTrialRef],
    disrupted_refs: list[RegistryTrialRef],
    evidence_strength: str,
) -> EvidenceBundle:
    stat_note = (
        f"Completed match {_fmt_pct(completed_match)} | "
        f"Disrupted match {_fmt_pct(disrupted_match)}"
    )
    if completed_match is not None and disrupted_match is not None:
        gap = completed_match - disrupted_match
        if gap >= 15:
            interpretation = (
                f"Protocol choice aligns with completed-trial majority — "
                f"a {gap:.1f}pp advantage over disrupted precedent."
            )
        elif gap <= -15:
            interpretation = (
                f"Protocol choice aligns more with disrupted-trial pattern — "
                f"a {abs(gap):.1f}pp deficit relative to completed precedent.  "
                f"This domain warrants explicit justification."
            )
        else:
            interpretation = (
                f"Mixed signal — the gap between completed and disrupted alignment "
                f"is {gap:+.1f}pp, below the ±15pp threshold for a strong directional call."
            )
    else:
        interpretation = "Insufficient matched evidence to determine direction."

    all_refs = completed_refs[:3] + disrupted_refs[:2]
    return EvidenceBundle(
        statistical_note=stat_note,
        strength=evidence_strength,
        source_count=len(completed_refs) + len(disrupted_refs),
        references=all_refs,
        interpretation=interpretation,
    )


def _build_enrollment_evidence(
    target: int | None,
    completed_p25: float | None,
    completed_p75: float | None,
    completed_median: float | None,
    disrupted_median: float | None,
    signal: str,
    evidence_strength: str,
    completed_df: pd.DataFrame,
) -> EvidenceBundle:
    stat_note = (
        f"Protocol target {target if target else 'not specified'} | "
        f"Completed median {completed_median} (IQR {completed_p25}–{completed_p75}) | "
        f"Disrupted median {disrupted_median}"
    )
    if target and completed_p75 and target > completed_p75:
        interpretation = (
            f"Target exceeds the upper bound of completed-trial range.  "
            f"Feasibility risk is elevated — site capacity and eligibility criteria need pressure-testing."
        )
    elif target and completed_p25 and target < completed_p25:
        interpretation = (
            f"Target is below the completed-trial lower bound.  "
            f"Confirm the smaller enrollment still supports the stated decision ambition."
        )
    else:
        interpretation = (
            f"Target sits within the completed-trial IQR.  "
            f"Execution and site selection are the primary feasibility levers."
        )

    # Pull exemplar refs from completed trials
    refs = []
    if not completed_df.empty:
        for _, row in completed_df.head(5).iterrows():
            nct_id = str(row.get("NCT ID", "")).strip()
            if not nct_id:
                continue
            try:
                enroll = int(row.get("Enrollment"))
            except (ValueError, TypeError):
                enroll = None
            refs.append(RegistryTrialRef(
                nct_id=nct_id,
                title=str(row.get("Title", ""))[:100],
                status=str(row.get("Status", "")),
                enrollment=enroll,
                sponsor=str(row.get("Sponsor", ""))[:50] or None,
            ))

    return EvidenceBundle(
        statistical_note=stat_note,
        strength=evidence_strength,
        source_count=len(refs),
        references=refs,
        interpretation=interpretation,
    )


def _build_duration_evidence(
    protocol_months: float | None,
    completed_median: float | None,
    completed_p25: float | None,
    completed_p75: float | None,
    evidence_strength: str,
) -> EvidenceBundle:
    stat_note = (
        f"Protocol planned {protocol_months} months | "
        f"Completed median {completed_median} months (IQR {completed_p25}–{completed_p75})"
    )
    if protocol_months and completed_p75 and protocol_months > completed_p75:
        interpretation = "Planned duration exceeds the completed-trial upper quartile.  Consider whether the timeline is realistic."
    elif protocol_months and completed_p25 and protocol_months < completed_p25:
        interpretation = "Planned duration is below the completed-trial lower quartile.  Confirm it accounts for regulatory, operational, and data maturity requirements."
    elif protocol_months:
        interpretation = "Planned duration is within the completed-trial precedent range."
    else:
        interpretation = "Protocol duration not available for positioning."
    return EvidenceBundle(
        statistical_note=stat_note,
        strength=evidence_strength,
        source_count=0,
        interpretation=interpretation,
    )


def _build_recommendation_evidence(
    rec_dict: dict,
    evidence_strength: str,
    domain_refs: list[RegistryTrialRef] | None = None,
) -> EvidenceBundle:
    return EvidenceBundle(
        statistical_note=rec_dict.get("Evidence", ""),
        strength=evidence_strength,
        source_count=len(domain_refs or []),
        references=domain_refs or [],
        interpretation=rec_dict.get("Rationale", ""),
    )


def build_comparison_result(
    protocol_meta: ProtocolMetadata,
    trials_df: pd.DataFrame,
) -> ComparisonResult:
    """
    Build a fully-typed ComparisonResult with EvidenceBundle objects
    attached to every domain alignment row and recommendation.

    This is the canonical comparison entry point.  The flat dict API
    (build_protocol_comparison_metrics / build_protocol_recommendations)
    remains available for backward compatibility; ComparisonResult.to_metrics_dict()
    and .to_recommendations_list() bridge between the two.
    """
    from trial_design_explorer.services.audit_service import current_utc_timestamp

    # Use existing flat builders as the computation core
    flat_metrics = build_protocol_comparison_metrics(protocol_meta, trials_df)
    flat_recs = build_protocol_recommendations(protocol_meta, flat_metrics)

    evidence_strength = flat_metrics.get("evidence_strength", "Limited")
    timestamp = current_utc_timestamp()

    # ── Subset frames ─────────────────────────────────────────────────────────
    if trials_df is not None and not trials_df.empty:
        norm_statuses = trials_df["Status"].fillna("").astype(str).apply(_normalize_status)
        completed_df = trials_df[norm_statuses.isin(COMPLETED_STATUSES)].copy()
        disrupted_df = trials_df[norm_statuses.isin(RISK_STATUSES)].copy()
        active_df    = trials_df[norm_statuses.isin(ACTIVE_STATUSES)].copy()
    else:
        completed_df = disrupted_df = active_df = pd.DataFrame()

    # ── CohortSummary ─────────────────────────────────────────────────────────
    cohort = CohortSummary(
        condition=flat_metrics.get("condition", protocol_meta.condition or DEFAULT_CONDITION),
        total_count=flat_metrics.get("cohort_size", 0),
        completed_count=flat_metrics.get("completed_cohort_size", 0),
        disrupted_count=flat_metrics.get("disrupted_cohort_size", 0),
        active_count=flat_metrics.get("active_cohort_size", 0),
        evidence_strength=evidence_strength,
        risk_share_pct=flat_metrics.get("risk_status_share_pct"),
        completed_share_pct=flat_metrics.get("completed_share_pct"),
        site_count_median=flat_metrics.get("site_count_median"),
        country_count_median=flat_metrics.get("country_count_median"),
        status_distribution=flat_metrics.get("status_distribution", {}),
        sponsor_type_distribution=flat_metrics.get("sponsor_type_distribution", {}),
        endpoint_category_distribution=flat_metrics.get("endpoint_category_distribution", {}),
        completed_endpoint_distribution=flat_metrics.get("completed_endpoint_distribution", {}),
        disrupted_endpoint_distribution=flat_metrics.get("disrupted_endpoint_distribution", {}),
    )

    # ── EnrollmentBenchmark ───────────────────────────────────────────────────
    enroll_signal = _numeric_position_signal(
        flat_metrics.get("enrollment_target"),
        flat_metrics.get("completed_enrollment_p25"),
        flat_metrics.get("completed_enrollment_p75"),
    )
    enrollment = EnrollmentBenchmark(
        target=flat_metrics.get("enrollment_target"),
        overall_median=flat_metrics.get("enrollment_median"),
        overall_p25=flat_metrics.get("enrollment_p25"),
        overall_p75=flat_metrics.get("enrollment_p75"),
        completed_median=flat_metrics.get("completed_enrollment_median"),
        completed_p25=flat_metrics.get("completed_enrollment_p25"),
        completed_p75=flat_metrics.get("completed_enrollment_p75"),
        disrupted_median=flat_metrics.get("disrupted_enrollment_median"),
        disrupted_p25=flat_metrics.get("disrupted_enrollment_p25"),
        disrupted_p75=flat_metrics.get("disrupted_enrollment_p75"),
        percentile_rank=flat_metrics.get("enrollment_percentile"),
        signal=enroll_signal,
        evidence=_build_enrollment_evidence(
            flat_metrics.get("enrollment_target"),
            flat_metrics.get("completed_enrollment_p25"),
            flat_metrics.get("completed_enrollment_p75"),
            flat_metrics.get("completed_enrollment_median"),
            flat_metrics.get("disrupted_enrollment_median"),
            enroll_signal,
            evidence_strength,
            completed_df,
        ),
    )

    # ── DurationBenchmark ─────────────────────────────────────────────────────
    dur_signal = _numeric_position_signal(
        flat_metrics.get("protocol_duration_months"),
        flat_metrics.get("completed_duration_p25_months"),
        flat_metrics.get("completed_duration_p75_months"),
        unit="duration",
    )
    duration = DurationBenchmark(
        protocol_months=flat_metrics.get("protocol_duration_months"),
        overall_median_months=flat_metrics.get("duration_median_months"),
        overall_p25_months=flat_metrics.get("duration_p25_months"),
        overall_p75_months=flat_metrics.get("duration_p75_months"),
        completed_median_months=flat_metrics.get("completed_duration_median_months"),
        completed_p25_months=flat_metrics.get("completed_duration_p25_months"),
        completed_p75_months=flat_metrics.get("completed_duration_p75_months"),
        disrupted_median_months=flat_metrics.get("disrupted_duration_median_months"),
        disrupted_p25_months=flat_metrics.get("disrupted_duration_p25_months"),
        disrupted_p75_months=flat_metrics.get("disrupted_duration_p75_months"),
        signal=dur_signal,
        evidence=_build_duration_evidence(
            flat_metrics.get("protocol_duration_months"),
            flat_metrics.get("completed_duration_median_months"),
            flat_metrics.get("completed_duration_p25_months"),
            flat_metrics.get("completed_duration_p75_months"),
            evidence_strength,
        ),
    )

    # ── DomainAlignmentResult list ────────────────────────────────────────────
    domain_results: list[DomainAlignmentResult] = []
    domain_refs_by_label: dict[str, list[RegistryTrialRef]] = {}

    for flat_row, domain_def in zip(
        flat_metrics.get("alignment_by_domain", []),
        ALIGNMENT_DOMAINS,
    ):
        protocol_value = flat_row.get("Protocol Choice")
        comp_match = flat_row.get("Completed Match (%)")
        disr_match = flat_row.get("Disrupted Match (%)")
        signal = flat_row.get("Signal", "")

        c_refs = _trial_refs_for_domain(completed_df, domain_def, protocol_value, max_refs=4)
        d_refs = _trial_refs_for_domain(disrupted_df, domain_def, protocol_value, max_refs=3)
        domain_refs_by_label[flat_row.get("Domain", "")] = c_refs + d_refs

        ev = _build_domain_evidence(
            flat_row.get("Domain", ""),
            comp_match,
            disr_match,
            signal,
            c_refs,
            d_refs,
            evidence_strength,
        )
        domain_results.append(DomainAlignmentResult(
            domain=flat_row.get("Domain", ""),
            protocol_choice=str(protocol_value or "Not provided"),
            overall_match_pct=flat_row.get("Overall Match (%)"),
            completed_match_pct=comp_match,
            disrupted_match_pct=disr_match,
            net_gap_pct=flat_row.get("Net Gap (%)"),
            signal=signal,
            why_it_matters=flat_row.get("Why It Matters", ""),
            evidence=ev,
        ))

    # ── DesignRecommendation list ─────────────────────────────────────────────
    design_recs: list[DesignRecommendation] = []
    for flat_rec in flat_recs:
        category = flat_rec.get("Category", "")
        refs = domain_refs_by_label.get(category, [])
        ev = _build_recommendation_evidence(flat_rec, evidence_strength, refs)
        design_recs.append(DesignRecommendation(
            priority=flat_rec.get("Priority", "Monitor"),
            category=category,
            action_type=flat_rec.get("Action Type", "Monitor"),
            recommendation=flat_rec.get("Recommendation", ""),
            rationale=flat_rec.get("Rationale", ""),
            evidence=ev,
        ))

    # ── ComparisonResult ──────────────────────────────────────────────────────
    return ComparisonResult(
        protocol_condition=flat_metrics.get("condition", DEFAULT_CONDITION),
        timestamp=timestamp,
        cohort=cohort,
        enrollment=enrollment,
        duration=duration,
        alignment_by_domain=domain_results,
        design_alignment_index=flat_metrics.get("design_alignment_index"),
        completed_design_fit_pct=flat_metrics.get("completed_design_fit_pct"),
        disrupted_design_fit_pct=flat_metrics.get("disrupted_design_fit_pct"),
        precedent_gap_pct=flat_metrics.get("precedent_gap_pct"),
        precedent_posture=flat_metrics.get("precedent_posture", "Incomplete precedent signal"),
        missing_core_fields=flat_metrics.get("missing_core_fields", []),
        protocol_endpoint_focus=flat_metrics.get("protocol_endpoint_focus", ""),
        recommendations=design_recs,
    )
