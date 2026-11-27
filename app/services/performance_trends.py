"""Read-only, permission-scoped performance comparisons. Never alter recorded KPI results."""
from collections import defaultdict
from app.models import KPIResult, Service
from app.services.analytics import overall_for_results

RAG_ORDER = {"Red": 0, "Amber": 1, "Green": 2}


def compare_performance(current_month, previous_month, *, service_ids=None, local_authority=None,
                        service_type=None, regional_manager=None, registered_manager=None):
    """Compare like-for-like services and KPI results across reporting months.

    A missing KPI is not treated as an improvement or deterioration. A missing
    service/month score is not treated as zero. Aggregate movement excludes
    unmatched services, and only scored results contribute to totals.
    """
    services = Service.query.filter(Service.active.is_(True))
    if service_ids is not None:
        if not service_ids:
            return _empty(current_month, previous_month)
        services = services.filter(Service.id.in_(service_ids))
    if local_authority:
        services = services.filter(Service.local_authority == local_authority)
    if service_type:
        services = services.filter(Service.service_type == service_type)
    if regional_manager:
        services = services.filter(Service.regional_manager == regional_manager)
    if registered_manager:
        services = services.filter(Service.registered_manager == registered_manager)
    selected_services = services.order_by(Service.name).all()
    if not selected_services:
        return _empty(current_month, previous_month)
    ids = [s.id for s in selected_services]
    months = [current_month] + ([previous_month] if previous_month else [])
    results = KPIResult.query.filter(KPIResult.scope == 'service', KPIResult.service_id.in_(ids),
                                     KPIResult.reporting_month.in_(months)).all()
    by_month_service = defaultdict(list)
    for result in results:
        by_month_service[(result.reporting_month, result.service_id)].append(result)

    rows = []
    transitions = []
    improving = declining = unchanged = 0
    for service in selected_services:
        current = by_month_service.get((current_month, service.id), [])
        previous = by_month_service.get((previous_month, service.id), []) if previous_month else []
        if not current and not previous:
            continue
        current_rag, current_score = overall_for_results(current)
        previous_rag, previous_score = overall_for_results(previous)
        delta = round(current_score - previous_score, 2) if current_score is not None and previous_score is not None else None
        if delta is not None:
            if delta > 0: improving += 1
            elif delta < 0: declining += 1
            else: unchanged += 1
        rows.append(dict(service=service, current=current_score, previous=previous_score,
                         current_rag=current_rag, previous_rag=previous_rag, delta=delta,
                         scored_current=sum(r.rag in RAG_ORDER for r in current),
                         scored_previous=sum(r.rag in RAG_ORDER for r in previous)))
        old_kpis = {r.kpi_id: r for r in previous}
        for item in current:
            old = old_kpis.get(item.kpi_id)
            if not old or item.rag not in RAG_ORDER or old.rag not in RAG_ORDER:
                continue
            change = RAG_ORDER[item.rag] - RAG_ORDER[old.rag]
            if change:
                transitions.append(dict(service=service, kpi=item.kpi, previous=old.rag,
                                        current=item.rag, direction='Improved' if change > 0 else 'Deteriorated',
                                        steps=abs(change)))
    comparable = [r for r in rows if r['delta'] is not None]
    avg_change = round(sum(r['delta'] for r in comparable)/len(comparable), 2) if comparable else None
    return dict(current_month=current_month, previous_month=previous_month, rows=rows,
                ranked=sorted([r for r in rows if r['current'] is not None], key=lambda r: (-r['current'], r['service'].name)),
                improving=improving, declining=declining, unchanged=unchanged,
                comparable=len(comparable), avg_change=avg_change,
                transitions=sorted(transitions, key=lambda x:(x['direction'] != 'Deteriorated', -x['steps'], x['service'].name, x['kpi'].name)))


def _empty(current_month, previous_month):
    return dict(current_month=current_month, previous_month=previous_month, rows=[], ranked=[],
                improving=0, declining=0, unchanged=0, comparable=0, avg_change=None, transitions=[])
