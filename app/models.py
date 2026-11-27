from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    local_authority = db.Column(db.String(150), nullable=True, index=True)
    regional_manager = db.Column(db.String(150), nullable=True, index=True)
    registered_manager = db.Column(db.String(150), nullable=True)
    service_type = db.Column(db.String(40), nullable=True, index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    manual_master_data = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class SLSubService(db.Model):
    """A drill-down location/service that sits beneath a top-level Supported Living service."""

    id = db.Column(db.Integer, primary_key=True)
    parent_service_id = db.Column(db.Integer, db.ForeignKey("service.id"), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    code = db.Column(db.String(80), nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    parent_service = db.relationship(
        "Service",
        backref=db.backref("sl_sub_services", lazy=True, cascade="all, delete-orphan"),
    )

    __table_args__ = (
        db.UniqueConstraint("parent_service_id", "name", name="uq_sl_sub_service_parent_name"),
    )


class KPIDefinition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), unique=True, nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    domain = db.Column(db.String(80), nullable=False)
    unit = db.Column(db.String(30), nullable=True)
    direction = db.Column(db.String(20), nullable=False, default="manual")
    target_value = db.Column(db.Float, nullable=True)
    green_threshold = db.Column(db.Float, nullable=True)
    amber_threshold = db.Column(db.Float, nullable=True)
    weight = db.Column(db.Float, nullable=False, default=1.0)
    group_only = db.Column(db.Boolean, nullable=False, default=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    aggregation_method = db.Column(db.String(30), nullable=False, default="average")
    notes = db.Column(db.Text, nullable=True)


class KPIResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reporting_month = db.Column(db.Date, nullable=False, index=True)
    scope = db.Column(db.String(20), nullable=False, default="service")
    service_id = db.Column(db.Integer, db.ForeignKey("service.id"), nullable=True, index=True)
    kpi_id = db.Column(db.Integer, db.ForeignKey("kpi_definition.id"), nullable=False, index=True)
    value_numeric = db.Column(db.Float, nullable=True)
    value_text = db.Column(db.String(255), nullable=True)
    rag = db.Column(db.String(20), nullable=False, default="Unscored")
    commentary = db.Column(db.Text, nullable=True)
    source = db.Column(db.String(100), nullable=True)
    imported_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    service = db.relationship("Service", backref="results")
    kpi = db.relationship("KPIDefinition", backref="results")

    __table_args__ = (
        db.UniqueConstraint(
            "reporting_month", "scope", "service_id", "kpi_id",
            name="uq_month_scope_service_kpi",
        ),
    )


class SLSubServiceKPIResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reporting_month = db.Column(db.Date, nullable=False, index=True)
    sub_service_id = db.Column(db.Integer, db.ForeignKey("sl_sub_service.id"), nullable=False, index=True)
    kpi_id = db.Column(db.Integer, db.ForeignKey("kpi_definition.id"), nullable=False, index=True)
    value_numeric = db.Column(db.Float, nullable=True)
    value_text = db.Column(db.String(255), nullable=True)
    rag = db.Column(db.String(20), nullable=False, default="Unscored")
    commentary = db.Column(db.Text, nullable=True)
    source = db.Column(db.String(100), nullable=False, default="Manual entry")
    imported_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    sub_service = db.relationship("SLSubService", backref="kpi_results")
    kpi = db.relationship("KPIDefinition", backref="sl_sub_service_results")

    __table_args__ = (
        db.UniqueConstraint(
            "reporting_month", "sub_service_id", "kpi_id",
            name="uq_month_sl_sub_service_kpi",
        ),
    )


class NPSResponse(db.Model):
    """Individual monthly NPS response attached to a top-level or SL sub-service."""

    id = db.Column(db.Integer, primary_key=True)
    reporting_month = db.Column(db.Date, nullable=False, index=True)
    response_date = db.Column(db.Date, nullable=True)
    service_id = db.Column(db.Integer, db.ForeignKey("service.id"), nullable=True, index=True)
    sub_service_id = db.Column(db.Integer, db.ForeignKey("sl_sub_service.id"), nullable=True, index=True)
    score = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    source = db.Column(db.String(150), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    service = db.relationship("Service", backref="nps_responses")
    sub_service = db.relationship("SLSubService", backref="nps_responses")

    @property
    def category(self):
        if self.score >= 9:
            return "Promoter"
        if self.score >= 7:
            return "Passive"
        return "Detractor"

    __table_args__ = (
        db.CheckConstraint("score >= 0 AND score <= 10", name="ck_nps_response_score_0_10"),
        db.CheckConstraint(
            "(service_id IS NOT NULL AND sub_service_id IS NULL) OR "
            "(service_id IS NULL AND sub_service_id IS NOT NULL)",
            name="ck_nps_response_single_scope",
        ),
    )


class ImportLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    imported_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    rows_received = db.Column(db.Integer, nullable=False, default=0)
    rows_imported = db.Column(db.Integer, nullable=False, default=0)
    rows_rejected = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(30), nullable=False, default="Completed")
    message = db.Column(db.Text, nullable=True)


class AuditEvent(db.Model):
    """Minimal audit trail for governance-sensitive database mutations."""
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, nullable=True, index=True)
    action = db.Column(db.String(12), nullable=False)
    entity_type = db.Column(db.String(60), nullable=False)
    entity_id = db.Column(db.String(80), nullable=True)
    changed_fields = db.Column(db.Text, nullable=True)
    occurred_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class LoginAttempt(db.Model):
    """Rolling 15-minute authentication failure counter, shared by all workers."""
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(80), nullable=False, index=True)
    identity_hash = db.Column(db.String(64), nullable=False, index=True)
    action = db.Column(db.String(12), nullable=False, default="login")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(180), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(40), nullable=False, default="Admin", index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)

    # Reserved scope fields for future role-based portfolio access.
    regional_manager = db.Column(db.String(150), nullable=True, index=True)
    registered_manager = db.Column(db.String(150), nullable=True, index=True)
    local_authority = db.Column(db.String(150), nullable=True, index=True)
    service_id = db.Column(db.Integer, db.ForeignKey("service.id"), nullable=True, index=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    # Per-user Executive dashboard widget order (JSON array of widget IDs).
    dashboard_layout = db.Column(db.Text, nullable=True)

    service = db.relationship("Service", foreign_keys=[service_id])

    @property
    def is_active(self):
        return bool(self.active)

    @property
    def is_admin(self):
        return self.role == "Admin"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class ImprovementAction(db.Model):
    """Accountable improvement linked to a historical Red/Amber KPI result."""
    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey("service.id"), nullable=False, index=True)
    sub_service_id = db.Column(db.Integer, db.ForeignKey("sl_sub_service.id"), nullable=True, index=True)
    kpi_id = db.Column(db.Integer, db.ForeignKey("kpi_definition.id"), nullable=False, index=True)
    reporting_month = db.Column(db.Date, nullable=False, index=True)
    source_rag = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False)
    owner = db.Column(db.String(150), nullable=False)
    due_date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="Open", index=True)
    priority = db.Column(db.String(12), nullable=False, default="Medium")
    evidence_url = db.Column(db.String(1000), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    service = db.relationship("Service", foreign_keys=[service_id])
    sub_service = db.relationship("SLSubService", foreign_keys=[sub_service_id])
    kpi = db.relationship("KPIDefinition", foreign_keys=[kpi_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])


class ImprovementActionEvent(db.Model):
    """Append-only action history; never deletes existing entries."""
    id = db.Column(db.Integer, primary_key=True)
    action_id = db.Column(db.Integer, db.ForeignKey("improvement_action.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    occurred_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    previous_status = db.Column(db.String(30), nullable=True)
    new_status = db.Column(db.String(30), nullable=False)
    note = db.Column(db.Text, nullable=False)
    action = db.relationship("ImprovementAction", backref=db.backref("events", lazy="select", order_by="ImprovementActionEvent.occurred_at.desc()"))
    author = db.relationship("User")
