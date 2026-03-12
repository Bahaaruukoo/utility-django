from django.urls import include, path

from bills.views import (MeterReadingCreateView, MeterReadingListView,
                         bill_detail, bill_detail_print, bill_list,
                         edit_billing_settings, mark_bill_sold,
                         meter_reading_detail, meter_reading_edit, void_bill)

urlpatterns = [
    path("create/", MeterReadingCreateView.as_view(), name="meter_reading_create"),
    path("readings/", MeterReadingListView.as_view(), name="meter_reading_list"),
    path("readings/<int:pk>/", meter_reading_detail, name="meter_reading_detail"),
    path("readings/<int:pk>/edit/", meter_reading_edit, name="meter_reading_edit"),
    path("settings/edit/", edit_billing_settings, name="edit_billing_settings"),
    path("bills/", bill_list, name="bill-list"),
    path("bills/<int:pk>/", bill_detail, name="bill-detail"),
    path("bills/<int:pk>/print/", bill_detail_print, name="bill-detail-print"),
    path("bills/<int:pk>/sell/", mark_bill_sold, name="bill-sell"),
    path("bills/<int:pk>/void/", void_bill, name="bill_void"),

    #path("unpaid/", views.unpaid_bills_view, name="unpaid_bills"),
] 
