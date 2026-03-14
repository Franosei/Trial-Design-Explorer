import pandas as pd
import plotly.express as px
import streamlit as st

CONTINENT_REGIONS = {
    "Global": {},
    "Africa": {"scope": "africa"},
    "Asia": {"scope": "asia"},
    "Europe": {"scope": "europe"},
    "North America": {"scope": "north america"},
    "South America": {"scope": "south america"},
}


def extract_locations(df):
    locations = []
    for _, row in df.iterrows():
        for location in row.get("Locations", []):
            lat = location.get("lat")
            lon = location.get("lon")
            if lat is None or lon is None:
                continue
            locations.append(
                {
                    "NCT ID": row["NCT ID"],
                    "Title": row["Title"],
                    "Status": row.get("Status", "Unknown"),
                    "City": location.get("city", ""),
                    "Country": location.get("country", ""),
                    "Latitude": lat,
                    "Longitude": lon,
                }
            )
    return pd.DataFrame(locations)


def show_location_panel(df):
    if "Locations" not in df.columns:
        st.info("No site location data is available.")
        return

    location_df = extract_locations(df)
    if location_df.empty:
        st.info("No geocoded trial sites are available in this cohort.")
        return

    region = st.selectbox("Region Focus", options=list(CONTINENT_REGIONS.keys()), index=0)
    region_config = CONTINENT_REGIONS[region]

    fig = px.scatter_geo(
        location_df,
        lat="Latitude",
        lon="Longitude",
        color="Status",
        hover_name="Country",
        hover_data={"City": True, "Title": True, "Status": True},
        color_discrete_sequence=px.colors.qualitative.Set2,
        title=f"Trial Site Distribution ({region})",
    )
    fig.update_layout(
        geo=dict(
            showland=True,
            landcolor="whitesmoke",
            countrycolor="lightgray",
            showcountries=True,
            showcoastlines=True,
            projection_type="natural earth",
            **region_config,
        ),
        template="plotly_white",
        height=650,
        margin=dict(t=60, b=10, l=10, r=10),
        legend_title_text="Status",
    )
    st.plotly_chart(fig, width="stretch")

    grouped = (
        location_df.groupby(["NCT ID", "Title", "Status"])
        .agg(
            Countries=("Country", lambda values: ", ".join(sorted(set(filter(None, values))))),
            Cities=("City", lambda values: ", ".join(sorted(set(filter(None, values))))),
            Location_Count=("Latitude", "count"),
        )
        .reset_index()
    )
    st.markdown("#### Site Distribution Table")
    st.dataframe(grouped, width="stretch", height=500)
