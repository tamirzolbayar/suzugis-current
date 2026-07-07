# SuzuGIS

SuzuGIS is a lightweight Streamlit mapping dashboard for managing road restrictions and field recovery work in Suzu City.

The current prototype links GeoJSON road segments with an Excel management table, then displays the active restrictions on a GSI base map with filters, progress status, popups, drawing tools, and editable management fields.

## Current Features

- Display road restrictions on an interactive Folium map
- Filter by target date, restriction type, and contractor
- Show actual progress and scheduled progress
- Edit contractor, progress, and notes from the sidebar
- Save Excel updates with timestamped backups
- Link road-use-permit PDFs by restriction ID
- Draw new map features and save them to GeoJSON
- Switch between GSI standard, pale, photo, blank, and hillshade maps

## Run Locally

```powershell
pip install -r requirements.txt
streamlit run src/app.py
```

## Data Files

- `data/excel/restriction_list.xlsx`: management table
- `data/geojson/suzu_sample.geojson`: map features
- `data/documents/<規制ID>/道路使用許可.pdf`: road-use-permit PDF for each restriction
- `data/backups/`: automatic Excel backups created when edits are saved

## Broader Direction

Although the first use case is road restriction management, the same structure can support a wider municipal field operations platform:

- road restrictions
- water, power, and communications restoration status
- construction progress
- hazard zones and access control
- photos and field inspection notes
- public-facing situation maps
- internal dashboards for contractors and city staff

The core idea is to treat every mapped feature as a managed field object with geometry, schedule, responsible party, status, and notes.
