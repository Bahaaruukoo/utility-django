# services/email_service.py

import logging
from typing import List, Optional

from django.conf import settings
from django.core.mail import EmailMessage, send_mail

logger = logging.getLogger("app")


class EmailService:
    """
    Email service that works with console backend (dev)
    and real SMTP (prod) without changes.
    """

    def __init__(self, from_email: Optional[str] = None):
        self.from_email = from_email or settings.DEFAULT_FROM_EMAIL

    def send_simple_email(
        self,
        subject: str,
        message: str,
        recipient_list: List[str],
        fail_silently: bool = False,
    ) -> int:
        result = send_mail(
            subject=subject,
            message=message,
            from_email=self.from_email,
            recipient_list=recipient_list,
            fail_silently=fail_silently,
        )

        # Helpful debug log (since console backend prints raw email)
        logger.info(f"[EMAIL SENT - SIMPLE] To: {recipient_list} | Subject: {subject}")

        return result

    def send_html_email(
        self,
        subject: str,
        html_content: str,
        recipient_list: List[str],
        text_content: Optional[str] = None,
        fail_silently: bool = False,
    ) -> None:
        email = EmailMessage(
            subject=subject,
            body=text_content or "This is an HTML email.",
            from_email=self.from_email,
            to=recipient_list,
        )

        email.content_subtype = "html"
        email.body = html_content
        email.send(fail_silently=fail_silently)

        logger.info(f"[EMAIL SENT - HTML] To: {recipient_list} | Subject: {subject}")

    def send_email_with_attachments(
        self,
        subject: str,
        message: str,
        recipient_list: List[str],
        attachments: List[tuple],
        fail_silently: bool = False,
    ) -> None:
        email = EmailMessage(
            subject=subject,
            body=message,
            from_email=self.from_email,
            to=recipient_list,
        )

        for attachment in attachments:
            email.attach(*attachment)

        email.send(fail_silently=fail_silently)

        logger.info(f"[EMAIL SENT - ATTACHMENT] To: {recipient_list} | Subject: {subject}")