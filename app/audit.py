"""Best-effort change audit within the same SQLAlchemy transaction as the edit.

Do not store passwords, free-text feedback or other sensitive field values in logs.
"""
import json
from flask import has_request_context
from flask_login import current_user
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from .models import AuditEvent, Service, SLSubService, KPIResult, SLSubServiceKPIResult, KPIDefinition, NPSResponse, User, ImprovementAction, ImprovementActionEvent, BoardReportNarrative

AUDITED = (Service, SLSubService, KPIResult, SLSubServiceKPIResult, KPIDefinition, NPSResponse, User, ImprovementAction, ImprovementActionEvent, BoardReportNarrative)

@event.listens_for(Session, "before_flush")
def audit_changes(session, flush_context, instances):
    if not has_request_context():
        return
    actor_id = current_user.id if current_user.is_authenticated else None
    for target in list(session.new) + list(session.dirty) + list(session.deleted):
        if not isinstance(target, AUDITED):
            continue
        is_new = target in session.new
        is_deleted = target in session.deleted
        state = inspect(target)
        fields = []
        if not is_new and not is_deleted:
            for attr in state.mapper.column_attrs:
                key = attr.key
                if key in ("updated_at", "imported_at"):
                    continue
                if state.attrs[key].history.has_changes():
                    fields.append(key)
            if not fields:
                continue
        session.add(AuditEvent(
            actor_id=actor_id,
            action="create" if is_new else "delete" if is_deleted else "update",
            entity_type=target.__class__.__name__,
            entity_id=str(state.identity[0]) if state.identity else None,
            changed_fields=json.dumps(fields if not (is_new or is_deleted) else ["record"]),
        ))
