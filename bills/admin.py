from django.contrib import admin

from bills.models import BillingSettings, BlockRate
from core.admin_sites import tenant_admin_site  # ✅ tenant admin site (custom)


@admin.register(BlockRate, site=tenant_admin_site)
class BlockRateAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "start_unit",
        "end_unit",
        "RES",
        "COM",
        "GOV",
        "PUB",
        "IND",
    )

    search_fields = ("name",)
    ordering = ("start_unit",)

    # Prevent tenant editing in admin form
    readonly_fields = ("tenant",)
    
    def get_queryset(self, request):
        """
        Ensure only current tenant data is shown.
        """
        qs = super().get_queryset(request)

        if hasattr(request, "tenant"):
            return qs.filter(tenant=request.tenant)
        return qs.none()

    def save_model(self, request, obj, form, change):
        """
        Automatically attach tenant.
        """
        if not change:
            obj.tenant = request.tenant

        super().save_model(request, obj, form, change)
    
    def has_module_permission(self, request):
        return True
    
    def has_delete_permission(self, request, obj=None):
        """
        Disable hard delete.
        """
        return False

    def has_add_permission(self, request):
        """
        Prevent adding new blocks from admin.
        """
        return False

    def has_change_permission(self, request, obj=None):
        
        # Branch admin = read-only
        if getattr(request.user, "is_branch_admin", False):
            return False

        if obj and obj.tenant != request.tenant:
            return False
        return True

    def has_view_permission(self, request, obj=None):
        """
        Allow viewing only within tenant.
        """
        if obj and obj.tenant != request.tenant:
            return False
        return True

@admin.register(BillingSettings, site=tenant_admin_site)
class BillingSettingsAdmin(admin.ModelAdmin):

    list_display = ("late_fee_rate", "meter_rental_fee", "billing_cycle_days", 
                    "bill_overdue_in_days", "service_charge_fee", 
                    "operation_charge_fee", "manual_bill_generation", 
                    "bill_generation_date")
    #search_fields = ("name",)
    #ordering = ("name",)

    def get_queryset(self, request):
        """
        Ensure only current tenant data is shown.
        """
        qs = super().get_queryset(request)
        return qs.filter(tenant=request.tenant)

    def save_model(self, request, obj, form, change):
        """
        Automatically attach tenant and user.
        """
        if not change:  # Only when creating
            obj.tenant = request.tenant

        if hasattr(obj, "registered_by"):
            obj.registered_by = request.user

        super().save_model(request, obj, form, change)
    
    def has_module_permission(self, request):
        return True
    
    def has_delete_permission(self, request, obj=None):
        """
        Disable hard delete.
        """
        return False
    def has_view_permission(self, request, obj = ...):
        return True
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        # Branch admin = read-only

        if getattr(request, "is_branch_admin", False):
            return False
        if getattr(request, "is_admin", False):
            return True
        
        if obj and obj.tenant != request.tenant:
            return False
        
        return True

def is_tenant_admin(request) -> bool:
    u = request.user
    return bool(
        u.is_authenticated
        and getattr(u, "is_staff", False)
        and not getattr(u, "is_platform_admin", False)
        #and not is_branch_admin(request)  # treat branch-admin separately
    ) or bool(
        u.is_authenticated
        and getattr(u, "is_staff", False)
        and not getattr(u, "is_platform_admin", False)
        and getattr(u, "is_admin", False)  # treat branch-admin separately
    )
