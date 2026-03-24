import json
from datetime import date, datetime, time

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count, F, Max, Min, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from bills.models import Bill
from customers.models import Customer
from payments.models import CashierSession, PaymentAllocation
from reports.forms import (BillingReportForm, CollectionReportForm,
                           SessionReportForm)
from reports.models import (BillReport, CashierSessionReport, CollectionReport,
                            MonthlyStatistics)
from reports.services.billing_report_service import \
    generate_monthly_billing_report
from reports.services.collection_report_service import \
    generate_monthly_collection_report
from reports.services.dashboard_service import get_dashboard_data
from reports.services.debt_aging_service import generate_debt_aging_report
from reports.services.session_report_service import get_closed_sessions_report
from reports.services.statistics_generator import (generate_monthly_statistics,
                                                   generate_yearly_statistics)
from tenant_utils.models import Branch


@login_required
def statistics_view(request):
    tenant = request.user.tenant
    today = timezone.now()

    year_param = request.GET.get("year")
    month_param = request.GET.get("month")

    year = int(year_param) if year_param else today.year
    month = int(month_param) if month_param else today.month

    if month != 0:

        report = generate_monthly_statistics(
            tenant=tenant,
            year=year,
            month=month
        )

        report_type = "monthly"

    else:
        report = generate_yearly_statistics(
            tenant=tenant,
            year=year
        )

        report_type = "yearly"

    return render(
        request,
        "reports/monthly_statistics.html",
        {
            "report": report,
            "year": year,
            "month": str(month),
            "report_type": report_type,
        }
    )

@login_required
def print_session_report_view(request, session_id):

    tenant = request.tenant

    session = (
        CashierSession.objects
        .filter(
            id=session_id,
            tenant=tenant,
            status="CLOSED"
        )
        .select_related("cashier")
        .first()
    )

    report = CashierSessionReport.objects.filter(
        session=session
    ).first()

    return render(request, "reports/print_session.html", {
        "session": session,
        "report": report
    })

@login_required
def billing_report_generate(request):

    form = BillingReportForm(request.POST or None)

    if request.method == "POST":

        if form.is_valid():

            year = form.cleaned_data["year"]
            month = form.cleaned_data["month"]

            report = generate_monthly_billing_report(
                tenant=request.user.tenant,
                year=year,
                month=month,
                user=request.user
            )

            return redirect(
                "billing_report_detail",
                report_id=report.id
            )

    return render(
        request,
        "reports/billing_report_generate.html",
        {"form": form}
    )

@login_required
def billing_report_detail(request, report_id):

    report = get_object_or_404(
        BillReport.objects.prefetch_related(
            "bills__customer",
            "bills__meter"
        ),
        id=report_id,
        tenant=request.user.tenant
    )

    return render(
        request,
        "reports/billing_report_detail.html",
        {
            "report": report
        }
    )



@login_required
def collection_report_generate(request):

    tenant = request.user.tenant

    form = CollectionReportForm(
        request.POST or None,
        tenant=tenant
    )

    if request.method == "POST":

        if form.is_valid():

            year = form.cleaned_data["year"]
            month = form.cleaned_data["month"]
            branch = form.cleaned_data["branch"]

            report = generate_monthly_collection_report(
                tenant=tenant,
                year=year,
                month=month,
                branch=branch,
                user=request.user, 
                force=True
            )

            return redirect(
                "collection_report_detail",
                report_id=report.id
            )

    return render(
        request,
        "reports/collection_report_generate.html",
        {"form": form}
    )


@login_required
def collection_report_detail(request, report_id):

    report = get_object_or_404(
        CollectionReport.objects.prefetch_related(
            "payments__bill",
            "payments__customer"
        ),
        id=report_id,
        tenant=request.user.tenant
    )

    return render(
        request,
        "reports/collection_report_detail.html",
        {"report": report}
    )


@login_required
def debt_aging_report(request):

    tenant = request.tenant

    as_of = request.GET.get("as_of_date")

    if as_of:
        as_of_date = date.fromisoformat(as_of)
    else:
        as_of_date = date.today()

    as_of_date = timezone.make_aware(
        datetime.combine(as_of_date, time.max)
    )
    branch_id = request.GET.get("branch")

    branch = None
    if branch_id:
        branch = Branch.objects.get(pk=branch_id)

    report = generate_debt_aging_report(
        tenant=tenant,
        as_of_date=as_of_date,
        branch=branch
    )

    branches = Branch.objects.filter(tenant=tenant)

    return render(
        request,
        "reports/debt_aging.html",
        {
            "report": report,
            "branches": branches,
            "selected_branch": branch,
        }
    )


@login_required
def dashboard(request):

    tenant = request.tenant

    data = get_dashboard_data(tenant)

   
    context = {
        "data": data,
        "monthly_json": json.dumps(
            data["monthly_collections"],
            cls=DjangoJSONEncoder
        ),
        "methods_json": json.dumps(
            data["payment_methods"],
            cls=DjangoJSONEncoder
        )
    }

    return render(
        request,
        "reports/dashboard.html",
        context
    )

@login_required
def session_financial_report(request):

    form = SessionReportForm(request.POST or None, tenant=request.tenant)

    sessions = None
    totals = None

    if request.method == "POST" and form.is_valid():

        start = form.cleaned_data["start_date"]
        end = form.cleaned_data["end_date"]
        branch = form.cleaned_data["branch"]

        sessions, totals = get_closed_sessions_report(
            tenant=request.tenant,
            start_date=start,
            end_date=end,
            branch=branch
        )
        

    return render(
        request,
        "reports/session_financial_report.html",
        {
            "form": form,
            "sessions": sessions,
            "totals": totals
        }
    )


def kebele_category_report(request):
    month = request.GET.get("month")
    year = request.GET.get("year")
    page = request.GET.get("page", 1)

    if not year:
        year = timezone.now().year

    # ✅ Default month (IMPORTANT)
    if not month:
        month = timezone.now().month
    else:
        month = int(month)
    # ---------------------------------------
    # PAYMENT ALLOCATIONS (FINANCIAL DATA)
    # ---------------------------------------
    allocations = PaymentAllocation.objects.filter(
        tenant=request.tenant,
        payment__bill__status="SOLD",
        payment__bill__bill_period__year=year,
        payment__status="COMPLETED",     # ✅ only successful payments
        payment__is_reversal=False,      # ✅ exclude reversals
        payment__reversal_entries__isnull=True 
    )

    if month and month != "0":
        allocations = allocations.filter(
            #payment__payment_date__month=month
            payment__bill__bill_period__month=month
        )
    component_data = allocations.values(
        "payment__bill__customer__kebele__name",
        "payment__bill__customer__customer_type",
        "component"
    ).annotate(
        total=Sum("amount")
    )

    # ---------------------------------------
    # BILL METRICS
    # ---------------------------------------
    bills = Bill.objects.select_related(
        "customer__kebele", "reading"
    ).filter(
        tenant=request.tenant,
        status="SOLD",
        bill_period__year=year
    )
    if month and month != 0:
        bills = bills.filter(bill_period__month=month)

    bill_stats = bills.values(
        "customer__kebele__name",
        "customer__customer_type"
    ).annotate(
        billCount=Count("id"),
        minBillAmount=Min("amount"),
        maxBillAmount=Max("amount"),
    )

    # ---------------------------------------
    # INITIALIZE STRUCTURE (VERY IMPORTANT)
    # ---------------------------------------
    grouped = {}

    for stat in bill_stats:
        kebele = stat["customer__kebele__name"] or "Unknown"
        category = stat["customer__customer_type"]

        if kebele not in grouped:
            grouped[kebele] = {
                "kebele": kebele,
                "categoryReports": {},
                "billCountKebeleTotal": 0,
                "consumptionKebeleTotal": 0,
                "rentKebeleTotal": 0,
                "consCostKebeleTotal": 0,
                "serviceKebeleTotal": 0,
                "operationKebeleTotal": 0,
                "penaltyKebeleTotal": 0,
                "kebeleTotal": 0,
            }

        grouped[kebele]["categoryReports"][category] = {
            "customerCategory": category,
            "billCount": stat["billCount"],
            "minBillAmount": stat["minBillAmount"],
            "maxBillAmount": stat["maxBillAmount"],
            "totalConsumption": 0,  # ✅ initialize here
            "totalMeterRent": 0,
            "totalAmount": 0,
            "totalServiceCharge": 0,
            "totalOperationCharge": 0,
            "totalPenalty": 0,
            "categoryTotal": 0,
        }

        grouped[kebele]["billCountKebeleTotal"] += stat["billCount"]

    # ---------------------------------------
    # ADD CONSUMPTION (SAFE METHOD)
    # ---------------------------------------
    for bill in bills:
        kebele = bill.customer.kebele.name if bill.customer.kebele else "Unknown"
        category = bill.customer.customer_type

        if kebele not in grouped or category not in grouped[kebele]["categoryReports"]:
            continue

        consumption = bill.reading.consumption if bill.reading else 0

        grouped[kebele]["categoryReports"][category]["totalConsumption"] += consumption
        grouped[kebele]["consumptionKebeleTotal"] += consumption

    # ---------------------------------------
    # APPLY COMPONENT TOTALS
    # ---------------------------------------
    for row in component_data:
        kebele = row["payment__bill__customer__kebele__name"] or "Unknown"
        category = row["payment__bill__customer__customer_type"]
        component = row["component"]
        total = row["total"] or 0

        if kebele not in grouped or category not in grouped[kebele]["categoryReports"]:
            continue

        cat = grouped[kebele]["categoryReports"][category]

        if component == "WATER":
            cat["totalAmount"] += total
            grouped[kebele]["consCostKebeleTotal"] += total

        elif component == "METER_RENT":
            cat["totalMeterRent"] += total
            grouped[kebele]["rentKebeleTotal"] += total

        elif component == "SERVICE_FEE":
            cat["totalServiceCharge"] += total
            grouped[kebele]["serviceKebeleTotal"] += total

        elif component == "OPERATION_FEE":
            cat["totalOperationCharge"] += total
            grouped[kebele]["operationKebeleTotal"] += total

        elif component == "PENALTY":
            cat["totalPenalty"] += total
            grouped[kebele]["penaltyKebeleTotal"] += total

    # ---------------------------------------
    # FINAL TOTALS
    # ---------------------------------------
    for kebele, data in grouped.items():
        for cat in data["categoryReports"].values():
            cat_total = (
                cat["totalAmount"]
                + cat["totalMeterRent"]
                + cat["totalServiceCharge"]
                + cat["totalOperationCharge"]
                + cat["totalPenalty"]
            )
            cat["categoryTotal"] = cat_total
            data["kebeleTotal"] += cat_total

        data["categoryReports"] = list(data["categoryReports"].values())

    grand_totals = {
        "billCount": 0,
        "totalConsumption": 0,
        "totalAmount": 0,
        "totalMeterRent": 0,
        "totalServiceCharge": 0,
        "totalOperationCharge": 0,
        "totalPenalty": 0,
        "grandTotal": 0,
    }

    # ---------------------------------------
    # GRAND TOTAL PER CATEGORY
    # ---------------------------------------
    category_totals = {}

    for kebele, data in grouped.items():
        for cat in data["categoryReports"]:
            category = cat["customerCategory"]

            if category not in category_totals:
                category_totals[category] = {
                    "customerCategory": category,
                    "billCount": 0,
                    "totalConsumption": 0,
                    "totalAmount": 0,
                    "totalMeterRent": 0,
                    "totalServiceCharge": 0,
                    "totalOperationCharge": 0,
                    "totalPenalty": 0,
                    "categoryTotal": 0,
                }

            agg = category_totals[category]

            agg["billCount"] += cat["billCount"]
            agg["totalConsumption"] += cat["totalConsumption"]
            agg["totalAmount"] += cat["totalAmount"]
            agg["totalMeterRent"] += cat["totalMeterRent"]
            agg["totalServiceCharge"] += cat["totalServiceCharge"]
            agg["totalOperationCharge"] += cat["totalOperationCharge"]
            agg["totalPenalty"] += cat["totalPenalty"]
            agg["categoryTotal"] += cat["categoryTotal"]

    # convert to list for template
    category_totals_list = list(category_totals.values())

    # ---------------------------------------
    # GRAND TOTAL (EXCLUDES MIN/MAX)
    # ---------------------------------------
    for kebele, data in grouped.items():
        grand_totals["billCount"] += data["billCountKebeleTotal"]
        grand_totals["totalConsumption"] += data["consumptionKebeleTotal"]
        grand_totals["totalAmount"] += data["consCostKebeleTotal"]
        grand_totals["totalMeterRent"] += data["rentKebeleTotal"]
        grand_totals["totalServiceCharge"] += data["serviceKebeleTotal"]
        grand_totals["totalOperationCharge"] += data["operationKebeleTotal"]
        grand_totals["totalPenalty"] += data["penaltyKebeleTotal"]
        grand_totals["grandTotal"] += data["kebeleTotal"]

    # ---------------------------------------
    # PAGINATION
    # ---------------------------------------
    reports = list(grouped.values())
    paginator = Paginator(reports, 5)
    page_obj = paginator.get_page(page)

    months = range(1, 13)
    year = timezone.now().year
    years = range(year - 5, year + 1)

    return render(request, "reports/kebele_category_report.html", {
        "page_obj": page_obj,
        "reportsGroupedByKebele": page_obj.object_list,
        "selectedMonth": int(month) if month else 0,
        "selectedYear": int(year),
        "months": months,
        "years": years,
        "grandTotals": grand_totals,
        "categoryTotals": category_totals_list,
    })

