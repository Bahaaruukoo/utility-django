import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models, transaction
from django.forms import ValidationError
from django.utils import timezone
from PIL import Image

from core.models import TenantAwareModel
from tenant_utils.models import Branch


class Woreda(TenantAwareModel):
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name}"

class Kebele(TenantAwareModel):
    name = models.CharField(max_length=100)
    number = models.CharField(max_length=20, blank=True)
    woreda = models.ForeignKey(Woreda, default=None, null=True, on_delete=models.CASCADE, related_name="kebeles")    

    def __str__(self):
        return f"{self.name}"
    
class Customer(TenantAwareModel):
    CUSTOMER_TYPE_CHOICES = (
        ('RES', 'Residential'),
        ('COM', 'Commercial'),
        ('GOV', 'Government'),
        ('PUB', 'Public'),
        ('IND', 'Industry'),
    )

    customer_no = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True
    )
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    woreda = models.ForeignKey('Woreda', on_delete=models.SET_NULL, null=True, blank=True)
    kebele = models.ForeignKey('Kebele', on_delete=models.SET_NULL, null=True, blank=True)
    address = models.TextField()
    id_number = models.CharField(max_length=100, blank=True)
    id_image = models.ImageField(upload_to='id_images/', blank=True, null=True)
    delegation_letter = models.FileField(upload_to='delegation_letters/', blank=True, null=True)

    customer_type = models.CharField(
        max_length=3,
        choices=CUSTOMER_TYPE_CHOICES,
        default='RES'
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    registered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    updated_at = models.DateTimeField(default=None, blank=True, null=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_customers"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer_no"],
                name="unique_customer_per_tenant"
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "created_at"])
        ]

    def save(self, *args, **kwargs):
        if not self.customer_no:
            with transaction.atomic():
                last = (
                    Customer.objects
                    .select_for_update()
                    .filter(tenant=self.tenant)
                    .order_by("-id")
                    .first()
                )
                next_number = 1 if not last else last.id + 1
                self.customer_no = f"{self.tenant.schema_name.upper()}-{next_number:06d}"

        super().save(*args, **kwargs)

    def full_name(self):
        return f"{self.first_name} {self.middle_name } {self.last_name}".strip()

    def __str__(self):
        return f"{self.full_name()} - {self.phone}"
    

class CustomerActivationDeactivation(TenantAwareModel):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="deactivation_logs")
    action_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    reason = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.customer} changed by {self.action_by} at {self.timestamp}"
    
class Meter(TenantAwareModel):
    METER_STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
        ('FAULTY', 'Faulty'),
        ('REMOVED', 'Removed'),
    )
    METER_TYPE_CHOICES = (
        ('WATER', 'Water'),
        ('ELECTRIC', 'Electric'),
        ('GAS', 'Gas'),
    )
    meter_number = models.CharField(max_length=50, unique=True)
    bill_number = models.PositiveIntegerField(unique=True, editable=False)  # constant per meter
    meter_size = models.CharField(max_length=50)
    meter_type = models.CharField(max_length=50, choices=METER_TYPE_CHOICES, default='WATER')
    status = models.CharField(max_length=10, choices=METER_STATUS_CHOICES, default='ACTIVE')
    initial_reading = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)

    @property
    def created_at_ddmmyyyy(self):
        return self.created_at.strftime("%d-%m-%Y") if self.created_at else ""

    @property
    def created_at_yyyymmdd(self):
        return self.created_at.strftime("%Y-%m-%d") if self.created_at else ""

    @property
    def updated_at_ddmmyyyy(self):
        return self.updated_at.strftime("%d-%m-%Y") if self.updated_at else ""

    @property
    def updated_at_yyyymmdd(self):
        return self.updated_at.strftime("%Y-%m-%d") if self.updated_at else ""
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "meter_number"],
                name="unique_meter_per_tenant"
            )
        ]

    def save(self, *args, **kwargs):
        if not self.bill_number:
            self.bill_number = Meter.next_bill_number(self.tenant)
        super().save(*args, **kwargs)

    @classmethod
    def next_bill_number(cls, tenant):
        with transaction.atomic():
            last = (
                cls.objects
                .select_for_update()
                .filter(tenant=tenant)
                .order_by("-bill_number")
                .first()
            )
            return (last.bill_number + 1) if last else 100000
        
    def __str__(self):
        return self.meter_number
    
class MeterAssignment(TenantAwareModel):
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="meter_assignments"
    )
    meter = models.ForeignKey(
        Meter,
        on_delete=models.CASCADE,
        related_name="assignments"
    )
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    installation_address = models.TextField()
    building_name = models.CharField(max_length=100, blank=True)    
    apartment_no = models.CharField(max_length=50, blank=True) 
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)      

    installation_date = models.DateField()
    removal_date = models.DateField(null=True, blank=True)  
    
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['meter'],
                condition=models.Q(is_active=True),
                name='one_active_meter_assignment'
            )
        ]

    def __str__(self):
        return f"{self.meter} → {self.customer}"    
    
    def clean(self):
        if self.meter.tenant != self.tenant:
            raise ValidationError("Meter tenant mismatch.")

        if self.meter.status != "ACTIVE":
            raise ValidationError("Cannot assign inactive meter.")

        if self.is_active:
            existing = MeterAssignment.objects.filter(
                tenant=self.tenant,
                meter=self.meter,
                is_active=True
            ).exclude(pk=self.pk)

            if existing.exists():
                raise ValidationError("This meter is already actively assigned.")

