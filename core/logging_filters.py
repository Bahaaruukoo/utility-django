import logging

from .log_context import get_context


class ContextFilter(logging.Filter):

    def filter(self, record):

        ctx = get_context()

        record.tenant = ctx["tenant"]
        record.branch = ctx["branch"]
        record.user = ctx["user"]
        record.request_id = ctx["request_id"]

        return True