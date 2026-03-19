# Trial Design Explorer

Clinical trial planning intelligence for pharma, biotech, and CRO teams.

Upload a draft protocol/synposium/trial document, extract a structured clinical profile using an LLM, and immediately see how your design compares against a scored cohort of historical trials from ClinicalTrials.gov, with domain-level risk findings, enrollment and duration benchmarks, a priority-coded action register, and a boardroom-ready PDF and PowerPoint export.

---

## What It Does

A trial planner uploads a draft protocolprotocol document (PDF, DOCX, TXT, or RTF). The system:

1. **Extracts a structured clinical profile** using a multi-pass LLM extraction architecture — title, condition, phase, allocation, masking, intervention model, primary purpose, planned enrollment, arms count, dates, primary and secondary endpoints (verbatim), target population and full eligibility criteria (verbatim), intervention description, and comparator.

2. **Lets the reviewer confirm and correct** every extracted field before any analysis runs. Provenance of the extraction is recorded.

3. **Builds a design-similar trial cohort** from ClinicalTrials.gov using a five-domain PICO similarity model (Population, Design, Endpoints, Intervention, Duration). Sponsor is intentionally excluded from scoring. Each trial is scored 0–1 and classified as Clinically Comparable, Methodologically Aligned, or Not Directly Comparable.

4. **Runs domain-level landscape intelligence** — for each design domain, shows the match rate in completed trials versus terminated/disrupted trials, flags where the protocol's choices are more common in failed trials, and quantifies the precedent gap.

5. **Benchmarks enrollment and duration** — compares planned N and trial length against the IQR of completed and disrupted comparator trials, with explicit in-range / out-of-range callouts.

6. **Generates a priority-coded risk register** — High, Medium, Monitor, and Preserve findings grounded in the comparator data, with rationale and evidence for each item.

7. **Exports a formal report package** — multi-section PDF with charts and a PowerPoint slide deck for governance and review meetings.

---

## Protocol Extraction Architecture

Extraction is LLM-first. No regex or heuristics are used to assign field values.

For documents under 50,000 characters, a single comprehensive LLM pass on the full text extracts all fields.

For longer documents (100-page protocols), four keyword-anchored passes are used:

| Pass | Content target | Anchor strategy |
|------|----------------|-----------------|
| 1 | Title, sponsor, design header | First 15k chars + synopsis window |
| 2 | Primary and secondary endpoints | Anchored from char 25,000+ to skip glossary false matches |
| 3 | Eligibility criteria | Anchored from char 25,000+ to skip summary-of-changes table |
| 4 | Intervention, dose, comparator | Anchored from char 25,000+ to skip title-page header |

The 25,000-character minimum offset prevents common false matches where terms like "primary outcome measure", "study intervention", and "inclusion criteria" appear in document glossaries, amendment tables, and title pages before the actual content sections.

Field values are copied verbatim from the document. The LLM is instructed not to paraphrase or invent. Extraction confidence (High / Medium / Low) is scored from required field coverage.

When no OpenAI API key is configured, only structural fields derivable from document patterns (phase, allocation, masking) are extracted. All rich text fields are left empty and a clear configuration prompt is shown.

---

## Design Similarity Model

Trials are scored against the protocol across five clinical domains that determine whether two studies are truly comparable — matching the strictness required for regulatory external control arms, systematic reviews, and indirect treatment comparisons.

| Domain | Weight | Key dimensions |
|--------|--------|----------------|
| Population | 5 | Disease indication (keyword overlap), age range (numeric overlap %), line of therapy (1L vs 2L+) |
| Design | 5 | Study type, allocation (RCT vs non-RCT), masking, intervention model |
| Endpoints | 5 | Primary endpoint text (Jaccard token similarity), phase context |
| Intervention | 4 | Drug/device class, comparator structure (single-arm vs placebo vs active) |
| Duration | 3 | Treatment duration and follow-up window |

**Similarity thresholds:**

| Score | Classification | Interpretation |
|-------|---------------|----------------|
| ≥ 0.70 | Clinically comparable | Suitable for external control / ITC without adjustment |
| 0.45–0.70 | Methodologically aligned | Minor differences; requires statistical adjustment |
| < 0.45 | Not directly comparable | Major differences; similarity claim is not defensible |

Sponsor is excluded from all scoring dimensions by design.

---

## Analysis Stage

The Analysis stage is structured around decisions, not summaries.

**Trial Landscape Brief** — headline counts (matched, completed, terminated, active), evidence strength, design posture badge, completion rate narrative, and design-fit progress bars showing alignment with each precedent group.

**Domain Intelligence (tabbed)** — one tab per domain. Each tab shows the protocol's design choice, the percentage of completed trials that used that choice, the percentage of terminated trials that used it, and a green/amber/red gap signal.

**Enrollment & Duration Benchmarks** — protocol target vs completed-trial IQR with explicit in-range / above-range / below-range callouts and percentile rank.

**Risk Register** — priority-coded bordered cards (not a table). High-priority items are design choices that are statistically more common in terminated than completed trials.

**Comparator Exemplars** — top 20 trials ranked by similarity score, with status badges, phase, masking, enrollment, and similarity classification.

**AI Review Assistant** — grounded chat using protocol metadata, benchmark metrics, and recommendations as context. Does not fabricate evidence.

---

## Report Package

### PDF

Multi-section clinical review document:

1. Cover page with protocol identity and generation timestamp
2. Executive summary with narrative and KPI table
3. Senior decision signals
4. Executive action register
5. Reviewed protocol profile (structured fields table + verbatim long-text blocks)
6. Precedent posture analysis with narrative
7. Design domain alignment with radar chart and heatmap
8. Design differential matrix
9. Enrollment benchmark with box-plot chart
10. Duration comparison chart
11. Comparator cohort definition
12. Success vs disruption benchmark
13. Endpoint evidence
14. PubMed literature evidence (if fetched)
15. Comparator exemplars
16. Recommendation detail
17. Audit trail and methodology

### PowerPoint

Slide deck for governance and review meetings — one slide per analytical section with embedded charts, auto-numbered footers showing true slide count.

---

## Workspaces

**Protocol Intelligence** (primary)
Document intake → structured review → landscape analysis → risk register → report export.

**Registry Explorer** (secondary)
Condition-level cohort discovery, overview analytics, location maps, duration distributions, outcome trends, sponsor analysis, and timeline charts. Useful for building benchmark context before drafting a protocol.

---

## Repository Structure

```
trial-design-explorer/
├── app.py                                  # Streamlit entrypoint — loads .env at module level
├── .env                                    # OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
├── requirements.txt
├── assets/
├── data/
├── trial_design_explorer/
│   ├── config.py                           # Constants, condition list, field registry
│   ├── state.py                            # Session state initialisation
│   ├── domain/
│   │   └── models.py                       # ProtocolMetadata, ComparisonResult, domain types
│   └── services/
│   │   ├── audit_service.py                # Audit event builder, provenance records
│   │   ├── chart_service.py                # Matplotlib chart generators (BytesIO)
│   │   ├── clinical_trials_service.py      # CT.gov fetch, parse, PICO similarity scoring
│   │   ├── comparison_service.py           # Cohort metrics, domain alignment, recommendations
│   │   ├── document_service.py             # PDF/DOCX/RTF text extraction
│   │   ├── openai_service.py               # OpenAI API wrapper, has_openai_config()
│   │   ├── protocol_service.py             # LLM extraction, multi-pass, grounded chat
│   │   ├── pubmed_service.py               # PubMed article fetch and parsing
│   │   ├── report_service.py               # ReportLab PDF generation
│   │   └── slides_service.py               # python-pptx slide deck generation
│   └── ui/
│       ├── app_shell.py                    # App layout, workspace switcher
│       ├── styles.py                       # CSS theme
│       ├── pages/
│       │   ├── protocol_workspace.py       # 4-stage protocol workflow
│       │   └── registry_explorer.py        # Registry cohort explorer
│       └── panels/
│           ├── protocol_benchmarks.py      # Plotly benchmark charts
│           ├── overview.py
│           ├── duration.py
│           ├── location.py
│           ├── outcome.py
│           ├── sponsor.py
│           ├── summary.py
│           └── timeline.py
```

---

## Getting Started

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure the OpenAI API key

Edit `.env` in the project root:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

The app will show a clear error on the Intake stage if no key is configured. Without a key, only structural fields (phase, allocation, masking) can be extracted from uploaded documents.

### 3. Run

```bash
streamlit run app.py
```

---

## Design Principles

**LLM for content, structure for signals.**
Field values are always extracted by the LLM. Regex is used only to validate controlled-vocabulary fields (phase format, status normalization) — never to assign content.

**Reviewer in the loop.**
No analysis runs until a reviewer has confirmed or corrected the extracted profile. Extraction confidence and provenance are visible at every stage.

**Sponsor-blind similarity.**
The comparator cohort selection model does not use sponsor identity. This prevents circular reasoning (comparing your Pfizer trial only against other Pfizer trials) and keeps the benchmark methodologically defensible.

**Grounded outputs.**
Recommendations and risk findings are derived from the comparator cohort data — not from templates or generic rules. Each finding cites the completed vs disrupted match rates that drive it.

**Paginate, don't truncate.**
Long clinical text (eligibility criteria, endpoint descriptions) renders as flowing prose in the PDF, not as table cells, so no content is lost and ReportLab does not overflow.

---

## Current Limitations

- Comparator matching uses PICO-domain scoring against ClinicalTrials.gov registry data. Results data (whether a trial actually met its primary endpoint) is not incorporated — completion status is used as a proxy for success.
- Recommendations are grounded in design-domain precedent patterns, not in therapeutic-area-specific clinical expertise.
- No persistent project storage — session state is lost on app restart.
- The Registry Explorer workspace does not yet integrate with the Protocol Intelligence scoring model.

---

## Roadmap

- Results-data integration (met/missed primary endpoint signal from CT.gov results API)
- Therapeutic-area-specific recommendation modules
- Persistent project storage and run history
- Approval workflow and sign-off audit trail
- Multi-protocol comparison (compare two drafts against the same comparator cohort)
