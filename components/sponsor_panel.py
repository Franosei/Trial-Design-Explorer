import streamlit as st
import pandas as pd
import plotly.express as px
import re

def classify_sponsor_type(name):
    """Classify sponsor as 'Industry' or 'Academic' based on keywords."""
    if not isinstance(name, str):
        return "Unknown"
    name = name.lower()
    academic_keywords = ["university", "college", "institute", "hospital", "nhs", "school", "center", "centre", "clinic"]
    if any(kw in name for kw in academic_keywords):
        return "Academic"
    else:
        return "Industry"

def show_sponsor_panel(df):
    # st.markdown("### Sponsor Landscape Analysis")

    if "Sponsor" not in df.columns or "Status" not in df.columns:
        st.info("Sponsor or status data is not available in this dataset.")
        return

    sponsor_df = df[["Sponsor", "Status", "Start Date"]].copy()
    sponsor_df = sponsor_df.dropna(subset=["Sponsor"])
    sponsor_df = sponsor_df[sponsor_df["Sponsor"].str.strip() != ""]

    if sponsor_df.empty:
        st.info("No sponsor data found.")
        return

    # Classify sponsor type
    sponsor_df["Sponsor Type"] = sponsor_df["Sponsor"].apply(classify_sponsor_type)

    # ---- Bar Chart: Top Sponsors by Status ----
    grouped = (
        sponsor_df.groupby(["Sponsor", "Status"])
        .size()
        .reset_index(name="Trial Count")
    )

    top_sponsors = (
        grouped.groupby("Sponsor")["Trial Count"].sum()
        .sort_values(ascending=False)
        .head(15)
        .index
    )

    filtered = grouped[grouped["Sponsor"].isin(top_sponsors)]

    # st.subheader("Top Sponsors by Trial Status")
    fig1 = px.bar(
        filtered,
        x="Trial Count",
        y="Sponsor",
        color="Status",
        orientation="h",
        title="Top Sponsors by Trial Status",
        labels={"Trial Count": "Number of Trials"},
        height=600,
        color_discrete_sequence=px.colors.qualitative.Set2
    )
    fig1.update_layout(yaxis={"categoryorder": "total ascending"}, font=dict(size=14))
    st.plotly_chart(fig1, use_container_width=True)

    # ---- Time Trend of Sponsorship ----
    # st.subheader("Sponsorship Trends Over Time")
    # st.markdown("### Trial Start Timeline")

    sponsor_df["Start Date"] = pd.to_datetime(sponsor_df["Start Date"], errors="coerce")
    trend_data = (
        sponsor_df.dropna(subset=["Start Date"])
        .groupby([pd.Grouper(key="Start Date", freq="Y"), "Sponsor Type"])
        .size()
        .reset_index(name="Trials Started")
    )

    if trend_data.empty:
        st.info("No valid start date data to show trends.")
    else:
        fig2 = px.line(
            trend_data,
            x="Start Date",
            y="Trials Started",
            color="Sponsor Type",
            markers=True,
            labels={"Start Date": "Year", "Trials Started": "Number of Trials"},
            title="Annual Sponsor Activity by Sponsor Type",
            height=500,
            color_discrete_map={"Industry": "#636EFA", "Academic": "#EF553B"}
        )
        fig2.update_traces(mode="lines+markers")
        fig2.update_layout(xaxis_title="Year", yaxis_title="Trial Count", font=dict(size=14))
        st.plotly_chart(fig2, use_container_width=True)

    # ---- Optional Summary Table ----
    # st.subheader("#### Sponsor Summary Table")
    st.markdown("#### Sponsor Summary Table")
    summary = (
        sponsor_df.groupby(["Sponsor", "Sponsor Type"])
        .agg(Trials=("Sponsor", "count"))
        .sort_values("Trials", ascending=False)
        .reset_index()
    )
    st.dataframe(summary, use_container_width=True, height=500)
