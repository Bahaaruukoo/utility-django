# core/urls.py
from django.urls import include, path

from .views import register_invitee

urlpatterns = [
    #path("invite/<uuid:token>/", invite_register, name="invite_register"),
    path("register-invite/<uuid:token>/", register_invitee, name="register_invitee"),
    path("portal/", include("portal.urls")),
    path("payments/", include("payments.urls")),
    path("reports/", include("reports.urls")),
]
