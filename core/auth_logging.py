import logging

from django.contrib.auth.signals import (user_logged_in, user_logged_out,
                                         user_login_failed)
from django.dispatch import receiver

logger = logging.getLogger("app")


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    logger.info(
        f"User login successful user_id={user}"
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):

    if user:
        logger.info(
            f"User logout user_id={user}"
        )
    else:
        logger.info("Anonymous logout event")


@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request, **kwargs):

    username = credentials.get("username") or credentials.get("email")

    logger.warning(
        f"Login failed username={username}"
    )