# utility/urls.py
from django.urls import include, path

from . import views

urlpatterns = [
    
    #path("", views.landing_page, name="landing"),
    path("", views.portal_home, name="portal_home"),
    path("customers/", include("customers.urls")),
    path("meters/", include("customers.urls")),
    path("b/", include("bills.urls")),

]
