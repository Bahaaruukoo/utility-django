# tenant_manager/admin.py
from __future__ import annotations

import logging
from contextlib import contextmanager

from django.contrib import admin, messages
from django.contrib.admin.sites import AlreadyRegistered
from django.db import connection
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django_tenants.utils import get_public_schema_name

from .models import Domain, Tenant

logger = logging.getLogger(__name__)


@contextmanager
def public_schema():
    """
    Temporarily switch DB connection to public schema, then restore
    whatever schema/tenant was active before.
    """
    original_schema = connection.schema_name
    original_tenant = getattr(connection, "tenant", None)

    connection.set_schema_to_public()
    try:
        yield
    finally:
        # Restore original schema/tenant safely
        if original_schema == get_public_schema_name():
            connection.set_schema_to_public()
        else:
            # Prefer restoring tenant object if available (django-tenants friendly)
            if original_tenant is not None:
                connection.set_tenant(original_tenant)
            else:
                # Fallback: restore schema name directly
                connection.set_schema(original_schema)

'''
class TenantAdminSite(admin.AdminSite):
    """
    Single admin site used on BOTH:
      - public domain  -> platform admin
      - tenant domains -> tenant admin

    Rules:
      - Platform admins can access from anywhere.
      - Tenant admins:
          - must be on a tenant domain (request.tenant exists)
          - must have membership.role == "TENANT_ADMIN" for that tenant
          - must be is_staff == True
    """

    site_header = "Admin"
    site_title = "Admin"
    index_title = "Administration"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Register here so this site is self-contained.
        # Use try/except to avoid reload errors.
        try:
            self.register(Tenant)
        except AlreadyRegistered:
            pass

        try:
            self.register(Domain)
        except AlreadyRegistered:
            pass
    
    def has_permission(self, request):
        """
        Django admin calls this everywhere to decide if user can enter admin.
        """
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        # Platform admin can access from public or any tenant domain
        if getattr(user, "is_platform_admin", False):
            return True

        # Tenant admins MUST be on a tenant domain
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return False

        # Tenant admin must be staff
        if not getattr(user, "is_staff", False):
            return False

        # Check membership in PUBLIC schema (common in django-tenants setups)
        with public_schema():
            # If your membership relation isn't attached, just fail safely
            if not hasattr(user, "tenant_memberships"):
                return False

            if getattr(user, "tenant_id", None) != tenant.id:
                return False
            
            membership = user.tenant_memberships.filter(tenant_id=tenant.id).first()            
            if not membership:
                logger.warning(
                    "User %s attempted tenant admin on %s (id=%s) without membership",
                    getattr(user, "email", user.pk),
                    getattr(tenant, "name", "Tenant"),
                    tenant.id,
                )
                return False

            # Must be tenant admin role
            return getattr(membership, "role", None) == "TENANT_ADMIN"

    def login(self, request, extra_context=None):
        """
        Do NOT block the login form itself.
        But if user is already authenticated and not allowed, redirect nicely.
        """
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            if not self.has_permission(request):
                messages.error(request, "You do not have permission to access this admin site.")
                return redirect("home")
        return super().login(request, extra_context=extra_context)

    def index(self, request, extra_context=None):
        """
        Optional: give a friendlier message instead of default 403.
        """
        if not self.has_permission(request):
            messages.error(request, "You do not have permission to access this admin site.")
            return HttpResponseForbidden("You do not have permission to access this admin site.")
        return super().index(request, extra_context=extra_context)
    '''
    
class NoDeleteAdminMixin:

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions
    
class TenantAdmin( NoDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("name", "schema_name")


class DomainAdmin(admin.ModelAdmin):
    list_display = ("domain", "tenant")

class TenantAdminSite( admin.AdminSite):
    """
    Single admin site used on BOTH:
      - public domain  -> platform admin
      - tenant domains -> tenant admin

    Rules:
      - Platform admins can access from anywhere.
      - Tenant admins:
          - must be on a tenant domain (request.tenant exists)
          - must have membership.role == "TENANT_ADMIN" for that tenant
          - must be is_staff == True

    Deletion:
      - Disabled for ALL users.
    """
    site_header = "Admin"
    site_title = "Admin"
    index_title = "Administration"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        try:
            self.register(Tenant, TenantAdmin)
        except AlreadyRegistered:
            pass

        try:
            self.register(Domain, DomainAdmin)
        except AlreadyRegistered:
            pass
    
    def has_permission(self, request):
        """
        Django admin calls this everywhere to decide if user can enter admin.
        """
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        # Platform admin can access from public or any tenant domain
        if getattr(user, "is_platform_admin", False):
            return True

        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return False

        if not getattr(user, "is_staff", False):
            return False

        with public_schema():
            if not hasattr(user, "tenant_memberships"):
                return False

            if getattr(user, "tenant_id", None) != tenant.id:
                return False

            membership = user.tenant_memberships.filter(tenant_id=tenant.id).first()

            if not membership:
                logger.warning(
                    "User %s attempted tenant admin on %s (id=%s) without membership",
                    getattr(user, "email", user.pk),
                    getattr(tenant, "name", "Tenant"),
                    tenant.id,
                )
                return False

            return getattr(membership, "role", None) == "TENANT_ADMIN"

    def login(self, request, extra_context=None):
        """
        Do NOT block the login form itself.
        """
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            if not self.has_permission(request):
                messages.error(request, "You do not have permission to access this admin site.")
                return redirect("home")
        return super().login(request, extra_context=extra_context)

    def index(self, request, extra_context=None):
        if not self.has_permission(request):
            messages.error(request, "You do not have permission to access this admin site.")
            return HttpResponseForbidden("You do not have permission to access this admin site.")
        return super().index(request, extra_context=extra_context)

    # ----------------------------------------------------
    # Disable delete globally
    # ----------------------------------------------------

    def each_context(self, request):
        """
        Remove delete_selected action globally.
        """
        context = super().each_context(request)
        context["actions"] = None
        return context

    def get_actions(self, request):
        """
        Remove bulk delete action.
        """
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

tenant_domain_admin_site = TenantAdminSite(name="tenant_admin_site")
