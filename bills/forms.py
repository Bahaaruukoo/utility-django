from django import forms

from bills.models import BillingSettings, MeterReading


class MeterReadingForm(forms.ModelForm):
    class Meta:
        model = MeterReading
        fields = ["meter", "reading_value"]

    def __init__(self, *args, **kwargs):
        tenant = kwargs.pop("tenant")
        super().__init__(*args, **kwargs)

        # Only show meters belonging to this tenant
        self.fields["meter"].queryset = (
            self.fields["meter"]
            .queryset
            .filter(tenant=tenant)
        )

class BillingSettingsForm(forms.ModelForm):

    class Meta:
        model = BillingSettings
        fields = [
            "late_fee_rate",
            "meter_rental_fee",
            "billing_cycle_days",
            "bill_overdue_in_days",
            "service_charge_fee",
            "manual_bill_generation",
            "bill_generation_date",
            "operation_charge_fee",
        ]

    def clean_bill_generation_date(self):
        value = self.cleaned_data["bill_generation_date"]

        if value < 1 or value > 28:
            raise forms.ValidationError(
                "Bill generation date must be between 1 and 28."
            )

        return value
