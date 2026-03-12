import secrets

from django.db import models

from tenant_manager.models import Tenant
from tenant_utils.models import Branch


class APIKey(models.Model):
    name = models.CharField(max_length=100)
    key = models.CharField(max_length=64, unique=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    can_read_bill = models.BooleanField(default=False)
    can_send_payment_confirmation = models.BooleanField(default=False)

    def __str__(self):
        return self.key
    
    def save(self, *args, **kwargs):

        if len(self.key) < 64:
            self.key = secrets.token_hex(32)

        super().save(*args, **kwargs)