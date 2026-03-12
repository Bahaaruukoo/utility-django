from datetime import date, timedelta

from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce

from bills.models import Bill
from payments.models import Payment

# reports/services/debt_aging_service.py

def generate_debt_aging_report(tenant, as_of_date, branch=None):

    bills = Bill.objects.filter(
        tenant=tenant,
        issue_date__lte=as_of_date
    ).exclude(
        status="VOIDED"
    ).select_related(
        "customer",
        "meter",
        "branch"
    )

    if branch:
        bills = bills.filter(branch=branch)

    # annotate paid amount
    bills = bills.annotate(
        paid_amount=Coalesce(
            Sum(
                "payments__amount_paid",
                filter=Q(
                    payments__status="COMPLETED",
                    payments__is_reversal=False,
                    payments__payment_date__lte=as_of_date
                )
            ),
            Value(0),
            output_field=DecimalField()
        )
    )

    # compute outstanding
    bills = bills.annotate(
        outstanding=F("amount") - F("paid_amount")
    ).filter(
        outstanding__gt=0
    )

    aging = {
        "0_30": 0,
        "31_60": 0,
        "61_90": 0,
        "90_plus": 0
    }

    rows = []

    for bill in bills:

        age_days = (as_of_date - bill.issue_date).days
        outstanding = bill.outstanding

        if age_days <= 30:
            aging["0_30"] += outstanding
            bucket = "0-30"

        elif age_days <= 60:
            aging["31_60"] += outstanding
            bucket = "31-60"

        elif age_days <= 90:
            aging["61_90"] += outstanding
            bucket = "61-90"

        else:
            aging["90_plus"] += outstanding
            bucket = "90+"

        rows.append({
            "customer": bill.customer,
            "bill": bill,
            "outstanding": outstanding,
            "age_days": age_days,
            "bucket": bucket
        })

    total_outstanding = sum(aging.values())

    return {
        "aging": aging,
        "rows": rows,
        "total_outstanding": total_outstanding,
        "as_of_date": as_of_date
    }