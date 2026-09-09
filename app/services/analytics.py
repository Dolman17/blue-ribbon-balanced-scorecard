from collections import defaultdict
from datetime import date

from sqlalchemy import func

from app.models import KPIDefinition, KPIResult, Service
from app.services.scoring import rag_score


def latest_month():
    return KPIResult.query.with_entities(func.max(KPIResult.reporting_month)).scalar()


def available_months():
    return [
        row[0]
        for row in KPIResult.query.with_entities(KPIResult.reporting_month)
        .distinct()
        .order_by(KPIResult.reporting_month.desc())
        .all()
    ]


def resolve_month(month_arg=None):
    if month_arg:
        try:
            return date.fromisoformat(f"{month_arg}-01")
        except ValueError:
            return latest_month()
    return latest_month()


def filter_options(regional_manager=None, registered_manager=None, local_authority=None, service_type=None):
    active = Service.query.filter(Service.active.is_(True))

    regional_managers = [
        r[0] for r in active.with_entities(Service.regional_manager)
        .filter(Service.regional_manager.isnot(None))
        .distinct().order_by(Service.regional_manager).all() if r[0]
    ]

    rm_query = Service.query.filter(Service.active.is_(True), Service.registered_manager.isnot(None))
    if regional_manager:
        rm_query = rm_query.filter(Service.regional_manager == regional_manager)
    registered_managers = [
        r[0] for r in rm_query.with_entities(Service.registered_manager)
        .distinct().order_by(Service.registered_manager).all() if r[0]
    ]

    la_query = Service.query.filter(Service.active.is_(True), Service.local_authority.isnot(None))
    if regional_manager:
        la_query = la_query.filter(Service.regional_manager == regional_manager)
    if registered_manager:
        la_query = la_query.filter(Service.registered_manager == registered_manager)
    local_authorities = [
        r[0] for r in la_query.with_entities(Service.local_authority)
        .distinct().order_by(Service.local_authority).all() if r[0]
    ]

    service_types = ["Registered", "Supported Living"]

    services_query = Service.query.filter(Service.active.is_(True))
    if regional_manager:
        services_query = services_query.filter(Service.regional_manager == regional_manager)
    if registered_manager:
        services_query = services_query.filter(Service.registered_manager == registered_manager)
    if local_authority:
        services_query = services_query.filter(Service.local_authority == local_authority)
    if service_type:
        services_query = services_query.filter(Service.service_type == service_type)
    services = services_query.order_by(Service.name).all()

    return {
        "regional_managers": regional_managers,
        "registered_managers": registered_managers,
        "local_authorities": local_authorities,
        "service_types": service_types,
        "services": services,
    }


def overall_for_results(results):
    weighted_total = 0.0
    weight_total = 0.0
    for result in results:
        score = rag_score(result.rag)
        if score is None:
            continue
        weight = result.kpi.weight or 1.0
        weighted_total += score * weight
        weight_total += weight

    if not weight_total:
        return "Unscored", None

    score = weighted_total / weight_total
    if score >= 2.5:
        rag = "Green"
    elif score >= 1.75:
        rag = "Amber"
    else:
        rag = "Red"
    return rag, round(score, 2)


def service_rows_for_month(
    reporting_month,
    local_authority=None,
    regional_manager=None,
    registered_manager=None,
    service_id=None,
    overall_rag=None,
    service_type=None,
):
    query = KPIResult.query.filter_by(reporting_month=reporting_month, scope="service").join(Service)
    if local_authority:
        query = query.filter(Service.local_authority == local_authority)
    if regional_manager:
        query = query.filter(Service.regional_manager == regional_manager)
    if registered_manager:
        query = query.filter(Service.registered_manager == registered_manager)
    if service_id:
        query = query.filter(Service.id == service_id)
    if service_type:
        query = query.filter(Service.service_type == service_type)
    results = query.all()

    grouped = defaultdict(list)
    for result in results:
        grouped[result.service].append(result)

    rows = []
    for service, service_results in grouped.items():
        overall, score = overall_for_results(service_results)
        if overall_rag and overall != overall_rag:
            continue
        rows.append({
            "service": service,
            "overall": overall,
            "score": score,
            "red_count": sum(1 for r in service_results if r.rag == "Red"),
            "amber_count": sum(1 for r in service_results if r.rag == "Amber"),
            "results": service_results,
        })

    rows.sort(key=lambda row: (row["score"] is None, row["score"] if row["score"] is not None else 99, row["service"].name))
    return rows


def domain_scores_for_month(
    reporting_month,
    local_authority=None,
    regional_manager=None,
    registered_manager=None,
    service_id=None,
    overall_rag=None,
    service_type=None,
):
    rows = service_rows_for_month(
        reporting_month, local_authority, regional_manager, registered_manager, service_id, overall_rag, service_type
    )
    bucket = defaultdict(lambda: {"weighted": 0.0, "weights": 0.0})
    for row in rows:
        for result in row["results"]:
            score = rag_score(result.rag)
            if score is None:
                continue
            weight = result.kpi.weight or 1.0
            bucket[result.kpi.domain]["weighted"] += score * weight
            bucket[result.kpi.domain]["weights"] += weight

    return {
        domain: round(values["weighted"] / values["weights"], 2)
        for domain, values in bucket.items() if values["weights"]
    }


def _summary_row(name_key, name, rows):
    scored = [r["score"] for r in rows if r["score"] is not None]
    avg = round(sum(scored) / len(scored), 2) if scored else None
    if avg is None:
        overall = "Unscored"
    elif avg >= 2.5:
        overall = "Green"
    elif avg >= 1.75:
        overall = "Amber"
    else:
        overall = "Red"
    return {
        name_key: name,
        "score": avg,
        "overall": overall,
        "service_count": len(rows),
        "red_services": sum(1 for r in rows if r["overall"] == "Red"),
        "amber_services": sum(1 for r in rows if r["overall"] == "Amber"),
    }


def local_authority_rows_for_month(reporting_month):
    grouped = defaultdict(list)
    for row in service_rows_for_month(reporting_month):
        grouped[row["service"].local_authority or "Unassigned"].append(row)
    rows = [_summary_row("local_authority", name, values) for name, values in grouped.items()]
    rows.sort(key=lambda r: (r["score"] is None, r["score"] if r["score"] is not None else 99, r["local_authority"]))
    return rows


def manager_rows_for_month(reporting_month):
    grouped = defaultdict(list)
    for row in service_rows_for_month(reporting_month):
        grouped[row["service"].regional_manager or "Unassigned"].append(row)
    rows = []
    for manager, values in grouped.items():
        summary = _summary_row("regional_manager", manager, values)
        summary["registered_manager_count"] = len({r["service"].registered_manager or "Unassigned" for r in values})
        rows.append(summary)
    rows.sort(key=lambda r: (r["score"] is None, r["score"] if r["score"] is not None else 99, r["regional_manager"]))
    return rows


def registered_manager_rows_for_month(reporting_month, regional_manager=None):
    grouped = defaultdict(list)
    rows = service_rows_for_month(reporting_month, regional_manager=regional_manager)
    for row in rows:
        grouped[row["service"].registered_manager or "Unassigned"].append(row)
    summaries = []
    for manager, values in grouped.items():
        summary = _summary_row("registered_manager", manager, values)
        summary["regional_manager"] = values[0]["service"].regional_manager or "Unassigned"
        summaries.append(summary)
    summaries.sort(key=lambda r: (r["score"] is None, r["score"] if r["score"] is not None else 99, r["registered_manager"]))
    return summaries


def executive_trend(
    month_limit=12,
    local_authority=None,
    regional_manager=None,
    registered_manager=None,
    service_id=None,
    overall_rag=None,
    service_type=None,
):
    months = list(reversed(available_months()[:month_limit]))
    trend = []
    for month in months:
        rows = service_rows_for_month(
            month, local_authority, regional_manager, registered_manager, service_id, overall_rag, service_type
        )
        scores = [row["score"] for row in rows if row["score"] is not None]
        score = round(sum(scores) / len(scores), 2) if scores else None
        trend.append({"month": month, "score": score})
    return trend


def service_numeric_trends(service_id, month_limit=12):
    months = [
        row[0]
        for row in KPIResult.query.with_entities(KPIResult.reporting_month)
        .filter_by(scope="service", service_id=service_id)
        .distinct().order_by(KPIResult.reporting_month.desc()).limit(month_limit).all()
    ]
    months = list(reversed(months))
    if not months:
        return []

    results = (
        KPIResult.query.filter(
            KPIResult.scope == "service",
            KPIResult.service_id == service_id,
            KPIResult.reporting_month.in_(months),
            KPIResult.value_numeric.isnot(None),
        )
        .join(KPIDefinition)
        .order_by(KPIDefinition.domain, KPIDefinition.name, KPIResult.reporting_month)
        .all()
    )

    grouped = defaultdict(list)
    for result in results:
        grouped[result.kpi].append(result)

    return [
        {
            "kpi": kpi,
            "points": [
                {"month": result.reporting_month, "value": result.value_numeric, "rag": result.rag}
                for result in kpi_results
            ],
        }
        for kpi, kpi_results in grouped.items()
    ]
