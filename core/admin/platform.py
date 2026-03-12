from collections import defaultdict
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.sessions.models import Session
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from core.admin_audit import *  # noqa
from core.admin_sites import platform_admin_site
from core.audit import audit, log_audit
from core.models import (CustomUser, Invitation, Profile, Role, RoleTemplate,
                         TenantRolePermission, TenantUserRole)
from core.models_audit import AuditAction, AuditLog
from core.session.admin_mixins import UserSessionAdminMixin
from tenant_manager.models import Tenant

# core/admin_platform.py (or your platform admin file)

def _parse_session_expire(session: Session) -> str:
    # Pretty formatting
    try:
        exp = session.expire_date
        if timezone.is_aware(exp):
            exp_local = timezone.localtime(exp)
        else:
            exp_local = exp
        return exp_local.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(session.expire_date)


def _session_user_id(session: Session) -> int | None:
    """
    Extract _auth_user_id from session data.
    Works with DB session backend.
    """
    try:
        data = session.get_decoded()
        uid = data.get("_auth_user_id")
        return int(uid) if uid is not None else None
    except Exception:
        return None


class ProfileInline(admin.StackedInline):
    model = Profile
    extra = 0
    can_delete = False
    fields = ("phone", "address", "department", "position", "picture")


class TenantUserRoleInline(admin.TabularInline):
    model = TenantUserRole
    fk_name = "user"
    extra = 0
    can_delete = True
    fields = ("tenant", "role")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "role":
            kwargs["queryset"] = Role.objects.all().order_by("name")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(CustomUser, site=platform_admin_site)
class PlatformUserAdmin(BaseUserAdmin):
    model = CustomUser
    inlines = [ProfileInline, TenantUserRoleInline]
    ordering = ("email",)
    search_fields = ("email",)

    list_display = ("email", "first_name", "middle_name", "last_name", "tenant", "is_platform_admin", "is_staff", "is_active", "sessions_link")

    fieldsets = (
        (None, {"fields": ("first_name", "middle_name", "last_name", "email", "password")}),
        ("Status", {"fields": ("tenant", "is_platform_admin", "is_staff", "is_superuser", "is_active")}),
        ("Important dates", {"fields": ("last_login",)}),
    )

    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2", "tenant", "is_platform_admin", "is_staff", "is_active")}),
    )
    
    # ------------------------------------------------------------------
    # Sessions button on the user list
    # ------------------------------------------------------------------
    def sessions_link(self, obj):
        url = reverse(f"{self.admin_site.name}:core_user_sessions", args=[obj.pk])
        return format_html('<a class="button" href="{}">Sessions</a>', url)

    sessions_link.short_description = "Sessions"

    # ------------------------------------------------------------------
    # Custom URLs
    # ------------------------------------------------------------------
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:user_id>/sessions/",
                self.admin_site.admin_view(self.user_sessions_view),
                name="core_user_sessions",
            ),
            path(
                "<int:user_id>/sessions/revoke/",
                self.admin_site.admin_view(self.user_sessions_revoke_view),
                name="core_user_sessions_revoke",
            ),
        ]
        return custom + urls

    # ------------------------------------------------------------------
    # Sessions views
    # ------------------------------------------------------------------
    def user_sessions_view(self, request, user_id: int, *args: Any, **kwargs: Any):
        """
        Show active sessions for a specific user.
        """
        user = get_object_or_404(CustomUser, pk=user_id)

        # Find sessions that belong to this user
        sessions = []
        now = timezone.now()

        for s in Session.objects.filter(expire_date__gt=now).order_by("-expire_date"):
            if _session_user_id(s) == user.id:
                sessions.append(
                    {
                        "session_key": s.session_key,
                        "expires": _parse_session_expire(s),
                    }
                )

        context = {
            **self.admin_site.each_context(request),
            "title": f"Active sessions for {user.email}",
            "target_user": user,
            "sessions": sessions,
            "revoke_url": reverse(
                f"{self.admin_site.name}:core_user_sessions_revoke",
                args=[user.id],
            ),
            "back_url": reverse(f"{self.admin_site.name}:core_customuser_changelist")
            if "customuser" in self.model._meta.model_name.lower()
            else reverse(f"{self.admin_site.name}:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"),
        }

        # Create this template file (below)
        return render(request, "admin/platform/user_sessions.html", context)

    def user_sessions_revoke_view(self, request, user_id: int, *args: Any, **kwargs: Any):
        """
        Revoke all sessions for a specific user (force logout everywhere).
        """
        user = get_object_or_404(CustomUser, pk=user_id)
        now = timezone.now()

        deleted = 0
        for s in Session.objects.filter(expire_date__gt=now):
            if _session_user_id(s) == user.id:
                s.delete()
                deleted += 1

        messages.success(request, f"Revoked {deleted} session(s) for {user.email}.")
        return redirect(reverse(f"{self.admin_site.name}:core_user_sessions", args=[user.id]))
    
@admin.register(Role, site=platform_admin_site)
class RolePlatformAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(TenantRolePermission, site=platform_admin_site)
class TenantRolePermissionPlatformAdmin(admin.ModelAdmin):
    list_display = ("tenant", "role")
    list_filter = ("tenant", "role")
    search_fields = ("tenant__name", "role__name")
    filter_horizontal = ("permissions",)

def build_invite_url(request, *, token, tenant_domain: str | None):
    """
    Builds a link that points to the correct host:
    - tenant_domain if tenant invite
    - current host if platform invite
    """
    scheme = "https" if request.is_secure() else "http"
    host = tenant_domain or request.get_host()

    port = request.get_port()
    if ":" in host:
        full_host = host
    else:
        if port and port not in ("80", "443"):
            full_host = f"{host}:{port}"
        else:
            full_host = host

    # IMPORTANT: must match your core/urls.py pattern
    return f"{scheme}://{full_host}/register-invite/{token}/"

@admin.register(Tenant, site=platform_admin_site)
class TenantPlatformAdmin(admin.ModelAdmin):
    list_display = ("name", "primary_domain", "send_invite_button")
    search_fields = ("name",)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:tenant_id>/send-invite/",
                self.admin_site.admin_view(self.send_invite_view),
                name="tenant_send_invite",
            ),
        ]
        return custom_urls + urls

    def primary_domain(self, obj):
        d = obj.domains.first()
        return d.domain if d else "-"
    primary_domain.short_description = "Domain"
    
    def send_invite_button(self, obj):
        url = reverse("platform_admin:tenant_send_invite", args=[obj.id])
        return format_html('<a class="button" href="{}">Send Invite</a>', url)
    send_invite_button.short_description = "Send Invite"

    #@audit(AuditAction.INVITE_SENT)
    def send_invite_view(self, request, tenant_id, *args, **kwargs):
        tenant = get_object_or_404(Tenant, pk=tenant_id)
        if request.method == "POST":
            email = request.POST.get("email")
            role_id = request.POST.get("role")

            role = get_object_or_404(Role, pk=role_id)

            if email and role_id:

                # Check existing user in this tenant
                if CustomUser.objects.filter(
                    email=email,
                    tenant=tenant
                ).exists():
                    messages.error(
                        request,
                        f"A user with email {email} already exists in this tenant."
                    )
                    return redirect(request.path)
                
                active_invite_exists = Invitation.objects.filter(
                    email=email,
                    tenant=tenant,
                    used=False,
                ).exclude(expires_at__lt=timezone.now()).exists()

                if active_invite_exists:
                    messages.error(request, "An active (non-expired) invitation already exists for this email.")
                    #return redirect(request.path)
                    invite = active_invite_exists.first()  # get the existing invite to resend
                else:
                    invite = Invitation.objects.create(
                        email=email,
                        tenant=tenant,
                        role=role,
                        expires_at=timezone.now() + timedelta(days=2),
                        sent_by=request.user if request.user.is_authenticated else None,
                    )
                    log_audit(
                        tenant=tenant,
                        actor=request.user,
                        action=AuditAction.INVITE_SENT,
                        target=invite,
                        request=request,
                        metadata={"invitee_email": email, "role_id": role.id, "role_name": role.name},
                    )
                # ✅ CRITICAL: build link to TENANT domain (not platform host)
                tenant_domain = None
                dom = tenant.domains.first()
                if dom:
                    tenant_domain = dom.domain

                invite_link = build_invite_url(
                    request,
                    token=invite.token,
                    tenant_domain=tenant_domain,
                )

                subject = f"Invitation to join {tenant.name}"
                message = (
                    f"Hello,\n\n"
                    f"You have been invited to join {tenant.name} as {role.name}.\n\n"
                    f"Register here:\n{invite_link}\n"
                )
                send_mail(subject, message, "noreply@example.com", [invite.email])

                self.message_user(request, f"Invitation sent to {email}", level=messages.SUCCESS)
                return redirect("platform_admin:tenant_manager_tenant_changelist")

        return render(request, "admin/tenant_send_invite.html", {
            "title": f"Send Invitation for {tenant.name}",
            "tenant": tenant,
            "roles": Role.objects.all().order_by("name"),
        })

    def has_module_permission(self, request): return True
    def has_view_permission(self, request, obj=None): True
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return True
    def has_delete_permission(self, request, obj=None): return False

@admin.register(AuditLog, site=platform_admin_site)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "tenant", "action", "actor", "target_repr")
    list_filter = ("tenant", "action", "created_at")
    search_fields = ("actor__email", "target_repr", "target_model", "target_pk", "path", "ip_address")
    
    readonly_fields = (
        "tenant", "actor", "action",
        "target_model", "target_pk", "target_repr",
        "ip_address", "user_agent", "path", "method",
        "metadata", "created_at",
    )
    ordering = ("-created_at",)
    actions = None
    def has_add_permission(self, request):
        return False  # logs should be write-only via code

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # optional: allow platform admin to delete, but usually keep immutable
        return False # getattr(request.user, "is_platform_admin", False)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if getattr(request.user, "is_platform_admin", False):
            return qs
        tenant = getattr(request, "tenant", None) or getattr(request.user, "tenant", None)
        if tenant:
            return qs.filter(tenant=tenant)
        return qs.none()

    list_display = ("created_at", "tenant", "action", "actor", "target_repr")
    list_filter = ("tenant", "action", "created_at")
    search_fields = (
        "actor__email",
        "target_repr",
        "target_model",
        "target_pk",
        "path",
        "ip_address",
    )
    ordering = ("-created_at",)

    readonly_fields = (
        "tenant",
        "actor",
        "action",
        "target_model",
        "target_pk",
        "target_repr",
        "ip_address",
        "user_agent",
        "path",
        "method",
        "metadata",
        "created_at",
    )

    # Logs are immutable from admin
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    # Optional: only platform admin can delete (you can also return False always)
    def has_delete_permission(self, request, obj=None):
        return bool(getattr(request.user, "is_platform_admin", False))

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        # Platform admin sees all
        if getattr(request.user, "is_platform_admin", False):
            return qs

        # Tenant admin sees only own tenant
        tenant = getattr(request, "tenant", None) or getattr(request.user, "tenant", None)
        if tenant:
            return qs.filter(tenant=tenant)

        return qs.none()

    def get_list_filter(self, request):
        """
        Tenant admins should NOT even see a tenant filter,
        platform admins can filter by tenant.
        """
        if getattr(request.user, "is_platform_admin", False):
            return self.list_filter
        # hide tenant filter for tenant admins
        return tuple(x for x in self.list_filter if x != "tenant")

"""


def _session_user_id(session: Session):
    try:
        data = session.get_decoded()
        uid = data.get("_auth_user_id")
        return int(uid) if uid is not None else None
    except Exception:
        return None
"""

@admin.register(Session, site=platform_admin_site)
class PlatformSessionAdmin(admin.ModelAdmin):
    """
    Sessions menu will show grouped-by-user view by default.
    Also provides per-user session list + revoke.
    """
    # keep these so admin permissions & search still work if needed
    list_display = ("session_key", "expire_date")
    ordering = ("-expire_date",)
    search_fields = ("session_key",)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "user/<int:user_id>/",
                self.admin_site.admin_view(self.sessions_for_user_view),
                name="sessions_for_user",
            ),
            path(
                "user/<int:user_id>/revoke/",
                self.admin_site.admin_view(self.revoke_user_sessions_view),
                name="revoke_user_sessions",
            ),
        ]
        return custom + urls

    def changelist_view(self, request, extra_context=None):
        """
        Make Sessions menu open the grouped-by-user page.
        """
        return self.sessions_by_user_view(request)

    def sessions_by_user_view(self, request):
        now = timezone.now()

        counts = defaultdict(int)
        last_expiry = {}

        for s in Session.objects.filter(expire_date__gt=now).only("session_data", "expire_date"):
            uid = _session_user_id(s)
            if uid is None:
                continue
            counts[uid] += 1
            if uid not in last_expiry or s.expire_date > last_expiry[uid]:
                last_expiry[uid] = s.expire_date

        user_ids = list(counts.keys())
        users = CustomUser.objects.filter(id__in=user_ids).select_related("tenant")

        users_sorted = sorted(users, key=lambda u: counts.get(u.id, 0), reverse=True)

        rows = []
        for u in users_sorted:
            rows.append({
                "user": u,
                "tenant": getattr(u.tenant, "name", "-"),
                "count": counts.get(u.id, 0),
                "last_expiry": last_expiry.get(u.id),
                "view_url": reverse(f"{self.admin_site.name}:sessions_for_user", args=[u.id]),
                "revoke_url": reverse(f"{self.admin_site.name}:revoke_user_sessions", args=[u.id]),
            })

        context = {
            **self.admin_site.each_context(request),
            "title": "Active sessions (by user)",
            "rows": rows,
        }
        return render(request, "admin/sessions/session/by_user.html", context)

    def sessions_for_user_view(self, request, user_id):
        user = get_object_or_404(CustomUser, pk=user_id)
        now = timezone.now()

        sessions = []
        for s in Session.objects.filter(expire_date__gt=now).order_by("-expire_date"):
            if _session_user_id(s) == user.id:
                sessions.append(s)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Active sessions for {user.email}",
            "target_user": user,
            "sessions": sessions,
            "revoke_url": reverse(f"{self.admin_site.name}:revoke_user_sessions", args=[user.id]),
            "back_url": reverse(f"{self.admin_site.name}:sessions_session_changelist"),
        }
        return render(request, "admin/sessions/session/user_sessions.html", context)

    def revoke_user_sessions_view(self, request, user_id):
        user = get_object_or_404(CustomUser, pk=user_id)
        now = timezone.now()

        deleted = 0
        for s in Session.objects.filter(expire_date__gt=now):
            if _session_user_id(s) == user.id:
                s.delete()
                deleted += 1

        messages.success(request, f"Revoked {deleted} session(s) for {user.email}.")
        return redirect(reverse(f"{self.admin_site.name}:sessions_for_user", args=[user.id]))

    def has_add_permission(self, request):
        return False


@admin.register(RoleTemplate, site=platform_admin_site)
class RoleTemplateAdmin(admin.ModelAdmin):

    list_display = ("name", "description")

    filter_horizontal = ("permissions",)

    search_fields = ("name",)

    ordering = ("name",)

    # only platform admins should manage templates
    def has_module_permission(self, request):
        return request.user.is_platform_admin

    def has_view_permission(self, request, obj=None):
        return request.user.is_platform_admin

    def has_add_permission(self, request):
        return request.user.is_platform_admin

    def has_change_permission(self, request, obj=None):
            return request.user.is_platform_admin

    def has_delete_permission(self, request, obj=None):
        return request.user.is_platform_admin

