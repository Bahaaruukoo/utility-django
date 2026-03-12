from django.urls import path
from rest_framework_simplejwt.views import (TokenObtainPairView,
                                            TokenRefreshView)

from .APIKeyViews import external_create_meter_reading
from .views import create_meter_reading

urlpatterns = [
    path("login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    path("meter-readings/", create_meter_reading, name="meter-reading-create"),
    path("ex-meter-readings/", external_create_meter_reading, name="ex-meter-reading-create"),
]