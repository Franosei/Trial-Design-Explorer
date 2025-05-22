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
    template="plotly",  # Theme-aware background
    margin=dict(t=60, b=40, l=100, r=30),  # Reduce l=250 if not needed
    height=min(len(df), 1200),  # Dynamically based on bar count
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
    template="plotly",  # Theme-aware background
    margin=dict(t=60, b=40, l=100, r=30),  # Reduce l=250 if not needed
    height=min(len(df), 1200),  # Dynamically based on bar count
    showlegend=True
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
            template="plotly", 
            height=min(len(df), 1200),
            margin=dict(t=60, b=40, l=100, r=30),
            legend_title="Status",
            showlegend=True
        )
        

        st.plotly_chart(fig_status, use_container_width=False, key=f"status_pie_chart_{unique_id}")
    else:
        st.info("Trial status information is not available.")
