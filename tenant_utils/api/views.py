from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from bills.services import MeterReadingService
from customers.models import Meter
from tenant_utils.models import BranchMembership

from .serializers import MeterReadingSerializer


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_meter_reading(request):

    user = request.user
    tenant = request.tenant
    membership = BranchMembership.objects.filter(
        tenant=request.tenant,
        user=request.user,
        is_active=True
    ).select_related("branch").first()
    print(membership)
    print(user)
    print(request.branch)
    print(tenant)
    branch = membership.branch

    meter_number = request.data.get("meter")
    reading_value = request.data.get("reading_value")

    from decimal import Decimal, InvalidOperation

    try:
        reading_value = Decimal(str(reading_value))
    except (InvalidOperation, TypeError, ValueError):
        return Response(
            {"error": "Invalid reading value"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not meter_number:
        return Response(
            {"error": "Meter is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        meter = Meter.objects.get(meter_number=meter_number, tenant=tenant)
    except Meter.DoesNotExist:
        return Response(
            {"error": "Meter not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        reading = MeterReadingService.create_reading(
            tenant=tenant,
            branch=branch,
            meter=meter,
            reading_value=reading_value,
            reader=user
        )

    except IntegrityError as e:
        return Response(
            {"error": "A reading for this meter on this date already exists."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    serializer = MeterReadingSerializer(reading)
    return Response(serializer.data, status=201)


