from django import forms

from tenant_utils.models import Branch

from .models import Customer, Meter, MeterAssignment


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            "first_name",
            "middle_name",
            "last_name",
            "phone",
            "email",
            "address",
            "id_number",
            "id_image",
            "customer_type",
            "delegation_letter",
            "is_active",
            "woreda",
            "kebele",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
        }

class MeterForm(forms.ModelForm):

    class Meta:
        model = Meter
        fields = [
            "meter_number",
            "meter_size",
            "meter_type",
            "status",
            "initial_reading",
        ]

    def __init__(self, *args, **kwargs):
        edit_mode = kwargs.pop("edit_mode", False)
        super().__init__(*args, **kwargs)

        # 🔒 Prevent meter_number change after creation
        if edit_mode:
            self.fields["meter_number"].disabled = True

    def clean_initial_reading(self):
        value = self.cleaned_data.get("initial_reading")
        if value < 0:
            raise forms.ValidationError("Initial reading cannot be negative.")
        return value



class MeterAssignmentForm(forms.ModelForm):

    class Meta:
        model = MeterAssignment
        fields = "__all__"
        '''fields = [
            "customer",
            "meter",
            "installation_address",
            "building_name",
            "apartment_no",
            "city",
            "state",
            "country",
            "latitude",
            "longitude",
            "installation_date",
            "start_date",
            "is_active",
        ]'''
        widgets = {
            "installation_date": forms.DateInput(
                format="%d-%m-%Y",
                attrs={"class": "form-control", "placeholder": "dd-mm-yyyy"}
            ),
            "start_date": forms.DateInput(
                format="%d-%m-%Y",
                attrs={"class": "form-control", "placeholder": "dd-mm-yyyy"}
            ),
            "removal_date": forms.DateInput(
                format="%d-%m-%Y",
                attrs={"class": "form-control", "placeholder": "dd-mm-yyyy"}
            ),
            "end_date": forms.DateInput(
                format="%d-%m-%Y",
                attrs={"class": "form-control", "placeholder": "dd-mm-yyyy"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ["installation_date", "start_date", "removal_date", "end_date"]:
            if self.instance.pk and getattr(self.instance, field):
                self.fields[field].initial = getattr(self.instance, field).strftime("%d-%m-%Y")
    
    def __init__(self, *args, **kwargs):
        tenant = kwargs.pop("tenant", None)
        branch = kwargs.pop("branch", None)
        super().__init__(*args, **kwargs)

        if tenant:
            # Only active meters
            self.fields["meter"].queryset = Meter.objects.filter(
                tenant=tenant,
                #branch=branch,
                status="ACTIVE"
            )

            self.fields["customer"].queryset = Customer.objects.filter(
                tenant=tenant,
                #branch=branch,
                is_active=True
            )
    
        