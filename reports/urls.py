from django.urls import path

from .views import (billing_report_detail, billing_report_generate,
                    collection_report_detail, collection_report_generate,
                    dashboard, debt_aging_report, print_session_report_view,
                    session_financial_report, statistics_view)

urlpatterns = [
    path("statistics/monthly/", statistics_view, name="monthly_statistics"),
    path("billing/generate/", billing_report_generate, name="billing_report_generate"),

    path("billing/<int:report_id>/", billing_report_detail, name="billing_report_detail"),
    path("collections/generate/", collection_report_generate, name="collection_report_generate"),
    path("collections/<int:report_id>/", collection_report_detail, name="collection_report_detail"),
    path("debt-aging/", debt_aging_report,name="debt_aging_report"),
    path("session/", session_financial_report, name="report_cashier_sessions"),
    path("session/<int:session_id>", print_session_report_view, name="report_cashier_sessions_print"),
    path("dashboard/", dashboard, name="report_dashboard"),
]