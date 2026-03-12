from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone

from bills.models import Bill
from payments.models import Payment


def get_dashboard_data(tenant):

    today = timezone.now().date()
    year_start = today.replace(month=1, day=1)

    # TOTAL BILLED
    total_billed = Bill.objects.filter(
        tenant=tenant,
        status__in=["UNSOLD", "SOLD"]
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0

    # TOTAL COLLECTED
    total_collected = Payment.objects.filter(
        tenant=tenant,
        status="COMPLETED",
        is_reversal=False
    ).aggregate(
        total=Sum("amount_paid")
    )["total"] or 0

    # OUTSTANDING
    outstanding = total_billed - total_collected

    # COLLECTION EFFICIENCY
    efficiency = 0
    if total_billed > 0:
        efficiency = (total_collected / total_billed) * 100

    # PAYMENT METHODS
    payment_methods = Payment.objects.filter(
        tenant=tenant,
        status="COMPLETED"
    ).values(
        "payment_method"
    ).annotate(
        total=Sum("amount_paid")
    )

    # MONTHLY COLLECTION
    monthly_collections = Payment.objects.filter(
        tenant=tenant,
        status="COMPLETED",
        payment_date__year=today.year
    ).extra(
        {"month": "EXTRACT(month FROM payment_date)"}
    ).values("month").annotate(
        total=Sum("amount_paid")
    ).order_by("month")

    return {
        "total_billed": total_billed,
        "total_collected": total_collected,
        "outstanding": outstanding,
        "efficiency": round(efficiency, 2),
        "payment_methods": list(payment_methods),
        "monthly_collections": list(monthly_collections)
    }