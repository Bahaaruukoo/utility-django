# core/session_meta_middleware.py
class SessionMetaMiddleware:
    """
    Stores minimal request info into the session so admin can see it.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if getattr(request, "session", None) is not None:
            if request.user and request.user.is_authenticated:
                # Only set if missing, to avoid rewriting session constantly
                if "ip" not in request.session:
                    request.session["ip"] = self._get_ip(request)
                if "ua" not in request.session:
                    request.session["ua"] = request.META.get("HTTP_USER_AGENT", "")[:500]
                request.session["path"] = request.path[:500]

        return response

    def _get_ip(self, request):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")
