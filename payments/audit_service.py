from django.utils import timezone

from tenant_utils.models_audit import AuditAction, AuditLog


def _log_event(
    *,
    action,
    actor=None,
    branch=None,
    target=None,
    metadata=None,
    request=None,
):
    """
    Internal audit logger.
    """

    AuditLog.objects.create(
        branch=branch,
        actor=actor,
        action=action,
        target_model=target.__class__.__name__ if target else "",
        target_pk=str(target.pk) if target else "",
        target_repr=str(target) if target else "",
        metadata=metadata or {},
        ip_address=request.META.get("REMOTE_ADDR") if request else None,
        user_agent=request.META.get("HTTP_USER_AGENT") if request else "",
        path=request.path if request else "",
        method=request.method if request else "",
        created_at=timezone.now(),
    )

def log_payment_created(payment, actor, request=None):
    _log_event(
        branch=payment.branch,
        actor=actor,
        action=AuditAction.PAYMENT_CREATED,
        target=payment,
        metadata={
            "amount": str(payment.amount_paid),
            "method": payment.payment_method,
            "source": payment.source,
            "session_id": payment.session_id,
            "bill": payment.bill.invoice_number,
        },
        request=request,
    )

def log_payment_completed(payment, actor, request=None):
    _log_event(
        branch=payment.branch,
        actor=actor,
        action=AuditAction.PAYMENT_COMPLETED,
        target=payment,
        metadata={
            "amount": str(payment.amount_paid),
            "method": payment.payment_method,
            "reference": payment.reference_number,
        },
        request=request,
    )

def log_payment_reversed(payment, actor, reason, request=None):
    _log_event(
        branch=payment.branch,
        actor=actor,
        action=AuditAction.PAYMENT_REVERSED,
        target=payment,
        metadata={
            "amount": str(payment.amount_paid),
            "reason": reason,
        },
        request=request,
    )

def log_session_opened(session, actor, request=None):
    _log_event(
        branch=session.branch,
        actor=actor,
        action=AuditAction.SESSION_OPENED,
        target=session,
        metadata={
            "session_type": session.session_type,
            "opening_balance": str(session.opening_balance),
        },
        request=request,
    )

def log_session_close_requested(session, actor, request=None):
    _log_event(
        branch=session.branch,
        actor=actor,
        action=AuditAction.SESSION_CLOSE_REQUESTED,
        target=session,
        request=request,
    )

def log_session_closed(session, supervisor, request=None):
    _log_event(
        branch=session.branch,
        actor=supervisor,
        action=AuditAction.SESSION_CLOSED,
        target=session,
        metadata={
            "closing_balance": str(session.closing_balance),
            "physical_cash": str(session.physical_cash),
            "difference": str(session.cash_difference),
        },
        request=request,
    )

def log_external_payment_received(external_payment, request=None):
    _log_event(
        #tenant=external_payment.tenant,
        branch=external_payment.bill.branch,
        actor=None,
        action=AuditAction.EXTERNAL_PAYMENT_RECEIVED,
        target=external_payment,
        metadata={
            "amount": str(external_payment.amount),
            "reference": external_payment.external_reference,
            "source": external_payment.source,
        },
        request=request,
    )

def log_external_payment_posted(external_payment, request=None):
    _log_event(
        #tenant=external_payment.tenant,
        branch=external_payment.bill.branch,
        actor=None,
        action=AuditAction.EXTERNAL_PAYMENT_POSTED,
        target=external_payment,
        metadata={
            "amount": str(external_payment.amount),
            "reference": external_payment.external_reference,
            "source": external_payment.source,
        },
        request=request,
    )

