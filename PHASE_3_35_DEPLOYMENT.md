# Phase 3.35 — Data Quality & Scoring Assurance

Based on Phase 3.34. New `Data Quality` navigation page at `/data-quality`.

## What's included
- Monthly service-level completeness, including missing versus blank, explicit N/A, and recorded numeric zero.
- Separate Supported Living child completeness, avoiding double-counting children in top-level totals.
- Advisory NPS low-sample flag (default 5, adjustable only for the current report).
- Negative vacancy review flag; **existing scoring is unchanged**.
- SL parent roll-up coverage flags for stored `SL aggregate` results when not all active children contribute recorded values.
- Role-scoped view for Registered Managers and Regional Managers; standard permissions for other roles.

## Important interpretation
- Expected KPI count = active, non-group-only definitions across active services. Some KPIs may not apply; review missing/blank indicators rather than treating every gap as an overdue return.
- NPS thresholds are an advisory sample size only; they do not suppress or recalculate scores.
- There are **no changes to KPI scoring, SL aggregation algorithms, imports, exports or schema**.
- No new permanent data storage. The database at `/data/bsc.db` is not replaced.

## Local deployment
1. Update `main`, create `phase-3-35-data-quality` branch.
2. Copy the extracted package into your repo, excluding `.git`, `.venv`, `.env` and `*.db`.
3. Run `python -m compileall -q app config.py run.py` and `python -m pytest -q`.
4. Review the diff; merge through a PR only after tests pass and a Railway volume backup is confirmed.
5. After Railway deploys, verify data-quality page, RM and Regional Manager restrictions, and unchanged historic scores.

## Future changes requiring separate approval
- Editable per-service KPI applicability and formal N/A states.
- Configurable persisted minimum NPS response sample and any actual score suppression.
- Revised vacancy policy for negative values and modified aggregation weighting.
