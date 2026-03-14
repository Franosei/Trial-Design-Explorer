from trial_design_explorer.domain import AuditEvent, ProvenanceRecord
from trial_design_explorer.services.openai_service import configured_model_name


def current_utc_timestamp() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_provenance_record(
    source: str,
    tool: str,
    notes: str | None = None,
    source_sections: list[str] | None = None,
) -> ProvenanceRecord:
    return ProvenanceRecord(
        source=source,
        tool=tool,
        timestamp=current_utc_timestamp(),
        model=configured_model_name(),
        notes=notes,
        source_sections=source_sections or [],
    )


def build_audit_event(
    action: str,
    details: str,
    actor: str = "system",
    artifact_type: str | None = None,
    artifact_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    event = AuditEvent(
        action=action,
        details=details,
        timestamp=current_utc_timestamp(),
        actor=actor,
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        metadata=metadata or {},
    )
    return event.to_dict()

