"""Append-only audit trail."""

from typing import Any

from sqlalchemy.orm import Session

from kontor.models import AuditLog, User


def record(
    db: Session,
    user: User,
    action: str,
    entity: str,
    entity_id: int,
    *,
    reason: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            household_id=user.household_id,
            user_id=user.id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            reason=reason,
            before=before,
            after=after,
        )
    )
