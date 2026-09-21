from collections import defaultdict
from datetime import datetime

from app.extensions import db
from app.models import KPIDefinition, KPIResult, SLSubService, SLSubServiceKPIResult
from app.services.scoring import calculate_rag, rag_score


AGGREGATION_METHODS = {
    "average": "Average",
    "sum": "Sum",
    "worst_rag": "Worst RAG",
    "none": "Do not aggregate",
}


def _worst_result(results):
    order = {"Red": 0, "Amber": 1, "Green": 2, "Unscored": 3}
    return min(results, key=lambda r: order.get(r.rag, 3)) if results else None


def aggregate_parent_service(parent_service_id, reporting_month):
    """Roll active SL sub-service KPI results into the top-level Supported Living service.

    Parent KPI rows are stored as ordinary service results so all existing dashboards,
    hierarchy views and exports continue to work without counting child locations as
    additional top-level services.
    """
    children = (
        SLSubService.query
        .filter_by(parent_service_id=parent_service_id, active=True)
        .order_by(SLSubService.name)
        .all()
    )
    if not children:
        return 0

    child_ids = [child.id for child in children]
    child_results = (
        SLSubServiceKPIResult.query
        .filter(
            SLSubServiceKPIResult.reporting_month == reporting_month,
            SLSubServiceKPIResult.sub_service_id.in_(child_ids),
        )
        .all()
    )

    grouped = defaultdict(list)
    for result in child_results:
        grouped[result.kpi_id].append(result)

    kpis = KPIDefinition.query.filter_by(active=True, group_only=False).all()
    changed = 0

    for kpi in kpis:
        # NPS must be calculated from underlying individual responses, never by
        # averaging child NPS percentages. It is recalculated separately below.
        if kpi.code == "NPS_SCORE":
            continue
        results = grouped.get(kpi.id, [])
        method = (kpi.aggregation_method or "average").strip().lower()
        if method == "none":
            continue

        parent_result = KPIResult.query.filter_by(
            reporting_month=reporting_month,
            scope="service",
            service_id=parent_service_id,
            kpi_id=kpi.id,
        ).first()

        if not results:
            # If this KPI was previously generated from child services, clear the
            # stale roll-up when no active child now has a value. Imported/manual
            # parent values are left untouched until child data exists for the KPI.
            if parent_result and parent_result.source == "SL aggregate":
                parent_result.value_numeric = None
                parent_result.value_text = None
                parent_result.rag = "Unscored"
                parent_result.commentary = f"No child-level value entered across {len(children)} active Supported Living sub-services."
                parent_result.imported_at = datetime.utcnow()
                changed += 1
            continue

        numeric_values = [r.value_numeric for r in results if r.value_numeric is not None]
        value_numeric = None
        value_text = None
        rag = "Unscored"

        if method == "sum":
            if numeric_values:
                value_numeric = sum(numeric_values)
                rag = calculate_rag(kpi, value_numeric, None, None)
            else:
                worst = _worst_result(results)
                if worst:
                    value_text = worst.value_text
                    rag = worst.rag

        elif method == "worst_rag":
            worst = _worst_result(results)
            if worst:
                value_numeric = worst.value_numeric
                value_text = worst.value_text
                rag = worst.rag

        else:  # average
            if numeric_values:
                value_numeric = sum(numeric_values) / len(numeric_values)
                rag = calculate_rag(kpi, value_numeric, None, None)
            else:
                worst = _worst_result(results)
                if worst:
                    value_text = worst.value_text
                    rag = worst.rag

        if not parent_result:
            parent_result = KPIResult(
                reporting_month=reporting_month,
                scope="service",
                service_id=parent_service_id,
                kpi_id=kpi.id,
            )
            db.session.add(parent_result)

        parent_result.value_numeric = value_numeric
        parent_result.value_text = value_text
        parent_result.rag = rag
        parent_result.source = "SL aggregate"
        parent_result.commentary = (
            f"Automatically aggregated from {len(results)} of {len(children)} active "
            f"Supported Living sub-services using {AGGREGATION_METHODS.get(method, method)}."
        )
        parent_result.imported_at = datetime.utcnow()
        changed += 1

    db.session.commit()

    # Keep parent NPS mathematically correct by using all underlying responses.
    from app.services.nps import recalculate_service_nps, recalculate_group_nps
    recalculate_service_nps(parent_service_id, reporting_month)
    recalculate_group_nps(reporting_month)
    db.session.commit()
    return changed


def aggregate_all_parent_months(parent_service_id):
    months = [
        row[0]
        for row in db.session.query(SLSubServiceKPIResult.reporting_month)
        .join(SLSubService, SLSubService.id == SLSubServiceKPIResult.sub_service_id)
        .filter(SLSubService.parent_service_id == parent_service_id)
        .distinct()
        .all()
    ]
    total = 0
    for month in months:
        total += aggregate_parent_service(parent_service_id, month)
    return total


def sub_service_rows_for_month(parent_service_id, reporting_month):
    children = (
        SLSubService.query
        .filter_by(parent_service_id=parent_service_id, active=True)
        .order_by(SLSubService.name)
        .all()
    )
    expected_count = KPIDefinition.query.filter_by(active=True, group_only=False).count()
    rows = []
    for child in children:
        results = (
            SLSubServiceKPIResult.query
            .filter_by(reporting_month=reporting_month, sub_service_id=child.id)
            .join(KPIDefinition)
            .order_by(KPIDefinition.domain, KPIDefinition.name)
            .all()
        )
        weighted = 0.0
        weights = 0.0
        for result in results:
            score = rag_score(result.rag)
            if score is None:
                continue
            weight = result.kpi.weight or 1.0
            weighted += score * weight
            weights += weight
        score = round(weighted / weights, 2) if weights else None
        if score is None:
            overall = "Unscored"
        elif score >= 2.5:
            overall = "Green"
        elif score >= 1.75:
            overall = "Amber"
        else:
            overall = "Red"
        rows.append({
            "sub_service": child,
            "results": results,
            "score": score,
            "overall": overall,
            "red_count": sum(1 for r in results if r.rag == "Red"),
            "amber_count": sum(1 for r in results if r.rag == "Amber"),
            "entered_count": len(results),
            "expected_count": expected_count,
        })
    rows.sort(key=lambda row: row["sub_service"].name.lower())
    return rows


def sub_service_numeric_trends(sub_service_id, month_limit=12):
    months = [
        row[0]
        for row in SLSubServiceKPIResult.query.with_entities(SLSubServiceKPIResult.reporting_month)
        .filter_by(sub_service_id=sub_service_id)
        .distinct()
        .order_by(SLSubServiceKPIResult.reporting_month.desc())
        .limit(month_limit)
        .all()
    ]
    months = list(reversed(months))
    if not months:
        return []

    results = (
        SLSubServiceKPIResult.query
        .filter(
            SLSubServiceKPIResult.sub_service_id == sub_service_id,
            SLSubServiceKPIResult.reporting_month.in_(months),
            SLSubServiceKPIResult.value_numeric.isnot(None),
        )
        .join(KPIDefinition)
        .order_by(KPIDefinition.domain, KPIDefinition.name, SLSubServiceKPIResult.reporting_month)
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
