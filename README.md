# AvailOps — War Room (Python Demo)

A lightweight, shareable **sports performance “War Room” dashboard** built in **Streamlit**.

This repository is the **public-facing demo UI**. It reads **anonymized/synthetic** CSV exports and renders a decision-support view (Watchlist, Team Trends, Public Case Study).

---

## What this is (for recruiters / teams)

**AvailOps War Room** consolidates key availability signals into one view:
- **Watchlist** (who needs attention today)
- **Team trends** (last 7 days context)
- **Public case study** (multi-season, anonymized availability via public boxscores)

It’s designed to plug into an ops pipeline that generates daily exports.

---

## Inputs (CSV files)

The app reads from a data folder:

- **Demo mode (default / deployed):** `demo_data/` (inside this repo)
- **Private mode (local only):** a folder outside the repo (recommended), e.g. `C:\AvailOps_PrivateData`

Expected filenames:

### Watchlist
- `watchlist_today.csv` (preferred)
- `watchlist_today_example.csv` (fallback)

### Team trends
- `team_trends_7d.csv` (preferred)
- `team_trends_7d_example.csv` (fallback)

### Public case study (multi-season)
- `public_wnba_availability_anon_multi.csv` (preferred)

> The public case study dataset should be **anonymized** (e.g., `DAL25_P##`) and contain no medical notes.

---

## Data safety model (important)

### Hard fail-safe
When the app is **deployed (Streamlit Cloud/headless)**:
- It **forces Demo mode**
- It reads **ONLY** from `demo_data/`
- **Anonymization is always ON**
- It cannot read your `C:\...` private folders

### Private mode (local only)
For internal use, you run locally and point the app to a secure folder **outside the repo**.

---

## Run locally (Windows)

Open PowerShell and run:

```powershell
cd C:\GitHub\availops-python-demo\availops-python-demo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run .\app.py