from sqlalchemy.orm import Session

from app.models import Department


def list_departments(db: Session) -> list[Department]:
    return db.query(Department).order_by(Department.name).all()


def get_department_by_name(db: Session, name: str) -> Department | None:
    """Case-insensitive exact match, used to validate LLM triage output."""
    return db.query(Department).filter(Department.name.ilike(name)).one_or_none()
