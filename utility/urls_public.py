# utility/urls_public.py
from django.urls import include, path

from core import views as core_views
from core.admin import platform_admin_site  # ✅ platform admin site (custom)
from core.admin_sites import platform_admin_site, tenant_admin_site
from portal.views import landing_page
from tenant_manager.admin import \
    tenant_domain_admin_site  # ✅ tenant domain admin site (custom)

urlpatterns = [
    # Home pages (public)
    path("", landing_page, name="landing"),
    #path("home/", core_views.home, name="home"),

    # ✅ Platform admin (PUBLIC ONLY)
    path("admin/", platform_admin_site.urls),
    path('admin_tenant/', tenant_domain_admin_site.urls),

    path("b/<slug:branch_code>/admin/", tenant_admin_site.urls), # Optional: branch-specific admin URLs
    path("b/<slug:branch_code>/", include("core.urls")),

    # Auth / allauth
    path("accounts/login/", core_views.TenantLoginView.as_view(), name="account_login"),
    path("accounts/", include("allauth.urls")),
    # Invitations / registration
    path("", include("core.urls")),
]
