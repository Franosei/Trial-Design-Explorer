import streamlit as st
import pandas as pd
from utils.api_client import fetch_trials_by_condition
from utils.parser import parse_trials_to_df
from config import DEFAULT_CONDITION
from components.overview_panel import show_overview
from components.outcome_panel import classify_outcome, clean_outcome

# ---- PAGE CONFIG ----
st.set_page_config(
    page_title="Trial Design Explorer",
    layout="wide",
    page_icon="🧫"
)

# ---- HEADER ----
col1, col2 = st.columns([1, 5])
with col1:
    st.image("assets/logo.png", width=120)
with col2:
    st.markdown("""
        <h1 style='margin-bottom:0;'>Trial Design Explorer</h1>
        <p style='font-size:18px; color:gray; margin-top:0;'>Explore real-time patterns in clinical trial design using global registry data.</p>
        """, unsafe_allow_html=True)

# ---- SIDEBAR ----
with st.sidebar:
    st.markdown("## 🔍 Explore Trials")
    st.markdown("<hr style='margin-top:-10px;'>", unsafe_allow_html=True)
    st.markdown("<div style='color:gray; font-size:14px;'>Select a condition below or start typing to search for real-time clinical trials.</div>", unsafe_allow_html=True)

    common_conditions = [
        "Sepsis", "ARDS", "Pneumonia", "COVID-19", "Heart Failure",
        "Asthma", "Stroke", "Hypertension", "Cancer", "Diabetes",
        "Renal Failure", "Liver Disease", "ICU Delirium", "Myocardial Infarction",
        "Chronic Obstructive Pulmonary Disease", "Cardiac Arrest", "Traumatic Brain Injury",
        "Multiple Organ Dysfunction Syndrome", "Acute Kidney Injury", "Lung Cancer",
        "Breast Cancer", "Colorectal Cancer", "Pancreatic Cancer", "Prostate Cancer",
        "Ventilator-Associated Pneumonia", "Hemorrhagic Stroke", "Ischemic Stroke",
        "Deep Vein Thrombosis", "Pulmonary Embolism", "Anemia", "Leukemia",
        "Meningitis", "Tuberculosis", "HIV", "Influenza", "COVID-19 Reinfection",
        "Obesity", "Malnutrition", "Burn Injuries", "Surgical Site Infections",
        "Nosocomial Infections", "Clostridium difficile Infection", "Delirium",
        "Postoperative Complications", "ARDS Secondary to Sepsis", "Neutropenia",
        "Liver Cirrhosis", "Hepatitis B", "Hepatitis C", "Acute Respiratory Failure",
        "respiratory syncytial virus"
    ]

    condition = st.selectbox(
        "🩺 Clinical Condition",
        options=common_conditions,
        index=common_conditions.index(DEFAULT_CONDITION) if DEFAULT_CONDITION in common_conditions else 0,
        placeholder="Enter or select a condition...",
        key="condition_selector"
    )

    st.markdown("<div style='font-size:12px; color:gray;'>Tip: You can also type a new condition that’s not in the list.</div>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    run = st.button("Search Trials", use_container_width=True)


# ---- MAIN ----
def summary_cards(df):
    import textwrap
    from collections import Counter

    n_trials = len(df)
    n_countries = len(set([
        loc.get("country")
        for row in df.get("Locations", [])
        for loc in row if isinstance(loc, dict) and "country" in loc
    ])) if "Locations" in df else 0

    try:
        start_dates = pd.to_datetime(df["Start Date"], errors="coerce")
        end_dates = pd.to_datetime(df["Completion Date"], errors="coerce")
        avg_duration = (end_dates - start_dates).dt.days.dropna().median() // 30
        avg_duration = int(avg_duration) if pd.notna(avg_duration) else "N/A"
    except:
        avg_duration = "N/A"

    top_outcome = "N/A"
    top_class = "N/A"

    if "Primary Outcome" in df and not df["Primary Outcome"].dropna().empty:
        outcomes = df["Primary Outcome"].dropna().tolist()
        invalids = {"n/a", "na", "none", "n.a.", "-", ""}
        cleaned = [
            clean_outcome(item)
            for entry in outcomes
            for item in entry.split(",")
            if clean_outcome(item) not in invalids
        ]

        if cleaned:
            outcome_counts = Counter(cleaned)
            most_common_outcome = outcome_counts.most_common(1)[0][0]
            short_name = most_common_outcome.title()
            if len(short_name) > 40:
                short_name = textwrap.shorten(short_name, width=40, placeholder="...")
            top_outcome = short_name
            top_class = classify_outcome(most_common_outcome)

    col1, col2, col3 = st.columns(3)
    col1.metric("🌍 Countries Involved", f"{n_countries}")
    col2.metric("⏳ Median Trial Duration", f"{avg_duration} mo" if isinstance(avg_duration, (int, float)) else "N/A")
    col3.metric("🔬 Top Outcome", f"{top_outcome} ({top_class})" if top_class != "N/A" else top_outcome)


# ---- SEARCH ----
if run:
    with st.spinner("Fetching trials..."):
        response = fetch_trials_by_condition(condition)
        if response:
            df = parse_trials_to_df(response)
            st.session_state["df_trials"] = df
            st.session_state["tab_selector"] = "Locations"  # Start in Locations after search
            st.success(f"{len(df)} trials retrieved for '{condition}'.")
        else:
            st.error("Could not retrieve trials at this time. Please try again.")
            st.stop()

# ---- RENDER ----
if "df_trials" in st.session_state:
    df = st.session_state["df_trials"]
    summary_cards(df)

    tab_options = [
        "Overview", "Durations", "Locations", "Outcomes", "Summary", "Timeline", "Sponsors", "More Coming"
    ]

    if "tab_selector" not in st.session_state:
        st.session_state["tab_selector"] = "Locations"

    selected_tab = st.radio(
        " ",
        tab_options,
        index=tab_options.index(st.session_state["tab_selector"]),
        horizontal=True,
        key="tab_selector"
    )

    if selected_tab == "Overview":
        from components.overview_panel import show_overview
        show_overview(df)

    elif selected_tab == "Durations":
        from components.duration_panel import show_duration_panel
        show_duration_panel(df)

    elif selected_tab == "Locations":
        from components.location_panel import show_location_panel
        show_location_panel(df)

    elif selected_tab == "Outcomes":
        from components.outcome_panel import show_outcome_panel
        show_outcome_panel(df)

    elif selected_tab == "Summary":
        from components.summary_table import show_summary_table
        show_summary_table(df)

    elif selected_tab == "Timeline":
        from components.timeline_panel import show_timeline_panel
        show_timeline_panel(df)

    elif selected_tab == "Sponsors":
        from components.sponsor_panel import show_sponsor_panel
        show_sponsor_panel(df)

    else:
        st.info("More predictive analytics coming soon.")

else:
    st.markdown("""
        <div style='margin-top:3rem; color: #999999; font-size: 18px;'>
        Use the panel on the left to start exploring clinical trial data.
        </div>
    """, unsafe_allow_html=True)
