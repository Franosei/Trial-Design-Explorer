from pathlib import Path

BASE_API_URL = "https://clinicaltrials.gov/api/v2/studies"
DEFAULT_CONDITION = "Sepsis"
DEFAULT_PAGE_SIZE = 1000
DEFAULT_REPORT_FILE = "trial_protocol_report.pdf"

APP_TITLE = "Trial Design Explorer"
APP_SUBTITLE = (
    "Clinical trial design intelligence for protocol benchmarking, evidence review, "
    "and traceable reporting."
)

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"

COMMON_CONDITIONS = [
    "Sepsis",
    "ARDS",
    "Pneumonia",
    "COVID-19",
    "Heart Failure",
    "Asthma",
    "Stroke",
    "Hypertension",
    "Cancer",
    "Diabetes",
    "Renal Failure",
    "Liver Disease",
    "ICU Delirium",
    "Myocardial Infarction",
    "Chronic Obstructive Pulmonary Disease",
    "Cardiac Arrest",
    "Traumatic Brain Injury",
    "Multiple Organ Dysfunction Syndrome",
    "Acute Kidney Injury",
    "Lung Cancer",
    "Breast Cancer",
    "Colorectal Cancer",
    "Pancreatic Cancer",
    "Prostate Cancer",
    "Ventilator-Associated Pneumonia",
    "Hemorrhagic Stroke",
    "Ischemic Stroke",
    "Deep Vein Thrombosis",
    "Pulmonary Embolism",
    "Anemia",
    "Leukemia",
    "Meningitis",
    "Tuberculosis",
    "HIV",
    "Influenza",
    "COVID-19 Reinfection",
    "Obesity",
    "Malnutrition",
    "Burn Injuries",
    "Surgical Site Infections",
    "Nosocomial Infections",
    "Clostridium difficile Infection",
    "Delirium",
    "Postoperative Complications",
    "ARDS Secondary to Sepsis",
    "Neutropenia",
    "Liver Cirrhosis",
    "Hepatitis B",
    "Hepatitis C",
    "Acute Respiratory Failure",
    "Respiratory Syncytial Virus",
]

REGISTRY_TABS = [
    "Overview",
    "Durations",
    "Locations",
    "Outcomes",
    "Summary",
    "Timeline",
    "Sponsors",
]

PROTOCOL_FIELDS = [
    "title",
    "condition",
    "phase",
    "study_type",
    "sponsor",
    "sample_size",
    "arms_count",
    "allocation",
    "masking",
    "intervention_model",
    "primary_purpose",
    "comparator",
    "intervention_description",
    "target_population",
    "geography_focus",
    "endpoint_focus",
    "start_date",
    "completion_date",
    "primary_endpoints",
    "secondary_endpoints",
]
