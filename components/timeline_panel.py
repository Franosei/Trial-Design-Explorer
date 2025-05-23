import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

def show_timeline_panel(df):
    # st.markdown("### Trial Start Timeline")

    # Check if "Start Date" exists
    if "Start Date" not in df.columns:
        st.info("Start Date not available in this dataset.")
        return

    # Preprocess the data
    df = df.copy()
    df["Start Year"] = pd.to_datetime(df["Start Date"], errors="coerce").dt.year
    timeline_df = df["Start Year"].value_counts().sort_index().reset_index()
    timeline_df.columns = ["Year", "Trials Started"]

    # Create the bar chart with an improved color scale
    fig = px.bar(
        timeline_df,
        x="Year",
        y="Trials Started",
        title="Number of Trials Started by Year",
        color="Trials Started",
        color_continuous_scale="Turbo"  # More vibrant and visible
    )

    # Update layout for better appearance
    fig.update_layout(
        template="plotly",
        margin=dict(t=50, b=50, r=30, l=30),
     
    )

    # Display the chart
    st.plotly_chart(fig, use_container_width=True)
    
    
    #    # ------------------ Trials by Year and Phase ------------------
    if "Phase" in df.columns:
        df_phase = df.copy()
        df_phase["Start Year"] = pd.to_datetime(df_phase["Start Date"], errors="coerce").dt.year

        # Normalize Phase column: merge NA and N/A as 'N/A'
        df_phase["Phase"] = df_phase["Phase"].replace({"NA": "N/A", "NaN": "N/A", pd.NA: "N/A"}).fillna("N/A")

        df_phase = df_phase.dropna(subset=["Start Year"])

        phase_timeline_df = df_phase.groupby(["Start Year", "Phase"]).size().reset_index(name="Count")

        fig_phase_year = px.bar(
            phase_timeline_df,
            x="Start Year",
            y="Count",
            color="Phase",
            title="Number of Trials by Year and Phase",
            color_discrete_sequence=px.colors.qualitative.Set2,
            height=500
        )

        fig_phase_year.update_layout(
            barmode="stack",
            template="plotly",
            margin=dict(t=60, b=40, l=100, r=30),
            xaxis_title="Year",
            yaxis_title="Number of Trials",
            legend_title="Phase",
        )

        st.plotly_chart(fig_phase_year, use_container_width=True)
    else:
        st.info("Phase information is not available for this dataset.")

    # Trials by Year for Top 10 Countries (Last 5 Years Only)
    if "Locations" in df.columns:
        location_records = []

        for _, row in df.iterrows():
            start_date = pd.to_datetime(row.get("Start Date"), errors="coerce")
            year = start_date.year if pd.notna(start_date) else None
            for loc in row.get("Locations", []):
                country = loc.get("country")
                if year and country:
                    location_records.append({"Start Year": year, "Country": country})

        location_df = pd.DataFrame(location_records).dropna()

        if not location_df.empty:
            # Filter to only include the last 5 years dynamically
            current_year = datetime.now().year
            location_df = location_df[location_df["Start Year"] >= current_year - 5]

            # Get top 10 countries by total trial count in the last 5 years
            top_countries = (
                location_df["Country"]
                .value_counts()
                .nlargest(10)
                .index
            )

            filtered_df = location_df[location_df["Country"].isin(top_countries)]

            timeline_data = (
                filtered_df.groupby(["Start Year", "Country"])
                .size()
                .reset_index(name="Trial Count")
            )

            fig = px.line(
                timeline_data,
                x="Start Year",
                y="Trial Count",
                color="Country",
                title="Top 10 Countries – Trials Started Over Time (Last 5 Years)",
                line_shape="spline",
                markers=True,
                color_discrete_sequence=px.colors.qualitative.Set2
            )

            fig.update_layout(
                template="plotly_white",
                margin=dict(t=60, b=40, l=80, r=40),
                xaxis_title="Year",
                yaxis_title="Number of Trials",
                legend_title="Country",
                height=550
            )

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No valid location data available for timeline plotting.")
    else:
        st.info("No location field in dataset.")
