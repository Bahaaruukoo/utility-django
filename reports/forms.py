import datetime
from datetime import date

# reports/forms.py
from django import forms

from tenant_utils.models import Branch


class BillingReportForm(forms.Form):
    today = datetime.date.today()
    current_year = today.year

    YEAR_CHOICES = [
        (y, y) for y in range(current_year, current_year - 11, -1)
    ]

    year = forms.ChoiceField(
        choices=YEAR_CHOICES,
        initial=current_year,
        widget=forms.Select(attrs={"class": "form-select"})
    )

    month = forms.ChoiceField(
        choices=[(m, m) for m in range(1, 12 + 1)],
        initial=today.month,
        widget=forms.Select(attrs={"class": "form-select"})
    )

    def clean_year(self):
        return int(self.cleaned_data["year"])

    def clean_month(self):
        return int(self.cleaned_data["month"])


class CollectionReportForm(forms.Form):

    today = date.today()
    current_year = today.year

    # Month dropdown
    MONTH_CHOICES = [
        (1, "January"),
        (2, "February"),
        (3, "March"),
        (4, "April"),
        (5, "May"),
        (6, "June"),
        (7, "July"),
        (8, "August"),
        (9, "September"),
        (10, "October"),
        (11, "November"),
        (12, "December"),
    ]

    month = forms.ChoiceField(
        choices=MONTH_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"})
    )

    # Year dropdown (current year → 10 years back)
    year = forms.ChoiceField(
        choices=[
            (y, y)
            for y in range(current_year, current_year - 11, -1)
        ],
        widget=forms.Select(attrs={"class": "form-select"})
    )

    branch = forms.ModelChoiceField(
        queryset=Branch.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"})
    )

    def __init__(self, *args, **kwargs):
        tenant = kwargs.pop("tenant", None)
        super().__init__(*args, **kwargs)

        if tenant:
            self.fields["branch"].queryset = Branch.objects.filter(
                tenant=tenant
            )

from django import forms

from tenant_utils.models import Branch


class SessionReportForm(forms.Form):

    start_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"})
    )

    end_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"})
    )

    branch = forms.ModelChoiceField(
        queryset=Branch.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"})
    )

    def __init__(self, *args, **kwargs):
        tenant = kwargs.pop("tenant", None)
        super().__init__(*args, **kwargs)

        if tenant:
            self.fields["branch"].queryset = Branch.objects.filter(tenant=tenant)

