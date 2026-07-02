# core/admin_sites.py
from django.contrib.admin import AdminSite
from django.shortcuts import redirect
from django.urls import reverse

from core.session.admin_sessions import AdminSessionViewsMixin


class PlatformAdminSite(AdminSessionViewsMixin, AdminSite):
    site_header = "Utility Platform Admin"
    site_title = "Platform Admin"
    index_title = ""

    def login(self, request, extra_context=None):
        return redirect(
            f"{reverse('account_login')}?next={request.get_full_path()}"
        )   

class TenantAdminSite(AdminSessionViewsMixin, AdminSite):
    site_header = "Tenant Admin"
    site_title = "Tenant Admin"
    index_title = ""


    def each_context(self, request):
        context = super().each_context(request)

        tenant = getattr(request, "tenant", None)
        branch = getattr(request, "branch", None)

        if branch:
            # Branch admin
            context["site_header"] = f"{branch.name.capitalize()} Branch Admin"
            context["site_title"] = f"{branch.name.capitalize()} Admin"
        elif tenant:
            # Tenant admin
            context["site_header"] = f"{tenant.name.capitalize()} Admin"
            context["site_title"] = f"{tenant.name.capitalize()} Admin"
        else:
            # Fallback (should rarely happen)
            context["site_header"] = "Admin"
            context["site_title"] = "Admin"

        return context
    
    def login(self, request, extra_context=None):
        return redirect(
            f"{reverse('account_login')}?next={request.get_full_path()}"
        )
    
class TenantDomainAdminSite(AdminSessionViewsMixin, AdminSite):
    site_header = "Domain Admin"
    site_title = "Domain Admin"
    index_title = "Domain Administration"

    def login(self, request, extra_context=None):
        return redirect(
            f"{reverse('account_login')}?next={request.get_full_path()}"
        )


platform_admin_site = PlatformAdminSite(name="platform_admin")
tenant_admin_site = TenantAdminSite(name="tenant_admin")
tenant_domain_admin_site = TenantDomainAdminSite(name="tenant_domain_admin")