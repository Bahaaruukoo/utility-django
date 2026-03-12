# core/auth_backends.py
from __future__ import annotations

from django.contrib.auth.backends import ModelBackend
from django.db import connection

'''
class TenantAwareBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not request:
            return None

        tenant = getattr(request, "tenant", None)
        user = super().authenticate(request, username, password, **kwargs)

        if not user:
            return None

        # platform admins
        if user.is_superuser and user.tenant is None:
            return user
        if user.is_platform_admin and user.tenant is None:
            return user

        # tenant user must match schema
        if tenant and user.tenant_id == tenant.id:
            return user

        return None
'''
# core/auth_backends.py

class TenantAwareBackend(ModelBackend):
    """
    Authenticate users stored in PUBLIC schema (shared users),
    while enforcing tenant boundary only when request.tenant exists.

    Rules:
    - Platform admins (is_platform_admin or is_superuser) can login from anywhere.
    - Tenant users:
        - If request.tenant is present (tenant domain), user.tenant must match it.
        - If request.tenant is None (public domain), allow login (you can redirect later).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if request is None:
            return None

        req_tenant = getattr(request, "tenant", None)

        # ---- Always authenticate in PUBLIC schema (shared user table) ----
        prev_schema = connection.schema_name
        try:
            connection.set_schema_to_public()

            user = super().authenticate(request, username=username, password=password, **kwargs)
            if not user:
                return None

            # ---- Platform admins can login anywhere ----
            if getattr(user, "is_platform_admin", False) or getattr(user, "is_superuser", False):
                return user

            # ---- Tenant users: enforce only if request has tenant ----
            if req_tenant is not None:
                if getattr(user, "tenant_id", None) == req_tenant.id:
                    return user
                return None

            # Public domain login for tenant users is allowed;
            # your TenantLoginView can redirect them to their tenant domain.
            return user

        finally:
            # Restore schema to what it was
            connection.set_schema(prev_schema)
