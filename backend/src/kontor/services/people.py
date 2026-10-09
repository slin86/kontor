"""Depot owners (persons) of a household."""

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kontor.models import Person, User


def add_person(db: Session, household_id: int, name: str, user: User | None = None) -> Person:
    """Create a person behind everyone else in the household."""
    last = db.scalar(select(func.max(Person.sort_order)).where(Person.household_id == household_id))
    person = Person(
        household_id=household_id,
        name=name.strip(),
        user_id=user.id if user else None,
        sort_order=(last + 1) if last is not None else 0,
    )
    db.add(person)
    db.flush()
    return person


def own_person(db: Session, user: User) -> Person:
    """The person that belongs to a signed-in user (created on the fly for older accounts)."""
    person = db.scalar(
        select(Person).where(Person.user_id == user.id, Person.household_id == user.household_id)
    )
    if person is None:
        person = add_person(db, user.household_id, user.display_name, user)
    return person


def list_people(db: Session, household_id: int) -> list[Person]:
    return list(
        db.scalars(
            select(Person)
            .where(Person.household_id == household_id)
            .order_by(Person.sort_order, Person.id)
        )
    )


def get_person(db: Session, household_id: int, person_id: int) -> Person:
    person = db.get(Person, person_id)
    if person is None or person.household_id != household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person nicht gefunden")
    return person
