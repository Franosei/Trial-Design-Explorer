# components/timeline_panel.py

import streamlit as st
import pandas as pd
import plotly.express as px

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
