import secrets
import string
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.forms import ValidationError
from django.utils import timezone

from core.models import TenantAwareModel
from customers.models import Customer, Meter
from tenant_utils.models import Branch


class MeterReading(TenantAwareModel):
    reading_status_choices = [
        ('INITIAL', 'Initial'), #when first introduced to the system. Or be ready to deploy
        ('FRESH', 'Fresh'), #new reading taken but bill not generated
        ('GENERATED', 'Generated'), #bill generated for this reading
        ('FAILED', 'Failed'), #reading taken but some error occurred during bill generation
        ('VOIDED', 'Voided'), #reading voided 
        ('BILVOIDED', 'Bill Voided'), #reading voided 
        ('EDITED', 'Edited'), #reading edited. Needs regeneration of bill
    ]
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name="readings")
    reader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    reading_date = models.DateField(auto_now_add=True)
    reading_value = models.DecimalField(max_digits=10, decimal_places=2)
    reading_status = models.CharField(max_length=10, choices=reading_status_choices, default='FRESH')
    previous_reading = models.DecimalField(max_digits=12, decimal_places=2)
    consumption = models.DecimalField(max_digits=12, decimal_places=2)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)

    class Meta:
        constraints = [ models.UniqueConstraint( fields=['meter', 'reading_date'], 
                        name='unique_meter_reading_date', 
                        violation_error_message="A reading for this meter on this date already exists." ) ]
        ordering = ['-reading_date']
        
    def clean(self):
        if not self.meter:
            raise ValidationError("Meter is required.")

        last_reading = (
            MeterReading.objects
            .filter(
                #tenant=self.tenant,
                meter=self.meter
            )
            .exclude(pk=self.pk)   # important when editing
            .order_by("-reading_date")
            .first()
        )

        if last_reading:
            if self.reading_value < last_reading.reading_value:
                raise ValidationError(
                    "Reading cannot be less than previous reading."
                )
            self.previous_reading = last_reading.reading_value
        else:
            self.previous_reading = self.meter.initial_reading

        self.consumption = self.reading_value - self.previous_reading

    def __str__(self):
        return f"{self.meter.meter_no} - {self.reading_value} on {self.reading_date}"

class Bill(TenantAwareModel):
    status_choices = [
        ('UNSOLD', 'Unsold'),
        ('SOLD', 'Sold'),
        ('VOIDED', 'Voided'),
    ]
    reading = models.OneToOneField("MeterReading", on_delete=models.PROTECT, related_name="bill")
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name="bills")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="bills")
    issue_date = models.DateField(auto_now_add=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bill_period = models.DateField()
    invoice_number = models.CharField(max_length=30, unique=True, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=status_choices, default='UNSOLD')
    void_reason = models.TextField(blank=True, null=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "meter", "bill_period"],
                name="unique_bill_per_period_per_meter",
                violation_error_message="Bill for this period is already generated"
            )
        ]
        indexes = [
            models.Index(fields=["issue_date"]),
            models.Index(fields=["tenant", "issue_date"]),
        ]

    @property
    def bill_number(self):
        # Always returns meter's constant bill number
        return self.meter.bill_number

    def is_overdue(self):
        try:
            billing_settings = BillingSettings.objects.get(
                tenant=self.tenant
            )
        except BillingSettings.DoesNotExist:
            return False

        due_date = self.issue_date + timezone.timedelta(
            days=billing_settings.bill_overdue_in_days
        )
        return (
            timezone.now().date() > due_date
            and self.status == "UNSOLD"
        )

    def calculate_late_fee(self):
        try:
            settings = BillingSettings.objects.get(tenant=self.tenant)
        except BillingSettings.DoesNotExist:
            return Decimal("0.00")

        if not self.is_overdue():
            return Decimal("0.00")

        return (
            self.amount *
            (settings.late_fee_rate / Decimal("100"))
        ).quantize(Decimal("0.01"))


    def total_payable(self):
        return self.amount + self.calculate_late_fee()
        
    def save(self, *args, **kwargs):
        if not self.invoice_number:
            timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
            random_suffix = ''.join(
                secrets.choice(string.ascii_uppercase + string.digits)
                for _ in range(4)
            )
            self.invoice_number = f"{timestamp}-{random_suffix}"
        super().save(*args, **kwargs)

    def void(self, user, reason):

        if self.status != "UNSOLD":
            raise ValidationError("Only unsold bills can be voided.")

        self.status = "VOIDED"
        self.void_reason = reason
        self.voided_at = timezone.now()
        self.voided_by = user
        self.save(update_fields=[
            "status",
            "void_reason",
            "voided_at",
            "voided_by"
        ])
        self.reading.reading_status = "BILVOIDED"
        self.reading.save(update_fields=["reading_status"])

    def __str__(self):
        return f"Bill {self.bill_number} - {self.meter.meter_no} - {self.issue_date}"


class BillItem(TenantAwareModel):

    bill = models.ForeignKey(
        "Bill",
        on_delete=models.CASCADE,
        related_name="items"
    )

    block_name = models.CharField(max_length=50)

    units = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)

    amount = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.block_name} - {self.units} units"
    
class BlockRate(TenantAwareModel):
   
    name = models.CharField(max_length=50)
    start_unit = models.DecimalField(max_digits=10, decimal_places=2)
    end_unit = models.DecimalField(max_digits=10, decimal_places=2)
    RES = models.DecimalField(max_digits=10, decimal_places=2) # Residential rate
    COM = models.DecimalField(max_digits=10, decimal_places=2) # Commercial rate
    GOV = models.DecimalField(max_digits=10, decimal_places=2) # Government rate
    PUB = models.DecimalField(max_digits=10, decimal_places=2) # Public rate
    IND = models.DecimalField(max_digits=10, decimal_places=2) # Industry rate
    class Meta:
        ordering = ['start_unit']

    def __str__(self):
        return f"{self.name}: {self.start_unit}-{self.end_unit}"

class BillingSettings(TenantAwareModel):
    late_fee_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    meter_rental_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    billing_cycle_days = models.PositiveIntegerField(default=30)
    bill_overdue_in_days = models.PositiveIntegerField(default=15)
    #reject_less_reading = models.BooleanField(default=False)
    manual_bill_generation = models.BooleanField(default=True)
    bill_generation_date = models.PositiveIntegerField(default=5)
    service_charge_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    operation_charge_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['tenant'],
                name='unique_billing_settings_per_tenant'
            )
        ]

    def __str__(self):
        return "Billing Settings"


class SoldBillReport(TenantAwareModel):
    start_date = models.DateField()
    end_date = models.DateField()
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    bills = models.ManyToManyField(Bill, related_name='reports')
    audited = models.BooleanField(default=False)
    auditor = models.CharField(max_length=100, null=True, blank=True)
    audited_date = models.DateField(null=True, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)

    def __str__(self):
        return f"Report {self.start_date} to {self.end_date} - Total: {self.total_amount}"



