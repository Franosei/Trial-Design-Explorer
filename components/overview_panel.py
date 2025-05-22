import streamlit as st
import plotly.express as px
import uuid

def show_overview(df):
    if df.empty:
        st.warning("No data available to visualize.")
        return

    unique_id = str(uuid.uuid4())

    # ------------------ Study Type Pie Chart ------------------
    type_counts = df["Study Type"].value_counts().reset_index()
    type_counts.columns = ["Study Type", "Count"]

    # st.markdown("#### Overview")
    fig_pie = px.pie(
        type_counts,
        names="Study Type",
        values="Count",
        title="Study Type Distribution",
        hole=0.4,
        color_discrete_sequence=px.colors.qualitative.Set3
    )
    fig_pie.update_traces(
        textinfo="percent+label",
        pull=[0.05]*len(type_counts),
        marker=dict(line=dict(color="#000000", width=1))
    )
    fig_pie.update_layout(
        height=450,
        margin=dict(t=40, b=40, r=40, l=40),
        font=dict(size=13, color="#333333"),
        showlegend=True
    )
    st.plotly_chart(fig_pie, use_container_width=True, key=f"study_type_pie_{unique_id}")

    # ------------------ Trial Phase Bar Chart ------------------
    phase_counts = df["Phase"].value_counts().reset_index()
    phase_counts.columns = ["Phase", "Count"]

    fig2 = px.bar(
        phase_counts,
        x="Phase",
        y="Count",
        color="Phase",
        color_discrete_sequence=px.colors.qualitative.Pastel, 
        title="Trial Phases",
        height=400
    )
    fig2.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(color="#333333"),
        title_font=dict(size=20),
        margin=dict(t=40, b=10)
    )
    st.plotly_chart(fig2, use_container_width=True, key=f"phase_chart_{unique_id}")

    # ------------------ Trial Status Pie Chart ------------------
    if "Status" in df.columns:
        status_counts = df["Status"].value_counts().reset_index()
        status_counts.columns = ["Status", "Count"]

        fig_status = px.pie(
            status_counts,
            names="Status",
            values="Count",
            hole=0.5,
            title="Recruitment Status of Trials",
            color_discrete_sequence=px.colors.sequential.Cividis
        )
        fig_status.update_layout(
            height=600,
            width=1000,
            margin=dict(t=60, b=80, l=80, r=250),
            legend_title="Status",
            legend=dict(
                font=dict(size=12),
                orientation="v",
                yanchor="middle",
                y=0.5,
                xanchor="right",
                x=1.25
            ),
            font=dict(size=14, color="#333333"),
            showlegend=True
        )

        st.plotly_chart(fig_status, use_container_width=False, key=f"status_pie_chart_{unique_id}")
    else:
        st.info("Trial status information is not available.")
