# core/admin_views.py

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.forms import SendInviteForm
from core.models import Invitation, Role
from tenant_manager.models import Tenant


@staff_member_required
def send_invitation_view(request, tenant_id):
    """
    Platform or tenant admin sends invitation to a user for a specific tenant.
    """
    tenant = get_object_or_404(Tenant, pk=tenant_id)

    # Tenant admin can send invite only for their tenant
    if not getattr(request.user, "is_platform_admin", False):
        if getattr(request.user, "tenant", None) != tenant:
            messages.error(request, "You can only invite users for your tenant.")
            return redirect("admin:index")

    if request.method == "POST":
        form = SendInviteForm(request.POST)
        if form.is_valid():
            invite = Invitation.objects.create(
                email=form.cleaned_data["email"],
                tenant=tenant,
                role=form.cleaned_data["role"]
            )

            invite_url = request.build_absolute_uri(
                reverse("register_invitee", kwargs={"token": invite.token})
            )

            send_mail(
                subject=f"Invitation to join {tenant.name}",
                message=f"Hello! You have been invited to join {tenant.name}.\nClick here: {invite_url}",
                from_email="noreply@yourapp.com",
                recipient_list=[invite.email],
                fail_silently=False,
            )

            messages.success(request, f"Invitation sent to {invite.email}")
            return redirect(reverse("admin:tenant_manager_tenant_change", args=[tenant.id]))
    else:
        form = SendInviteForm()

    return render(request, "core/admin_send_invite.html", {"form": form, "tenant": tenant})
