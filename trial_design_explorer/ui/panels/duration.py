import pandas as pd
import plotly.express as px
import streamlit as st


def compute_trial_durations(df):
    durations = df.copy()
    start_dates = pd.to_datetime(durations["Start Date"], errors="coerce")
    end_dates = pd.to_datetime(durations["Completion Date"], errors="coerce")
    durations["Duration (months)"] = ((end_dates - start_dates).dt.days / 30).round(1)
    return durations.dropna(subset=["Duration (months)"])


def show_duration_panel(df):
    duration_df = compute_trial_durations(df)
    if duration_df.empty:
        st.info("No trial duration data is available.")
        return

    col1, col2 = st.columns(2)
    with col1:
        fig = px.histogram(
            duration_df,
            x="Duration (months)",
            color="Status",
            nbins=24,
            title="Trial Duration Distribution",
            color_discrete_sequence=px.colors.qualitative.Set2,
            opacity=0.8,
        )
        fig.update_layout(template="plotly_white", height=420, margin=dict(t=60, b=20, l=20, r=20))
        st.plotly_chart(fig, width="stretch")

    with col2:
        phase_df = duration_df[duration_df["Phase"].fillna("N/A") != "N/A"].copy()
        if phase_df.empty:
            st.info("No phase-tagged duration data is available.")
        else:
            fig = px.box(
                phase_df,
                x="Phase",
                y="Duration (months)",
                color="Phase",
                title="Duration Spread by Phase",
                color_discrete_sequence=px.colors.qualitative.Bold,
            )
            fig.update_layout(template="plotly_white", height=420, margin=dict(t=60, b=20, l=20, r=20), showlegend=False)
            st.plotly_chart(fig, width="stretch")

    summary = (
        duration_df[["NCT ID", "Title", "Study Type", "Phase", "Status", "Duration (months)"]]
        .sort_values("Duration (months)", ascending=False)
        .reset_index(drop=True)
    )
    st.markdown("#### Duration Benchmark Table")
    st.dataframe(summary, width="stretch", height=450)
