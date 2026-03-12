# utility/urls.py
from django.urls import include, path

from . import views

urlpatterns = [
    
    path("", views.portal_home, name="home"),
    path("customers/", include("customers.urls")),
    path("meters/", include("customers.urls")),
    path("b/", include("bills.urls")),

]
