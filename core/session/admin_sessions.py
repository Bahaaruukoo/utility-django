from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone

#from core.admin_sites import platform_admin_site, tenant_admin_site

User = get_user_model()

@dataclass
class SessionRow:
    session_key: str
    expires: Any
    user: Any


def _is_platform_admin(user) -> bool:
    return bool(user.is_authenticated and getattr(user, "is_platform_admin", False))


def _is_tenant_admin(request: HttpRequest) -> bool:
    u = request.user
    return bool(
        u.is_authenticated
        and getattr(u, "is_staff", False)
        and not getattr(u, "is_platform_admin", False)
    )


def _extract_user_id_from_session(session: Session) -> int | None:
    """
    Django stores the logged-in user id in session under _auth_user_id.
    """
    try:
        data = session.get_decoded()
    except Exception:
        return None

    uid = data.get("_auth_user_id")
    if not uid:
        return None
    try:
        return int(uid)
    except Exception:
        return None


def _tenant_from_request(request: HttpRequest):
    # django-tenants attaches request.tenant on tenant domains
    return getattr(request, "tenant", None)


def _can_view_sessions(request: HttpRequest) -> bool:
    if not request.user.is_authenticated:
        return False
    if _is_platform_admin(request.user):
        return True
    return _is_tenant_admin(request)


class AdminSessionViewsMixin:
    """
    Add:
      /admin/sessions/                     -> list active sessions
      /admin/sessions/revoke/<key>/        -> revoke 1 session (POST)
      /admin/sessions/revoke-user/<id>/    -> revoke all sessions for user (POST)
    """

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path("sessions/", self.admin_view(self.sessions_list_view), name="active_sessions"),
            path("sessions/revoke/<str:session_key>/", self.admin_view(self.revoke_session_view), name="revoke_session"),
            path("sessions/revoke-user/<int:user_id>/", self.admin_view(self.revoke_user_sessions_view), name="revoke_user_sessions"),
        ]
        return my_urls + urls

    def sessions_list_view(self, request: HttpRequest) -> HttpResponse:
        if not _can_view_sessions(request):
            return redirect("admin:login")

        now = timezone.now()

        # Active sessions only
        sessions_qs = Session.objects.filter(expire_date__gte=now).order_by("-expire_date")

        # Safety: avoid decoding tens of thousands in a big system
        sessions_qs = sessions_qs[:5000]

        # Decode sessions -> user_ids
        session_to_uid: dict[str, int] = {}
        user_ids: set[int] = set()
        for s in sessions_qs:
            uid = _extract_user_id_from_session(s)
            if uid:
                session_to_uid[s.session_key] = uid
                user_ids.add(uid)

        # Load users (public/shared schema user table)
        users = User.objects.filter(id__in=user_ids)
        users_by_id = {u.id: u for u in users}

        # Apply tenant boundary for tenant admins
        req_tenant = _tenant_from_request(request)
        if not _is_platform_admin(request.user):
            # tenant admins: request must be on a tenant
            if not req_tenant:
                sessions_rows: list[SessionRow] = []
            else:
                allowed_users_by_id = {
                    u.id: u for u in users_by_id.values()
                    if getattr(u, "tenant_id", None) == getattr(req_tenant, "id", None)
                }
                users_by_id = allowed_users_by_id

        # Build rows
        rows: list[SessionRow] = []
        for s in sessions_qs:
            uid = session_to_uid.get(s.session_key)
            if not uid:
                continue
            u = users_by_id.get(uid)
            if not u:
                continue
            rows.append(SessionRow(session_key=s.session_key, expires=s.expire_date, user=u))

        # Optional tenant filter UI for platform admin
        tenant_filter = request.GET.get("tenant")
        if _is_platform_admin(request.user) and tenant_filter:
            try:
                tenant_id = int(tenant_filter)
                rows = [r for r in rows if getattr(r.user, "tenant_id", None) == tenant_id]
            except Exception:
                pass

        # Group by user
        grouped: dict[Any, list[SessionRow]] = {}
        for r in rows:
            grouped.setdefault(r.user, []).append(r)

        context = {
            **self.each_context(request),
            "title": "Active Sessions",
            "grouped": grouped,
            "is_platform_admin": _is_platform_admin(request.user),
            "tenant_filter": tenant_filter or "",
        }
        return render(request, "admin/active_sessions.html", context)

    def revoke_session_view(self, request: HttpRequest, session_key: str) -> HttpResponse:
        if request.method != "POST":
            return redirect("admin:active_sessions")
        if not _can_view_sessions(request):
            return redirect("admin:login")

        # Tenant boundary: tenant admins can revoke only within their tenant
        if not _is_platform_admin(request.user):
            req_tenant = _tenant_from_request(request)
            if not req_tenant:
                messages.error(request, "No tenant context.")
                return redirect("admin:active_sessions")

            s = Session.objects.filter(session_key=session_key).first()
            if not s:
                return redirect("admin:active_sessions")
            uid = _extract_user_id_from_session(s)
            if not uid:
                return redirect("admin:active_sessions")

            u = User.objects.filter(id=uid).first()
            if not u or getattr(u, "tenant_id", None) != getattr(req_tenant, "id", None):
                messages.error(request, "Not allowed.")
                return redirect("admin:active_sessions")

        Session.objects.filter(session_key=session_key).delete()
        messages.success(request, "Session revoked.")
        return redirect("admin:active_sessions")

    def revoke_user_sessions_view(self, request: HttpRequest, user_id: int) -> HttpResponse:
        if request.method != "POST":
            return redirect("admin:active_sessions")
        if not _can_view_sessions(request):
            return redirect("admin:login")

        # Tenant boundary for tenant admins
        if not _is_platform_admin(request.user):
            req_tenant = _tenant_from_request(request)
            if not req_tenant:
                messages.error(request, "No tenant context.")
                return redirect("admin:active_sessions")

            u = User.objects.filter(id=user_id).first()
            if not u or getattr(u, "tenant_id", None) != getattr(req_tenant, "id", None):
                messages.error(request, "Not allowed.")
                return redirect("admin:active_sessions")

        # Delete all sessions matching user_id
        now = timezone.now()
        sessions_qs = Session.objects.filter(expire_date__gte=now)
        deleted = 0
        for s in sessions_qs:
            uid = _extract_user_id_from_session(s)
            if uid == user_id:
                s.delete()
                deleted += 1

        messages.success(request, f"Revoked {deleted} session(s) for that user.")
        return redirect("admin:active_sessions")


    