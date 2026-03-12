from django.db import transaction
from django.db.models import Sum

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