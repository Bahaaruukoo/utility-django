import json
from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from payments.models import CashierSession
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

    if month_param:

        month = int(month_param)

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
            "month": month_param,
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
                user=request.user, force=True
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

