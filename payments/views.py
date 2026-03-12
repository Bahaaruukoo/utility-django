import hashlib
import logging
import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from bills.models import Bill, BillingSettings
from customers.models import Meter
from payments.audit_service import (log_session_close_requested,
                                    log_session_closed, log_session_opened)
from payments.cashier_service import (approve_session_close,
                                      get_active_session, open_cashier_session,
                                      request_session_close)
from payments.forms import PaymentReversalForm
from payments.models import (CashierSession, Payment, PaymentReversalRequest,
                             Receipt)
from payments.payment_service import pay_bill
from payments.services.reversal_service import (create_reversed_entry,
                                                reverse_manual_payment)
from tenant_utils.decorators import *

logger = logging.getLogger("app")

@login_required
@require_POST
@permission("payments.add_payment")
def pay_bill_view(request, bill_id):  # cash payment processing

    tenant = request.tenant
    branch = request.branch
    user = request.user

    logger.info(f"Payment attempt for bill {bill_id}")

    bill = get_object_or_404(
        Bill,
        id=bill_id,
        tenant=tenant,
        branch=branch
    )

    raw_amount = request.POST.get("amount", "").replace(",", "").strip()

    try:
        amount = Decimal(raw_amount)

    except InvalidOperation:

        logger.warning(
            f"Invalid payment amount '{raw_amount}' "
        )

        messages.error(request, "Amount must be a number.")
        q = request.POST.get("q")
        return redirect(f"{reverse('bill_search')}?q={q}")

    payment_method = "CASH"
    reference_num = f"{uuid.uuid4().hex[:12].upper()}"

    # Find open cashier session
    session = CashierSession.objects.filter(
        tenant=tenant,
        cashier=user,
        closed_at__isnull=True
    ).first()

    if not session:

        logger.warning(
            f"No open cashier session"
        )

        messages.error(request, "No open cashier session.")
        q = request.POST.get("q")

        return redirect(f"{reverse('bill_search')}?q={q}")

    try:

        receipt = pay_bill(
            request=request,
            tenant=tenant,
            branch=branch,
            bill=bill,
            session=session,
            received_by=user,
            payment_method=payment_method,
            reference_number=reference_num,
            source="MANUAL",
            amount=amount,
        )

        logger.info(
            f"Bill {bill.id} paid successfully receipt={receipt.id} amount={amount}"
        )

        messages.success(request, "Bill paid successfully.")

        return redirect("print_receipt", receipt_id=receipt.id)

    except IntegrityError:

        logger.warning(
            f"Duplicate payment attempt for bill {bill.id}"
        )

        messages.error(request, "This bill has already been paid.")

        q = request.POST.get("q")

        return redirect(f"{reverse('bill_search')}?q={q}")

    except Exception as e:

        logger.error(
            f"Payment failure bill={bill.id} error={str(e)}"
        )

        messages.error(request, str(e))

    return redirect("bill-detail", pk=bill.id)

@login_required
@permission(["payments.view_payment","bills.view_bill"])
def bill_detail_view(request, bill_id):

    tenant = request.tenant
    branch = request.branch
    user = request.user

    logger.info(f"User {user} requested bill detail bill_id={bill_id}")

    try:

        bill = get_object_or_404(
            Bill.objects.select_related("customer", "meter"),
            id=bill_id,
            tenant=tenant,
            branch=branch
        )

    except Exception:

        logger.warning(
            f"Bill access failed bill_id={bill_id} user={user} tenant={tenant}"
        )

        return render(request, "payments/dashboard.html", {})

    '''payment = Payment.objects.filter(
        bill=bill,
        status="COMPLETED"
    ).first()'''

    context = {
        "bill": bill,
        "late_fee": bill.calculate_late_fee(),
        "total_payable": bill.total_payable(),
    }

    return render(request, "bills/bill_detail.html", context)

@login_required
@permission(["payments.view_payment","bills.view_bill"])
def unpaid_bills_view(request):
    tenant = request.tenant
    branch = request.branch
    user = request.user

    logger.info(f"Unpaid bills view accessed user={user} tenant={tenant} branch={branch}")

    bills = Bill.objects.filter(
        tenant=tenant,
        branch=branch,
        status="UNSOLD"
    ).select_related("customer", "meter")

    logger.info(
        f"Fetched unpaid bills user={user} tenant={tenant} branch={branch} count={bills.count()}"
    )

    return render(request, "bills/unpaid_bills.html", {"bills": bills})


@login_required
@require_POST
@permission("payments.add_payment")
def reverse_payment_view(request, payment_id):
    tenant = request.tenant
    branch = request.branch
    user = request.user

    logger.info(
        f"Payment reversal attempt payment_id={payment_id} user={user} tenant={tenant} branch={branch}"
    )

    payment = get_object_or_404(
        Payment,
        id=payment_id,
        tenant=tenant,
        branch=branch,
        status="COMPLETED"
    )

    try:
        create_reversed_entry(request, payment)

        logger.info(
            f"Payment reversed successfully payment_id={payment.id} bill_id={payment.bill.id} user={user}"
        )

        messages.success(request, "Payment reversed.")

    except Exception as e:

        logger.error(
            f"Payment reversal failed payment_id={payment_id} user={user} error={str(e)}"
        )

        messages.error(request, str(e))

    return redirect("bill-detail", pk=payment.bill.id)


@login_required
@require_POST
@permission("payments.add_cashiersession")
def open_session_view(request):
    tenant = request.tenant
    branch = request.branch
    user = request.user
    opening_balance = Decimal(request.POST.get("opening_balance"))

    logger.info(
        f"Cashier session open attempt opening_balance={opening_balance}"
    )

    try:
        session = open_cashier_session(
            tenant=tenant,
            branch=branch,
            cashier=user,
            opening_balance=opening_balance
        )

        if session:
            log_session_opened(session, user, request)

            logger.info(
                f"Cashier session opened session_id={session.id} user={user} tenant={tenant} branch={branch}"
            )

        messages.success(request, "Session opened.")

    except Exception as e:

        logger.error(
            f"Failed to open cashier session user={user} tenant={tenant} branch={branch} error={str(e)}"
        )

        messages.error(request, str(e))

    return redirect("cashier_dashboard")


@login_required
@require_POST
@permission("payments.change_cashiersession")
def request_close_view(request):
    tenant = request.tenant
    user = request.user
    branch = request.branch

    logger.info(
        f"Session close request attempt "
    )

    session = get_active_session(tenant, branch, user)

    if not session:
        logger.warning(
            f"No active cashier session for close request"
        )
        messages.error(request, "No active session.")
        return redirect("cashier_dashboard")

    #check if there is an initiated payment reverse in this session
    reverse_request = PaymentReversalRequest.objects.filter(
                    tenant=tenant,
                    requested_by=user,
                    status__in=["PENDING", "APPROVED"]
                )
    if reverse_request:
        messages.warning(request, "You have payment reversal in progress.")
        return redirect("cashier_dashboard")
    
    try:
        physical_cash = Decimal(request.POST.get("physical_cash"))

        session_ = request_session_close(session, physical_cash)

        log_session_close_requested(session_, user, request)

        logger.info(
            f"Session close requested session_id={session_.id} physical_cash={physical_cash}"
        )

        messages.success(request, "Session submitted for approval.")
        return redirect("cashier_dashboard")

    except Exception as e:
        logger.error(
            f"Session close request failed error={str(e)}"
        )
        messages.error(request, str(e))
        return redirect("cashier_dashboard")
    
@login_required
@require_POST
@permission("payments.change_cashiersession")
def approve_close_view(request, session_id):
    tenant = request.tenant
    branch = request.branch
    supervisor = request.user

    logger.info(
        f"Session close approval attempt session_id={session_id} supervisor={supervisor} tenant={tenant} branch={branch}"
    )

    session = get_object_or_404(
        CashierSession,
        id=session_id,
        tenant=tenant,
        branch=branch,
        status="PENDING"
    )

    try:
        session_ = approve_session_close(session, supervisor)

        log_session_closed(session_, supervisor, request)

        logger.info(
            f"Session closed session_id={session_.id} supervisor={supervisor} tenant={tenant} branch={branch}"
        )

        messages.success(request, "Session approved.")

    except Exception as e:

        logger.error(
            f"Session close approval failed session_id={session_id} supervisor={supervisor} error={str(e)}"
        )

        messages.error(request, str(e))

    return redirect("pending_sessions")

@login_required
@permission("payments.add_cashiersession")
def cashier_dashboard(request):
    tenant = request.tenant
    branch = request.branch
    user = request.user

    logger.info(f"Cashier dashboard accessed" )

    try:
        session = get_active_session(tenant, branch, user)

        payments = []
        total = 0

        if session:
            payments = session.payments.filter(status__in=["COMPLETED", "REVERSED"])

            total = payments.aggregate(
                total=Sum("amount_paid")
            )["total"] or 0

            logger.info(
                f"Cashier session active session_id={session.id} payments_count={payments.count()} total={total}"
            )
        else:
            logger.warning(
                f"No active cashier session "
            )

    except Exception as e:
        logger.error(
            f"Cashier dashboard error={str(e)}"
        )
        return render(request, "payments/cashier/dashboard.html")

    return render(request, "payments/cashier/dashboard.html", {
        "session": session,
        "payments": payments,
        "total": total
    })

def is_supervisor(user):
    return user.is_admin or user.is_platform_admin


@login_required
#@user_passes_test(is_supervisor)
@permission("payments.view_paymentreversal")
def supervisor_dashboard_view(request):
    
    context = {
        "message": "Dashboard Coming Soon"
    }

    return render(request, "supervisor/supervisor_dashboard.html", context)

@login_required
#@user_passes_test(is_supervisor)
@permission("payments.view_paymentreversal")
def pending_sessions_view(request):
    tenant = request.tenant
    branch = request.branch
    user = request.user

    logger.info(
        f"Pending sessions view accessed"
    )

    sessions = CashierSession.objects.select_related(
        "cashier"
    ).filter(
        tenant=tenant,
        branch=branch,
        status="PENDING"
    )

    logger.info(
        f"Fetched pending sessions, count={sessions.count()}"
    )

    context = {
        "sessions": sessions
    }

    return render(request, "supervisor/pending_sessions.html", context)

@login_required
#@user_passes_test(is_supervisor)
@permission("payments.change_cashiersession")
def session_approval_view(request, session_id):
    tenant = request.tenant
    branch = request.branch
    user = request.user

    logger.info(
        f"Session approval view accessed session_id={session_id}"
    )

    session = get_object_or_404(
        CashierSession,
        id=session_id,
        tenant=tenant,
        branch=branch,
        status="PENDING"
    )

    payments = session.payments.filter(status__in=["COMPLETED", "REVERSED"])

    total_cash = payments.filter(payment_method="CASH").aggregate(
        total=Sum("amount_paid")
    )["total"] or 0

    total_bank = payments.filter(payment_method="BANK").aggregate(
        total=Sum("amount_paid")
    )["total"] or 0

    total_mobile = payments.filter(payment_method="MOBILE").aggregate(
        total=Sum("amount_paid")
    )["total"] or 0

    total_card = payments.filter(payment_method="CARD").aggregate(
        total=Sum("amount_paid")
    )["total"] or 0

    system_total = total_cash + total_bank + total_mobile + total_card

    logger.info(
        f"Session approval totals session_id={session.id} cash={total_cash} bank={total_bank} mobile={total_mobile} card={total_card} system_total={system_total}"
    )

    context = {
        "session": session,
        "total_cash": total_cash,
        "total_bank": total_bank,
        "total_mobile": total_mobile,
        "total_card": total_card,
        "closing_balance": system_total + session.opening_balance,
        "system_total": system_total,
    }

    return render(request, "supervisor/session_approval.html", context)

@login_required
@permission("payments.view_cashiersession")
def cashier_session_sales_view(request):
    tenant = request.tenant
    branch = request.branch
    user = request.user

    logger.info(
        f"Cashier session sales view accessed "
    )
    session = CashierSession.objects.filter(
        tenant=tenant,
        branch=branch,
        cashier=user,
        status__in=["PENDING", "OPEN"]
        ).first()
    
    if not session:
        messages.error(request, "There is no active session ")
        return redirect("cashier_dashboard")

    payments = session.payments.filter(status__in=["COMPLETED", "REVERSED"]).order_by('-id')

    total_cash = payments.filter(payment_method="CASH").aggregate(
        total=Sum("amount_paid")
    )["total"] or 0

    total_bank = payments.filter(payment_method="BANK").aggregate(
        total=Sum("amount_paid")
    )["total"] or 0

    total_mobile = payments.filter(payment_method="MOBILE").aggregate(
        total=Sum("amount_paid")
    )["total"] or 0

    total_card = payments.filter(payment_method="CARD").aggregate(
        total=Sum("amount_paid")
    )["total"] or 0

    system_total = total_cash + total_bank + total_mobile + total_card

    logger.info(
        f"Session sales totals session_id={session.id} cash={total_cash} bank={total_bank} mobile={total_mobile} card={total_card} system_total={system_total}"
    )

    # Pagination
    paginator = Paginator(payments, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    logger.info(
        f"Session sales pagination session_id={session.id} page={page_number} total_payments={payments.count()}"
    )

    context = {
        "page_obj": page_obj,
        "session": session,
        "total_cash": total_cash,
        "total_bank": total_bank,
        "total_mobile": total_mobile,
        "total_card": total_card,
        "closing_balance": system_total + session.opening_balance,
        "system_total": system_total,
        "payments": payments,
    }

    return render(request, "payments/cashier/session_sales.html", context)

@login_required
#@user_passes_test(is_supervisor)
@permission("payments.view_cashiersession")
def session_sales_view(request, session_id):
    tenant = request.tenant
    branch = request.branch
    user = request.user

    logger.info(
        f"Session sales view accessed session_id={session_id}"
    )

    session = get_object_or_404(
        CashierSession,
        id=session_id,
        tenant=tenant,
        branch=branch,
        status="PENDING"
    )

    payments = session.payments.filter(status__in=["COMPLETED", "REVERSED"]).order_by('-id')

    total_cash = payments.filter(payment_method="CASH").aggregate(
        total=Sum("amount_paid")
    )["total"] or 0

    total_bank = payments.filter(payment_method="BANK").aggregate(
        total=Sum("amount_paid")
    )["total"] or 0

    total_mobile = payments.filter(payment_method="MOBILE").aggregate(
        total=Sum("amount_paid")
    )["total"] or 0

    total_card = payments.filter(payment_method="CARD").aggregate(
        total=Sum("amount_paid")
    )["total"] or 0

    system_total = total_cash + total_bank + total_mobile + total_card

    logger.info(
        f"Session sales totals session_id={session.id} cash={total_cash} bank={total_bank} mobile={total_mobile} card={total_card} system_total={system_total}"
    )

    # Pagination
    paginator = Paginator(payments, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    logger.info(
        f"Session sales pagination session_id={session.id} page={page_number} total_payments={payments.count()}"
    )

    context = {
        "page_obj": page_obj,
        "session": session,
        "total_cash": total_cash,
        "total_bank": total_bank,
        "total_mobile": total_mobile,
        "total_card": total_card,
        "closing_balance": system_total + session.opening_balance,
        "system_total": system_total,
        "payments": payments,
    }

    return render(request, "supervisor/session_sales.html", context)

@login_required
@permission(["payments.view_payment", "payments.view_cashiersession"])
def bill_search_view(request):

    tenant = request.tenant
    branch = request.branch
    user = request.user

    query = request.GET.get("q", "").strip()

    logger.info(
        f"Bill search accessed query='{query}'"
    )

    # --------------------------------------------------
    #  Require Active Session
    # --------------------------------------------------

    session = get_active_session(tenant, branch, user)

    if not session:
        logger.warning(
            f"Bill search attempted without active session "
        )
        return render(request, "payments/bill_search.html", {
            "error": "No active session. Please open session first.",
            "query": query,
            "bills": [],
        })

    bills = []
    settings = None

    if query:

        # Load billing settings once
        try:
            settings = BillingSettings.objects.get(tenant=tenant)
        except BillingSettings.DoesNotExist:
            settings = None

        # Smart search query
        search_filter = (
            Q(invoice_number__icontains=query) |
            Q(meter__meter_number__icontains=query) |
            Q(customer__first_name__icontains=query) |
            Q(customer__last_name__icontains=query)
        )

        bills_qs = (
            Bill.objects
            .select_related("customer", "meter")
            .filter(
                tenant=tenant,
                branch=branch,
                status="UNSOLD"
            )
            .filter(search_filter)
            .order_by("-issue_date")[:20]
        )

        logger.info(
            f"Bill search results query='{query}' count={bills_qs.count()}"
        )

        # --------------------------------------------------
        # 2 Compute Late Fee + Total Payable
        # --------------------------------------------------

        bills = []

        for bill in bills_qs:
            late_fee = Decimal("0.00")

            if settings and bill.is_overdue():
                late_fee = bill.calculate_late_fee().quantize(Decimal("0.01"))

            total_payable = bill.total_payable()

            bills.append({
                "bill": bill,
                "late_fee": late_fee,
                "total_payable": total_payable,
            })

    context = {
        "query": query,
        "bills": bills,
        "session": session,
    }

    return render(request, "payments/cashier/bill_search.html", context)

def verify_receipt(receipt):

    payment = receipt.payment

    logger.info(
        f"Receipt verification started receipt={receipt.receipt_number} tenant={payment.tenant} user={payment.received_by}"
    )

    raw_string = (
        f"{receipt.receipt_number}|"
        f"{payment.bill.invoice_number}|"
        f"{payment.amount_paid}|"
        f"{payment.payment_date}|"
        f"{payment.customer_id}|"
        f"{payment.tenant_id}|"
        f"{settings.SECRET_KEY}"
    )

    expected_hash = hashlib.sha256(raw_string.encode()).hexdigest()

    is_valid = expected_hash == receipt.signature_hash

    if is_valid:
        logger.info(
            f"Receipt verified successfully receipt={receipt.receipt_number}"
        )
    else:
        logger.warning(
            f"Receipt verification failed receipt={receipt.receipt_number}"
        )

    return is_valid

@login_required
def print_receipt_view(request, receipt_id):
    tenant = request.tenant
    user = request.user

    logger.info(
        f"Receipt print requested receipt_id={receipt_id}"
    )

    receipt = get_object_or_404(
        Receipt.objects.select_related(
            "payment__bill",
            "payment__customer",
            "payment__session"
        ),
        id=receipt_id,
        tenant=tenant
    )

    if not verify_receipt(receipt):
        logger.warning(
            f"Receipt verification failed during print receipt={receipt.receipt_number}"
        )
        messages.error(request, "Invalid receipt. Data integrity check failed.")
        return redirect("cashier_dashboard")

    logger.info(
        f"Receipt printed receipt={receipt.receipt_number}"
    )

    return render(request, "payments/receipt_print.html", {
        "receipt": receipt
    })

@login_required
@permission("payments.view_payment")
def payment_list_view(request):

    user = request.user
    tenant = request.tenant
    branch = request.branch

    logger.info(
        f"Payment list accessed "
    )

    payments = Payment.objects.select_related(
        "bill",
        "customer",
        "received_by"
    ).filter(
        tenant=tenant
    )

    if getattr(user, "is_manager", False):
        logger.info(
            f"Manager viewing all payments "
        )
        pass
    else:
        if not branch:
            logger.warning(
                f"Payment list access denied (no branch)"
            )
            messages.error(request, "You should be branch member to view payments.")
            return redirect("portal-home")

        payments = payments.filter(branch=branch)

        logger.info(
            f"Payment list restricted to branch "
        )

    # Filters
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    payment_method = request.GET.get("payment_method")
    cashier_id = request.GET.get("cashier")

    if date_from:
        payments = payments.filter(
            payment_date__date__gte=parse_date(date_from)
        )

    if date_to:
        payments = payments.filter(
            payment_date__date__lte=parse_date(date_to)
        )

    if payment_method:
        payments = payments.filter(payment_method=payment_method)

    if cashier_id:
        payments = payments.filter(received_by_id=cashier_id)

    payments = payments.order_by("-payment_date")

    logger.info(
        f"Payment list filtered, count={payments.count()}"
    )

    # Pagination
    paginator = Paginator(payments, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    logger.info(
        f"Payment list pagination page={page_number}"
    )

    # For filter dropdown
    User = get_user_model()
    cashiers = User.objects.filter(
        tenant=tenant,
        is_active=True
    )

    context = {
        "page_obj": page_obj,
        "cashiers": cashiers,
        "payment_methods": Payment.PAYMENT_METHODS,
        "filters": {
            "date_from": date_from,
            "date_to": date_to,
            "payment_method": payment_method,
            "cashier": cashier_id,
        }
    }

    return render(request, "payments/payment_list.html", context)

@login_required
@permission("payments.change_paymentreversal")
def reverse_payment_approve_view(request, payment_id):

    tenant = request.tenant
    user = request.user

    logger.info(
        f"Manual payment reversal page accessed payment_id={payment_id}"
    )

    payment = get_object_or_404(
        Payment,
        id=payment_id,
        tenant=tenant
    )

    if request.method == "POST":
        form = PaymentReversalForm(request.POST)

        if form.is_valid():
            try:
                reverse_manual_payment(
                    payment_id=payment.id,
                    reason=form.cleaned_data["reason"],
                    reversed_by=user,
                    supervisor=user,
                    request=request,
                )

                logger.info(
                    f"Manual payment reversed payment_id={payment.id}"
                )

                messages.success(request, "Payment reversed successfully.")
                return redirect("payment_detail", payment_id=payment.id)

            except Exception as e:

                logger.error(
                    f"Manual payment reversal failed payment_id={payment.id} error={str(e)}"
                )

                messages.error(request, str(e))

    else:
        form = PaymentReversalForm()

    return render(request, "payments/reverse_payment.html", {
        "payment": payment,
        "form": form,
    })

@login_required
@permission("payments.add_paymentreversal")
def request_reversal_view(request, payment_id):

    tenant = request.tenant
    branch = request.branch
    user = request.user

    logger.info(
        f"Reversal request page accessed payment_id={payment_id} user={user}"
    )

    payment = get_object_or_404(
        Payment.objects.select_related("session"),
        id=payment_id,
        tenant=tenant,
        status="COMPLETED",
        is_reversal=False,
        session__branch=branch
    )

    # Prevent duplicate request
    if hasattr(payment, "reversal_request"):
        logger.warning(
            f"Duplicate reversal request attempt payment_id={payment.id}"
        )
        messages.error(request, "Reversal already requested.")
        return redirect("reversal_payment_search")

    if request.method == "POST":
        form = PaymentReversalForm(request.POST)

        if form.is_valid():
            with transaction.atomic():

                PaymentReversalRequest.objects.create(
                    tenant=tenant,
                    payment=payment,
                    reason=form.cleaned_data["reason"],
                    requested_by=user,
                )

                logger.info(
                    f"Reversal request submitted payment_id={payment.id}"
                )

            messages.success(request, "Reversal request submitted.")
            return redirect("reversal_payment_search")

    else:
        form = PaymentReversalForm()

    return render(request, "payments/reversal_request.html", {
        "payment": payment,
        "form": form
    })

@login_required
@permission("payments.view_paymentreversal")
def reversal_payment_search_view_(request):

    tenant = request.tenant
    branch = request.branch
    user = request.user
    query = request.GET.get("q", "").strip()

    logger.info(
        f"Reversal payment search accessed query='{query}'"
    )

    payments = []

    if query:
        payments = Payment.objects.select_related(
            "bill",
            "customer",
            "session"
        ).filter(
            tenant=tenant,
            session__branch=branch,
            status="COMPLETED",
            is_reversal=False
        ).filter(
            Q(reference_number__icontains=query) |
            Q(bill__invoice_number__icontains=query) |
            Q(customer__first_name__icontains=query) |
            Q(customer__last_name__icontains=query) |
            Q(bill__meter__meter_number__icontains=query)
        )

        payments = payments.exclude(
            id__in=PaymentReversalRequest.objects.filter(
                status="PENDING"
            ).values_list("payment_id", flat=True)
        )

        logger.info(
            f"Reversal search results count={payments.count()}"
        )

    return render(request, "payments/reversal_search.html", {
        "payments": payments[:30],
        "query": query,
    })


@login_required
@permission("payments.view_paymentreversal")
def pending_reversal_requests_view(request):

    tenant = request.tenant
    branch = getattr(request, "branch", None)
    user = request.user

    search = request.GET.get("search", "").strip()

    logger.info(
        f"Pending reversal requests viewed search='{search}'"
    )

    requests = PaymentReversalRequest.objects.select_related(
        "payment",
        "payment__bill",
        "payment__customer",
        "requested_by",
    ).filter(
        tenant=tenant,
        status="PENDING"
    )

    if branch:
        requests = requests.filter(
            payment__session__branch=branch
        )

    if search:
        requests = requests.filter(
            Q(payment__reference_number__icontains=search) |
            Q(payment__bill__invoice_number__icontains=search) |
            Q(requested_by__email__icontains=search)
        )

    requests = requests.order_by("-requested_at")

    logger.info(
        f"Pending reversal requests fetched count={requests.count()}"
    )

    paginator = Paginator(requests, 20)
    page = request.GET.get("page")
    page_obj = paginator.get_page(page)

    return render(request, "supervisor/pending_reversals.html", {
        "requests": page_obj,
        "search": search,
    })


@login_required
@permission(["payments.view_cashiersession"])
def my_pending_reversal_requests_view(request):

    tenant = request.tenant
    branch = getattr(request, "branch", None)
    user = request.user

    query = request.GET.get("q", "").strip()

    logger.info(
        f"My reversal requests accessed query='{query}'"
    )

    payments = []

    if query:
        payments = Payment.objects.select_related(
            "bill",
            "customer",
            "session"
        ).filter(
            tenant=tenant,
            session__branch=branch,
            status="COMPLETED",
            is_reversal=False
        ).filter(
            Q(reference_number__icontains=query) |
            Q(bill__invoice_number__icontains=query) |
            Q(customer__first_name__icontains=query) |
            Q(customer__last_name__icontains=query) |
            Q(bill__meter__meter_number__icontains=query)
        )

        payments = payments.exclude(
            id__in=PaymentReversalRequest.objects.filter(
                status__in=["PENDING", "APPROVED", "PROCESSED"]
            ).values_list("payment_id", flat=True)
        )

        logger.info(
            f"My reversal payment search results count={payments.count()}"
        )

    search = request.GET.get("search", "").strip()

    requests = PaymentReversalRequest.objects.select_related(
        "payment",
        "payment__bill",
        "payment__customer",
        "requested_by",
    ).filter(
        tenant=tenant
    ).filter(
        status__in=["APPROVED", "PENDING"]
    )

    if branch:
        requests = requests.filter(
            payment__session__branch=branch
        )

    if search:
        requests = requests.filter(
            Q(payment__reference_number__icontains=search) |
            Q(payment__bill__invoice_number__icontains=search) |
            Q(requested_by__email__icontains=search)
        )

    requests = requests.order_by("-requested_at")

    logger.info(
        f"My reversal requests fetched count={requests.count()}"
    )

    paginator = Paginator(requests, 20)
    page = request.GET.get("page")
    page_obj = paginator.get_page(page)

    return render(request, "payments/cashier/reversal_search.html", {
        "requests": page_obj,
        "search": search,
        "payments": payments[:30],
        "query": query,
    })

@login_required
@permission(["payments.add_cashiersession"])
def my_pending_reversal_requests_status_view(request):

    tenant = request.tenant
    branch = getattr(request, "branch", None)
    user = request.user

    requests = PaymentReversalRequest.objects.select_related(
        "payment",
        "payment__bill",
        "payment__customer",
        "requested_by",
    ).filter(
        tenant=tenant
    ).filter(
        status__in=["APPROVED", "PENDING"]
    )

    if branch:
        requests = requests.filter(
            payment__session__branch=branch
        )

    requests = requests.order_by("-requested_at")

    logger.info(
        f"My reversal requests fetched count={requests.count()}"
    )

    paginator = Paginator(requests, 20)
    page = request.GET.get("page")
    page_obj = paginator.get_page(page)

    return render(request, "payments/cashier/payment_reversal_status.html", {
        "requests": page_obj,
    })


@login_required
@permission("payments.view_paymentreversal")
def review_reversal_view(request, request_id):

    tenant = request.tenant
    user = request.user

    logger.info(
        f"Reversal review page accessed request_id={request_id}"
    )

    reversal_request = get_object_or_404(
        PaymentReversalRequest.objects.select_related(
            "payment",
            "payment__bill",
            "payment__customer",
            "requested_by",
        ),
        id=request_id,
        tenant=tenant,
        status="PENDING"
    )

    if request.method == "POST":

        action = request.POST.get("action")

        if action == "approve":

            with transaction.atomic():

                if reversal_request.requested_by == user:
                    logger.warning(
                        f"Self-approval attempt request_id={reversal_request.id}"
                    )
                    messages.error(request, "Cannot approve your own request.")
                    pass

                reversal_request.status = "APPROVED"
                reversal_request.reviewed_by = user
                reversal_request.reviewed_at = timezone.now()
                reversal_request.save()

                logger.info(
                    f"Reversal approved request_id={reversal_request.id}"
                )

            messages.success(request, "Reversal approved.")
            return redirect("pending_reversals")

        elif action == "reject":

            reversal_request.status = "REJECTED"
            reversal_request.reviewed_by = user
            reversal_request.reviewed_at = timezone.now()
            reversal_request.review_note = request.POST.get("note", "")
            reversal_request.save()

            logger.info(
                f"Reversal rejected request_id={reversal_request.id}"
            )

            messages.success(request, "Reversal rejected.")
            return redirect("pending_reversals")

    return render(request, "supervisor/review_reversal.html", {
        "req": reversal_request
    })

