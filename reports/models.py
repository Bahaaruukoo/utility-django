from django.conf import settings
from django.db import models

from bills.models import Bill
from customers.models import Customer
from payments.models import CashierSession, Payment
from tenant_utils.models import Branch, TenantAwareModel


class BillReport(TenantAwareModel):
    billing_month = models.DateField()
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bill_reports"
    )

    bills = models.ManyToManyField(Bill, related_name="bill_reports")

    total_billed_amount = models.DecimalField(
        max_digits=15, decimal_places=2, default=0
    )

    def __str__(self):
        return f"Bill Report {self.start_date} - {self.end_date}"
        
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "billing_month"],
                name="unique_billing_month_report"
            )
        ]

class CollectionReport(TenantAwareModel):

    collection_month = models.DateField()

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    generated_at = models.DateTimeField(auto_now_add=True)

    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="collection_reports"
    )

    payments = models.ManyToManyField(
        Payment,
        related_name="collection_reports"
    )

    payment_count = models.PositiveIntegerField(default=0)

    total_collected = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )

    total_cash = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_bank = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_mobile = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_card = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    reversed_total = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "collection_month", "branch"],
                name="unique_collection_report_per_branch"
            )
        ]

    def __str__(self):

        if self.branch:
            return f"{self.branch} Collection {self.collection_month.strftime('%B %Y')}"

        return f"Tenant Collection {self.collection_month.strftime('%B %Y')}"
    
class CashierSessionReport(TenantAwareModel):
    session = models.OneToOneField(
        CashierSession,
        on_delete=models.PROTECT,
        related_name="report"
    )

    total_cash = models.DecimalField(max_digits=15, decimal_places=2)
    total_bank = models.DecimalField(max_digits=15, decimal_places=2)
    total_mobile = models.DecimalField(max_digits=15, decimal_places=2)

    system_total = models.DecimalField(max_digits=15, decimal_places=2)
    physical_cash = models.DecimalField(max_digits=15, decimal_places=2)

    difference = models.DecimalField(max_digits=15, decimal_places=2)

    prepared_at = models.DateTimeField(auto_now_add=True)
    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cashier_reports"
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="approved_cashier_reports"
    )

    def __str__(self):
        return f"Session Report - {self.session.id}"

class OutstandingBalanceReport(TenantAwareModel):
    as_of_date = models.DateField()

    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="outstanding_reports"
    )

    total_outstanding = models.DecimalField(
        max_digits=15, decimal_places=2, default=0
    )

    def __str__(self):
        return f"Outstanding Balance as of {self.as_of_date}"

class AuditTrailReport(TenantAwareModel):
    start_date = models.DateField()
    end_date = models.DateField()

    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="audit_reports"
    )

    description = models.TextField()

    def __str__(self):
        return f"Audit Report {self.start_date} - {self.end_date}"


class MonthlyStatistics(TenantAwareModel):

    month = models.DateField()

    total_customers = models.PositiveIntegerField(default=0)
    total_meters = models.PositiveIntegerField(default=0)
    total_assignments = models.PositiveIntegerField(default=0)

    total_consumption = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )

    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "month"],
                name="unique_monthly_statistics"
            )
        ]

    def __str__(self):
        return f"{self.month}"
    
class YearlyStatistics(TenantAwareModel):

    year = models.IntegerField()

    total_customers = models.PositiveIntegerField()
    total_meters = models.PositiveIntegerField()
    total_assignments = models.PositiveIntegerField()

    total_consumption = models.DecimalField(
        max_digits=15,
        decimal_places=2
    )

    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "year"],
                name="unique_yearly_statistics"
            )
        ]

