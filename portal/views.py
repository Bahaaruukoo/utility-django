# Create your views here.
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from bills.models import Bill
from customers.models import Customer, Meter, MeterAssignment


@login_required
def portal_home(request):

    tenant = request.tenant
    branch = getattr(request, "branch", None)

    customers = Customer.objects.filter(tenant=tenant)
    meters = Meter.objects.filter(tenant=tenant)
    assignments = MeterAssignment.objects.filter(tenant=tenant, is_active=True)
    unpaid_bills = Bill.objects.filter(tenant=tenant, status="UNSOLD")

    if branch:
        assignments = assignments.filter(branch=branch)

    context = {
        "total_customers": customers.count(),
        "total_meters": meters.count(),
        "active_assignments": assignments.count(),
        "unpaid_bills": unpaid_bills.count()
    }

    return render(request, "portal/home.html", context)
