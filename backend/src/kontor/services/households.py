"""Households of an account: it can belong to several, each fully separate."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from kontor.core.security import new_token
from kontor.models import Household, Person, User
from kontor.services.categories import seed_default_categories
from kontor.services.people import add_person


def memberships(db: Session, user: User) -> list[Household]:
    """Every household the account belongs to, oldest first."""
    return list(
        db.scalars(
            select(Household)
            .join(Person, Person.household_id == Household.id)
            .where(Person.user_id == user.id)
            .order_by(Household.id)
        )
    )


def member_users(db: Session, household_id: int) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .join(Person, Person.user_id == User.id)
            .where(Person.household_id == household_id)
            .order_by(User.id)
        )
    )


def create_household(db: Session, user: User, name: str) -> Household:
    """A new, empty household with the account as its first member; it becomes the active one."""
    household = Household(name=name.strip(), invite_code=new_token())
    db.add(household)
    db.flush()
    seed_default_categories(db, household.id)
    add_person(db, household.id, user.display_name, user)
    user.household_id = household.id
    db.flush()
    return household
