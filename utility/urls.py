# utility/urls.py
from django.urls import include, path

from core import views as core_views
from core.admin import platform_admin_site  # ✅ platform admin site (custom)
from core.admin import tenant_admin_site  # ✅ tenant admin site (custom)
from tenant_manager.admin import tenant_domain_admin_site
from tenant_utils.views import \
    select_branch  # ✅ tenant domain admin site (custom)

urlpatterns = [
    # Tenant home pages
    path("", core_views.home, name="home"),

    path("b/<slug:branch_code>/", select_branch, name="select_branch"),
    # ✅ Tenant admin (TENANT DOMAINS ONLY)
    path("admin/", tenant_admin_site.urls),
    
    #path("b/<slug:branch_code>/admin/", tenant_domain_admin_site.urls),
    # Auth / allauth
    path("accounts/login/", core_views.TenantLoginView.as_view(), name="account_login"),
    path("accounts/profile/", core_views.profile_view, name="profile"),
    path("profile/edit/", core_views.profile_edit, name="profile_edit"),
    path("accounts/dashboard/", core_views.account_dashboard, name="account_dashboard"),
    path("accounts/", include("allauth.urls")),

    path("api/", include("tenant_utils.api.urls")),
    # Invitations / registration
    path("", include("core.urls")),

]
