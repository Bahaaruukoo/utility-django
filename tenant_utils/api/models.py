import secrets
import hashlib

from django.db import models

from tenant_manager.models import Tenant
from tenant_utils.models import Branch


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


class APIKey(models.Model):
    name = models.CharField(max_length=100)

    # public identifier (first few chars)
    prefix = models.CharField(max_length=8, db_index=True, null=True, blank=True)

    # hashed secret
    hashed_key = models.CharField(max_length=64, unique=True)

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    can_read_bill = models.BooleanField(default=False)
    can_send_payment_confirmation = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ({self.prefix})"

    def save(self, *args, **kwargs):

        # Only generate if not already set
        if not self.hashed_key:
            raw_key = secrets.token_hex(32)

            self.prefix = raw_key[:8]
            self.hashed_key = hash_key(raw_key)

            # store raw key temporarily so we can show it
            self._raw_key = raw_key

        super().save(*args, **kwargs)