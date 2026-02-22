\# AvailOps — War Room (Python Demo)



A lightweight, shareable \*\*sports performance “War Room” dashboard\*\* built in \*\*Streamlit\*\*.  

This repository is the \*\*public-facing demo UI\*\* that reads \*\*anonymized/synthetic\*\* exports (CSV) from an ops workflow.



\## What this is

AvailOps consolidates key availability signals (watchlist flags, recent team trends, and a public-only availability case study) into a single view for quick decision support. It’s designed to be portable across teams: drop in CSV exports and the dashboard updates immediately.



\## Inputs (demo)

The app reads CSVs from `/demo\_data`:



\- Watchlist: `watchlist\_today.csv` (or `watchlist\_today\_example.csv`)

\- Team trends: `team\_trends\_7d.csv` (or `team\_trends\_7d\_example.csv`)

\- Public case study: `public\_wnba\_2025\_DAL\_availability\_anon.csv` (public-only, anonymized)



> \*\*Privacy note:\*\* This repo uses \*\*demo/anonymized data only\*\*. Do not commit real athlete health/medical data.



\## Outputs

Streamlit tabs:

\- \*\*Watchlist\*\*: player flags + risk score summary

\- \*\*Team Trends\*\*: rolling 7-day team metrics

\- \*\*Public Case Study\*\*: anonymized availability vs workload



\## Run locally (Windows)

```powershell

cd C:\\GitHub\\availops-python-demo\\availops-python-demo

python -m venv .venv

.\\.venv\\Scripts\\Activate.ps1

pip install -r requirements.txt

streamlit run app.py

