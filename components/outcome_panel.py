import streamlit as st
import pandas as pd
import plotly.express as px
from collections import Counter

def clean_outcome(text):
    return text.lower().strip()

def classify_outcome(outcome):
    outcome = outcome.lower()

    if any(k in outcome for k in [
        "mortality", "survival", "efficacy", "response", "remission", "recurrence",
        "relapse", "tumor size", "cure", "progression", "control", "primary outcome",
        "treatment success", "success rate", "responder", "rate of improvement"
    ]):
        return "Efficacy"

    elif any(k in outcome for k in [
        "adverse", "side effect", "toxicity", "tolerability", "complication",
        "dose limiting", "serious", "safety", "death", "risk", "severe",
        "incidence of adrs", "illness expectations", "withdrawal", "dropout"
    ]):
        return "Safety"

    elif any(k in outcome for k in [
        "quality of life", "wellbeing", "pain", "fatigue", "anxiety", "mental", "symptom",
        "depression", "cognitive", "psychological", "fsi-10", "life impact"
    ]):
        return "Quality of Life"

    elif any(k in outcome for k in [
        "biomarker", "gene", "expression", "mrna", "rna", "cytokine", "level", "marker",
        "protein", "phenotype", "immunologic", "neutrophil", "blood analysis", "vitamin d"
    ]):
        return "Biomarker"

    elif any(k in outcome for k in [
        "hospital stay", "icu", "length of stay", "resource", "cost", "utilization",
        "readmission", "ventilation time", "respiratory support", "outpatient", "emergency",
        "healthcare use"
    ]):
        return "Utilization"

    elif any(k in outcome for k in [
        "exercise", "walk test", "distance", "mobility", "functional class", "movement",
        "gait", "reaction", "lung capacity", "spirometry", "breathing test", "airflow", "fvc",
        "airway resistance", "lung function", "pulmonary pressure", "expiratory"
    ]):
        return "Functional Capacity"

    elif any(k in outcome for k in [
        "protocol adherence", "completion rate", "dropout", "recruitment rate",
        "participant withdrawal", "enrollment", "retention", "feasibility", "study success",
        "protocol deviation"
    ]):
        return "Trial Logistics"

    elif any(k in outcome for k in [
        "respiratory distress", "asthma", "copd", "bronchitis", "airway inflammation",
        "lung", "ventilation", "breath", "oxygenation", "spirometry", "resistance"
    ]):
        return "Respiratory Outcomes"

    elif any(k in outcome for k in [
        "dpi", "nebulizer", "device", "telesurgery", "digital health", "platform",
        "remote monitoring"
    ]):
        return "Digital & Device"

    else:
        return "Unclassified"

def show_outcome_panel(df):
    if df.empty or "Primary Outcome" not in df.columns:
        st.info("No outcome data available.")
        return

    outcomes = df["Primary Outcome"].dropna().tolist()

    # Clean and split
    cleaned = []
    for entry in outcomes:
        for item in entry.split(","):
            cleaned.append(clean_outcome(item))

    if not cleaned:
        st.info("No valid outcome descriptions found.")
        return

    # Count and classify
    top_outcomes = Counter(cleaned).most_common(100)
    outcome_df = pd.DataFrame(top_outcomes, columns=["Outcome", "Count"])
    outcome_df["Type"] = outcome_df["Outcome"].apply(classify_outcome)

    # Available types
    selected_types = sorted(outcome_df["Type"].unique())
    filtered_df = outcome_df[outcome_df["Type"].isin(selected_types)]

    # Display type legend
    st.markdown("**Outcome Types Detected:**")
    label_colors = {
        "Efficacy": "#1f77b4",             # blue
        "Safety": "#d62728",               # deep red
        "Quality of Life": "#2ca02c",      # green
        "Biomarker": "#9467bd",            # purple
        "Utilization": "#8c564b",          # brown
        "Functional Capacity": "#17becf",  # cyan
        "Trial Logistics": "#bcbd22",      # olive
        "Respiratory Outcomes": "#e377c2", # pink
        "Digital & Device": "#7f7f7f",     # grey
        "Unclassified": "#cccccc"          # light grey
    }

    st.markdown(
        " ".join(
            f"<span style='background-color:{label_colors.get(ot, '#ccc')}; "
            f"color:white; padding:4px 10px; border-radius:12px; margin-right:6px;'>"
            f"{ot}</span>"
            for ot in selected_types
        ),
        unsafe_allow_html=True
    )

    # Shorten long outcomes
    filtered_df["Short Outcome"] = filtered_df["Outcome"].apply(
        lambda x: x[:80] + "..." if len(x) > 80 else x
    )

    # ✅ Limit number of bars
    filtered_df = filtered_df.sort_values("Count", ascending=False).head(30)

    # ✅ Calculate dynamic chart height
    bar_count = len(filtered_df)
    chart_height = min(bar_count * 35 + 100, 1200)

    # Chart
    fig = px.bar(
        filtered_df.sort_values("Count", ascending=True),
        x="Count",
        y="Short Outcome",
        color="Type",
        barmode="stack",
        orientation="h",
        title="Top Primary Outcomes by Classification",
        hover_data={"Outcome": True, "Short Outcome": False, "Count": True},
        color_discrete_map=label_colors,
        opacity=1.0
    )

    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(color="#333333", size=14),
        margin=dict(t=60, b=50, l=300, r=30),
        height=chart_height,
        yaxis_title="Outcome",
        legend_title="Outcome Type",
        bargap=0.15
    )

    st.plotly_chart(fig, use_container_width=True)
