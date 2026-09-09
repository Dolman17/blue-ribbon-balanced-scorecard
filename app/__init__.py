from pathlib import Path

from flask import Flask
from sqlalchemy import inspect, text

from config import Config
from .extensions import db, login_manager, migrate


def _ensure_compatible_schema():
    """Keep older local SQLite databases compatible with current service master data."""
    inspector = inspect(db.engine)
    if "service" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("service")}
    with db.engine.begin() as connection:
        if "regional_manager" not in columns:
            connection.execute(text("ALTER TABLE service ADD COLUMN regional_manager VARCHAR(150)"))
        if "local_authority" not in columns:
            connection.execute(text("ALTER TABLE service ADD COLUMN local_authority VARCHAR(150)"))
            if "region" in columns:
                connection.execute(text("UPDATE service SET local_authority = region WHERE local_authority IS NULL"))
        if "service_type" not in columns:
            connection.execute(text("ALTER TABLE service ADD COLUMN service_type VARCHAR(40)"))
        if "manual_master_data" not in columns:
            connection.execute(text("ALTER TABLE service ADD COLUMN manual_master_data BOOLEAN NOT NULL DEFAULT 0"))
        if "updated_at" not in columns:
            connection.execute(text("ALTER TABLE service ADD COLUMN updated_at DATETIME"))
            connection.execute(text("UPDATE service SET updated_at = created_at WHERE updated_at IS NULL"))

    inspector = inspect(db.engine)
    if "kpi_definition" in inspector.get_table_names():
        kpi_columns = {column["name"] for column in inspector.get_columns("kpi_definition")}
        with db.engine.begin() as connection:
            if "target_value" not in kpi_columns:
                connection.execute(text("ALTER TABLE kpi_definition ADD COLUMN target_value FLOAT"))


def _format_kpi_value(value, unit=None):
    """Display KPI values cleanly, especially whole-number count measures."""
    if value is None:
        return ""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)

    # Count KPIs (e.g. Safeguardings, Complaints, Whistleblowing) should
    # display as whole numbers whenever the imported value is integral.
    if unit == "count" and numeric.is_integer():
        display = str(int(numeric))
    elif abs(numeric) < 1e-12:
        display = "0"
    else:
        display = str(value)

    return f"{display}%" if unit == "%" else display


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.jinja_env.filters["kpi_value"] = _format_kpi_value

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "main.login"
    login_manager.login_message = "Please sign in to access the Balanced Scorecard."
    login_manager.login_message_category = "info"

    from . import models  # noqa: F401

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return models.User.query.get(int(user_id))
        except (TypeError, ValueError):
            return None
    from .routes import bp

    app.register_blueprint(bp)

    with app.app_context():
        db.create_all()
        _ensure_compatible_schema()
        from .services.scoring import seed_default_kpis
        seed_default_kpis()

    return app
