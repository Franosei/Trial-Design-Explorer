from collections import Counter

import pandas as pd
import plotly.express as px
import streamlit as st


def clean_outcome(text):
    return text.lower().strip()


def classify_outcome(outcome):
    outcome = outcome.lower()

    if any(
        keyword in outcome
        for keyword in [
            "mortality",
            "survival",
            "efficacy",
            "response",
            "remission",
            "recurrence",
            "relapse",
            "tumor size",
            "progression",
            "treatment success",
        ]
    ):
        return "Efficacy"
    if any(
        keyword in outcome
        for keyword in [
            "adverse",
            "toxicity",
            "tolerability",
            "complication",
            "safety",
            "risk",
            "death",
        ]
    ):
        return "Safety"
    if any(
        keyword in outcome
        for keyword in [
            "quality of life",
            "pain",
            "fatigue",
            "symptom",
            "depression",
            "cognitive",
        ]
    ):
        return "Patient-Reported"
    if any(
        keyword in outcome
        for keyword in [
            "biomarker",
            "gene",
            "rna",
            "cytokine",
            "protein",
            "marker",
        ]
    ):
        return "Biomarker"
    if any(
        keyword in outcome
        for keyword in [
            "hospital stay",
            "icu",
            "length of stay",
            "cost",
            "utilization",
            "readmission",
        ]
    ):
        return "Utilization"
    return "Other"


def show_outcome_panel(df):
    if df.empty or "Primary Outcome" not in df.columns:
        st.info("No primary outcome data is available.")
        return

    cleaned = []
    for entry in df["Primary Outcome"].dropna().astype(str):
        cleaned.extend(clean_outcome(item) for item in entry.split(",") if item.strip())

    if not cleaned:
        st.info("No outcome descriptions are available.")
        return

    outcome_df = pd.DataFrame(Counter(cleaned).most_common(40), columns=["Outcome", "Count"])
    outcome_df["Type"] = outcome_df["Outcome"].apply(classify_outcome)
    outcome_df["Short Outcome"] = outcome_df["Outcome"].apply(lambda value: value[:90] + "..." if len(value) > 90 else value)

    fig = px.bar(
        outcome_df.sort_values("Count", ascending=True),
        x="Count",
        y="Short Outcome",
        color="Type",
        orientation="h",
        title="Primary Outcome Landscape",
        hover_data={"Outcome": True, "Short Outcome": False, "Count": True},
        color_discrete_sequence=px.colors.qualitative.Set3,
    )
    fig.update_layout(
        template="plotly_white",
        height=min(len(outcome_df) * 28 + 120, 1200),
        margin=dict(t=60, b=20, l=40, r=20),
        yaxis_title="Outcome",
        legend_title="Classification",
    )
    st.plotly_chart(fig, width="stretch")
