from datetime import date, datetime
from pathlib import Path

import pandas as pd

from app.extensions import db
from app.models import ImportLog, KPIDefinition, KPIResult, Service
from app.services.scoring import calculate_rag


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

    for _, row in services_df.iterrows():
        code = _clean(row.get("Service Code"))
        name = _clean(row.get("Service Name"))
        if not code or not name:
            continue
        service = Service.query.filter_by(code=str(code)).first()
        if not service:
            service = Service(code=str(code), name=str(name))
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

    for excel_row, row in kpi_df.iterrows():
        row_no = excel_row + 2
        try:
            reporting_month = _parse_month(row.get("Reporting Month"))
            scope = str(_clean(row.get("Scope")) or "Service").strip().lower()
            if scope not in {"service", "group"}:
                raise ValueError("Scope must be Service or Group")

            kpi_code = str(_clean(row.get("KPI Code")) or "").upper()
            kpi = KPIDefinition.query.filter_by(code=kpi_code, active=True).first()
            if not kpi:
                raise ValueError(f"Unknown KPI Code '{kpi_code}'")

            service = None
            if scope == "service":
                service_code = str(_clean(row.get("Service Code")) or "")
                if not service_code:
                    raise ValueError("Service Code is required for service-level rows")
                service = Service.query.filter_by(code=service_code).first()
                if not service:
                    raise ValueError(f"Unknown Service Code '{service_code}'")
                if kpi.group_only:
                    raise ValueError(f"{kpi.name} is configured as group-only")

            raw_value = _clean(row.get("Value"))
            if raw_value is None:
                raise ValueError("Value is blank")

            numeric_value = None
            text_value = None
            if kpi.direction in {"higher", "lower", "manual", "target_range"}:
                try:
                    numeric_value = float(raw_value)
                except (TypeError, ValueError):
                    text_value = str(raw_value)
            else:
                text_value = str(raw_value)

            manual_rag = _clean(row.get("Manual RAG"))
            rag = calculate_rag(kpi, numeric_value, text_value, manual_rag)

            result = KPIResult.query.filter_by(
                reporting_month=reporting_month,
                scope=scope,
                service_id=service.id if service else None,
                kpi_id=kpi.id,
            ).first()
            if not result:
                result = KPIResult(
                    reporting_month=reporting_month,
                    scope=scope,
                    service_id=service.id if service else None,
                    kpi_id=kpi.id,
                )
                db.session.add(result)

            result.value_numeric = numeric_value
            result.value_text = text_value
            result.rag = rag
            result.commentary = _clean(row.get("Commentary"))
            result.source = _clean(row.get("Source"))
            imported += 1
        except Exception as exc:
            errors.append(f"Row {row_no}: {exc}")

    log.rows_imported = imported
    log.rows_rejected = len(errors)
    log.status = "Completed with errors" if errors else "Completed"
    log.message = "\n".join(errors[:100]) if errors else "Import completed successfully."
    db.session.commit()

    return {
        "rows_received": len(kpi_df),
        "rows_imported": imported,
        "rows_rejected": len(errors),
        "errors": errors,
    }
