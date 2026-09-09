from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.formatting.rule import ColorScaleRule, FormulaRule
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.models import KPIResult, KPIDefinition
from app.services.analytics import executive_trend, local_authority_rows_for_month, service_rows_for_month


# Brand / report palette
NAVY = "173042"
BLUE = "1F5B83"
MID_BLUE = "2D709E"
PALE_BLUE = "EAF2F8"
VERY_PALE_BLUE = "F5F9FC"
GREEN = "E2F0D9"
GREEN_DARK = "23734A"
AMBER = "FFF2CC"
AMBER_DARK = "936100"
RED = "F4CCCC"
RED_DARK = "A62F2F"
GREY = "E7E6E6"
LIGHT_GREY = "F3F5F7"
MID_GREY = "D9E0E5"
DARK_GREY = "66737C"
WHITE = "FFFFFF"
BLACK = "1F2933"

THIN_GREY = Side(style="thin", color="D9E1E6")
MEDIUM_BLUE = Side(style="medium", color=BLUE)

LOGO_PATH = Path(__file__).resolve().parents[1] / "static" / "blue_ribbon_logo.png"


def _solid(color):
    return PatternFill("solid", fgColor=color)


def _add_logo(ws, anchor="A1", width=44, height=44):
    if not LOGO_PATH.exists():
        return
    try:
        img = XLImage(str(LOGO_PATH))
        img.width = width
        img.height = height
        ws.add_image(img, anchor)
    except Exception:
        # Export should never fail just because a logo cannot be rendered.
        pass


def _title(ws, title, subtitle=None, end_col=8):
    """Professional two-row report banner with Blue Ribbon branding."""
    end_col = max(end_col, 8)
    end_letter = get_column_letter(end_col)
    ws.sheet_view.showGridLines = False

    # Background band.
    for row in (1, 2):
        for col in range(1, end_col + 1):
            ws.cell(row=row, column=col).fill = _solid(NAVY)

    ws.merge_cells(start_row=1, start_column=2, end_row=1, end_column=end_col)
    ws.merge_cells(start_row=2, start_column=2, end_row=2, end_column=end_col)
    ws["B1"] = title
    ws["B1"].font = Font(name="Segoe UI", size=18, bold=True, color=WHITE)
    ws["B1"].alignment = Alignment(vertical="center")
    ws["B2"] = subtitle or "Blue Ribbon Health & Wellbeing"
    ws["B2"].font = Font(name="Segoe UI", size=9, color="C9D9E4")
    ws["B2"].alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 29
    ws.row_dimensions[2].height = 22

    _add_logo(ws, "A1", 42, 42)

    # Accent divider.
    for col in range(1, end_col + 1):
        ws.cell(row=3, column=col).fill = _solid(MID_BLUE)
    ws.row_dimensions[3].height = 4


def _section(ws, row, title, start_col=1, end_col=8):
    for col in range(start_col, end_col + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = _solid(PALE_BLUE)
        cell.border = Border(bottom=MEDIUM_BLUE)
    cell = ws.cell(row=row, column=start_col)
    cell.value = title
    cell.font = Font(name="Segoe UI", size=11, bold=True, color=NAVY)
    cell.alignment = Alignment(vertical="center")
    ws.row_dimensions[row].height = 22


def _header(row_cells):
    for cell in row_cells:
        cell.font = Font(name="Segoe UI", size=9, bold=True, color=WHITE)
        cell.fill = _solid(BLUE)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = Border(bottom=Side(style="thin", color="FFFFFF"))


def _rag_fill(cell):
    value = str(cell.value or "").strip().lower()
    if value == "green":
        cell.fill = _solid(GREEN)
        cell.font = Font(name="Segoe UI", bold=True, color=GREEN_DARK)
    elif value == "amber":
        cell.fill = _solid(AMBER)
        cell.font = Font(name="Segoe UI", bold=True, color=AMBER_DARK)
    elif value == "red":
        cell.fill = _solid(RED)
        cell.font = Font(name="Segoe UI", bold=True, color=RED_DARK)
    else:
        cell.fill = _solid(GREY)
        cell.font = Font(name="Segoe UI", bold=True, color=DARK_GREY)


def _add_rag_conditional_formatting(ws, cell_range):
    first_cell = cell_range.split(":")[0]
    for text, fill, font_color in (
        ("Green", GREEN, GREEN_DARK),
        ("Amber", AMBER, AMBER_DARK),
        ("Red", RED, RED_DARK),
        ("Unscored", GREY, DARK_GREY),
    ):
        ws.conditional_formatting.add(
            cell_range,
            FormulaRule(
                formula=[f'{first_cell}="{text}"'],
                fill=_solid(fill),
                font=Font(color=font_color, bold=True),
            ),
        )


def _zebra(ws, start_row, end_row, start_col=1, end_col=None):
    if end_row < start_row:
        return
    end_col = end_col or ws.max_column
    for row in range(start_row, end_row + 1):
        if (row - start_row) % 2:
            for col in range(start_col, end_col + 1):
                cell = ws.cell(row=row, column=col)
                # Don't overwrite RAG colour cells.
                if cell.fill.fill_type is None:
                    cell.fill = _solid(VERY_PALE_BLUE)


def _autosize(ws, max_width=35, min_width=10):
    for idx in range(1, ws.max_column + 1):
        letter = get_column_letter(idx)
        width = 0
        for cell in ws[letter]:
            if cell.value is not None:
                width = max(width, len(str(cell.value)))
        ws.column_dimensions[letter].width = min(max(width + 2, min_width), max_width)


def _rag_formula(score_ref):
    return f'=IF({score_ref}="","Unscored",IF({score_ref}>=2.5,"Green",IF({score_ref}>=1.75,"Amber","Red")))'


def _result_display(result):
    if result is None:
        return ""
    if result.value_numeric is not None:
        return result.value_numeric
    return result.value_text or ""


def _style_card(ws, label_cell, value_cell, fill=WHITE, accent=BLUE, value_format=None):
    label_cell.font = Font(name="Segoe UI", size=9, bold=True, color=DARK_GREY)
    label_cell.fill = _solid(fill)
    label_cell.alignment = Alignment(horizontal="center", vertical="center")
    label_cell.border = Border(top=MEDIUM_BLUE, left=THIN_GREY, right=THIN_GREY)

    value_cell.fill = _solid(fill)
    value_cell.font = Font(name="Segoe UI", size=22, bold=True, color=accent)
    value_cell.alignment = Alignment(horizontal="center", vertical="center")
    value_cell.border = Border(left=THIN_GREY, right=THIN_GREY, bottom=THIN_GREY)
    if value_format:
        value_cell.number_format = value_format


def _link_to_sheet(cell, sheet_title, display=None):
    cell.hyperlink = f"#'{sheet_title}'!A1"
    if display is not None:
        cell.value = display
    cell.style = "Hyperlink"
    cell.font = Font(name="Segoe UI", size=9, color=BLUE, underline="single")


def _finish_sheet(ws, landscape=True, fit_to_width=1, print_title_rows=None):
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.fitToWidth = fit_to_width
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = 0.25
    ws.page_margins.right = 0.25
    ws.page_margins.top = 0.5
    ws.page_margins.bottom = 0.5
    ws.oddFooter.left.text = "Blue Ribbon Balanced Scorecard"
    ws.oddFooter.left.size = 8
    ws.oddFooter.left.color = DARK_GREY
    ws.oddFooter.center.text = "CONFIDENTIAL"
    ws.oddFooter.center.size = 8
    ws.oddFooter.center.color = DARK_GREY
    ws.oddFooter.right.text = "Page &P of &N"
    ws.oddFooter.right.size = 8
    ws.oddFooter.right.color = DARK_GREY
    if print_title_rows:
        ws.print_title_rows = print_title_rows


def build_board_pack(reporting_month):
    wb = Workbook()
    wb.properties.title = f"Blue Ribbon Balanced Scorecard - {reporting_month:%B %Y}"
    wb.properties.subject = "Monthly Board Performance Dashboard"
    wb.properties.creator = "Blue Ribbon Health & Wellbeing"

    ws = wb.active
    ws.title = "Executive Summary"
    ws.sheet_properties.tabColor = NAVY

    service_rows = service_rows_for_month(reporting_month)
    local_authority_rows = local_authority_rows_for_month(reporting_month)
    kpis = (
        KPIDefinition.query.filter_by(active=True, group_only=False)
        .order_by(KPIDefinition.domain, KPIDefinition.name)
        .all()
    )
    group_results = (
        KPIResult.query.filter_by(reporting_month=reporting_month, scope="group")
        .join(KPIDefinition)
        .order_by(KPIDefinition.domain, KPIDefinition.name)
        .all()
    )

    # ---------- All Services matrix ----------
    all_ws = wb.create_sheet("All Services")
    all_ws.sheet_properties.tabColor = MID_BLUE
    headers = [
        "Service", "Regional Manager", "Registered Manager", "Local Authority",
        "Overall Score", "Overall RAG",
    ] + [kpi.name for kpi in kpis] + ["Red KPIs", "Amber KPIs", "Sort Key", "Service Type"]
    _title(
        all_ws,
        "Blue Ribbon Balanced Scorecard - Service Matrix",
        reporting_month.strftime("Reporting month: %B %Y"),
        end_col=min(max(len(headers), 8), 18),
    )
    for col, value in enumerate(headers, 1):
        all_ws.cell(row=4, column=col, value=value)
    _header(all_ws[4])
    all_ws.row_dimensions[4].height = 34

    first_kpi_col = 7
    last_kpi_col = first_kpi_col + len(kpis) - 1
    all_ws.cell(row=5, column=1, value="KPI weights")
    for offset, kpi in enumerate(kpis):
        all_ws.cell(row=5, column=first_kpi_col + offset, value=kpi.weight or 1.0)
    all_ws.row_dimensions[5].hidden = True
    all_ws.freeze_panes = "G6"

    service_sheet_titles = {}
    used_titles = set(wb.sheetnames)
    for row in service_rows:
        raw_title = row["service"].name[:31]
        title = raw_title
        suffix = 2
        while title in used_titles:
            suffix_text = f" {suffix}"
            title = raw_title[:31 - len(suffix_text)] + suffix_text
            suffix += 1
        used_titles.add(title)
        service_sheet_titles[row["service"].id] = title

    for row_idx, row in enumerate(service_rows, 6):
        service = row["service"]
        all_ws.cell(row=row_idx, column=1, value=service.name)
        all_ws.cell(row=row_idx, column=2, value=service.regional_manager or "Unassigned")
        all_ws.cell(row=row_idx, column=3, value=service.registered_manager or "Unassigned")
        all_ws.cell(row=row_idx, column=4, value=service.local_authority or "Unassigned")
        _link_to_sheet(all_ws.cell(row=row_idx, column=1), service_sheet_titles[service.id], service.name)

        result_by_kpi = {r.kpi_id: r for r in row["results"]}
        for offset, kpi in enumerate(kpis):
            result = result_by_kpi.get(kpi.id)
            cell = all_ws.cell(
                row=row_idx,
                column=first_kpi_col + offset,
                value=result.rag if result else "Unscored",
            )
            _rag_fill(cell)
            cell.alignment = Alignment(horizontal="center", vertical="center")

        row_values, row_weights = [], []
        for col_idx in range(first_kpi_col, last_kpi_col + 1):
            letter = get_column_letter(col_idx)
            row_values.append(
                f'IF({letter}{row_idx}="Green",3,IF({letter}{row_idx}="Amber",2,IF({letter}{row_idx}="Red",1,0)))*{letter}$5'
            )
            row_weights.append(
                f'IF(OR({letter}{row_idx}="Green",{letter}{row_idx}="Amber",{letter}{row_idx}="Red"),{letter}$5,0)'
            )
        score_formula = f'=IFERROR(({"+".join(row_values)})/({"+".join(row_weights)}),"")'
        rng = f"{get_column_letter(first_kpi_col)}{row_idx}:{get_column_letter(last_kpi_col)}{row_idx}"
        all_ws.cell(row=row_idx, column=5, value=score_formula)
        all_ws.cell(row=row_idx, column=5).number_format = "0.00"
        all_ws.cell(row=row_idx, column=6, value=_rag_formula(f"E{row_idx}"))
        all_ws.cell(row=row_idx, column=last_kpi_col + 1, value=f'=COUNTIF({rng},"Red")')
        all_ws.cell(row=row_idx, column=last_kpi_col + 2, value=f'=COUNTIF({rng},"Amber")')
        all_ws.cell(row=row_idx, column=last_kpi_col + 3, value=f'=IF(E{row_idx}="","",E{row_idx}+ROW()/1000000)')
        all_ws.cell(row=row_idx, column=last_kpi_col + 4, value=service.service_type or "Not set")
        _rag_fill(all_ws.cell(row=row_idx, column=6))
        for col in range(1, len(headers) + 1):
            all_ws.cell(row=row_idx, column=col).border = Border(bottom=THIN_GREY)
            all_ws.cell(row=row_idx, column=col).alignment = Alignment(vertical="center", wrap_text=False)
        all_ws.row_dimensions[row_idx].height = 21

    sort_key_col = 7 + len(kpis) + 2
    all_ws.column_dimensions[get_column_letter(sort_key_col)].hidden = True
    last_service_row = 5 + len(service_rows)
    if service_rows:
        _add_rag_conditional_formatting(all_ws, f"F6:F{last_service_row}")
        all_ws.conditional_formatting.add(
            f"E6:E{last_service_row}",
            ColorScaleRule(
                start_type="num", start_value=1, start_color="F8696B",
                mid_type="num", mid_value=2, mid_color="FFEB84",
                end_type="num", end_value=3, end_color="63BE7B",
            ),
        )
    _autosize(all_ws, 28)
    all_ws.column_dimensions["A"].width = max(all_ws.column_dimensions["A"].width or 0, 24)
    all_ws.column_dimensions["B"].width = max(all_ws.column_dimensions["B"].width or 0, 22)
    all_ws.column_dimensions["C"].width = max(all_ws.column_dimensions["C"].width or 0, 22)
    all_ws.column_dimensions["D"].width = max(all_ws.column_dimensions["D"].width or 0, 22)
    _finish_sheet(all_ws, landscape=True, fit_to_width=1, print_title_rows="1:4")

    # ---------- Executive Summary ----------
    _title(
        ws,
        "Blue Ribbon Balanced Scorecard - Board Dashboard",
        reporting_month.strftime("Reporting month: %B %Y"),
        end_col=10,
    )
    _section(ws, 4, "HEADLINE PERFORMANCE", 1, 10)

    # Four dashboard tiles.
    card_ranges = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)]
    labels = ["Overall Service Score", "Overall RAG", "Red Services", "Amber Services", "Services Reported"]
    formulas = [
        '=IFERROR(AVERAGE(\'All Services\'!$E$6:$E$500),"")',
        _rag_formula("A6"),
        '=COUNTIF(\'All Services\'!$F$6:$F$500,"Red")',
        '=COUNTIF(\'All Services\'!$F$6:$F$500,"Amber")',
        '=COUNT(\'All Services\'!$E$6:$E$500)',
    ]
    accents = [BLUE, BLUE, RED_DARK, AMBER_DARK, NAVY]
    for i, ((c1, c2), label, formula, accent) in enumerate(zip(card_ranges, labels, formulas, accents)):
        ws.merge_cells(start_row=5, start_column=c1, end_row=5, end_column=c2)
        ws.merge_cells(start_row=6, start_column=c1, end_row=7, end_column=c2)
        label_cell = ws.cell(row=5, column=c1, value=label)
        value_cell = ws.cell(row=6, column=c1, value=formula)
        _style_card(ws, label_cell, value_cell, fill=WHITE, accent=accent, value_format="0.00" if i == 0 else None)
        ws.row_dimensions[5].height = 19
        ws.row_dimensions[6].height = 26
        ws.row_dimensions[7].height = 18
    _add_rag_conditional_formatting(ws, "C6:C6")

    _section(ws, 9, "SERVICE EXCEPTIONS & PERFORMANCE", 1, 10)
    ws["A10"] = "Bottom 5 services"
    ws["F10"] = "Top 5 services"
    for c in (ws["A10"], ws["F10"]):
        c.font = Font(name="Segoe UI", size=11, bold=True, color=NAVY)
    for start_col in (1, 6):
        ws.cell(row=11, column=start_col, value="Service")
        ws.cell(row=11, column=start_col + 1, value="Score")
        ws.cell(row=11, column=start_col + 2, value="RAG")
        ws.cell(row=11, column=start_col + 3, value="Red KPIs")
        _header(ws[11][start_col - 1:start_col + 3])

    key_letter = get_column_letter(sort_key_col)
    for i in range(5):
        r = 12 + i
        rank = i + 1
        ws.cell(row=r, column=1, value=f'=IFERROR(INDEX(\'All Services\'!$A$6:$A$500,MATCH(SMALL(\'All Services\'!${key_letter}$6:${key_letter}$500,{rank}),\'All Services\'!${key_letter}$6:${key_letter}$500,0)),"")')
        ws.cell(row=r, column=2, value=f'=IF(A{r}="","",INDEX(\'All Services\'!$E$6:$E$500,MATCH(A{r},\'All Services\'!$A$6:$A$500,0)))')
        ws.cell(row=r, column=3, value=f'=IF(A{r}="","",INDEX(\'All Services\'!$F$6:$F$500,MATCH(A{r},\'All Services\'!$A$6:$A$500,0)))')
        ws.cell(row=r, column=4, value=f'=IF(A{r}="","",INDEX(\'All Services\'!${get_column_letter(last_kpi_col + 1)}$6:${get_column_letter(last_kpi_col + 1)}$500,MATCH(A{r},\'All Services\'!$A$6:$A$500,0)))')

        ws.cell(row=r, column=6, value=f'=IFERROR(INDEX(\'All Services\'!$A$6:$A$500,MATCH(LARGE(\'All Services\'!${key_letter}$6:${key_letter}$500,{rank}),\'All Services\'!${key_letter}$6:${key_letter}$500,0)),"")')
        ws.cell(row=r, column=7, value=f'=IF(F{r}="","",INDEX(\'All Services\'!$E$6:$E$500,MATCH(F{r},\'All Services\'!$A$6:$A$500,0)))')
        ws.cell(row=r, column=8, value=f'=IF(F{r}="","",INDEX(\'All Services\'!$F$6:$F$500,MATCH(F{r},\'All Services\'!$A$6:$A$500,0)))')
        ws.cell(row=r, column=9, value=f'=IF(F{r}="","",INDEX(\'All Services\'!${get_column_letter(last_kpi_col + 1)}$6:${get_column_letter(last_kpi_col + 1)}$500,MATCH(F{r},\'All Services\'!$A$6:$A$500,0)))')
        ws.cell(row=r, column=2).number_format = "0.00"
        ws.cell(row=r, column=7).number_format = "0.00"
    _add_rag_conditional_formatting(ws, "C12:C16")
    _add_rag_conditional_formatting(ws, "H12:H16")
    _zebra(ws, 12, 16, 1, 4)
    _zebra(ws, 12, 16, 6, 9)

    # 12 month trend + RAG distribution.
    _section(ws, 18, "TREND & DISTRIBUTION", 1, 10)
    trend = executive_trend(12)
    ws["A19"] = "12-month overall score"
    ws["A19"].font = Font(name="Segoe UI", size=10, bold=True, color=NAVY)
    ws["A20"] = "Month"
    ws["B20"] = "Score"
    _header(ws[20][0:2])
    for idx, point in enumerate(trend, 21):
        ws.cell(row=idx, column=1, value=point["month"])
        ws.cell(row=idx, column=1).number_format = "mmm-yy"
        ws.cell(row=idx, column=2, value=point["score"])
        ws.cell(row=idx, column=2).number_format = "0.00"
    if trend:
        chart = LineChart()
        chart.title = "Overall service score"
        chart.style = 13
        chart.y_axis.title = "Score"
        chart.y_axis.scaling.min = 1
        chart.y_axis.scaling.max = 3
        chart.height = 7.2
        chart.width = 14.2
        data = Reference(ws, min_col=2, min_row=20, max_row=20 + len(trend))
        cats = Reference(ws, min_col=1, min_row=21, max_row=20 + len(trend))
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        chart.legend = None
        ws.add_chart(chart, "D19")

    rag_start = max(34, 21 + len(trend) + 1)
    ws.cell(row=rag_start, column=1, value="Service RAG distribution")
    ws.cell(row=rag_start, column=1).font = Font(name="Segoe UI", size=10, bold=True, color=NAVY)
    ws.cell(row=rag_start + 1, column=1, value="RAG")
    ws.cell(row=rag_start + 1, column=2, value="Count")
    _header(ws[rag_start + 1][0:2])
    for offset, rag in enumerate(["Green", "Amber", "Red", "Unscored"], 2):
        rr = rag_start + offset
        ws.cell(row=rr, column=1, value=rag)
        ws.cell(row=rr, column=2, value=f'=COUNTIF(\'All Services\'!$F$6:$F$500,A{rr})')
        _rag_fill(ws.cell(row=rr, column=1))

    pie = PieChart()
    pie.title = "Services by RAG"
    pie.height = 7.2
    pie.width = 10.5
    pie.add_data(Reference(ws, min_col=2, min_row=rag_start + 1, max_row=rag_start + 5), titles_from_data=True)
    pie.set_categories(Reference(ws, min_col=1, min_row=rag_start + 2, max_row=rag_start + 5))
    pie.dataLabels = DataLabelList()
    pie.dataLabels.showPercent = True
    pie.dataLabels.showLeaderLines = True
    ws.add_chart(pie, f"D{rag_start}")

    # Navigation note.
    ws["J12"] = "Drill-down"
    ws["J12"].font = Font(name="Segoe UI", bold=True, color=NAVY)
    ws["J13"] = "Use the tabs below for manager, local authority, group KPI and service detail views."
    ws["J13"].alignment = Alignment(wrap_text=True, vertical="top")
    ws["J13"].font = Font(name="Segoe UI", size=8, color=DARK_GREY)

    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 12
    ws.column_dimensions["E"].width = 3
    ws.column_dimensions["F"].width = 22
    ws.column_dimensions["G"].width = 12
    ws.column_dimensions["H"].width = 14
    ws.column_dimensions["I"].width = 12
    ws.column_dimensions["J"].width = 24
    ws.freeze_panes = "A4"
    _finish_sheet(ws, landscape=True, fit_to_width=1)

    # ---------- Local Authority Summary ----------
    la_ws = wb.create_sheet("Local Authority Summary")
    la_ws.sheet_properties.tabColor = "5B9BD5"
    _title(la_ws, "Blue Ribbon Balanced Scorecard - Local Authority Summary", reporting_month.strftime("Reporting month: %B %Y"), end_col=8)
    la_headers = ["Local Authority", "Services", "Average Score", "Overall RAG", "Red Services", "Amber Services"]
    for col, value in enumerate(la_headers, 1):
        la_ws.cell(row=4, column=col, value=value)
    _header(la_ws[4])
    local_authority_names = [r["local_authority"] for r in local_authority_rows]
    for idx, local_authority in enumerate(local_authority_names, 5):
        la_ws.cell(row=idx, column=1, value=local_authority)
        la_ws.cell(row=idx, column=2, value=f"=COUNTIF('All Services'!$D:$D,A{idx})")
        la_ws.cell(row=idx, column=3, value=f'=IFERROR(AVERAGEIF(\'All Services\'!$D:$D,A{idx},\'All Services\'!$E:$E),"")')
        la_ws.cell(row=idx, column=3).number_format = "0.00"
        la_ws.cell(row=idx, column=4, value=_rag_formula(f"C{idx}"))
        la_ws.cell(row=idx, column=5, value=f'=COUNTIFS(\'All Services\'!$D:$D,A{idx},\'All Services\'!$F:$F,"Red")')
        la_ws.cell(row=idx, column=6, value=f'=COUNTIFS(\'All Services\'!$D:$D,A{idx},\'All Services\'!$F:$F,"Amber")')
    if local_authority_names:
        _add_rag_conditional_formatting(la_ws, f"D5:D{4 + len(local_authority_names)}")
        _zebra(la_ws, 5, 4 + len(local_authority_names), 1, 6)
        la_ws.conditional_formatting.add(
            f"C5:C{4 + len(local_authority_names)}",
            ColorScaleRule(start_type="num", start_value=1, start_color="F8696B", mid_type="num", mid_value=2, mid_color="FFEB84", end_type="num", end_value=3, end_color="63BE7B"),
        )
    _autosize(la_ws, 32)
    la_ws.freeze_panes = "A5"
    la_ws.auto_filter.ref = f"A4:F{max(4, 4 + len(local_authority_names))}"
    _finish_sheet(la_ws, landscape=True, fit_to_width=1, print_title_rows="1:4")

    # ---------- Regional Manager Summary ----------
    rm_ws = wb.create_sheet("Regional Manager Summary")
    rm_ws.sheet_properties.tabColor = "70AD47"
    _title(rm_ws, "Blue Ribbon Balanced Scorecard - Regional Manager Summary", reporting_month.strftime("Reporting month: %B %Y"), end_col=8)
    rm_headers = ["Regional Manager", "Services", "Average Score", "Overall RAG", "Red Services", "Amber Services"]
    for col, value in enumerate(rm_headers, 1):
        rm_ws.cell(row=4, column=col, value=value)
    _header(rm_ws[4])
    manager_names = sorted({row["service"].regional_manager or "Unassigned" for row in service_rows})
    for idx, manager in enumerate(manager_names, 5):
        rm_ws.cell(row=idx, column=1, value=manager)
        rm_ws.cell(row=idx, column=2, value=f'=COUNTIF(\'All Services\'!$B:$B,A{idx})')
        rm_ws.cell(row=idx, column=3, value=f'=IFERROR(AVERAGEIF(\'All Services\'!$B:$B,A{idx},\'All Services\'!$E:$E),"")')
        rm_ws.cell(row=idx, column=3).number_format = "0.00"
        rm_ws.cell(row=idx, column=4, value=_rag_formula(f"C{idx}"))
        rm_ws.cell(row=idx, column=5, value=f'=COUNTIFS(\'All Services\'!$B:$B,A{idx},\'All Services\'!$F:$F,"Red")')
        rm_ws.cell(row=idx, column=6, value=f'=COUNTIFS(\'All Services\'!$B:$B,A{idx},\'All Services\'!$F:$F,"Amber")')
    if manager_names:
        _add_rag_conditional_formatting(rm_ws, f"D5:D{4 + len(manager_names)}")
        _zebra(rm_ws, 5, 4 + len(manager_names), 1, 6)
        rm_ws.conditional_formatting.add(
            f"C5:C{4 + len(manager_names)}",
            ColorScaleRule(start_type="num", start_value=1, start_color="F8696B", mid_type="num", mid_value=2, mid_color="FFEB84", end_type="num", end_value=3, end_color="63BE7B"),
        )
    _autosize(rm_ws, 30)
    rm_ws.freeze_panes = "A5"
    rm_ws.auto_filter.ref = f"A4:F{max(4, 4 + len(manager_names))}"
    _finish_sheet(rm_ws, landscape=True, fit_to_width=1, print_title_rows="1:4")

    # ---------- Registered Manager Summary ----------
    rgm_ws = wb.create_sheet("Registered Manager Summary")
    rgm_ws.sheet_properties.tabColor = "A5A5A5"
    _title(rgm_ws, "Blue Ribbon Balanced Scorecard - Registered Manager Summary", reporting_month.strftime("Reporting month: %B %Y"), end_col=8)
    rgm_headers = ["Regional Manager", "Registered Manager", "Services", "Average Score", "Overall RAG", "Red Services", "Amber Services"]
    for col, value in enumerate(rgm_headers, 1):
        rgm_ws.cell(row=4, column=col, value=value)
    _header(rgm_ws[4])
    manager_pairs = sorted({
        (row["service"].regional_manager or "Unassigned", row["service"].registered_manager or "Unassigned")
        for row in service_rows
    })
    for idx, (regional_manager, registered_manager) in enumerate(manager_pairs, 5):
        rgm_ws.cell(row=idx, column=1, value=regional_manager)
        rgm_ws.cell(row=idx, column=2, value=registered_manager)
        rgm_ws.cell(row=idx, column=3, value=f"=COUNTIFS('All Services'!$B:$B,A{idx},'All Services'!$C:$C,B{idx})")
        rgm_ws.cell(row=idx, column=4, value=f'=IFERROR(AVERAGEIFS(\'All Services\'!$E:$E,\'All Services\'!$B:$B,A{idx},\'All Services\'!$C:$C,B{idx}),"")')
        rgm_ws.cell(row=idx, column=4).number_format = "0.00"
        rgm_ws.cell(row=idx, column=5, value=_rag_formula(f"D{idx}"))
        rgm_ws.cell(row=idx, column=6, value=f'=COUNTIFS(\'All Services\'!$B:$B,A{idx},\'All Services\'!$C:$C,B{idx},\'All Services\'!$F:$F,"Red")')
        rgm_ws.cell(row=idx, column=7, value=f'=COUNTIFS(\'All Services\'!$B:$B,A{idx},\'All Services\'!$C:$C,B{idx},\'All Services\'!$F:$F,"Amber")')
    if manager_pairs:
        _add_rag_conditional_formatting(rgm_ws, f"E5:E{4 + len(manager_pairs)}")
        _zebra(rgm_ws, 5, 4 + len(manager_pairs), 1, 7)
        rgm_ws.conditional_formatting.add(
            f"D5:D{4 + len(manager_pairs)}",
            ColorScaleRule(start_type="num", start_value=1, start_color="F8696B", mid_type="num", mid_value=2, mid_color="FFEB84", end_type="num", end_value=3, end_color="63BE7B"),
        )
    _autosize(rgm_ws, 30)
    rgm_ws.freeze_panes = "A5"
    rgm_ws.auto_filter.ref = f"A4:G{max(4, 4 + len(manager_pairs))}"
    _finish_sheet(rgm_ws, landscape=True, fit_to_width=1, print_title_rows="1:4")

    # ---------- Group KPIs ----------
    grp_ws = wb.create_sheet("Group KPIs")
    grp_ws.sheet_properties.tabColor = "FFC000"
    _title(grp_ws, "Blue Ribbon Balanced Scorecard - Group Measures", reporting_month.strftime("Reporting month: %B %Y"), end_col=8)
    grp_headers = ["Domain", "KPI", "Value", "RAG", "Commentary", "Source"]
    for col, value in enumerate(grp_headers, 1):
        grp_ws.cell(row=4, column=col, value=value)
    _header(grp_ws[4])
    for idx, result in enumerate(group_results, 5):
        grp_ws.cell(row=idx, column=1, value=result.kpi.domain)
        grp_ws.cell(row=idx, column=2, value=result.kpi.name)
        grp_ws.cell(row=idx, column=3, value=_result_display(result))
        if result.value_numeric is not None:
            if result.kpi.unit == "%":
                grp_ws.cell(row=idx, column=3).number_format = '0.0"%";-0.0"%";0"%"'
            else:
                grp_ws.cell(row=idx, column=3).number_format = '0.0;-0.0;0'
        grp_ws.cell(row=idx, column=4, value=result.rag)
        _rag_fill(grp_ws.cell(row=idx, column=4))
        grp_ws.cell(row=idx, column=5, value=result.commentary or "")
        grp_ws.cell(row=idx, column=6, value=result.source or "")
        grp_ws.cell(row=idx, column=5).alignment = Alignment(wrap_text=True, vertical="top")
        for col in range(1, 7):
            grp_ws.cell(row=idx, column=col).border = Border(bottom=THIN_GREY)
    if group_results:
        _zebra(grp_ws, 5, 4 + len(group_results), 1, 6)
    _autosize(grp_ws, 45)
    grp_ws.column_dimensions["E"].width = 48
    grp_ws.freeze_panes = "A5"
    grp_ws.auto_filter.ref = f"A4:F{max(4, 4 + len(group_results))}"
    _finish_sheet(grp_ws, landscape=True, fit_to_width=1, print_title_rows="1:4")

    # ---------- Service detail sheets ----------
    for row in service_rows:
        service = row["service"]
        title = service_sheet_titles[service.id]
        svc_ws = wb.create_sheet(title)
        svc_ws.sheet_properties.tabColor = "D9EAD3"
        _title(svc_ws, f"Service Scorecard - {service.name}", reporting_month.strftime("Reporting month: %B %Y"), end_col=10)

        # Back link.
        svc_ws["J2"] = "Back to Executive Summary"
        _link_to_sheet(svc_ws["J2"], "Executive Summary", "Back to Executive Summary")
        svc_ws["J2"].alignment = Alignment(horizontal="right")

        # Service profile strip.
        profile = [
            ("Regional Manager", service.regional_manager or "Not set"),
            ("Registered Manager", service.registered_manager or "Not set"),
            ("Local Authority", service.local_authority or "Unassigned"),
            ("Service Type", service.service_type or "Not set"),
        ]
        col_pairs = [(1, 2), (3, 4), (5, 6), (7, 8)]
        for (label, value), (c1, c2) in zip(profile, col_pairs):
            svc_ws.cell(row=4, column=c1, value=label)
            svc_ws.cell(row=4, column=c1).font = Font(name="Segoe UI", size=8, bold=True, color=DARK_GREY)
            svc_ws.cell(row=4, column=c2, value=value)
            svc_ws.cell(row=4, column=c2).font = Font(name="Segoe UI", size=9, bold=True, color=NAVY)
            svc_ws.cell(row=4, column=c1).fill = _solid(PALE_BLUE)
            svc_ws.cell(row=4, column=c2).fill = _solid(PALE_BLUE)

        _section(svc_ws, 6, "KPI PERFORMANCE", 1, 8)
        service_headers = ["Domain", "KPI", "Value", "RAG", "Commentary", "Source"]
        for col, value in enumerate(service_headers, 1):
            svc_ws.cell(row=7, column=col, value=value)
        _header(svc_ws[7][0:6])

        ordered = sorted(row["results"], key=lambda r: (r.kpi.domain, r.kpi.name))
        for idx, result in enumerate(ordered, 8):
            svc_ws.cell(row=idx, column=1, value=result.kpi.domain)
            svc_ws.cell(row=idx, column=2, value=result.kpi.name)
            svc_ws.cell(row=idx, column=3, value=_result_display(result))
            if result.value_numeric is not None:
                if result.kpi.unit == "%":
                    svc_ws.cell(row=idx, column=3).number_format = '0.0"%";-0.0"%";0"%"'
                else:
                    svc_ws.cell(row=idx, column=3).number_format = '0.0;-0.0;0'
            svc_ws.cell(row=idx, column=4, value=result.rag)
            _rag_fill(svc_ws.cell(row=idx, column=4))
            svc_ws.cell(row=idx, column=5, value=result.commentary or "")
            svc_ws.cell(row=idx, column=6, value=result.source or "")
            svc_ws.cell(row=idx, column=5).alignment = Alignment(wrap_text=True, vertical="top")
            for col in range(1, 7):
                svc_ws.cell(row=idx, column=col).border = Border(bottom=THIN_GREY)
                svc_ws.cell(row=idx, column=col).alignment = Alignment(
                    vertical="top",
                    wrap_text=True if col in (2, 5) else False,
                )
            svc_ws.row_dimensions[idx].height = 24
        if ordered:
            _zebra(svc_ws, 8, 7 + len(ordered), 1, 6)
        _autosize(svc_ws, 50)
        svc_ws.column_dimensions["A"].width = 18
        svc_ws.column_dimensions["B"].width = 28
        svc_ws.column_dimensions["C"].width = 13
        svc_ws.column_dimensions["D"].width = 12
        svc_ws.column_dimensions["E"].width = 48
        svc_ws.column_dimensions["F"].width = 20
        svc_ws.freeze_panes = "A8"
        svc_ws.auto_filter.ref = f"A7:F{max(7, 7 + len(ordered))}"
        _finish_sheet(svc_ws, landscape=True, fit_to_width=1, print_title_rows="1:7")

    # Workbook calculation settings.
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    wb.calculation.calcMode = "auto"

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output
