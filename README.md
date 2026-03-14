# Trial Design Explorer

Protocol-first clinical trial planning intelligence for pharma and CRO teams.

The application combines protocol intake, structured extraction, historical trial benchmarking, traceable review, and professional PDF reporting in a single Streamlit workspace. It is designed to support high-stakes planning discussions, not just exploratory visualization.

## What The App Does

- upload protocol or study documents
- extract a structured protocol profile with heuristics and optional LLM support
- let reviewers confirm and edit extracted fields before analysis
- build comparable cohorts from ClinicalTrials.gov
- compare the draft protocol against completed and disrupted precedent
- generate decision-grade benchmark tables, charts, and action signals
- support grounded review chat with audit history
- export a formal PDF report with tables, figures, and provenance-oriented sections

## Current Product Shape

The app has two workspaces:

- `Protocol Intelligence`
  The main workspace for document intake, protocol review, benchmark analysis, recommendations, chat, and report export.

- `Registry Explorer`
  A secondary workspace for cohort discovery and broader historical benchmark context.

The protocol workflow is staged for easier navigation:

1. `Intake`
2. `Review`
3. `Analysis`
4. `Report`

## Current Decision Logic

The analysis layer is not generic cohort summary. It focuses on planning signals that are more useful in real review settings:

- completed vs disrupted comparator cohorts
- protocol fit against completed precedent
- protocol fit against disrupted precedent
- success-vs-disruption benchmark tables
- design differential matrix by domain
- executive action register
- comparator exemplar selection
- traceable decision signals for reporting

This gives reviewers a more concrete answer to questions like:

- where does this draft align with completed precedent?
- where does it resemble disrupted precedent?
- what should be clarified before governance review?
- which design choices should be preserved versus challenged?

## Reporting Standard

The PDF export is built as a decision pack rather than a UI dump. Current report sections include:

- executive summary
- senior decision signals
- executive action register
- reviewed protocol profile
- comparative narrative
- comparator cohort definition
- success-vs-disruption benchmark
- decision scorecard
- design differential matrix
- key figures
- recommendation detail
- comparator exemplars
- audit trail and methodology

## Repository Structure

```text
TRIAL-DESIGN-EXPLORER/
|-- app.py
|-- assets/
|-- data/
|-- docs/
|   `-- platform_blueprint.md
|-- trial_design_explorer/
|   |-- config.py
|   |-- state.py
|   |-- domain/
|   |   |-- __init__.py
|   |   `-- models.py
|   |-- services/
|   |   |-- __init__.py
|   |   |-- audit_service.py
|   |   |-- clinical_trials_service.py
|   |   |-- comparison_service.py
|   |   |-- document_service.py
|   |   |-- openai_service.py
|   |   |-- protocol_service.py
|   |   `-- report_service.py
|   `-- ui/
|       |-- __init__.py
|       |-- app_shell.py
|       |-- styles.py
|       |-- pages/
|       |   |-- __init__.py
|       |   |-- protocol_workspace.py
|       |   `-- registry_explorer.py
|       `-- panels/
|           |-- __init__.py
|           |-- duration.py
|           |-- location.py
|           |-- outcome.py
|           |-- overview.py
|           |-- protocol_benchmarks.py
|           |-- sponsor.py
|           |-- summary.py
|           `-- timeline.py
`-- requirements.txt
```

## Getting Started

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

Create a local `.env` file if you want model-assisted extraction and grounded review chat.

Supported variables:

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`

If no model configuration is present, the app falls back to heuristic extraction and deterministic comparison outputs.

### 3. Run the app

```bash
py -3 -m streamlit run app.py
```

## Key Files

- [app.py](/c:/Users/oseif/OneDrive/Desktop/Trial-Design-Explorer/app.py)
  Thin Streamlit entrypoint.

- [trial_design_explorer/ui/app_shell.py](/c:/Users/oseif/OneDrive/Desktop/Trial-Design-Explorer/trial_design_explorer/ui/app_shell.py)
  App shell, workspace switcher, and top-level layout.

- [trial_design_explorer/ui/pages/protocol_workspace.py](/c:/Users/oseif/OneDrive/Desktop/Trial-Design-Explorer/trial_design_explorer/ui/pages/protocol_workspace.py)
  Protocol-first review workflow.

- [trial_design_explorer/services/protocol_service.py](/c:/Users/oseif/OneDrive/Desktop/Trial-Design-Explorer/trial_design_explorer/services/protocol_service.py)
  Protocol extraction, session hydration, and grounded chat preparation.

- [trial_design_explorer/services/comparison_service.py](/c:/Users/oseif/OneDrive/Desktop/Trial-Design-Explorer/trial_design_explorer/services/comparison_service.py)
  Comparator cohort logic, completed-vs-disrupted benchmarking, and recommendations.

- [trial_design_explorer/services/report_service.py](/c:/Users/oseif/OneDrive/Desktop/Trial-Design-Explorer/trial_design_explorer/services/report_service.py)
  Boardroom-style PDF generation.

## Trust, Review, And Auditability

The repo is being shaped around higher-trust review standards:

- reviewer confirmation before protocol fields are treated as approved
- explicit visibility into audit events
- provenance-aware extraction objects in the domain model
- recommendation outputs grounded in matched comparator data
- no requirement for an LLM to use the core benchmarking workflow

## Current Limitations

The application is much stronger than the original prototype, but there are still major upgrades ahead:

- comparator matching is still condition-led rather than true semantic similarity ranking
- recommendations are benchmark-driven and not yet deeply therapeutic-area-specific
- project persistence and long-term audit storage are not finished
- the reporting engine is strong enough for review drafts, but it can still be pushed further toward full consulting-grade templating

## Near-Term Roadmap

- true similarity ranking for comparator selection
- deeper therapeutic-area logic
- richer evidence and provenance panels
- saved projects and run history
- stronger enterprise approval workflow

## Platform Blueprint

See [docs/platform_blueprint.md](/c:/Users/oseif/OneDrive/Desktop/Trial-Design-Explorer/docs/platform_blueprint.md) for the platform direction and phased implementation plan.
