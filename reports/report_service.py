from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from payments.models import CashierSession, Payment
from reports.models import CashierSessionReport


@transaction.atomic
def generate_session_report(session, prepared_by, physical_cash):
    if session.status != "CLOSED":
        raise ValueError("Session must be closed before generating report.")

    # Prevent duplicate report
    if hasattr(session, "report"):
        return session.report

    payments = session.payments.filter(status="COMPLETED")

    total_cash = payments.filter(payment_method="CASH").aggregate(
        total=Sum("amount_paid")
    )["total"] or 0

    total_bank = payments.filter(payment_method="BANK").aggregate(
        total=Sum("amount_paid")
    )["total"] or 0

    total_mobile = payments.filter(payment_method="MOBILE").aggregate(
        total=Sum("amount_paid")
    )["total"] or 0

    total_card = payments.filter(payment_method="CARD").aggregate(
        total=Sum("amount_paid")
    )["total"] or 0

    system_total = total_cash + total_bank + total_mobile + total_card
    difference = physical_cash - total_cash

    report = CashierSessionReport.objects.create(
        tenant=session.tenant,
        session=session,
        total_cash=total_cash,
        total_bank=total_bank,
        total_mobile=total_mobile,
        system_total=system_total,
        physical_cash=physical_cash,
        difference=difference,
        prepared_by=prepared_by,
        approved_by=session.approved_by,
    )

    return report



# ADD THIS helper ABOVE your loop
def get_col_widths(doc, num_cols):
    return [doc.width / num_cols] * num_cols


from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (HRFlowable, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)


def export_kebele_pdf(title, reports, category_totals, grand_totals, tenant, metadata=None):
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{title}.pdf"'

    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(letter),
        leftMargin=20,
        rightMargin=20,
        topMargin=20,
        bottomMargin=20,
    )

    styles = getSampleStyleSheet()
    elements = []

    # -------------------
    # HEADER (LEFT + RIGHT)
    # -------------------
    if metadata:
        month = metadata.get("Month", "")
        year = metadata.get("Year", "")
        org_name = metadata.get("Organization", tenant.name if tenant else "Utility Company")

        header_data = [[
            f"Month: {month} : {year}",
            org_name
        ]]

        header_table = Table(
            header_data,
            colWidths=[doc.width / 2.0, doc.width / 2.0]
        )

        header_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))

        elements.append(header_table)
        elements.append(Spacer(1, 2))

    # -------------------
    # TITLE (RIGHT)
    # -------------------
    title_para = Paragraph(
        f"<para alignment='right'><b>{title}</b></para>",
        styles["Title"]
    )

    elements.append(title_para)
    #elements.append(Spacer(1, 1))

    # -------------------
    # LINE SEPARATOR
    # -------------------
    elements.append(HRFlowable(width="100%", thickness=1))
    #elements.append(Spacer(1, 4))

    # -------------------
    # COMMON TABLE STYLE
    # -------------------
    def base_style():
        return TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),

            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),

            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),

            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ])

    # -------------------
    # FULL WIDTH HELPER
    # -------------------
    def full_width(data):
        return [doc.width / len(data[0])] * len(data[0])

    # -------------------
    # PER-KEBELE TABLES
    # -------------------
    for kebele in reports:
        elements.append(Paragraph(
            f"<b>Kebele: {kebele['kebele']}</b>",
            styles["Heading3"]
        ))
        #elements.append(Spacer(1, 2))

        table_data = [[
            "Category", "Bill Count", "Min", "Max",
            "Consumption", "Water", "Rent",
            "Service", "Operation", "Penalty", "Total"
        ]]

        for c in kebele["categoryReports"]:
            table_data.append([
                c["customerCategory"],
                c["billCount"],
                c["minBillAmount"] or 0,
                c["maxBillAmount"] or 0,
                c["totalConsumption"],
                c["totalAmount"],
                c["totalMeterRent"],
                c["totalServiceCharge"],
                c["totalOperationCharge"],
                c["totalPenalty"],
                c["categoryTotal"],
            ])

        # TOTAL ROW
        table_data.append([
            "TOTAL",
            kebele["billCountKebeleTotal"],
            "", "",
            kebele["consumptionKebeleTotal"],
            kebele["consCostKebeleTotal"],
            kebele["rentKebeleTotal"],
            kebele["serviceKebeleTotal"],
            kebele["operationKebeleTotal"],
            kebele["penaltyKebeleTotal"],
            kebele["kebeleTotal"],
        ])

        table = Table(
            table_data,
            colWidths=full_width(table_data),
            repeatRows=1
        )

        style = base_style()
        style.add("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey)
        style.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")

        table.setStyle(style)

        elements.append(table)
        elements.append(Spacer(1, 2))

    # -------------------
    # CATEGORY TOTALS
    # -------------------
    elements.append(Paragraph("Category Totals", styles["Heading2"]))
    #elements.append(Spacer(1, 2))

    cat_data = [[
        "Category", "Bill Count", "Min", "Max",
        "Consumption", "Water", "Rent",
        "Service", "Operation", "Penalty", "Total"
    ]]

    for c in category_totals:
        cat_data.append([
            c["customerCategory"],
            c["billCount"],
            "", "",
            c["totalConsumption"],
            c["totalAmount"],
            c["totalMeterRent"],
            c["totalServiceCharge"],
            c["totalOperationCharge"],
            c["totalPenalty"],
            c["categoryTotal"],
        ])

    cat_table = Table(cat_data, colWidths=full_width(cat_data), repeatRows=1)
    cat_table.setStyle(base_style())

    elements.append(cat_table)
    elements.append(Spacer(1, 2))

    # -------------------
    # GRAND TOTAL
    # -------------------
    elements.append(Paragraph("Grand Total", styles["Heading2"]))
    #elements.append(Spacer(1, 2))

    grand_data = [[
        "Category", "Bill Count", "Min", "Max",
        "Consumption", "Water", "Rent",
        "Service", "Operation", "Penalty", "Total"
    ], [
        "",
        grand_totals["billCount"],
        "", "",
        grand_totals["totalConsumption"],
        grand_totals["totalAmount"],
        grand_totals["totalMeterRent"],
        grand_totals["totalServiceCharge"],
        grand_totals["totalOperationCharge"],
        grand_totals["totalPenalty"],
        grand_totals["grandTotal"],
    ]]

    grand_table = Table(grand_data, colWidths=full_width(grand_data))

    style = base_style()
    style.add("BACKGROUND", (0, 1), (-1, 1), colors.lightgrey)
    style.add("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold")

    grand_table.setStyle(style)

    elements.append(grand_table)

    doc.build(elements)
    return response

    