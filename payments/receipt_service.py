import hashlib
import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from payments.models import Receipt

logger = logging.getLogger("app")


@transaction.atomic
def generate_receipt(payment):

    logger.info(f"Generating receipt for payment_id={payment.id}")

    tenant = payment.tenant

    # Prevent duplicate receipt
    if hasattr(payment, "receipt"):
        logger.info(f"Receipt already exists payment_id={payment.id} receipt_id={payment.receipt.id}")
        return payment.receipt

    # Lock receipt table rows for this tenant
    last_number = (
        Receipt.objects
        .select_for_update()
        .filter(tenant=tenant)
        .aggregate(max_number=Max("receipt_number"))
    )["max_number"]

    if last_number:
        last_seq = int(last_number.split("-")[-1])
        next_seq = last_seq + 1
    else:
        next_seq = 1

    receipt_number = f"RCPT-{timezone.now().year}-{next_seq:07d}"
    logger.info(f"Next receipt number generated payment_id={payment.id} receipt_number={receipt_number}")

    # Create deterministic hash
    raw_string = (
        f"{receipt_number}|"
        f"{payment.bill.invoice_number}|"
        f"{payment.amount_paid}|"
        f"{payment.payment_date}|"
        f"{payment.customer_id}|"
        f"{payment.tenant_id}|"
        f"{settings.SECRET_KEY}"
    )

    signature = hashlib.sha256(raw_string.encode()).hexdigest()
    logger.info(f"Signature created for receipt_#={receipt_number} payment_id={payment.id}")

    receipt = Receipt.objects.create(
        tenant=payment.tenant,
        payment=payment,
        receipt_number=receipt_number,
        signature_hash=signature
    )

    logger.info(f"Receipt created receipt_id={receipt.id} payment_id={payment.id}")

    return receipt