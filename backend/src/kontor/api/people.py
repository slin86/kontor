"""People of a household: the owners of depot positions, with or without their own login."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from kontor.api.deps import CurrentUser, DbSession
from kontor.models import Asset, CashflowItem, Financing, Instrument, Person
from kontor.services.audit import record as audit
from kontor.services.people import add_person, get_person, list_people, own_person

router = APIRouter(prefix="/api/people", tags=["people"])


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class PersonOut(BaseModel):
    id: int
    name: str
    has_login: bool
    is_me: bool
    positions: int


def _out(db: DbSession, p: Person, me_id: int) -> PersonOut:
    count = db.scalar(select(func.count(Instrument.id)).where(Instrument.person_id == p.id)) or 0
    return PersonOut(
        id=p.id, name=p.name, has_login=p.user_id is not None, is_me=p.id == me_id, positions=count
    )


@router.get("", response_model=list[PersonOut])
def people(user: CurrentUser, db: DbSession) -> list[PersonOut]:
    me = own_person(db, user)
    return [_out(db, p, me.id) for p in list_people(db, user.household_id)]


@router.post("", response_model=PersonOut, status_code=status.HTTP_201_CREATED)
def create_person(body: PersonIn, user: CurrentUser, db: DbSession) -> PersonOut:
    """Add someone without a login, for example a child with their own depot."""
    person = add_person(db, user.household_id, body.name)
    audit(db, user, "create", "person", person.id, after={"name": person.name})
    return _out(db, person, own_person(db, user).id)


@router.put("/{person_id}", response_model=PersonOut)
def rename_person(person_id: int, body: PersonIn, user: CurrentUser, db: DbSession) -> PersonOut:
    person = get_person(db, user.household_id, person_id)
    before = {"name": person.name}
    person.name = body.name.strip()
    audit(db, user, "update", "person", person.id, before=before, after={"name": person.name})
    return _out(db, person, own_person(db, user).id)


@router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(person_id: int, user: CurrentUser, db: DbSession) -> None:
    person = get_person(db, user.household_id, person_id)
    if person.user_id is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Diese Person hat ein Konto. Entferne zuerst das Mitglied im Haushalt.",
        )
    booked = db.scalar(
        select(func.count(CashflowItem.id)).where(
            or_(CashflowItem.person_id == person.id, CashflowItem.transfer_to_id == person.id)
        )
    ) or db.scalar(select(func.count(Financing.id)).where(Financing.person_id == person.id))
    if booked:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Die Person hat noch Cashflow-Posten, Übertragungen oder Finanzierungen. "
            "Lösche oder verschiebe sie zuerst.",
        )
    if db.scalar(select(func.count(Instrument.id)).where(Instrument.person_id == person.id)) or (
        db.scalar(select(func.count(Asset.id)).where(Asset.person_id == person.id))
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Die Person hat noch Depotpositionen oder Vermögenswerte. Lösche sie zuerst.",
        )
    audit(db, user, "delete", "person", person.id, before={"name": person.name})
    db.delete(person)
