from dataclasses import asdict, dataclass, field
from typing import Any


# ── Evidence objects ────────────────────────────────────────────────────────────

@dataclass(slots=True)
class RegistryTrialRef:
    """
    Thin, auditable pointer to a specific ClinicalTrials.gov precedent study.
    Embedded inside EvidenceBundle to ground findings in real data.
    """
    nct_id: str
    title: str
    status: str
    phase: str | None = None
    enrollment: int | None = None
    sponsor: str | None = None
    start_date: str | None = None
    completion_date: str | None = None
    primary_outcome: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def citation(self) -> str:
        parts = [self.nct_id]
        if self.title:
            parts.append(self.title[:80])
        if self.status:
            parts.append(f"[{self.status}]")
        if self.enrollment:
            parts.append(f"N={self.enrollment}")
        return " | ".join(parts)


@dataclass(slots=True)
class EvidenceBundle:
    """
    Richer evidence container that groups a statistical finding with its
    grounding references and a strength classification.  Every signal,
    recommendation, and domain alignment row carries one of these.
    """
    statistical_note: str                              # e.g. "Completed match 72% vs disrupted 41%"
    strength: str                                      # Strong | Moderate | Limited | Anecdotal
    source_count: int = 0                              # number of grounding trials / articles
    references: list[RegistryTrialRef] = field(default_factory=list)
    pubmed_pmids: list[str] = field(default_factory=list)  # optional literature links
    interpretation: str = ""                           # plain-language interpretation of the stat

    def to_dict(self) -> dict[str, Any]:
        return {
            "statistical_note": self.statistical_note,
            "strength": self.strength,
            "source_count": self.source_count,
            "references": [r.to_dict() for r in self.references],
            "pubmed_pmids": self.pubmed_pmids,
            "interpretation": self.interpretation,
        }

    def summary(self) -> str:
        parts = [self.statistical_note]
        if self.source_count:
            parts.append(f"({self.source_count} grounding studies)")
        if self.interpretation:
            parts.append(self.interpretation)
        return "  ".join(parts)


# ── Typed comparison sub-objects ───────────────────────────────────────────────

@dataclass(slots=True)
class DomainAlignmentResult:
    """
    Typed result for one design domain in a protocol vs cohort comparison.
    Replaces the raw dict returned by _build_domain_alignment_row().
    """
    domain: str
    protocol_choice: str
    overall_match_pct: float | None
    completed_match_pct: float | None
    disrupted_match_pct: float | None
    net_gap_pct: float | None
    signal: str
    why_it_matters: str
    evidence: EvidenceBundle

    def to_dict(self) -> dict[str, Any]:
        return {
            "Domain": self.domain,
            "Protocol Choice": self.protocol_choice,
            "Overall Match (%)": self.overall_match_pct,
            "Completed Match (%)": self.completed_match_pct,
            "Disrupted Match (%)": self.disrupted_match_pct,
            "Net Gap (%)": self.net_gap_pct,
            "Signal": self.signal,
            "Why It Matters": self.why_it_matters,
            "evidence": self.evidence.to_dict(),
        }

    def to_flat_dict(self) -> dict[str, Any]:
        """Backward-compatible flat dict (no nested evidence)."""
        return {
            "Domain": self.domain,
            "Protocol Choice": self.protocol_choice,
            "Overall Match (%)": self.overall_match_pct,
            "Completed Match (%)": self.completed_match_pct,
            "Disrupted Match (%)": self.disrupted_match_pct,
            "Net Gap (%)": self.net_gap_pct,
            "Signal": self.signal,
            "Why It Matters": self.why_it_matters,
        }


@dataclass(slots=True)
class EnrollmentBenchmark:
    """Typed enrollment benchmark with protocol position and evidence."""
    target: int | None
    overall_median: float | None
    overall_p25: float | None
    overall_p75: float | None
    completed_median: float | None
    completed_p25: float | None
    completed_p75: float | None
    disrupted_median: float | None
    disrupted_p25: float | None
    disrupted_p75: float | None
    percentile_rank: float | None
    signal: str
    evidence: EvidenceBundle

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DurationBenchmark:
    """Typed duration benchmark with protocol position and evidence."""
    protocol_months: float | None
    overall_median_months: float | None
    overall_p25_months: float | None
    overall_p75_months: float | None
    completed_median_months: float | None
    completed_p25_months: float | None
    completed_p75_months: float | None
    disrupted_median_months: float | None
    disrupted_p25_months: float | None
    disrupted_p75_months: float | None
    signal: str
    evidence: EvidenceBundle

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CohortSummary:
    """Typed descriptor of the matched comparator cohort."""
    condition: str
    total_count: int
    completed_count: int
    disrupted_count: int
    active_count: int
    evidence_strength: str
    risk_share_pct: float | None
    completed_share_pct: float | None
    site_count_median: float | None
    country_count_median: float | None
    status_distribution: dict[str, float] = field(default_factory=dict)
    sponsor_type_distribution: dict[str, float] = field(default_factory=dict)
    endpoint_category_distribution: dict[str, float] = field(default_factory=dict)
    completed_endpoint_distribution: dict[str, float] = field(default_factory=dict)
    disrupted_endpoint_distribution: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DesignRecommendation:
    """
    Typed recommendation with fully-grounded EvidenceBundle.
    Replaces the raw dict in build_protocol_recommendations().
    """
    priority: str           # High | Medium | Monitor | Preserve
    category: str
    action_type: str        # Challenge | Clarify | Monitor | Preserve
    recommendation: str
    rationale: str
    evidence: EvidenceBundle

    def to_dict(self) -> dict[str, Any]:
        return {
            "Priority": self.priority,
            "Category": self.category,
            "Action Type": self.action_type,
            "Recommendation": self.recommendation,
            "Rationale": self.rationale,
            "Evidence": self.evidence.statistical_note,
            "Evidence Strength": self.evidence.strength,
            "Source Count": self.evidence.source_count,
            "Interpretation": self.evidence.interpretation,
            "_evidence_bundle": self.evidence.to_dict(),
        }

    def to_flat_dict(self) -> dict[str, Any]:
        """Backward-compatible flat dict matching old list[dict] format."""
        return {
            "Priority": self.priority,
            "Category": self.category,
            "Action Type": self.action_type,
            "Recommendation": self.recommendation,
            "Rationale": self.rationale,
            "Evidence": self.evidence.statistical_note,
        }


@dataclass(slots=True)
class ComparisonResult:
    """
    Top-level typed result of a protocol vs cohort comparison.
    Replaces the flat metrics dict as the canonical comparison object.
    Provides .to_metrics_dict() and .to_recommendations_list() for
    backward compatibility with all existing chart/report/slide code.
    """
    protocol_condition: str
    timestamp: str
    cohort: CohortSummary
    enrollment: EnrollmentBenchmark
    duration: DurationBenchmark
    alignment_by_domain: list[DomainAlignmentResult]
    design_alignment_index: float | None
    completed_design_fit_pct: float | None
    disrupted_design_fit_pct: float | None
    precedent_gap_pct: float | None
    precedent_posture: str
    missing_core_fields: list[str]
    protocol_endpoint_focus: str
    recommendations: list[DesignRecommendation]

    # ── Backward-compatible flat dict ──────────────────────────────────────────

    def to_metrics_dict(self) -> dict[str, Any]:
        """
        Returns the flat metrics dict used by existing chart/report/slide code.
        All keys match the original build_protocol_comparison_metrics() output.
        """
        c = self.cohort
        e = self.enrollment
        d = self.duration
        return {
            "condition": self.protocol_condition,
            "cohort_size": c.total_count,
            "completed_cohort_size": c.completed_count,
            "disrupted_cohort_size": c.disrupted_count,
            "active_cohort_size": c.active_count,
            "evidence_strength": c.evidence_strength,
            "phase_alignment_pct": self._domain_metric("Phase"),
            "study_type_alignment_pct": self._domain_metric("Study Type"),
            "allocation_alignment_pct": self._domain_metric("Allocation"),
            "masking_alignment_pct": self._domain_metric("Masking"),
            "intervention_model_alignment_pct": self._domain_metric("Intervention Model"),
            "primary_purpose_alignment_pct": self._domain_metric("Primary Purpose"),
            "endpoint_alignment_pct": self._domain_metric("Endpoint Focus"),
            "design_alignment_index": self.design_alignment_index,
            "completed_design_fit_pct": self.completed_design_fit_pct,
            "disrupted_design_fit_pct": self.disrupted_design_fit_pct,
            "precedent_gap_pct": self.precedent_gap_pct,
            "precedent_posture": self.precedent_posture,
            "enrollment_target": e.target,
            "enrollment_median": e.overall_median,
            "enrollment_p25": e.overall_p25,
            "enrollment_p75": e.overall_p75,
            "enrollment_percentile": e.percentile_rank,
            "completed_enrollment_median": e.completed_median,
            "completed_enrollment_p25": e.completed_p25,
            "completed_enrollment_p75": e.completed_p75,
            "disrupted_enrollment_median": e.disrupted_median,
            "disrupted_enrollment_p25": e.disrupted_p25,
            "disrupted_enrollment_p75": e.disrupted_p75,
            "protocol_duration_months": d.protocol_months,
            "duration_median_months": d.overall_median_months,
            "duration_p25_months": d.overall_p25_months,
            "duration_p75_months": d.overall_p75_months,
            "completed_duration_median_months": d.completed_median_months,
            "completed_duration_p25_months": d.completed_p25_months,
            "completed_duration_p75_months": d.completed_p75_months,
            "disrupted_duration_median_months": d.disrupted_median_months,
            "disrupted_duration_p25_months": d.disrupted_p25_months,
            "disrupted_duration_p75_months": d.disrupted_p75_months,
            "site_count_median": c.site_count_median,
            "country_count_median": c.country_count_median,
            "risk_status_share_pct": c.risk_share_pct,
            "completed_share_pct": c.completed_share_pct,
            "recruiting_share_pct": round(float(c.status_distribution.get("Recruiting", 0.0)), 1),
            "active_share_pct": None,
            "industry_share_pct": round(float(c.sponsor_type_distribution.get("Industry", 0.0)), 1),
            "academic_share_pct": round(float(c.sponsor_type_distribution.get("Academic", 0.0)), 1),
            "protocol_endpoint_focus": self.protocol_endpoint_focus,
            "status_distribution": c.status_distribution,
            "status_distribution_raw": c.status_distribution,
            "sponsor_type_distribution": c.sponsor_type_distribution,
            "endpoint_category_distribution": c.endpoint_category_distribution,
            "completed_endpoint_distribution": c.completed_endpoint_distribution,
            "disrupted_endpoint_distribution": c.disrupted_endpoint_distribution,
            "alignment_by_domain": [r.to_flat_dict() for r in self.alignment_by_domain],
            "missing_core_fields": self.missing_core_fields,
        }

    def to_recommendations_list(self) -> list[dict[str, Any]]:
        """Backward-compatible flat list[dict] for existing report/slide code."""
        return [r.to_flat_dict() for r in self.recommendations]

    def to_dict(self) -> dict[str, Any]:
        """Full serialisation for session state storage."""
        return {
            "protocol_condition": self.protocol_condition,
            "timestamp": self.timestamp,
            "cohort": self.cohort.to_dict(),
            "enrollment": self.enrollment.to_dict(),
            "duration": self.duration.to_dict(),
            "alignment_by_domain": [r.to_dict() for r in self.alignment_by_domain],
            "design_alignment_index": self.design_alignment_index,
            "completed_design_fit_pct": self.completed_design_fit_pct,
            "disrupted_design_fit_pct": self.disrupted_design_fit_pct,
            "precedent_gap_pct": self.precedent_gap_pct,
            "precedent_posture": self.precedent_posture,
            "missing_core_fields": self.missing_core_fields,
            "protocol_endpoint_focus": self.protocol_endpoint_focus,
            "recommendations": [r.to_dict() for r in self.recommendations],
        }

    def _domain_metric(self, domain_label: str) -> float | None:
        for row in self.alignment_by_domain:
            if row.domain == domain_label:
                return row.overall_match_pct
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Original models below — unchanged
# ─────────────────────────────────────────────────────────────────────────────

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
