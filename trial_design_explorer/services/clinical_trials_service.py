from collections import Counter

import pandas as pd
import requests

from trial_design_explorer.config import BASE_API_URL, DEFAULT_PAGE_SIZE


def fetch_trials_by_condition(condition: str, limit: int = DEFAULT_PAGE_SIZE):
    try:
        response = requests.get(
            BASE_API_URL,
            params={"query.term": condition, "pageSize": limit},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None


def parse_trials_to_df(api_response) -> pd.DataFrame:
    trials: list[dict] = []

    for study in api_response.get("studies", []):
        try:
            protocol_section = study.get("protocolSection", {})

            identification = protocol_section.get("identificationModule", {})
            status_module = protocol_section.get("statusModule", {})
            design_module = protocol_section.get("designModule", {})
            sponsor_module = protocol_section.get("sponsorCollaboratorsModule", {})
            outcomes_module = protocol_section.get("outcomesModule", {})
            conditions_module = protocol_section.get("conditionsModule", {})
            contacts_module = protocol_section.get("contactsLocationsModule", {})
            arms_module = protocol_section.get("armsInterventionsModule", {})
            eligibility_module = protocol_section.get("eligibilityModule", {})
            enrollment_module = protocol_section.get("designModule", {})

            raw_locations = contacts_module.get("locations", [])
            locations = []
            for location in raw_locations:
                geo = location.get("geoPoint", {})
                locations.append(
                    {
                        "city": location.get("city"),
                        "country": location.get("country"),
                        "facility": location.get("facility"),
                        "lat": geo.get("lat"),
                        "lon": geo.get("lon"),
                    }
                )

            primary_outcomes = ", ".join(
                outcome.get("measure", "")
                for outcome in outcomes_module.get("primaryOutcomes", [])
                if outcome.get("measure")
            ) or "N/A"

            interventions = ", ".join(
                intervention.get("type", "")
                for intervention in arms_module.get("interventions", [])
                if intervention.get("type")
            ) or "N/A"

            intervention_names = ", ".join(
                intervention.get("name", "")
                for intervention in arms_module.get("interventions", [])
                if intervention.get("name")
            ) or "N/A"

            collaborator_names = ", ".join(
                collaborator.get("name", "")
                for collaborator in sponsor_module.get("collaborators", [])
                if collaborator.get("name")
            ) or "N/A"

            country_count = len({location.get("country") for location in locations if location.get("country")})

            trials.append(
                {
                    "NCT ID": identification.get("nctId"),
                    "Title": identification.get("briefTitle", "Untitled Trial"),
                    "Conditions": ", ".join(conditions_module.get("conditions", [])) or "N/A",
                    "Study Type": design_module.get("studyType", "N/A"),
                    "Phase": ", ".join(design_module.get("phases", [])) or "N/A",
                    "Status": status_module.get("overallStatus", "Unknown"),
                    "Start Date": status_module.get("startDateStruct", {}).get("date"),
                    "Completion Date": status_module.get("completionDateStruct", {}).get("date"),
                    "Enrollment": enrollment_module.get("enrollmentInfo", {}).get("count"),
                    "Enrollment Type": enrollment_module.get("enrollmentInfo", {}).get("type", "N/A"),
                    "Allocation": design_module.get("designInfo", {}).get("allocation", "N/A"),
                    "Intervention Model": design_module.get("designInfo", {}).get("interventionModel", "N/A"),
                    "Masking": design_module.get("designInfo", {}).get("maskingInfo", {}).get("masking", "N/A"),
                    "Primary Purpose": design_module.get("designInfo", {}).get("primaryPurpose", "N/A"),
                    "Intervention Types": interventions,
                    "Interventions": intervention_names,
                    "Sponsor": sponsor_module.get("leadSponsor", {}).get("name", "Unknown Sponsor"),
                    "Collaborators": collaborator_names,
                    "Sex": eligibility_module.get("sex", "N/A"),
                    "Minimum Age": eligibility_module.get("minimumAge", "N/A"),
                    "Maximum Age": eligibility_module.get("maximumAge", "N/A"),
                    "Healthy Volunteers": eligibility_module.get("healthyVolunteers", "N/A"),
                    "Primary Outcome": primary_outcomes,
                    "Primary Outcome Count": len(outcomes_module.get("primaryOutcomes", [])),
                    "Arms Count": len(arms_module.get("armGroups", [])),
                    "Location Count": len(locations),
                    "Country Count": country_count,
                    "Locations": locations,
                }
            )
        except Exception:
            continue

    return pd.DataFrame(trials)


def median_trial_duration_months(trials_df: pd.DataFrame) -> int | None:
    if trials_df.empty:
        return None

    start_dates = pd.to_datetime(trials_df["Start Date"], errors="coerce")
    end_dates = pd.to_datetime(trials_df["Completion Date"], errors="coerce")
    months = ((end_dates - start_dates).dt.days / 30).dropna()
    if months.empty:
        return None
    return int(months.median())


def count_countries(trials_df: pd.DataFrame) -> int:
    countries = {
        location.get("country")
        for locations in trials_df.get("Locations", [])
        for location in locations
        if isinstance(location, dict) and location.get("country")
    }
    return len(countries)


def most_common_primary_outcome(trials_df: pd.DataFrame) -> tuple[str, int] | None:
    if "Primary Outcome" not in trials_df or trials_df["Primary Outcome"].dropna().empty:
        return None

    outcomes = []
    for value in trials_df["Primary Outcome"].dropna().astype(str):
        outcomes.extend(part.strip() for part in value.split(",") if part.strip())

    if not outcomes:
        return None

    outcome, count = Counter(outcomes).most_common(1)[0]
    return outcome, count
