from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ProvenanceRecord:
    source: str
    tool: str
    timestamp: str
    model: str | None = None
    notes: str | None = None
    source_sections: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ProtocolMetadata:
    title: str | None = None
    condition: str | None = None
    phase: str | None = None
    study_type: str | None = None
    sponsor: str | None = None
    sample_size: str | None = None
    arms_count: str | None = None
    allocation: str | None = None
    masking: str | None = None
    intervention_model: str | None = None
    primary_purpose: str | None = None
    comparator: str | None = None
    intervention_description: str | None = None
    target_population: str | None = None
    geography_focus: str | None = None
    endpoint_focus: str | None = None
    start_date: str | None = None
    completion_date: str | None = None
    primary_endpoints: str | None = None
    secondary_endpoints: str | None = None
    description: str | None = None
    confidence: str | None = None
    confirmation_status: str = "draft"
    provenance: ProvenanceRecord | None = None

    def update_from_mapping(self, data: dict[str, Any]) -> None:
        for key, value in data.items():
            if key == "provenance":
                if isinstance(value, ProvenanceRecord):
                    self.provenance = value
                elif isinstance(value, dict) and value:
                    self.provenance = ProvenanceRecord(
                        source=value.get("source", "session"),
                        tool=value.get("tool", "session"),
                        timestamp=value.get("timestamp", ""),
                        model=value.get("model"),
                        notes=value.get("notes"),
                        source_sections=value.get("source_sections", []),
                    )
                continue
            if hasattr(self, key) and value not in (None, ""):
                setattr(self, key, value)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    def to_display_dict(self) -> dict[str, Any]:
        data = self.to_dict()
        data.pop("description", None)
        return data


@dataclass(slots=True)
class EvidenceReference:
    source_name: str
    locator: str
    detail: str
    confidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AuditEvent:
    action: str
    details: str
    timestamp: str
    actor: str = "system"
    artifact_type: str | None = None
    artifact_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ChatMessage:
    role: str
    text: str
    timestamp: str
    citations: list[EvidenceReference] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


@dataclass(slots=True)
class ProjectRun:
    workspace: str
    status: str
    timestamp: str
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
