from collections import defaultdict
from datetime import date, datetime
from io import BytesIO

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from sqlalchemy import func, or_
from flask_login import current_user, login_user, logout_user

from .extensions import db
from .models import ImportLog, KPIDefinition, KPIResult, Service, User
from .services.analytics import (
    available_months,
    domain_scores_for_month,
    executive_trend,
    filter_options,
    latest_month,
    local_authority_rows_for_month,
    manager_rows_for_month,
    registered_manager_rows_for_month,
    resolve_month,
    service_numeric_trends,
    service_rows_for_month,
)
from .services.exporter import build_board_pack
from .services.importer import import_workbook
from .services.scoring import calculate_rag

bp = Blueprint("main", __name__)


USER_ROLES = ["Admin", "Executive", "Regional Manager", "Registered Manager", "Viewer"]


def _admin_required():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


@bp.before_request
def require_authentication():
    if request.endpoint in {"main.login", "main.setup"}:
        return None
    if User.query.count() == 0:
        return redirect(url_for("main.setup"))
    if not current_user.is_authenticated:
        return redirect(url_for("main.login", next=request.url))
    if not current_user.active:
        logout_user()
        flash("Your account is inactive.", "warning")
        return redirect(url_for("main.login"))
    return None


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if User.query.count() > 0:
        return redirect(url_for("main.login"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower() or None
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""

        errors = []
        if len(username) < 3:
            errors.append("Username must be at least 3 characters.")
        if len(password) < 10:
            errors.append("Password must be at least 10 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("setup.html")

        user = User(username=username, email=email, role="Admin", active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        user.last_login_at = datetime.utcnow()
        db.session.commit()
        flash("Administrator account created.", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("setup.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if User.query.count() == 0:
        return redirect(url_for("main.setup"))
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        identity = (request.form.get("identity") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter(or_(func.lower(User.username) == identity.lower(), func.lower(User.email) == identity.lower())).first()
        if not user or not user.active or not user.check_password(password):
            flash("Incorrect username/email or password.", "danger")
            return render_template("login.html", identity=identity)
        login_user(user, remember=request.form.get("remember") == "on")
        user.last_login_at = datetime.utcnow()
        db.session.commit()
        next_url = request.args.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("main.dashboard"))

    return render_template("login.html", identity="")


@bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.login"))


def _counts(results):
    counts = defaultdict(int)
    for result in results:
        counts[result.rag] += 1
    return dict(counts)


def _portfolio_score(service_rows):
    scores = [row["score"] for row in service_rows if row["score"] is not None]
    if not scores:
        return "Unscored", None
    score = round(sum(scores) / len(scores), 2)
    if score >= 2.5:
        rag = "Green"
    elif score >= 1.75:
        rag = "Amber"
    else:
        rag = "Red"
    return rag, score


@bp.route("/")
def dashboard():
    selected_month = resolve_month(request.args.get("month"))
    months = available_months()
    filters = {
        "regional_manager": (request.args.get("regional_manager") or "").strip(),
        "registered_manager": (request.args.get("registered_manager") or "").strip(),
        "local_authority": (request.args.get("local_authority") or "").strip(),
        "service_type": (request.args.get("service_type") or "").strip(),
        "service_id": request.args.get("service_id", type=int),
        "rag": (request.args.get("rag") or "").strip(),
    }
    options = filter_options(filters["regional_manager"] or None, filters["registered_manager"] or None, filters["local_authority"] or None, filters["service_type"] or None)

    if not selected_month:
        return render_template(
            "dashboard.html", selected_month=None, months=[], service_rows=[],
            top_services=[], bottom_services=[], group_results=[], counts={},
            domain_scores={}, trend=[], filters=filters, options=options,
        )

    service_rows = service_rows_for_month(
        selected_month, filters["local_authority"] or None, filters["regional_manager"] or None,
        filters["registered_manager"] or None, filters["service_id"], filters["rag"] or None, filters["service_type"] or None,
    )
    service_results = [r for row in service_rows for r in row["results"]]
    group_results = (
        KPIResult.query.filter_by(reporting_month=selected_month, scope="group")
        .join(KPIDefinition)
        .order_by(KPIDefinition.domain, KPIDefinition.name)
        .all()
    )
    scored = [row for row in service_rows if row["score"] is not None]
    bottom_services = scored[:5]
    top_services = list(reversed(scored[-5:]))

    return render_template(
        "dashboard.html", selected_month=selected_month, months=months,
        service_rows=service_rows, top_services=top_services, bottom_services=bottom_services,
        group_results=group_results, counts=_counts(service_results),
        domain_scores=domain_scores_for_month(
            selected_month, filters["local_authority"] or None, filters["regional_manager"] or None,
            filters["registered_manager"] or None, filters["service_id"], filters["rag"] or None, filters["service_type"] or None,
        ),
        trend=executive_trend(
            12, filters["local_authority"] or None, filters["regional_manager"] or None,
            filters["registered_manager"] or None, filters["service_id"], filters["rag"] or None, filters["service_type"] or None,
        ),
        filters=filters, options=options,
    )


@bp.route("/local-authorities")
def local_authorities():
    selected_month = resolve_month(request.args.get("month"))
    months = available_months()
    rows = local_authority_rows_for_month(selected_month) if selected_month else []
    return render_template("local_authorities.html", selected_month=selected_month, months=months, local_authority_rows=rows)


@bp.route("/local-authority/<path:local_authority_name>")
def local_authority_detail(local_authority_name):
    selected_month = resolve_month(request.args.get("month"))
    months = available_months()
    rows = service_rows_for_month(selected_month, local_authority=local_authority_name) if selected_month else []
    service_results = [r for row in rows for r in row["results"]]
    scored = [row for row in rows if row["score"] is not None]
    bottom_services = scored[:5]
    top_services = list(reversed(scored[-5:]))
    overall_rag, overall_score = _portfolio_score(rows)
    return render_template(
        "local_authority.html",
        local_authority_name=local_authority_name,
        selected_month=selected_month,
        months=months,
        service_rows=rows,
        counts=_counts(service_results),
        overall_rag=overall_rag,
        overall_score=overall_score,
        top_services=top_services,
        bottom_services=bottom_services,
        domain_scores=domain_scores_for_month(selected_month, local_authority=local_authority_name) if selected_month else {},
        trend=executive_trend(12, local_authority=local_authority_name) if selected_month else [],
    )


@bp.route("/regional-managers")
def regional_managers():
    selected_month = resolve_month(request.args.get("month"))
    months = available_months()
    rows = manager_rows_for_month(selected_month) if selected_month else []
    return render_template("regional_managers.html", selected_month=selected_month, months=months, manager_rows=rows)


@bp.route("/regional-manager/<path:manager_name>")
def regional_manager_detail(manager_name):
    selected_month = resolve_month(request.args.get("month"))
    months = available_months()
    rows = service_rows_for_month(selected_month, regional_manager=manager_name) if selected_month else []
    registered_managers = registered_manager_rows_for_month(selected_month, manager_name) if selected_month else []
    service_results = [r for row in rows for r in row["results"]]
    scored = [row for row in rows if row["score"] is not None]
    bottom_services = scored[:5]
    top_services = list(reversed(scored[-5:]))
    overall_rag, overall_score = _portfolio_score(rows)
    return render_template(
        "regional_manager.html", manager_name=manager_name, selected_month=selected_month,
        months=months, service_rows=rows, registered_manager_rows=registered_managers,
        counts=_counts(service_results), overall_rag=overall_rag, overall_score=overall_score,
        top_services=top_services, bottom_services=bottom_services,
        domain_scores=domain_scores_for_month(selected_month, regional_manager=manager_name) if selected_month else {},
        trend=executive_trend(12, regional_manager=manager_name) if selected_month else [],
    )


@bp.route("/regional-manager/<path:manager_name>/registered-manager/<path:registered_manager_name>")
def registered_manager_detail(manager_name, registered_manager_name):
    selected_month = resolve_month(request.args.get("month"))
    months = available_months()
    rows = service_rows_for_month(
        selected_month, regional_manager=manager_name, registered_manager=registered_manager_name
    ) if selected_month else []
    return render_template(
        "registered_manager.html", manager_name=manager_name, registered_manager_name=registered_manager_name,
        selected_month=selected_month, months=months, service_rows=rows,
        domain_scores=domain_scores_for_month(
            selected_month, regional_manager=manager_name, registered_manager=registered_manager_name
        ) if selected_month else {},
    )


@bp.route("/services", methods=["GET", "POST"])
def service_master():
    _admin_required()
    if request.method == "POST":
        service_id = request.form.get("service_id", type=int)
        service = Service.query.get_or_404(service_id)
        try:
            service.name = (request.form.get("name") or service.name).strip()
            service.regional_manager = (request.form.get("regional_manager") or "").strip() or None
            service.registered_manager = (request.form.get("registered_manager") or "").strip() or None
            service.local_authority = (request.form.get("local_authority") or "").strip() or None
            service_type = (request.form.get("service_type") or "").strip() or None
            if service_type not in {None, "Registered", "Supported Living"}:
                raise ValueError("Service Type must be Registered or Supported Living")
            service.service_type = service_type
            service.active = request.form.get("active") == "on"
            service.manual_master_data = True
            db.session.commit()
            flash(f"{service.name} updated. Manual master data will be retained on future workbook imports.", "success")
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        return redirect(url_for("main.service_master", q=request.args.get("q", "")))

    q = (request.args.get("q") or "").strip()
    query = Service.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Service.name.ilike(like),
                Service.code.ilike(like),
                Service.regional_manager.ilike(like),
                Service.registered_manager.ilike(like),
                Service.local_authority.ilike(like),
                Service.service_type.ilike(like),
            )
        )
    services = query.order_by(Service.active.desc(), Service.regional_manager, Service.registered_manager, Service.name).all()

    regional_managers = [r[0] for r in db.session.query(Service.regional_manager).filter(Service.regional_manager.isnot(None), Service.regional_manager != "").distinct().order_by(Service.regional_manager).all()]
    registered_managers = [r[0] for r in db.session.query(Service.registered_manager).filter(Service.registered_manager.isnot(None), Service.registered_manager != "").distinct().order_by(Service.registered_manager).all()]
    local_authorities = [r[0] for r in db.session.query(Service.local_authority).filter(Service.local_authority.isnot(None), Service.local_authority != "").distinct().order_by(Service.local_authority).all()]
    return render_template(
        "services.html", services=services, q=q,
        regional_managers=regional_managers, registered_managers=registered_managers,
        local_authorities=local_authorities, service_types=["Registered", "Supported Living"],
    )


@bp.route("/services/<int:service_id>/use-import-master", methods=["POST"])
def service_use_import_master(service_id):
    _admin_required()
    service = Service.query.get_or_404(service_id)
    service.manual_master_data = False
    db.session.commit()
    flash(f"{service.name} will use hierarchy details from the Services sheet on the next import.", "info")
    return redirect(url_for("main.service_master"))


@bp.route("/upload", methods=["GET", "POST"])
def upload():
    _admin_required()
    if request.method == "POST":
        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            flash("Choose an Excel workbook first.", "danger")
            return redirect(url_for("main.upload"))
        if not uploaded.filename.lower().endswith(".xlsx"):
            flash("Only .xlsx files are supported in this version.", "danger")
            return redirect(url_for("main.upload"))

        try:
            # Read the upload into memory instead of saving it to a temporary
            # Windows path. This avoids WinError 267 when Flask/Werkzeug
            # receives an uploaded workbook from certain browser/temp setups.
            workbook_bytes = uploaded.read()
            if not workbook_bytes:
                raise ValueError("The uploaded workbook is empty.")

            outcome = import_workbook(BytesIO(workbook_bytes), uploaded.filename)
            if outcome["rows_rejected"]:
                flash(f"Imported {outcome['rows_imported']} rows; {outcome['rows_rejected']} rejected. See Import Log.", "warning")
            else:
                flash(f"Imported {outcome['rows_imported']} KPI rows successfully.", "success")
            return redirect(url_for("main.dashboard"))
        except Exception as exc:
            flash(str(exc), "danger")

    logs = ImportLog.query.order_by(ImportLog.imported_at.desc()).limit(10).all()
    return render_template("upload.html", logs=logs)


@bp.route("/service/<int:service_id>")
def service_detail(service_id):
    service = Service.query.get_or_404(service_id)
    month_arg = request.args.get("month")
    selected_month = date.fromisoformat(month_arg + "-01") if month_arg else latest_month()

    results = []
    if selected_month:
        results = (
            KPIResult.query.filter_by(reporting_month=selected_month, scope="service", service_id=service.id)
            .join(KPIDefinition)
            .order_by(KPIDefinition.domain, KPIDefinition.name)
            .all()
        )

    months = [
        r[0]
        for r in KPIResult.query.with_entities(KPIResult.reporting_month)
        .filter_by(scope="service", service_id=service.id)
        .distinct()
        .order_by(KPIResult.reporting_month.desc())
        .all()
    ]
    return render_template(
        "service.html",
        service=service,
        results=results,
        selected_month=selected_month,
        months=months,
        trends=service_numeric_trends(service.id, 12),
    )




def _parse_manual_month(value):
    if not value:
        return latest_month() or date.today().replace(day=1)
    try:
        parsed = datetime.strptime(value, "%Y-%m")
        return date(parsed.year, parsed.month, 1)
    except ValueError as exc:
        raise ValueError("Reporting month must be in YYYY-MM format.") from exc


@bp.route("/manual-entry", methods=["GET", "POST"])
def manual_entry():
    _admin_required()
    services = Service.query.filter_by(active=True).order_by(Service.name).all()
    scope = (request.values.get("scope") or "service").strip().lower()
    if scope not in {"service", "group"}:
        scope = "service"

    service_id = request.values.get("service_id", type=int)
    if scope == "service" and not service_id and services:
        service_id = services[0].id
    service = Service.query.get(service_id) if service_id else None

    try:
        selected_month = _parse_manual_month(request.values.get("month"))
    except ValueError as exc:
        flash(str(exc), "danger")
        selected_month = latest_month() or date.today().replace(day=1)

    if request.method == "POST":
        if scope == "service" and not service:
            flash("Choose a service before saving KPI data.", "danger")
            return redirect(url_for("main.manual_entry", scope=scope, month=selected_month.strftime("%Y-%m")))

        kpis = KPIDefinition.query.filter_by(active=True).order_by(KPIDefinition.domain, KPIDefinition.name).all()
        if scope == "service":
            kpis = [k for k in kpis if not k.group_only]

        changed = 0
        created = 0
        errors = []
        for kpi in kpis:
            prefix = f"kpi_{kpi.id}_"
            raw_value = (request.form.get(prefix + "value") or "").strip()
            commentary = (request.form.get(prefix + "commentary") or "").strip() or None
            manual_rag = (request.form.get(prefix + "rag") or "").strip() or None

            # Blank rows are ignored, which lets users add only the information
            # that has become available without disturbing previously loaded data.
            if not raw_value:
                continue

            try:
                numeric_value = None
                text_value = None
                if kpi.direction in {"higher", "lower", "manual", "target_range"}:
                    try:
                        numeric_value = float(raw_value)
                    except (TypeError, ValueError):
                        text_value = raw_value
                else:
                    text_value = raw_value

                rag = calculate_rag(kpi, numeric_value, text_value, manual_rag)
                result = KPIResult.query.filter_by(
                    reporting_month=selected_month,
                    scope=scope,
                    service_id=service.id if service else None,
                    kpi_id=kpi.id,
                ).first()
                if not result:
                    result = KPIResult(
                        reporting_month=selected_month,
                        scope=scope,
                        service_id=service.id if service else None,
                        kpi_id=kpi.id,
                    )
                    db.session.add(result)
                    created += 1

                result.value_numeric = numeric_value
                result.value_text = text_value
                result.rag = rag
                result.commentary = commentary
                result.source = "Manual entry"
                result.imported_at = datetime.utcnow()
                changed += 1
            except Exception as exc:
                errors.append(f"{kpi.name}: {exc}")

        if errors:
            db.session.rollback()
            flash("Nothing was saved because of errors: " + " | ".join(errors[:5]), "danger")
        else:
            db.session.commit()
            updated = changed - created
            target = "Group" if scope == "group" else service.name
            flash(f"{target} / {selected_month.strftime('%B %Y')}: saved {changed} KPI record(s) ({created} new, {updated} amended).", "success")
        return redirect(url_for(
            "main.manual_entry", scope=scope,
            service_id=service.id if service else None,
            month=selected_month.strftime("%Y-%m"),
        ))

    kpis = KPIDefinition.query.filter_by(active=True).order_by(KPIDefinition.domain, KPIDefinition.name).all()
    if scope == "service":
        kpis = [k for k in kpis if not k.group_only]

    existing_results = {}
    if selected_month:
        query = KPIResult.query.filter_by(reporting_month=selected_month, scope=scope)
        if scope == "service" and service:
            query = query.filter_by(service_id=service.id)
        elif scope == "group":
            query = query.filter(KPIResult.service_id.is_(None))
        existing_results = {r.kpi_id: r for r in query.all()}

    rows = []
    for kpi in kpis:
        result = existing_results.get(kpi.id)
        if result:
            if result.value_numeric is not None:
                value = str(int(result.value_numeric)) if kpi.unit == "count" and float(result.value_numeric).is_integer() else str(result.value_numeric)
            else:
                value = result.value_text or ""
        else:
            value = ""
        rows.append({"kpi": kpi, "result": result, "value": value})

    return render_template(
        "manual_entry.html",
        services=services, service=service, service_id=service_id, scope=scope,
        selected_month=selected_month, rows=rows,
    )


@bp.route("/kpis", methods=["GET", "POST"])
def kpi_config():
    _admin_required()
    kpis = KPIDefinition.query.order_by(KPIDefinition.domain, KPIDefinition.name).all()
    if request.method == "POST":
        try:
            for kpi in kpis:
                prefix = f"kpi_{kpi.id}_"
                kpi.domain = (request.form.get(prefix + "domain") or kpi.domain).strip()
                kpi.direction = (request.form.get(prefix + "direction") or kpi.direction).strip()
                kpi.target_value = _optional_float(request.form.get(prefix + "target_value"))
                kpi.green_threshold = _optional_float(request.form.get(prefix + "green_threshold"))
                kpi.amber_threshold = _optional_float(request.form.get(prefix + "amber_threshold"))
                kpi.weight = _optional_float(request.form.get(prefix + "weight"), default=1.0)
                kpi.active = request.form.get(prefix + "active") == "on"
                kpi.group_only = request.form.get(prefix + "group_only") == "on"
                kpi.notes = (request.form.get(prefix + "notes") or "").strip() or None
            db.session.commit()

            if request.form.get("recalculate") == "yes":
                recalc_count = _recalculate_results()
                flash(f"KPI configuration saved and {recalc_count} historical result(s) recalculated.", "success")
            else:
                flash("KPI configuration saved. Existing historical RAGs were left unchanged.", "success")
            return redirect(url_for("main.kpi_config"))
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "danger")

    return render_template("kpis.html", kpis=kpis)


def _optional_float(value, default=None):
    if value is None or str(value).strip() == "":
        return default
    return float(value)


def _recalculate_results():
    count = 0
    for result in KPIResult.query.join(KPIDefinition).all():
        if result.kpi.direction == "manual":
            continue
        result.rag = calculate_rag(result.kpi, result.value_numeric, result.value_text, None)
        count += 1
    db.session.commit()
    return count


@bp.route("/users")
def user_management():
    _admin_required()
    users = User.query.order_by(User.active.desc(), User.username).all()
    return render_template("users.html", users=users, roles=USER_ROLES)


@bp.route("/users/new", methods=["GET", "POST"])
def user_create():
    _admin_required()
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower() or None
        role = (request.form.get("role") or "Viewer").strip()
        password = request.form.get("password") or ""
        if role not in USER_ROLES:
            role = "Viewer"
        if len(username) < 3 or len(password) < 10:
            flash("Username must be at least 3 characters and password at least 10 characters.", "danger")
            return render_template("user_form.html", user=None, roles=USER_ROLES)
        if User.query.filter(func.lower(User.username) == username.lower()).first():
            flash("That username already exists.", "danger")
            return render_template("user_form.html", user=None, roles=USER_ROLES)
        if email and User.query.filter(func.lower(User.email) == email.lower()).first():
            flash("That email address is already in use.", "danger")
            return render_template("user_form.html", user=None, roles=USER_ROLES)
        user = User(
            username=username, email=email, role=role, active=request.form.get("active") == "on",
            regional_manager=(request.form.get("regional_manager") or "").strip() or None,
            registered_manager=(request.form.get("registered_manager") or "").strip() or None,
            local_authority=(request.form.get("local_authority") or "").strip() or None,
            service_id=request.form.get("service_id", type=int),
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f"User {user.username} created.", "success")
        return redirect(url_for("main.user_management"))
    return render_template("user_form.html", user=None, roles=USER_ROLES)


@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
def user_edit(user_id):
    _admin_required()
    user = User.query.get_or_404(user_id)
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower() or None
        role = (request.form.get("role") or user.role).strip()
        if role not in USER_ROLES:
            role = "Viewer"
        duplicate_username = User.query.filter(func.lower(User.username) == username.lower(), User.id != user.id).first()
        duplicate_email = email and User.query.filter(func.lower(User.email) == email.lower(), User.id != user.id).first()
        if duplicate_username or duplicate_email:
            flash("Username or email is already in use.", "danger")
            return render_template("user_form.html", user=user, roles=USER_ROLES)
        user.username = username
        user.email = email
        user.role = role
        user.regional_manager = (request.form.get("regional_manager") or "").strip() or None
        user.registered_manager = (request.form.get("registered_manager") or "").strip() or None
        user.local_authority = (request.form.get("local_authority") or "").strip() or None
        user.service_id = request.form.get("service_id", type=int)
        if user.id == current_user.id:
            user.active = True
        else:
            user.active = request.form.get("active") == "on"
        password = request.form.get("password") or ""
        if password:
            if len(password) < 10:
                flash("New password must be at least 10 characters.", "danger")
                return render_template("user_form.html", user=user, roles=USER_ROLES)
            user.set_password(password)
        db.session.commit()
        flash(f"User {user.username} updated.", "success")
        return redirect(url_for("main.user_management"))
    return render_template("user_form.html", user=user, roles=USER_ROLES)


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
def user_delete(user_id):
    _admin_required()
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot delete the account you are currently signed in with.", "warning")
        return redirect(url_for("main.user_management"))
    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f"User {username} deleted.", "success")
    return redirect(url_for("main.user_management"))


@bp.route("/export/board")
def export_board():
    selected_month = resolve_month(request.args.get("month"))
    if not selected_month:
        flash("Import data before exporting a Board scorecard.", "warning")
        return redirect(url_for("main.dashboard"))

    output = build_board_pack(selected_month)
    filename = f"Blue_Ribbon_Balanced_Scorecard_{selected_month.strftime('%Y_%m')}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
