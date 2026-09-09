# Blue Ribbon Balanced Scorecard - Phase 3.1

Local Flask/SQLite balanced scorecard for monthly Blue Ribbon service, management-hierarchy, Local Authority and group KPI reporting.

## Phase 3.1 changes

The service hierarchy is now:

**Regional Manager > Registered Manager > Service**

`Local Authority` is now a separate geographic attribute and replaces the previous `Region` field throughout the application.

The Services import structure is:

`Service Code | Service Name | Regional Manager | Registered Manager | Local Authority | Active`

### Executive filters

The Executive dashboard includes Power BI-style filters for:

- Reporting Month
- Regional Manager
- Registered Manager
- Local Authority
- Service
- Overall RAG

Registered Manager options are filtered by the selected Regional Manager, reflecting the management hierarchy.

### Portfolio views

- `/regional-managers` - Regional Manager portfolio overview
- Regional Manager drill-down shows the Registered Managers reporting to that Regional Manager
- Registered Manager drill-down shows their assigned services
- `/local-authorities` - geographic Local Authority overview
- Service view shows Regional Manager > Registered Manager and Local Authority

### Existing database compatibility

You can keep an existing Phase 2/3 `instance/bsc.db`.

On startup the app:

1. Adds `regional_manager` if needed.
2. Adds `local_authority` if needed.
3. If the old `region` column exists, copies its existing values into `local_authority` once so historical service master data is retained.

The old database column can remain in SQLite; the current application no longer uses it.

## Importing data

Upload either `Blue_Ribbon_BSC_Import_Template.xlsx` or the populated demonstration workbook `Blue_Ribbon_BSC_Sample_Data.xlsx` through **Import**.

The sample workbook contains fictional KPI and manager data for testing the dashboard layout only.

## Run locally

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
flask --app run.py run --debug
```

Open `http://127.0.0.1:5000`.

## Board Excel export

The Board export now includes:

- Executive Summary
- All Services matrix with Regional Manager, Registered Manager and Local Authority
- Local Authority Summary
- Regional Manager Summary
- Registered Manager Summary nested under Regional Manager
- Group KPIs
- Individual service sheets


## Phase 3.2 - Service Master editing

The Admin menu now includes **Service Master**. Service records can be amended directly in the app, including Service Name, Regional Manager, Registered Manager, Local Authority and Active status. Saving a row marks it as manually maintained so later workbook imports do not overwrite those hierarchy fields. Use **Use workbook values** to return that service to workbook-controlled master data.


## Service Type
Services can now be categorised as either **Registered** or **Supported Living**. The field is available in Service Master, the monthly Services import sheet, the Executive dashboard filters and service detail views. Existing databases are upgraded automatically on startup.


## Phase 3.6 - Professional Excel Board Export

The Board Excel export has been redesigned for ExCo/Board presentation use, including:

- Blue Ribbon branded title banners and logo
- Executive KPI cards for overall score, RAG and service exceptions
- Improved top/bottom service exception tables
- 12-month trend and RAG distribution visuals
- Consistent professional styling across all summary and service sheets
- RAG conditional formatting and score heatmaps
- Regional Manager, Registered Manager and Local Authority summary sheets
- Clickable links from the All Services matrix into individual service scorecards
- Back-to-dashboard links on service sheets
- Improved commentary wrapping, row heights, widths, freeze panes and print settings
- Confidential footers and page numbering for Board-pack printing

The export continues to use the same live database and KPI configuration; no database migration is required.


## Phase 3.8 scoring update
- CQC combined values such as `Good / Not Rated` now score Green based on the substantive rating.
- Hours Usage now defaults to a Target Range rule: target 100%, Green within +/-2%, Amber within +/-5%, Red outside +/-5%.
- Budget Over / Underspend now defaults to a Target Range rule: target 0%, Green within +/-2%, Amber within +/-5%, Red outside +/-5%.
- Target, Green tolerance and Amber tolerance can be edited in KPI Setup.
- Existing databases are upgraded automatically with the new `target_value` field. If Hours Usage or Budget Variance are still configured as Manual, they are upgraded to these starter rules on first launch.


## Phase 3.9 display formatting
- Exact numeric zero values display as `0` rather than `0.0` in the dashboard and service views.
- Excel KPI values use matching zero-friendly number formats.


## Phase 3.10 formatting update
Count KPIs such as Safeguardings, Complaints and Whistleblowing display whole-number values without a trailing `.0` when the imported value is an integer.

## NPS Score

`NPS_SCORE` is included as a People KPI and can be imported at either Service or Group scope. The starter RAG thresholds are Green >= 50, Amber 0 to 49.9, and Red < 0. These thresholds are editable in KPI Setup. Values should be imported as the calculated NPS score on the standard -100 to +100 scale.


## Manual KPI entry
Use Admin > Manual Entry to amend imported KPI values or add missing KPI data later. Existing records are pre-filled and saved edits are marked with source `Manual entry`. The RAG recalculates automatically unless a manual RAG is selected. The same page supports service-level and group-level monthly data.


## Phase 3.16 - Login, user CRUD and future access levels

Authentication is now enabled with Flask-Login. On the first launch after upgrading, if there are no users, browse to the app and you will be sent to `/setup` to create the first Administrator account. No default password is supplied.

Admin users can manage accounts from **Admin > Users**: create, read, update, activate/deactivate, reset passwords, and delete other accounts. Roles available are Admin, Executive, Regional Manager, Registered Manager and Viewer. Scope fields are stored for Regional Manager, Registered Manager, Local Authority and Service so portfolio restrictions can be enforced in a future phase. For now, Admin is the intended live role and admin-only pages are protected.


## Screen notes / change list

Every authenticated screen now has a **Notes** button in the top bar. Notes are stored against the current screen path, record the author and optional reporting-month context, and can be marked done/reopened or deleted. This is intended as a lightweight working change list while reviewing the dashboard. The `screen_note` table is created automatically on first startup via `db.create_all()`.


## Development notes

Admin users have a **Dev Notes** button in the top bar. These notes are intended only as a personal app-development/change list. They are stored in the browser's `localStorage`, keyed to the current screen path, and are **not** written to the Blue Ribbon scorecard database or attached to KPI/service records. Clearing browser site data or using another browser/device will not carry these notes across.
