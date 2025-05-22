import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

def compute_trial_durations(df):
    df = df.copy()

    def calc_months(start, end):
        try:
            start_date = pd.to_datetime(start)
            end_date = pd.to_datetime(end)
            duration = (end_date - start_date).days // 30
            return duration if duration > 0 else None
        except:
            return None

    df["Duration (months)"] = df.apply(
        lambda row: calc_months(row["Start Date"], row["Completion Date"]), axis=1
    )
    return df.dropna(subset=["Duration (months)"])


def show_duration_panel(df):
    # st.markdown("### ⏳ Trial Duration Distribution")

    df_duration = compute_trial_durations(df)

    if df_duration.empty:
        st.info("No trial duration data available.")
        return

    # Filter down to relevant columns
    if "Status" not in df_duration.columns:
        df_duration["Status"] = "Unknown"

    # Histogram grouped by status
    fig = px.histogram(
        df_duration,
        x="Duration (months)",
        color="Status",
        nbins=20,
        title="Trial Duration Histogram",
        color_discrete_sequence=px.colors.qualitative.Set2,
        barmode="overlay",  # Options: "group", "stack", "overlay"
        opacity=0.75
    )
    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(color="#333333"),
        margin=dict(t=40, b=20),
        legend_title_text="Status"
    )

    st.plotly_chart(fig, use_container_width=True)
    
    
        # ------------------ Median Duration by Phase (Pie Chart) ------------------
    # st.markdown("#### Median Trial Duration per Phase")

    # Clean & filter
    df_phase_avg = df_duration[df_duration["Phase"] != "N/A"].copy()
    phase_avg_duration = (
        df_phase_avg.groupby("Phase")["Duration (months)"]
        .median()
        .reset_index()
        .sort_values("Duration (months)", ascending=False)
    )

    if phase_avg_duration.empty:
        st.info("No valid phase-duration data to display.")
        return

    fig_pie_avg = px.pie(
        phase_avg_duration,
        names="Phase",
        values="Duration (months)",
        title="Median Trial Duration by Phase",
        hole=0.4,
        color_discrete_sequence=px.colors.qualitative.Vivid
    )

    fig_pie_avg.update_traces(
        textinfo="percent",  # ONLY percentage
        pull=[0.03] * len(phase_avg_duration),
        marker=dict(line=dict(color="white", width=1)),
        textfont_size=14
    )

    fig_pie_avg.update_layout(
        height=500,
        margin=dict(t=40, b=40, l=80, r=80),
        font=dict(size=14, color="#333333"),
        showlegend=True,
        legend_title="Phase"
    )

    st.plotly_chart(fig_pie_avg, use_container_width=True)


    # Styled Summary Table
    st.markdown("#### Duration Summary Table")

    styled_df = df_duration[["NCT ID", "Title", "Study Type", "Phase", "Status", "Duration (months)"]].style\
        .background_gradient(subset=["Duration (months)"], cmap='YlGnBu')\
        .set_table_styles([
            {'selector': 'thead th',
             'props': [('background-color', '#4f81bd'), ('color', 'white'), ('font-weight', 'bold')]},
            {'selector': 'tbody td',
             'props': [('border', '1px solid #ddd'), ('padding', '8px')]},
            {'selector': 'tbody tr:nth-child(even)',
             'props': [('background-color', '#f9f9f9')]},
            {'selector': 'tbody tr:hover',
             'props': [('background-color', '#f1f1f1')]}
        ])\
        .format({'Duration (months)': '{:.0f}'})\
        .set_properties(**{
            'text-align': 'left',
            'border-radius': '4px',
        })

    st.dataframe(styled_df, use_container_width=True, height=500)
