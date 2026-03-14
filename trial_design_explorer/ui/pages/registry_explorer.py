import streamlit as st

from trial_design_explorer.config import COMMON_CONDITIONS, DEFAULT_CONDITION, REGISTRY_TABS
from trial_design_explorer.services.clinical_trials_service import (
    count_countries,
    fetch_trials_by_condition,
    median_trial_duration_months,
    most_common_primary_outcome,
    parse_trials_to_df,
)
from trial_design_explorer.ui.panels.duration import show_duration_panel
from trial_design_explorer.ui.panels.location import show_location_panel
from trial_design_explorer.ui.panels.outcome import classify_outcome, show_outcome_panel
from trial_design_explorer.ui.panels.overview import show_overview_panel
from trial_design_explorer.ui.panels.sponsor import show_sponsor_panel
from trial_design_explorer.ui.panels.summary import show_summary_panel
from trial_design_explorer.ui.panels.timeline import show_timeline_panel


def render_registry_sidebar():
    st.markdown("## Registry Explorer")
    st.caption("Search historical trial cohorts to support benchmark review.")

    with st.form("registry_search_form"):
        selected_condition = st.selectbox(
            "Clinical condition",
            options=COMMON_CONDITIONS,
            index=COMMON_CONDITIONS.index(DEFAULT_CONDITION) if DEFAULT_CONDITION in COMMON_CONDITIONS else 0,
        )
        custom_condition = st.text_input("Custom condition", placeholder="Optional free-text condition")
        submitted = st.form_submit_button("Search trial registry", width="stretch")

    if submitted:
        condition = custom_condition.strip() or selected_condition
        with st.spinner("Retrieving ClinicalTrials.gov studies..."):
            response = fetch_trials_by_condition(condition)
            if response:
                trials_df = parse_trials_to_df(response)
                st.session_state["df_trials"] = trials_df
                st.session_state["registry_tab"] = "Overview"
                st.success(f"Retrieved {len(trials_df)} studies for {condition}.")
            else:
                st.error("Unable to retrieve trials at this time.")

    if st.session_state.get("df_trials") is not None:
        st.markdown("---")
        st.metric("Loaded Studies", len(st.session_state["df_trials"]))


def render_summary_cards(df):
    countries = count_countries(df)
    median_duration = median_trial_duration_months(df)
    top_outcome = most_common_primary_outcome(df)

    col1, col2, col3 = st.columns(3)
    col1.metric("Countries Represented", f"{countries}")
    col2.metric("Median Trial Duration", f"{median_duration} mo" if median_duration is not None else "Unavailable")
    if top_outcome:
        outcome_label = top_outcome[0]
        col3.metric("Most Common Primary Outcome", f"{outcome_label[:36]} ({classify_outcome(outcome_label)})")
    else:
        col3.metric("Most Common Primary Outcome", "Unavailable")


def render_registry_workspace():
    st.markdown("### Registry Benchmark Workspace")
    df = st.session_state.get("df_trials")
    if df is None:
        st.info("Search the registry from the sidebar to begin a benchmark cohort review.")
        return

    if df.empty:
        st.warning("The last registry search returned no records.")
        return

    render_summary_cards(df)
    selected_tab = st.segmented_control(
        "Registry analysis modules",
        REGISTRY_TABS,
        default=st.session_state.get("registry_tab", "Overview"),
        selection_mode="single",
        width="stretch",
    )
    st.session_state["registry_tab"] = selected_tab or st.session_state.get("registry_tab", "Overview")
    st.caption("Switch modules to move between cohort overview, timing, geography, outcomes, sponsor activity, and operational history.")

    if st.session_state["registry_tab"] == "Overview":
        show_overview_panel(df)
    elif st.session_state["registry_tab"] == "Durations":
        show_duration_panel(df)
    elif st.session_state["registry_tab"] == "Locations":
        show_location_panel(df)
    elif st.session_state["registry_tab"] == "Outcomes":
        show_outcome_panel(df)
    elif st.session_state["registry_tab"] == "Summary":
        show_summary_panel(df)
    elif st.session_state["registry_tab"] == "Timeline":
        show_timeline_panel(df)
    elif st.session_state["registry_tab"] == "Sponsors":
        show_sponsor_panel(df)
