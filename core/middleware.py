# core/middleware.py

from __future__ import annotations

import logging
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from django.urls import Resolver404, resolve
from rest_framework import request

logger = logging.getLogger("app")


from django.contrib.auth.models import Permission
from django.contrib.auth.views import redirect_to_login
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
from django_tenants.utils import get_public_schema_name
from psycopg2 import OperationalError, ProgrammingError

from core.models import TenantRolePermission, TenantUserRole
from tenant_utils.models import (  # adjust import to your actual location
    Branch, BranchMembership)
from utility import settings

from .log_context import set_context

logger = logging.getLogger("app")

'''
class TenantAccessMiddleware:
    """
    Enforce tenant boundary:
    - Platform admins: can access any tenant
    - Tenant users: can only access the tenant matching request.tenant
      and also matching user.tenant
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        # If not authenticated, ignore
        if not request.user.is_authenticated:
            return self.get_response(request)

        # Platform admins bypass
        if getattr(request.user, "is_platform_admin", False):
            return self.get_response(request)

        req_tenant = getattr(request, "tenant", None)

        # If request is on a tenant domain, enforce
        if req_tenant is not None:
            user_tenant = getattr(request.user, "tenant", None)

            if user_tenant is None or user_tenant.id != req_tenant.id:
                return HttpResponseForbidden("You do not have access to this tenant.")

        return self.get_response(request)
'''
class TenantAccessMiddleware:
    """
    Strict tenant boundary enforcement.

    Rules:
    - Platform admins: full access
    - Tenant users: may only access their own tenant domain
    - Tenant users cannot access public admin
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        user = request.user
        tenant = getattr(request, "tenant", None)

        # Not logged in → ignore
        if not user.is_authenticated:
            return self.get_response(request)

        # Platform admins → always allowed
        if getattr(user, "is_platform_admin", False):
            return self.get_response(request)
        '''
        # 🚨 BLOCK tenant users from PUBLIC schema entirely
        if connection.schema_name == get_public_schema_name():
            return HttpResponseForbidden("Tenant users cannot access public area.")
        '''
        # 🚨 STRICT tenant match
        if not tenant or user.tenant_id != tenant.id:
            return HttpResponseForbidden("Cross-tenant access denied.")

        return self.get_response(request)


class TenantPermissionMiddleware:
    """
    Inject tenant-scoped permissions into request.user._perm_cache
    using:
      TenantUserRole(user, role, tenant)
      TenantRolePermission(tenant, role) -> permissions M2M
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        user = request.user
        if not user.is_authenticated:
            return self.get_response(request)

        # Platform admin: keep default Django perms (or you can inject all)
        if getattr(user, "is_platform_admin", False):
            return self.get_response(request)

        tenant = getattr(request, "tenant", None) or getattr(user, "tenant", None)
        if not tenant:
            return self.get_response(request)

        role_ids = TenantUserRole.objects.filter(
            user=user,
            tenant=tenant
        ).values_list("role_id", flat=True)

        perms_qs = Permission.objects.filter(
            tenantrolepermission__tenant=tenant,
            tenantrolepermission__role_id__in=role_ids
        ).distinct()

        user._perm_cache = set(
            f"{p.content_type.app_label}.{p.codename}" for p in perms_qs
        )

        return self.get_response(request)

class NoTenantUserOnPublicAdminMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/admin/"):
            tenant = getattr(request, "tenant", None)
            if tenant is None and request.user.is_authenticated:
                if not getattr(request.user, "is_platform_admin", False):
                    return HttpResponseForbidden("Not allowed.")
        return self.get_response(request)
    

@dataclass
class BranchResolution:
    branch: Optional[Branch] = None
    membership: Optional[BranchMembership] = None



class PublicAuthSchemaMiddleware(MiddlewareMixin):
    """
    Ensure auth endpoints query users from PUBLIC schema.
    Works well with django-tenants when users live in public schema.
    """

    AUTH_PREFIXES = (
        "/accounts/login/",
        "/admin/login/",
        "/accounts/password/reset/",
        "/accounts/password/change/",
    )

    def process_request(self, request):
        request._schema_before_auth = None
        if request.path.startswith(self.AUTH_PREFIXES):
            request._schema_before_auth = connection.schema_name
            connection.set_schema_to_public()

    def process_response(self, request, response):
        prev = getattr(request, "_schema_before_auth", None)
        if prev and prev != connection.schema_name:
            connection.set_schema(prev)
        return response

    def process_exception(self, request, exception):
        prev = getattr(request, "_schema_before_auth", None)
        if prev:
            connection.set_schema(prev)


class BranchMiddleware(MiddlewareMixin):

    def process_request(self, request):
        request.branch = None
        request.branch_membership = None
        request.is_branch_admin = False

        # 🚨 DO NOT RUN IN PUBLIC SCHEMA
        if connection.schema_name == get_public_schema_name():
            return None

        tenant = getattr(request, "tenant", None)
        user = getattr(request, "user", None)

        if not tenant or not user or not user.is_authenticated:
            return None

        try:
            membership = BranchMembership.objects.filter(
                tenant=tenant,
                user=user,
                is_active=True,
            ).select_related("branch").first()

        except (ProgrammingError, OperationalError):
            # Table not migrated yet
            return None

        if not membership:
            return None

        request.branch_membership = membership
        request.branch = membership.branch
        request.is_branch_admin = bool(membership.is_branch_admin)

        return None


class RequestLoggingMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        request_id = str(uuid.uuid4())
        start_time = time.time()

        # Default values
        tenant = "anonymous"
        user = "anonymous"
        branch = "None"

        if hasattr(request, "user") and request.user.is_authenticated:

            user = str(request.user)

            tenant_obj = getattr(request, "tenant", None)
            tenant = str(tenant_obj) if tenant_obj else "public"

            branch_obj = getattr(request, "branch", None)
            branch = str(branch_obj) if branch_obj else "None"

        set_context(
            tenant=tenant,
            branch=branch,
            user=user,
            request_id=request_id
        )

        response = self.get_response(request)

        duration = int((time.time() - start_time) * 1000)

        logger.info(
            f"{request.method} {request.path} {response.status_code} {duration}ms"
        )

        response["X-Request-ID"] = request_id

        return response

class SessionBindingMiddleware:
    """
    Browser session binding protection.

    Prevents replay of a stolen session cookie by requiring an additional
    browser binding token.

    This middleware MUST be placed:

        SessionMiddleware
        ↓
        SessionBindingMiddleware
        ↓
        AuthenticationMiddleware

    so the binding is verified before Django authenticates the session.
    """

    COOKIE_NAME = settings.BINDING_COOKIE_NAME
    SESSION_KEY = settings.BINDING_SESSION_KEY

    # URL names that must bypass binding verification
    EXEMPT_URL_NAMES = {
        "account_login",
        "account_logout",
        "account_reset_password",
        "account_reset_password_done",
        "account_reset_password_from_key",
        "account_reset_password_from_key_done",
        "admin_login",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        # ------------------------------------------------------------
        # Ignore anonymous sessions
        # ------------------------------------------------------------
        if request.session.session_key is None:
            return self.get_response(request)

        # ------------------------------------------------------------
        # Skip exempt URLs
        # ------------------------------------------------------------
        try:
            match = resolve(request.path_info)

            if match.url_name in self.EXEMPT_URL_NAMES:
                return self.get_response(request)

        except Resolver404:
            # Unknown URL
            return self.get_response(request)

        # ------------------------------------------------------------
        # Retrieve binding tokens
        # ------------------------------------------------------------
        session_token = request.session.get(self.SESSION_KEY)
        cookie_token = request.COOKIES.get(self.COOKIE_NAME)

        # ------------------------------------------------------------
        # Session has no binding token
        #
        # This may happen for:
        # - anonymous sessions
        # - old sessions created before this feature
        #
        # Allow the request to continue.
        # ------------------------------------------------------------
        if session_token is None:
            return self.get_response(request)

        # ------------------------------------------------------------
        # Cookie missing
        # ------------------------------------------------------------
        if cookie_token is None:

            logger.warning(
                "Session binding cookie missing. "
                "session=%s ip=%s path=%s ua=%s",
                request.session.session_key,
                request.META.get("REMOTE_ADDR"),
                request.path,
                request.META.get("HTTP_USER_AGENT", "")[:250],
            )

            return HttpResponseForbidden("Invalid session binding.")

        # ------------------------------------------------------------
        # Binding mismatch
        # ------------------------------------------------------------
        print("Session :", repr(session_token))
        print("Cookie  :", repr(cookie_token))
        print("Equal   :", session_token == cookie_token)
        if not secrets.compare_digest(session_token, cookie_token):

            logger.warning(
                "Session binding mismatch. "
                "session=%s ip=%s path=%s ua=%s",
                request.session.session_key,
                request.META.get("REMOTE_ADDR"),
                request.path,
                request.META.get("HTTP_USER_AGENT", "")[:250],
            )

            return HttpResponseForbidden("Invalid session binding.")

        return self.get_response(request)

class SessionBindingCookieMiddleware:


    COOKIE_NAME = settings.BINDING_COOKIE_NAME
    SESSION_KEY = settings.BINDING_SESSION_KEY

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # ------------------------------------------
        # Create cookie after successful login
        # ------------------------------------------
        if request.session.pop("_set_binding_cookie", False):

            response.set_cookie(
                self.COOKIE_NAME,
                request.session["_binding_token"],
                httponly=True,
                secure=not settings.DEBUG,
                samesite="Lax",
                path="/",
            )

        # ------------------------------------------
        # Remove cookie after logout
        # ------------------------------------------
        try:
            match = resolve(request.path_info)

            if match.url_name == "account_logout":
                response.delete_cookie(
                    self.COOKIE_NAME,
                    path="/",
                )

        except Resolver404:
            pass

        return response

