from django.urls import path

from . import views

urlpatterns = [
    path("", views.customer_list_, name="customer_list"),
    path("new/", views.customer_create, name="customer_a_create"),
    path("<uuid:customer_no>/", views.customer_detail, name="customer_detail"),
    path("<uuid:customer_no>/edit/", views.customer_update, name="customer_update"),
    path("m/", views.meter_list, name="meter_list"),
    path("m/new/", views.meter_create, name="meter_create"),
    path("m/assigns/", views.meter_assignment_list, name="meter_assignment_list"),
    path("m/<int:pk>/edit/", views.meter_update, name="meter_update"),
    path("m/assigns/new/", views.assign_meter, name="assign_meter"),
    path("m/assigns/<int:pk>/", views.meter_assignment_detail, name="meter_assignment_detail"),
    path("m/assigns/<int:pk>/edit/", views.meter_assignment_update, name="meter_assignment_update"),
    path("m/assigns/<int:pk>/close/", views.close_assignment, name="close_assignment"),
]
