import pandas as pd
import plotly.express as px
import streamlit as st


def classify_sponsor_type(name):
    if not isinstance(name, str):
        return "Unknown"

    name = name.lower()
    academic_keywords = ["university", "college", "institute", "hospital", "nhs", "school", "center", "centre", "clinic"]
    return "Academic" if any(keyword in name for keyword in academic_keywords) else "Industry"


def show_sponsor_panel(df):
    if "Sponsor" not in df.columns or "Status" not in df.columns:
        st.info("Sponsor data is not available.")
        return

    sponsor_df = df[["Sponsor", "Status", "Start Date"]].copy()
    sponsor_df = sponsor_df.dropna(subset=["Sponsor"])
    sponsor_df = sponsor_df[sponsor_df["Sponsor"].astype(str).str.strip() != ""]
    if sponsor_df.empty:
        st.info("Sponsor data is not available.")
        return

    sponsor_df["Sponsor Type"] = sponsor_df["Sponsor"].apply(classify_sponsor_type)
    grouped = sponsor_df.groupby(["Sponsor", "Status"]).size().reset_index(name="Trial Count")
    top_sponsors = grouped.groupby("Sponsor")["Trial Count"].sum().sort_values(ascending=False).head(15).index
    filtered = grouped[grouped["Sponsor"].isin(top_sponsors)]

    fig = px.bar(
        filtered,
        x="Trial Count",
        y="Sponsor",
        color="Status",
        orientation="h",
        title="Top Sponsors by Operational Status",
        color_discrete_sequence=px.colors.qualitative.Set2,
        height=620,
    )
    fig.update_layout(template="plotly_white", yaxis={"categoryorder": "total ascending"}, margin=dict(t=60, b=20, l=20, r=20))
    st.plotly_chart(fig, width="stretch")

    sponsor_df["Start Date"] = pd.to_datetime(sponsor_df["Start Date"], errors="coerce")
    trend_df = (
        sponsor_df.dropna(subset=["Start Date"])
        .groupby([pd.Grouper(key="Start Date", freq="YE"), "Sponsor Type"])
        .size()
        .reset_index(name="Trials Started")
    )

    if not trend_df.empty:
        fig = px.line(
            trend_df,
            x="Start Date",
            y="Trials Started",
            color="Sponsor Type",
            markers=True,
            title="Annual Sponsor Activity",
            color_discrete_map={"Industry": "#355C7D", "Academic": "#C06C84", "Unknown": "#6C757D"},
            height=460,
        )
        fig.update_layout(template="plotly_white", margin=dict(t=60, b=20, l=20, r=20))
        st.plotly_chart(fig, width="stretch")

    summary = (
        sponsor_df.groupby(["Sponsor", "Sponsor Type"])
        .agg(Trials=("Sponsor", "count"))
        .sort_values("Trials", ascending=False)
        .reset_index()
    )
    st.markdown("#### Sponsor Summary")
    st.dataframe(summary, width="stretch", height=420)
