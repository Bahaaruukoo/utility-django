import logging

from django.db import models, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from payments.models import CashierSession
from reports.services.session_report_service import generate_session_report

logger = logging.getLogger("app")

@transaction.atomic
def open_cashier_session(*, tenant, branch, cashier, opening_balance):

    logger.info("Opening cashier session")

    existing = CashierSession.objects.filter(
        tenant=tenant,
        branch=branch,
        cashier=cashier,
        closed_at__isnull=True
    ).select_for_update().first()

    if existing:
        logger.warning(
            f"Open session already exists session_id={existing.id}"
        )
        raise ValueError("You already have an open session.")

    session = CashierSession.objects.create(
        tenant=tenant,
        branch=branch,
        cashier=cashier,
        opening_balance=opening_balance,
        status="OPEN"
    )

    logger.info(
        f"Cashier session opened session_id={session.id} opening_balance={opening_balance}"
    )

    return session

def get_active_session(tenant, branch, cashier):

    session = CashierSession.objects.filter(
        tenant=tenant,
        branch=branch,
        cashier=cashier,
        status="OPEN",
        closed_at__isnull=True
    ).first()

    if session:
        logger.info(f"Active session found session_id={session.id}")
    else:
        logger.info("No active cashier session found")

    return session

@transaction.atomic
def request_session_close(session, physical_cash):

    logger.info(f"Session close requested session_id={session.id}")

    if session.status != "OPEN":
        logger.warning(
            f"Invalid close request session_id={session.id} status={session.status}"
        )
        raise ValueError("Session is not open.")

    payments = session.payments.filter(status__in=["COMPLETED", "REVERSED"])

    total_cash = payments.filter(
        payment_method="CASH"
    ).aggregate(total=Sum("amount_paid"))["total"] or 0

    difference = physical_cash - total_cash

    if difference != 0:
        logger.warning(
            f"Cash mismatch session_id={session.id} expected={total_cash} physical={physical_cash}"
        )
        raise ValueError("Cash mismatch. Cannot close session.")

    session.closing_balance = total_cash
    session.physical_cash = physical_cash
    session.cash_difference = difference
    session.status = "PENDING"
    session.closed_at = timezone.now()

    session.save()

    logger.info(
        f"Session submitted for approval session_id={session.id} closing_balance={total_cash}"
    )

    return session

@transaction.atomic
def approve_session_close(session, supervisor):

    logger.info(f"Approving session close session_id={session.id}")

    if session.status != "PENDING":
        logger.warning(
            f"Invalid approval attempt session_id={session.id} status={session.status}"
        )
        raise ValueError("Session not pending approval.")

    session.status = "CLOSED"
    session.approved_by = supervisor
    session.approved_at = timezone.now()

    session.save()

    logger.info(f"Session closed session_id={session.id}")
    
    generate_session_report(session, session.cashier )

    return session

