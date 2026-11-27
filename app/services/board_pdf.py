"""Paginated, escaped Board PDF; creates documents in memory without temporary files."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

BR_BLUE = colors.HexColor("#0160B1")
NAVY = colors.HexColor("#173042")

def clean(value):
    return escape(str(value if value is not None else ""))

def make_pdf(report, narrative):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=17*mm, rightMargin=17*mm,
                            topMargin=19*mm, bottomMargin=19*mm, title="Blue Ribbon Board Performance Report")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="BRTitle", parent=styles["Title"], fontSize=19, leading=23, textColor=NAVY, spaceAfter=8, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name="BRSection", parent=styles["Heading2"], fontSize=12, leading=15, textColor=BR_BLUE, spaceBefore=14, spaceAfter=7))
    styles.add(ParagraphStyle(name="BRBody", parent=styles["BodyText"], fontSize=9, leading=13, spaceAfter=6))
    styles.add(ParagraphStyle(name="BRCell", parent=styles["BodyText"], fontSize=8, leading=10))
    flow = [Paragraph("Blue Ribbon | Board Performance Report", styles["BRTitle"]),
            Paragraph(clean(report["month"].strftime("%B %Y")) + " | Generated " + clean(report["generated_on"].strftime("%d %B %Y")), styles["BRBody"])]
    def para(s):
        return Paragraph(clean(s).replace("\n", "<br/>"), styles["BRBody"])
    def section(label):
        flow.append(Paragraph(label, styles["BRSection"]))
    def table(headers, rows, widths=None):
        header_style = ParagraphStyle(name="BRHeader", parent=styles["BRCell"], textColor=colors.white, fontName="Helvetica-Bold")
        content = [[Paragraph(clean(x), header_style) for x in headers]]
        content += [[Paragraph(clean(x), styles["BRCell"]) for x in row] for row in rows]
        t = Table(content, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),NAVY),
            ("TEXTCOLOR",(0,0),(-1,0),colors.white), ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#EFF5FA")]),
            ("VALIGN",(0,0),(-1,-1),"TOP"), ("LEFTPADDING",(0,0),(-1,-1),8), ("RIGHTPADDING",(0,0),(-1,-1),8),
            ("TOPPADDING",(0,0),(-1,-1),7), ("BOTTOMPADDING",(0,0),(-1,-1),7)]))
        flow.append(t)
    def fmt(x):
        return "N/A" if x is None else f"{x:.2f}"
    section("Executive overview")
    flow.append(para(f"Portfolio score: {fmt(report['score'])}/10 across {report['scored_services']} scored services. "
                     f"RAG: {report['rag_counts']['Green']} Green, {report['rag_counts']['Amber']} Amber, "
                     f"{report['rag_counts']['Red']} Red, {report['rag_counts']['Unscored']} Unscored."))
    if report["previous_month"]:
        flow.append(para(f"Comparable services: {report['movement']['comparable']}. "
                         f"Improving: {report['movement']['improving']}; declining: {report['movement']['declining']}; "
                         f"unchanged: {report['movement']['unchanged']}."))
    section("Performance movements")
    movers = [("Improved", r) for r in report["best"]] + [("Declined", r) for r in report["worst"]]
    if movers:
        table(["Movement", "Service", "Previous", "Current", "Delta"],
              [[label, r["service"].name, fmt(r["previous"]), fmt(r["current"]), f"{r['delta']:+.2f}"] for label,r in movers],
              [62, 176, 75, 75, 70])
    else:
        flow.append(para("No comparable service movements for this reporting period."))
    section("KPI RAG movements")
    changes = report["movement"]["transitions"]
    if changes:
        table(["Service", "KPI", "Previous", "Current", "Direction"],
              [[r["service"].name, r["kpi"].name, r["previous"], r["current"], r["direction"]] for r in changes[:16]],
              [110, 142, 65, 65, 76])
        if len(changes) > 16: flow.append(para(f"Showing the first 16 of {len(changes)} KPI RAG changes. See Performance Trends for all movements."))
    else:
        flow.append(para("No comparable KPI RAG movements."))
    section("Data quality and assurance")
    q = report["quality"]
    flow.append(para(f"Recorded KPI coverage: {report['coverage'] if report['coverage'] is not None else 'N/A'}%. "
                     f"Missing: {q['totals']['missing']}; blank: {q['totals']['blank']}; explicit N/A: {q['totals']['na']}. "
                     f"Advisory flags: {len(q['flags'])}."))
    if q["flags"]:
        table(["Service", "Warning", "Review"], [[f["service"], f["kind"], f["detail"]] for f in q["flags"][:18]], [115, 110, 233])
        if len(q["flags"]) > 18: flow.append(para("Additional validation flags are available in the Data Quality dashboard."))
    section("Improvement actions linked to reporting month")
    flow.append(para(f"Total: {len(report['actions'])}; outstanding: {len(report['open_actions'])}; "
                     f"overdue today: {len(report['overdue'])}. Status reflects the live tracker at report generation, not a historical snapshot."))
    if report["actions"]:
        table(["Service", "Action", "Owner", "Due", "Status"],
              [[a.service.name, a.title, a.owner, a.due_date.strftime("%d %b %Y"), a.status] for a in report["actions"][:20]],
              [90, 139, 90, 70, 69])
        if len(report["actions"]) > 20: flow.append(para("Further actions are available in the Improvement Action Tracker."))
    section("Executive commentary")
    for label, key in (("Highlights", "highlights"), ("Areas of concern", "concerns"), ("Priorities", "priorities")):
        flow.append(Paragraph(clean(label), styles["Heading3"]))
        flow.append(para(getattr(narrative, key, "") or "No commentary recorded."))
    flow.append(Spacer(1, 8))
    flow.append(para("Methodology: uses existing service scoring. Missing results are not zero scores. "
                     "Data-quality flags are advisory and have not changed recorded KPI values. "
                     "Historical service coverage can vary by reporting month."))
    def decorate(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(BR_BLUE)
        canvas.line(17*mm, 16*mm, A4[0]-17*mm, 16*mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(NAVY)
        canvas.drawString(17*mm, 11*mm, "Blue Ribbon | Board Performance")
        canvas.drawRightString(A4[0]-17*mm, 11*mm, f"Page {document.page}")
        canvas.restoreState()
    doc.build(flow, onFirstPage=decorate, onLaterPages=decorate)
    buffer.seek(0)
    return buffer
