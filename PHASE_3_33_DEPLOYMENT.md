# Phase 3.33 — Improvement Action Tracker

## Scope

This is **the first of the planned scorecard enhancement releases**, not all of Phases 3.33–3.40. It builds on the user's already deployed **Phase 3.32 Security Hardening** source. Preserve the existing Railway `SECRET_KEY` and persistent `/data/bsc.db` volume.

### New functionality

- Improvement Actions screen in navigation for permitted roles.
- Create an action against a **Red or Amber result** for an existing reporting month, covering standard service KPIs and Supported Living child KPI results.
- Assign an owner (free-text name), priority, deadline and intended outcome.
- Record progress notes, status changes and supporting **http(s) evidence links**. Evidence is linked, not uploaded to the app.
- Completion requires a linked evidence URL. Actions have immutable dated progress events and administrative field audit records.
- Display overdue items and status filters.
- Link directly from Red / Amber service and sub-service KPI cards.
- View restrictions for Registered Managers (assigned service) and Regional Managers (assigned region) remain enforced on the server; Viewers cannot mutate actions.

### Database changes

The application creates two new tables automatically on startup using `db.create_all()`:

- `improvement_action`
- `improvement_action_event`

Existing KPI tables, user records, scoring rules and Supported Living aggregation methods are unchanged. No existing database file is included in this package. This is an additive schema change; **do not replace `/data/bsc.db` with any local file**.

## Deployment procedure

1. Verify a recent, correct Railway volume backup of `/data/bsc.db` and confirm the existing Phase 3.32 deployment is healthy.
2. In the local Git repository: `git switch main` then `git pull --rebase origin main`. Ensure a clean working tree.
3. Create a feature branch: `git switch -c phase-3-33-action-tracker`.
4. Copy **contents** of this ZIP's `blue-ribbon-balanced-scorecard-main` folder over the local repository folder, merging app files. Do not overwrite `.env`, `.venv`, `.git` or local databases.
5. Set up your existing virtual environment; run `python -m compileall -q app config.py run.py` and `python -m pytest -q`.
6. Test locally with a **temporary local database**. Try Admin, Executive, Registered Manager, Regional Manager and Viewer access as well as SL actions and action history.
7. Commit/push feature branch, create a PR, run checks, then merge only after review.
8. Check Railway deployment health, login, `/actions`, existing data, and permissions.

Example PowerShell Git commands after branch and local testing:

```powershell
git add .
git commit -m "Phase 3.33 - KPI improvement action tracker"
git push -u origin phase-3-33-action-tracker
gh pr create --base main --head phase-3-33-action-tracker --title "Phase 3.33 - Improvement Action Tracker" --body "Add accountable KPI actions, progress history, evidence links, and service-scoped access."
```

## Important caveats

- Automated runtime tests **could not run inside the artifact environment** because Flask and Flask-SQLAlchemy could not be installed; syntax and Jinja template parsing passed. You **must run** the Python tests locally before merging.
- Evidence is a URL to an approved store, not an embedded file upload. Keep document access restricted separately.
- Owner is stored as free text for now. The later notifications phase should introduce controlled user assignment where needed.
- For a service using SL aggregation, create actions against the **child KPI result** for precise accountability, or against the parent aggregate if organizational ownership is desired.
- New actions link to the historical KPI reporting month and original Red/Amber rating. Later changes to score values do not silently rewrite action origins.

## Next roadmap releases

- 3.34: Month-on-month performance movement and comparability.
- 3.35: Completeness checks, NPS sample thresholds, vacancy interpretation and SL aggregation review.
- 3.36: Automated Board reports and narrative.
- 3.37: Persistent risk and early-warning rules.
- 3.38: Month-end locks, approvals and correction workflow.
- 3.39: Notifications and overdue reminders.
- 3.40: Integration adapters, subject to supported APIs and permissions.
