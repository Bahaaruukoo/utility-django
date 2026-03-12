from django import forms


class AuditExportForm(forms.Form):
    date_from = forms.DateField(required=False)
    date_to = forms.DateField(required=False)