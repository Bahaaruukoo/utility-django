from django.urls import include, path

from bills.views import (MeterReadingCreateView,  # edit_billing_settings,
                         MeterReadingListView, bill_detail, bill_detail_print,
                         bill_list, manual_bill_generation, mark_bill_sold,
                         meter_reading_detail, meter_reading_edit, void_bill)

urlpatterns = [
    path("readings/", MeterReadingListView.as_view(), name="meter_reading_list"),
    path("readings/create/", MeterReadingCreateView.as_view(), name="meter_reading_create"),
    path("readings/<int:pk>/", meter_reading_detail, name="meter_reading_detail"),
    path("readings/<int:pk>/edit/", meter_reading_edit, name="meter_reading_edit"),
    #path("settings/edit/", edit_billing_settings, name="edit_billing_settings"),
    path("bills/", bill_list, name="bill-list"),
    path("bills/<int:pk>/", bill_detail, name="bill-detail"),
    path("bills/<int:pk>/print/", bill_detail_print, name="bill-detail-print"),
    path("bills/<int:pk>/sell/", mark_bill_sold, name="bill-sell"),
    path("bills/<int:pk>/void/", void_bill, name="bill_void"),
    path("bills/generate/<int:pk>/", manual_bill_generation, name="generate_bill"),

    #path("unpaid/", views.unpaid_bills_view, name="unpaid_bills"),
] 
