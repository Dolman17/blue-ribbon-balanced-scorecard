"""Create an editable Blue Ribbon board deck from a PptxGenJS-designed template.

All slide numbers, headings, graphics and editable tables come from the template;
only text values are inserted at runtime, so Railway needs Python, not Node.js.
"""
from io import BytesIO
from pathlib import Path
from pptx import Presentation

TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "board_report_template.pptx"


def _text(value, limit=100, empty="—"):
    if value is None or str(value).strip() == "":
        return empty
    v = " ".join(str(value).split())
    if len(v) > limit:
        return v[:limit - 1].rstrip() + "…"
    return v


def _num(value):
    return "N/A" if value is None else f"{value:.2f}"


def make_pptx(report, narrative):
    month = report["month"]
    previous = report.get("previous_month")
    movement = report["movement"]
    quality = report["quality"]
    totals = quality["totals"]
    flags = quality.get("flags", [])
    actions = report.get("actions", [])
    maps = {
        "MONTH": month.strftime("%B %Y"),
        "DATE": report["generated_on"].strftime("%d %B %Y"),
        "PREV": previous.strftime("%B %Y") if previous else "no previous month",
        "SCORE": _num(report.get("score")) + " / 10",
        "SCORED": str(report["scored_services"]),
        "COVERAGE": (f"{report['coverage']:.1f}%" if report.get("coverage") is not None else "N/A"),
        "OPEN": str(len(report.get("open_actions", []))),
        "OVERDUE": str(len(report.get("overdue", []))),
        "GREEN": str(report["rag_counts"].get("Green", 0)),
        "AMBER": str(report["rag_counts"].get("Amber", 0)),
        "RED": str(report["rag_counts"].get("Red", 0)),
        "UNSCORED": str(report["rag_counts"].get("Unscored", 0)),
        "MOVEMENT": f"{movement.get('improving', 0)} improving; {movement.get('declining', 0)} declining; {movement.get('unchanged', 0)} unchanged.",
        "QUALITY": f"{len(flags)} advisory flags; {totals.get('missing', 0)} missing KPI results.",
        "PRIORITY": f"{len(report.get('overdue', []))} overdue actions require follow-up.",
        "IMPROVING": str(movement.get("improving", 0)),
        "DECLINING": str(movement.get("declining", 0)),
        "UNCHANGED": str(movement.get("unchanged", 0)),
        "PRESENT": str(totals.get("present", 0)),
        "EXPECTED": str(totals.get("expected", 0)),
        "MISSING": str(totals.get("missing", 0)),
        "FLAGS": str(len(flags)),
        "ACTION_TOTAL": str(len(actions)),
        "ACTION_OUTSTANDING": str(len(report.get("open_actions", []))),
        "ACTION_OVERDUE": str(len(report.get("overdue", []))),
        "RAG_FOOTNOTE": f"Showing up to 11 of {len(movement.get('transitions', []))} KPI RAG changes; full list available in Performance Trends.",
        "FLAGS_FOOTNOTE": f"Showing up to 9 of {len(flags)} validation exceptions; advisory only, no scoring changes.",
        "ACTIONS_FOOTNOTE": f"Showing up to 9 of {len(actions)} actions. Status is live as at generation, not a historic snapshot.",
    }
    for prefix, rows in (("BEST", report.get("best", [])), ("WORST", report.get("worst", []))):
        for i in range(5):
            row = rows[i] if i < len(rows) else None
            maps[f"{prefix}_{i}_NAME"] = _text(row["service"].name, 35) if row else ""
            maps[f"{prefix}_{i}_DELTA"] = f"{row['delta']:+.2f}" if row else ""
    for i in range(11):
        row = movement.get("transitions", [])[i] if i < len(movement.get("transitions", [])) else None
        maps[f"RAG_{i}_SERVICE"] = _text(row["service"].name, 25) if row else ""
        maps[f"RAG_{i}_KPI"] = _text(row["kpi"].name, 51) if row else ""
        maps[f"RAG_{i}_PREV"] = _text(row["previous"], 13) if row else ""
        maps[f"RAG_{i}_CURR"] = _text(row["current"], 13) if row else ""
        maps[f"RAG_{i}_DIRECTION"] = _text(row["direction"], 23) if row else ""
    for i in range(9):
        flag = flags[i] if i < len(flags) else None
        maps[f"FLAG_{i}_SERVICE"] = _text(flag.get("service"), 24) if flag else ""
        maps[f"FLAG_{i}_TYPE"] = _text(flag.get("kind"), 24) if flag else ""
        maps[f"FLAG_{i}_DETAIL"] = _text(flag.get("detail"), 70) if flag else ""
        action = actions[i] if i < len(actions) else None
        maps[f"ACTION_{i}_SERVICE"] = _text(action.service.name, 24) if action else ""
        maps[f"ACTION_{i}_TITLE"] = _text(action.title, 45) if action else ""
        maps[f"ACTION_{i}_OWNER"] = _text(action.owner, 25) if action else ""
        maps[f"ACTION_{i}_DUE"] = action.due_date.strftime("%d %b %y") if action and action.due_date else ""
        maps[f"ACTION_{i}_STATUS"] = _text(action.status, 22) if action else ""
    overflow = False
    for key in ("HIGHLIGHTS", "CONCERNS", "PRIORITIES"):
        raw = getattr(narrative, key.lower(), "") if narrative else ""
        raw = raw or "No commentary recorded."
        if len(raw) > 500:
            overflow = True
        maps[key] = _text(raw, 500)
    maps["COMMENTARY_NOTE"] = ("Commentary over 500 characters is abbreviated on this slide. Full text remains in Board Reporting."
                                if overflow else "Board commentary reflects the selected reporting month. Review before circulation.")

    prs = Presentation(str(TEMPLATE))
    for slide in prs.slides:
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for paragraph in shape.text_frame.paragraphs:
                for run in paragraph.runs:
                    for key, val in maps.items():
                        token = "{{" + key + "}}"
                        if token in run.text:
                            run.text = run.text.replace(token, str(val))
    output = BytesIO()
    prs.save(output)
    output.seek(0)
    return output
