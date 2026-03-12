# core/adapters.py
from allauth.account.adapter import DefaultAccountAdapter
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import HttpResponseRedirect

from tenant_manager.models import Domain
from utility import settings


class NoPublicSignupAdapter(DefaultAccountAdapter):
    domain_name = settings.DOMAIN
    port_number = settings.PORT

    def is_open_for_signup(self, request):
        return False
    
    def get_login_redirect_url(self, request):
        """
        Redirect users to their tenant after login.
        If on tenant domain, stay there. If on public, redirect to tenant selection.
        """
        tenant = getattr(request, "tenant", None)
        print(".....adapter domain name....", self.domain_name)
        print(".....adapter tenant name....", tenant)
        # Already on tenant domain
        if tenant:
            return super().get_login_redirect_url(request)

        # Public schema
        if request.user.is_authenticated:
            connection.set_schema_to_public()

            if request.user.is_platform_admin:
                # Platform admins go to tenant selection
                from django.urls import reverse
                return reverse('select_tenant')

            # Normal tenant user: redirect to their tenant
            tenant = request.user.tenant
            if tenant:
                domain = tenant.domains.first()
                if domain:
                    scheme = 'http' if not request.is_secure() else 'https'
                    port = request.META.get('SERVER_PORT', '')
                    if port and port not in ['80', '443']:
                        return f"{scheme}://{domain.domain}.{self.domain_name}:{self.port_number}/"
                    else:
                        return f"{scheme}://{self.domain_name}:{self.port_number}/"

            # Fallback
            from django.urls import reverse
            return reverse('select_tenant')

        return super().get_login_redirect_url(request)
