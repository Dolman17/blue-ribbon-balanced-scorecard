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

## Phase 3.19 - Supported Living drill-down

Supported Living services can now contain manually maintained sub-services/locations without increasing top-level service counts.

### Workflow
1. Open **Service Master** and use **Manage** against a Supported Living service, or open the service and select **Manage SL services**.
2. Add the individual services/locations beneath that Supported Living service.
3. Open a child service and choose **Edit month** to enter its KPI values manually.
4. Saving child KPI values automatically recalculates the parent Supported Living KPI results for the same reporting month.
5. The parent then continues to feed the existing Registered Manager, Regional Manager, Local Authority and Executive views.

### KPI roll-up methods
KPI Setup now includes an **SL roll-up** field:
- **Average** - average numeric child values, then score the aggregated value.
- **Sum** - sum numeric child values, then score the aggregated value.
- **Worst RAG** - use the most adverse child RAG/value.
- **Do not aggregate** - leave that KPI outside the child roll-up.

Starter defaults are Sum for count KPIs, Worst RAG for categorical/status KPIs, and Average for most percentages/scores. Group-only KPIs are excluded from child entry.

### Database compatibility
The app creates the new `sl_sub_service` and `sl_sub_service_kpi_result` tables automatically on startup. Existing databases are upgraded in place with the new `aggregation_method` field on `kpi_definition`. Existing top-level KPI history is retained.

## Phase 3.20 - Monthly NPS response drill-down

NPS can now be maintained at individual-response level for each top-level service and each Supported Living sub-service.

- Open a service or SL sub-service and choose **NPS detail**.
- Select the reporting month and enter one or more 0-10 responses, with optional response date, comment/reason and source.
- Scores are categorised automatically: 9-10 Promoter, 7-8 Passive, 0-6 Detractor.
- The NPS score is calculated from the underlying response population: `% Promoters - % Detractors`.
- A Supported Living parent's NPS is calculated from all underlying responses across its active child services plus any responses entered directly against the parent. Child NPS percentages are never averaged.
- Group NPS is calculated from all individual responses across the organisation, so each response is counted once.
- Calculated response-level NPS is written back to the existing `NPS_SCORE` KPI result, so the Executive, hierarchy, service dashboards and Board export continue to use the same KPI framework.
- Manual NPS entry remains available as a fallback where no response-level NPS data exists for the month. Once detailed responses exist, they take precedence over manual NPS values.
- Admin users can add and delete response records. Deleting a response automatically recalculates the affected child/service, parent Supported Living service and Group NPS as applicable.

## Phase 3.21 - Supported Living service view layout
- Reordered the Supported Living parent service page so the main KPI cards appear before the Supported Living sub-service breakdown.
- The drill-down table now sits immediately beneath the parent KPI cards, followed by the existing trend charts.


## Phase 3.22 – Executive NPS Response Card
- Adds a monthly NPS response card to the Executive dashboard.
- Shows service / SL sub-service, response date, score, category and comment.
- The card follows the Executive service filters.
- A fixed-height scroll area is used automatically when a month contains many responses.
- Displays response count and calculated NPS for the currently filtered response population.

## Phase 3.23 - Per-user Executive dashboard customisation

The Executive dashboard now includes a **Customise dashboard** button. Each authenticated user can drag the main dashboard cards into their preferred order. The order is stored against that user account in the database, so it follows the user across browsers/devices. A Reset default option restores the standard Blue Ribbon layout. New dashboard cards introduced in future releases are automatically appended if they are not yet present in a user's saved layout.
