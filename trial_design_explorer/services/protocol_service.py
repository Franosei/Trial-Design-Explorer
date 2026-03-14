import json
import re

from trial_design_explorer.config import PROTOCOL_FIELDS
from trial_design_explorer.domain import ProtocolMetadata, ProvenanceRecord
from trial_design_explorer.services.comparison_service import classify_endpoint_category
from trial_design_explorer.services.audit_service import build_provenance_record
from trial_design_explorer.services.openai_service import generate_chat_completion, has_openai_config


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


def _load_json_payload(raw_text: str) -> dict | None:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _extract_phase(text: str) -> str | None:
    match = re.search(r"(phase\s*(?:[ivx]+|\d+))", text, re.IGNORECASE)
    return match.group(1).title() if match else None


def _extract_sample_size(text: str) -> str | None:
    match = re.search(
        r"(?:sample size|enroll(?:ment)?|n\s*=)\s*[:=]?\s*([0-9,]+(?:\s*(?:-|to)\s*[0-9,]+)?)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return " ".join(match.group(1).replace(",", "").split())


def _extract_arms_count(text: str) -> str | None:
    match = re.search(r"(\d+)\s+(?:study\s+)?arms?\b", text, re.IGNORECASE)
    return match.group(1) if match else None


def _extract_choice(text: str, options: list[tuple[str, str]]) -> str | None:
    for pattern, label in options:
        if re.search(pattern, text, re.IGNORECASE):
            return label
    return None


def _extract_labeled_value(text: str, labels: list[str], width: int = 220) -> str | None:
    for label in labels:
        pattern = rf"{label}\s*[:\-]\s*([^\n\r\.]+)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return " ".join(match.group(1).strip().split())[:width]
    return None


def _extract_section(text: str, headings: list[str], width: int = 420) -> str | None:
    normalized = text.replace("\r", "\n")
    heading_pattern = "|".join(re.escape(heading) for heading in headings)
    match = re.search(
        rf"(?:{heading_pattern})\s*[:\-]?\s*(.+?)(?:\n[A-Z][A-Za-z /()\-]{{3,40}}[:\n]|\n\d+\.\s+[A-Z]|\Z)",
        normalized,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    section_text = " ".join(match.group(1).split())
    return section_text[:width] if section_text else None


def _extract_date(text: str, labels: list[str]) -> str | None:
    month_day_year = r"([A-Z][a-z]+ \d{1,2}, \d{4})"
    month_year = r"([A-Z][a-z]+ \d{4})"
    iso_date = r"(\d{4}-\d{2}-\d{2})"
    for label in labels:
        pattern = rf"{label}\s*[:\-]?\s*(?:{month_day_year}|{month_year}|{iso_date})"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            for group in match.groups():
                if group:
                    return group
    return None


def _heuristic_protocol_metadata(text: str) -> ProtocolMetadata:
    metadata = ProtocolMetadata(
        description=text.strip()[:4000],
        confidence="low",
        provenance=build_provenance_record(
            source="heuristic",
            tool="protocol_metadata_heuristics",
            notes="Fallback extraction from uploaded protocol text.",
        ),
    )
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    if lines:
        metadata.title = lines[0][:160]
    if len(lines) > 1:
        metadata.condition = lines[1][:120]

    lower_text = text.lower()
    metadata.phase = _extract_phase(lower_text)
    metadata.sample_size = _extract_sample_size(text)
    metadata.arms_count = _extract_arms_count(text)
    metadata.study_type = _extract_choice(text, [(r"\binterventional\b", "Interventional"), (r"\bobservational\b", "Observational")])
    metadata.allocation = _extract_choice(
        text,
        [(r"\bnon[- ]?randomized\b", "Non-Randomized"), (r"\brandomized\b", "Randomized")],
    )
    metadata.masking = _extract_choice(
        text,
        [
            (r"\bquadruple\b", "Quadruple"),
            (r"\btriple\b", "Triple"),
            (r"\bdouble(?:[- ]blind)?\b", "Double"),
            (r"\bsingle(?:[- ]blind)?\b", "Single"),
            (r"\bopen[- ]label\b", "Open Label"),
        ],
    )
    metadata.intervention_model = _extract_choice(
        text,
        [
            (r"\bparallel\b", "Parallel Assignment"),
            (r"\bcrossover\b", "Crossover Assignment"),
            (r"\bfactorial\b", "Factorial Assignment"),
            (r"\bsingle group\b", "Single Group Assignment"),
            (r"\bsequential\b", "Sequential Assignment"),
        ],
    )
    metadata.primary_purpose = _extract_choice(
        text,
        [
            (r"\btreatment\b", "Treatment"),
            (r"\bprevention\b", "Prevention"),
            (r"\bdiagnostic\b", "Diagnostic"),
            (r"\bsupportive care\b", "Supportive Care"),
            (r"\bscreening\b", "Screening"),
            (r"\bdevice feasibility\b", "Device Feasibility"),
        ],
    )
    metadata.sponsor = _extract_labeled_value(text, ["sponsor", "lead sponsor"])
    metadata.comparator = _extract_labeled_value(text, ["comparator", "control arm", "control", "comparator arm"])
    metadata.intervention_description = _extract_section(text, ["intervention", "interventions", "study intervention"])
    metadata.target_population = _extract_section(text, ["population", "target population", "eligibility criteria", "study population"])
    metadata.primary_endpoints = metadata.primary_endpoints or _extract_section(
        text, ["primary endpoint", "primary endpoints", "primary outcome", "primary outcomes"]
    )
    metadata.secondary_endpoints = metadata.secondary_endpoints or _extract_section(
        text, ["secondary endpoint", "secondary endpoints", "secondary outcome", "secondary outcomes"]
    )
    metadata.start_date = _extract_date(text, ["start date", "study start", "planned start date"])
    metadata.completion_date = _extract_date(text, ["completion date", "study completion", "primary completion date"])
    metadata.geography_focus = _extract_labeled_value(text, ["location", "locations", "countries", "country"])
    metadata.endpoint_focus = classify_endpoint_category(metadata.primary_endpoints or metadata.secondary_endpoints)
    return metadata


def extract_protocol_metadata_from_text(text: str) -> ProtocolMetadata:
    metadata = _heuristic_protocol_metadata(text)
    if not has_openai_config():
        return metadata

    system_prompt = (
        "You extract structured clinical trial protocol metadata. "
        "Return valid JSON only. Do not invent unavailable fields. "
        "If a value is missing, return null. "
        "Use concise field values, not paragraphs. "
        "For study_type use controlled values like Interventional or Observational. "
        "For allocation use Randomized, Non-Randomized, or null. "
        "For masking use Open Label, Single, Double, Triple, Quadruple, or null. "
        "For primary_purpose use a concise label like Treatment, Prevention, Diagnostic, Supportive Care, Screening, or Device Feasibility."
    )
    user_prompt = (
        "Extract the following fields from the protocol text as JSON with these keys: "
        + ", ".join(PROTOCOL_FIELDS)
        + ".\n\nProtocol text:\n"
        + text[:18000]
    )
    raw_response = generate_chat_completion(system_prompt, user_prompt, temperature=0.0, max_tokens=1200)
    if not raw_response:
        return metadata

    parsed = _load_json_payload(raw_response)
    if not parsed:
        return metadata

    metadata.update_from_mapping(parsed)
    if not metadata.endpoint_focus:
        metadata.endpoint_focus = classify_endpoint_category(metadata.primary_endpoints or metadata.secondary_endpoints)
    metadata.confidence = "medium"
    metadata.provenance = build_provenance_record(
        source="llm_plus_heuristic",
        tool="protocol_metadata_extraction",
        notes="Structured extraction from uploaded protocol text with model assistance.",
        source_sections=["protocol text upload"],
    )
    return metadata


def grounded_assistant_response(
    user_question: str,
    protocol_meta: ProtocolMetadata,
    trial_summary: str,
    comparison_metrics: dict | None = None,
    recommendations: list[dict] | None = None,
) -> str:
    fallback = (
        "Current evidence review is limited to the approved protocol profile and the matched trial summary in this workspace. "
        "Please validate any planning decision with clinical, regulatory, and operational review."
    )

    if not has_openai_config():
        return fallback

    system_prompt = (
        "You are a senior clinical trial planning assistant. "
        "Be truthful, do not fabricate evidence, state uncertainty clearly, and only use the provided context."
    )
    user_prompt = (
        f"Protocol metadata: {json.dumps(protocol_meta.to_display_dict(), ensure_ascii=True, default=str)}\n"
        f"Comparison summary: {trial_summary}\n"
        f"Comparison metrics: {json.dumps(comparison_metrics or {}, ensure_ascii=True, default=str)}\n"
        f"Recommendations: {json.dumps(recommendations or [], ensure_ascii=True, default=str)}\n"
        f"User question: {user_question}\n\n"
        "Answer concisely. If evidence is incomplete, say so explicitly."
    )
    response = generate_chat_completion(system_prompt, user_prompt, temperature=0.2, max_tokens=450)
    return response or fallback
