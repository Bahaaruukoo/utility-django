# core/session_utils.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from django.contrib.sessions.models import Session
from django.utils import timezone


@dataclass
class UserSessionInfo:
    session_key: str
    expire_date: object
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    last_path: Optional[str] = None


def _decode_session(session: Session) -> dict:
    """
    Safely decode Django DB session.
    """
    try:
        return session.get_decoded()
    except Exception:
        return {}


def list_active_sessions_for_user(user) -> List[UserSessionInfo]:
    """
    Returns non-expired sessions that belong to this user.
    """
    now = timezone.now()
    qs = Session.objects.filter(expire_date__gt=now).order_by("-expire_date")

    results: List[UserSessionInfo] = []
    user_id_str = str(user.pk)

    for s in qs:
        data = _decode_session(s)
        if data.get("_auth_user_id") == user_id_str:
            results.append(
                UserSessionInfo(
                    session_key=s.session_key,
                    expire_date=s.expire_date,
                    ip=data.get("ip"),
                    user_agent=data.get("ua") or data.get("user_agent"),
                    last_path=data.get("path"),
                )
            )

    return results


def revoke_all_sessions_for_user(user) -> int:
    """
    Deletes all non-expired sessions for this user.
    Returns number of deleted sessions.
    """
    now = timezone.now()
    qs = Session.objects.filter(expire_date__gt=now)

    user_id_str = str(user.pk)
    to_delete = []

    for s in qs:
        data = _decode_session(s)
        if data.get("_auth_user_id") == user_id_str:
            to_delete.append(s.session_key)

    if not to_delete:
        return 0

    deleted, _ = Session.objects.filter(session_key__in=to_delete).delete()
    return deleted
