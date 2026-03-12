# core/audit.py
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Optional

from django.http import HttpRequest, HttpResponse
from django.utils.timezone import now

from core.models_audit import AuditLog


def _find_request(args, kwargs) -> HttpRequest | None:
    # common patterns:
    # - function: (request, ...)
    # - method: (self, request, ...)
    req = kwargs.get("request")
    if req is not None:
        return req
    for a in args:
        if isinstance(a, HttpRequest):
            return a
    return None


def log_audit(
    *,
    request: HttpRequest,
    action: str,
    target: Any = None,
    metadata: Optional[dict] = None,
    tenant=None,
    actor=None,
) -> None:
    user = actor if actor is not None else getattr(request, "user", None)

    # tenant priority:
    # 1) explicit tenant passed in
    # 2) target.tenant (if exists)
    # 3) request.tenant
    # 4) user.tenant
    tenant_obj = tenant
    if tenant_obj is None and target is not None and hasattr(target, "tenant"):
        tenant_obj = getattr(target, "tenant", None)
    if tenant_obj is None:
        tenant_obj = getattr(request, "tenant", None) or getattr(user, "tenant", None)

    # if still None, we cannot create tenant-scoped log
    if tenant_obj is None:
        return

    target_model = ""
    target_pk = ""
    target_repr = ""

    if target is not None:
        target_model = target.__class__.__name__
        target_pk = str(getattr(target, "pk", "") or "")
        target_repr = str(target)[:255]

    AuditLog.objects.create(
        tenant=tenant_obj,
        actor=user if getattr(user, "is_authenticated", False) else None,
        action=action,
        target_model=target_model,
        target_pk=target_pk,
        target_repr=target_repr,
        ip_address=(request.META.get("REMOTE_ADDR") or None),
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:2000],
        path=(request.path or "")[:512],
        method=(request.method or "")[:16],
        metadata=metadata or {},
        created_at=now(),
    )


def audit(
    action: str,
    *,
    tenant_getter: Callable[..., Any] | None = None,
    target_getter: Callable[..., Any] | None = None,
    metadata_getter: Callable[..., dict] | None = None,
):
    """
    Works for both function views and bound methods.

    tenant_getter: optional; if request.tenant is None (public schema) you can provide tenant from args.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            response: HttpResponse = func(*args, **kwargs)

            request = _find_request(args, kwargs)
            if request is None:
                return response

            tenant = tenant_getter(*args, **kwargs) if tenant_getter else None
            target = target_getter(*args, **kwargs) if target_getter else None
            metadata = metadata_getter(*args, **kwargs) if metadata_getter else None

            log_audit(
                request=request,
                action=action,
                tenant=tenant,
                target=target,
                metadata=metadata,
            )
            return response
        return wrapper
    return decorator
