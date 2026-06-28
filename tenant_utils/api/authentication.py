from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import APIKey, hash_key

class APIKeyAuthentication(BaseAuthentication):

    def authenticate(self, request):

        api_key = request.headers.get("X-API-KEY")

        if not api_key:
            return None

        prefix = api_key[:8]

        try:
            key_obj = APIKey.objects.select_related("tenant", "branch").get(
                prefix=prefix,
                is_active=True
            )
        except APIKey.DoesNotExist:
            raise AuthenticationFailed("Invalid API Key")

        # Verify hash
        if key_obj.hashed_key != hash_key(api_key):
            raise AuthenticationFailed("Invalid API Key")

        # attach tenant & branch
        request.tenant = key_obj.tenant
        request.branch = key_obj.branch

        return (None, key_obj)