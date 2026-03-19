# tenant_utils/admin.py
from __future__ import annotations

import io

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import path
from django.utils import timezone
from django_tenants.utils import get_public_schema_name
from rangefilter.filters import DateRangeFilter
from reportlab.lib import colors, pagesizes
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

from core.admin_sites import tenant_admin_site
from core.models import CustomUser
from tenant_utils.forms import AuditExportForm
from tenant_utils.models import Branch, BranchMembership
from tenant_utils.models_audit import AuditAction, AuditLog

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def is_tenant_admin(request) -> bool:
    u = request.user
    return bool(
        u.is_authenticated
        and getattr(u, "is_staff", False)
        and not getattr(u, "is_platform_admin", False)
        and not is_branch_admin(request)  # treat branch-admin separately
    ) or bool(
        u.is_authenticated
        and getattr(u, "is_staff", False)
        and not getattr(u, "is_platform_admin", False)
        and getattr(u, "is_admin", False)  # treat branch-admin separately
    )


def is_branch_admin(request) -> bool:
    """
    Branch admin = user who has an active BranchMembership in the current tenant
    with is_branch_admin=True.
    """
    u = request.user
    if not u.is_authenticated:
        return False

    tenant = getattr(request, "tenant", None)
    branch = getattr(request, "branch", None)
    
     # 🚨 CRITICAL: do not query tenant tables in public schema
    if not tenant or connection.schema_name == get_public_schema_name():
        return False
    
    if not branch:
        return False
    
    member_to_branchs = BranchMembership.objects.filter(
        tenant=tenant,
        user=u,
        is_branch_admin=True,
        is_active=True,
    )
    if member_to_branchs:
        member_to_a_branch = member_to_branchs.first()
        return branch == member_to_a_branch.branch
    
    return False


def branch_admin_branch_ids(request) -> list[int]:
    """
    Returns branch IDs that this branch-admin controls.
    If you later allow a user to be admin of multiple branches, this still works.
    """
    u = request.user
    tenant = getattr(request, "tenant", None)
    if not u.is_authenticated or not tenant:
        return []

    return list(
        BranchMembership.objects.filter(
            tenant=tenant,
            user=u,
            is_branch_admin=True,
            is_active=True,
        ).values_list("branch_id", flat=True)
    )


def user_ids_in_branches(tenant, branch_ids: list[int]) -> list[int]:
    """
    Returns user IDs who belong to these branches (active memberships).
    """
    if not tenant or not branch_ids:
        return []
    return list(
        BranchMembership.objects.filter(
            tenant=tenant,
            branch_id__in=branch_ids,
            is_active=True,
        ).values_list("user_id", flat=True)
    )


# ------------------------------------------------------------
# Tenant-scoped base admin
# ------------------------------------------------------------

class TenantScopedAdminMixin(admin.ModelAdmin):
    """
    Tenant-scoped base admin:
    - Filters to request.tenant
    - Hides tenant field for tenant-side admins
    - Forces tenant on save
    - Prevents delete by default
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        tenant = getattr(request, "tenant", None)

        # (Optional) platform admin in tenant admin UI: still let them see
        if getattr(request.user, "is_platform_admin", False):
            return qs

        if tenant:
            return qs #.filter(tenant=tenant)

        return qs.none()

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        # Hide tenant field for anyone who is NOT platform admin
        if not getattr(request.user, "is_platform_admin", False):
            form.base_fields.pop("tenant", None)

        return form

    def save_model(self, request, obj, form, change):
        # Force tenant from request if model has tenant
        if not getattr(request.user, "is_platform_admin", False):
            if hasattr(obj, "tenant_id"):
                obj.tenant = getattr(request, "tenant", None)
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        return bool(
            getattr(request.user, "is_platform_admin", False)
            or is_tenant_admin(request)
            or is_branch_admin(request)
        )

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        # default: tenant admin or platform admin only
        return bool(getattr(request.user, "is_platform_admin", False) or is_tenant_admin(request))

    def has_change_permission(self, request, obj=None):
        return bool(getattr(request.user, "is_platform_admin", False) or is_tenant_admin(request))

    def has_delete_permission(self, request, obj=None):
        return False


# ============================================================
# Branch (tenant admins only)
# ============================================================

@admin.register(Branch, site=tenant_admin_site)
class BranchAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")
    ordering = ("name",)

    # Branch admins should not see/manage branches
    def has_module_permission(self, request):
        tenant = getattr(request, "tenant", None)
        if not tenant:
            return False
        if is_branch_admin(request):
            return False
        return bool(getattr(request.user, "is_platform_admin", False) or is_tenant_admin(request))

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        if is_branch_admin(request):
            return False
        return bool(getattr(request.user, "is_platform_admin", False) or is_tenant_admin(request))

    def has_change_permission(self, request, obj=None):
        if is_branch_admin(request):
            return False
        return bool(getattr(request.user, "is_platform_admin", False) or is_tenant_admin(request))


# ============================================================
# BranchMembership (tenant admins only)
# ============================================================

@admin.register(BranchMembership, site=tenant_admin_site)
class BranchMembershipAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("user", "branch", "is_branch_admin", "is_active")
    list_filter = ("branch", "is_branch_admin", "is_active")
    search_fields = ("user__email", "branch__code", "branch__name")

    # Branch admins should not see/manage memberships
    def has_module_permission(self, request):
        if is_branch_admin(request):
            return False
        return bool(getattr(request.user, "is_platform_admin", False) or is_tenant_admin(request))

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        if is_branch_admin(request):
            return False
        return bool(getattr(request.user, "is_platform_admin", False) or is_tenant_admin(request))

    def has_change_permission(self, request, obj=None):
        if is_branch_admin(request):
            return False
        return bool(getattr(request.user, "is_platform_admin", False) or is_tenant_admin(request))

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # tenant admins should only pick users/branches from same tenant
        if not getattr(request.user, "is_platform_admin", False):
            tenant = getattr(request, "tenant", None)
            if tenant and db_field.name == "user":
                kwargs["queryset"] = CustomUser.objects.filter(tenant=tenant)
            if tenant and db_field.name == "branch":
                kwargs["queryset"] = Branch.objects.filter(tenant=tenant)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        # Force tenant always (no dropdown)
        if not getattr(request.user, "is_platform_admin", False):
            obj.tenant = request.tenant
        super().save_model(request, obj, form, change)


# ============================================================
# CustomUser restriction INSIDE tenant admin site
# (Branch admin: only users in their branch; no add/delete)
# ============================================================

class TenantAdminUserRestrictionMixin:
    """
    Apply branch boundary to CustomUser list/change pages under tenant_admin_site.
    - Tenant admin: sees all tenant users
    - Branch admin: sees only users in branch(es) they admin
      and can view/change only (no add/delete)
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        tenant = getattr(request, "tenant", None)
        if not tenant:
            return qs.none()

        # always tenant-scoped here
        qs = qs.filter(tenant=tenant, is_platform_admin=False)

        if is_branch_admin(request):
            branch_ids = branch_admin_branch_ids(request)
            allowed_user_ids = user_ids_in_branches(tenant, branch_ids)
            return qs.filter(id__in=allowed_user_ids)

        # tenant admin sees all tenant users
        return qs

    def has_add_permission(self, request):
        # branch admin cannot create users
        if is_branch_admin(request):
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        # branch admin cannot delete users
        if is_branch_admin(request):
            return False
        return super().has_delete_permission(request, obj=obj)

    def has_change_permission(self, request, obj=None):
        # branch admin can only change users that are in their queryset
        if is_branch_admin(request) and obj is not None:
            tenant = getattr(request, "tenant", None)
            if not tenant or obj.tenant_id != tenant.id:
                return False

            branch_ids = branch_admin_branch_ids(request)
            allowed_user_ids = set(user_ids_in_branches(tenant, branch_ids))
            return obj.id in allowed_user_ids

        return super().has_change_permission(request, obj=obj)

    def has_view_permission(self, request, obj=None):
        if is_branch_admin(request) and obj is not None:
            return self.has_change_permission(request, obj=obj)
        return super().has_view_permission(request, obj=obj)


def _patch_tenant_admin_site_customuser():
    """
    Monkey-patch the CustomUser admin registered on tenant_admin_site
    by wrapping its class with TenantAdminUserRestrictionMixin.

    This avoids having to edit core tenant admin code.
    """
    key = CustomUser
    if key not in tenant_admin_site._registry:
        return

    current_admin = tenant_admin_site._registry[key]
    current_cls = current_admin.__class__

    # If already patched, skip
    if TenantAdminUserRestrictionMixin in current_cls.__mro__:
        return

    Wrapped = type(
        f"{current_cls.__name__}BranchRestricted",
        (TenantAdminUserRestrictionMixin, current_cls),
        {},
    )

    tenant_admin_site.unregister(CustomUser)
    tenant_admin_site.register(CustomUser, Wrapped)


_patch_tenant_admin_site_customuser()

# ============================================================
# AuditLog (tenant admins only, read-only)
# ============================================================
@admin.register(AuditLog, site=tenant_admin_site)
class AuditLogAdmin(TenantScopedAdminMixin, admin.ModelAdmin):

    list_display = ("branch", "action", "target_model", "actor", "created_at")
    search_fields = ("branch__code", "action", "actor__email", "target_repr")
    ordering = ("-created_at",)
    #change_list_template = "admin/tenant_utils/auditlog/change_list.html"
    list_filter = (
        ("created_at", DateRangeFilter),
        "action",
        "branch",
    )
    def has_module_permission(self, request):
        if is_branch_admin(request):
            return False
        return bool(getattr(request.user, "is_platform_admin", False) or is_tenant_admin(request))

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    # --------------------------------------------------
    # Remove action system
    # --------------------------------------------------

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "export-pdf/",
                self.admin_site.admin_view(self.export_pdf),
                name="auditlog_export_pdf",
            ),
        ]
        return custom_urls + urls

    # --------------------------------------------------
    # Add Export Button in Admin
    # --------------------------------------------------

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["export_pdf_url"] = "export-pdf/"
        return super().changelist_view(request, extra_context=extra_context)

    # --------------------------------------------------
    # EXPORT PDF VIEW
    # --------------------------------------------------

    def export_pdf(self, request):

        # Get filtered queryset exactly as admin does
        queryset = self.get_queryset(request)

        # Apply current filters manually
        changelist = self.get_changelist_instance(request)
        queryset = changelist.get_queryset(request)

        queryset = queryset.order_by("-created_at")

        MAX_ROWS = 3000
        total_records = queryset.count()

        if total_records > MAX_ROWS:
            self.message_user(
                request,
                f"Too many records ({total_records}). Max allowed is {MAX_ROWS}."
            )
            return redirect("..")

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        elements = []
        styles = getSampleStyleSheet()

        # --------------------------------------------------
        # HEADER
        # --------------------------------------------------

        elements.append(Paragraph("AUDIT LOG REPORT", styles["Heading1"]))
        elements.append(Spacer(1, 0.2 * inch))

        elements.append(Paragraph(
            f"Tenant: {request.tenant.name}",
            styles["Normal"]
        ))

        elements.append(Paragraph(
            f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')}",
            styles["Normal"]
        ))

        elements.append(Paragraph(
            f"Total Records: {total_records}",
            styles["Normal"]
        ))

        elements.append(Spacer(1, 0.3 * inch))

        # --------------------------------------------------
        # TABLE DATA (MORE FIELDS)
        # --------------------------------------------------

        data = [[
            "Date",
            "Branch",
            "Action",
            "Actor",
            "Target Model",
            "Target ID",
            "IP",
            "Method"
        ]]

        for log in queryset:
            data.append([
                log.created_at.strftime("%Y-%m-%d %H:%M"),
                str(log.branch or "-"),
                log.get_action_display(),
                getattr(log.actor, "email", "SYSTEM"),
                log.target_model or "-",
                log.target_pk or "-",
                log.ip_address or "-",
                log.method or "-",
            ])

        table = Table(data, repeatRows=1)

        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.black),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            
        ]))

        elements.append(table)

        # --------------------------------------------------
        # FOOTER + PAGE NUMBER + WATERMARK
        # --------------------------------------------------

        def add_page_number_and_watermark(canvas_obj, doc_obj):
            canvas_obj.saveState()

            # Page number
            canvas_obj.setFont("Helvetica", 8)
            canvas_obj.drawRightString(
                A4[0] - 40,
                20,
                f"Page {doc_obj.page}"
            )

            # Watermark
            canvas_obj.setFont("Helvetica", 60)
            canvas_obj.setFillColorRGB(0.9, 0.9, 0.9)
            canvas_obj.rotate(45)
            canvas_obj.drawCentredString(400, -100, "CONFIDENTIAL")

            canvas_obj.restoreState()

        doc.build(
            elements,
            onFirstPage=add_page_number_and_watermark,
            onLaterPages=add_page_number_and_watermark
        )

        pdf = buffer.getvalue()
        buffer.close()

        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="audit_logs_{timezone.now().date()}.pdf"'
        )
        response.write(pdf)

        return response

