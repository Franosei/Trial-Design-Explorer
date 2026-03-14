import pandas as pd
import streamlit as st


def show_summary_panel(df):
    if df.empty:
        st.info("No trial summary is available.")
        return

    col1, col2 = st.columns(2)
    with col1:
        status_summary = (
            df["Status"]
            .fillna("Unknown")
            .value_counts()
            .rename_axis("Status")
            .reset_index(name="Trial Count")
        )
        st.markdown("#### Status Summary")
        st.dataframe(status_summary, width="stretch", height=260)

    with col2:
        phase_summary = (
            df["Phase"]
            .fillna("N/A")
            .value_counts()
            .rename_axis("Phase")
            .reset_index(name="Trial Count")
        )
        st.markdown("#### Phase Summary")
        st.dataframe(phase_summary, width="stretch", height=260)

    table_columns = [
        "NCT ID",
        "Title",
        "Conditions",
        "Study Type",
        "Phase",
        "Status",
        "Enrollment",
        "Sponsor",
        "Primary Outcome",
    ]
    preview = df[[column for column in table_columns if column in df.columns]].copy()
    preview["Enrollment"] = pd.to_numeric(preview.get("Enrollment"), errors="coerce")

    st.markdown("#### Trial Detail Table")
    st.dataframe(preview, width="stretch", height=580)
