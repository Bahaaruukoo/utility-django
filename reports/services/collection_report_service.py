from calendar import monthrange
from datetime import date, datetime

from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import ExtractMonth
from django.utils import timezone

from payments.models import Payment
from reports.models import CollectionReport


@transaction.atomic
def generate_monthly_collection_report(
    tenant,
    year,
    month,
    user,
    branch=None,
    force=False
):

    # Build the first day of the month in the tenant's timezone
    year = int(year)
    month = int(month)

    start = datetime(year, month, 1)
    start = timezone.make_aware(start, timezone.get_current_timezone())

    # Compute the first day of the next month
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)

    next_month = timezone.make_aware(next_month, timezone.get_current_timezone())

    existing = CollectionReport.objects.filter(
        tenant=tenant,
        collection_month=start,
        branch=branch
    ).first()

    if existing and not force:
        return existing

    # Real payment queryset (used for report relations)
    payments = Payment.objects.filter(
        tenant=tenant,
        status="COMPLETED",
        is_reversal=False,
        payment_date__gte=start,
        payment_date__lt=next_month
    )
    print(payments)
    if branch:
        payments = payments.filter(branch=branch)


    # Monthly aggregation (for dashboard charts only)
    monthly_payments = Payment.objects.filter(
        tenant=tenant,
        status="COMPLETED",
        is_reversal=False,
        payment_date__year=date.today().year
    ).annotate(
        month=ExtractMonth("payment_date")
    ).values(
        "month"
    ).annotate(
        total=Sum("amount_paid")
    )
    # convert to dict
    monthly_map = {p["month"]: float(p["total"]) for p in monthly_payments}

    monthly_collections = []

    for m in range(1,13):
        monthly_collections.append({
            "month": m,
            "total": monthly_map.get(m,0)
        })
    if branch:
        payments = payments.filter(branch=branch)

    totals = payments.aggregate(
        total=Sum("amount_paid"),
        cash=Sum("amount_paid", filter=Q(payment_method="CASH")),
        bank=Sum("amount_paid", filter=Q(payment_method="BANK")),
        mobile=Sum("amount_paid", filter=Q(payment_method="MOBILE")),
        card=Sum("amount_paid", filter=Q(payment_method="CARD")),
    )

    payment_count = payments.count()

    if existing and force:

        existing.total_collected = totals["total"] or 0
        existing.total_cash = totals["cash"] or 0
        existing.total_bank = totals["bank"] or 0
        existing.total_mobile = totals["mobile"] or 0
        existing.total_card = totals["card"] or 0
        existing.payment_count = payment_count
        existing.generated_by = user
        existing.save()

        existing.payments.set(payments)

        return existing

    report = CollectionReport.objects.create(
        tenant=tenant,
        collection_month=start,
        branch=branch,
        generated_by=user,
        total_collected=totals["total"] or 0,
        total_cash=totals["cash"] or 0,
        total_bank=totals["bank"] or 0,
        total_mobile=totals["mobile"] or 0,
        total_card=totals["card"] or 0,
        payment_count=payment_count,
    )

    report.payments.set(payments)

    return report