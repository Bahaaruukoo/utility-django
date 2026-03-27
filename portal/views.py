# Create your views here.
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from bills.models import Bill
from customers.models import Customer, Meter, MeterAssignment


def landing_page(request):
    if request.user and request.user.is_authenticated:
        #return redirect("home")
        if getattr(request.user, "is_platform_admin", False):
            return redirect("/admin/")
        if getattr(request.user, "is_admin", False): #tenant admin
            return redirect("/admin/")
        if getattr(request.user, "is_branch_admin", False):
            return redirect("/admin/")
        return redirect("/portal/")
    return render(request, "portal/landing_page.html", {})
     

@login_required
def portal_home(request):
    if getattr(request.user, "is_platform_admin", False):
        return redirect("/admin/")
    if getattr(request.user, "is_admin", False): #tenant admin
        return redirect("/admin/")
    if getattr(request.user, "is_branch_admin", False):
        return redirect("/admin/")
    
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


def csrf_failure(request, reason=""):
    return render(request, "403_csrf.html", status=403)



def bad_request(request, exception):
    return render(request, "400.html", status=400)

def permission_denied(request, exception):
    return render(request, "403.html", status=403)

def page_not_found(request, exception):
    return render(request, "404.html", status=404)

def server_error(request):
    return render(request, "500.html", status=500)
