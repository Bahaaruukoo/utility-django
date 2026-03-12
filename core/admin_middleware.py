"""
Middleware to protect tenant admin site from unauthorized access.
"""
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.shortcuts import redirect
from django.db import connection
from django.urls import resolve


class TenantAdminMiddleware:
    """
    Middleware that protects /admin_tenant/ URLs to ensure only:
    - Platform admins can access from public schema
    - Tenant admins can only access from their own tenant domain
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only check admin_tenant URLs
        if request.path.startswith('/admin_tenant/'):
            if request.user.is_authenticated:
                tenant = getattr(request, "tenant", None)
                
                # Platform admins can always access
                if request.user.is_platform_admin:
                    return self.get_response(request)
                
                # For tenant admins, they MUST be on their own tenant domain
                if not tenant:
                    # Tenant admins cannot access admin from public schema
                    messages.error(request, "Tenant admins can only access the admin site from their tenant domain.")
                    return redirect('home')
                
                # Verify tenant admin belongs to this specific tenant
                original_schema = connection.schema_name
                connection.set_schema_to_public()
                
                try:
                    if not hasattr(request.user, "tenant_memberships"):
                        messages.error(request, "You do not have access to this tenant admin site.")
                        return HttpResponseForbidden("You do not have access to this tenant admin site.")
                    
                    # Check if user is a member of this tenant
                    membership = request.user.tenant_memberships.filter(tenant_id=tenant.id).first()
                    if not membership:
                        messages.error(request, f"You do not have access to tenant '{tenant.name}'. You can only access your own tenant's admin site.")
                        return HttpResponseForbidden(f"You do not have access to tenant '{tenant.name}'.")
                    
                    # Check if user has TENANT_ADMIN role
                    if membership.role != 'TENANT_ADMIN':
                        messages.error(request, "You do not have permission to access this tenant admin site. Only tenant admins can access.")
                        return HttpResponseForbidden("You do not have permission to access this tenant admin site.")
                    
                    # User must also be staff
                    if not request.user.is_staff:
                        messages.error(request, "You must be a staff member to access the admin site.")
                        return HttpResponseForbidden("You must be a staff member to access the admin site.")
                finally:
                    # Restore original schema
                    if original_schema != 'public':
                        connection.set_tenant(tenant)

        return self.get_response(request)
