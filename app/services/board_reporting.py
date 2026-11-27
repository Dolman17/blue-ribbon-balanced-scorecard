"""Read-only Board summary, reusing existing scoring and quality calculations."""
from datetime import date
from app.models import ImprovementAction, KPIResult, Service
from app.services.performance_trends import compare_performance
from app.services.data_quality import quality_report


def build_summary(month, previous_month):
    movement = compare_performance(month, previous_month)
    quality = quality_report(month)
    scored = [r for r in movement["rows"] if r["current"] is not None]
    counts = {"Green": 0, "Amber": 0, "Red": 0, "Unscored": 0}
    for item in movement["rows"]:
        counts[item["current_rag"] if item["current_rag"] in counts else "Unscored"] += 1
    avg_score = round(sum(r["current"] for r in scored) / len(scored), 2) if scored else None
    comparable = [r for r in movement["rows"] if r["delta"] is not None]
    best = sorted((r for r in comparable if r["delta"] > 0), key=lambda r: -r["delta"])[:5]
    worst = sorted((r for r in comparable if r["delta"] < 0), key=lambda r: r["delta"])[:5]
    actions = (ImprovementAction.query.join(Service, ImprovementAction.service_id == Service.id)
               .filter(ImprovementAction.reporting_month == month).order_by(ImprovementAction.due_date.asc()).all())
    open_actions = [a for a in actions if a.status not in ("Completed", "Cancelled")]
    overdue = [a for a in open_actions if a.due_date < date.today()]
    totals = quality["totals"]
    coverage = round(100 * totals["present"] / totals["expected"], 1) if totals["expected"] else None
    # Improvement action status is live, even when a historical month is viewed.
    return {"month": month, "previous_month": previous_month, "movement": movement,
            "quality": quality, "score": avg_score, "scored_services": len(scored),
            "rag_counts": counts, "best": best, "worst": worst,
            "actions": actions, "open_actions": open_actions, "overdue": overdue,
            "coverage": coverage, "generated_on": date.today()}
