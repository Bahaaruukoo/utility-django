import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_migrate, pre_delete
from django.dispatch import receiver

User = get_user_model()


# ------------------------------------------------------------------
# Protect SYSTEM user
# ------------------------------------------------------------------
@receiver(pre_delete, sender=User)
def protect_system_user(sender, instance, **kwargs):
    if getattr(instance, "username", None) == "system":
        raise Exception("SYSTEM user cannot be deleted")


# ------------------------------------------------------------------
# Create SYSTEM user
# ------------------------------------------------------------------
@receiver(post_migrate)
def create_system_user(sender, **kwargs):
    user, created = User.objects.get_or_create(
        username="system",
        defaults={
            "is_staff": False,
            "is_superuser": False,
            "is_active": True,
        },
    )

    if created:
        user.set_unusable_password()
        user.save()


# ------------------------------------------------------------------
# Session Browser Binding
# ------------------------------------------------------------------
@receiver(user_logged_in)
def create_session_binding(sender, request, user, **kwargs):
    """
    Generates a browser binding token after a successful login.

    The token is stored in the authenticated session.
    SessionMetaMiddleware will later write it into an HttpOnly cookie.
    """
    
    if request is None:
        return

    token = secrets.token_urlsafe(32)

    request.session["_binding_token"] = token

    # Flag telling SessionMetaMiddleware to send the cookie
    request.session["_set_binding_cookie"] = True