from app.extensions import db
from app.models import KPIDefinition, KPIResult


DEFAULT_KPIS = [
    dict(code="SAFEGUARDINGS", name="Safeguardings", domain="Quality", unit="count", direction="lower", green_threshold=0, amber_threshold=2, notes="Example threshold only - replace with agreed Blue Ribbon threshold."),
    dict(code="CQC_OUTCOME", name="CQC Outcomes", domain="Quality", unit="rating", direction="categorical", notes="Outstanding/Good (including Good / Not Rated) = Green; Requires Improvement = Amber; Inadequate = Red; Not Rated only = Unscored."),
    dict(code="INTERNAL_AUDIT", name="Internal Audit Outcome", domain="Quality", unit="%", direction="higher", green_threshold=90, amber_threshold=80, notes="Example threshold only - replace with agreed Blue Ribbon threshold."),
    dict(code="RM_STATUS", name="Registered Manager Status", domain="Governance", unit="status", direction="categorical", notes="Registered = Green; In Progress = Amber; Vacancy/No RM = Red."),
    dict(code="COMPLAINTS", name="Complaints", domain="Quality", unit="count", direction="lower", green_threshold=0, amber_threshold=2, notes="Example threshold only. Family complaint count can be included in commentary or as separate KPI later."),
    dict(code="WHISTLEBLOWING", name="Whistleblowing", domain="Governance", unit="count", direction="lower", green_threshold=0, amber_threshold=1, notes="Consolidate Say So, HR whistleblowing and other inbound whistleblowing."),
    dict(code="TRAINING_COMPLIANCE", name="Training Compliance", domain="People", unit="%", direction="higher", green_threshold=95, amber_threshold=90),
    dict(code="NAPPI_COMPLIANCE", name="NAPPI Compliance", domain="People", unit="%", direction="higher", green_threshold=95, amber_threshold=90),
    dict(code="SICKNESS_RATE", name="Sickness Rate", domain="People", unit="%", direction="lower", green_threshold=4, amber_threshold=6, notes="Example threshold only - replace with agreed Blue Ribbon threshold."),
    dict(code="ATTRITION_RATE", name="Attrition Rate", domain="People", unit="%", direction="lower", green_threshold=26, amber_threshold=32, notes="Example threshold only - replace with agreed Blue Ribbon threshold."),
    dict(code="NPS_SCORE", name="NPS Score", domain="People", unit="score", direction="higher", green_threshold=50, amber_threshold=0, notes="Starter NPS thresholds: Green >= 50; Amber 0 to 49.9; Red < 0. Configurable in KPI Setup."),
    dict(code="OCCUPANCY", name="Occupancy", domain="Operations", unit="%", direction="higher", green_threshold=90, amber_threshold=85, group_only=True, notes="Group-only KPI per email scope."),
    dict(code="HOURS_USAGE", name="Hours Usage", domain="Operations", unit="%", direction="target_range", target_value=100, green_threshold=2, amber_threshold=5, notes="Target 100%. Green within +/-2%; Amber within +/-5%; Red outside +/-5%. Configurable in KPI Setup."),
    dict(code="BUDGET_VARIANCE", name="Budget Over / Underspend", domain="Finance", unit="%", direction="target_range", target_value=0, green_threshold=2, amber_threshold=5, notes="Target 0%. Green within +/-2%; Amber within +/-5%; Red outside +/-5%. Configurable in KPI Setup."),
]


def seed_default_kpis():
    upgraded_codes = set()
    for item in DEFAULT_KPIS:
        existing = KPIDefinition.query.filter_by(code=item["code"]).first()
        if not existing:
            db.session.add(KPIDefinition(**item))
            continue

        # Upgrade the two previously-manual KPIs to the agreed starter target-range logic
        # without overwriting later user-configured settings.
        if item["code"] in {"HOURS_USAGE", "BUDGET_VARIANCE"} and existing.direction == "manual":
            existing.direction = "target_range"
            existing.target_value = item.get("target_value")
            existing.green_threshold = item.get("green_threshold")
            existing.amber_threshold = item.get("amber_threshold")
            existing.notes = item.get("notes")
            upgraded_codes.add(item["code"])

        if item["code"] == "CQC_OUTCOME":
            upgraded_codes.add(item["code"])
            if not existing.notes:
                existing.notes = item.get("notes")
    db.session.flush()

    # Re-score only previously Unscored rows, preserving any Manual RAGs already
    # imported by the user. This makes the August live data update immediately.
    if upgraded_codes:
        results = (
            KPIResult.query
            .join(KPIDefinition)
            .filter(KPIDefinition.code.in_(upgraded_codes), KPIResult.rag == "Unscored")
            .all()
        )
        for result in results:
            result.rag = calculate_rag(result.kpi, result.value_numeric, result.value_text, None)

    db.session.commit()


def calculate_rag(kpi, numeric_value=None, text_value=None, manual_rag=None):
    if manual_rag:
        cleaned = str(manual_rag).strip().title()
        if cleaned in {"Green", "Amber", "Red", "Unscored"}:
            return cleaned

    if kpi.direction == "manual":
        return "Unscored"

    if kpi.direction == "categorical":
        value = (text_value or "").strip().lower()
        if kpi.code == "CQC_OUTCOME":
            # Some Blue Ribbon records combine a rated location with an unrated
            # element, e.g. "Good / Not Rated". Score the substantive rating.
            if "inadequate" in value:
                return "Red"
            if "requires improvement" in value:
                return "Amber"
            if "outstanding" in value or "good" in value:
                return "Green"
            if value == "not rated":
                return "Unscored"
            return "Unscored"
        if kpi.code == "RM_STATUS":
            mapping = {
                "registered": "Green",
                "in progress": "Amber",
                "application submitted": "Amber",
                "vacancy": "Red",
                "no rm": "Red",
                "no registered manager": "Red",
            }
            return mapping.get(value, "Unscored")
        return "Unscored"

    if numeric_value is None:
        return "Unscored"

    if kpi.direction == "higher":
        if numeric_value >= kpi.green_threshold:
            return "Green"
        if numeric_value >= kpi.amber_threshold:
            return "Amber"
        return "Red"

    if kpi.direction == "lower":
        if numeric_value <= kpi.green_threshold:
            return "Green"
        if numeric_value <= kpi.amber_threshold:
            return "Amber"
        return "Red"

    if kpi.direction == "target_range":
        if kpi.target_value is None or kpi.green_threshold is None or kpi.amber_threshold is None:
            return "Unscored"
        distance = abs(float(numeric_value) - float(kpi.target_value))
        if distance <= float(kpi.green_threshold):
            return "Green"
        if distance <= float(kpi.amber_threshold):
            return "Amber"
        return "Red"

    return "Unscored"


def rag_score(rag):
    return {"Green": 3, "Amber": 2, "Red": 1}.get(rag)
