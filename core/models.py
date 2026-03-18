from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import (AbstractBaseUser, Permission,
                                        PermissionsMixin)
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from PIL import Image

from tenant_manager.models import Tenant
from tenant_utils.models import Branch

ALLOWED_TENANT_APPS = settings.TENANT_APPS

# =====================================================
# ROLE (GLOBAL CATALOG)
# Same role names reused by all tenants
# =====================================================

class RoleTemplate(models.Model):
    name = models.CharField(max_length=100, unique=True)

    permissions = models.ManyToManyField(
        Permission,
        blank=True,
        related_name="role_templates"
    )

    description = models.TextField(blank=True)

    def __str__(self):
        return self.name
    

class Role(models.Model):
    name = models.CharField(max_length=50, unique=True)
    template = models.ForeignKey( RoleTemplate, null=True, blank=True, on_delete=models.SET_NULL )
    def __str__(self):
        return self.name
        
# =====================================================
# TENANT ROLE PERMISSIONS
# Each tenant assigns permissions to each role
# =====================================================


class TenantRolePermission(models.Model):

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    role = models.ForeignKey("Role", on_delete=models.CASCADE)
    permissions = models.ManyToManyField(Permission, blank=True)

    class Meta:
        unique_together = ("tenant", "role")
        verbose_name = "Role Permission"
        verbose_name_plural = "Role Permissions"

    def __str__(self):
        tenant = self.tenant.name if self.tenant_id else "No Tenant"
        role = self.role.name if self.role_id else "No Role"
        return f"{tenant} - {role}"
    

    def clean(self):
        """
        Validate that only tenant-safe permissions are assigned.
        """

        if not self.pk:
            return  # instance not saved yet, skip validation

        invalid_perms = []

        for perm in self.permissions.all():
            if perm.content_type.app_label not in ALLOWED_TENANT_APPS:
                invalid_perms.append(perm.codename)

        if invalid_perms:
            raise ValidationError(
                f"These permissions are not allowed for tenants: {', '.join(invalid_perms)}"
            )
# =====================================================
# USER ↔ ROLE (per tenant)
# =====================================================

class TenantUserRole(models.Model):
    user = models.ForeignKey("CustomUser", on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role", "tenant"],
                name="unique_user_role_per_tenant",
                violation_error_message="This user already has this role in this tenant."
            )
        ]
        verbose_name = "User Role"
        verbose_name_plural = "User Roles"
        permissions = [
            ("manage_user_roles", "Can manage user roles"),
        ]

    def __str__(self):
        tenant_name = getattr(self.tenant, "name", None) if self.tenant_id else "NO_TENANT"
        return f"{self.user.email} → {self.role.name} @ {tenant_name}"

    def save(self, *args, **kwargs):
        # Always force tenant from user if missing
        if not self.tenant_id and self.user_id and getattr(self.user, "tenant_id", None):
            self.tenant_id = self.user.tenant_id
        self.full_clean()  # triggers validation before hitting DB
        super().save(*args, **kwargs)

# =====================================================
# CUSTOM USER MANAGER
# =====================================================

class CustomUserManager(BaseUserManager):

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Platform admin (public schema)
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_platform_admin", True)
        extra_fields.setdefault("tenant", None)

        return self.create_user(email, password, **extra_fields)


# =====================================================
# CUSTOM USER (GLOBAL)
# =====================================================

class CustomUser(AbstractBaseUser, PermissionsMixin):
    
    first_name = models.CharField(max_length=50, blank=True)
    middle_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)
    email = models.EmailField(unique=True)

    # NULL = platform admin
    tenant = models.ForeignKey(
        Tenant,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users",
    )

    roles = models.ManyToManyField(
        Role,
        through="TenantUserRole",
        blank=True
    )

    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_platform_admin = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False) # For tenant-level admin role (can be assigned to users)
    is_branch_admin = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def get_all_permissions(self, obj=None):
        if self.is_platform_admin:
            return super().get_all_permissions(obj)

        tenant = getattr(self, "tenant", None)
        if not tenant:
            return set()

        role_ids = TenantUserRole.objects.filter(
            user=self,
            tenant=tenant
        ).values_list("role_id", flat=True)

        perms = Permission.objects.filter(
            tenantrolepermission__tenant=tenant,
            tenantrolepermission__role_id__in=role_ids
        )

        return {
            f"{p.content_type.app_label}.{p.codename}"
            for p in perms
        }
    
    def has_perm(self, perm, obj=None):

        if not self.is_active:
            return False

        if self.is_platform_admin:
            return True

        return perm in self.get_all_permissions()
    
    def get_full_name(self):
        return " ".join(filter(None, [self.first_name, self.middle_name, self.last_name]))
    
    def __str__(self):
        return str(self.first_name +" "+ self.middle_name +" "+ self.last_name)

# =====================================================
# OPTIONAL PROFILE
# =====================================================

class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile"
    )
    phone = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    department = models.CharField(max_length=100, blank=True)
    position = models.CharField(max_length=100, blank=True)
    picture = models.ImageField(upload_to="profile_pics/", blank=True, null=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if self.picture:
            img = Image.open(self.picture.path)

            if img.height > 300 or img.width > 300:
                output_size = (300, 300)
                img.thumbnail(output_size)
                img.save(self.picture.path)
                
        def __str__(self):
            return f"{self.user.email} Profile"


# =====================================================
# INVITATION (TENANT SCOPED)
# =====================================================

class Invitation(models.Model):

    email = models.EmailField()

    tenant = models.ForeignKey(
        Tenant,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="invitations",
    )

    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE
    )

    token = models.UUIDField(default=uuid.uuid4, unique=True)
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL
    )

    def is_expired(self):
        return self.expires_at and timezone.now() > self.expires_at
    
    def __str__(self):
        return f"{self.email} → {self.tenant.name} ({self.role.name})"


# =====================================================
# BASE MODEL FOR TENANT APPS
# =====================================================

class TenantAwareModel(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        editable=False
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            raise ValueError("Tenant must be set before saving.")
        super().save(*args, **kwargs)

class BranchAwareModel(TenantAwareModel):

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        default=None,
        null=True,
        db_index=True
    )

    class Meta:
        abstract = True