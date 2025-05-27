# components/summary_table.py
import streamlit as st
from wordcloud import WordCloud
import matplotlib.pyplot as plt

def show_summary_table(df):

    st.markdown("You can scroll, sort, and filter the table above.")

    # Divider
    st.markdown("---")

    # Word Cloud by Trial Status
    st.markdown("### Word Cloud by Trial Status")
    
    # Status selection
    status_options = df["Status"].dropna().unique().tolist()
    status_options = sorted(status_options)
    selected_status = st.selectbox("Select trial status:", status_options)

    # Optional field to choose text source
    text_column = st.radio(
        "Choose text field for word cloud:",
        ["Title", "Primary Outcome"],
        horizontal=True
    )

    # Filter and generate word cloud
    filtered_df = df[df["Status"] == selected_status]

    if not filtered_df.empty:
        text_data = filtered_df[text_column].dropna().astype(str)
        combined_text = " ".join(text_data)

        wordcloud = WordCloud(width=800, height=400, background_color="white").generate(combined_text)
        st.subheader(f"{selected_status} Trials - Word Cloud ({text_column})")
        fig, ax = plt.subplots(figsize=(15, 6))
        ax.imshow(wordcloud, interpolation="bilinear")
        ax.axis("off")
        st.pyplot(fig)
        
        
        # Divider
        st.markdown("---")
        st.markdown("### Summary Table of Trials")
        # Display the trial summary table
        st.dataframe(
        df[["NCT ID", "Title", "Study Type", "Phase", "Status", "Sponsor", "Primary Outcome"]],
        use_container_width=True,
        height=600
    )
    else:
        st.warning("No trials found with the selected status.")
