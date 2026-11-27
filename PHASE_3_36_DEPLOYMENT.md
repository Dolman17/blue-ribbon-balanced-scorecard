# Phase 3.36 – Automated Board Reporting

## Release summary

- New `/board-report` page with reporting month selector, portfolio score/RAG distribution, service and KPI movements, data completeness, advisory flags and improvement actions.
- New `/board-report/pdf` download, professionally paginated A4 PDF generated in memory using ReportLab.
- Admin and Executive users can edit highlights, concerns and priorities, saved independently for each month and added to audit history. Viewer can view/download but not edit. Regional/Registered Managers cannot access organisation-wide Board reports.
- Current action statuses and overdue flags are shown as **live status at generation** even in historic month reports, not as a reconstructed historical snapshot.
- RAG/scoring calculations, KPI storage, action records and scorecard imports are untouched.

## Database and dependencies

- Creates only one new table: `board_report_narrative`. The existing startup `db.create_all()` creates it automatically. **Do not reset or replace `/data/bsc.db`.**
- Adds `reportlab==4.4.5` to `requirements.txt`. Railway must successfully install it before the application can serve PDF exports.
- Back up the Railway `/data` volume and confirm the backup is for the attached database volume before merging.

## Local PowerShell steps

```powershell
git switch main
git pull origin main
git switch -c phase-3-36-board-reporting
# Extract ZIP then use robocopy to copy the application files over the repository.
# Exclude .git, .venv, .env, *.db and __pycache__.
python -m pip install -r requirements.txt
python -m compileall -q app config.py run.py
python -m pytest -q
git diff --check
git status --short
```

**Stop on failed tests**; do not deploy until the test suite and local PDF test pass. The expected test count is 17 (14 previous + 3 new). Before merging, inspect changes against GitHub main for unexpected differences.

## Production smoke test

1. Confirm Railway deploy is Active and logs are free of errors.
2. Open Board Reporting and select a reporting month with data. Confirm portfolio figures agree with Performance Trends and Data Quality.
3. Save commentary for one month (Admin/Executive). Reopen that month and confirm it persists; switch to a different month and verify separation.
4. Download the PDF and check pagination, data accuracy, commentary and styling.
5. Confirm Viewer cannot change commentary, and Regional/Registered Managers cannot access Board Reporting or its PDF endpoint.
6. Confirm previous KPIs, Improvement Actions and other dashboards still work.

## Limitations

- This is a live report export, not an approved/locked monthly reporting snapshot. Formal reporting sign-off and locks are planned for Phase 3.38.
- There is no automatic email delivery or scheduling yet. Those belong to the notifications phase.
- The PDF shows a capped set of detailed KPI transitions and actions; full detail remains in the app.


### PowerPoint export amendment
The PDF export has been replaced by an editable PowerPoint download. See `PHASE_3_36_PPTX_EXPORT.md`. `python-pptx==1.0.2` replaces ReportLab in requirements.
