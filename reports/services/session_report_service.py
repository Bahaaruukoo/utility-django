from django.db.models import Q, Sum

from payments.models import CashierSession, Payment
from reports.models import CashierSessionReport


def generate_session_report(session, user):

    payments = Payment.objects.filter(session=session)

    total_cash = payments.filter(method="CASH").aggregate(
        s=Sum("amount")
    )["s"] or 0

    total_bank = payments.filter(method="BANK").aggregate(
        s=Sum("amount")
    )["s"] or 0

    total_mobile = payments.filter(method="MOBILE").aggregate(
        s=Sum("amount")
    )["s"] or 0

    system_total = total_cash + total_bank + total_mobile

    physical_cash = total_cash  # or entered by cashier

    difference = physical_cash - total_cash

    return CashierSessionReport.objects.create(
        tenant=session.tenant,
        session=session,
        total_cash=total_cash,
        total_bank=total_bank,
        total_mobile=total_mobile,
        system_total=system_total,
        physical_cash=physical_cash,
        difference=difference,
        prepared_by=user,
        approved_by=user
    )

def get_closed_sessions_report(tenant, start_date, end_date, branch=None):
    
    sessions = CashierSession.objects.filter( #change to repors model
        tenant=tenant,
        closed_at__isnull=False,
        closed_at__date__gte=start_date,
        closed_at__date__lte=end_date
    ).select_related(
            "cashier",
        "branch"
    )

    if branch:
        sessions = sessions.filter(branch=branch)

    sessions = sessions.annotate(
        total_collected=Sum(
            "payments__amount_paid",
            filter=Q(payments__status="COMPLETED")
        )
    )
    totals = sessions.aggregate(
        total_cash=Sum("payments__amount_paid", filter=Q(payments__payment_method="CASH")),
        total_bank=Sum("payments__amount_paid", filter=Q(payments__payment_method="BANK")),
        total_mobile=Sum("payments__amount_paid", filter=Q(payments__payment_method="MOBILE")),
        total_card=Sum("payments__amount_paid", filter=Q(payments__payment_method="CARD")),
        grand_total=Sum("payments__amount_paid")
    )

    return sessions, totals