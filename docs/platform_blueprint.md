# Platform Blueprint

## Goal

Evolve Trial Design Explorer from a registry visualization tool into a professional trial planning intelligence platform for pharma and CRO teams.

Core intent:

1. ingest protocol and study documents
2. extract structured trial design data
3. build comparable cohorts from historical registry data
4. benchmark the proposed study against prior evidence
5. support review through grounded chat and traceable edits
6. export formal reports with provenance and auditability

## Current Refactor Outcome

The repository now follows a platform-style structure:

- `trial_design_explorer/domain`
  Typed models for protocol metadata, audit events, chat messages, and provenance.

- `trial_design_explorer/services`
  Integration and logic layer for document parsing, trial retrieval, protocol extraction, comparison, audit events, and reporting.

- `trial_design_explorer/ui`
  Streamlit shell, workspace pages, and registry analysis panels.

This separates UI orchestration from data logic and gives the app a stable base for future enterprise features.

## Target Product Modules

- `Document Intake`
  Upload, version, parse, and preview protocols and related study documents.

- `Protocol Extraction`
  Combine heuristics and model-assisted extraction to build a structured protocol profile.

- `Human Confirmation`
  Let reviewers edit extracted fields before using them in downstream analysis.

- `Trial Matching`
  Build comparison cohorts from public trial sources and later commercial or internal sources.

- `Benchmarking`
  Compare phase, status, enrollment, endpoints, geography, duration, sponsor mix, and execution patterns.

- `Recommendation Layer`
  Surface evidence-backed design suggestions and planning risks.

- `Traceable Chat`
  Let users challenge findings, ask follow-up questions, and confirm outputs while preserving a review log.

- `Professional Reporting`
  Produce boardroom-ready reports with executive summary, methods, tables, evidence notes, and audit trail.

## Trust and Governance Principles

- no unsupported claims
- explicit uncertainty when evidence is weak
- reviewer confirmation before protocol profile is treated as approved
- visible provenance for extracted fields and generated outputs
- timestamped audit events for extraction, comparison, chat, edits, and export

## Recommended Next Implementation Phases

### Phase 1

- completed: repo restructure into domain, services, and UI layers
- completed: separate registry and protocol workspaces
- completed: editable protocol profile review step
- completed: traceable chat and starter PDF export

### Phase 2

- completed: expand structured extraction schema for sponsor, arms, masking, purpose, comparator, population, and endpoint focus
- completed: normalize more trial attributes from registry sources
- completed: create stronger comparison metrics for enrollment, endpoint alignment, design alignment, status risk, and sponsor mix
- completed: add first generation of expert-grade benchmark visuals
- next: upgrade cohort selection from condition matching to true similarity ranking

### Phase 3

- add true similarity ranking and cohort selection logic
- add evidence cards and source-level provenance panels
- strengthen reporting layout and export fidelity
- introduce saved projects and run history

### Phase 4

- enterprise approval workflow
- versioned report packages
- persistent audit store
- advanced recommendation engine with explicit evidence citations

## Design Standard

The platform should feel credible, restrained, and senior:

- no novelty visuals that weaken trust
- no unsupported AI phrasing
- reports should read like strategy and operations deliverables
- tables, legends, and annotations should be clear enough for executive review

## Technical Follow-Up

The next refactor after this one should focus on:

- persistent storage for projects and analysis runs
- richer comparison schemas and evidence objects
- better PDF rendering technology for consulting-grade output
- test coverage around extraction, comparison, and report integrity
