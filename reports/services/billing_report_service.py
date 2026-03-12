from calendar import monthrange
from datetime import date

from django.db import transaction
from django.db.models import Q, Sum

from bills.models import Bill
from reports.models import BillReport


@transaction.atomic
def generate_monthly_billing_report(tenant, year, month, user, force=False):

    start = date(year, month, 1)

    # Check existing report
    existing_report = BillReport.objects.prefetch_related(
        "bills__customer",
        "bills__meter"
    ).filter(
        tenant=tenant,
        billing_month=start
    ).first()

    if existing_report and not force:
        return existing_report

    # Date range
    last_day = monthrange(year, month)[1]
    end = date(year, month, last_day)

    bills = Bill.objects.filter(
        tenant=tenant,
        issue_date__gte=start,
        issue_date__lte=end
    ).select_related(
        "customer",
        "meter"
    )

    # Sum excluding VOIDED bills
    total = bills.aggregate(
        total=Sum("amount", filter=~Q(status="VOIDED"))
    )["total"] or 0

    # If report exists and force=True → update it
    if existing_report and force:
        report = existing_report
        report.total_billed_amount = total
        report.generated_by = user
        report.save()

        report.bills.set(bills)
        return report

    # Otherwise create new report
    report = BillReport.objects.create(
        tenant=tenant,
        billing_month=start,
        generated_by=user,
        total_billed_amount=total
    )

    report.bills.set(bills)

    return report