from django.urls import path

from payments import views
from payments.external_payments_views import external_payment_webhook
from reports.views import print_session_report_view

urlpatterns = [
    path("open/", views.open_session_view, name="open_session"),
    path("request-close/", views.request_close_view, name="request_close"),
    path("approve/<int:session_id>/", views.approve_close_view, name="approve_close"),

    # 🧾 Cashier dashboard
    path("dashboard/", views.cashier_dashboard, name="cashier_dashboard"),

    # 🔓 Open session
    path("open/submit/", views.open_session_view, name="open_session_page"), # POST submit

    # 🖨 Print session report
    path("session/<int:session_id>/print/", print_session_report_view,name="print_session_report"),
    path("session/sales/", views.cashier_session_sales_view, name="cashier_session_sales"),

    # 👨‍💼 Supervisor views supervisor_dashboard
    path("supervisor/dashboard/", views.supervisor_dashboard_view, name="supervisor_dashboard"),
    path("supervisor/pending/", views.pending_sessions_view, name="pending_sessions"),
    path("supervisor/session/<int:session_id>/", views.session_approval_view, name="session_approval"),
    path("supervisor/session/<int:session_id>/sales/", views.session_sales_view, name="session_sales"),
    path("search/", views.bill_search_view, name="bill_search"),
    path("receipt/<int:receipt_id>/print/", views.print_receipt_view, name="print_receipt"),
    path("<int:bill_id>/pay/", views.pay_bill_view, name="pay_bill"),
    path("webhook/external-payment/", external_payment_webhook), # External payment webhook
    path("payments/", views.payment_list_view, name="payment_list"),

    path("reverse/<int:payment_id>/", views.reverse_payment_view, name="reverse_payment"),
    path("reversal/search/", views.my_pending_reversal_requests_view, name="reversal_payment_search"),
    path("reversal/status/", views.my_pending_reversal_requests_status_view, name="reversal_payment_status"),
    path("reversal/request/<int:payment_id>/", views.request_reversal_view, name="request_reversal"),
    path("reversal/pending/", views.pending_reversal_requests_view, name="pending_reversals"),
    path("reversal/review/<int:request_id>/", views.review_reversal_view, name="review_reversal"),
    #path("reversal/reverse/<int:request_id>/", views.review_reversal_view, name="review_reversal"),

]