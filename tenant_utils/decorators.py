import logging
from functools import wraps

from django.core.exceptions import PermissionDenied

logger = logging.getLogger("app")

def permission(permissions):
    """
        @permission("orders.create_order")
        def create_order(request):
    """
    if isinstance(permissions, str):
        permissions = [permissions]

    def decorator(view_func):

        @wraps(view_func)
        def wrapper(request, *args, **kwargs):

            user = request.user

            if not user.is_authenticated:                
                logger.warning(f"Authentication required")
                raise PermissionDenied("Authentication required")

            # platform admin bypass
            if user.is_platform_admin:
                return view_func(request, *args, **kwargs)

            # tenant safety
            request_tenant = getattr(request, "tenant", None)

            if request_tenant and user.tenant_id != request_tenant.id:
                logger.warning(f"Cross tenant access denied")
                raise PermissionDenied("Cross tenant access denied")

            # branch check
            if not user.is_branch_admin:
                user_branch = request.branch # getattr(user, "branch_id", None)

                if user_branch is None:
                    logger.warning(f"Branch not found. User is not part of a branch")
                    raise PermissionDenied("Branch not assigned")
            #print(request.user.get_all_permissions())
            # permission check
            for perm in permissions:
                if user.has_perm(perm):
                    return view_func(request, *args, **kwargs)
            
            logger.warning(f"Missing permission: {perm}")
            raise PermissionDenied(f"Missing permission: {perm}")
        return wrapper

    return decorator