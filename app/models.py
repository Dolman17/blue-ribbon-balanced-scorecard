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


class ImportLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    imported_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    rows_received = db.Column(db.Integer, nullable=False, default=0)
    rows_imported = db.Column(db.Integer, nullable=False, default=0)
    rows_rejected = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(30), nullable=False, default="Completed")
    message = db.Column(db.Text, nullable=True)


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
