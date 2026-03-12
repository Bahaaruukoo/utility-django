import logging
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect
from django.utils import timezone

from bills.models import Bill, BillingSettings
from payments.audit_service import (log_external_payment_posted,
                                    log_external_payment_received)
from payments.models import (CashierSession, Payment, PaymentAllocation,
                             PaymentReversal)
from payments.receipt_service import generate_receipt
from tenant_utils.models_audit import AuditAction, AuditLog

logger = logging.getLogger("app")

@transaction.atomic
def pay_bill(
    *,
    request,
    tenant,
    branch,
    bill: Bill,
    session,
    received_by,
    payment_method,
    reference_number,
    source,
    amount,
):

    logger.info(f"Starting bill payment bill_id={bill.id}")

    # 🔒 Lock bill row
    bill = Bill.objects.select_for_update().get(pk=bill.pk)

    if bill.status == "VOIDED":
        logger.warning(f"Payment attempt on voided bill bill_id={bill.id}")
        raise ValueError("Cannot pay a voided bill.")

    if bill.status == "SOLD":
        logger.warning(f"Duplicate payment attempt bill_id={bill.id}")
        raise ValueError("Bill already paid.")

    late_fee = bill.calculate_late_fee()
    total_payment = bill.total_payable()

    if amount != total_payment:
        logger.warning(
            f"Incorrect payment amount bill_id={bill.id} expected={total_payment} received={amount}"
        )
        raise ValueError("Payment must equal full bill amount.")

    payment = Payment.objects.create(
        tenant=tenant,
        branch=branch,
        bill=bill,
        customer=bill.customer,
        session=session,
        amount_paid=total_payment,
        payment_method=payment_method,
        source=source,
        status="COMPLETED",
        reference_number=reference_number,
        received_by=received_by,
    )

    logger.info(f"Payment created payment_id={payment.id} amount={payment.amount_paid}")

    settings = BillingSettings.objects.get(tenant=bill.tenant)
    total_cost = bill.amount

    if settings.meter_rental_fee > 0:
        PaymentAllocation.objects.create(
            tenant=bill.tenant,
            branch=branch,
            payment=payment,
            component="METER_RENT",
            amount=settings.meter_rental_fee,
        )
        total_cost -= settings.meter_rental_fee

    if settings.service_charge_fee > 0:
        PaymentAllocation.objects.create(
            tenant=bill.tenant,
            branch=branch,
            payment=payment,
            component="SERVICE_FEE",
            amount=settings.service_charge_fee,
        )
        total_cost -= settings.service_charge_fee

    if settings.operation_charge_fee > 0:
        PaymentAllocation.objects.create(
            tenant=bill.tenant,
            branch=branch,
            payment=payment,
            component="OPERATION_FEE",
            amount=settings.operation_charge_fee,
        )
        total_cost -= settings.operation_charge_fee

    PaymentAllocation.objects.create(
        tenant=bill.tenant,
        branch=branch,
        payment=payment,
        component="WATER",
        amount=total_cost
    )

    if late_fee > 0:
        PaymentAllocation.objects.create(
            tenant=bill.tenant,
            branch=branch,
            payment=payment,
            component="PENALTY",
            amount=late_fee,
        )

    logger.info(f"Payment allocations completed payment_id={payment.id}")

    bill.status = "SOLD"
    bill.save(update_fields=["status"])

    logger.info(f"Bill marked as sold bill_id={bill.id}")

    AuditLog.objects.create(
        branch=branch,
        actor=received_by,
        action=AuditAction.PAYMENT_COMPLETED,
        target_model="Payment",
        target_pk=str(payment.pk),
        target_repr=str(payment),
        metadata={
            "amount": str(payment.amount_paid),
            "method": payment.payment_method,
            "session_id": payment.session_id,
            "bill": payment.bill.invoice_number,
        },
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT"),
        path=request.path,
        method=request.method,
    )

    receipt = generate_receipt(payment)

    logger.info(f"Receipt generated payment_id={payment.id} receipt_id={receipt.id}")

    return receipt


@transaction.atomic
def reverse_bill_payment(payment, user, reason):

    logger.info(f"Starting bill payment reversal payment_id={payment.id}")

    payment = Payment.objects.select_for_update().get(pk=payment.pk)

    if payment.status != "COMPLETED":
        logger.warning(f"Invalid reversal attempt payment_id={payment.id}")
        raise ValueError("Only completed payments can be reversed.")

    bill = payment.bill

    payment.status = "REVERSED"
    payment.save(update_fields=["status"])

    bill.status = "UNSOLD"
    bill.save(update_fields=["status"])

    PaymentReversal.objects.create(
        tenant=bill.tenant,
        payment=payment,
        reason=reason,
        reversed_by=user,
        authorized_by=user,
        approved_by=user,
    )

    logger.info(f"Payment reversed payment_id={payment.id}")


@transaction.atomic
def post_external_payment(external_payment):

    logger.info(f"Processing external payment external_id={external_payment.id}")

    if external_payment.posted:
        logger.warning(f"External payment already posted external_id={external_payment.id}")
        return

    log_external_payment_received(external_payment)

    bill = external_payment.bill

    if bill.status != "UNSOLD":
        logger.warning(f"External payment attempted on non-payable bill bill_id={bill.id}")
        raise ValueError("Bill is not payable.")

    if external_payment.amount != bill.amount:
        logger.warning(
            f"External payment amount mismatch bill_id={bill.id} expected={bill.amount} received={external_payment.amount}"
        )
        raise ValueError("External amount mismatch.")

    User = get_user_model()
    system_user = User.objects.get(email="system@yourdomain.com")

    session = get_or_create_system_session(
        tenant=bill.tenant,
        branch=bill.branch
    )

    payment = Payment.objects.create(
        tenant=bill.tenant,
        bill=bill,
        customer=bill.customer,
        session=session,
        amount_paid=external_payment.amount,
        payment_method=external_payment.source,
        source="EXTERNAL",
        status="COMPLETED",
        reference_number=external_payment.external_reference,
        received_by=system_user
    )

    logger.info(f"External payment recorded payment_id={payment.id}")

    bill.status = "SOLD"
    bill.save(update_fields=["status"])

    generate_receipt(payment)

    external_payment.posted = True
    external_payment.posted_at = timezone.now()
    external_payment.save(update_fields=["posted", "posted_at"])

    log_external_payment_posted(payment)

    logger.info(f"External payment posted external_id={external_payment.id}")

    return payment

@transaction.atomic
def get_or_create_system_session(tenant, branch):

    today = timezone.now().date()

    session = CashierSession.objects.select_for_update().filter(
        tenant=tenant,
        branch=branch,
        session_type="SYSTEM",
        opened_at__date=today
    ).first()

    if not session:
        session = CashierSession.objects.create(
            tenant=tenant,
            branch=branch,
            session_type="SYSTEM",
            cashier=None,
            opening_balance=0,
            status="OPEN"
        )

        logger.info(f"Using existing system session session_id={session.id}")
        return session
        
    logger.info(f"System session created session_id={session.id}")
    return session

def calculate_late_fee(bill):
    settings = BillingSettings.objects.get(tenant=bill.tenant)

    base_amount = bill.amount
    late_fee = Decimal("0.00")

    # --------------------------------------------------
    # 2️⃣ Calculate Late Fee
    # --------------------------------------------------

    if bill.is_overdue():
        late_fee = (
            base_amount
            * (settings.late_fee_rate / Decimal("100"))
        ).quantize(Decimal("0.01"))

    return late_fee

