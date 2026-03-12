from django.conf import settings
from django.db import models
from django.utils import timezone

from tenant_manager.models import Tenant


class TenantAwareModel(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        editable=False
    )

    class Meta:
        abstract = True

class Branch(models.Model):
    """
    Branch belongs to a tenant (public/shared schema model).
    All branch security is enforced by filtering with tenant + membership.
    """
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="branches",
        db_index=True,
    )

    # Human / system identifiers
    name = models.CharField(max_length=150)
    code = models.SlugField(max_length=64)  # used in URL: /b/<code>/

    # Optional metadata
    is_active = models.BooleanField(default=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=32, blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = (("tenant", "code"),)  # code unique per tenant
        indexes = [
            models.Index(fields=["tenant", "code"]),
            models.Index(fields=["tenant", "is_active"]),
        ]
        ordering = ("tenant_id", "name")
        verbose_name = "Branch"
        verbose_name_plural = "Branches"

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class BranchMembership(models.Model):
    """
    Assigns a user to a branch within a tenant.

    IMPORTANT:
    - tenant is duplicated to make filtering fast and enforce consistency.
    - enforce tenant consistency in save() (user.tenant == branch.tenant == tenant)
    """
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="branch_memberships",
        db_index=True,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="branch_user_memberships",
        db_index=True,
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name="memberships",
        db_index=True,
    )

    # Role at branch-level (keep it small; your Role/permissions system can sit on top)
    is_branch_admin = models.BooleanField(default=False)

    # If you want one default branch for a user
    is_default = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = (("tenant", "user", "branch"),)
        indexes = [
            models.Index(fields=["tenant", "user"]),
            models.Index(fields=["tenant", "branch"]),
            models.Index(fields=["tenant", "user", "is_active"]),
        ]
        verbose_name = "Branch Membership"
        verbose_name_plural = "Branch Memberships"

    def __str__(self) -> str:
        return f"{self.user} @ {self.branch}"

    def clean(self):
        """
        Optional: stronger validation if you use ModelForms/admin.
        """
        # tenant must match branch.tenant
        if self.branch_id and self.tenant_id and self.branch.tenant_id != self.tenant_id:
            from django.core.exceptions import ValidationError
            raise ValidationError("Branch tenant mismatch.")

        # tenant must match user.tenant (if user is tenant-scoped)
        if self.user_id and self.tenant_id and getattr(self.user, "tenant_id", None) != self.tenant_id:
            from django.core.exceptions import ValidationError
            raise ValidationError("User tenant mismatch.")

    def save(self, *args, **kwargs):
        """
        Enforce tenant consistency automatically.
        """
        # If tenant missing, infer from branch (preferred)
        if not self.tenant_id and self.branch_id:
            self.tenant_id = self.branch.tenant_id

        # If still missing, infer from user (fallback)
        if not self.tenant_id and self.user_id and getattr(self.user, "tenant_id", None):
            self.tenant_id = self.user.tenant_id

        # Normalize default branch: only one default per (tenant, user)
        # Keep it simple: if setting is_default=True, unset others.
        super().save(*args, **kwargs)
        if self.is_default:
            BranchMembership.objects.filter(
                tenant_id=self.tenant_id,
                user_id=self.user_id,
            ).exclude(pk=self.pk).update(is_default=False)
