# AvailOps — War Room (Python Demo)

A lightweight, shareable **sports performance “War Room” dashboard** built in **Streamlit**.

This repo is the **public-facing demo UI**. It reads **anonymized/synthetic** CSV exports and renders:
- **Watchlist (today)**
- **Team trends (7-day)**
- **Public case study (WNBA / wehoop; anonymized, multi-season)**

## Data safety model (best practice)

### Demo (public-safe)
- Default mode
- Reads from `demo_data/`
- Anonymization ON

### Private (internal)
- Reads from a folder **outside** the repo, e.g. `C:\AvailOps_PrivateData`
- Anonymization ON by default
- **Identifiable mode is hard-blocked unless explicitly allowed and data is outside the repo**

## Inputs
Place CSVs in your data directory:

- `watchlist_today.csv`
- `team_trends_7d.csv`
- `public_wnba_availability_anon_multi.csv` (multi-team + multi-season)

Demo versions live in `demo_data/`.

## Run locally (Windows)

### 1) Demo mode (public-safe)
```powershell
cd C:\GitHub\availops-python-demo\availops-python-demo
Remove-Item Env:\AVAILOPS_DATA_DIR -ErrorAction SilentlyContinue
$env:AVAILOPS_ANON='1'
streamlit run app.py