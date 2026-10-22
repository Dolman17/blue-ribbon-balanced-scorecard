from datetime import date, datetime

import pandas as pd

from app.extensions import db
from app.models import (
    ImportLog,
    KPIDefinition,
    KPIResult,
    Service,
    SLSubService,
    SLSubServiceKPIResult,
)
from app.services.scoring import calculate_rag
from app.services.sl_aggregation import aggregate_parent_service


REQUIRED_SERVICE_COLUMNS = {"Service Code", "Service Name"}
REQUIRED_KPI_COLUMNS = {"Reporting Month", "Scope", "KPI Code", "Value"}


def _clean(value):
    if pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        return value if value else None
    return value


def _parse_month(value):
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return date(value.year, value.month, 1)
    parsed = pd.to_datetime(value, errors="raise")
    return date(parsed.year, parsed.month, 1)


def _normalise_code(value):
    cleaned = _clean(value)
    return str(cleaned).strip().upper() if cleaned is not None else ""


def _resolve_service_code(service_code):
    """Resolve a workbook Service Code to either a top-level service or SL sub-service.

    Existing workbook structure is retained: users continue to enter the reference in
    the Service Code column. The importer automatically detects whether the code is a
    top-level Service.code or an SLSubService.code.
    """
    code = _normalise_code(service_code)
    if not code:
        raise ValueError("Service Code is required for service-level rows")

    service = Service.query.filter(db.func.upper(Service.code) == code).first()
    sub_services = (
        SLSubService.query
        .filter(db.func.upper(SLSubService.code) == code)
        .all()
    )

    if service and sub_services:
        raise ValueError(
            f"Service Code '{code}' is ambiguous: it exists as both a top-level service "
            "and a Supported Living sub-service"
        )

    if len(sub_services) > 1:
        names = ", ".join(sorted(sub.name for sub in sub_services))
        raise ValueError(
            f"Supported Living reference '{code}' is used by more than one sub-service: {names}"
        )

    if service:
        return "service", service
    if sub_services:
        return "sl_sub_service", sub_services[0]

    raise ValueError(f"Unknown Service Code '{code}'")


def _split_value(kpi, raw_value):
    numeric_value = None
    text_value = None

    if kpi.direction in {"higher", "lower", "manual", "target_range"}:
        try:
            numeric_value = float(raw_value)
        except (TypeError, ValueError):
            text_value = str(raw_value)
    else:
        text_value = str(raw_value)

    return numeric_value, text_value


def import_workbook(file_source, original_filename):
    # file_source can be a filesystem path or an in-memory binary stream.
    # Using the ExcelFile object for subsequent reads keeps the importer
    # compatible with BytesIO uploads and avoids temporary-file path issues.
    xls = pd.ExcelFile(file_source, engine="openpyxl")
    if "Services" not in xls.sheet_names or "KPI_Data" not in xls.sheet_names:
        raise ValueError("Workbook must contain 'Services' and 'KPI_Data' sheets.")

    services_df = pd.read_excel(xls, sheet_name="Services")
    kpi_df = pd.read_excel(xls, sheet_name="KPI_Data")

    missing_services = REQUIRED_SERVICE_COLUMNS - set(services_df.columns)
    missing_kpis = REQUIRED_KPI_COLUMNS - set(kpi_df.columns)
    if missing_services:
        raise ValueError(f"Services sheet missing columns: {', '.join(sorted(missing_services))}")
    if missing_kpis:
        raise ValueError(f"KPI_Data sheet missing columns: {', '.join(sorted(missing_kpis))}")

    log = ImportLog(filename=original_filename, rows_received=len(kpi_df))
    db.session.add(log)
    db.session.flush()

    # The Services sheet continues to manage top-level services only. Supported
    # Living sub-services are maintained in the app and referenced from KPI_Data
    # by their own reference/code (for example BILLB, RIVER, SYCA, GREEN, etc.).
    for _, row in services_df.iterrows():
        code = _clean(row.get("Service Code"))
        name = _clean(row.get("Service Name"))
        if not code or not name:
            continue

        code = str(code).strip().upper()
        service = Service.query.filter(db.func.upper(Service.code) == code).first()
        if not service:
            service = Service(code=code, name=str(name))
            db.session.add(service)

        # A service amended in Master Data becomes the local source of truth.
        # Monthly workbook imports will still add/update KPI results, but will not
        # silently reverse hierarchy changes made in the app.
        if not service.manual_master_data:
            service.name = str(name)
            service.local_authority = _clean(row.get("Local Authority")) or _clean(row.get("Region"))
            service.regional_manager = _clean(row.get("Regional Manager"))
            service.registered_manager = _clean(row.get("Registered Manager"))
            service_type = _clean(row.get("Service Type"))
            if service_type:
                service_type = str(service_type).strip()
                if service_type not in {"Registered", "Supported Living"}:
                    raise ValueError(f"Invalid Service Type for {code}: {service_type}")
            service.service_type = service_type
            active = _clean(row.get("Active"))
            if active is not None:
                service.active = str(active).strip().lower() not in {"no", "n", "false", "0"}

    db.session.flush()

    errors = []
    imported = 0
    sl_rows_imported = 0
    affected_sl_parent_months = set()

    for excel_row, row in kpi_df.iterrows():
        row_no = excel_row + 2
        try:
            reporting_month = _parse_month(row.get("Reporting Month"))
            scope = str(_clean(row.get("Scope")) or "Service").strip().lower()
            if scope not in {"service", "group"}:
                raise ValueError("Scope must be Service or Group")

            kpi_code = _normalise_code(row.get("KPI Code"))
            kpi = KPIDefinition.query.filter_by(code=kpi_code, active=True).first()
            if not kpi:
                raise ValueError(f"Unknown KPI Code '{kpi_code}'")

            target_type = "group"
            target = None
            if scope == "service":
                target_type, target = _resolve_service_code(row.get("Service Code"))
                if kpi.group_only:
                    raise ValueError(f"{kpi.name} is configured as group-only")

            raw_value = _clean(row.get("Value"))
            if raw_value is None:
                raise ValueError("Value is blank")

            numeric_value, text_value = _split_value(kpi, raw_value)
            manual_rag = _clean(row.get("Manual RAG"))
            rag = calculate_rag(kpi, numeric_value, text_value, manual_rag)
            commentary = _clean(row.get("Commentary"))
            source = _clean(row.get("Source")) or "Workbook import"

            if target_type == "sl_sub_service":
                result = SLSubServiceKPIResult.query.filter_by(
                    reporting_month=reporting_month,
                    sub_service_id=target.id,
                    kpi_id=kpi.id,
                ).first()
                if not result:
                    result = SLSubServiceKPIResult(
                        reporting_month=reporting_month,
                        sub_service_id=target.id,
                        kpi_id=kpi.id,
                    )
                    db.session.add(result)

                result.value_numeric = numeric_value
                result.value_text = text_value
                result.rag = rag
                result.commentary = commentary
                result.source = source
                result.imported_at = datetime.utcnow()

                affected_sl_parent_months.add((target.parent_service_id, reporting_month))
                sl_rows_imported += 1

            else:
                service_id = target.id if target_type == "service" else None
                result = KPIResult.query.filter_by(
                    reporting_month=reporting_month,
                    scope=scope,
                    service_id=service_id,
                    kpi_id=kpi.id,
                ).first()
                if not result:
                    result = KPIResult(
                        reporting_month=reporting_month,
                        scope=scope,
                        service_id=service_id,
                        kpi_id=kpi.id,
                    )
                    db.session.add(result)

                result.value_numeric = numeric_value
                result.value_text = text_value
                result.rag = rag
                result.commentary = commentary
                result.source = source
                result.imported_at = datetime.utcnow()

            imported += 1
        except Exception as exc:
            errors.append(f"Row {row_no}: {exc}")

    log.rows_imported = imported
    log.rows_rejected = len(errors)
    log.status = "Completed with errors" if errors else "Completed"
    log.message = "\n".join(errors[:100]) if errors else "Import completed successfully."
    db.session.commit()

    # Recalculate each affected top-level Supported Living service after the
    # child-level rows have been committed. This keeps the normal service,
    # hierarchy and Executive dashboards in sync with the imported drill-down.
    aggregation_errors = []
    for parent_service_id, reporting_month in sorted(
        affected_sl_parent_months,
        key=lambda item: (item[1], item[0]),
    ):
        try:
            aggregate_parent_service(parent_service_id, reporting_month)
        except Exception as exc:
            aggregation_errors.append(
                f"Supported Living roll-up failed for service ID {parent_service_id} "
                f"({reporting_month:%Y-%m}): {exc}"
            )

    if aggregation_errors:
        log = db.session.get(ImportLog, log.id)
        log.status = "Completed with errors"
        existing = log.message or ""
        rollup_message = "\n".join(aggregation_errors)
        log.message = f"{existing}\n{rollup_message}".strip()
        db.session.commit()
        errors.extend(aggregation_errors)

    return {
        "rows_received": len(kpi_df),
        "rows_imported": imported,
        "sl_rows_imported": sl_rows_imported,
        "rows_rejected": len(errors),
        "errors": errors,
    }
