# components/summary_table.py
import streamlit as st

def show_summary_table(df):
    # st.markdown("### Trial Summary Table")

    st.dataframe(
        df[["NCT ID", "Title", "Study Type", "Phase", "Status", "Sponsor", "Primary Outcome"]],
        use_container_width=True,
        height=600
    )

    st.markdown("You can scroll, sort, and filter the table above.")
