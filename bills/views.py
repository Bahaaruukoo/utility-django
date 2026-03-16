import calendar
from decimal import Decimal
from multiprocessing import context
from urllib import request

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.forms import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
# Create your views here.
from django.views.generic import CreateView, ListView

from bills.forms import BillingSettingsForm, MeterReadingForm
from bills.models import Bill, BillingSettings, MeterReading
from bills.services import MeterReadingService
from core.models import TenantUserRole
from tenant_utils.decorators import permission

from .models import Bill


@login_required
def bill_list(request):


    from django.db.models.signals import post_save
    instance = Bill.objects.first()

    post_save.send(
        sender=Bill,
        instance=instance,
        created=False
    ) 
    tenant = request.tenant
    branch = getattr(request, "branch", None)
    today = timezone.now()

    # -------------------------------
    # Month / Year Selection
    # -------------------------------

    selected_month = request.GET.get("month")
    selected_year = request.GET.get("year")

    if not selected_month or not selected_year:
        selected_month = today.month
        selected_year = today.year
    else:
        selected_month = int(selected_month)
        selected_year = int(selected_year)

    # -------------------------------
    # Base Query
    # -------------------------------

    bills = Bill.objects.filter(
        tenant=tenant,
        bill_period__year=selected_year,
        bill_period__month=selected_month
    ).select_related("customer", "meter", "branch")

    if branch:
        bills = bills.filter(branch=branch)

    # -------------------------------
    # Search Filter
    # -------------------------------

    search = request.GET.get("search")
    if search:
        bills = bills.filter(
            Q(customer__first_name__icontains=search) |
            Q(customer__last_name__icontains=search) |
            Q(meter__meter_number__icontains=search) |
            Q(invoice_number__icontains=search)
        )

    # -------------------------------
    # Status Filter
    # -------------------------------

    status = request.GET.get("status")
    if status:
        bills = bills.filter(status=status)

    bills = bills.order_by("-issue_date")

    # -------------------------------
    # Pagination
    # -------------------------------

    paginator = Paginator(bills, 20)
    page = request.GET.get("page")
    bills_page = paginator.get_page(page)

    # -------------------------------
    # Load Billing Settings Once
    # -------------------------------

    try:
        settings = BillingSettings.objects.get(tenant=tenant)
    except BillingSettings.DoesNotExist:
        settings = None

    enhanced_bills = []

    for bill in bills_page:

        late_fee = Decimal("0.00")

        if (
            settings
            and bill.status == "UNSOLD"
            and bill.is_overdue()
        ):
            late_fee = (
                bill.amount *
                (settings.late_fee_rate / Decimal("100"))
            ).quantize(Decimal("0.01"))

        total_payable = bill.amount + late_fee

        enhanced_bills.append({
            "bill": bill,
            "late_fee": late_fee,
            "total_payable": total_payable,
        })

    # -------------------------------
    # Month / Year Dropdown
    # -------------------------------

    months = [
        (i, calendar.month_name[i])
        for i in range(1, 13)
    ]

    current_year = today.year
    years = list(range(current_year - 10, current_year + 1))

    return render(request, "bills/bill_list.html", {
        "bills": enhanced_bills,
        "page_obj": bills_page,
        "months": months,
        "years": years,
        "selected_month": int(selected_month),
        "selected_year": int(selected_year),
    })

@login_required
def bill_detail_print(request, pk):

    bill = get_object_or_404(
        Bill.objects.select_related("customer", "meter", "branch"),
        pk=pk,
        tenant=request.tenant
    )

    settings = BillingSettings.objects.get(tenant=request.tenant)

    completed_payment = bill.payments.filter(
            status="COMPLETED"
        ).select_related("receipt").first()
    
    return render(request, "bills/bill_detail_print.html", {
        "bill": bill,
        "late_fee": bill.calculate_late_fee(),
        "total_payable": bill.total_payable(),
        "settings": settings,
        #"receipt": completed_payment.receipt
    })

@login_required
def bill_detail(request, pk):

    bill = get_object_or_404(
        Bill.objects.select_related("customer", "meter", "branch"),
        pk=pk,
        tenant=request.tenant
    )

    settings = BillingSettings.objects.get(tenant=request.tenant)

    #allocation = BillAllocation.objects.filter

    completed_payment = bill.payments.filter(
            status="COMPLETED"
        ).select_related("receipt").first()
    
    if completed_payment and not hasattr(completed_payment, "receipt"):
        receipt = None
        late_fee = 0
        total_payable = bill.amount
    else: 
        receipt = completed_payment.receipt if completed_payment else None
        late_fee = bill.calculate_late_fee()
        total_payable = bill.total_payable()

    return render(request, "bills/bill_detail.html", {
        "bill": bill,
        "settings": settings,
        "receipt": receipt,
        "late_fee": late_fee,
        "total_payable" : total_payable 
    })

@login_required
@require_POST
@transaction.atomic
def mark_bill_sold(request, pk):

    bill = get_object_or_404(
        Bill,
        pk=pk,
        tenant=request.tenant
    )

    # Branch safety
    if getattr(request, "branch", None):
        if bill.branch != request.branch:
            messages.error(request, "Unauthorized access.")
            return redirect("bill-list")

    if bill.status != "UNSOLD":
        messages.warning(request, "Bill already processed.")
        return redirect("bill-detail", pk=bill.pk)

    bill.status = "SOLD"
    bill.save(update_fields=["status"])

    messages.success(request, "Bill marked as SOLD successfully.")

    return redirect("bill-detail", pk=bill.pk)

@login_required
@require_POST
@transaction.atomic
@permission("bills.change_bill")
def void_bill(request, pk):

    bill = get_object_or_404(
        Bill,
        pk=pk,
        tenant=request.tenant
    )

    # Branch safety
    if getattr(request, "branch", None):
        if bill.branch != request.branch:
            messages.error(request, "Unauthorized access.")
            return redirect("bill-list")

    reason = request.POST.get("reason")

    if not reason:
        messages.error(request, "Void reason is required.")
        return redirect("bill-detail", pk=bill.pk)

    try:
        bill.void(user=request.user, reason=reason)
        messages.success(request, "Bill successfully voided.")
    except ValidationError as e:
        messages.error(request, str(e))

    return redirect("bill-detail", pk=bill.pk)

@method_decorator(login_required, name="dispatch")
@method_decorator(permission("bills.add_meterreading"), name="dispatch")
class MeterReadingCreateView(CreateView):
    template_name = "bills/meter_reading_form.html"
    form_class = MeterReadingForm
    success_url = reverse_lazy("meter_reading_create")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.tenant
        return kwargs

    def form_valid(self, form):
        try:
            MeterReadingService.create_reading(
                tenant=self.request.tenant,
                branch=self.request.branch,
                reader=self.request.user,
                meter=form.cleaned_data["meter"],
                reading_value=form.cleaned_data["reading_value"],
            )
            messages.success(self.request, "Meter reading recorded successfully.")
        except IntegrityError: 
            messages.error(self.request, "A reading for this meter on this date already exists.")
        
        except Exception as e:
            messages.error(self.request, str(e))

        return redirect(self.success_url)

@method_decorator(login_required, name="dispatch")
class MeterReadingListView(ListView):
    model = MeterReading
    template_name = "bills/meter_reading_list.html"
    context_object_name = "readings"
    paginate_by = 10

    def get_queryset(self):
        tenant = self.request.tenant
        branch = self.request.branch        
        print("Tenant admin - showing all readings for tenant", tenant)

        if is_branch_member(self.request):
            queryset = MeterReading.objects.filter(
                tenant=tenant, branch=branch
            ).select_related("meter")

        else:
            queryset = MeterReading.objects.filter(
                tenant=tenant
            ).select_related("meter")

        # 🔎 Search by meter number
        search = self.request.GET.get("search")
        if search:
            queryset = queryset.filter(
                meter__meter_number__icontains=search
            )

        # 📅 Filter by date range
        start_date = self.request.GET.get("start_date")
        end_date = self.request.GET.get("end_date")

        if start_date:
            queryset = queryset.filter(reading_date__gte=start_date)

        if end_date:
            queryset = queryset.filter(reading_date__lte=end_date)

        return queryset

@login_required
@permission("bills.view_meterreading")
def meter_reading_detail(request, pk):
    tenant = request.tenant

    # 🔐 Tenant-safe object lookup
    if user_has_role(request, "TENANT_ADMIN"):
        reading = get_object_or_404(
            MeterReading.objects.select_related("meter"),
            pk=pk,
            tenant=tenant
        )
    else:
        reading = get_object_or_404(
            MeterReading.objects.select_related("meter"),
            pk=pk,
            tenant=tenant,
            branch=request.branch
        )

    # Optional: get related bill (if generated)
    bill = Bill.objects.filter(
        tenant=tenant,
        branch=request.branch,
        meter=reading.meter,
        bill_period=reading.reading_date
    ).first()
    context = {
        "reading": reading,
        "bill": bill
    }

    return render(request, "bills/meter_reading_detail.html", context)


@login_required
@permission("bills.change_meterreading")
def meter_reading_edit(request, pk):
    
    tenant = request.tenant

    reading = get_object_or_404(
        MeterReading,
        pk=pk,
        tenant=tenant,
        branch=request.branch
    )

    if hasattr(reading, "bill") and reading.bill.status == "SOLD":
        messages.warning(request, "Cannot modify meter reading for sold bill")
        return redirect("meter_reading_detail", pk=reading.pk)

    if hasattr(reading, "bill") and reading.bill.status != "VOIDED":
        messages.warning(request, "Bill associated to this reading is not voided")
        return redirect("meter_reading_detail", pk=reading.pk)

    if request.method == "POST":
        new_value = request.POST.get("reading_value")

        try:
            MeterReadingService.update_reading(
                tenant,
                reading,
                Decimal(new_value)
            )
            messages.success(request, "Reading updated successfully.")
            return redirect("meter_reading_detail", pk=reading.pk)
        except IntegrityError:
            messages.error(request, "A reading for this meter on this date already exists.")
        except Exception as e:
            messages.error(request, str(e))

    return render(request, "bills/meter_reading_edit.html", {"reading": reading})


def edit_billing_settings(request):
    tenant = request.tenant

    settings_obj = get_object_or_404(
        BillingSettings,
        tenant=tenant
    )
    if request.method == "POST":
        form = BillingSettingsForm(
            request.POST,
            instance=settings_obj
        )

        if form.is_valid():
            form.save()
            messages.success(request, "Billing settings updated successfully.")
            return redirect("edit-billing-settings")

    else:
        form = BillingSettingsForm(instance=settings_obj)

    return render(
        request,
        "bills/edit_billing_settings.html",
        {"form": form}
    )


def is_branch_member(request) -> bool:
        """
        Branch member = staff user who is marked is_branch_member in BranchMembership
        for the current request.tenant and current request.branch
        """
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_platform_admin", False):
            return False
        '''if not getattr(user, "is_staff", False):
            return False'''

        tenant = getattr(request, "tenant", None)
        branch = getattr(request, "branch", None)
        if not tenant or not branch:
            return False

        # local import to avoid circular imports
        from tenant_utils.models import BranchMembership

        return BranchMembership.objects.filter(
            tenant=tenant,
            branch=branch,
            user=user,
            is_branch_admin=True,
        ).exists()

def user_has_role(request, role_name):
    return TenantUserRole.objects.filter(
        user=request.user,
        tenant=request.tenant,
        role__name=role_name
    ).exists()


