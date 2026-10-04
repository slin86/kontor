"""Shared FastAPI dependencies: current session/user and CSRF enforcement."""

import hmac
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from kontor.core.config import get_settings
from kontor.core.db import get_db
from kontor.core.security import token_digest
from kontor.models import AuthSession, User

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

DbSession = Annotated[Session, Depends(get_db)]


def _aware(dt: datetime) -> datetime:
    # SQLite returns naive datetimes; treat them as UTC.
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def get_auth_session(request: Request, db: DbSession) -> AuthSession:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    auth = db.scalar(select(AuthSession).where(AuthSession.token_digest == token_digest(token)))
    if auth is None or _aware(auth.expires_at) <= datetime.now(UTC):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")

    if request.method not in SAFE_METHODS:
        header = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(token_digest(header), auth.csrf_digest):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid")
    return auth


CurrentSession = Annotated[AuthSession, Depends(get_auth_session)]


def get_current_user(auth: CurrentSession) -> User:
    return auth.user


CurrentUser = Annotated[User, Depends(get_current_user)]
