from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import APIKey


class APIKeyAuthentication(BaseAuthentication):

    def authenticate(self, request):
        api_key = request.headers.get("X-API-KEY")

        if not api_key:
            return None

        try:
            key = APIKey.objects.select_related("tenant").get(
                key=api_key,
                is_active=True
            )
            request.tenant = key.tenant
        except APIKey.DoesNotExist:
            raise AuthenticationFailed("Invalid API Key")
        
        return (None, key)