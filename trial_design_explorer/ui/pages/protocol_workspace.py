import pandas as pd
import streamlit as st

from trial_design_explorer.config import DEFAULT_CONDITION, DEFAULT_REPORT_FILE, DEFAULT_SLIDES_FILE
from trial_design_explorer.services.openai_service import has_openai_config
from trial_design_explorer.services import (
    articles_to_evidence_rows,
    build_audit_event,
    build_cohort_definition_table,
    build_comparison_result,
    build_protocol_comparison_metrics,
    build_protocol_recommendations,
    compare_protocol_to_trials,
    extract_protocol_metadata_from_text,
    extract_text_from_uploaded_file,
    fetch_trials_by_condition,
    generate_protocol_report_pdf,
    generate_slides_pptx,
    grounded_assistant_response,
    parse_trials_to_df,
    protocol_metadata_from_session,
    search_pubmed_evidence,
)
from trial_design_explorer.services.clinical_trials_service import (
    build_design_similar_cohort,
    cohort_selection_summary,
)
from trial_design_explorer.services.audit_service import current_utc_timestamp
from trial_design_explorer.ui.panels.protocol_benchmarks import render_protocol_benchmark_panel


PROTOCOL_STAGES = ["Intake", "Review", "Analysis", "Report"]
STUDY_TYPE_OPTIONS = ["", "Interventional", "Observational", "Expanded Access"]
ALLOCATION_OPTIONS = ["", "Randomized", "Non-Randomized"]
MASKING_OPTIONS = ["", "Open Label", "Single", "Double", "Triple", "Quadruple"]
INTERVENTION_MODEL_OPTIONS = [
    "",
    "Parallel Assignment",
    "Crossover Assignment",
    "Factorial Assignment",
    "Single Group Assignment",
    "Sequential Assignment",
]
PRIMARY_PURPOSE_OPTIONS = [
    "",
    "Treatment",
    "Prevention",
    "Diagnostic",
    "Supportive Care",
    "Screening",
    "Device Feasibility",
    "Basic Science",
    "Health Services Research",
]
ENDPOINT_FOCUS_OPTIONS = ["", "Efficacy", "Safety", "Patient Reported", "Biomarker", "Utilization", "Operational", "Other"]


def _reset_protocol_downstream_state():
    st.session_state["matching_trials"] = None
    st.session_state["latest_comparison"] = ""
    st.session_state["comparison_metrics"] = {}
    st.session_state["comparison_recommendations"] = []
    st.session_state["chat_history"] = []
    st.session_state["pubmed_articles"] = []


def _set_protocol_stage(stage: str) -> None:
    st.session_state["protocol_stage"] = stage


def _provenance_payload(protocol_meta):
    provenance = protocol_meta.provenance
    if not provenance:
        return {}
    if isinstance(provenance, dict):
        return {key: str(value) for key, value in provenance.items()}
    if hasattr(provenance, "to_dict"):
        return {key: str(value) for key, value in provenance.to_dict().items()}
    return {"value": str(provenance)}


def _safe_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe
    safe_df = dataframe.copy()
    for column in safe_df.columns:
        safe_df[column] = safe_df[column].apply(_safe_display_value)
    return safe_df


def _safe_display_value(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return str(value)


def _build_comparable_cohort(protocol_meta):
    compare_label = protocol_meta.condition or DEFAULT_CONDITION
    response = fetch_trials_by_condition(compare_label)
    all_trials_df = parse_trials_to_df(response) if response else pd.DataFrame()

    # ── Step 1: Design similarity filtering ───────────────────────────────────
    # Select trials that are design-comparable to the protocol.
    # Sponsor is NOT used as a selection criterion — only design dimensions.
    trials_df = build_design_similar_cohort(protocol_meta, all_trials_df)
    selection_info = cohort_selection_summary(protocol_meta, all_trials_df, trials_df)

    # ── Step 2: Build typed ComparisonResult ──────────────────────────────────
    result = build_comparison_result(protocol_meta, trials_df)
    comparison_metrics = result.to_metrics_dict()
    comparison_recommendations = result.to_recommendations_list()
    comparison_notes = compare_protocol_to_trials(protocol_meta, trials_df)

    st.session_state["matching_trials"] = trials_df
    st.session_state["all_condition_trials"] = all_trials_df   # keep full pool for reference
    st.session_state["cohort_selection_info"] = selection_info
    st.session_state["comparison_result"] = result.to_dict()
    st.session_state["comparison_metrics"] = comparison_metrics
    st.session_state["comparison_recommendations"] = comparison_recommendations
    st.session_state["latest_comparison"] = comparison_notes
    st.session_state["audit_log"].append(
        build_audit_event(
            "build_design_similar_cohort",
            (
                f"Fetched {selection_info.get('condition_matched_total', 0)} condition-matched trials for '{compare_label}'.  "
                f"Design similarity filter selected {selection_info.get('design_similar_selected', 0)} trials "
                f"({selection_info.get('selection_rate_pct', 0)}% of pool).  "
                f"Dimensions used: {', '.join(selection_info.get('design_dimensions_used', []))}.  "
                f"Sponsor NOT used for selection."
            ),
            artifact_type="comparison_cohort",
            metadata={
                "condition": compare_label,
                "condition_matched_total": selection_info.get("condition_matched_total", 0),
                "design_similar_selected": selection_info.get("design_similar_selected", 0),
                "similarity_score_median": selection_info.get("similarity_score_median"),
                "sponsor_used_for_selection": False,
                "completed": result.cohort.completed_count,
                "disrupted": result.cohort.disrupted_count,
                "evidence_strength": result.cohort.evidence_strength,
                "posture": result.precedent_posture,
            },
        )
    )


def _fetch_pubmed_evidence(protocol_meta):
    """Fetch PubMed articles for the protocol's condition and endpoint focus."""
    condition = protocol_meta.condition or DEFAULT_CONDITION
    endpoint_focus = protocol_meta.endpoint_focus or None
    articles = search_pubmed_evidence(
        condition=condition,
        endpoint_focus=endpoint_focus,
        max_results=8,
    )
    st.session_state["pubmed_articles"] = [a.to_dict() for a in articles]
    st.session_state["audit_log"].append(
        build_audit_event(
            "fetch_pubmed_evidence",
            f"Retrieved {len(articles)} PubMed articles for '{condition}'.",
            artifact_type="literature_evidence",
            artifact_id=condition,
            metadata={"article_count": len(articles), "endpoint_focus": endpoint_focus or "any"},
        )
    )
    return articles


_PROFILE_FIELDS = [
    ("title",                  "Title"),
    ("condition",              "Condition"),
    ("sponsor",                "Sponsor"),
    ("phase",                  "Phase"),
    ("study_type",             "Study Type"),
    ("allocation",             "Allocation"),
    ("masking",                "Masking"),
    ("intervention_model",     "Intervention Model"),
    ("primary_purpose",        "Primary Purpose"),
    ("sample_size",            "Sample Size"),
    ("arms_count",             "Arms Count"),
    ("primary_endpoints",      "Primary Endpoints"),
    ("secondary_endpoints",    "Secondary Endpoints"),
    ("target_population",      "Target Population"),
    ("intervention_description","Intervention"),
    ("comparator",             "Comparator"),
    ("start_date",             "Start Date"),
    ("completion_date",        "Completion Date"),
]

_EMPTY_VALUES = {"", "null", "n/a", "not provided", "not specified", "none", "unknown"}


def _completeness(protocol_meta) -> tuple[int, int, list[str]]:
    """Return (found_count, total_count, list_of_missing_labels)."""
    found, missing = 0, []
    for attr, label in _PROFILE_FIELDS:
        val = getattr(protocol_meta, attr, None)
        if val and str(val).strip().lower() not in _EMPTY_VALUES:
            found += 1
        else:
            missing.append(label)
    return found, len(_PROFILE_FIELDS), missing


def _render_protocol_profile_card(protocol_meta) -> None:
    """
    Rich, structured protocol profile display.

    Shows a clinical summary with: title banner + confidence badge,
    4-column design grid, primary endpoints as bullets, population and
    intervention blocks, and a completeness/missing-fields indicator.
    """
    found, total, missing = _completeness(protocol_meta)
    completeness_pct = round(found / total * 100)
    conf = (getattr(protocol_meta, "confidence", None) or "low").lower()

    # ── Title banner ───────────────────────────────────────────────────────────
    with st.container(border=True):
        title_col, badge_col = st.columns([3, 1])
        with title_col:
            title_text = protocol_meta.title or "*Protocol title not extracted*"
            st.markdown(f"### {title_text}")
            tags = []
            if protocol_meta.condition:
                tags.append(f"**Condition:** {protocol_meta.condition}")
            if protocol_meta.phase:
                tags.append(f"**Phase:** {protocol_meta.phase}")
            if protocol_meta.study_type:
                tags.append(f"**{protocol_meta.study_type}**")
            if protocol_meta.allocation:
                tags.append(f"**{protocol_meta.allocation}**")
            if protocol_meta.masking:
                tags.append(f"**{protocol_meta.masking} blind**")
            if tags:
                st.markdown("  ·  ".join(tags))
            if protocol_meta.sponsor:
                st.caption(f"Sponsor: {protocol_meta.sponsor}")
        with badge_col:
            st.metric("Profile completeness", f"{completeness_pct}%",
                      f"{found} of {total} fields")
            _conf_labels = {"high": ":green[High confidence]",
                            "medium": ":orange[Medium confidence]",
                            "low": ":red[Low confidence]"}
            st.caption(f"Extraction: {_conf_labels.get(conf, conf)}")

    # ── Design architecture grid ───────────────────────────────────────────────
    g1, g2, g3, g4 = st.columns(4)
    with g1:
        st.markdown("**Study Structure**")
        st.caption(f"Phase: {protocol_meta.phase or '—'}")
        st.caption(f"Study type: {protocol_meta.study_type or '—'}")
        st.caption(f"Allocation: {protocol_meta.allocation or '—'}")
        st.caption(f"Masking: {protocol_meta.masking or '—'}")
        st.caption(f"Model: {protocol_meta.intervention_model or '—'}")
    with g2:
        st.markdown("**Enrollment & Arms**")
        st.caption(f"Planned N: {protocol_meta.sample_size or '—'}")
        st.caption(f"Arms: {protocol_meta.arms_count or '—'}")
        st.caption(f"Primary purpose: {protocol_meta.primary_purpose or '—'}")
        st.caption(f"Endpoint focus: {protocol_meta.endpoint_focus or '—'}")
    with g3:
        st.markdown("**Timeline & Geography**")
        st.caption(f"Start date: {protocol_meta.start_date or '—'}")
        st.caption(f"Completion: {protocol_meta.completion_date or '—'}")
        st.caption(f"Geography: {protocol_meta.geography_focus or '—'}")
    with g4:
        st.markdown("**Missing Fields**")
        if missing:
            for label in missing[:6]:
                st.caption(f"⚠ {label}")
            if len(missing) > 6:
                st.caption(f"...and {len(missing) - 6} more")
        else:
            st.caption(":green[All fields extracted]")

    # ── Endpoint strategy ──────────────────────────────────────────────────────
    ep_val = protocol_meta.primary_endpoints
    if ep_val and str(ep_val).strip().lower() not in _EMPTY_VALUES:
        st.markdown("**Primary Endpoints**")
        if isinstance(ep_val, list):
            lines = [str(e).strip() for e in ep_val if str(e).strip()]
        else:
            lines = [ln.strip().lstrip("•·-–*").strip()
                     for ln in str(ep_val).splitlines()
                     if ln.strip().lstrip("•·-–*").strip()]
        for line in lines[:10]:
            st.markdown(f"- {line}")

    sec_val = protocol_meta.secondary_endpoints
    if sec_val and str(sec_val).strip().lower() not in _EMPTY_VALUES:
        with st.expander("Secondary endpoints", expanded=False):
            if isinstance(sec_val, list):
                for ep in sec_val:
                    st.markdown(f"- {ep}")
            else:
                for ln in str(sec_val).splitlines():
                    ln = ln.strip().lstrip("•·-–*").strip()
                    if ln:
                        st.markdown(f"- {ln}")

    # ── Population + Intervention columns ─────────────────────────────────────
    pop_col, iv_col = st.columns(2)
    with pop_col:
        pop_val = protocol_meta.target_population
        if pop_val and str(pop_val).strip().lower() not in _EMPTY_VALUES:
            st.markdown("**Target Population & Eligibility Criteria**")
            st.write(str(pop_val)[:800])
        else:
            st.caption(":red[Target population not extracted]")
    with iv_col:
        iv_val = protocol_meta.intervention_description
        comp_val = protocol_meta.comparator
        if (iv_val and str(iv_val).strip().lower() not in _EMPTY_VALUES) or \
           (comp_val and str(comp_val).strip().lower() not in _EMPTY_VALUES):
            st.markdown("**Intervention & Comparator**")
            if iv_val and str(iv_val).strip().lower() not in _EMPTY_VALUES:
                st.write(str(iv_val)[:500])
            if comp_val and str(comp_val).strip().lower() not in _EMPTY_VALUES:
                st.markdown(f"**Comparator / Control arm:** {comp_val}")
        else:
            st.caption(":red[Intervention details not extracted]")


def _select_index(options: list[str], value: str | None) -> int:
    if value in options:
        return options.index(value)
    return 0


def _render_stage_selector() -> str:
    selected_stage = st.segmented_control(
        "Protocol workflow stage",
        PROTOCOL_STAGES,
        default=st.session_state.get("protocol_stage", "Intake"),
        selection_mode="single",
        width="stretch",
        label_visibility="collapsed",
    )
    if selected_stage and selected_stage != st.session_state.get("protocol_stage"):
        st.session_state["protocol_stage"] = selected_stage
        st.rerun()
    return st.session_state.get("protocol_stage", "Intake")


def render_protocol_sidebar():
    protocol_payload = st.session_state.get("protocol_meta")
    protocol_meta = protocol_metadata_from_session(protocol_payload) if protocol_payload else None
    matching_trials = st.session_state.get("matching_trials")
    stage = st.radio(
        "Workflow stage",
        PROTOCOL_STAGES,
        index=PROTOCOL_STAGES.index(st.session_state.get("protocol_stage", "Intake")),
    )
    if stage != st.session_state.get("protocol_stage"):
        st.session_state["protocol_stage"] = stage
        st.rerun()

    st.markdown("---")
    st.markdown("### Project Status")
    st.caption(f"Document: {'Loaded' if st.session_state.get('protocol_text') else 'Not loaded'}")
    st.caption(f"Profile: {protocol_meta.confirmation_status.title() if protocol_meta else 'Not started'}")
    st.caption(f"Cohort size: {len(matching_trials) if matching_trials is not None else 0}")
    st.caption(f"Recommendations: {len(st.session_state.get('comparison_recommendations', []))}")
    st.caption(f"PubMed articles: {len(st.session_state.get('pubmed_articles', []))}")
    if protocol_meta and protocol_meta.condition:
        st.caption(f"Condition: {protocol_meta.condition}")


def render_protocol_workspace():
    protocol_payload = st.session_state.get("protocol_meta")
    protocol_meta = protocol_metadata_from_session(protocol_payload) if protocol_payload else None
    matching_trials = st.session_state.get("matching_trials")

    st.markdown("### Protocol Review Workspace")
    stage = _render_stage_selector()

    headline_col1, headline_col2, headline_col3, headline_col4 = st.columns([1, 1, 1, 2])
    headline_col1.metric("Profile Status", protocol_meta.confirmation_status.title() if protocol_meta else "Not started")
    headline_col2.metric("Comparable Studies", len(matching_trials) if matching_trials is not None else 0)
    headline_col3.metric("PubMed Articles", len(st.session_state.get("pubmed_articles", [])))
    headline_col4.caption(
        "Document intake → structured review → registry benchmarking → literature evidence → report export."
    )

    if stage == "Intake":
        _render_intake_stage()
    elif stage == "Review":
        _render_review_stage()
    elif stage == "Analysis":
        _render_analysis_stage()
    else:
        _render_report_stage()


def _render_intake_stage():
    st.markdown("#### Step 1: Document Intake")
    st.caption("Upload the current protocol or synopsis and generate the initial structured profile.")

    # ── LLM configuration check ───────────────────────────────────────────────
    if not has_openai_config():
        st.error(
            "**OpenAI API key not configured.** "
            "Protocol extraction requires an LLM — without it only Phase, Allocation, "
            "and Masking can be detected.  "
            "Add your key to the `.env` file in the project root:\n\n"
            "```\nOPENAI_API_KEY=sk-...\n```\n\n"
            "Then restart the app (`streamlit run app.py`)."
        )
        return

    left_col, right_col = st.columns([1.7, 1])
    with left_col:
        uploaded_file = st.file_uploader(
            "Upload protocol or study document",
            type=["txt", "pdf", "docx", "rtf"],
            help="Supported inputs: TXT, PDF, DOCX, and RTF.",
        )
        if uploaded_file:
            raw_text = extract_text_from_uploaded_file(uploaded_file)
            if not raw_text.strip():
                st.warning("No text could be extracted from the uploaded file.")
            else:
                st.session_state["protocol_text"] = raw_text
                st.text_area("Document preview", raw_text[:5000], height=320)
                if st.button("Generate structured protocol profile", type="primary", width="stretch"):
                    extracted_meta = extract_protocol_metadata_from_text(raw_text)
                    st.session_state["protocol_meta"] = extracted_meta.to_dict()
                    _reset_protocol_downstream_state()
                    st.session_state["audit_log"].append(
                        build_audit_event(
                            "extract_protocol_profile",
                            f"Extracted protocol profile from {uploaded_file.name}.",
                            artifact_type="document",
                            artifact_id=uploaded_file.name,
                        )
                    )
                    _set_protocol_stage("Review")
                    st.rerun()

    with right_col:
        st.markdown("##### Intake Guidance")
        st.caption("Use the most current protocol or synopsis available. The extracted profile is a draft — review before running any analysis.")
        if st.session_state.get("protocol_meta"):
            st.markdown("---")
            st.markdown("##### Extracted Protocol Profile")
            protocol_meta = protocol_metadata_from_session(st.session_state["protocol_meta"])
            _render_protocol_profile_card(protocol_meta)


def _render_review_stage():
    st.markdown("#### Step 2: Review and Confirm Protocol Profile")
    if not st.session_state.get("protocol_meta"):
        st.info("Start with Step 1 to generate the initial protocol profile.")
        return

    protocol_meta = protocol_metadata_from_session(st.session_state["protocol_meta"])

    # ── Rich profile card (primary display) ───────────────────────────────────
    _render_protocol_profile_card(protocol_meta)

    # ── Completeness guidance ─────────────────────────────────────────────────
    found, total, missing = _completeness(protocol_meta)
    if missing:
        st.warning(
            f"**{len(missing)} field(s) need attention** before running analysis: "
            + ", ".join(missing[:8])
            + ("..." if len(missing) > 8 else "")
            + ".  Use the edit form below to fill them in."
        )
    else:
        st.success("Profile is complete. Confirm and proceed to analysis.")

    st.markdown("---")

    # ── Edit form in expander ─────────────────────────────────────────────────
    with st.expander("Edit / correct extracted fields", expanded=(found < total * 0.8)):
        st.caption(
            "All fields were extracted automatically. Correct any errors before saving. "
            "Fields with free text (endpoints, population) should be reviewed with particular care."
        )
        with st.form("protocol_review_form"):
            # Row 1: Identity + Design
            identity_col, design_col = st.columns(2)
            with identity_col:
                st.markdown("##### Study Identity")
                title = st.text_area("Protocol title", value=protocol_meta.title or "", height=90)
                condition = st.text_input("Condition / indication", value=protocol_meta.condition or "")
                sponsor = st.text_input("Sponsor", value=protocol_meta.sponsor or "")
                phase = st.text_input("Phase (e.g. Phase 3)", value=protocol_meta.phase or "")
                study_type = st.selectbox(
                    "Study type", STUDY_TYPE_OPTIONS,
                    index=_select_index(STUDY_TYPE_OPTIONS, protocol_meta.study_type),
                )
                sample_size = st.text_input("Planned enrollment (N)", value=protocol_meta.sample_size or "")
                arms_count = st.text_input("Number of arms", value=protocol_meta.arms_count or "")
                start_date = st.text_input("Planned start date", value=protocol_meta.start_date or "")
                completion_date = st.text_input("Planned completion date", value=protocol_meta.completion_date or "")
                geography_focus = st.text_input("Geography / countries", value=protocol_meta.geography_focus or "")

            with design_col:
                st.markdown("##### Design Architecture")
                allocation = st.selectbox(
                    "Allocation", ALLOCATION_OPTIONS,
                    index=_select_index(ALLOCATION_OPTIONS, protocol_meta.allocation),
                    help="Randomized = RCT; Non-Randomized = single-arm or observational.",
                )
                masking = st.selectbox(
                    "Masking / blinding", MASKING_OPTIONS,
                    index=_select_index(MASKING_OPTIONS, protocol_meta.masking),
                )
                intervention_model = st.selectbox(
                    "Intervention model", INTERVENTION_MODEL_OPTIONS,
                    index=_select_index(INTERVENTION_MODEL_OPTIONS, protocol_meta.intervention_model),
                )
                primary_purpose = st.selectbox(
                    "Primary purpose", PRIMARY_PURPOSE_OPTIONS,
                    index=_select_index(PRIMARY_PURPOSE_OPTIONS, protocol_meta.primary_purpose),
                )
                comparator = st.text_input(
                    "Comparator / control arm",
                    value=protocol_meta.comparator or "",
                    help="e.g. Placebo, Active comparator (SOC), Single-arm (none).",
                )
                st.markdown("##### Intervention & Population")
                intervention_description = st.text_area(
                    "Intervention description",
                    value=protocol_meta.intervention_description or "",
                    height=110,
                    help="Include drug name, class, dose, route, and schedule if available.",
                )
                target_population = st.text_area(
                    "Target population & eligibility criteria",
                    value=protocol_meta.target_population or "",
                    height=130,
                    help="Copy the inclusion/exclusion summary verbatim from the protocol.",
                )

            # Row 2: Endpoints
            st.markdown("##### Endpoint Strategy")
            ep_col1, ep_col2 = st.columns([1, 1])
            with ep_col1:
                endpoint_focus = st.selectbox(
                    "Endpoint focus category", ENDPOINT_FOCUS_OPTIONS,
                    index=_select_index(ENDPOINT_FOCUS_OPTIONS, protocol_meta.endpoint_focus),
                )
                primary_endpoints = st.text_area(
                    "Primary endpoints",
                    value=protocol_meta.primary_endpoints or "",
                    height=160,
                    help="Copy verbatim from the protocol — e.g. 'Progression-Free Survival at 12 months (RECIST 1.1)'.",
                )
            with ep_col2:
                secondary_endpoints = st.text_area(
                    "Secondary endpoints",
                    value=protocol_meta.secondary_endpoints or "",
                    height=200,
                )

            save_review = st.form_submit_button(
                "Save and confirm profile", type="primary", width="stretch"
            )

        if save_review:
            protocol_meta.title                = title or None
            protocol_meta.condition            = condition or None
            protocol_meta.sponsor              = sponsor or None
            protocol_meta.study_type           = study_type or None
            protocol_meta.phase                = phase or None
            protocol_meta.sample_size          = sample_size or None
            protocol_meta.arms_count           = arms_count or None
            protocol_meta.start_date           = start_date or None
            protocol_meta.completion_date      = completion_date or None
            protocol_meta.allocation           = allocation or None
            protocol_meta.masking              = masking or None
            protocol_meta.intervention_model   = intervention_model or None
            protocol_meta.primary_purpose      = primary_purpose or None
            protocol_meta.comparator           = comparator or None
            protocol_meta.geography_focus      = geography_focus or None
            protocol_meta.target_population    = target_population or None
            protocol_meta.intervention_description = intervention_description or None
            protocol_meta.endpoint_focus       = endpoint_focus or None
            protocol_meta.primary_endpoints    = primary_endpoints or None
            protocol_meta.secondary_endpoints  = secondary_endpoints or None
            protocol_meta.confirmation_status  = "reviewed"
            st.session_state["protocol_meta"] = protocol_meta.to_dict()
            if st.session_state.get("matching_trials") is not None:
                _build_comparable_cohort(protocol_meta)
            st.session_state["audit_log"].append(
                build_audit_event(
                    "review_protocol_profile",
                    "Reviewer confirmed and saved protocol profile fields.",
                    actor="user",
                    artifact_type="protocol_profile",
                )
            )
            _set_protocol_stage("Analysis")
            st.rerun()

    # ── Provenance ─────────────────────────────────────────────────────────────
    with st.expander("Extraction provenance and traceability"):
        prov = _provenance_payload(protocol_meta)
        if prov:
            for k, v in prov.items():
                st.caption(f"**{k}:** {v}")
        else:
            st.caption("No provenance data available.")


# ─────────────────────────────────────────────────────────────────────────────
# Analysis stage helpers
# ─────────────────────────────────────────────────────────────────────────────

_PRIORITY_ICON  = {"High": "🔴", "Medium": "🟠", "Monitor": "🔵", "Preserve": "🟢"}
_STATUS_ICON_MAP = {
    "COMPLETED": "✅", "TERMINATED": "🔴", "SUSPENDED": "🔴", "WITHDRAWN": "🔴",
    "RECRUITING": "🟢", "NOT_YET_RECRUITING": "🟡", "ACTIVE_NOT_RECRUITING": "🟡",
    "ENROLLING_BY_INVITATION": "🟢",
}


def _status_badge(raw: str) -> str:
    norm = str(raw).strip().upper().replace(" ", "_")
    icon = _STATUS_ICON_MAP.get(norm, "⚪")
    return f"{icon} {str(raw).replace('_', ' ').title()}"


def _fmt(v, suffix="", fallback="—") -> str:
    if v is None or (isinstance(v, float) and v != v):  # NaN check
        return fallback
    try:
        if isinstance(v, float) and v == int(v):
            return f"{int(v):,}{suffix}"
        if isinstance(v, (int, float)):
            return f"{v:,.1f}{suffix}"
    except Exception:
        pass
    return f"{v}{suffix}"


def _render_landscape_brief(protocol_meta, m: dict, sel: dict) -> None:
    """Top-level trial landscape brief — orients the planner immediately."""
    cond      = m.get("condition") or protocol_meta.condition or DEFAULT_CONDITION
    total_n   = m.get("cohort_size", 0)
    completed = m.get("completed_cohort_size", 0)
    disrupted = m.get("disrupted_cohort_size", 0)
    active    = m.get("active_cohort_size", 0)
    ev_str    = m.get("evidence_strength", "Limited")
    posture   = m.get("precedent_posture", "")
    comp_fit  = m.get("completed_design_fit_pct")
    dis_fit   = m.get("disrupted_design_fit_pct")
    gap       = m.get("precedent_gap_pct")

    # Protocol snapshot tags
    proto_tags = [x for x in [
        protocol_meta.phase, protocol_meta.study_type,
        protocol_meta.allocation, protocol_meta.masking,
    ] if x]
    if proto_tags:
        st.caption("Protocol under review: " + "  ·  ".join(f"**{t}**" for t in proto_tags))

    # Six headline metrics
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Matched Trials", total_n,
              help="Trials from ClinicalTrials.gov matched by indication and design similarity")
    c2.metric("Completed", completed,
              help="Reached primary completion — your positive precedent class")
    c3.metric("Terminated / Disrupted", disrupted,
              help="Terminated, suspended, or withdrawn — your risk reference class")
    c4.metric("Active / Recruiting", active,
              help="Currently enrolling — competitive landscape pressure")
    ev_color = {"Strong": ":green", "Moderate": ":orange", "Limited": ":red"}.get(ev_str, "")
    c5.metric("Evidence Strength", ev_str,
              help="Strong = 100+ trials, 25+ completed, 8+ disrupted; Moderate = 40+/10+/4+")
    if comp_fit is not None and dis_fit is not None:
        if "completed" in posture.lower():
            c6.metric("Design Posture", "Completed-led",
                      f"+{gap}% vs disrupted" if gap is not None else None,
                      help="Your design choices are more common in completed than in disrupted trials")
        elif "disrupted" in posture.lower():
            c6.metric("Design Posture", "Risk-led",
                      f"{gap}% vs disrupted" if gap is not None else None,
                      delta_color="inverse",
                      help="Your design choices are more common in disrupted than in completed trials")
        else:
            c6.metric("Design Posture", "Mixed signal",
                      f"{gap}% gap" if gap is not None else None)

    # Landscape completion rate narrative
    if total_n > 0:
        comp_rate = round(completed / total_n * 100, 1)
        dis_rate  = round(disrupted / total_n * 100, 1)
        if comp_rate >= 55:
            st.success(
                f"**{comp_rate}% of comparable {cond} trials completed successfully** "
                f"({completed} of {total_n}).  "
                f"Disruption rate: {dis_rate}%.  This is a relatively proven trial landscape."
            )
        elif dis_rate >= 35:
            st.error(
                f"**{dis_rate}% of comparable {cond} trials were terminated or disrupted** "
                f"({disrupted} of {total_n}).  "
                f"Completion rate: only {comp_rate}%.  "
                f"Design defensibility is critical in this high-risk landscape."
            )
        else:
            st.warning(
                f"**Mixed landscape:** {comp_rate}% completed, {dis_rate}% terminated "
                f"({total_n} comparable trials).  "
                f"This indication carries moderate historical completion risk."
            )

    # Design alignment progress bars
    if comp_fit is not None and dis_fit is not None:
        bar1, bar2 = st.columns(2)
        with bar1:
            st.progress(
                min(comp_fit / 100, 1.0),
                text=f"Your design matches **{comp_fit}%** of completed trial designs",
            )
        with bar2:
            st.progress(
                min(dis_fit / 100, 1.0),
                text=f"Your design matches **{dis_fit}%** of disrupted trial designs",
            )
        if gap is not None:
            if gap >= 15:
                st.success(
                    f"**+{gap}% differentiation advantage.** "
                    f"Your design is substantially more common in completed than in disrupted trials. "
                    f"This is a positive design signal."
                )
            elif gap <= -10:
                st.error(
                    f"**{gap}% risk alignment.** "
                    f"Your design choices are more closely associated with disrupted trials than completed ones. "
                    f"Review the domain findings below."
                )
            else:
                st.info(
                    f"**{gap}% gap between completed and disrupted precedent fit.** "
                    f"Your design does not clearly differentiate from either group — "
                    f"focus on the domain-level findings below."
                )


def _render_domain_intelligence(protocol_meta, m: dict) -> None:
    """Tabbed domain intelligence cards — one tab per PICO domain."""
    st.markdown("#### Domain-Level Design Intelligence")
    st.caption(
        "Each tab shows how your design choice for that domain compares against completed and "
        "terminated trials.  A choice that is more common in completed trials is a positive signal; "
        "more common in terminated trials is a risk flag."
    )

    domains = m.get("alignment_by_domain", [])
    if not domains:
        st.info("Run the analysis to generate domain intelligence.")
        return

    tabs = st.tabs([row["Domain"] for row in domains])
    for tab, row in zip(tabs, domains):
        with tab:
            choice    = row.get("Protocol Choice", "Not provided")
            comp_pct  = row.get("Completed Match (%)")
            dis_pct   = row.get("Disrupted Match (%)")
            overall   = row.get("Overall Match (%)")
            gap       = row.get("Net Gap (%)")
            why       = row.get("Why It Matters", "")

            left, mid, right = st.columns([2, 1, 1])
            with left:
                is_missing = choice in ("Not provided", "Unspecified", "N/A", "")
                if is_missing:
                    st.error(f"**Not specified** — this field is missing from your protocol.")
                    st.caption(
                        "Without this value the benchmark for this domain is estimated from the cohort average. "
                        "Specify it in the Review stage to improve accuracy."
                    )
                else:
                    st.markdown(f"**Your protocol choice:** `{choice}`")
                st.caption(why)

            with mid:
                if comp_pct is not None:
                    st.metric(
                        "In completed trials",
                        f"{comp_pct}%",
                        help="Percentage of successfully completed comparable trials that share this design choice",
                    )
                if dis_pct is not None:
                    st.metric(
                        "In disrupted trials",
                        f"{dis_pct}%",
                        help="Percentage of terminated/disrupted trials that share this design choice",
                    )

            with right:
                if gap is not None:
                    if gap >= 15:
                        st.success(
                            f"**+{gap}% advantage**\n\n"
                            f"More common in completed trials.  Strong positive precedent."
                        )
                    elif gap <= -10:
                        st.error(
                            f"**{gap}% risk signal**\n\n"
                            f"More common in disrupted trials.  Review this design choice."
                        )
                    else:
                        st.warning(
                            f"**{gap}% neutral gap**\n\n"
                            f"Similar prevalence in both groups.  No strong differentiation signal."
                        )
                elif overall is not None:
                    st.metric("Overall field prevalence", f"{overall}%")


def _render_benchmarks(protocol_meta, m: dict) -> None:
    """Enrollment and duration benchmarks with clear protocol target comparison."""
    st.markdown("#### Enrollment & Duration Benchmarks")
    st.caption(
        "Compares your protocol targets against the IQR of completed and terminated comparator trials. "
        "Targets outside the completed-trial range carry higher feasibility risk."
    )

    b1, b2 = st.columns(2)

    with b1:
        st.markdown("**Enrollment Size Benchmark**")
        target   = m.get("enrollment_target")
        c_med    = m.get("completed_enrollment_median")
        c_p25    = m.get("completed_enrollment_p25")
        c_p75    = m.get("completed_enrollment_p75")
        d_med    = m.get("disrupted_enrollment_median")
        d_p25    = m.get("disrupted_enrollment_p25")
        d_p75    = m.get("disrupted_enrollment_p75")
        pct_rank = m.get("enrollment_percentile")

        r1, r2, r3 = st.columns(3)
        r1.metric("Your Target (N)",
                  _fmt(target) if target else "Not set",
                  help="Planned enrollment from your protocol")
        r2.metric("Completed Trials",
                  _fmt(c_med),
                  f"IQR {_fmt(c_p25)}–{_fmt(c_p75)}" if c_p25 and c_p75 else None,
                  help="Median enrollment of completed comparable trials")
        r3.metric("Disrupted Trials",
                  _fmt(d_med),
                  f"IQR {_fmt(d_p25)}–{_fmt(d_p75)}" if d_p25 and d_p75 else None,
                  help="Median enrollment of terminated comparable trials")

        if target and c_med:
            if c_p75 and target > c_p75:
                st.error(
                    f"Your target ({_fmt(target)}) exceeds the upper quartile of completed trials "
                    f"({_fmt(c_p75)}).  Enrollment ambition is above historical norms — "
                    f"validate site capacity and eligibility criteria width."
                )
            elif c_p25 and target < c_p25:
                st.warning(
                    f"Your target ({_fmt(target)}) is below the lower quartile of completed trials "
                    f"({_fmt(c_p25)}).  Ensure statistical power is preserved at this enrollment level."
                )
            else:
                st.success(
                    f"Your target ({_fmt(target)}) is within the completed-trial benchmark range "
                    f"({_fmt(c_p25)}–{_fmt(c_p75)}).  Enrollment ambition is consistent with precedent."
                )
            if pct_rank is not None:
                st.caption(
                    f"Your target is at the **{pct_rank:.0f}th percentile** of the matched cohort enrollment distribution."
                )
        elif not target:
            st.caption("Set a planned enrollment (N) in the Review stage to enable this benchmark.")

    with b2:
        st.markdown("**Trial Duration Benchmark**")
        proto_dur  = m.get("protocol_duration_months")
        c_dur_med  = m.get("completed_duration_median_months")
        c_dur_p25  = m.get("completed_duration_p25_months")
        c_dur_p75  = m.get("completed_duration_p75_months")
        d_dur_med  = m.get("disrupted_duration_median_months")
        site_med   = m.get("site_count_median")
        country_med = m.get("country_count_median")

        r1, r2, r3 = st.columns(3)
        r1.metric("Your Duration",
                  f"{proto_dur:.0f} mo" if proto_dur else "Not set",
                  help="Calculated from your protocol start and completion dates")
        r2.metric("Completed Trials",
                  f"{c_dur_med:.0f} mo" if c_dur_med else "—",
                  f"IQR {c_dur_p25:.0f}–{c_dur_p75:.0f} mo" if c_dur_p25 and c_dur_p75 else None,
                  help="Median duration of completed comparable trials")
        r3.metric("Disrupted Trials",
                  f"{d_dur_med:.0f} mo" if d_dur_med else "—",
                  help="Median duration of terminated comparable trials")

        if proto_dur and c_dur_med:
            diff_pct = abs(proto_dur - c_dur_med) / c_dur_med * 100
            if diff_pct <= 20:
                st.success(
                    f"Duration ({proto_dur:.0f} mo) aligns with the completed-trial median "
                    f"({c_dur_med:.0f} mo).  Within ±20% — operationally consistent."
                )
            elif c_dur_p75 and proto_dur > c_dur_p75:
                st.warning(
                    f"Duration ({proto_dur:.0f} mo) exceeds the upper quartile of completed trials "
                    f"({c_dur_p75:.0f} mo).  Extended follow-up increases retention risk and operational burden."
                )
            else:
                st.info(
                    f"Duration ({proto_dur:.0f} mo) vs completed-trial median ({c_dur_med:.0f} mo).  "
                    f"Difference: {diff_pct:.0f}%.  Review operational feasibility."
                )
        elif not proto_dur:
            st.caption("Set start and completion dates in the Review stage to enable this benchmark.")

        if site_med or country_med:
            parts = []
            if site_med:
                parts.append(f"**{site_med:.0f} sites**")
            if country_med:
                parts.append(f"**{country_med:.0f} countries**")
            st.caption(
                "Typical operational footprint in matched cohort: " + " across ".join(parts) + "."
            )


def _render_risk_register(rec: list[dict], m: dict) -> None:
    """Priority-coded risk and action register — the decision core."""
    st.markdown("#### Protocol Risk Register & Action Items")
    st.caption(
        "Risks are identified by comparing your protocol design choices against the completed and "
        "disrupted precedent cohort.  High-priority items represent design choices that are "
        "statistically more common in terminated trials than in completed ones."
    )

    if not rec:
        st.success(
            "No material design risks identified against the current comparator cohort.  "
            "Continue with clinical, statistical, and regulatory review before final sign-off."
        )
        return

    high    = [r for r in rec if r.get("Priority") == "High"]
    medium  = [r for r in rec if r.get("Priority") == "Medium"]
    monitor = [r for r in rec if r.get("Priority") == "Monitor"]
    preserve = [r for r in rec if r.get("Priority") == "Preserve"]

    for section_label, items, border_color in [
        ("🔴  High Priority — Action Required Before Sign-off", high, "red"),
        ("🟠  Medium Priority — Review Before Finalizing", medium, "orange"),
        ("🔵  Monitor", monitor, "blue"),
        ("🟢  Design Strengths to Preserve", preserve, "green"),
    ]:
        if not items:
            continue
        st.markdown(f"**{section_label}**")
        for r in items:
            with st.container(border=True):
                h_col, b_col = st.columns([1, 2.5])
                with h_col:
                    st.markdown(f"**{r.get('Category', '')}**")
                    st.caption(f"Action: **{r.get('Action Type', '')}**")
                with b_col:
                    st.write(r.get("Recommendation", ""))
                    rationale = r.get("Rationale", "")
                    evidence  = r.get("Evidence", "")
                    if rationale:
                        st.caption(f"**Why it matters:** {rationale}")
                    if evidence:
                        st.caption(f"**Evidence:** {evidence}")
        st.markdown("")


def _render_comparator_exemplars(trials_df: pd.DataFrame) -> None:
    """Top comparable trials ranked by design similarity — the reference class."""
    if trials_df is None or trials_df.empty:
        return

    st.markdown("#### Comparator Exemplars")
    st.caption(
        "Top comparable trials ranked by five-domain PICO design similarity score (0–1).  "
        "These are your primary reference class.  "
        "Use completed trials for design justification; study disrupted trials to understand what went wrong."
    )

    cols_wanted = [
        "NCT ID", "Title", "Status", "Phase", "Allocation", "Masking",
        "Enrollment", "design_similarity_score", "similarity_class",
        "Sponsor", "Start Date", "Completion Date",
    ]
    disp_cols = [c for c in cols_wanted if c in trials_df.columns]
    disp = trials_df[disp_cols].head(20).copy()

    if "design_similarity_score" in disp.columns:
        disp.rename(columns={"design_similarity_score": "Similarity", "similarity_class": "Class"}, inplace=True)
        disp["Similarity"] = disp["Similarity"].apply(lambda x: f"{x:.3f}" if pd.notna(x) else "—")

    if "Status" in disp.columns:
        disp["Status"] = disp["Status"].apply(_status_badge)

    st.dataframe(_safe_dataframe(disp), width="stretch", hide_index=True, height=420)


def _render_literature_panel() -> None:
    """PubMed literature evidence panel."""
    pubmed_articles = st.session_state.get("pubmed_articles", [])
    if not pubmed_articles:
        return

    st.markdown("#### Supporting Literature (PubMed)")
    st.caption(
        f"{len(pubmed_articles)} peer-reviewed article(s) retrieved.  "
        "All citations are traceable to NCBI via PMID."
    )
    pub_df = pd.DataFrame(pubmed_articles)
    show_cols = [c for c in ["pmid", "title", "authors", "journal", "year", "url"] if c in pub_df.columns]
    pub_disp = pub_df[show_cols].copy()
    pub_disp.columns = [c.upper() if c == "pmid" else c.title() for c in pub_disp.columns]
    st.dataframe(_safe_dataframe(pub_disp), width="stretch", hide_index=True)

    with st.expander("Abstract excerpts"):
        for art in pubmed_articles[:5]:
            st.markdown(f"**{art.get('title', '')}**")
            st.caption(
                f"PMID: {art.get('pmid', '')}  ·  "
                f"{art.get('authors', '')}  ·  "
                f"{art.get('journal', '')} ({art.get('year', '')})"
            )
            if art.get("abstract"):
                st.write(art["abstract"])
            st.divider()


def _render_assistant_panel(protocol_meta, comparison_metrics: dict, comparison_recommendations: list) -> None:
    """Interactive AI review assistant."""
    st.markdown("#### AI Review Assistant")
    st.caption(
        "Ask a focused question about your protocol, the benchmark findings, or the risk register. "
        "The assistant only uses context from this workspace — it will not fabricate evidence."
    )
    chat_col, next_col = st.columns([2, 1])
    with chat_col:
        user_query = st.text_input(
            "Ask a question",
            placeholder="e.g. What's the biggest enrollment risk for this trial? / Should I change the masking strategy?",
            key="protocol_chat_query",
        )
        if st.button("Submit question", type="primary", width="stretch") and user_query:
            assistant_text = grounded_assistant_response(
                user_query,
                protocol_meta,
                st.session_state.get("latest_comparison", ""),
                comparison_metrics,
                comparison_recommendations,
            )
            st.session_state["chat_history"].append(
                {"role": "user", "text": user_query, "timestamp": current_utc_timestamp()}
            )
            st.session_state["chat_history"].append(
                {"role": "assistant", "text": assistant_text, "timestamp": current_utc_timestamp()}
            )
            st.session_state["audit_log"].append(
                build_audit_event("chat_query", user_query, actor="user", artifact_type="chat")
            )
            st.session_state["audit_log"].append(
                build_audit_event("chat_response", assistant_text, artifact_type="chat")
            )
            st.rerun()

        if st.session_state.get("chat_history"):
            for msg in st.session_state["chat_history"][-8:]:
                speaker = "**You**" if msg["role"] == "user" else "**Assistant**"
                st.markdown(f"{speaker} _{msg['timestamp']}_")
                st.write(msg["text"])
                st.divider()
    with next_col:
        st.caption(
            "Once satisfied with the benchmark review, advance to the Report stage "
            "to generate a formal PDF and PowerPoint export package."
        )
        if st.button("Advance to Report stage", width="stretch"):
            _set_protocol_stage("Report")
            st.rerun()


def _render_analysis_stage():
    st.markdown("#### Trial Landscape Intelligence")
    if not st.session_state.get("protocol_meta"):
        st.info("Complete Step 1 (Intake) and Step 2 (Review) before running analysis.")
        return

    protocol_meta = protocol_metadata_from_session(st.session_state["protocol_meta"])

    # ── Action bar ────────────────────────────────────────────────────────────
    a1, a2 = st.columns(2)
    with a1:
        cond = protocol_meta.condition or DEFAULT_CONDITION
        if st.button(
            f"Run landscape analysis  ·  {cond}",
            type="primary",
            width="stretch",
            help="Fetches matching trials from ClinicalTrials.gov and scores design similarity",
        ):
            with st.spinner(
                f"Fetching registry data for '{cond}' and running PICO design similarity scoring..."
            ):
                _build_comparable_cohort(protocol_meta)
            st.rerun()
    with a2:
        pubmed_label = f"Fetch PubMed literature  ·  {protocol_meta.condition or DEFAULT_CONDITION}"
        if st.button(pubmed_label, width="stretch"):
            with st.spinner("Searching PubMed for peer-reviewed evidence..."):
                articles = _fetch_pubmed_evidence(protocol_meta)
            if articles:
                st.success(f"Retrieved {len(articles)} PubMed article(s).")
            else:
                st.warning("No PubMed articles found. Check the condition name or try again.")
            st.rerun()

    matching_trials = st.session_state.get("matching_trials")
    if matching_trials is None:
        st.info(
            "Run the landscape analysis above.  "
            "The system will fetch comparable trials from ClinicalTrials.gov, "
            "score each one against your protocol using a 5-domain PICO similarity model, "
            "and generate domain-level intelligence and risk findings."
        )
        return

    m   = st.session_state.get("comparison_metrics", {})
    rec = st.session_state.get("comparison_recommendations", [])
    sel = st.session_state.get("cohort_selection_info", {})

    # Cohort selection provenance (collapsible)
    if sel:
        with st.expander("Cohort selection methodology", expanded=False):
            all_n = sel.get("condition_matched_total", 0)
            sel_n = sel.get("design_similar_selected", 0)
            rate  = sel.get("selection_rate_pct", 0)
            med   = sel.get("similarity_score_median")
            dims  = sel.get("design_dimensions_used", [])
            strong   = sel.get("strong_similarity_count", 0)
            moderate = sel.get("moderate_similarity_count", 0)
            weak     = sel.get("weak_similarity_count", 0)
            st.caption(
                f"**{all_n}** condition-matched trials fetched from ClinicalTrials.gov.  "
                f"**{sel_n}** passed the design-similarity threshold ({rate}% of pool).  "
                f"Median similarity score: **{med}**.  "
                f"Strong: {strong}  ·  Moderate: {moderate}  ·  Weak: {weak}.  "
                f"Dimensions scored: {', '.join(dims)}.  "
                f"**Sponsor is not used as a selection criterion.**"
            )

    _render_landscape_brief(protocol_meta, m, sel)
    st.divider()

    _render_domain_intelligence(protocol_meta, m)
    st.divider()

    _render_benchmarks(protocol_meta, m)
    st.divider()

    _render_risk_register(rec, m)
    st.divider()

    # Visual benchmark panel (charts)
    with st.expander("Visual benchmark charts — precedent differential, endpoint split, status mix", expanded=False):
        render_protocol_benchmark_panel(matching_trials, m, rec)
    st.divider()

    _render_comparator_exemplars(matching_trials)
    st.divider()

    _render_literature_panel()

    _render_assistant_panel(protocol_meta, m, rec)


def _render_report_stage():
    st.markdown("#### Step 4: Report and Audit Package")
    if st.session_state.get("protocol_meta") is None or st.session_state.get("matching_trials") is None:
        st.info("Complete the review and analysis stages before exporting a report package.")
        return

    protocol_meta = protocol_metadata_from_session(st.session_state["protocol_meta"])
    pubmed_articles = st.session_state.get("pubmed_articles", [])

    report_col, audit_col = st.columns([1, 1.1])
    with report_col:
        st.markdown("##### Export Package")
        report_sections = [
            ("Executive decision summary + narrative",    "Included"),
            ("Precedent posture gauge chart",             "Included"),
            ("Design domain alignment (radar chart)",     "Included"),
            ("Alignment heatmap",                         "Included"),
            ("Enrollment benchmark (box plot)",           "Included"),
            ("Duration comparison chart",                 "Included"),
            ("Design differential matrix",                "Included"),
            ("Success vs disruption benchmark",           "Included"),
            ("Endpoint evidence (chart + table)",         "Included"),
            ("PubMed literature evidence",                f"{len(pubmed_articles)} article(s)" if pubmed_articles else "Not fetched"),
            ("Comparator exemplars",                      "Included"),
            ("Action register",                           "Included"),
            ("Audit trail and methodology",               "Included"),
        ]
        st.dataframe(_safe_dataframe(pd.DataFrame(report_sections, columns=["Section", "Status"])), width="stretch", hide_index=True)

        if not pubmed_articles:
            st.info("Tip: fetch PubMed evidence in the Analysis stage to include literature citations in the report.")

        # ── PDF export ────────────────────────────────────────────────────────
        if st.button("Generate PDF report", type="primary", width="stretch"):
            with st.spinner("Generating detailed PDF report with charts and evidence..."):
                output_file = DEFAULT_REPORT_FILE
                st.session_state["audit_log"].append(
                    build_audit_event(
                        "export_pdf_report",
                        f"Generated {output_file}.",
                        artifact_type="report",
                        artifact_id=output_file,
                        metadata={"pubmed_articles": len(pubmed_articles)},
                    )
                )
                generate_protocol_report_pdf(
                    output_file,
                    protocol_meta,
                    st.session_state.get("latest_comparison", ""),
                    st.session_state.get("audit_log", []),
                    st.session_state.get("matching_trials"),
                    st.session_state.get("chat_history", []),
                    st.session_state.get("comparison_metrics", {}),
                    st.session_state.get("comparison_recommendations", []),
                    pubmed_articles=pubmed_articles,
                )
            with open(output_file, "rb") as f:
                st.download_button(
                    "Download PDF report",
                    data=f.read(),
                    file_name=output_file,
                    mime="application/pdf",
                    width="stretch",
                )

        # ── PowerPoint export ─────────────────────────────────────────────────
        st.markdown("---")
        if st.button("Generate PowerPoint slides", width="stretch"):
            with st.spinner("Building presentation deck with charts and evidence slides..."):
                slides_file = DEFAULT_SLIDES_FILE
                st.session_state["audit_log"].append(
                    build_audit_event(
                        "export_pptx_slides",
                        f"Generated {slides_file}.",
                        artifact_type="slides",
                        artifact_id=slides_file,
                        metadata={"pubmed_articles": len(pubmed_articles)},
                    )
                )
                generate_slides_pptx(
                    slides_file,
                    protocol_meta,
                    st.session_state.get("comparison_metrics", {}),
                    st.session_state.get("comparison_recommendations", []),
                    st.session_state.get("audit_log", []),
                    st.session_state.get("matching_trials"),
                    pubmed_articles=pubmed_articles,
                )
            with open(slides_file, "rb") as f:
                st.download_button(
                    "Download PowerPoint slides",
                    data=f.read(),
                    file_name=slides_file,
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    width="stretch",
                )

    with audit_col:
        st.markdown("##### Cohort and Audit Preview")
        st.dataframe(
            _safe_dataframe(build_cohort_definition_table(st.session_state.get("comparison_metrics", {}))),
            width="stretch",
            hide_index=True,
            height=180,
        )
        st.markdown("##### PubMed Evidence Summary")
        if pubmed_articles:
            pub_summary = pd.DataFrame([
                {"PMID": a.get("pmid", ""), "Title": a.get("title", "")[:60], "Year": a.get("year", "")}
                for a in pubmed_articles[:6]
            ])
            st.dataframe(_safe_dataframe(pub_summary), width="stretch", hide_index=True)
        else:
            st.caption("No PubMed articles fetched yet.")
        st.markdown("##### Audit Trail")
        st.dataframe(_safe_dataframe(pd.DataFrame(st.session_state.get("audit_log", []))), width="stretch", height=180)
