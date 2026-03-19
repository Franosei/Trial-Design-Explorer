"""
Clinical Trials Service — registry fetch, parsing, and design similarity scoring.

Design Similarity Model
───────────────────────
Trials are scored across five clinical domains that determine whether two studies
are truly comparable — matching the strictness required for:
  • Regulatory submissions (external control arms, bridging studies)
  • Systematic reviews / meta-analyses (PICO alignment)
  • Indirect treatment comparisons (ITCs) and network meta-analyses

Domain                Weight  Key Sub-dimensions
──────────────────────────────────────────────────────────
Population               5    Disease indication, age range, line of therapy
Design                   5    Study type, allocation (RCT), masking, model
Endpoints                5    Primary endpoint text, phase context
Intervention             4    Drug/device class, comparator structure
Duration                 3    Treatment duration & follow-up window

Similarity thresholds (for interpretation, not hard filtering):
  ≥ 0.70  Strong    — suitable for external control / ITC without adjustment
  0.45–0.70 Moderate — requires statistical adjustment (matching, propensity)
  < 0.45  Weak      — major differences; do not claim similarity

Sponsor is intentionally excluded from all scoring.
"""

import re
from collections import Counter

import pandas as pd
import requests

from trial_design_explorer.config import BASE_API_URL, DEFAULT_PAGE_SIZE

# ── Domain weights ─────────────────────────────────────────────────────────────
# Top-level domains mirror the formal PICO-aligned similarity framework.
_DOMAIN_WEIGHTS = {
    "population":   5,   # Disease, age range, line of therapy
    "design":       5,   # Study type, allocation, masking, model
    "endpoints":    5,   # Primary endpoint + phase maturity context
    "intervention": 4,   # Drug/device class + comparator structure
    "duration":     3,   # Treatment duration and follow-up window
}
_MAX_DOMAIN_WEIGHT = sum(_DOMAIN_WEIGHTS.values())  # 22

# Similarity classification thresholds (0–1 scale)
SIMILARITY_STRONG   = 0.70   # All domains align — suitable for ITC / external control
SIMILARITY_MODERATE = 0.45   # Minor differences — requires statistical adjustment
# Below MODERATE: weak — major differences; similarity claim is not defensible

# Hard filter for cohort inclusion (relaxed to avoid empty cohorts)
_MIN_SIMILARITY = 0.25
_MIN_COHORT_SIZE = 30

# Phase adjacency: pairs considered "close enough" for partial credit
_ADJACENT_PHASES: set[frozenset] = {
    frozenset({"Phase 1", "Phase 1/2"}),
    frozenset({"Phase 1/2", "Phase 2"}),
    frozenset({"Phase 2", "Phase 2/3"}),
    frozenset({"Phase 2/3", "Phase 3"}),
    frozenset({"Phase 3", "Phase 3/4"}),
    frozenset({"Phase 3/4", "Phase 4"}),
}

# Line-of-therapy keywords for prior treatment signal
_FIRST_LINE_TERMS = {
    "first-line", "first line", "1st line", "1st-line",
    "treatment-naive", "treatment naive", "naive", "untreated",
    "previously untreated", "no prior", "without prior",
}
_SECOND_PLUS_TERMS = {
    "second-line", "second line", "2nd line", "2nd-line",
    "refractory", "relapsed", "relapsed/refractory", "relapsed or refractory",
    "previously treated", "prior therapy", "prior chemotherapy",
    "prior treatment", "after prior", "post-progression",
}

# Intervention category tags (CT.gov vocabulary)
_INTERVENTION_CATEGORIES = [
    "drug", "biologic", "biological", "device", "behavioral", "procedure",
    "radiation", "dietary supplement", "combination product", "genetic", "other",
]

# Token stop-words for endpoint similarity
_ENDPOINT_STOP = {
    "at", "the", "a", "in", "of", "or", "and", "to", "for", "by", "as", "from",
    "with", "after", "before", "during", "weeks", "months", "days",
    "week", "month", "day", "year", "time", "per", "rate", "change",
}

# Token stop-words for population / condition text
_POP_STOP = {
    "patient", "patients", "adult", "adults", "with", "and", "or", "who",
    "have", "had", "the", "a", "an", "of", "in", "to", "for", "receiving",
    "diagnosed", "history", "prior", "least", "more", "than", "years",
    "aged", "age", "disease", "disorder", "syndrome",
}


# ── Registry fetch and parse ───────────────────────────────────────────────────

def fetch_trials_by_condition(condition: str, limit: int = DEFAULT_PAGE_SIZE):
    try:
        response = requests.get(
            BASE_API_URL,
            params={"query.term": condition, "pageSize": limit},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None


def parse_trials_to_df(api_response) -> pd.DataFrame:
    trials: list[dict] = []

    for study in api_response.get("studies", []):
        try:
            protocol_section = study.get("protocolSection", {})

            identification   = protocol_section.get("identificationModule", {})
            status_module    = protocol_section.get("statusModule", {})
            design_module    = protocol_section.get("designModule", {})
            sponsor_module   = protocol_section.get("sponsorCollaboratorsModule", {})
            outcomes_module  = protocol_section.get("outcomesModule", {})
            conditions_module = protocol_section.get("conditionsModule", {})
            contacts_module  = protocol_section.get("contactsLocationsModule", {})
            arms_module      = protocol_section.get("armsInterventionsModule", {})
            eligibility_module = protocol_section.get("eligibilityModule", {})
            enrollment_module = protocol_section.get("designModule", {})

            raw_locations = contacts_module.get("locations", [])
            locations = [
                {
                    "city": loc.get("city"),
                    "country": loc.get("country"),
                    "facility": loc.get("facility"),
                    "lat": loc.get("geoPoint", {}).get("lat"),
                    "lon": loc.get("geoPoint", {}).get("lon"),
                }
                for loc in raw_locations
            ]

            primary_outcomes = ", ".join(
                o.get("measure", "")
                for o in outcomes_module.get("primaryOutcomes", [])
                if o.get("measure")
            ) or "N/A"

            interventions = ", ".join(
                i.get("type", "")
                for i in arms_module.get("interventions", [])
                if i.get("type")
            ) or "N/A"

            intervention_names = ", ".join(
                i.get("name", "")
                for i in arms_module.get("interventions", [])
                if i.get("name")
            ) or "N/A"

            collaborator_names = ", ".join(
                c.get("name", "")
                for c in sponsor_module.get("collaborators", [])
                if c.get("name")
            ) or "N/A"

            country_count = len({
                loc.get("country") for loc in locations if loc.get("country")
            })

            trials.append({
                "NCT ID":            identification.get("nctId"),
                "Title":             identification.get("briefTitle", "Untitled Trial"),
                "Conditions":        ", ".join(conditions_module.get("conditions", [])) or "N/A",
                "Study Type":        design_module.get("studyType", "N/A"),
                "Phase":             ", ".join(design_module.get("phases", [])) or "N/A",
                "Status":            status_module.get("overallStatus", "Unknown"),
                "Start Date":        status_module.get("startDateStruct", {}).get("date"),
                "Completion Date":   status_module.get("completionDateStruct", {}).get("date"),
                "Enrollment":        enrollment_module.get("enrollmentInfo", {}).get("count"),
                "Enrollment Type":   enrollment_module.get("enrollmentInfo", {}).get("type", "N/A"),
                "Allocation":        design_module.get("designInfo", {}).get("allocation", "N/A"),
                "Intervention Model": design_module.get("designInfo", {}).get("interventionModel", "N/A"),
                "Masking":           design_module.get("designInfo", {}).get("maskingInfo", {}).get("masking", "N/A"),
                "Primary Purpose":   design_module.get("designInfo", {}).get("primaryPurpose", "N/A"),
                "Intervention Types": interventions,
                "Interventions":     intervention_names,
                "Sponsor":           sponsor_module.get("leadSponsor", {}).get("name", "Unknown Sponsor"),
                "Collaborators":     collaborator_names,
                "Sex":               eligibility_module.get("sex", "N/A"),
                "Minimum Age":       eligibility_module.get("minimumAge", "N/A"),
                "Maximum Age":       eligibility_module.get("maximumAge", "N/A"),
                "Healthy Volunteers": eligibility_module.get("healthyVolunteers", "N/A"),
                "Primary Outcome":   primary_outcomes,
                "Primary Outcome Count": len(outcomes_module.get("primaryOutcomes", [])),
                "Arms Count":        len(arms_module.get("armGroups", [])),
                "Location Count":    len(locations),
                "Country Count":     country_count,
                "Locations":         locations,
            })
        except Exception:
            continue

    return pd.DataFrame(trials)


def median_trial_duration_months(trials_df: pd.DataFrame) -> int | None:
    if trials_df.empty:
        return None
    start = pd.to_datetime(trials_df["Start Date"], errors="coerce")
    end   = pd.to_datetime(trials_df["Completion Date"], errors="coerce")
    months = ((end - start).dt.days / 30).dropna()
    return int(months.median()) if not months.empty else None


def count_countries(trials_df: pd.DataFrame) -> int:
    return len({
        loc.get("country")
        for locs in trials_df.get("Locations", [])
        for loc in locs
        if isinstance(loc, dict) and loc.get("country")
    })


def most_common_primary_outcome(trials_df: pd.DataFrame) -> tuple[str, int] | None:
    if "Primary Outcome" not in trials_df or trials_df["Primary Outcome"].dropna().empty:
        return None
    outcomes = []
    for val in trials_df["Primary Outcome"].dropna().astype(str):
        outcomes.extend(p.strip() for p in val.split(",") if p.strip())
    if not outcomes:
        return None
    return Counter(outcomes).most_common(1)[0]


# ── Primitive scoring utilities ────────────────────────────────────────────────

def _norm(value: str | None) -> str:
    if not value or str(value).strip().lower() in ("n/a", "unknown", "", "not provided", "nan"):
        return ""
    return str(value).strip().lower()


def _field_score(protocol_value: str | None, trial_value: str | None) -> float:
    """1.0 exact match, 0.5 if either unspecified, 0.0 mismatch."""
    p = _norm(protocol_value)
    t = _norm(trial_value)
    if not p or not t:
        return 0.5
    return 1.0 if p in t or t in p else 0.0


def _phase_score(protocol_phase: str, trial_phase: str) -> float:
    """1.0 exact, 0.5 adjacent or unspecified, 0.0 incompatible."""
    p = _norm(protocol_phase)
    t = _norm(trial_phase)
    if not p or not t:
        return 0.5

    def _canonical(s: str) -> str:
        s = s.replace("phase", "").strip()
        roman = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5"}
        return "/".join(roman.get(part.strip(), part.strip()) for part in s.split("/"))

    pc, tc = _canonical(p), _canonical(t)
    if pc == tc:
        return 1.0
    if frozenset({f"phase {pc}", f"phase {tc}"}) in _ADJACENT_PHASES:
        return 0.5
    return 0.0


def _jaccard_score(text_a, text_b, stop: set) -> float:
    """
    Token Jaccard similarity with thresholded output:
      ≥ 0.30 → 1.0,  0.10–0.30 → 0.5,  < 0.10 → 0.0
    """
    def _tokens(text) -> set:
        if isinstance(text, list):
            text = " ".join(str(t) for t in text)
        cleaned = re.sub(r"[^a-z0-9/\-]", " ", str(text).lower())
        return {tok for tok in cleaned.split() if len(tok) > 2 and tok not in stop}

    a = _tokens(text_a)
    b = _tokens(text_b)
    if not a or not b:
        return 0.5
    j = len(a & b) / len(a | b)
    return 1.0 if j >= 0.30 else (0.5 if j >= 0.10 else 0.0)


# ── Domain 1: Population ───────────────────────────────────────────────────────

_AGE_RE = re.compile(r"\b(\d+)\s*(?:years?|yrs?|y\.?o\.?)", re.IGNORECASE)


def _parse_age(text: str) -> int | None:
    m = _AGE_RE.search(str(text))
    return int(m.group(1)) if m else None


def _age_range_score(protocol_meta, trial_row: dict) -> float:
    """
    Age-range overlap between protocol target_population and trial Minimum/Maximum Age.

    Overlap ≥ 80% of protocol range → 1.0
    Overlap  50–80%                 → 0.5
    Overlap < 50% or no overlap    → 0.0
    Either side missing             → 0.5 (neutral)

    Example:
      Protocol: "adults 18–75 years"
      Trial:    MinAge=18, MaxAge=70  → overlap 52/57 = 91% → 1.0
    """
    protocol_pop = _norm(getattr(protocol_meta, "target_population", None) or "")
    trial_min = _parse_age(str(trial_row.get("Minimum Age", "")))
    trial_max = _parse_age(str(trial_row.get("Maximum Age", "")))

    if trial_min is None and trial_max is None:
        return 0.5

    # Extract age numbers from protocol population text
    ages = [int(n) for n in re.findall(r"\b([1-9]\d)\b", protocol_pop) if 1 <= int(n) <= 120]
    if not ages:
        return 0.5

    proto_min = min(ages)
    proto_max = max(ages) if len(ages) > 1 else 100   # assume open upper bound

    t_min = trial_min if trial_min is not None else 0
    t_max = trial_max if trial_max is not None else 120

    overlap_lo = max(proto_min, t_min)
    overlap_hi = min(proto_max, t_max)

    if overlap_lo > overlap_hi:
        return 0.0

    proto_range = max(proto_max - proto_min, 1)
    overlap_pct = (overlap_hi - overlap_lo) / proto_range

    return 1.0 if overlap_pct >= 0.80 else (0.5 if overlap_pct >= 0.50 else 0.0)


def _disease_indication_score(protocol_meta, trial_row: dict) -> float:
    """
    Keyword overlap: protocol condition + target population vs trial Conditions.

    Same disease (e.g., "non-small cell lung cancer") → 1.0
    Related disease terms → partial
    Completely different → 0.0

    A different disease stage (e.g., early vs advanced) is a red flag —
    flagged by the line-of-therapy scorer, not here.
    """
    p_condition = _norm(getattr(protocol_meta, "condition", None) or "")
    p_pop = _norm(getattr(protocol_meta, "target_population", None) or "")[:300]
    t_conditions = _norm(trial_row.get("Conditions", ""))

    if not t_conditions:
        return 0.5

    source = (p_condition + " " + p_pop).strip()
    if not source:
        return 0.5

    p_tokens = {t for t in source.split() if len(t) > 3 and t not in _POP_STOP}
    t_tokens = set(t_conditions.split())

    if not p_tokens:
        return 0.5

    overlap = len(p_tokens & t_tokens) / len(p_tokens)
    return min(overlap * 2.0, 1.0)   # 50% keyword match → 1.0


def _line_of_therapy_score(protocol_meta, trial_row: dict) -> float:
    """
    First-line vs second-line / refractory signal.

    Different lines of therapy break comparability even when every other
    domain aligns — a Phase 3 trial in treatment-naive patients cannot be a
    valid comparator for a second-line trial.

    Returns:
      1.0  Same line (both first-line or both second+)
      0.0  Different lines (confirmed mismatch)
      0.5  Cannot determine (one or both sides unspecified)
    """
    p_pop = _norm(getattr(protocol_meta, "target_population", None) or "")
    t_text = _norm((trial_row.get("Conditions", "") or "") + " " +
                   (trial_row.get("Title", "") or ""))

    if not p_pop:
        return 0.5

    proto_first  = any(k in p_pop    for k in _FIRST_LINE_TERMS)
    proto_second = any(k in p_pop    for k in _SECOND_PLUS_TERMS)
    trial_first  = any(k in t_text   for k in _FIRST_LINE_TERMS)
    trial_second = any(k in t_text   for k in _SECOND_PLUS_TERMS)

    if not (proto_first or proto_second) or not (trial_first or trial_second):
        return 0.5   # Line cannot be determined on one side

    if (proto_first and trial_first) or (proto_second and trial_second):
        return 1.0

    return 0.0  # Confirmed different lines — comparability broken


def _score_population_domain(protocol_meta, trial_row: dict) -> float:
    """
    Population domain (weight 5).

    Sub-dimensions:
      Disease indication (weight 3) — same disease/indication keyword overlap
      Age range          (weight 2) — numeric age range overlap
      Line of therapy    (weight 1) — first-line vs second-line / refractory

    Example: HbA1c 7–10% on metformin ≈ HbA1c 7–9.5% on metformin → near 1.0
    """
    disease  = _disease_indication_score(protocol_meta, trial_row)
    age      = _age_range_score(protocol_meta, trial_row)
    lot      = _line_of_therapy_score(protocol_meta, trial_row)

    return (3 * disease + 2 * age + 1 * lot) / 6.0


# ── Domain 2: Study Design ─────────────────────────────────────────────────────

def _score_design_domain(protocol_meta, trial_row: dict) -> float:
    """
    Design domain (weight 5).

    Sub-dimensions (internal weights):
      Study type       (3) — Interventional vs Observational
      Allocation       (3) — RCT vs non-RCT — critical for regulatory submissions
      Masking          (2) — Double-blind vs open-label
      Intervention model (2) — Parallel vs Crossover

    High similarity requires same design paradigm (e.g., both double-blind RCTs).
    Breaks: RCT vs single-arm observational is a disqualifying difference.
    """
    study_type = _field_score(getattr(protocol_meta, "study_type", None), trial_row.get("Study Type"))
    allocation = _field_score(getattr(protocol_meta, "allocation", None), trial_row.get("Allocation"))
    masking    = _field_score(getattr(protocol_meta, "masking", None), trial_row.get("Masking"))
    model      = _field_score(getattr(protocol_meta, "intervention_model", None), trial_row.get("Intervention Model"))

    return (3 * study_type + 3 * allocation + 2 * masking + 2 * model) / 10.0


# ── Domain 3: Endpoints ────────────────────────────────────────────────────────

def _score_endpoints_domain(protocol_meta, trial_row: dict) -> float:
    """
    Endpoints domain (weight 5).

    Sub-dimensions:
      Primary endpoint text (weight 4) — Jaccard token similarity
        Even small differences in endpoint definitions can break comparability.
        "Change in HbA1c at 12 weeks" ≠ "Change in HbA1c at 26 weeks".
      Phase context (weight 2) — phase proximity as endpoint maturity proxy

    Critical point: different primary endpoints (OS vs PFS) → near 0.0 score.
    This is the most important domain for ITC/network meta-analysis.
    """
    endpoint = _jaccard_score(
        getattr(protocol_meta, "primary_endpoints", None),
        trial_row.get("Primary Outcome"),
        _ENDPOINT_STOP,
    )
    phase = _phase_score(
        getattr(protocol_meta, "phase", None),
        trial_row.get("Phase"),
    )

    return (4 * endpoint + 2 * phase) / 6.0


# ── Domain 4: Intervention & Comparator ───────────────────────────────────────

def _intervention_class_score(protocol_meta, trial_row: dict) -> float:
    """
    Drug class / mechanism alignment.

    Two trials using different drugs can still be "similar" if:
      • Same drug class (both are PD-1 inhibitors → Drug/Biologic match)
      • Same mechanism of action (both are kinase inhibitors)

    Scoring:
      Same CT.gov intervention category → 1.0
      Drug ≈ Biologic (both systemic agents) → 0.5
      Different categories → 0.0
      Missing data → 0.5 (neutral)
    """
    p_desc  = _norm(getattr(protocol_meta, "intervention_description", None))
    t_types = _norm(trial_row.get("Intervention Types", ""))
    t_names = _norm(trial_row.get("Interventions", ""))

    if not p_desc or (not t_types and not t_names):
        return 0.5

    p_cats = {c for c in _INTERVENTION_CATEGORIES if c in p_desc}
    t_cats = {c for c in _INTERVENTION_CATEGORIES if c in t_types}

    if p_cats and t_cats:
        p_norm = {"biological" if c == "biologic" else c for c in p_cats}
        t_norm = {"biological" if c == "biologic" else c for c in t_cats}
        if p_norm & t_norm:
            return 1.0
        if (("drug" in p_norm or "biological" in p_norm)
                and ("drug" in t_norm or "biological" in t_norm)):
            return 0.5   # Both systemic agents — partial credit
        return 0.0

    # Fallback: token overlap between description and trial intervention text
    p_tokens = set(p_desc.split())
    t_tokens = set((t_types + " " + t_names).split())
    if not p_tokens or not t_tokens:
        return 0.5
    overlap = len(p_tokens & t_tokens) / max(len(p_tokens | t_tokens), 1)
    return 1.0 if overlap >= 0.20 else (0.5 if overlap > 0.05 else 0.0)


_NO_COMPARATOR_TERMS = {
    "none", "single", "single-arm", "single arm", "no comparator",
    "no control", "open label", "n/a", "not applicable",
}
_PLACEBO_TERMS      = {"placebo", "sham", "sugar pill", "inactive"}
_ACTIVE_COMP_TERMS  = {
    "active", "standard of care", "soc", "standard care", "usual care",
    "best supportive", "active comparator", "comparator",
}


def _comparator_structure_score(protocol_meta, trial_row: dict) -> float:
    """
    Control arm structure: single-arm vs placebo vs active comparator.

    Breaks comparability:
      Protocol = placebo-controlled RCT  vs  Trial = single-arm → 0.0
      Protocol = single-arm              vs  Trial = 2-arm RCT  → 0.0

    Arms count from CT.gov is used as a proxy when comparator text is absent.
    """
    p_comp  = _norm(getattr(protocol_meta, "comparator", None))
    p_arms  = _norm(getattr(protocol_meta, "arms_count", None))
    t_arms  = trial_row.get("Arms Count") or 0
    try:
        t_arms = int(t_arms)
    except (ValueError, TypeError):
        t_arms = 0

    if not p_comp and not p_arms:
        return 0.5

    is_single_arm = any(k in p_comp for k in _NO_COMPARATOR_TERMS) if p_comp else False
    has_placebo   = any(k in p_comp for k in _PLACEBO_TERMS)        if p_comp else False
    has_active    = any(k in p_comp for k in _ACTIVE_COMP_TERMS)    if p_comp else False

    if p_arms and p_arms.isdigit():
        if int(p_arms) == 1:
            is_single_arm = True
        elif int(p_arms) >= 2:
            is_single_arm = False

    if t_arms == 0:
        return 0.5   # Unknown trial arm count — neutral

    if is_single_arm:
        return 1.0 if t_arms <= 1 else 0.0
    elif has_placebo or has_active:
        return 1.0 if t_arms >= 2 else 0.0
    return 0.5   # Comparator type indeterminate


def _score_intervention_domain(protocol_meta, trial_row: dict) -> float:
    """
    Intervention & Comparator domain (weight 4).

    Sub-dimensions (equal weight):
      Intervention class (2) — Drug / Biologic / Device / Behavioral
      Comparator structure (2) — Single-arm vs placebo vs active comparator

    Important nuance: two different drugs can still score high here if they
    share the same drug class or mechanism context.
    """
    iv_class = _intervention_class_score(protocol_meta, trial_row)
    comp     = _comparator_structure_score(protocol_meta, trial_row)
    return (2 * iv_class + 2 * comp) / 4.0


# ── Domain 5: Duration & Follow-up ────────────────────────────────────────────

def _parse_duration_months(start: str | None, end: str | None) -> float | None:
    """Return duration in months between two date strings; None if unparseable."""
    try:
        s = pd.to_datetime(start, errors="coerce")
        e = pd.to_datetime(end,   errors="coerce")
        if pd.isna(s) or pd.isna(e):
            return None
        months = (e - s).days / 30.44
        return months if months > 0 else None
    except Exception:
        return None


def _score_duration_domain(protocol_meta, trial_row: dict) -> float:
    """
    Duration & Follow-up domain (weight 3).

    Compares planned protocol duration (start → completion date) against the
    actual trial duration recorded in CT.gov.

    Thresholds:
      < 20% relative difference → 1.0  (closely comparable follow-up windows)
      20–50% difference          → 0.5  (similar but not identical)
      > 50% difference           → 0.0  (vastly different observation windows)
      Either side unparseable    → 0.5  (neutral; protocol often has no dates yet)

    Example:
      Protocol: 24-month follow-up
      Trial A:  22-month follow-up → Δ 8% → 1.0
      Trial B:  48-month follow-up → Δ 50% → 0.5
      Trial C:   6-month follow-up → Δ 75% → 0.0
    """
    proto_months = _parse_duration_months(
        getattr(protocol_meta, "start_date", None),
        getattr(protocol_meta, "completion_date", None),
    )
    trial_months = _parse_duration_months(
        trial_row.get("Start Date"),
        trial_row.get("Completion Date"),
    )

    if proto_months is None or trial_months is None:
        return 0.5

    diff_pct = abs(proto_months - trial_months) / max(proto_months, trial_months)
    return 1.0 if diff_pct <= 0.20 else (0.5 if diff_pct <= 0.50 else 0.0)


# ── Top-level scorer ───────────────────────────────────────────────────────────

def score_trial_design_similarity(protocol_meta, trial_row: dict) -> float:
    """
    Score a single trial row against a protocol across five clinical domains.

    Returns a float 0.0–1.0 where:
      ≥ 0.70  Strong    — clinically comparable; suitable for external control or ITC
      0.45–0.70 Moderate — minor differences; requires statistical adjustment
      < 0.45  Weak      — major differences; do not claim similarity

    The five domains and their weights are:
      Population   (5) — disease indication, age range, line of therapy
      Design       (5) — study type, allocation (RCT), masking, model
      Endpoints    (5) — primary endpoint text (Jaccard), phase context
      Intervention (4) — drug/device class, comparator structure
      Duration     (3) — treatment duration and follow-up window

    Sponsor is NOT used in any dimension.
    """
    domain_scores = score_domain_breakdown(protocol_meta, trial_row)
    weighted = sum(_DOMAIN_WEIGHTS[d] * s for d, s in domain_scores.items())
    return round(weighted / _MAX_DOMAIN_WEIGHT, 4)


def score_domain_breakdown(protocol_meta, trial_row: dict) -> dict[str, float]:
    """
    Return per-domain similarity scores for a single trial.

    Each value is 0.0–1.0.  Useful for:
      • Explaining why a trial was included or excluded ("Endpoint domain: 0.1")
      • Audit trail entries ("Strong population match, weak endpoint match")
      • UI display of per-dimension similarity bars

    Keys: population, design, endpoints, intervention, duration
    """
    return {
        "population":   _score_population_domain(protocol_meta, trial_row),
        "design":       _score_design_domain(protocol_meta, trial_row),
        "endpoints":    _score_endpoints_domain(protocol_meta, trial_row),
        "intervention": _score_intervention_domain(protocol_meta, trial_row),
        "duration":     _score_duration_domain(protocol_meta, trial_row),
    }


def classify_similarity(score: float) -> str:
    """
    Return a professional label for a similarity score.

    Aligns with the language used in regulatory submissions, meta-analyses,
    and ITC frameworks:
      'Clinically comparable'       → Strong (≥ 0.70)
      'Methodologically aligned'    → Moderate (0.45–0.70)
      'Not directly comparable'     → Weak (< 0.45)
    """
    if score >= SIMILARITY_STRONG:
        return "Clinically comparable"
    elif score >= SIMILARITY_MODERATE:
        return "Methodologically aligned"
    return "Not directly comparable"


def build_design_similar_cohort(
    protocol_meta,
    trials_df: pd.DataFrame,
    min_similarity: float = _MIN_SIMILARITY,
    min_cohort_size: int = _MIN_COHORT_SIZE,
) -> pd.DataFrame:
    """
    Filter and rank a condition-matched trial DataFrame by design similarity.

    Selection is based on the five-domain PICO-aligned scoring model.
    Sponsor is intentionally excluded from all scoring dimensions.

    Trials with score ≥ min_similarity are kept. If fewer than min_cohort_size
    pass the threshold, the threshold is relaxed to always return a useful cohort.

    Adds columns:
      design_similarity_score   — overall 0–1 score
      similarity_class          — "Clinically comparable" / "Methodologically aligned" / etc.
      sim_population            — population domain score
      sim_design                — design domain score
      sim_endpoints             — endpoints domain score
      sim_intervention          — intervention domain score
      sim_duration              — duration domain score
    """
    if trials_df is None or trials_df.empty:
        return trials_df if trials_df is not None else pd.DataFrame()

    records = trials_df.to_dict("records")
    breakdowns = [score_domain_breakdown(protocol_meta, row) for row in records]
    scores = [
        round(sum(_DOMAIN_WEIGHTS[d] * s for d, s in bd.items()) / _MAX_DOMAIN_WEIGHT, 4)
        for bd in breakdowns
    ]

    result = trials_df.copy()
    result["design_similarity_score"] = scores
    result["similarity_class"]  = [classify_similarity(s) for s in scores]
    result["sim_population"]    = [bd["population"]   for bd in breakdowns]
    result["sim_design"]        = [bd["design"]        for bd in breakdowns]
    result["sim_endpoints"]     = [bd["endpoints"]     for bd in breakdowns]
    result["sim_intervention"]  = [bd["intervention"]  for bd in breakdowns]
    result["sim_duration"]      = [bd["duration"]      for bd in breakdowns]

    result = result.sort_values("design_similarity_score", ascending=False)

    filtered = result[result["design_similarity_score"] >= min_similarity]
    if len(filtered) < min_cohort_size:
        filtered = result.head(max(min_cohort_size, len(result)))

    return filtered.reset_index(drop=True)


def cohort_selection_summary(
    protocol_meta,
    all_trials_df: pd.DataFrame,
    selected_df: pd.DataFrame,
) -> dict:
    """
    Return an audit-ready summary of how the design-similar cohort was selected.

    Includes per-domain median scores for the selected cohort — useful for
    explaining which domains drove inclusion/exclusion.
    """
    total    = len(all_trials_df)
    selected = len(selected_df)

    score_stats = {}
    if selected > 0 and "design_similarity_score" in selected_df.columns:
        score_stats = {
            "similarity_score_median": round(float(selected_df["design_similarity_score"].median()), 3),
            "similarity_score_min":    round(float(selected_df["design_similarity_score"].min()),    3),
            "similarity_score_max":    round(float(selected_df["design_similarity_score"].max()),    3),
        }
        # Per-domain medians for auditability
        for col in ("sim_population", "sim_design", "sim_endpoints", "sim_intervention", "sim_duration"):
            if col in selected_df.columns:
                score_stats[f"median_{col}"] = round(float(selected_df[col].median()), 3)

    strong   = (selected_df.get("design_similarity_score", pd.Series()) >= SIMILARITY_STRONG).sum()
    moderate = ((selected_df.get("design_similarity_score", pd.Series()) >= SIMILARITY_MODERATE) &
                (selected_df.get("design_similarity_score", pd.Series()) < SIMILARITY_STRONG)).sum()

    return {
        "condition_matched_total":   total,
        "design_similar_selected":   selected,
        "selection_rate_pct":        round(selected / total * 100, 1) if total else 0,
        "strong_similarity_count":   int(strong),
        "moderate_similarity_count": int(moderate),
        "weak_similarity_count":     max(0, selected - int(strong) - int(moderate)),
        "sponsor_used_for_selection": False,
        "design_dimensions_used":    list(_DOMAIN_WEIGHTS.keys()),
        "domain_weights":            dict(_DOMAIN_WEIGHTS),
        **score_stats,
    }
