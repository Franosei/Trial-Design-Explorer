import pandas as pd
import streamlit as st

from trial_design_explorer.config import DEFAULT_CONDITION, DEFAULT_REPORT_FILE, DEFAULT_SLIDES_FILE
from trial_design_explorer.services import (
    articles_to_evidence_rows,
    build_audit_event,
    build_action_register,
    build_cohort_definition_table,
    build_protocol_benchmark_table,
    build_protocol_comparison_metrics,
    build_protocol_recommendations,
    build_trial_exemplar_table,
    compare_protocol_to_trials,
    extract_protocol_metadata_from_text,
    extract_text_from_uploaded_file,
    fetch_trials_by_condition,
    generate_protocol_report_pdf,
    generate_slides_pptx,
    grounded_assistant_response,
    metrics_to_dataframe,
    parse_trials_to_df,
    protocol_metadata_from_session,
    recommendations_to_dataframe,
    search_pubmed_evidence,
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
    trials_df = parse_trials_to_df(response) if response else pd.DataFrame()
    comparison_metrics = build_protocol_comparison_metrics(protocol_meta, trials_df)
    comparison_recommendations = build_protocol_recommendations(protocol_meta, comparison_metrics)
    comparison_notes = compare_protocol_to_trials(protocol_meta, trials_df)

    st.session_state["matching_trials"] = trials_df
    st.session_state["comparison_metrics"] = comparison_metrics
    st.session_state["comparison_recommendations"] = comparison_recommendations
    st.session_state["latest_comparison"] = comparison_notes
    st.session_state["audit_log"].append(
        build_audit_event(
            "build_comparable_cohort",
            f"Built registry comparison cohort for {compare_label}.",
            artifact_type="comparison_cohort",
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
        st.caption("Use the most current protocol or synopsis available.")
        st.caption("The extracted profile is a draft and should be reviewed before any analysis or reporting.")
        if st.session_state.get("protocol_meta"):
            protocol_meta = protocol_metadata_from_session(st.session_state["protocol_meta"])
            st.markdown("##### Extracted Snapshot")
            snapshot_rows = [
                ("Title", protocol_meta.title or "Not provided"),
                ("Condition", protocol_meta.condition or "Not provided"),
                ("Study Type", protocol_meta.study_type or "Not provided"),
                ("Phase", protocol_meta.phase or "Not provided"),
                ("Sample Size", protocol_meta.sample_size or "Not provided"),
            ]
            st.dataframe(_safe_dataframe(pd.DataFrame(snapshot_rows, columns=["Field", "Value"])), width="stretch", hide_index=True)


def _render_review_stage():
    st.markdown("#### Step 2: Review and Confirm Protocol Profile")
    if not st.session_state.get("protocol_meta"):
        st.info("Start with Step 1 to generate the initial protocol profile.")
        return

    protocol_meta = protocol_metadata_from_session(st.session_state["protocol_meta"])
    with st.form("protocol_review_form"):
        identity_col, design_col = st.columns(2)
        with identity_col:
            st.markdown("##### Study Identity")
            title = st.text_area("Protocol title", value=protocol_meta.title or "", height=120)
            condition = st.text_input("Condition", value=protocol_meta.condition or "")
            sponsor = st.text_input("Sponsor", value=protocol_meta.sponsor or "")
            study_type = st.selectbox("Study type", STUDY_TYPE_OPTIONS, index=_select_index(STUDY_TYPE_OPTIONS, protocol_meta.study_type))
            phase = st.text_input("Phase", value=protocol_meta.phase or "")
            sample_size = st.text_input("Planned enrollment", value=protocol_meta.sample_size or "")
            arms_count = st.text_input("Arms count", value=protocol_meta.arms_count or "")
            start_date = st.text_input("Start date", value=protocol_meta.start_date or "")
            completion_date = st.text_input("Completion date", value=protocol_meta.completion_date or "")

        with design_col:
            st.markdown("##### Design and Population")
            allocation = st.selectbox("Allocation", ALLOCATION_OPTIONS, index=_select_index(ALLOCATION_OPTIONS, protocol_meta.allocation))
            masking = st.selectbox("Masking", MASKING_OPTIONS, index=_select_index(MASKING_OPTIONS, protocol_meta.masking))
            intervention_model = st.selectbox(
                "Intervention model",
                INTERVENTION_MODEL_OPTIONS,
                index=_select_index(INTERVENTION_MODEL_OPTIONS, protocol_meta.intervention_model),
            )
            primary_purpose = st.selectbox(
                "Primary purpose",
                PRIMARY_PURPOSE_OPTIONS,
                index=_select_index(PRIMARY_PURPOSE_OPTIONS, protocol_meta.primary_purpose),
            )
            comparator = st.text_input("Comparator", value=protocol_meta.comparator or "")
            geography_focus = st.text_input("Geography focus", value=protocol_meta.geography_focus or "")
            target_population = st.text_area("Target population", value=protocol_meta.target_population or "", height=110)
            intervention_description = st.text_area(
                "Intervention description",
                value=protocol_meta.intervention_description or "",
                height=110,
            )

        st.markdown("##### Endpoint Strategy")
        endpoint_col1, endpoint_col2 = st.columns([1, 1])
        with endpoint_col1:
            endpoint_focus = st.selectbox(
                "Endpoint focus",
                ENDPOINT_FOCUS_OPTIONS,
                index=_select_index(ENDPOINT_FOCUS_OPTIONS, protocol_meta.endpoint_focus),
            )
            primary_endpoints = st.text_area("Primary endpoints", value=protocol_meta.primary_endpoints or "", height=150)
        with endpoint_col2:
            secondary_endpoints = st.text_area("Secondary endpoints", value=protocol_meta.secondary_endpoints or "", height=150)

        save_review = st.form_submit_button("Save reviewed profile", type="primary", width="stretch")

    if save_review:
        protocol_meta.title = title or None
        protocol_meta.condition = condition or None
        protocol_meta.sponsor = sponsor or None
        protocol_meta.study_type = study_type or None
        protocol_meta.phase = phase or None
        protocol_meta.sample_size = sample_size or None
        protocol_meta.arms_count = arms_count or None
        protocol_meta.start_date = start_date or None
        protocol_meta.completion_date = completion_date or None
        protocol_meta.allocation = allocation or None
        protocol_meta.masking = masking or None
        protocol_meta.intervention_model = intervention_model or None
        protocol_meta.primary_purpose = primary_purpose or None
        protocol_meta.comparator = comparator or None
        protocol_meta.geography_focus = geography_focus or None
        protocol_meta.target_population = target_population or None
        protocol_meta.intervention_description = intervention_description or None
        protocol_meta.endpoint_focus = endpoint_focus or None
        protocol_meta.primary_endpoints = primary_endpoints or None
        protocol_meta.secondary_endpoints = secondary_endpoints or None
        protocol_meta.confirmation_status = "reviewed"
        st.session_state["protocol_meta"] = protocol_meta.to_dict()
        if st.session_state.get("matching_trials") is not None:
            _build_comparable_cohort(protocol_meta)
        st.session_state["audit_log"].append(
            build_audit_event(
                "review_protocol_profile",
                "Reviewer updated and confirmed protocol profile fields.",
                actor="user",
                artifact_type="protocol_profile",
            )
        )
        _set_protocol_stage("Analysis")
        st.rerun()

    with st.expander("Traceability and provenance"):
        st.dataframe(_safe_dataframe(pd.DataFrame([_provenance_payload(protocol_meta)])), width="stretch", hide_index=True)


def _render_analysis_stage():
    st.markdown("#### Step 3: Analysis and Expert Review")
    if not st.session_state.get("protocol_meta"):
        st.info("Complete Step 1 and Step 2 before running analysis.")
        return

    protocol_meta = protocol_metadata_from_session(st.session_state["protocol_meta"])

    # ── Action row ────────────────────────────────────────────────────────────
    action_col, pubmed_col, status_col = st.columns([1.2, 1.2, 1])
    with action_col:
        label = protocol_meta.condition or DEFAULT_CONDITION
        if st.button(f"Build or refresh cohort for {label}", type="primary", width="stretch"):
            with st.spinner("Building comparison cohort and benchmark outputs..."):
                _build_comparable_cohort(protocol_meta)
            st.rerun()
    with pubmed_col:
        pubmed_label = f"Fetch PubMed evidence for {protocol_meta.condition or DEFAULT_CONDITION}"
        if st.button(pubmed_label, width="stretch"):
            with st.spinner("Searching PubMed for peer-reviewed evidence..."):
                articles = _fetch_pubmed_evidence(protocol_meta)
            if articles:
                st.success(f"Retrieved {len(articles)} PubMed article(s).")
            else:
                st.warning("No PubMed articles found. Check the condition name or try again.")
            st.rerun()
    with status_col:
        st.caption("Analysis uses the reviewed protocol profile as the source of truth for cohort benchmarking.")

    matching_trials = st.session_state.get("matching_trials")
    if matching_trials is None:
        st.info("Run the cohort build action to generate benchmark analytics, recommendations, and trial comparisons.")
        return

    comparison_metrics = st.session_state.get("comparison_metrics", {})
    comparison_recommendations = st.session_state.get("comparison_recommendations", [])
    benchmark_df = build_protocol_benchmark_table(protocol_meta, comparison_metrics)
    action_df = build_action_register(comparison_recommendations)

    summary_col1, summary_col2 = st.columns([1.4, 1])
    with summary_col1:
        st.markdown("##### Senior Planning Narrative")
        narrative = st.session_state.get("latest_comparison", "No comparison analysis is available.")
        for line in [entry.strip() for entry in narrative.splitlines() if entry.strip()]:
            st.write(line)
    with summary_col2:
        st.markdown("##### Decision Scorecard")
        st.dataframe(
            _safe_dataframe(metrics_to_dataframe(comparison_metrics).head(8)),
            width="stretch",
            height=260,
            hide_index=True,
        )

    decision_col, action_review_col = st.columns([1.3, 1])
    with decision_col:
        st.markdown("##### Success vs Disruption Benchmark")
        st.dataframe(_safe_dataframe(benchmark_df), width="stretch", hide_index=True, height=360)
    with action_review_col:
        st.markdown("##### Current Action Register")
        st.dataframe(_safe_dataframe(action_df), width="stretch", hide_index=True, height=360)

    render_protocol_benchmark_panel(matching_trials, comparison_metrics, comparison_recommendations)

    rec_col, trials_col = st.columns([1, 1.3])
    with rec_col:
        st.markdown("##### Recommendation Detail")
        st.dataframe(
            _safe_dataframe(recommendations_to_dataframe(comparison_recommendations)),
            width="stretch",
            height=360,
            hide_index=True,
        )
    with trials_col:
        st.markdown("##### Comparator Exemplars")
        st.dataframe(_safe_dataframe(build_trial_exemplar_table(matching_trials, limit=10)), width="stretch", hide_index=True, height=360)

    # ── PubMed evidence panel ─────────────────────────────────────────────────
    pubmed_articles = st.session_state.get("pubmed_articles", [])
    if pubmed_articles:
        st.markdown("##### PubMed Literature Evidence")
        st.caption(
            f"{len(pubmed_articles)} peer-reviewed article(s) retrieved from PubMed. "
            "All citations are traceable to NCBI via PMID."
        )
        evidence_rows = articles_to_evidence_rows([
            type("A", (), a)() if not hasattr(a, "to_dict") else a
            for a in pubmed_articles
        ])
        # Convert dict list to df
        pub_display = pd.DataFrame(pubmed_articles)[
            [c for c in ["pmid", "title", "authors", "journal", "year", "url"] if c in pd.DataFrame(pubmed_articles).columns]
        ]
        pub_display.columns = [c.upper() if c == "pmid" else c.title() for c in pub_display.columns]
        st.dataframe(_safe_dataframe(pub_display), width="stretch", hide_index=True)

        with st.expander("View abstract excerpts"):
            for art in pubmed_articles[:4]:
                st.markdown(f"**{art.get('title', '')}**")
                st.caption(f"PMID: {art.get('pmid', '')} | {art.get('authors', '')} | {art.get('journal', '')} ({art.get('year', '')})")
                if art.get("abstract"):
                    st.write(art["abstract"])
                st.markdown("---")

    st.markdown("##### Interactive Review Assistant")
    chat_col, next_col = st.columns([1.6, 1])
    with chat_col:
        user_query = st.text_input("Ask a focused review question", key="protocol_chat_query")
        if st.button("Run review question", width="stretch") and user_query:
            assistant_text = grounded_assistant_response(
                user_query,
                protocol_meta,
                st.session_state.get("latest_comparison", "No comparison analysis is available."),
                comparison_metrics,
                comparison_recommendations,
            )
            st.session_state["chat_history"].append({"role": "user", "text": user_query, "timestamp": current_utc_timestamp()})
            st.session_state["chat_history"].append({"role": "assistant", "text": assistant_text, "timestamp": current_utc_timestamp()})
            st.session_state["audit_log"].append(build_audit_event("chat_query", user_query, actor="user", artifact_type="chat"))
            st.session_state["audit_log"].append(build_audit_event("chat_response", assistant_text, artifact_type="chat"))
            st.rerun()
        if st.session_state.get("chat_history"):
            for message in st.session_state["chat_history"][-6:]:
                speaker = "Reviewer" if message["role"] == "user" else "Assistant"
                st.markdown(f"**{speaker}** ({message['timestamp']}): {message['text']}")
    with next_col:
        st.caption("Once the benchmark review is satisfactory, move to the report stage for formal export.")
        if st.button("Open report stage", width="stretch"):
            _set_protocol_stage("Report")
            st.rerun()


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
