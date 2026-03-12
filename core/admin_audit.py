from django.contrib import admin

from core.models_audit import AuditLog


#@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
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
