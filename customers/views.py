from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

#from forms import CustomerForm
from customers.forms import CustomerForm
from customers.models import Customer, Kebele, MeterAssignment
from tenant_utils.decorators import permission

from .forms import CustomerForm, MeterAssignmentForm, MeterForm
from .models import (Customer, CustomerActivationDeactivation, Meter,
                     MeterAssignment)
from .services import create_customer

User = get_user_model()

@login_required
@permission("customers.view_customer")
def customer_list(request):
    customers = Customer.objects.all()

    # Tenant already isolated by schema

    # Branch restriction
    if getattr(request, "branch", None):
        customers = customers.filter(
            meter_assignments__branch=request.branch,
            meter_assignments__is_active=True
        ).distinct()

    search = request.GET.get("q")
    if search:
        customers = customers.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(phone__icontains=search)
        )

    context = {
        "customers": customers,
        "search": search
    }
    return render(request, "customers/customer_list.html", context)


@login_required
@permission("customers.add_customer")
def customer_create(request):
    if request.method == "POST":
        form = CustomerForm(request.POST, request.FILES)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.tenant = request.tenant
            customer.registered_by = request.user
            customer.save()
            messages.success(request, "Customer registered successfully.")
            return redirect("customer_list")
    else:
        form = CustomerForm()

    return render(request, "customers/customer_form.html", {"form": form})


@login_required
@permission("customers.view_customer")
def customer_detail(request, customer_no):

    # 🔒 Tenant Isolation
    customer = get_object_or_404(
        Customer,
        customer_no=customer_no,
        tenant=request.tenant
    )

    
    # 📊 Active Assignment
    active_assignment = customer.meter_assignments.filter(
        is_active=True
    ).select_related("meter", "branch").first()

    # 📜 Assignment History
    assignment_history = customer.meter_assignments.select_related(
        "meter", "branch"
    ).order_by("-start_date")

    context = {
        "customer": customer,
        "active_assignment": active_assignment,
        "assignment_history": assignment_history,
    }

    return render(request, "customers/customer_detail.html", context)


@login_required
@permission("customers.change_customer")
def customer_update(request, customer_no):

    customer = get_object_or_404(
        Customer,
        customer_no=customer_no,
        tenant=request.tenant
    )

    next_url = request.GET.get("next") or request.POST.get("next")
    old_status = customer.is_active

    if request.method == "POST":
        form = CustomerForm(request.POST, request.FILES, instance=customer)
        reason = request.POST.get("status_reason")

        if form.is_valid():
            updated_customer = form.save(commit=False)
            new_status = updated_customer.is_active

            # 🔥 If status changed
            if old_status != new_status:

                # 🔥 If reason missing → reopen modal
                if not reason:
                    return render(request, "customers/customer_form.html", {
                        "form": form,
                        "customer": customer,
                        "next_url": next_url,
                        "edit_mode": True,
                        "show_status_modal": True,
                    })

                updated_customer.updated_by = request.user
                updated_customer.save()

                # 🔥 Create activation/deactivation log
                CustomerActivationDeactivation.objects.create(
                    tenant=request.tenant,
                    customer=updated_customer,
                    action_by=request.user,
                    reason=reason,
                )

            else:
                updated_customer.updated_by = request.user
                updated_customer.save()

            messages.success(request, "Customer updated successfully.")

            if next_url:
                return redirect(next_url)

            return redirect("customers:customer_list")

    else:
        form = CustomerForm(instance=customer)

    return render(request, "customers/customer_form.html", {
        "form": form,
        "customer": customer,
        "next_url": next_url,
        "edit_mode": True,
    })

@login_required
def customer_list_(request):

    customers = Customer.objects.filter(tenant=request.tenant)

    search = request.GET.get("q")
    if search:
        customers = customers.filter(first_name__icontains=search)

    paginator = Paginator(customers, 10)  # 10 per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "customers/customer_list.html", {
        "page_obj": page_obj,
        "customers": page_obj,   # so existing template works
        "search": search
    })

@login_required
@permission("customers.add_meter")
def meter_create(request):

    if request.method == "POST":
        
        tenant = request.tenant
        branch = request.branch
        if not tenant or not branch:
            messages.error(request, "User has to be part of a branch")
            return render(request, "customers/meter_form.html", {
                "form": form,
                "edit_mode": False
            })
        form = MeterForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    meter = form.save(commit=False)
                    meter.tenant = tenant
                    meter.branch = branch
                    meter.added_by = request.user
                    print( request.tenant)
                    # run model validation, including UniqueConstraint
                    meter.full_clean()

                    meter.save()

                messages.success(request, "Meter created successfully.")
                return redirect("meter_list")

            except ValidationError as e:
                # Show all validation messages
                for field, msgs in e.message_dict.items():
                    for msg in msgs:
                        messages.error(request, msg)
                return render(request, "customers/meter_form.html", {
                    "form": form,
                    "edit_mode": False
                })

    else:
        form = MeterForm()

    return render(request, "customers/meter_form.html", {
        "form": form,
        "edit_mode": False
    })

@login_required
@permission("customers.view_meter")
def meter_list(request):

    tenant = getattr(request, "tenant", None)
    branch = getattr(request, "branch", None)

    if not tenant:
        return render(request, "customers/meter_list.html", {
            "meters": []
        })

 
    # 🔐 Branch restriction
    #if is_branch_admin(request) and branch:
    ''' 
    if not is_tenant_admin(request) and branch:
        assigned_meter_ids = MeterAssignment.objects.filter(
            tenant=tenant,
            branch=branch,
            is_active=True
        ).values_list("meter_id", flat=True)

        meters_under_active_assignment = Meter.objects.filter(id__in=assigned_meter_ids)
    '''
    # 🔎 Search
    search = request.GET.get("q")
    if not search:
        return render(request, "customers/meter_list.html", {})

    # 🔒 Base queryset
    meters = Meter.objects.filter(tenant=tenant)
    meters = meters.filter(
        Q(meter_number__icontains=search) |
        Q(meter_type__icontains=search) |
        Q(meter_size__icontains=search)
    )

    # 🔄 Status filter
    status = request.GET.get("status")
    if status:
        meters = meters.filter(status=status)

    # 📄 Pagination
    paginator = Paginator(meters.order_by("-created_at"), 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "customers/meter_list.html", {
        "page_obj": page_obj,
        "search": search,
        "status": status,
    })

@login_required
@permission("customers.change_meter")
def meter_update(request, pk):

    tenant = getattr(request, "tenant", None)

    if not tenant:
        return HttpResponseForbidden("No tenant.")

    # 🔒 Only tenant admin can edit
    if not is_tenant_admin(request):
        return HttpResponseForbidden("Not allowed.")

    meter = get_object_or_404(
        Meter,
        pk=pk,
        tenant=tenant
    )

    # Optional business rule:
    # Prevent editing if actively assigned
    if MeterAssignment.objects.filter(
        tenant=tenant,
        meter=meter,
        is_active=True
    ).exists():
        messages.error(request, "Cannot edit a meter that is actively assigned.")
        return redirect("meter_list")

    if request.method == "POST":
        form = MeterForm(
            request.POST,
            instance=meter,
            edit_mode=True
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Meter updated successfully.")
            return redirect(request.POST.get("next") or "meter_list")
    else:
        form = MeterForm(instance=meter, edit_mode=True)

    return render(request, "customers/meter_form.html", {
        "form": form,
        "edit_mode": True,
        "meter": meter,
        "next_url": request.GET.urlencode()
    })

def is_branch_admin(request) -> bool:
    """
    Branch admin = staff user who is marked is_branch_admin in BranchMembership
    for the current request.tenant and current request.branch
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_platform_admin", False):
        return False
    if not getattr(user, "is_staff", False):
        return False

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

def is_tenant_admin(request) -> bool:
    u = getattr(request, "user", None)
    return bool(
        u
        and u.is_authenticated
        and getattr(u, "is_staff", False)
        and not getattr(u, "is_platform_admin", False)
    )

@login_required
@permission("customers.add_meterassignment")
def assign_meter(request):

    tenant = getattr(request, "tenant", None)
    branch = getattr(request, "branch", None)

    if not tenant:
        return HttpResponseForbidden("No Account found. Make sure signed in to the right account.")

    if not branch:
        return HttpResponseForbidden("No branch found. You should be part of a branch to assign meters.")
    '''
    # Only tenant admin OR branch admin
    if not (is_tenant_admin(request) or is_branch_admin(request)):
        return HttpResponseForbidden("Not allowed.")'''

    if request.method == "POST":
        form = MeterAssignmentForm(
            request.POST,
            tenant=tenant,
            branch=branch
        )
        assignment = form.instance
        assignment.tenant = tenant
        assignment.branch = branch
        assignment.assigned_by = request.user
        assignment.is_active = True
        print(".......................................1")
        if form.is_valid():
            print(".......................................11")
            is_existing = MeterAssignment.objects.filter(meter=form.data.get("meter"), is_active=True).exists()
            if is_existing:
                form.add_error("meter", "This meter is already actively assigned.")
                messages.error(request, "This meter is already actively assigned.")

                return render(request, "customers/meter_assignment_form.html", {
                    "form": form
                })
            assignment = form.save(commit=False)
            assignment.tenant = tenant
            assignment.branch = branch
            assignment.assigned_by = request.user
            assignment.is_active = True
            assignment.save()
            print(".......................................111")

            messages.success(request, "Meter assigned successfully.")
            return redirect("meter_assignment_list")

    else:
        form = MeterAssignmentForm(
            tenant=tenant,
            branch=branch 
            
        )
        print("...............................11........1")

    return render(request, "customers/meter_assignment_form.html", {
        "form": form
    })


@login_required
@permission("customers.view_meterassignment")
def meter_assignment_list(request):

    tenant = getattr(request, "tenant", None)
    branch = getattr(request, "branch", None)

    if not tenant:
        return render(request, "customers/meter_assignment_list.html", {
            "page_obj": []
        })

    # 🔒 Base queryset (tenant isolation)
    assignments = MeterAssignment.objects.select_related(
        "customer",
        "meter",
        "branch"
    ).filter(
        tenant=tenant
    )

    # 🔐 Branch restriction
    if is_branch_admin(request) and branch:
        assignments = assignments.filter(branch=branch)

    # 🔎 Search
    search = request.GET.get("q")
    if not search:
        return render(request, "customers/meter_assignment_list.html", {})
    
    assignments = assignments.filter(
        Q(customer__first_name__icontains=search) |
        Q(customer__last_name__icontains=search) |
        Q(customer__customer_no__icontains=search) |
        Q(meter__meter_number__icontains=search)
    )

    # 🔄 Status filter
    status = request.GET.get("status")

    if status == "active":
        assignments = assignments.filter(is_active=True)
    elif status == "inactive":
        assignments = assignments.filter(is_active=False)

    # 📄 Pagination
    paginator = Paginator(assignments.order_by("-start_date"), 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "customers/meter_assignment_list.html", {
        "page_obj": page_obj,
        "search": search,
        "status": status,
    })


@login_required
@permission("customers.view_meterassignment")
def meter_assignment_detail(request, pk):

    tenant = getattr(request, "tenant", None)
    branch = getattr(request, "branch", None)

    if not tenant:
        return HttpResponseForbidden("No tenant.")

    assignment = get_object_or_404(
        MeterAssignment.objects.select_related(
            "customer",
            "meter",
            "branch",
            "assigned_by"
        ),
        pk=pk,
        tenant=tenant
    )

    # 🔒 Branch restriction
    if is_branch_admin(request) and branch:
        if assignment.branch != branch:
            return HttpResponseForbidden("Not allowed.")

    return render(request, "customers/meter_assignment_detail.html", {
        "assignment": assignment
    })

@login_required
@permission("customers.change_meterassignment")
def close_assignment(request, pk):

    tenant = getattr(request, "tenant", None)

    assignment = get_object_or_404(
        MeterAssignment,
        pk=pk,
        tenant=tenant,
        is_active=True
    )    

    assignment.is_active = False
    assignment.end_date = timezone.now().date()
    assignment.save()

    messages.success(request, "Assignment closed successfully.")
    return redirect("meter_assignment_detail", pk=pk)


@login_required
@permission("customers.change_meterassignment")
def meter_assignment_update(request, pk):

    tenant = getattr(request, "tenant", None)
    branch = getattr(request, "branch", None)

    if not tenant:
        return HttpResponseForbidden("No tenant context.")

    assignment = get_object_or_404(
        MeterAssignment,
        pk=pk,
        tenant=tenant
    )

    # 🔒 Branch restriction
    if is_branch_admin(request) and branch:
        if assignment.branch != branch:
            return HttpResponseForbidden("Not allowed.")

    # ❗ Prevent editing closed assignment
    if not assignment.is_active:
        messages.error(request, "Closed assignments cannot be edited.")
        return redirect("meter_assignment_detail", pk=assignment.pk)

    if request.method == "POST":
        form = MeterAssignmentForm(
            request.POST,
            instance=assignment,
            tenant=tenant,
            branch=branch
        )

        if form.is_valid():
            updated_assignment = form.save(commit=False)
            updated_assignment.assigned_by = request.user
            updated_assignment.save()

            messages.success(request, "Assignment updated successfully.")
            return redirect("meter_assignment_detail", pk=assignment.pk)

    else:
        form = MeterAssignmentForm(
            instance=assignment,
            tenant=tenant,
            branch=branch
        )

    return render(request, "customers/meter_assignment_form.html", {
        "form": form,
        "assignment": assignment,
        "edit_mode": True
    })
