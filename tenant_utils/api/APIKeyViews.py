from rest_framework.decorators import (api_view, authentication_classes,
                                       permission_classes)
from rest_framework.response import Response

from .authentication import APIKeyAuthentication
from .permissions import HasAPIKey


@api_view(["POST"])
@authentication_classes([APIKeyAuthentication])
@permission_classes([HasAPIKey])
def external_create_meter_reading(request):
    #auditLog and system log is very important here
    
    meter_id = request.data.get("meter")
    reading_value = request.data.get("reading_value")
    print(meter_id, reading_value)
    # call your service
    #reading = MeterReadingService.create_reading(...)

    serializer = "" #MeterReadingSerializer(reading)

     #Response(serializer.data, status=201)
    return Response({"q":"a"}, status=201)