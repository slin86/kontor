"""Registration, login, logout and "who am I" endpoints."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from kontor.api.deps import CurrentSession, CurrentUser, DbSession
from kontor.core.config import get_settings
from kontor.core.security import (
    hash_password,
    needs_rehash,
    new_token,
    token_digest,
    verify_password,
)
from kontor.models import AuthSession, Household, User
from kontor.schemas.auth import HouseholdOut, LoginRequest, MeOut, RegisterRequest, UserOut
from kontor.services.categories import seed_default_categories

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Verified against when the e-mail is unknown, so timing does not reveal valid accounts.
_DUMMY_HASH = hash_password("kontor-dummy-password")


def _start_session(db: DbSession, response: Response, user: User) -> None:
    settings = get_settings()
    token, csrf = new_token(), new_token()
    expires = datetime.now(UTC) + timedelta(days=settings.session_ttl_days)
    db.add(
        AuthSession(
            user_id=user.id,
            token_digest=token_digest(token),
            csrf_digest=token_digest(csrf),
            expires_at=expires,
        )
    )
    max_age = settings.session_ttl_days * 86400
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    # Readable by the frontend, which echoes it back in the X-CSRF-Token header.
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _me(user: User) -> MeOut:
    return MeOut(
        user=UserOut.model_validate(user),
        household=HouseholdOut.model_validate(user.household),
    )


@router.post("/register", response_model=MeOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, response: Response, db: DbSession) -> MeOut:
    if bool(body.household_name) == bool(body.invite_code):
        raise HTTPException(
            422,
            "Provide exactly one of household_name or invite_code",
        )
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "E-mail already registered")

    if body.invite_code:
        household = db.scalar(select(Household).where(Household.invite_code == body.invite_code))
        if household is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid invite code")
    else:
        household = Household(name=body.household_name or "", invite_code=new_token())
        db.add(household)
        db.flush()
        seed_default_categories(db, household.id)

    user = User(
        household_id=household.id,
        email=body.email,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()
    db.refresh(household)
    _start_session(db, response, user)
    return _me(user)


@router.post("/login", response_model=MeOut)
def login(body: LoginRequest, response: Response, db: DbSession) -> MeOut:
    user = db.scalar(select(User).where(User.email == body.email))
    stored = user.password_hash if user else _DUMMY_HASH
    if not verify_password(stored, body.password) or user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid e-mail or password")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    _start_session(db, response, user)
    return _me(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(auth: CurrentSession, response: Response, db: DbSession) -> None:
    settings = get_settings()
    db.delete(auth)
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser, request: Request) -> MeOut:
    return _me(user)
