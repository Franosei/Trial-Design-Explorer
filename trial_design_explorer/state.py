SESSION_DEFAULTS = {
    "workspace": "Protocol Intelligence",
    "registry_tab": "Overview",
    "df_trials": None,
    "protocol_meta": None,
    "protocol_text": "",
    "matching_trials": None,
    "latest_comparison": "",
    "comparison_metrics": {},
    "comparison_recommendations": [],
    "protocol_stage": "Intake",
    "audit_log": [],
    "chat_history": [],
}


def ensure_session_defaults(session_state):
    for key, value in SESSION_DEFAULTS.items():
        if key not in session_state:
            session_state[key] = value
