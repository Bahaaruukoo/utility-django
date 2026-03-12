import logging

from django.db.models import Sum
from django.utils import timezone

from payments.models import CashierSession
from tenant_manager.models import Tenant
from tenant_utils.models import Branch

logger = logging.getLogger("app")

def open_daily_system_sessions():

    today = timezone.now().date()

    logger.info("Starting daily system session opening")

    tenants = Tenant.objects.all()

    for tenant in tenants:

        branches = Branch.objects.filter(
            tenant=tenant,
            is_active=True
        )

        for branch in branches:

            exists = CashierSession.objects.filter(
                tenant=tenant,
                branch=branch,
                session_type="SYSTEM",
                opened_at__date=today
            ).exists()

            if exists:
                logger.info(
                    f"System session already exists branch_id={branch.id}"
                )
                continue

            session = CashierSession.objects.create(
                tenant=tenant,
                branch=branch,
                session_type="SYSTEM",
                cashier=None,
                opening_balance=0,
                status="OPEN"
            )

            logger.info(
                f"System session opened session_id={session.id}"
            )

    logger.info("Daily system session opening completed")

def close_daily_system_sessions():

    today = timezone.now().date()

    logger.info("Starting daily system session closing")

    sessions = CashierSession.objects.filter(
        session_type="SYSTEM",
        opened_at__date=today,
        status="OPEN"
    )

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

    logger.info("Daily system session closing completed")