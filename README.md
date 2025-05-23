# Trial Design Explorer

**An interactive Streamlit platform for exploring global clinical trial design trends.**  
Built by [Francis Osei](https://github.com/Franosei) | [Live Demo: https://trialexplorer.streamlit.app/](#)

---

## Project Overview

Trial Design Explorer is an interactive visualization tool that helps **researchers**, **trial planners**, and **sponsors** evaluate and compare clinical trial design patterns using global registry data. The tool enables data-driven decisions around:

- **Feasibility benchmarking**
- **Trial site selection**
- **Outcome measure alignment**
- **Design competitiveness analysis**

Inspired by real-world challenges in designing trials for conditions like **sepsis**, this tool empowers users to answer critical planning questions using real data from over 76 countries:contentReference[oaicite:1]{index=1}.

---

## Features

-  **Duration Panel**: Analyze typical trial lengths across conditions.
-  **Location Panel**: Visualize geographic distribution and representation gaps.
-  **Outcome Panel**: Identify common regulatory-aligned primary endpoints.
-  **Sponsor Panel**: Track sponsor activity by type and geography.
-  **Timeline Panel**: View trial status over time (recruiting, completed, etc.).
-  **Summary Table**: Summarize key trial metadata and filter by custom criteria.
-  **Future Enhancements**:
  - Natural Language Summaries
  - Smart Recommendations for trial structure and design:contentReference[oaicite:2]{index=2}

---

## Repository Structure

```bash
TRIAL-DESIGN-EXPLORER/
├── assets/
│   └── logo.png
├── components/
│   ├── duration_panel.py
│   ├── location_panel.py
│   ├── outcome_panel.py
│   ├── overview_panel.py
│   ├── sponsor_panel.py
│   ├── summary_table.py
│   └── timeline_panel.py
├── data/
│   └── sample_response.json
├── utils/
│   ├── api_client.py
│   ├── helpers.py
│   └── parser.py
├── app.py
├── config.py
└── README.md


```
---

## Getting Started

### 1. Clone the repository

```
git clone https://github.com/Franosei/Trial-Design-Explorer.git
cd Trial-Design-Explorer


### 2. Install dependencies

```bash
pip install -r requirements.txt

---

### 3. Run the Streamlit app

```bash
python -m streamlit run app.py
---

### 4. Configuration

 - Modify config.py to set base endpoints, environment settings, or other parameters as needed.
 - Sample JSON input is provided in data/sample_response.json.

---

### 5. Use Case Example

Planning a Sepsis Trial?

- Median duration: 24 months
- Site viability: Africa & Asia underrepresented
- Outcomes: Mortality, SOFA score, length of hospital stay are most common

→ Use this data to benchmark your protocol against real-world studies.

---

### 6. Future Roadmap

 - GPT-powered clinical summary generator
 - Evidence-based trial design suggestions
 - Sponsor-type based comparative insights

---

### 7. Citation

- If you use this tool for academic or professional work, please credit:

→ Osei, Francis. Trial Design Explorer: Real-time Benchmarking of Clinical Trials Using Registry Data. 2025.

---
### Contact
Feel free to reach out via https://www.linkedin.com/in/francis-osei-b2b02116a/ for collaborations or feedback!