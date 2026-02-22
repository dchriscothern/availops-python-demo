## Privacy, Security, and Operating Model (Best Practice)

This repository is a **public-facing demo**. It is designed to be **safe by default** and portable across teams.

### Data classification
- **Public/Demo (OK to commit):** `demo_data/`  
  Contains anonymized/synthetic CSVs and public-only case study exports.
- **Private/Internal (NEVER commit):** a local folder outside this repo, e.g. `C:\AvailOps_PrivateData\`  
  May contain identifiable or sensitive performance/medical fields.

### Fail-safe design
The app supports two runtime modes using environment variables:

**Demo / Streamlit Cloud (forced anonymized)**
- Reads from `demo_data/`
- Anonymization is ON (`AVAILOPS_ANON=1`)
- Intended for recruiters and portfolio review

**Private / Local (internal use)**
- Reads from a private folder outside the repo (e.g., `C:\AvailOps_PrivateData\`)
- Anonymization can be ON or OFF, but defaults to ON for screenshots

**Hard rule:** do not place private files inside this GitHub repository. Keep private data outside the repo so it cannot be accidentally committed.

### Environment variables
- `AVAILOPS_DATA_DIR`  
  Folder where the app reads CSV inputs (default: `demo_data`)
- `AVAILOPS_ANON`  
  `1` = anonymize/redact identities (recommended)  
  `0` = show identifiable fields (local only; never for Cloud)
- `AVAILOPS_SALT`  
  Stable anonymization salt so player codes remain consistent across runs

### Redaction policy (public-safe)
When `AVAILOPS_ANON=1`, the app:
- Generates `player_code` (stable hashed ID)
- Removes name-like columns (`name`, `player_name`, `display_name`, etc.)
- Drops diagnosis/surgery/medical-note columns if present (keeps generic “flags/drivers”)

### Public case study note (ESPN/wehoop)
The optional WNBA case study uses **public boxscore availability** (minutes played / DNP events).  
If “reasons” are shown, they are labeled as **publicly reported** (not medical ground truth) and remain anonymized.

### Debugging & reliability
- The UI validates inputs (required columns, coercible types) and fails gracefully.
- If one file is missing/empty, other tabs still render.
- For troubleshooting: confirm `AVAILOPS_DATA_DIR`, check row counts, and review logs (local-only).
