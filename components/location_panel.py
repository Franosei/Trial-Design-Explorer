import streamlit as st
import pandas as pd
import plotly.express as px

continent_regions = {
    "All": {},
    "Africa": {"scope": "africa"},
    "Asia": {"scope": "asia"},
    "Europe": {"scope": "europe"},
    "North America": {"scope": "north america"},
    "South America": {"scope": "south america"}
}

def extract_locations(df):
    """Extracts geocoded trial locations, including status for coloring."""
    locations = []

    for _, row in df.iterrows():
        locs = row.get("Locations", [])
        for loc in locs:
            lat = loc.get("lat")
            lon = loc.get("lon")
            if lat is not None and lon is not None:
                locations.append({
                    "NCT ID": row["NCT ID"],
                    "Title": row["Title"],
                    "Status": row.get("Status", "Unknown"),
                    "City": loc.get("city", ""),
                    "Country": loc.get("country", ""),
                    "Latitude": lat,
                    "Longitude": lon
                })

    return pd.DataFrame(locations)


def show_location_panel(df):
    # st.markdown("### Global Trial Site Distribution")

    if "Locations" not in df.columns:
        st.info("No location data found in this dataset.")
        return

    df_map = extract_locations(df)

    if df_map.empty:
        st.info("No valid trial location coordinates available.")
        return

    # ---- Scroll Anchor ----
    st.markdown("<div id='location-tab-anchor'></div>", unsafe_allow_html=True)

    # ---- Continent Filter ----
    continent = st.selectbox(
        "🌐 Focus Region",
        options=list(continent_regions.keys()),
        index=0,
        help="Zoom to a specific continent"
    )

    # ---- Scroll Fix: Trigger scroll only on first continent selection ----
    if "location_scroll_patch" not in st.session_state:
        st.session_state["location_scroll_patch"] = True
        st.markdown("""
            <script>
                const anchor = document.getElementById("location-tab-anchor");
                if (anchor) {
                    anchor.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            </script>
        """, unsafe_allow_html=True)

    region_config = continent_regions.get(continent, {"scope": "All"})

    # ---- Plot Map ----
    fig = px.scatter_geo(
        df_map,
        lat="Latitude",
        lon="Longitude",
        color="Status",
        hover_name="Country",
        hover_data={
            "City": True,
            "Title": True,
            "Status": True
        },
        color_discrete_sequence=px.colors.qualitative.Set2,
        title=f"Trial Site Locations by Recruitment Status ({continent})"
    )

    fig.update_layout(
        geo=dict(
            showland=True,
            landcolor="whitesmoke",
            countrycolor="lightgray",
            showcountries=True,
            showcoastlines=True,
            projection_type="natural earth",
            **region_config
        ),
        font=dict(color="#333333", size=14),
        margin=dict(t=40, b=10, r=10, l=10),
        height=800,
        legend_title_text="Recruitment Status"
    )

    st.plotly_chart(fig, use_container_width=True)

    # ---- Summary Table ----
    st.markdown("#### Location Summary Table")

    df_grouped = (
        df_map.groupby(["NCT ID", "Title", "Status"])
        .agg({
            "Country": lambda x: ", ".join(sorted(set(x))),
            "City": lambda x: ", ".join(sorted(set(x))),
            "Latitude": "count"
        })
        .rename(columns={
            "Country": "Countries",
            "City": "Cities",
            "Latitude": "Location Count"
        })
        .reset_index()
    )

    st.dataframe(df_grouped, use_container_width=True, height=600)
