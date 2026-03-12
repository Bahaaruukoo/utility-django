import logging

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils import timezone

from payments.models import CashierSession

logger = logging.getLogger("app")

"""
Run it automatically via cron or Celery beat at midnight:
    0 0 * * * python manage.py close_system_sessions
This ensures yesterday's SYSTEM sessions always close automatically.
"""

class Command(BaseCommand):
    help = "Close all open SYSTEM sessions before today"

    def handle(self, *args, **kwargs):

        logger.info("Starting system session auto-close job")

        today = timezone.now().date()

        sessions = CashierSession.objects.filter(
            session_type="SYSTEM",
            opened_at__date__lt=today,
            status="OPEN"
        )

        count = 0

        for session in sessions:

            payments = session.payments.filter(status="COMPLETED")

            total = payments.aggregate(
                total=Sum("amount_paid")
            )["total"] or 0

            session.closing_balance = total
            session.closed_at = timezone.now()
            session.status = "CLOSED"

            session.save(update_fields=[
                "closing_balance",
                "closed_at",
                "status"
            ])

            logger.info(
                f"System session closed session_id={session.id} total={total}"
            )

            count += 1

        logger.info(f"System session auto-close completed closed_count={count}")

        self.stdout.write(
            self.style.SUCCESS(f"Closed {count} system session(s).")
        )
