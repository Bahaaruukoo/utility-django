from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from bills.models import Bill
from core.models import BranchAwareModel, TenantAwareModel
from customers.models import Customer


class CashierSession(BranchAwareModel):

    SESSION_TYPES = [
        ("CASHIER", "Cashier"),
        ("SYSTEM", "System"),
    ]

    session_type = models.CharField(
        max_length=10,
        choices=SESSION_TYPES,
        default="CASHIER"
    )

    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cashier_sessions",
        null=True,   # allow null for system sessions
        blank=True
    )

    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    closing_balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    physical_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    cash_difference = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_sessions"
    )

    approved_at = models.DateTimeField(null=True, blank=True)

    approval_note = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=[
            ("OPEN", "Open"),
            ("PENDING", "Pending Approval"),
            ("CLOSED", "Closed")
        ],
        default="OPEN"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "cashier"],
                condition=models.Q(
                    closed_at__isnull=True,
                    session_type="CASHIER"
                ),
                name="one_open_cashier_session_per_user"
            )
        ]

    def request_close(self):
        pass
    def close(self, supervisor):
        if self.closed_at:
            raise ValueError("Session already closed")

        total_collected = self.payments.filter(
            status="COMPLETED"
        ).aggregate(
            total=models.Sum("amount_paid")
        )["total"] or 0

        self.closing_balance = self.opening_balance + total_collected
        self.closed_at = timezone.now()
        self.approved_by = supervisor
        self.approved_at = timezone.now()
        self.save()

class Payment(BranchAwareModel):
    PAYMENT_METHODS = [
        ("CASH", "Cash"),
        ("BANK", "Bank Transfer"),
        ("MOBILE", "Mobile Money"),
        ("CARD", "Card"),
    ]

    PAYMENT_STATUS = [
        ("PENDING", "Pending"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
        ("REVERSED", "Reversed"),
    ]
    SOURCE_TYPES = [
        ("MANUAL", "Manual"),
        ("EXTERNAL", "External"),
        ("SYSTEM", "System"),
    ]

    
    bill = models.ForeignKey(
        Bill,
        on_delete=models.PROTECT,
        related_name="payments"
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="payments"
    )
    session = models.ForeignKey(
        CashierSession ,
        on_delete=models.PROTECT,
        related_name="payments"
    )
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    source = models.CharField(
        max_length=20,
        choices=SOURCE_TYPES,
        default="MANUAL"
    )
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default="PENDING")

    payment_date = models.DateTimeField(auto_now_add=True)
    reference_number = models.CharField(max_length=100, unique=True)

    received_by = models.ForeignKey( settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="received_payments",
        help_text="Cashier or system user"
    )
    is_reversal = models.BooleanField(default=False)

    reversal_of = models.ForeignKey( "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="reversal_entries"
    )
    def save(self, *args, **kwargs):
        with transaction.atomic():
            session = CashierSession.objects.select_for_update().get(pk=self.session.pk)
            if session.closed_at:
                raise ValueError("Cannot add payment to closed session")

            super().save(*args, **kwargs)

    def __str__(self):
        return f"Payment {self.reference_number} - {self.amount_paid}"
    
    class Meta:
        indexes = [
            models.Index(fields=["payment_date"]),
            models.Index(fields=["reference_number"]),
            models.Index(fields=["status"]),
            models.Index(fields=["payment_method"]),
            models.Index(fields=["received_by"]),
            models.Index(fields=["bill", "status"]),
        ]
   
        constraints = [
            models.UniqueConstraint(
                fields=["bill"],
                condition=models.Q(status="COMPLETED", is_reversal=False),
                name="one_completed_payment_per_bill"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_reversal=False, reversal_of=None) |
                    models.Q(is_reversal=True, reversal_of__isnull=False)
                ),
                name="valid_reversal_relationship"
            )
        ]
        
    
class ExternalPayment(TenantAwareModel):
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    source = models.CharField(max_length=20, choices=[
        ("BANK", "Bank"),
        ("MOBILE", "Mobile Money"),
    ])

    external_reference = models.CharField(max_length=100, unique=True)
    received_at = models.DateTimeField()

    posted = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["external_reference"],
                name="unique_external_reference"
            )
        ]

    indexes = [
        models.Index(fields=["external_reference"]),
        models.Index(fields=["posted"]),
    ]

    def __str__(self):
        return f"{self.source} - {self.external_reference}"

class PaymentAllocation(BranchAwareModel):
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="allocations"
    )

    COMPONENTS = [
        ("WATER", "Water Charge"),
        ("PENALTY", "Penalty"),
        ("INTEREST", "Interest"),
        ("METER_RENT", "Meter Rental"),
        ("SERVICE_FEE", "Service Fee"),
        ("OPERATION_FEE", "Operation Fee"),
        ("OTHER", "Other Charges"),
    ]

    component = models.CharField(max_length=20, choices=COMPONENTS)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.component} - {self.amount}"

class Receipt(BranchAwareModel):
    payment = models.OneToOneField(
        Payment,
        on_delete=models.PROTECT,  
        related_name="receipt"
    )

    receipt_number = models.CharField(max_length=50)

    signature_hash = models.CharField(max_length=64, editable=False)

    issued_date = models.DateTimeField(auto_now_add=True)
    is_void = models.BooleanField(default=False)


    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "receipt_number"],
                name="unique_receipt_per_tenant"
            )
        ]

    '''def save(self, *args, **kwargs):
        if self.pk and not self.is_void:
            raise ValueError("Receipts are immutable and cannot be modified.")
        super().save(*args, **kwargs)
    ''' 
    def save(self, *args, **kwargs):
    # If this is an update (object already exists)
        if self.pk:
            old = type(self).objects.get(pk=self.pk)

            # Check if any field other than is_void has changed
            for field in self._meta.fields:
                name = field.name
                if name == "is_void":
                    continue  # allow is_void to change

                old_value = getattr(old, name)
                new_value = getattr(self, name)

                if old_value != new_value:
                    raise ValueError("You can only void a receipt after creation.")

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Receipt {self.receipt_number}"
    
class PaymentReversal(BranchAwareModel):
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT)
    reason = models.TextField()
    reversed_at = models.DateTimeField(auto_now_add=True)

    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reversed_payments",
        help_text="User who performed the reversal"
    )   

    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="authorized_reversals",
        help_text="User who authorized the reversal"
    )   

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="approved_reversals",
        help_text="User who approved the reversal"
    )
    def __str__(self):
        return f"Reversal for {self.payment.reference_number}"

    class Meta:
        indexes = [
            models.Index(fields=["reversed_at"]),
        ]

class PaymentReversalRequest(TenantAwareModel):

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("PROCESSED", "Processed"),
    ]

    payment = models.OneToOneField(
        Payment,
        on_delete=models.PROTECT,
        related_name="reversal_request"
    )

    reason = models.TextField()

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_reversals"
    )

    requested_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="PENDING"
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_reversals"
    )

    reviewed_at = models.DateTimeField(null=True, blank=True)

    review_note = models.TextField(blank=True)

    