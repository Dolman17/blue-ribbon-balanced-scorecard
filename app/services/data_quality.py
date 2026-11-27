"""Read-only reporting quality review: it never recalculates stored KPI results."""
from collections import defaultdict
from app.models import (Service, SLSubService, KPIDefinition, KPIResult,
                        SLSubServiceKPIResult, NPSResponse)

NOT_APPLICABLE = {"n/a", "na", "not applicable", "not-applicable"}


def classify_result(result):
    """An absent row, an empty record, explicit N/A and numeric zero are different."""
    if result is None:
        return "Missing"
    if (result.value_text or "").strip().lower() in NOT_APPLICABLE:
        return "Not applicable"
    if result.value_numeric is not None:
        return "Zero" if result.value_numeric == 0 else "Present"
    if (result.value_text or "").strip():
        return "Present"
    return "Blank"


def quality_report(month, *, service_ids=None, regional_manager=None,
                   local_authority=None, service_type=None, nps_min_responses=5):
    """Review active service KPIs; no persisted configuration or score changes."""
    nps_min_responses = max(1, min(int(nps_min_responses), 100))
    query = Service.query.filter(Service.active.is_(True))
    if service_ids is not None:
        if not service_ids:
            return {"rows": [], "child_rows": [], "totals": {"expected": 0, "present": 0, "missing": 0, "blank": 0, "na": 0, "zero": 0}, "flags": [], "nps_min": nps_min_responses}
        query = query.filter(Service.id.in_(service_ids))
    if regional_manager:
        query = query.filter(Service.regional_manager == regional_manager)
    if local_authority:
        query = query.filter(Service.local_authority == local_authority)
    if service_type:
        query = query.filter(Service.service_type == service_type)
    services = query.order_by(Service.name).all()
    kpis = KPIDefinition.query.filter_by(active=True, group_only=False).order_by(KPIDefinition.name).all()
    ids = [s.id for s in services]
    children = (SLSubService.query.filter(SLSubService.active.is_(True),
                                          SLSubService.parent_service_id.in_(ids)).order_by(SLSubService.name).all()) if ids else []
    child_ids = [c.id for c in children]
    results = (KPIResult.query.filter(KPIResult.reporting_month == month, KPIResult.scope == "service",
                                     KPIResult.service_id.in_(ids)).all()) if ids and month else []
    child_results = (SLSubServiceKPIResult.query.filter(SLSubServiceKPIResult.reporting_month == month,
                          SLSubServiceKPIResult.sub_service_id.in_(child_ids)).all()) if child_ids and month else []
    nps_responses = (NPSResponse.query.filter(NPSResponse.reporting_month == month).filter(
        (NPSResponse.service_id.in_(ids)) | (NPSResponse.sub_service_id.in_(child_ids))).all()) if ids and month else []
    result_map = {(r.service_id, r.kpi_id): r for r in results}
    child_map = {(r.sub_service_id, r.kpi_id): r for r in child_results}
    direct_nps = defaultdict(int)
    child_nps = defaultdict(int)
    for r in nps_responses:
        if r.service_id is not None:
            direct_nps[r.service_id] += 1
        else:
            child_nps[r.sub_service_id] += 1
    children_by_parent = defaultdict(list)
    for child in children:
        children_by_parent[child.parent_service_id].append(child)
    totals = {"expected": 0, "present": 0, "missing": 0, "blank": 0, "na": 0, "zero": 0}
    rows, child_rows, flags = [], [], []

    def make_row(name, parent_id, link_id, results_map, unit_type, nps_count):
        summary = {"expected": len(kpis), "present": 0, "missing": 0, "blank": 0, "na": 0, "zero": 0}
        gaps = []
        for kpi in kpis:
            result = results_map.get((link_id, kpi.id))
            status = classify_result(result)
            if status in ("Present", "Zero"):
                summary["present"] += 1
            elif status == "Not applicable":
                summary["na"] += 1
            elif status == "Blank":
                summary["blank"] += 1
                gaps.append(kpi.name + " (blank)")
            else:
                summary["missing"] += 1
                gaps.append(kpi.name)
            if status == "Zero":
                summary["zero"] += 1
            if kpi.code == "VACANCY_PCT" and result is not None and result.value_numeric is not None and result.value_numeric < 0:
                flags.append({"service": name, "kind": "Negative vacancy", "detail": f"{result.value_numeric:g}% recorded; confirm this represents surplus staffing rather than an error."})
            if kpi.code == "NPS_SCORE" and result is not None and status in ("Present", "Zero") and nps_count < nps_min_responses:
                flags.append({"service": name, "kind": "Low NPS sample", "detail": f"{nps_count} recorded responses; advisory minimum is {nps_min_responses}. The displayed NPS is not altered."})
        summary["coverage"] = round(100 * summary["present"] / summary["expected"], 1) if summary["expected"] else None
        return dict(name=name, parent_id=parent_id, id=link_id, kind=unit_type, gaps=gaps, **summary)

    for service in services:
        count = direct_nps[service.id] + sum(child_nps[c.id] for c in children_by_parent[service.id])
        row = make_row(service.name, service.id, service.id, result_map, "Service", count)
        rows.append(row)
        for field in totals:
            totals[field] += row[field]
    for child in children:
        row = make_row(child.name, child.parent_service_id, child.id, child_map, "SL sub-service", child_nps[child.id])
        child_rows.append(row)
    for service in services:
        active_children = children_by_parent[service.id]
        if not active_children:
            continue
        for kpi in kpis:
            if kpi.code == "NPS_SCORE" or (kpi.aggregation_method or "average").lower() == "none":
                continue
            parent = result_map.get((service.id, kpi.id))
            if parent is None or parent.source != "SL aggregate":
                continue
            contributing = sum(classify_result(child_map.get((c.id, kpi.id))) in ("Present", "Zero") for c in active_children)
            if contributing < len(active_children):
                flags.append({"service": service.name, "kind": "SL roll-up coverage",
                              "detail": f"{kpi.name}: {contributing}/{len(active_children)} active sub-services have numeric or recorded values; verify the parent aggregate."})
    return dict(rows=rows, child_rows=child_rows, totals=totals, flags=flags, nps_min=nps_min_responses)
