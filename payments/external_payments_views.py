import json
import logging

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from bills.models import Bill
from payments.models import CashierSession, ExternalPayment
from payments.payment_service import post_external_payment

logger = logging.getLogger("app")


@csrf_exempt
@transaction.atomic
def external_payment_webhook(request):

    logger.info("External payment webhook received")

    if request.method != "POST":
        logger.warning("Webhook called with invalid method")
        return JsonResponse({"error": "Invalid method"}, status=405)

    signature = request.headers.get("X-SIGNATURE")

    '''
    if not verify_signature(signature, request.body):
        logger.warning("Webhook signature verification failed")
        return JsonResponse({"error": "Invalid signature"}, status=403)
    '''

    try:
        data = json.loads(request.body)

        invoice_number = data.get("invoice_number")
        amount = data.get("amount")
        external_reference = data.get("reference")
        source = data.get("source")  # BANK / MOBILE

        if not all([invoice_number, amount, external_reference, source]):
            logger.warning("Webhook missing required fields")
            return JsonResponse({"error": "Missing fields"}, status=400)

        logger.info(
            f"Webhook payload parsed invoice={invoice_number} reference={external_reference} amount={amount}"
        )

        # 1️⃣ Locate bill
        bill = Bill.objects.select_for_update().get(
            invoice_number=invoice_number,
            status="UNSOLD"
        )

        logger.info(f"Bill located bill_id={bill.id}")

        # 2️⃣ Create ExternalPayment record
        external_payment = ExternalPayment.objects.select_for_update().filter(
            tenant=bill.tenant,
            external_reference=external_reference
        ).first()

        if not external_payment:

            external_payment = ExternalPayment.objects.create(
                tenant=bill.tenant,
                bill=bill,
                amount=amount,
                source=source,
                external_reference=external_reference,
                received_at=timezone.now(),
                posted=False,
            )

            logger.info(
                f"External payment record created external_id={external_payment.id} reference={external_reference}"
            )

        else:

            logger.info(
                f"External payment record reused external_id={external_payment.id} reference={external_reference}"
            )

       
        # 3️⃣ Idempotency check
        if external_payment.posted:
            logger.info(
                f"Webhook already processed reference={external_reference}"
            )
            return JsonResponse({"status": "already_processed"})

        # 4️⃣ Process payment
        payment = post_external_payment(external_payment)

        logger.info(
            f"External payment processed payment_id={payment.id} reference={external_reference}"
        )

        return JsonResponse({
            "status": "success",
            "receipt": payment.receipt.receipt_number
        })

    except Bill.DoesNotExist:
        logger.warning(
            f"Webhook bill not found invoice={invoice_number}"
        )
        return JsonResponse(
            {"error": "Bill not found or already paid"},
            status=404
        )

    except json.JSONDecodeError:
        logger.warning("Webhook invalid JSON payload")
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    except Exception as e:
        logger.error(f"Webhook processing failed error={str(e)}")
        return JsonResponse({"error": "Processing failed"}, status=400)