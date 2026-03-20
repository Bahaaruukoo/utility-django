from allauth.account.forms import LoginForm
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django_tenants.utils import get_public_schema_name

from core.models import Profile
from tenant_manager.models import Domain, Tenant

from .models import Role, RoleTemplate, TenantRolePermission, TenantUserRole

User = get_user_model()


class CustomSignupForm(forms.Form):
    first_name = forms.CharField(max_length=30, label='First Name')
    last_name = forms.CharField(max_length=30, label='Last Name')
    phone = forms.CharField(max_length=15, label='Phone Number' )
    #address = forms.CharField(widget=forms.Textarea, label='Address' )
    #department = forms.CharField(max_length=100, label='Department' )
    #position = forms.CharField(max_length=100, label='Position')

    def signup(self, request, user):
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.save()

        phone = self.cleaned_data['phone']
        profile = Profile(user=user, phone=phone)
        profile.save()


class CreateTenantForm(forms.Form):
    """Form for platform admins to create a new tenant with admin user."""
    
    # Tenant fields
    tenant_name = forms.CharField(
        max_length=100,
        label='Tenant Name',
        help_text='The display name for the tenant'
    )
    schema_name = forms.CharField(
        max_length=63,
        label='Schema Name',
        help_text='Database schema name (lowercase, alphanumeric and underscores only)',
        required=False
    )
    domain = forms.CharField(
        max_length=253,
        label='Domain',
        help_text='Domain name for the tenant (e.g., tenant1.example.com)'
    )
    on_trial = forms.BooleanField(
        required=False,
        initial=True,
        label='On Trial',
        help_text='Mark tenant as being on trial period'
    )
    
    # Admin user fields
    admin_email = forms.EmailField(
        label='Admin Email',
        help_text='Email address for the tenant admin user'
    )
    admin_password = forms.CharField(
        widget=forms.PasswordInput,
        label='Admin Password',
        help_text='Password for the tenant admin user',
        min_length=8
    )
    admin_password_confirm = forms.CharField(
        widget=forms.PasswordInput,
        label='Confirm Password',
        help_text='Re-enter the password to confirm'
    )
    admin_phone = forms.CharField(
        max_length=15,
        label='Phone Number',
        required=False,
        help_text='Optional phone number for the admin user'
    )
    
    def clean_schema_name(self):
        schema_name = self.cleaned_data.get('schema_name')
        if not schema_name:
            # Generate schema name from tenant name
            tenant_name = self.cleaned_data.get('tenant_name', '')
            schema_name = tenant_name.lower().replace(' ', '_').replace('-', '_')
            # Remove special characters
            schema_name = ''.join(c for c in schema_name if c.isalnum() or c == '_')
            if not schema_name:
                raise ValidationError('Could not generate schema name from tenant name. Please provide one manually.')
        
        schema_name = schema_name.lower()
        
        # Validate schema name format
        if not schema_name.replace('_', '').isalnum():
            raise ValidationError('Schema name can only contain lowercase letters, numbers, and underscores.')
        
        if schema_name.startswith('pg_'):
            raise ValidationError('Schema name cannot start with "pg_"')
        
        # Check if schema already exists
        connection.set_schema_to_public()
        if Tenant.objects.filter(schema_name=schema_name).exists():
            raise ValidationError(f'Schema name "{schema_name}" already exists.')
        
        return schema_name
    
    def clean_domain(self):
        domain = self.cleaned_data.get('domain')
        if not domain:
            return domain
        
        # Remove protocol and port if present
        domain = domain.replace('http://', '').replace('https://', '')
        domain = domain.split(':')[0].split('/')[0].strip()
        
        # Check if domain already exists
        connection.set_schema_to_public()
        if Domain.objects.filter(domain=domain).exists():
            raise ValidationError(f'Domain "{domain}" is already in use.')
        
        return domain
    
    def clean_admin_email(self):
        email = self.cleaned_data.get('admin_email')
        if not email:
            return email
        
        # Check if user already exists
        connection.set_schema_to_public()
        if User.objects.filter(email=email).exists():
            # User exists, that's okay - we'll add them to the tenant
            pass
        
        return email
    
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('admin_password')
        password_confirm = cleaned_data.get('admin_password_confirm')
        
        if password and password_confirm and password != password_confirm:
            raise ValidationError({
                'admin_password_confirm': 'Passwords do not match.'
            })
        
        return cleaned_data
    
    def save(self):
        """Create tenant, domain, and admin user."""
        # Ensure we're on public schema
        connection.set_schema_to_public()
        
        # Create tenant
        tenant = Tenant(
            name=self.cleaned_data['tenant_name'],
            schema_name=self.cleaned_data['schema_name'],
            on_trial=self.cleaned_data.get('on_trial', False)
        )
        tenant.save()  # This automatically creates the schema
        
        # Create domain
        domain = Domain(
            domain=self.cleaned_data['domain'],
            tenant=tenant,
            is_primary=True
        )
        domain.save()
        
        # Create or get admin user
        email = self.cleaned_data['admin_email']
        try:
            user = User.objects.get(email=email)
            # User exists, update password
            user.set_password(self.cleaned_data['admin_password'])
        except User.DoesNotExist:
            # Create new user using the manager's create_user method
            # Note: CustomUser doesn't have first_name/last_name fields
            user = User.objects.create_user(
                email=email,
                password=self.cleaned_data['admin_password'],
            )
        
        # Set staff and active status
        user.is_staff = True
        user.is_active = True
        user.save()
        
        # Create or update profile with phone (if provided)
        if self.cleaned_data.get('admin_phone'):
            profile, created = Profile.objects.get_or_create(
                user=user,
                defaults={'phone': self.cleaned_data['admin_phone']}
            )
            # Update profile if it already existed
            if not created:
                profile.phone = self.cleaned_data['admin_phone']
                profile.save()
        
        # Create tenant membership with TENANT_ADMIN role
        # Ensure we're on public schema for TenantUser (it's in shared apps)
        connection.set_schema_to_public()
       
        return tenant, domain, user

# core/forms.py



class InviteRegisterForm(forms.Form):
    
    first_name = forms.CharField(max_length=50, required=True, label="First name")
    middle_name = forms.CharField(max_length=50, required=False, label="Middle name")
    last_name = forms.CharField(max_length=50, required=True, label="Last name")

    password1 = forms.CharField(
        widget=forms.PasswordInput,
        label="Password",
        required=True
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput,
        label="Confirm password",
        required=True
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")

        if p1 and p2 and p1 != p2:
            raise ValidationError("Passwords do not match.")
        return cleaned


class SendInviteForm(forms.Form):
    email = forms.EmailField(label="Invitee Email")
    #role = forms.ChoiceField(choices=Role.choices, label="Role")
    role = forms.ModelChoiceField(
        queryset=Role.objects.all(),
        empty_label="Select Role"
    )



class TenantLoginForm(LoginForm):

    def clean(self):
        cleaned = super().clean()
        user = self.user
        tenant = getattr(self.request, "tenant", None)

        if user.is_platform_admin:
            if tenant:
                raise forms.ValidationError(
                    "Platform administrators must login on public domain."
                )

        else:
            if not tenant:
                raise forms.ValidationError(
                    "Tenant users must login on tenant domain."
                )

            if user.tenant_id != tenant.id:
                raise forms.ValidationError(
                    "You do not belong to this tenant."
                )

        return cleaned

class TenantUserRoleInlineForm(forms.ModelForm):
    class Meta:
        model = TenantUserRole
        fields = ("role",)   # ONLY ROLE

class ProfileInlineForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("phone", "address", "department", "position", "picture")
        widgets = {
            # 3-line textarea
            "address": forms.Textarea(attrs={"rows": 3}),
        }

class ProfileForm(forms.ModelForm):

    class Meta:
        model = Profile
        fields = [
            "phone",
            "address",
            "department",
            "position",
            "picture",
        ]

        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
        }



class TenantRolePermissionAdminForm(forms.ModelForm):

    template = forms.ModelChoiceField(
        queryset=RoleTemplate.objects.all(),
        required=False,
        help_text="Select a template to populate permissions."
    )

    class Meta:
        model = TenantRolePermission
        fields = "__all__"

