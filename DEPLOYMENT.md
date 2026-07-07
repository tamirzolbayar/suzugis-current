# Deploying SuzuGIS

## Recommended Demo Deployment

Use Streamlit Community Cloud for the current demo/prototype.

Community Cloud is a good fit because SuzuGIS is a Python Streamlit app with local data files. Vercel is not recommended for this version because it is optimized for frontend/static or serverless web apps, not long-running Streamlit apps.

## GitHub Repository Layout

Upload this project folder as the root of a GitHub repository:

```text
SuzuGIS/
  .streamlit/config.toml
  data/
  src/
  README.md
  requirements.txt
```

Do not upload generated caches or backups. The `.gitignore` file excludes:

```text
__pycache__/
data/backups/
data/geojson/backups/
output/
```

## Streamlit Community Cloud Settings

When creating the app:

```text
Repository: your SuzuGIS GitHub repository
Branch: main
Main file path: src/app.py
```

## Important Data Note

The current app edits `data/excel/restriction_list.xlsx` directly.

On Streamlit Community Cloud this is acceptable for a demo, but it is not a production database. File edits may not persist reliably across app restarts, redeployments, or multiple users.

For production, move the management data to one of:

- Google Sheets
- Supabase/PostgreSQL
- SQLite/PostgreSQL on a persistent host
- S3-compatible storage for documents

## Current Recommendation

Use Streamlit Community Cloud for the deadline demo. For a real municipal/consultant workflow, keep Streamlit as the interface but move Excel-backed state into a real database or managed spreadsheet.
