# core/mixins.py
class TenantAwareCreateMixin:
    def form_valid(self, form):
        form.instance.tenant = self.request.tenant
        return super().form_valid(form)
