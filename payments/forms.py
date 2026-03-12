from django import forms


class PaymentReversalForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea,
        required=True
    )