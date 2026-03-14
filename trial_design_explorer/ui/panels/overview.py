import plotly.express as px
import streamlit as st


def show_overview_panel(df):
    if df.empty:
        st.warning("No data is available for overview analysis.")
        return

    study_type_counts = df["Study Type"].fillna("Unknown").value_counts().reset_index()
    study_type_counts.columns = ["Study Type", "Count"]
    phase_counts = df["Phase"].fillna("Unknown").value_counts().reset_index()
    phase_counts.columns = ["Phase", "Count"]
    status_counts = df["Status"].fillna("Unknown").value_counts().reset_index()
    status_counts.columns = ["Status", "Count"]

    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(
            study_type_counts,
            x="Count",
            y="Study Type",
            orientation="h",
            title="Study Type Distribution",
            color="Study Type",
            color_discrete_sequence=px.colors.qualitative.Safe,
        )
        fig.update_layout(template="plotly_white", height=420, margin=dict(t=60, b=20, l=20, r=20), showlegend=False)
        st.plotly_chart(fig, width="stretch")

    with col2:
        fig = px.bar(
            phase_counts,
            x="Phase",
            y="Count",
            title="Phase Mix",
            color="Phase",
            color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        fig.update_layout(template="plotly_white", height=420, margin=dict(t=60, b=20, l=20, r=20), showlegend=False)
        st.plotly_chart(fig, width="stretch")

    fig = px.bar(
        status_counts,
        x="Count",
        y="Status",
        orientation="h",
        title="Operational Status Distribution",
        color="Status",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(template="plotly_white", height=450, margin=dict(t=60, b=20, l=20, r=20), showlegend=False)
    st.plotly_chart(fig, width="stretch")
