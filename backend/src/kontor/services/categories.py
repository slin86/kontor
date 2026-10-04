"""Default category tree created for every new household."""

from sqlalchemy.orm import Session

from kontor.models import Category, CategoryKind

# (group name, kind, children)
DEFAULT_TREE: list[tuple[str, CategoryKind, list[str]]] = [
    ("Gehalt", CategoryKind.INCOME, []),
    ("Kindergeld", CategoryKind.INCOME, []),
    ("Sonstige Einnahmen", CategoryKind.INCOME, []),
    ("Wohnen", CategoryKind.EXPENSE, ["Nebenkosten", "Strom und Gas", "Internet und Handy"]),
    ("Mobilität", CategoryKind.EXPENSE, ["Auto", "Nahverkehr"]),
    ("Lebensmittel", CategoryKind.EXPENSE, []),
    ("Versicherungen", CategoryKind.EXPENSE, []),
    ("Kinder", CategoryKind.EXPENSE, ["Kita und Schule", "Kleidung und Material"]),
    ("Freizeit und Urlaub", CategoryKind.EXPENSE, []),
    ("Abos", CategoryKind.EXPENSE, []),
]


def seed_default_categories(db: Session, household_id: int) -> None:
    order = 0
    for name, kind, children in DEFAULT_TREE:
        parent = Category(household_id=household_id, name=name, kind=kind, sort_order=order)
        db.add(parent)
        db.flush()
        order += 1
        for child in children:
            db.add(
                Category(
                    household_id=household_id,
                    parent_id=parent.id,
                    name=child,
                    kind=kind,
                    sort_order=order,
                )
            )
            order += 1
