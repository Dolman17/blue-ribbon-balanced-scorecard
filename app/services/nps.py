from datetime import datetime

from app.extensions import db
from app.models import KPIDefinition, KPIResult, NPSResponse, SLSubService, SLSubServiceKPIResult
from app.services.scoring import calculate_rag


def nps_value(responses):
    total = len(responses)
    if not total:
        return None
    promoters = sum(1 for response in responses if response.score >= 9)
    detractors = sum(1 for response in responses if response.score <= 6)
    return round(((promoters - detractors) / total) * 100, 2)


def nps_summary(responses):
    total = len(responses)
    promoters = sum(1 for response in responses if response.score >= 9)
    passives = sum(1 for response in responses if 7 <= response.score <= 8)
    detractors = sum(1 for response in responses if response.score <= 6)
    return {
        "total": total,
        "promoters": promoters,
        "passives": passives,
        "detractors": detractors,
        "score": nps_value(responses),
    }


def _nps_kpi():
    return KPIDefinition.query.filter_by(code="NPS_SCORE").first()


def _service_responses(service_id, reporting_month):
    """Return responses that contribute to a top-level service NPS.

    Direct responses are included for every service. For Supported Living parents,
    child-level responses are also included, so the parent NPS is calculated from
    the underlying response population rather than by averaging child NPS scores.
    """
    direct = NPSResponse.query.filter_by(
        reporting_month=reporting_month,
        service_id=service_id,
        sub_service_id=None,
    ).all()

    child_ids = [
        row[0]
        for row in db.session.query(SLSubService.id)
        .filter_by(parent_service_id=service_id)
        .all()
    ]
    children = []
    if child_ids:
        children = (
            NPSResponse.query
            .filter(
                NPSResponse.reporting_month == reporting_month,
                NPSResponse.sub_service_id.in_(child_ids),
            )
            .all()
        )
    return direct + children


def recalculate_sub_service_nps(sub_service_id, reporting_month):
    kpi = _nps_kpi()
    if not kpi:
        return None

    responses = (
        NPSResponse.query
        .filter_by(reporting_month=reporting_month, sub_service_id=sub_service_id)
        .order_by(NPSResponse.id)
        .all()
    )
    value = nps_value(responses)
    result = SLSubServiceKPIResult.query.filter_by(
        reporting_month=reporting_month,
        sub_service_id=sub_service_id,
        kpi_id=kpi.id,
    ).first()

    if value is None:
        if result and result.source == "NPS responses":
            result.value_numeric = None
            result.value_text = None
            result.rag = "Unscored"
            result.commentary = "No response-level NPS data entered for this month."
            result.imported_at = datetime.utcnow()
        return result

    if not result:
        result = SLSubServiceKPIResult(
            reporting_month=reporting_month,
            sub_service_id=sub_service_id,
            kpi_id=kpi.id,
        )
        db.session.add(result)

    summary = nps_summary(responses)
    result.value_numeric = value
    result.value_text = None
    result.rag = calculate_rag(kpi, value, None, None)
    result.source = "NPS responses"
    result.commentary = (
        f"Calculated from {summary['total']} response(s): "
        f"{summary['promoters']} promoter(s), {summary['passives']} passive(s), "
        f"{summary['detractors']} detractor(s)."
    )
    result.imported_at = datetime.utcnow()
    return result


def recalculate_service_nps(service_id, reporting_month):
    kpi = _nps_kpi()
    if not kpi:
        return None

    responses = _service_responses(service_id, reporting_month)
    value = nps_value(responses)
    result = KPIResult.query.filter_by(
        reporting_month=reporting_month,
        scope="service",
        service_id=service_id,
        kpi_id=kpi.id,
    ).first()

    if value is None:
        if result and result.source == "NPS responses":
            result.value_numeric = None
            result.value_text = None
            result.rag = "Unscored"
            result.commentary = "No response-level NPS data entered for this month."
            result.imported_at = datetime.utcnow()
        return result

    if not result:
        result = KPIResult(
            reporting_month=reporting_month,
            scope="service",
            service_id=service_id,
            kpi_id=kpi.id,
        )
        db.session.add(result)

    summary = nps_summary(responses)
    result.value_numeric = value
    result.value_text = None
    result.rag = calculate_rag(kpi, value, None, None)
    result.source = "NPS responses"
    result.commentary = (
        f"Calculated from {summary['total']} underlying response(s): "
        f"{summary['promoters']} promoter(s), {summary['passives']} passive(s), "
        f"{summary['detractors']} detractor(s)."
    )
    result.imported_at = datetime.utcnow()
    return result


def recalculate_group_nps(reporting_month):
    kpi = _nps_kpi()
    if not kpi:
        return None

    # Each stored response represents one person and is counted exactly once.
    responses = NPSResponse.query.filter_by(reporting_month=reporting_month).all()
    value = nps_value(responses)
    result = KPIResult.query.filter_by(
        reporting_month=reporting_month,
        scope="group",
        service_id=None,
        kpi_id=kpi.id,
    ).first()

    if value is None:
        if result and result.source == "NPS responses":
            result.value_numeric = None
            result.value_text = None
            result.rag = "Unscored"
            result.commentary = "No response-level NPS data entered for this month."
            result.imported_at = datetime.utcnow()
        return result

    if not result:
        result = KPIResult(
            reporting_month=reporting_month,
            scope="group",
            service_id=None,
            kpi_id=kpi.id,
        )
        db.session.add(result)

    summary = nps_summary(responses)
    result.value_numeric = value
    result.value_text = None
    result.rag = calculate_rag(kpi, value, None, None)
    result.source = "NPS responses"
    result.commentary = (
        f"Calculated from {summary['total']} response(s) across all services: "
        f"{summary['promoters']} promoter(s), {summary['passives']} passive(s), "
        f"{summary['detractors']} detractor(s)."
    )
    result.imported_at = datetime.utcnow()
    return result


def recalculate_after_response_change(reporting_month, service_id=None, sub_service_id=None):
    if sub_service_id:
        child = SLSubService.query.get(sub_service_id)
        if child:
            recalculate_sub_service_nps(child.id, reporting_month)
            recalculate_service_nps(child.parent_service_id, reporting_month)
    elif service_id:
        recalculate_service_nps(service_id, reporting_month)

    recalculate_group_nps(reporting_month)
    db.session.commit()
