from sqlalchemy.orm import Session

from app.models import AuditLog


def log_action(
    db: Session,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    details: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=details,
    )
    db.add(entry)
    db.flush()
    return entry
