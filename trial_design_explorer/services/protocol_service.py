"""
Protocol extraction service.

Architecture
────────────
The LLM is the sole extractor of field values.  No regex is used to read or
parse field values.

For short documents (≤ 50 k chars): one comprehensive LLM pass on the full text.

For longer documents (100+ page protocols): four targeted LLM passes, each
receiving a keyword-anchored reading window — a slice of raw text centred on
the ACTUAL position of the relevant content in the document (found via simple
string search).  This avoids the broken-section-detection problem where a
pattern like "study site" accidentally matches an adverse-event section instead
of the geography section.

Keyword-anchored windows:
  Pass 1 — first 15 k chars  (title page, synopsis, study design header)
  Pass 2 — window around "primary endpoint" / "primary outcome"
  Pass 3 — window around "inclusion criteria" / "eligibility criteria"
  Pass 4 — window around "investigational product" / "study treatment" / dosing

Merging: later passes win for their specialist fields; rich text fields prefer
the longer, more detailed value.

The minimal structural-heuristic fallback is used ONLY when no LLM is available.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from trial_design_explorer.config import PROTOCOL_FIELDS
from trial_design_explorer.domain import ProtocolMetadata, ProvenanceRecord
from trial_design_explorer.services.comparison_service import classify_endpoint_category
from trial_design_explorer.services.audit_service import build_provenance_record
from trial_design_explorer.services.openai_service import (
    generate_chat_completion,
    has_openai_config,
    configured_model_name,
)


# ── Document size thresholds ───────────────────────────────────────────────────
_SINGLE_PASS_MAX_CHARS = 50_000   # ≤ this → full-text single LLM pass
_WINDOW_SIZE           = 14_000   # chars per keyword-anchored window
_WINDOW_LEAD           = 800      # chars before the anchor keyword

# Content sections (endpoints, eligibility, intervention) almost never appear
# in the first ~25 k chars of a multi-page protocol — that space is occupied by
# the title page, document history / amendment table, TOC, and abbreviations /
# glossary.  Searching from min_pos skips these early false anchor matches
# (e.g. "primary outcome measure" appearing in the glossary definitions, or
# "study intervention" appearing in the title-page header, or
# "inclusion criteria" appearing in the summary-of-changes table).
_CONTENT_MIN_POS = 25_000   # skip first ~25 k chars for content section anchors


# ── Keyword anchors for each pass (plain substrings, case-insensitive) ─────────
# These are searched in the RAW document text.  The first match wins and a
# reading window is extracted around it.  Plain substrings are more reliable
# than regex on OCR'd / PDF-extracted text with character artifacts.

_PASS1_ANCHORS = [
    # Synopsis / study design header — usually in the first quarter of a protocol
    "synopsis", "study synopsis", "brief summary",
    "study design", "trial design", "overall design",
    "study objectives", "primary objective",
]

_PASS2_ANCHORS = [
    # Primary endpoints section — can be anywhere in the document
    "primary endpoint", "primary efficacy endpoint",
    "primary outcome measure", "co-primary endpoint",
    "primary end point", "key secondary endpoint",
    "secondary endpoint", "secondary outcome",
]

_PASS3_ANCHORS = [
    # Eligibility / inclusion criteria section
    "inclusion criteria", "inclusion/exclusion", "inclusion and exclusion",
    "eligibility criteria", "participants are eligible",
    "subjects are eligible", "key inclusion",
]

_PASS4_ANCHORS = [
    # Intervention / dosing section
    "investigational product", "study medication",
    "dose and administration", "dosing regimen",
    "treatment description", "study treatment",
    "study intervention", "drug product",
]


# ── LLM system prompt ──────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """\
You are a senior clinical trial protocol analyst with deep expertise in ICH E6 GCP,
FDA/EMA regulatory submissions, and Phase 1–4 trial design.

Your sole task: extract structured protocol fields from the text provided and return
them as a single valid JSON object.

Extraction rules:
1. Return ONLY a JSON object — no prose, no markdown code fences, no extra text.
2. Use JSON null for any field not found in the provided text. Never guess or invent.
3. Do NOT paraphrase — copy field values VERBATIM from the document.
4. Endpoints: include the exact measure AND the timepoint/assessment window
   (e.g. "Progression-Free Survival at 12 months per RECIST 1.1").
   If there are multiple primary endpoints list each on a separate line separated by \\n.
5. target_population: copy the FULL inclusion AND exclusion criteria text verbatim.
   Include age ranges, biomarker thresholds (e.g. HbA1c 7–10 %), prior treatment
   requirements, performance status, organ function criteria — everything stated.
6. intervention_description: include drug name, mechanism, dose, route, schedule,
   and cycle length if stated.
7. comparator: describe the control arm fully (placebo, active comparator,
   standard of care, single-arm / no comparator).
8. study_type — use EXACTLY one of: Interventional, Observational, Expanded Access
9. allocation — use EXACTLY one of: Randomized, Non-Randomized (or null)
10. masking — use EXACTLY one of: Open Label, Single, Double, Triple, Quadruple (or null)
11. intervention_model — use EXACTLY one of: Parallel Assignment, Crossover Assignment,
    Factorial Assignment, Single Group Assignment, Sequential Assignment (or null)
12. primary_purpose — use EXACTLY one of: Treatment, Prevention, Diagnostic,
    Supportive Care, Screening, Device Feasibility, Basic Science,
    Health Services Research (or null)
13. phase — use the standard clinical format: "Phase 1", "Phase 2", "Phase 3",
    "Phase 1/2", "Phase 2/3", "Phase 3/4" etc.
14. sample_size — numeric string only (e.g. "450"), no units.
15. arms_count — numeric string only (e.g. "2").
16. dates — use YYYY-MM or YYYY-MM-DD if available, else natural language as written.
"""

# Full field list for a single comprehensive pass
_ALL_FIELDS = [
    "title", "condition", "sponsor", "phase", "study_type", "sample_size",
    "arms_count", "allocation", "masking", "intervention_model", "primary_purpose",
    "start_date", "completion_date", "geography_focus",
    "primary_endpoints", "secondary_endpoints", "endpoint_focus",
    "target_population", "comparator", "intervention_description",
]

# Fields per targeted pass (used when document is too long for single pass)
_PASS1_FIELDS = [
    "title", "condition", "sponsor", "phase", "study_type", "sample_size",
    "arms_count", "allocation", "masking", "intervention_model", "primary_purpose",
    "start_date", "completion_date", "geography_focus",
]
_PASS2_FIELDS = ["primary_endpoints", "secondary_endpoints", "endpoint_focus"]
_PASS3_FIELDS = ["target_population", "comparator", "intervention_description"]


# ── Keyword-anchored window extraction ────────────────────────────────────────

def _anchor_window(text: str, anchors: list[str],
                   window: int = _WINDOW_SIZE,
                   lead: int = _WINDOW_LEAD,
                   min_pos: int = 0) -> Optional[str]:
    """
    Find the FIRST occurrence of any anchor keyword in the raw text (case-
    insensitive plain substring search) and return a reading window around it.

    min_pos — skip the first N characters before beginning the search.
    Use _CONTENT_MIN_POS for content sections (endpoints, eligibility,
    intervention) to avoid false matches in the title page, changes table,
    TOC, glossary, and abbreviations sections that appear in the first
    ~25 k chars of a multi-page protocol.

    Returns None if no anchor is found at or after min_pos.
    """
    lower_text = text.lower()
    best_pos: Optional[int] = None
    for anchor in anchors:
        idx = lower_text.find(anchor.lower(), min_pos)
        if idx >= 0 and (best_pos is None or idx < best_pos):
            best_pos = idx
    if best_pos is None:
        return None
    start = max(0, best_pos - lead)
    end   = min(len(text), best_pos + window)
    return text[start:end]


def _first_n_chars(text: str, n: int = 15_000) -> str:
    """Return the first n characters — used for Pass 1 (title/synopsis area)."""
    return text[:n]


# ── JSON utilities ─────────────────────────────────────────────────────────────

def _parse_json(raw: str) -> Optional[dict]:
    cleaned = raw.strip()
    # Strip markdown code fences if present
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to rescue a partial JSON object
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def _normalise_value(v) -> Optional[str]:
    """Coerce a JSON value to a clean string, or None if empty/null."""
    if v is None:
        return None
    if isinstance(v, list):
        # Endpoints or eligibility criteria returned as a JSON array
        parts = [str(item).strip() for item in v if str(item).strip()]
        return "\n".join(parts) if parts else None
    val = str(v).strip()
    if val.lower() in ("null", "none", "n/a", "not specified", "not provided",
                       "not found", "unknown", ""):
        return None
    return val


def _merge_llm_results(*parsed_dicts: Optional[dict]) -> dict:
    """
    Merge results from multiple LLM passes.

    Priority rules:
    - Later passes win for their specialist fields (they had better context).
    - For free-text fields (endpoints, population, intervention) prefer the
      longer / more detailed value.
    - Never let a shorter value overwrite a longer one for rich text fields.
    """
    _RICH_TEXT_FIELDS = {
        "primary_endpoints", "secondary_endpoints", "target_population",
        "intervention_description", "comparator",
    }
    merged: dict = {}
    for parsed in parsed_dicts:
        if not parsed:
            continue
        for k, raw_v in parsed.items():
            v = _normalise_value(raw_v)
            if v is None:
                continue
            existing = merged.get(k)
            if existing is None:
                merged[k] = v
            elif k in _RICH_TEXT_FIELDS:
                # Keep whichever is longer and more detailed
                if len(v) > len(existing):
                    merged[k] = v
            else:
                # For structured fields (phase, allocation, etc.) later pass wins
                merged[k] = v
    return merged


# ── LLM call wrapper ───────────────────────────────────────────────────────────

def _llm_pass(text_chunk: str, fields: list[str], max_tokens: int = 3000) -> Optional[dict]:
    """Run one LLM extraction pass and return the parsed dict or None."""
    if not text_chunk.strip():
        return None

    field_json_schema = json.dumps({f: "<string or null>" for f in fields}, indent=2)
    user_prompt = (
        f"Extract the following fields from the protocol text below.\n"
        f"Return a JSON object with exactly these keys:\n{field_json_schema}\n\n"
        f"Critical reminders:\n"
        f"- Copy endpoint wording VERBATIM including timepoints and assessment criteria.\n"
        f"- Copy eligibility criteria VERBATIM — include inclusion AND exclusion criteria.\n"
        f"- For multi-item fields (endpoints, eligibility) separate items with newlines.\n"
        f"- Use null for anything not found — do not invent.\n\n"
        f"Protocol text:\n{text_chunk}"
    )
    raw = generate_chat_completion(
        _SYSTEM_PROMPT, user_prompt, temperature=0.0, max_tokens=max_tokens
    )
    return _parse_json(raw) if raw else None


# ── Main LLM extraction paths ──────────────────────────────────────────────────

def _extract_single_pass(text: str) -> tuple[dict, int]:
    """
    One comprehensive LLM pass on the full text (for documents ≤ 50k chars).
    Returns (result_dict, passes_succeeded).
    """
    result = _llm_pass(text[:_SINGLE_PASS_MAX_CHARS], _ALL_FIELDS, max_tokens=4000)
    return (result or {}), (1 if result else 0)


def _extract_multi_pass(text: str) -> tuple[dict, int]:
    """
    Four keyword-anchored LLM passes for long documents.

    Each pass receives a reading window extracted around the ACTUAL position
    of its anchor keywords in the raw text — NOT a section detected by regex.
    This prevents the broken-section-detection problem where regex accidentally
    matches unrelated parts of the document.

    Pass 1 — First 15 k chars + synopsis window : title, sponsor, design header
    Pass 2 — Endpoint window                    : primary/secondary endpoints
    Pass 3 — Eligibility window                 : inclusion/exclusion criteria
    Pass 4 — Intervention window                : drug, dose, comparator

    Returns (merged_dict, passes_succeeded_count).
    """
    # Pass 1: title page / synopsis / study design header
    chunk1 = _first_n_chars(text, 15_000)
    synopsis_window = _anchor_window(text, _PASS1_ANCHORS, window=10_000, lead=200)
    if synopsis_window and synopsis_window not in chunk1:
        chunk1 += "\n\n--- [SYNOPSIS / STUDY DESIGN SECTION] ---\n\n" + synopsis_window
    chunk1 = chunk1[:_WINDOW_SIZE * 2]           # cap at ~28 k chars
    parsed1 = _llm_pass(chunk1, _PASS1_FIELDS, max_tokens=2000)

    # Pass 2: endpoints — skip first _CONTENT_MIN_POS chars to avoid false
    # matches in glossary ("primary outcome measure"), TOC, or changes table.
    chunk2 = _anchor_window(text, _PASS2_ANCHORS, min_pos=_CONTENT_MIN_POS)
    if not chunk2:
        # Fallback: take a window from the middle-third of the document
        mid = max(_CONTENT_MIN_POS, len(text) // 3)
        chunk2 = text[mid:mid + _WINDOW_SIZE]
    parsed2 = _llm_pass(chunk2, _PASS2_FIELDS, max_tokens=2500)

    # Pass 3: eligibility — skip early sections where "inclusion criteria"
    # appears in the summary-of-changes table before the actual criteria text.
    chunk3 = _anchor_window(text, _PASS3_ANCHORS, min_pos=_CONTENT_MIN_POS)
    if not chunk3:
        mid = max(_CONTENT_MIN_POS, len(text) // 3)
        chunk3 = text[mid:mid + _WINDOW_SIZE]
    parsed3 = _llm_pass(chunk3, _PASS3_FIELDS, max_tokens=3000)

    # Pass 4: intervention — skip early sections where "study intervention"
    # appears in the title-page header or "investigational product" in the TOC.
    chunk4 = _anchor_window(text, _PASS4_ANCHORS, min_pos=_CONTENT_MIN_POS)
    if not chunk4:
        mid = max(_CONTENT_MIN_POS, len(text) // 4)
        chunk4 = text[mid:mid + _WINDOW_SIZE]
    parsed4 = _llm_pass(chunk4, ["comparator", "intervention_description"], max_tokens=2000)

    passes_ok = sum(1 for p in (parsed1, parsed2, parsed3, parsed4) if p)
    merged = _merge_llm_results(parsed1, parsed2, parsed3, parsed4)
    return merged, passes_ok


# ── Confidence scoring ─────────────────────────────────────────────────────────

_CONFIDENCE_REQUIRED_FIELDS = [
    "title", "condition", "phase", "study_type", "allocation",
    "primary_endpoints", "target_population", "intervention_description",
]


def _score_confidence(merged: dict) -> str:
    found = sum(1 for f in _CONFIDENCE_REQUIRED_FIELDS if merged.get(f))
    if found >= 7:
        return "high"
    elif found >= 4:
        return "medium"
    return "low"


# ── Build ProtocolMetadata from merged LLM dict ────────────────────────────────

def _build_metadata_from_llm(merged: dict, full_text: str,
                              confidence: str, provenance: ProvenanceRecord) -> ProtocolMetadata:
    """Construct a ProtocolMetadata object from the LLM-extracted dict."""

    def _get(field: str) -> Optional[str]:
        return _normalise_value(merged.get(field))

    # Post-process endpoint_focus: classify from endpoint text if not extracted
    endpoint_focus = _get("endpoint_focus")
    if not endpoint_focus or endpoint_focus.lower() in ("other", "unspecified"):
        endpoint_focus = classify_endpoint_category(
            _get("primary_endpoints") or _get("secondary_endpoints") or ""
        )

    return ProtocolMetadata(
        title                  = _get("title"),
        condition              = _get("condition"),
        sponsor                = _get("sponsor"),
        phase                  = _get("phase"),
        study_type             = _get("study_type"),
        sample_size            = _get("sample_size"),
        arms_count             = _get("arms_count"),
        allocation             = _get("allocation"),
        masking                = _get("masking"),
        intervention_model     = _get("intervention_model"),
        primary_purpose        = _get("primary_purpose"),
        start_date             = _get("start_date"),
        completion_date        = _get("completion_date"),
        geography_focus        = _get("geography_focus"),
        primary_endpoints      = _get("primary_endpoints"),
        secondary_endpoints    = _get("secondary_endpoints"),
        endpoint_focus         = endpoint_focus,
        target_population      = _get("target_population"),
        comparator             = _get("comparator"),
        intervention_description = _get("intervention_description"),
        description            = full_text.strip()[:2000],
        confidence             = confidence,
        provenance             = provenance,
    )


# ── Minimal structural fallback (NO LLM available) ────────────────────────────

def _minimal_heuristic_fallback(text: str) -> ProtocolMetadata:
    """
    Last-resort extraction when no LLM is available.

    This path uses only structural patterns to identify a small set of values
    that can be reliably detected from document structure alone (phase, sample
    size, allocation, masking).  All rich text fields (endpoints, population,
    intervention) are populated from detected section bodies — not parsed by
    regex.  The profile will be incomplete and should be manually reviewed.
    """
    phase_m = re.search(r"\b(phase\s*(?:[ivx]+|\d+(?:[a-b]?)))\b", text, re.IGNORECASE)
    phase = phase_m.group(1).title() if phase_m else None

    size_m = re.search(
        r"(?:sample size|planned enrollment|total enrollment|enroll(?:ment)?|n\s*=)\s*"
        r"[:\=]?\s*(?:approximately\s+)?([0-9,]{2,})\s*(?:subjects?|patients?|participants?)?",
        text, re.IGNORECASE,
    )
    sample_size = size_m.group(1).replace(",", "") if size_m else None

    def _pick(options):
        for pat, label in options:
            if re.search(pat, text, re.IGNORECASE):
                return label
        return None

    study_type = _pick([(r"\binterventional\b", "Interventional"),
                        (r"\bobservational\b", "Observational")])
    allocation = _pick([(r"\bnon[- ]?randomized\b", "Non-Randomized"),
                        (r"\bnon[- ]?randomised\b", "Non-Randomized"),
                        (r"\brandomized\b", "Randomized"),
                        (r"\brandomised\b", "Randomized")])
    masking = _pick([
        (r"\bquadruple\b", "Quadruple"), (r"\btriple\b", "Triple"),
        (r"\bdouble[- ]blind\b", "Double"), (r"\bsingle[- ]blind\b", "Single"),
        (r"\bopen[- ]label\b", "Open Label"),
    ])
    intervention_model = _pick([
        (r"\bparallel\b", "Parallel Assignment"),
        (r"\bcrossover\b", "Crossover Assignment"),
        (r"\bsingle\s+group\b", "Single Group Assignment"),
    ])
    primary_purpose = _pick([
        (r"\btreatment\b", "Treatment"), (r"\bprevention\b", "Prevention"),
        (r"\bdiagnostic\b", "Diagnostic"),
    ])

    # Rich text fields (endpoints, eligibility, intervention) require LLM
    # interpretation — without the LLM these fields are left empty.
    # Do NOT dump raw text windows here: they contain wrong sections (title
    # page, glossary, changes table) and confuse reviewers.
    return ProtocolMetadata(
        phase                    = phase,
        study_type               = study_type,
        sample_size              = sample_size,
        allocation               = allocation,
        masking                  = masking,
        intervention_model       = intervention_model,
        primary_purpose          = primary_purpose,
        primary_endpoints        = None,
        secondary_endpoints      = None,
        target_population        = None,
        intervention_description = None,
        comparator               = None,
        description              = text.strip()[:2000],
        confidence               = "low",
        provenance               = build_provenance_record(
            source="heuristic_fallback",
            tool="structural_heuristics_no_llm",
            notes=(
                "No OpenAI API key is configured — LLM extraction is unavailable. "
                "Only structural fields (phase, allocation, masking) were extracted. "
                "Set OPENAI_API_KEY in the .env file and restart the app to enable "
                "full protocol extraction."
            ),
        ),
    )


# ── Main entry point ───────────────────────────────────────────────────────────

def extract_protocol_metadata_from_text(text: str) -> ProtocolMetadata:
    """
    Extract structured ProtocolMetadata from the full protocol text.

    LLM is the sole extractor of field values.

    Strategy:
    • Short docs (≤ 50 k chars): single comprehensive LLM pass on the full text.
    • Long docs (100-page protocols): four keyword-anchored passes — each pass
      receives a reading window extracted around the ACTUAL location of the
      relevant content (title area, endpoint section, eligibility section,
      intervention section).  No regex section detection is used for routing.
    • Falls back to minimal structural heuristics only when no API key is set.
    """
    if not has_openai_config():
        return _minimal_heuristic_fallback(text)

    is_short = len(text) <= _SINGLE_PASS_MAX_CHARS

    if is_short:
        merged, passes_ok = _extract_single_pass(text)
        strategy = f"single-pass LLM on full text ({len(text):,} chars)"
    else:
        merged, passes_ok = _extract_multi_pass(text)
        strategy = (
            f"four-pass keyword-anchored LLM extraction "
            f"({len(text):,} chars, {passes_ok}/4 passes succeeded)"
        )

    if not merged:
        fallback = _minimal_heuristic_fallback(text)
        fallback.confidence = "low"
        fallback.provenance = build_provenance_record(
            source="heuristic_fallback",
            tool="structural_heuristics_llm_failed",
            notes=f"LLM returned no usable output ({strategy}). "
                  "Keyword-anchored heuristics used. Manual review is essential.",
        )
        return fallback

    confidence = _score_confidence(merged)
    fields_extracted = sum(1 for v in merged.values() if _normalise_value(v))

    provenance = build_provenance_record(
        source="llm_extraction",
        tool=f"protocol_extraction_v4/{configured_model_name() or 'openai'}",
        notes=(
            f"LLM-primary extraction. {strategy}. "
            f"Confidence: {confidence}. "
            f"{fields_extracted} fields extracted."
        ),
    )

    return _build_metadata_from_llm(merged, text, confidence, provenance)


# ── Session helpers ────────────────────────────────────────────────────────────

def protocol_metadata_from_session(payload) -> ProtocolMetadata:
    if isinstance(payload, ProtocolMetadata):
        return payload
    if not payload:
        return ProtocolMetadata()

    provenance_payload = payload.get("provenance") if isinstance(payload, dict) else None
    provenance = None
    if provenance_payload:
        provenance = ProvenanceRecord(
            source=provenance_payload.get("source", "session"),
            tool=provenance_payload.get("tool", "session"),
            timestamp=provenance_payload.get("timestamp", ""),
            model=provenance_payload.get("model"),
            notes=provenance_payload.get("notes"),
            source_sections=provenance_payload.get("source_sections", []),
        )
    metadata = ProtocolMetadata(provenance=provenance)
    metadata.update_from_mapping(payload)
    return metadata


def grounded_assistant_response(
    user_question: str,
    protocol_meta: ProtocolMetadata,
    trial_summary: str,
    comparison_metrics: Optional[dict] = None,
    recommendations: Optional[list] = None,
) -> str:
    fallback = (
        "Current evidence review is limited to the approved protocol profile and the "
        "matched trial summary in this workspace. "
        "Please validate any planning decision with clinical, regulatory, and operational review."
    )
    if not has_openai_config():
        return fallback

    system_prompt = (
        "You are a senior clinical trial planning assistant. "
        "Be truthful, do not fabricate evidence, state uncertainty clearly, "
        "and only use the provided context."
    )
    user_prompt = (
        f"Protocol metadata: {json.dumps(protocol_meta.to_display_dict(), ensure_ascii=True, default=str)}\n"
        f"Comparison summary: {trial_summary}\n"
        f"Comparison metrics: {json.dumps(comparison_metrics or {}, ensure_ascii=True, default=str)}\n"
        f"Recommendations: {json.dumps(recommendations or [], ensure_ascii=True, default=str)}\n"
        f"User question: {user_question}\n\n"
        "Answer concisely. If evidence is incomplete, say so explicitly."
    )
    response = generate_chat_completion(
        system_prompt, user_prompt, temperature=0.2, max_tokens=600
    )
    return response or fallback
