# core/admin_mixins.py
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import path
from django.utils.translation import gettext_lazy as _

from core.session.session_utils import (list_active_sessions_for_user,
                                        revoke_all_sessions_for_user)


class UserSessionAdminMixin:
    """
    Adds:
      - /<user_id>/sessions/ page
      - /<user_id>/revoke-sessions/ action
    """

    def get_urls(self):
        urls = super().get_urls()
        extra = [
            path(
                "<int:user_id>/sessions/",
                self.admin_site.admin_view(self.user_sessions_view),
                name="core_customuser_sessions",
            ),
            path(
                "<int:user_id>/revoke-sessions/",
                self.admin_site.admin_view(self.revoke_sessions_view),
                name="core_customuser_revoke_sessions",
            ),
        ]
        return extra + urls

    def _can_manage_user(self, request, user_obj) -> bool:
        # Default safety: platform admin can manage any user
        if getattr(request.user, "is_platform_admin", False):
            return True

        tenant = getattr(request, "tenant", None)
        return bool(tenant and getattr(user_obj, "tenant_id", None) == tenant.id)

    def user_sessions_view(self, request, user_id: int):
        user_obj = self.model.objects.filter(pk=user_id).first()
        if not user_obj:
            raise Http404("User not found")

        if not self._can_manage_user(request, user_obj):
            raise Http404("Not allowed")

        sessions = list_active_sessions_for_user(user_obj)

        context = dict(
            self.admin_site.each_context(request),
            title=_("Active sessions"),
            user_obj=user_obj,
            sessions=sessions,
        )
        return render(request, "admin/core/user_sessions.html", context)

    def revoke_sessions_view(self, request, user_id: int):
        user_obj = self.model.objects.filter(pk=user_id).first()
        if not user_obj:
            raise Http404("User not found")

        if not self._can_manage_user(request, user_obj):
            raise Http404("Not allowed")

        deleted = revoke_all_sessions_for_user(user_obj)
        messages.success(request, f"Revoked {deleted} session(s) for {user_obj.email}.")

        # go back to change page
        return redirect(f"../{user_id}/change/")
