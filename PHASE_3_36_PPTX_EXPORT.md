# Phase 3.36 – Board PowerPoint Export

This update replaces the PDF download with an **editable six-slide PowerPoint report**, styled after the supplied Blue Ribbon safeguarding overview slide.

## Slides
1. Portfolio overview and assurance messages
2. Month-on-month performance movements
3. KPI RAG movements
4. Data quality and validation exceptions
5. Improvement action oversight
6. Executive commentary and priorities

The slides contain editable PowerPoint text boxes, shapes and tables. The template was authored using PptxGenJS and is populated at request time by `python-pptx`, which runs on Railway's Python service without requiring Node.js.

## Safety and data fidelity
- Uses existing Board-report summary, existing scoring and access controls.
- Does not alter KPI records or Board commentary.
- Long table lists show first 5–11 entries, with the full number of available entries printed on the relevant slide. The app retains the complete detailed reports.
- Individual commentary fields over 500 characters are abbreviated with an explicit warning on the commentary slide. The full text remains in the web app.
- Live action status is explicitly labelled as not a historical snapshot.

## Deploy
1. Create a Git feature branch from current `main`.
2. Copy the package files over the repository (excluding `.git`, `.venv`, `.env` and database files).
3. `python -m pip install -r requirements.txt`
4. `python -m compileall -q app config.py run.py`
5. `python -m pytest -q`
6. Test the selected-month `/board-report/pptx` download locally and open it in PowerPoint.
7. Review the PR and confirm Railway volume backup before merging.
8. After deploying, check PowerPoint export, existing Board page, login and service dashboards.

The old `/board-report/pdf` route is removed in this update, and ReportLab is no longer required.
