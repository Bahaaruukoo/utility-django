import threading

_local = threading.local()

def set_context(tenant=None, branch=None, user=None, request_id=None):
    _local.tenant = tenant
    _local.branch = branch
    _local.user = user
    _local.request_id = request_id


def get_context():
    return {
        "tenant": getattr(_local, "tenant", "public"),
        "branch": getattr(_local, "branch", "None"),
        "user": getattr(_local, "user", "anonymous"),
        "request_id": getattr(_local, "request_id", "-"),
    }