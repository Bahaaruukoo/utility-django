from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth, TruncYear

from bills.models import MeterReading
from customers.models import Customer, Meter, MeterAssignment


class StatisticsService:

    # -----------------------------
    # CUSTOMER REPORTS
    # -----------------------------

    @staticmethod
    def customers_per_month(tenant, year=None):
        qs = Customer.objects.filter(tenant=tenant)

        if year:
            qs = qs.filter(created_at__year=year)

        return (
            qs.annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(total=Count("id"))
            .order_by("month")
        )

    @staticmethod
    def customers_per_year(tenant):
        return (
            Customer.objects.filter(tenant=tenant)
            .annotate(year=TruncYear("created_at"))
            .values("year")
            .annotate(total=Count("id"))
            .order_by("year")
        )

    # -----------------------------
    # METER REPORTS
    # -----------------------------

    @staticmethod
    def meters_per_month(tenant, year=None):
        qs = Meter.objects.filter(tenant=tenant)

        if year:
            qs = qs.filter(created_at__year=year)

        return (
            qs.annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(total=Count("id"))
            .order_by("month")
        )

    @staticmethod
    def meters_per_year(tenant):
        return (
            Meter.objects.filter(tenant=tenant)
            .annotate(year=TruncYear("created_at"))
            .values("year")
            .annotate(total=Count("id"))
            .order_by("year")
        )

    # -----------------------------
    # METER ASSIGNMENT REPORTS
    # -----------------------------

    @staticmethod
    def assignments_per_month(tenant, year=None):
        qs = MeterAssignment.objects.filter(tenant=tenant)

        if year:
            qs = qs.filter(start_date__year=year)

        return (
            qs.annotate(month=TruncMonth("start_date"))
            .values("month")
            .annotate(total=Count("id"))
            .order_by("month")
        )

    @staticmethod
    def assignments_per_year(tenant):
        return (
            MeterAssignment.objects.filter(tenant=tenant)
            .annotate(year=TruncYear("start_date"))
            .values("year")
            .annotate(total=Count("id"))
            .order_by("year")
        )

    # -----------------------------
    # CONSUMPTION REPORTS
    # -----------------------------

    @staticmethod
    def consumption_per_month(tenant, year=None):
        qs = MeterReading.objects.filter(
            tenant=tenant,
            reading_status="GENERATED"
        )

        if year:
            qs = qs.filter(reading_date__year=year)

        return (
            qs.annotate(month=TruncMonth("reading_date"))
            .values("month")
            .annotate(total_consumption=Sum("consumption"))
            .order_by("month")
        )

    @staticmethod
    def consumption_per_year(tenant):
        return (
            MeterReading.objects.filter(
                tenant=tenant,
                reading_status="GENERATED"
            )
            .annotate(year=TruncYear("reading_date"))
            .values("year")
            .annotate(total_consumption=Sum("consumption"))
            .order_by("year")
        )