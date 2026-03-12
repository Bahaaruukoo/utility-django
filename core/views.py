from allauth.account import app_settings
from allauth.account.views import LoginView, SignupView
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, connection, transaction
from django.http import HttpResponseForbidden, HttpResponseRedirect
# core/views.py
from django.shortcuts import get_object_or_404, redirect, render

from core.audit import audit, log_audit
from core.models_audit import AuditAction
from tenant_manager.models import Domain, Tenant
from utility import settings

from .forms import CreateTenantForm, InviteRegisterForm, ProfileForm
from .models import CustomUser, Invitation, Profile, Role, TenantUserRole

User = get_user_model()

class CustomSignupView_(SignupView):
    def form_valid(self, form):
                
        response = super().form_valid(form)

        if app_settings.EMAIL_VERIFICATION == app_settings.EmailVerificationMethod.MANDATORY:
            messages.info(self.request, "Email verification has been sent. Please check your inbox.")
        else:
            messages.success(self.request, "Your account has been created successfully.")
        return response

@login_required
def home(request):
    if getattr(request.user, "is_platform_admin", False):
        return redirect("/admin/")
    if getattr(request.user, "is_tenant_admin", False):
        return redirect("/admin/")
    if getattr(request.user, "is_branch_admin", False):
        return redirect("/admin/")
    return redirect("/portal/")


class InviteSignupView(SignupView):
    def dispatch(self, request, *args, **kwargs):
        # Switch to public schema to access invitations
        connection.set_schema_to_public()
        self.invite = get_object_or_404(
            Invitation,
            token=kwargs["token"],
            used=False
        )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # Ensure we're on public schema
        connection.set_schema_to_public()
        
        user = form.save(self.request)

        # Force correct identity
        user.email = self.invite.email
        user.is_staff = True
        user.save()

        self.invite.used = True
        self.invite.save()

        return super().form_valid(form)

class TenantLoginView(LoginView):

    def form_invalid(self, form):
        print("LOGIN ERRORS:", form.errors)
        return super().form_invalid(form)

    def _current_tenant(self, request):
        return getattr(request, "tenant", None)

    def _redirect_after_login(self, request, user):
        """
        Final redirect logic after successful login.
        """

        # Platform admin → always platform admin
        if getattr(user, "is_platform_admin", False):
            return HttpResponseRedirect("/admin/")

        # Tenant users → portal
        return HttpResponseRedirect("/portal/")

    # --------------------------------------------------
    # Already authenticated user hitting login page
    # --------------------------------------------------
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            tenant = self._current_tenant(request)

            # If on tenant domain, enforce boundary
            if tenant and not getattr(request.user, "is_platform_admin", False):
                if request.user.tenant_id != tenant.id:
                    logout(request)
                    return HttpResponseForbidden("You do not have access to this tenant.")

            return self._redirect_after_login(request, request.user)

        return super().dispatch(request, *args, **kwargs)

    # --------------------------------------------------
    # Successful login
    # --------------------------------------------------
    def form_valid(self, form):
        response = super().form_valid(form)

        request = self.request
        user = request.user
        tenant = self._current_tenant(request)

        # -----------------------
        # Platform admin
        # -----------------------
        if getattr(user, "is_platform_admin", False):
            return HttpResponseRedirect("/admin/")

        # -----------------------
        # Login on tenant domain
        # -----------------------
        if tenant:
            if user.tenant_id != tenant.id:
                logout(request)
                messages.error(request, "You do not have access to this tenant.")
                return redirect("account_login")

            return HttpResponseRedirect("/portal/")

        # -----------------------
        # Login on public domain
        # Redirect tenant user to their tenant domain
        # -----------------------
        if not user.tenant_id:
            logout(request)
            messages.error(request, "You are not assigned to any tenant.")
            return redirect("account_login")

        user_tenant = user.tenant
        dom = user_tenant.domains.first()

        if not dom:
            logout(request)
            messages.error(request, "Tenant domain is not configured.")
            return redirect("account_login")

        scheme = "https" if request.is_secure() else "http"
        host = dom.domain

        port = request.get_port()
        if port and port not in ("80", "443") and ":" not in host:
            host = f"{host}:{port}"

        return HttpResponseRedirect(f"{scheme}://{host}/portal/")

class TenantSelectionForm(forms.Form):
    tenant = forms.ModelChoiceField(
        queryset=Tenant.objects.none(),
        widget=forms.RadioSelect,
        empty_label=None
    )


@login_required
def select_tenant(request):
    """
    Allow users with multiple tenant memberships to select which tenant to access.
    This view should only be accessible from the public schema.
    """
    # Ensure we're on public schema - switch if needed
    connection.set_schema_to_public()
    
    if request.user.is_platform_admin:
        # Platform admins can access any tenant, show all
        connection.set_schema_to_public()
        tenants = Tenant.objects.all()
    else:
        # Regular users can only see their tenants
        connection.set_schema_to_public()
        tenant_memberships = request.user.tenant_memberships.select_related('tenant').all()
        tenants = [tm.tenant for tm in tenant_memberships]
    
    if not tenants:
        messages.error(request, "You are not a member of any tenant.")
        from django.contrib.auth import logout
        logout(request)
        return redirect('account_login')
    
    # If only one tenant, redirect directly
    if len(tenants) == 1:
        tenant = tenants[0]
        domain = tenant.domains.first()
        if domain:
            scheme = 'http' if not request.is_secure() else 'https'
            port = request.META.get('SERVER_PORT', '')
            if port and port not in ['80', '443']:
                tenant_url = f"{scheme}://{domain.domain}:{port}/"
            else:
                tenant_url = f"{scheme}://{domain.domain}/"
            return HttpResponseRedirect(tenant_url)
    
    if request.method == 'POST':
        form = TenantSelectionForm(request.POST)
        form.fields['tenant'].queryset = Tenant.objects.filter(id__in=[t.id for t in tenants])
        
        if form.is_valid():
            tenant = form.cleaned_data['tenant']
            domain = tenant.domains.first()
            if domain:
                scheme = 'http' if not request.is_secure() else 'https'
                port = request.META.get('SERVER_PORT', '')
                if port and port not in ['80', '443']:
                    tenant_url = f"{scheme}://{domain.domain}:{port}/"
                else:
                    tenant_url = f"{scheme}://{domain.domain}/"
                return HttpResponseRedirect(tenant_url)
    else:
        form = TenantSelectionForm()
        form.fields['tenant'].queryset = Tenant.objects.filter(id__in=[t.id for t in tenants])
    
    return render(request, 'core/select_tenant.html', {'form': form, 'tenants': tenants})


@login_required
def create_tenant(request):
    """
    Platform admin interface to create a new tenant with admin user.
    """
    # Check if user is platform admin
    if not request.user.is_platform_admin:
        messages.error(request, "Only platform administrators can create tenants.")
        return redirect('home')
    
    if request.method == 'POST':
        form = CreateTenantForm(request.POST)
        if form.is_valid():
            try:
                tenant, domain, user = form.save()
                # Build the login URL for the tenant
                scheme = 'http' if not request.is_secure() else 'https'
                port = request.META.get('SERVER_PORT', '')
                if port and port not in ['80', '443']:
                    login_url = f"{scheme}://{domain.domain}:{port}/accounts/login/"
                else:
                    login_url = f"{scheme}://{domain.domain}/accounts/login/"
                
                messages.success(
                    request,
                    f'Tenant "{tenant.name}" created successfully!<br>'
                    f'<strong>Admin Email:</strong> {user.email}<br>'
                    f'<strong>Tenant Domain:</strong> {domain.domain}<br>'
                    f'<strong>Login URL:</strong> <a href="{login_url}" target="_blank">{login_url}</a><br>'
                    f'<small>Please use the tenant domain URL to log in.</small>',
                    extra_tags='safe'
                )
                return redirect('create_tenant')
            except Exception as e:
                messages.error(request, f'Error creating tenant: {str(e)}')
    else:
        form = CreateTenantForm()
    
    return render(request, 'core/create_tenant.html', {'form': form})

@login_required
def profile_view(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    return render(request, 'core/profile_view.html', {'profile': profile})

@login_required
@transaction.atomic
def profile_edit(request):

    profile, _ = Profile.objects.get_or_create(
        user=request.user
    )

    if request.method == "POST":
        form = ProfileForm(
            request.POST,
            request.FILES,
            instance=profile
        )

        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect("profile-view")

    else:
        form = ProfileForm(instance=profile)

    return render(request, "core/profile_edit.html", {
        "form": form
    })

@login_required
def account_dashboard(request):
    return render(request, "core/account_dashboard.html")

@login_required
def debug_user_tenant(request):
    """
    Debug view to check user's tenant memberships.
    Only accessible to platform admins.
    """
    if not request.user.is_platform_admin:
        messages.error(request, "Only platform administrators can access this page.")
        return redirect('home')
    
    connection.set_schema_to_public()
    
    # Get email from query parameter
    email = request.GET.get('email', '')
    debug_info = {}
    
    if email:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(email=email)
            debug_info['user'] = user
            debug_info['is_active'] = user.is_active
            debug_info['is_staff'] = user.is_staff
            debug_info['is_platform_admin'] = user.is_platform_admin
            debug_info['tenant_memberships'] = list(user.tenant_memberships.select_related('tenant').all())
            debug_info['tenants'] = [tm.tenant for tm in debug_info['tenant_memberships']]
        except User.DoesNotExist:
            debug_info['error'] = f'User with email {email} not found'
    
    return render(request, 'core/debug_user_tenant.html', {'debug_info': debug_info, 'email': email})

@audit(AuditAction.INVITE_ACCEPTED)
def register_invitee(request, token):
    invitation = get_object_or_404(Invitation, token=token, used=False)

    if request.method == "POST":
        form = InviteRegisterForm(request.POST)
        if form.is_valid():
            email = invitation.email
            tenant = invitation.tenant
            role = invitation.role

            try:
                user = CustomUser.objects.create_user(
                    email=email,
                    password=form.cleaned_data["password1"],
                    tenant=tenant,
                    first_name=form.cleaned_data["first_name"],
                    middle_name=form.cleaned_data["middle_name"],
                    last_name=form.cleaned_data["last_name"],
                )
            except IntegrityError:
                messages.error(request, "A user with this email already exists.")
                return redirect(request.path)

            # allow tenant admin login (if your tenant admins use /admin on tenant domain)
            user.is_active = True
            user.is_staff = True
            user.save()

            # assign role safely (ignore duplicates)
            TenantUserRole.objects.get_or_create(
                user=user,
                tenant=tenant,
                role=role,
            )

            invitation.used = True
            invitation.save(update_fields=["used"])

            """
            log_audit(
                tenant=invitation.tenant,
                actor=user,  # or request.user (after login)
                action=AuditAction.INVITE_ACCEPTED,
                target=user,
                request=request,
                metadata={"invitation_token": str(invitation.token), "role": invitation.role.name},
            )
"""


            # Optional: auto-login immediately
            #login(request, user)
            auth_user = authenticate(
                request,
                username=user.email,   # email is USERNAME_FIELD
                password=form.cleaned_data["password1"],
            )

            if auth_user is not None:
                login(request, auth_user)

            messages.success(request, "Registration successful. You are now logged in.")
            return redirect("/admin/")  # or "/admin_tenant/" depending on your setup

    else:
        form = InviteRegisterForm()

    return render(request, "core/register_invitee.html", {
        "invitation": invitation,
        "form": form,
    })
    invitation = get_object_or_404(Invitation, token=token, used=False)

    if request.method == "POST":
        password = request.POST.get("password")
        if not password:
            messages.error(request, "Password is required.")
            return redirect(request.path)

        with transaction.atomic():
            user, created = User.objects.get_or_create(email=invitation.email)

            # ✅ force tenant boundary
            user.tenant = invitation.tenant  # may be None (platform invite)
            user.is_active = True

            # If invited to tenant, allow tenant admin login
            if invitation.tenant_id:
                user.is_staff = True

            user.set_password(password)
            user.save()

            # ✅ assign role using TenantUserRole (if you have it)
            if invitation.tenant_id:
                TenantUserRole.objects.get_or_create(
                    user=user,
                    tenant=invitation.tenant,
                    role=invitation.role,
                )

            invitation.used = True
            invitation.save(update_fields=["used"])

        messages.success(request, f"Account created for {user.email}. You can now log in.")
        return redirect("/admin/login/")  # will be tenant admin if host is tenant domain

    return render(request, "core/register_invitee.html", {"invitation": invitation})