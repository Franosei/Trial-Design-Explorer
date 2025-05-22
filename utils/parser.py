# utils/parser.py

import pandas as pd

def parse_trials_to_df(api_response):
    trials = []

    for study in api_response.get("studies", []):
        try:
            p = study.get("protocolSection", {})

            # Identification and Title
            id_module = p.get("identificationModule", {})
            nct_id = id_module.get("nctId")
            title = id_module.get("briefTitle", "Untitled Trial")

            # Status and Dates
            status_module = p.get("statusModule", {})
            status = status_module.get("overallStatus", "Unknown")
            start_date = status_module.get("startDateStruct", {}).get("date")
            completion_date = status_module.get("completionDateStruct", {}).get("date")

            # Study Design
            design_module = p.get("designModule", {})
            study_type = design_module.get("studyType", "N/A")
            phases = ", ".join(design_module.get("phases", [])) if design_module.get("phases") else "N/A"

            # Sponsor
            sponsor_module = p.get("sponsorCollaboratorsModule", {})
            sponsor = sponsor_module.get("leadSponsor", {}).get("name", "Unknown Sponsor")

            # Primary Outcomes
            outcomes_module = p.get("outcomesModule", {})
            primary_outcomes = ", ".join([
                o.get("measure", "") for o in outcomes_module.get("primaryOutcomes", [])
            ]) if outcomes_module.get("primaryOutcomes") else "N/A"

            # Locations with Geo
            location_module = p.get("contactsLocationsModule", {})
            raw_locations = location_module.get("locations", [])
            locations = []
            for loc in raw_locations:
                geo = loc.get("geoPoint", {})
                locations.append({
                    "city": loc.get("city"),
                    "country": loc.get("country"),
                    "lat": geo.get("lat"),
                    "lon": geo.get("lon")
                })

            # Assemble Trial Dictionary
            trials.append({
                "NCT ID": nct_id,
                "Title": title,
                "Study Type": study_type,
                "Phase": phases,
                "Status": status,
                "Start Date": start_date,
                "Completion Date": completion_date,
                "Sponsor": sponsor,
                "Primary Outcome": primary_outcomes,
                "Locations": locations
            })

        except Exception as e:
            print(f"[Error] Failed to parse study: {e}")
            continue

    return pd.DataFrame(trials)
