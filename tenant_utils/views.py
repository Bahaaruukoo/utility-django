from django.http import Http404
# Create your views here.
# tenant_utils/views.py
from django.shortcuts import redirect, render

from tenant_utils.models import Branch


def select_branch(request, branch_code):
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Tenant not found")

    branch = Branch.objects.filter(tenant=tenant, code=branch_code).first()
    if not branch:
        raise Http404("Branch not found")

    request.session["active_branch_id"] = branch.id
    return redirect("/admin/")
