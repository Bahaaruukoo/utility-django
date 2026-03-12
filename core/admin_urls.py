# core/admin_urls.py
from django.urls import path

from .admin_views import send_invitation_view

urlpatterns = [
    #ath("customuser/<int:user_id>/send-invite/", send_invitation_view, name="send_invitation"),
    path("<int:tenant_id>/send-invite/", send_invitation_view, name="send_invitation"),
]
