from datetime import date

from django.db.models import Sum

from bills.models import MeterReading
from customers.models import Customer, Meter, MeterAssignment
from reports.models import MonthlyStatistics, YearlyStatistics


def generate_yearly_statistics(tenant, year):

    customers = Customer.objects.filter(
        tenant=tenant,
        created_at__year=year
    ).count()

    meters = Meter.objects.filter(
        tenant=tenant,
        created_at__year=year
    ).count()

    assignments = MeterAssignment.objects.filter(
        tenant=tenant,
        start_date__year=year
    ).count()

    consumption = MeterReading.objects.filter(
        tenant=tenant,
        reading_date__year=year,
        reading_status="GENERATED"
    ).aggregate(
        total=Sum("consumption")
    )["total"] or 0

    report, created = YearlyStatistics.objects.update_or_create(
        tenant=tenant,
        year=year,
        defaults={
            "total_customers": customers,
            "total_meters": meters,
            "total_assignments": assignments,
            "total_consumption": consumption,
        }
    )

    return report
def generate_monthly_statistics(tenant, year, month):

    start = date(year, month, 1)

    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)

    customers = Customer.objects.filter(
        tenant=tenant,
        created_at__gte=start,
        created_at__lt=end
    ).count()

    meters = Meter.objects.filter(
        tenant=tenant,
        created_at__gte=start,
        created_at__lt=end
    ).count()

    assignments = MeterAssignment.objects.filter(
        tenant=tenant,
        start_date__gte=start,
        start_date__lt=end
    ).count()

    consumption = MeterReading.objects.filter(
        tenant=tenant,
        reading_date__gte=start,
        reading_date__lt=end,
        reading_status="GENERATED"
    ).aggregate(
        total=Sum("consumption")
    )["total"] or 0

    report, created = MonthlyStatistics.objects.update_or_create(
        tenant=tenant,
        month=start,
        defaults={
            "total_customers": customers,
            "total_meters": meters,
            "total_assignments": assignments,
            "total_consumption": consumption,
        }
    )

    return report