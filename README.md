# AvailOps — Availability Operations (Python Demo)

AvailOps is a portfolio-grade **availability decision-support** demo for high-performance sport:
multi-source monitoring → trend features → explainable flags → staff-facing dashboard.

**Data disclosure:** this repository uses **synthetic / demo data** intended for safe sharing.  
It is **not** a validated clinical tool and does not claim injury prediction, diagnosis, or prevention.

---

## Why this repo exists
This repo is the **public-facing demo**:
- Shows you can ship a usable dashboard (UI/UX + analytics)
- Demonstrates an end-to-end monitoring workflow using synthetic data
- Safe to share with recruiters and teams without exposing athlete data

For the **operational, on-prem** implementation (secure ingest + warehouse + scheduled Quarto reports), see:
**AvailOps-r-ops-pipeline**

---

## What this demonstrates
- A daily “AM board” mindset (readiness + workload context)
- Multi-source schema thinking (wellness, load, testing, and event history)
- Transparent flagging (“why” drivers), not black-box claims
- Optional ML layer as **decision support**, not as a sole decision-maker

---

## Tech stack
- Python (pandas, numpy, scikit-learn)
- Streamlit (dashboard)
- SQLite (demo database): `availops_demo.db`
- Optional model artifact: `availops_risk_model.pkl`

---

## Quick start (local)

### 1) Create and activate a virtual environment
Windows (PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2) Run the dashboard
```powershell
streamlit run dashboard_availops.py
```

---

## Repository structure
```
availops-python-demo/
├── dashboard_availops.py           # Streamlit dashboard (AvailOps-branded)
├── ml_models_availops.py           # Optional demo scoring / model build
├── availops_demo.db                # Demo SQLite database
├── availops_risk_model.pkl         # Optional demo model artifact
├── outputs/                        # Optional exports (CSV)
├── requirements.txt
├── README.md
└── LICENSE
```

---

## What to show in interviews
Suggested positioning:
> “This is a public demo using synthetic data to illustrate an availability decision-support workflow.
> In production, the same logic runs on team hardware with secure exports, role-based access, and scheduled reporting.”

---

## Notes on naming and trademarks
“AvailOps” is used here as a descriptive internal-tool style name.  
If you ever commercialize, do a formal trademark search and counsel review.

---

## License
MIT (see LICENSE)

---

## Contact
Chris Cothern  
Sport Scientist | Performance Analytics | High Performance Ops
