from django.contrib import admin
from django.utils import timezone

from core.admin_sites import tenant_admin_site  # ✅ tenant admin site (custom)
from customers.models import Customer, Kebele, Woreda


# Register your models here.
#@admin.register(Customer, site=tenant_admin_site)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "customer_no",
        "full_name",
        "phone",
        "customer_type",
        "is_active",
        "created_at",
    )

    search_fields = (
        "customer_no",
        "first_name",
        "last_name",
        "phone",
        "email",
        "woreda",
        "kebele",
    )
    list_filter = ("customer_type", "is_active", "created_at", "woreda", "kebele"  )

    readonly_fields = ("customer_no", "registered_by", "created_at", "updated_at", "updated_by")

    def save_model(self, request, obj, form, change):
        obj.tenant = request.tenant
        if obj.registered_by is None:
            obj.registered_by = request.user
            obj.created_at = timezone.now()
        else:
            obj.updated_by = request.user
            obj.updated_at = timezone.now()
            
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        return True

    def has_delete_permission(self, request, obj=None):
        return False  # soft delete only


@admin.register(Woreda, site=tenant_admin_site)
class WoredaAdmin(admin.ModelAdmin):

    list_display = ("name",)
    search_fields = ("name",)
    ordering = ("name",)
    # Optional: remove list_filter since filtering by name is redundant
    # list_filter = ("name",)

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
        return True
    def has_change_permission(self, request, obj = ...):
        return True
#tenant_admin_site.register(Woreda, WoredaAdmin)

@admin.register(Kebele, site=tenant_admin_site)
class KebeleAdmin(admin.ModelAdmin):

    list_display = ("name", "woreda")
    search_fields = ("name", "woreda__name")
    ordering = ("name",)
    # Optional: remove list_filter since filtering by name is redundant
    # list_filter = ("name",)

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
        return True
    def has_change_permission(self, request, obj = ...):
        return True
