# Blue Ribbon BSC — Phase 3.32 Security Hardening

This package is based on the user-supplied GitHub archive at commit `7971de7`.
It does **not** contain a production database or any Railway secrets.

## BEFORE deploying to Railway

1. Back up the existing Railway volume file `/data/bsc.db`. Verify the copy is readable.
2. In Railway service **Variables**, confirm `DATABASE_PATH=/data/bsc.db`.
3. Add or confirm `SECRET_KEY` with at least 32 random characters. Generate locally with:
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`
   Never commit the key or paste it into chat. Changing an existing key logs out active users.
4. **Do not set `BSC_DEV_MODE=1` in Railway.** It is only for running local HTTP development.
5. `ADMIN_SETUP_TOKEN` is optional **when your existing database has users**. If starting with an empty DB, securely set a new random 32+ character token and enter it at `/setup`. Remove the variable once the first admin is created. Avoid an empty DB being mistaken for the production database.
6. Review the Railway deployment logs after pushing; the application intentionally refuses to start with a missing/short `SECRET_KEY`.

## What changed

- `config.py`: production secret required; Secure/HttpOnly/SameSite cookies.
- `app/security.py`: CSRF on all state-changing requests; basic browser security headers; persistent 15-minute failed-login throttling by IP and normalized username/email hash.
- `app/models.py`: new `login_attempt` and `audit_event` tables. Both created via `db.create_all()` without replacing the existing database. Existing KPI, Service, NPS, and user tables are not dropped.
- `app/audit.py`: transactional audit history of create/update/delete actions against core business models. Stores actor, timestamp, record type and changed-field names, **not** free-text comments, passwords or old/new sensitive values. This is a lightweight audit rather than a complete regulatory audit system.
- `app/routes.py`: gated first-run admin creation, login throttling, blocked protocol-relative login redirects, generic unexpected import errors.
- HTML forms and dashboard JavaScript: CSRF token included in POST requests.
- `app/services/importer.py`: all-or-nothing Excel KPI imports; limits on workbook size, ZIP expansion and row count; reject duplicate keys. Failed imports are logged and leave business data unchanged. **This changes previous partial-import behavior:** if any row is invalid, *none* are imported. Correct the workbook and retry.
- `app/services/sl_aggregation.py`: supports deferring commit so SL roll-ups and the underlying workbook are saved together.
- `app/services/exporter.py`: text beginning with Excel formula prefixes is escaped, preserving built-in report formulas.
- `run.py`: debug mode off unless `BSC_DEV_MODE=1`.

## Local Windows/PowerShell test commands

```powershell
cd C:\Users\seand\Downloads\Blue_Ribbon_BSC_MVP\blue_ribbon_bsc
$env:BSC_DEV_MODE = '1'
$env:SECRET_KEY = 'local-only-placeholder-not-for-production-0123456789'
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q tests/test_security.py
python run.py
```

The production app must use HTTPS; local `http://127.0.0.1:5000` works only with `BSC_DEV_MODE=1`.

## Recommended acceptance tests before pushing

- Admin can log in, log out, edit a KPI, upload a valid Excel file and export the board pack.
- Every form rejects a missing or stale CSRF token; dashboard widget changes still save.
- Admin setup fails when `ADMIN_SETUP_TOKEN` is absent and there are no users.
- The Registered Manager role can only access its assigned service; a Regional Manager only its portfolio.
- An import with one bad row leaves every KPI/service unchanged and logs `Rejected (no changes)`.
- An import containing SL child codes rolls up correctly into the parent service.
- Workbook comments such as `=1+1` appear as text, not formulas, in exported Excel.
- The existing Railway volume and all historic months remain after redeploy.

## Review limitations

Source compilation and static checks were performed in this environment. The environment did not contain Flask runtime dependencies and could not reach the Python package index, so live Flask integration tests were **not** run here. Run the included tests and perform user acceptance testing on a staging database before production. Dependency vulnerability scanning and a professional external penetration test remain outstanding. Content-Security-Policy is deliberately limited to frame/base/form restrictions, since the existing UI has inline JavaScript and third-party CDNs; a full nonce-based CSP requires a separate UI pass.
