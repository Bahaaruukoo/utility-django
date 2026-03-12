import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from bills.models import Bill
from payments.audit_service import log_payment_reversed
from payments.models import (CashierSession, Payment, PaymentAllocation,
                             PaymentReversal, PaymentReversalRequest)

logger = logging.getLogger("app")

@transaction.atomic
def reverse_manual_payment(
    *,
    payment_id,
    reason,
    reversed_by,
    supervisor,
    request=None,
):

    logger.info(f"Starting manual payment reversal payment_id={payment_id}")

    # --------------------------------------------------
    # 1️⃣ Lock Payment
    # --------------------------------------------------
    payment = (
        Payment.objects
        .select_for_update()
        .select_related("bill", "session")
        .get(id=payment_id)
    )

    if payment.status != "COMPLETED":
        logger.warning(f"Reverse attempt on non-completed payment payment_id={payment_id}")
        raise ValidationError("Only completed payments can be reversed.")

    if payment.is_reversal.exists():
        logger.warning(f"Duplicate reversal detected payment_id={payment_id}")
        raise ValidationError("Already reversed")

    # --------------------------------------------------
    # 2️⃣ Check Session State
    # --------------------------------------------------
    session = payment.session

    if session.status == "CLOSED":
        logger.warning(f"Reverse attempt from closed session payment_id={payment_id} session_id={session.id}")
        raise ValidationError(
            "Cannot reverse payment from a closed session."
        )

    # --------------------------------------------------
    # 3️⃣ Create Reversal Record
    # --------------------------------------------------
    PaymentReversal.objects.create(
        tenant=payment.tenant,
        payment=payment,
        reason=reason,
        reversed_by=reversed_by,
        authorized_by=supervisor,
        approved_by=supervisor,
    )

    logger.info(f"Reversal record created payment_id={payment_id}")

    return payment


def create_reversed_entry(request, original_payment):

    logger.info(f"Creating reversed payment entry payment_id={original_payment.id}")

    if original_payment.status != "COMPLETED":
        logger.warning(f"Invalid reversal attempt payment_id={original_payment.id}")
        raise ValidationError("Only completed payments can be reversed.")

    if original_payment.is_reversal:
        logger.warning(f"Payment already reversed payment_id={original_payment.id}")
        raise ValidationError("Already reversed")

    session = CashierSession.objects.filter(
        tenant=original_payment.tenant,
        cashier=request.user,
        closed_at__isnull=True
    ).first()

    if not session:
        logger.warning(f"No active cashier session for reversal payment_id={original_payment.id}")
        raise ValidationError("No active session available.")

    # --------------------------------------------------
    # Create Reversal Payment
    # --------------------------------------------------
    reversal = Payment.objects.create(
        tenant=original_payment.tenant,
        branch=original_payment.branch,
        bill=original_payment.bill,
        customer=original_payment.customer,
        session=session,
        amount_paid=-original_payment.amount_paid,
        payment_method=original_payment.payment_method,
        source="MANUAL",
        status="COMPLETED",
        is_reversal=True,
        reversal_of=original_payment,
        reference_number=f"REV-{original_payment.reference_number}",
        received_by=request.user
    )

    logger.info(f"Reversal payment created payment_id={reversal.id}")

    # --------------------------------------------------
    # Negative allocations
    # --------------------------------------------------
    for alloc in original_payment.allocations.all():
        PaymentAllocation.objects.create(
            tenant=alloc.tenant,
            payment=reversal,
            component=alloc.component,
            amount=-alloc.amount
        )

    logger.info(f"Reversal allocations created payment_id={reversal.id}")

    # --------------------------------------------------
    # Restore bill
    # --------------------------------------------------
    original_payment.bill.status = "UNSOLD"
    original_payment.bill.save(update_fields=["status"])

    original_payment.status = "REVERSED"
    original_payment.save()

    logger.info(f"Original payment marked reversed payment_id={original_payment.id}")

    PaymentReversalRequest.objects.filter(
        payment=original_payment,
        status="APPROVED"
    ).update(status="PROCESSED")

    # --------------------------------------------------
    # Void Receipt
    # --------------------------------------------------
    if hasattr(original_payment, "receipt"):
        receipt = original_payment.receipt
        receipt.is_void = True
        receipt.save(update_fields=["is_void"])

        logger.info(f"Receipt voided receipt_id={receipt.id}")

    # --------------------------------------------------
    # Audit Log
    # --------------------------------------------------
    log_payment_reversed(
        payment=original_payment,
        actor=request.user,
        reason=PaymentReversalRequest.objects.get(payment=original_payment).reason
    )

    logger.info(f"Payment reversal completed payment_id={original_payment.id}")

    return reversal