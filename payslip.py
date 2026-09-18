"""
payslip.py
Generates a professional payslip PDF for an employee for a given month/year,
using a stored payroll_records snapshot.
"""

import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

from database import MONTH_NAMES

NAVY = colors.HexColor("#0b1c2c")
TEAL = colors.HexColor("#17b6a7")
LIGHT_GREY = colors.HexColor("#f1f5f9")
TEXT_GREY = colors.HexColor("#475569")


def _amount_in_words(n):
    """Basic Indian-numbering currency-in-words for whole rupees."""
    try:
        n = int(round(float(n)))
    except (TypeError, ValueError):
        return ""
    if n == 0:
        return "Zero Rupees Only"

    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
            "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
            "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def two_digit(x):
        if x < 20:
            return ones[x]
        return (tens[x // 10] + (" " + ones[x % 10] if x % 10 else "")).strip()

    def three_digit(x):
        if x >= 100:
            return ones[x // 100] + " Hundred" + (" " + two_digit(x % 100) if x % 100 else "")
        return two_digit(x)

    parts = []
    crore = n // 10000000
    n %= 10000000
    lakh = n // 100000
    n %= 100000
    thousand = n // 1000
    n %= 1000
    hundred = n

    if crore:
        parts.append(three_digit(crore) + " Crore")
    if lakh:
        parts.append(three_digit(lakh) + " Lakh")
    if thousand:
        parts.append(three_digit(thousand) + " Thousand")
    if hundred:
        parts.append(three_digit(hundred))

    return (" ".join(parts) + " Rupees Only") if parts else "Zero Rupees Only"


def generate_payslip_pdf(employee: dict, payroll: dict, company_name="TEC TANIVA", logo_path=None) -> bytes:
    """Return PDF bytes for a single month's payslip."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=14 * mm, bottomMargin=14 * mm, leftMargin=16 * mm, rightMargin=16 * mm,
        title=f"Payslip - {employee.get('employee_name', '')} - {MONTH_NAMES[payroll['month']-1]} {payroll['year']}",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CompanyTitle", fontSize=17, leading=20, textColor=NAVY, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="SubTitle", fontSize=9.5, leading=13, textColor=TEXT_GREY))
    styles.add(ParagraphStyle(name="SectionHead", fontSize=10.5, leading=14, textColor=colors.white,
                               fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="Cell", fontSize=9, leading=12, textColor=colors.HexColor("#0f172a")))
    styles.add(ParagraphStyle(name="CellRight", fontSize=9, leading=12, alignment=TA_RIGHT,
                               textColor=colors.HexColor("#0f172a")))
    styles.add(ParagraphStyle(name="CenterMuted", fontSize=8.5, leading=11, textColor=TEXT_GREY, alignment=TA_CENTER))

    story = []

    story.append(Paragraph(company_name, styles["CompanyTitle"]))
    story.append(Paragraph("Payslip / Salary Statement", styles["SubTitle"]))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", color=TEAL, thickness=1.4))
    story.append(Spacer(1, 10))

    month_label = f"{MONTH_NAMES[payroll['month'] - 1]} {payroll['year']}"
    story.append(Paragraph(f"<b>Pay Period:</b> {month_label}", styles["Cell"]))
    story.append(Spacer(1, 8))

    emp_info = [
        ["Employee Name", employee.get("employee_name", "-"), "Employee Code", employee.get("employee_code", "-")],
        ["Designation", employee.get("designation") or "-", "Employee Type", employee.get("employee_type") or "-"],
        ["Date of Joining", employee.get("date_of_joining") or "-", "Reporting Boss", employee.get("reporting_boss") or "-"],
        ["UAN Number", employee.get("uan_number") or "-", "ESIC Number", employee.get("esic_number") or "-"],
        ["Bank Name", employee.get("bank_name") or "-", "IFSC Code", employee.get("ifsc_code") or "-"],
    ]
    t = Table(emp_info, colWidths=[35 * mm, 55 * mm, 35 * mm, 45 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("BACKGROUND", (2, 0), (2, -1), LIGHT_GREY),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))

    def section_header(text):
        tbl = Table([[Paragraph(text, styles["SectionHead"])]], colWidths=[160 * mm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        return tbl

    story.append(section_header("Earnings & Deductions"))
    earn_ded = [
        [Paragraph("<b>Earnings</b>", styles["Cell"]), Paragraph("<b>Amount (₹)</b>", styles["CellRight"]),
         Paragraph("<b>Deductions</b>", styles["Cell"]), Paragraph("<b>Amount (₹)</b>", styles["CellRight"])],
        ["Basic Pay", f"{payroll.get('basic_pay', 0):,.2f}", "Employee PF", f"{payroll.get('employee_pf', 0):,.2f}"],
        ["Dearness Allowance", f"{payroll.get('da', 0):,.2f}", "Employee ESIC",
         f"{payroll.get('employee_esic', 0):,.2f}" if payroll.get('employee_esic', 0) else "0.00"],
        ["HRA", f"{payroll.get('hra', 0):,.2f}", "", ""],
        ["Phone Bill Allowance", f"{payroll.get('phonebill_pay', 0):,.2f}", "", ""],
        ["Other Allowances", f"{payroll.get('others', 0):,.2f}", "", ""],
        [Paragraph("<b>Gross Earnings</b>", styles["Cell"]),
         Paragraph(f"<b>{payroll.get('gross', 0):,.2f}</b>", styles["CellRight"]),
         Paragraph("<b>Total Deductions</b>", styles["Cell"]),
         Paragraph(f"<b>{(payroll.get('employee_pf', 0) + payroll.get('employee_esic', 0)):,.2f}</b>", styles["CellRight"])],
    ]
    t2 = Table(earn_ded, colWidths=[47 * mm, 33 * mm, 47 * mm, 33 * mm])
    t2.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GREY),
        ("BACKGROUND", (0, -1), (-1, -1), LIGHT_GREY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t2)
    story.append(Spacer(1, 14))

    # -----------------------------------------------------------------
    # Attendance Adjustments: Loss of Pay (LOP) / Extra Days Worked
    # Only rendered when this payroll snapshot actually has LOP or Extra
    # day amounts recorded against it, so older/unaffected payslips are
    # completely unchanged.
    # -----------------------------------------------------------------
    lop_days = payroll.get("lop_days", 0) or 0
    extra_days = payroll.get("extra_days", 0) or 0
    lop_amount = payroll.get("lop_amount", 0) or 0
    extra_amount = payroll.get("extra_amount", 0) or 0
    per_day_rate = payroll.get("per_day_rate", 0) or 0
    present_days = payroll.get("present_days", 0) or 0
    source = payroll.get("source", "manual")

    if lop_days or extra_days or present_days:
        story.append(section_header("Attendance Adjustments (Loss of Pay / Extra Days)"))
        att_rows = [
            ["Per-Day Rate (Gross ÷ 26)", f"₹ {per_day_rate:,.2f}"],
        ]
        if source == "attendance" and present_days:
            att_rows.append([f"Days Present (from monthly attendance)", f"{present_days:g} day(s)"])
        if lop_days:
            att_rows.append([f"Loss of Pay ({lop_days:g} day(s))", f"- ₹ {lop_amount:,.2f}"])
        if extra_days:
            att_rows.append([f"Extra Days Worked ({extra_days:g} day(s))", f"+ ₹ {extra_amount:,.2f}"])
        net_adjustment = extra_amount - lop_amount
        att_rows.append([
            Paragraph("<b>Net Attendance Adjustment</b>", styles["Cell"]),
            Paragraph(
                f"<b>{'+' if net_adjustment >= 0 else '-'} ₹ {abs(net_adjustment):,.2f}</b>",
                styles["CellRight"],
            ),
        ])
        t_att = Table(att_rows, colWidths=[110 * mm, 50 * mm])
        t_att.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("BACKGROUND", (0, -1), (-1, -1), LIGHT_GREY),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t_att)
        story.append(Spacer(1, 14))

    net_pay = payroll.get("net_pay", 0)
    story.append(section_header("Net Pay"))
    net_tbl = Table([
        [Paragraph("Net Pay for the month", styles["Cell"]),
         Paragraph(f"<b>₹ {net_pay:,.2f}</b>", ParagraphStyle(name="NetVal", fontSize=13, alignment=TA_RIGHT,
                                                               textColor=TEAL, fontName="Helvetica-Bold"))],
        [Paragraph(f"<i>In words: {_amount_in_words(net_pay)}</i>", styles["CenterMuted"]), ""],
    ], colWidths=[110 * mm, 50 * mm])
    net_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (1, 0), 0.5, colors.HexColor("#e2e8f0")),
        ("SPAN", (0, 1), (1, 1)),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(net_tbl)
    story.append(Spacer(1, 14))

    story.append(section_header("Employer Contributions (paid on top of Gross, part of CTC)"))
    contrib = [
        ["Employer PF Total (EPF+EPS+EDLI+Admin)", f"₹ {payroll.get('employer_pf_total', 0):,.2f}"],
        ["Employer ESIC (3.25%)", f"₹ {payroll.get('employer_esic', 0):,.2f}" if payroll.get('employer_esic', 0) else "Not Applicable"],
        [Paragraph("<b>Total Cost to Company (CTC) for the month</b>", styles["Cell"]),
         Paragraph(f"<b>₹ {payroll.get('ctc', 0):,.2f}</b>", styles["CellRight"])],
    ]
    t3 = Table(contrib, colWidths=[110 * mm, 50 * mm])
    t3.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0, -1), (-1, -1), LIGHT_GREY),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t3)
    story.append(Spacer(1, 20))

    story.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0"), thickness=0.8))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "This is a system-generated payslip and does not require a signature. "
        "For any discrepancy, please contact HR within 7 working days.",
        styles["CenterMuted"],
    ))

    doc.build(story)
    return buf.getvalue()