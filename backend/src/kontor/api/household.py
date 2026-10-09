"""Household administration: members, invite code and the signed-in user's own account."""

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from kontor.api.auth import _blocked, _client, by_ip
from kontor.api.deps import CurrentSession, CurrentUser, DbSession
from kontor.core.security import hash_password, new_token, verify_password
from kontor.models import AuthSession, Household, Person, User
from kontor.services.audit import record as audit
from kontor.services.households import create_household, member_users, memberships
from kontor.services.people import add_person

router = APIRouter(prefix="/api", tags=["household"])


class MemberOut(BaseModel):
    id: int
    email: str
    display_name: str
    is_me: bool


class HouseholdDetail(BaseModel):
    id: int
    name: str
    invite_code: str
    members: list[MemberOut]


class HouseholdIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ProfileIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


def _household(db: DbSession, user: User) -> Household:
    household = db.get(Household, user.household_id)
    assert household is not None
    return household


def _detail(db: DbSession, user: User) -> HouseholdDetail:
    household = _household(db, user)
    members = member_users(db, household.id)
    return HouseholdDetail(
        id=household.id,
        name=household.name,
        invite_code=household.invite_code,
        members=[
            MemberOut(id=m.id, email=m.email, display_name=m.display_name, is_me=m.id == user.id)
            for m in members
        ],
    )


@router.get("/household", response_model=HouseholdDetail)
def get_household(user: CurrentUser, db: DbSession) -> HouseholdDetail:
    return _detail(db, user)


@router.put("/household", response_model=HouseholdDetail)
def rename_household(body: HouseholdIn, user: CurrentUser, db: DbSession) -> HouseholdDetail:
    household = _household(db, user)
    before = {"name": household.name}
    household.name = body.name.strip()
    audit(db, user, "update", "household", household.id, before=before, after={"name": body.name})
    return _detail(db, user)


@router.post("/household/invite-code", response_model=HouseholdDetail)
def renew_invite_code(user: CurrentUser, db: DbSession) -> HouseholdDetail:
    """Replace the invite code; the old one stops working at once."""
    household = _household(db, user)
    household.invite_code = new_token()
    audit(db, user, "invite_code_renew", "household", household.id)
    return _detail(db, user)


@router.delete("/household/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(user_id: int, user: CurrentUser, db: DbSession) -> None:
    """Take a member's access away. Their depot stays as a person without a login."""
    if user_id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Du kannst dich nicht selbst entfernen.")
    member = db.get(User, user_id)
    person = db.scalar(
        select(Person).where(Person.user_id == user_id, Person.household_id == user.household_id)
    )
    if member is None or person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mitglied nicht gefunden")
    person.user_id = None
    db.flush()
    audit(
        db, user, "member_remove", "user", member.id, before={"display_name": member.display_name}
    )
    remaining = memberships(db, member)
    if remaining:  # the account lives on in its other households
        if member.household_id == user.household_id:
            member.household_id = remaining[0].id
        return
    db.execute(delete(AuthSession).where(AuthSession.user_id == member.id))
    db.delete(member)


class HouseholdBrief(BaseModel):
    id: int
    name: str
    is_active: bool


class NewHouseholdIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class JoinIn(BaseModel):
    invite_code: str = Field(min_length=1, max_length=64)


def _briefs(db: DbSession, user: User) -> list[HouseholdBrief]:
    return [
        HouseholdBrief(id=h.id, name=h.name, is_active=h.id == user.household_id)
        for h in memberships(db, user)
    ]


@router.get("/households", response_model=list[HouseholdBrief])
def list_households(user: CurrentUser, db: DbSession) -> list[HouseholdBrief]:
    """All households of the account; each one has its own data, people and categories."""
    return _briefs(db, user)


@router.post(
    "/households", response_model=list[HouseholdBrief], status_code=status.HTTP_201_CREATED
)
def new_household(body: NewHouseholdIn, user: CurrentUser, db: DbSession) -> list[HouseholdBrief]:
    """Create a further household and switch to it."""
    household = create_household(db, user, body.name)
    audit(db, user, "create", "household", household.id, after={"name": household.name})
    return _briefs(db, user)


@router.post("/households/join", response_model=list[HouseholdBrief])
def join_household(
    body: JoinIn, request: Request, user: CurrentUser, db: DbSession
) -> list[HouseholdBrief]:
    """Join an existing household with its invite code and switch to it."""
    ip = _client(request)
    _blocked(by_ip.retry_after(f"invite:{ip}"))
    household = db.scalar(select(Household).where(Household.invite_code == body.invite_code))
    if household is None:
        by_ip.fail(f"invite:{ip}")
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Der Einladungscode ist ungültig.")
    if household not in memberships(db, user):
        add_person(db, household.id, user.display_name, user)
        user.household_id = household.id
        audit(db, user, "member_join", "household", household.id)
    else:
        user.household_id = household.id
    return _briefs(db, user)


@router.post("/households/{household_id}/switch", response_model=list[HouseholdBrief])
def switch_household(household_id: int, user: CurrentUser, db: DbSession) -> list[HouseholdBrief]:
    """Work in another household of the account."""
    if household_id not in {h.id for h in memberships(db, user)}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Haushalt nicht gefunden")
    user.household_id = household_id
    return _briefs(db, user)


@router.put("/auth/profile", response_model=MemberOut)
def update_profile(body: ProfileIn, user: CurrentUser, db: DbSession) -> MemberOut:
    user.display_name = body.display_name.strip()
    for person in db.scalars(select(Person).where(Person.user_id == user.id)):
        person.name = user.display_name
    return MemberOut(id=user.id, email=user.email, display_name=user.display_name, is_me=True)


@router.post("/auth/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: PasswordIn, auth: CurrentSession, user: CurrentUser, db: DbSession, response: Response
) -> None:
    """Change the password and sign out every other device."""
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Das aktuelle Passwort stimmt nicht.")
    user.password_hash = hash_password(body.new_password)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.id != auth.id))
