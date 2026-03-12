from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from tenant_manager.models import Tenant
from tenant_utils.models import Branch


class AuditAction(models.TextChoices):
    # Invitations
    INVITE_SENT = "INVITE_SENT", "Invite sent"
    INVITE_ACCEPTED = "INVITE_ACCEPTED", "Invite accepted"
    INVITE_REVOKED = "INVITE_REVOKED", "Invite revoked"
    INVITE_EXPIRED = "INVITE_EXPIRED", "Invite expired"

    # Users
    USER_CREATED = "USER_CREATED", "User created"
    USER_UPDATED = "USER_UPDATED", "User updated"
    USER_DEACTIVATED = "USER_DEACTIVATED", "User deactivated"
    USER_REACTIVATED = "USER_REACTIVATED", "User reactivated"

    # Roles & permissions
    ROLE_ASSIGNED = "ROLE_ASSIGNED", "Role assigned"
    ROLE_REMOVED = "ROLE_REMOVED", "Role removed"
    ROLE_PERMS_CHANGED = "ROLE_PERMS_CHANGED", "Role permissions changed"

    # Payments
    PAYMENT_CREATED = "PAYMENT_CREATED", "Payment created"
    PAYMENT_COMPLETED = "PAYMENT_COMPLETED", "Payment completed"
    PAYMENT_REVERSED = "PAYMENT_REVERSED", "Payment reversed"

    # Cashier session
    SESSION_OPENED = "SESSION_OPENED", "Session opened"
    SESSION_CLOSE_REQUESTED = "SESSION_CLOSE_REQUESTED", "Session close requested"
    SESSION_CLOSED = "SESSION_CLOSED", "Session closed"
    SESSION_APPROVED = "SESSION_APPROVED", "Session approved"

    # External payments
    EXTERNAL_PAYMENT_RECEIVED = "EXTERNAL_PAYMENT_RECEIVED", "External payment received"
    EXTERNAL_PAYMENT_POSTED = "EXTERNAL_PAYMENT_POSTED", "External payment posted"

    # Receipt
    RECEIPT_GENERATED = "RECEIPT_GENERATED", "Receipt generated"
    
    # Generic
    GENERIC = "GENERIC", "Generic"


class AuditLog(models.Model):
    """
    Tenant scoped audit log.
    - Tenant admins see only their tenant logs.
    - Platform admins can see everything (and filter by tenant).
    """

    """tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="tenant_audit_logs",
        db_index=True,
    )"""
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        default=None,
        null=True,
        blank=True,
        related_name="tenant_audit_logs",
        db_index=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tenant_audit_logs",
        db_index=True,
    )

    action = models.CharField(
        max_length=64,
        choices=AuditAction.choices,
        default=AuditAction.GENERIC,
        db_index=True,
    )

    # What object was affected (simple + robust)
    target_model = models.CharField(max_length=128, blank=True)
    target_pk = models.CharField(max_length=64, blank=True)
    target_repr = models.CharField(max_length=255, blank=True)

    # Request context (useful for investigation)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    path = models.CharField(max_length=512, blank=True)
    method = models.CharField(max_length=16, blank=True)

    # Old/new values or any structured info
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["branch", "created_at"]),
            models.Index(fields=["branch", "action", "created_at"]),
            models.Index(fields=["branch", "target_model", "target_pk"]),
        ]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"

    def __str__(self):
        who = getattr(self.actor, "email", "SYSTEM")
        return f"[{self.branch}] {self.action} by {who}"
