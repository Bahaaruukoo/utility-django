# core/admin_mixins.py
from django.contrib import admin


class BranchFilteredAdmin(admin.ModelAdmin):
    """
    For branch-scoped admin pages:
    - list shows only current branch
    - branch is not editable
    - save forces tenant+branch from request
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        tenant = getattr(request, "tenant", None)
        branch = getattr(request, "branch", None)

        if getattr(request.user, "is_platform_admin", False):
            return qs

        if tenant and branch:
            return qs.filter(tenant=tenant, branch=branch)

        return qs.none()

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # hide tenant/branch fields from branch admins
        form.base_fields.pop("tenant", None)
        form.base_fields.pop("branch", None)
        return form

    def save_model(self, request, obj, form, change):
        tenant = getattr(request, "tenant", None)
        branch = getattr(request, "branch", None)

        if tenant and hasattr(obj, "tenant_id"):
            obj.tenant = tenant
        if branch and hasattr(obj, "branch_id"):
            obj.branch = branch

        super().save_model(request, obj, form, change)