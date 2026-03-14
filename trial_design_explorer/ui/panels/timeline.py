from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st


def show_timeline_panel(df):
    if "Start Date" not in df.columns:
        st.info("Start date data is not available.")
        return

    timeline_df = df.copy()
    timeline_df["Start Year"] = pd.to_datetime(timeline_df["Start Date"], errors="coerce").dt.year
    annual_counts = timeline_df["Start Year"].value_counts().sort_index().reset_index()
    annual_counts.columns = ["Year", "Trials Started"]

    fig = px.bar(
        annual_counts,
        x="Year",
        y="Trials Started",
        color="Trials Started",
        color_continuous_scale="Blues",
        title="Trials Started by Year",
    )
    fig.update_layout(template="plotly_white", margin=dict(t=60, b=20, l=20, r=20), height=420)
    st.plotly_chart(fig, width="stretch")

    phase_df = timeline_df.dropna(subset=["Start Year"]).copy()
    phase_df["Phase"] = phase_df["Phase"].fillna("N/A")
    phase_timeline = phase_df.groupby(["Start Year", "Phase"]).size().reset_index(name="Count")
    if not phase_timeline.empty:
        fig = px.bar(
            phase_timeline,
            x="Start Year",
            y="Count",
            color="Phase",
            title="Phase Activity Over Time",
            color_discrete_sequence=px.colors.qualitative.Set2,
            height=500,
        )
        fig.update_layout(template="plotly_white", barmode="stack", margin=dict(t=60, b=20, l=20, r=20))
        st.plotly_chart(fig, width="stretch")

    if "Locations" not in df.columns:
        return

    location_rows = []
    current_year = datetime.now().year
    for _, row in df.iterrows():
        year = pd.to_datetime(row.get("Start Date"), errors="coerce")
        if pd.isna(year):
            continue
        for location in row.get("Locations", []):
            country = location.get("country")
            if country and year.year >= current_year - 5:
                location_rows.append({"Start Year": year.year, "Country": country})

    location_df = pd.DataFrame(location_rows)
    if location_df.empty:
        return

    top_countries = location_df["Country"].value_counts().head(10).index
    filtered = location_df[location_df["Country"].isin(top_countries)]
    trend = filtered.groupby(["Start Year", "Country"]).size().reset_index(name="Trial Count")

    fig = px.line(
        trend,
        x="Start Year",
        y="Trial Count",
        color="Country",
        markers=True,
        title="Top Countries by Recent Trial Starts",
        color_discrete_sequence=px.colors.qualitative.Set2,
        height=520,
    )
    fig.update_layout(template="plotly_white", margin=dict(t=60, b=20, l=20, r=20))
    st.plotly_chart(fig, width="stretch")
