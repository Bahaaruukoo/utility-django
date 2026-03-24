from django.urls import path

from . import views

urlpatterns = [
    path("customer/find/", views.customer_search, name="customer_search"),
    path("customer/all/", views.customer_list_, name="customer_list"),
    path("customer/new/", views.customer_create, name="customer_a_create"),
    path("customer/<str:customer_no>/", views.customer_detail, name="customer_detail"),
    path("customer/<str:customer_no>/edit/", views.customer_update, name="customer_update"),
    path("meter/", views.meter_list, name="meter_list"),
    path("meter/new/", views.meter_create, name="meter_create"),
    path("meter/assigns/", views.meter_assignment_list, name="meter_assignment_list"),
    path("meter/<int:pk>/edit/", views.meter_update, name="meter_update"),
    path("meter/assigns/new/", views.assign_meter, name="assign_meter"),
    path("meter/assigns/<int:pk>/", views.meter_assignment_detail, name="meter_assignment_detail"),
    path("meter/assigns/<int:pk>/edit/", views.meter_assignment_update, name="meter_assignment_update"),
    path("meter/assigns/<int:pk>/close/", views.close_assignment, name="close_assignment"),
]
