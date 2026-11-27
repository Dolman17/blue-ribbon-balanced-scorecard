# Phase 3.34 — Performance Trends

Read-only comparison of selected month to previous available reporting month, weighted service score changes, ranking, KPI RAG movements, and score coverage. Existing results, actions, scoring thresholds, and /data/bsc.db are not modified by this release; there are **no schema migrations**.

## Deployment

1. Extract the ZIP locally, create branch `phase-3-34-performance-trends` from updated `main`, and copy its contents into your cloned repository (excluding `.git`, `.venv`, `.env` and database files).
2. Run `python -m compileall -q app config.py run.py` and `python -m pytest -q`.
3. Review the changes with `git diff --check`, `git status`, and `git diff --stat`.
4. Commit and push, create a Pull Request targeting `main`. Take/verify Railway volume backup at `/data` before merging.
5. After Railway deploys, visit **Performance Trends** in the sidebar. Validate month, filters and comparison against actual KPI records. Check Registered Manager and Regional Manager access.

## Data semantics

- Uses existing KPIResult rows with `scope=service`; SL parent scores use already-aggregated records. Child-level comparisons can follow as a separate enhancement.
- Prior month is the previous **available** reporting month, which may not be the immediately preceding calendar month.
- Comparison excludes services with no scored results in either period. A missing score does not count as an improvement, deterioration or zero.
- Individual KPI changes compare only RAG-classified results present in both periods.
- Score changes are based on existing weighted-score rules; no rescoring is performed.
- Rankings are for the selected reporting month only.
