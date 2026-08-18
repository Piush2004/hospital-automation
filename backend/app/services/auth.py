"""Staff-only JWT auth.

Deliberately narrow scope: patient-facing channels (web chat, WhatsApp,
voice, CLI) stay phone-identified, not authenticated — that's
intentional (see CLAUDE.md), not something this module touches. This is
purely for the staff surfaces added in Phase 9: doctor/front_desk/admin
login, gating the doctor and admin dashboards and /internal/push-live.

Also the first place in this codebase to use FastAPI's Depends(get_db)
pattern instead of SessionLocal() directly (see CLAUDE.md deviations on
why every other channel uses SessionLocal() — this is deliberately the
exception, so the new auth/dashboard routes can get real TestClient +
test-DB-override pytest coverage instead of only being live-verified).
"""

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User, UserRole

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

STAFF_ROLES = (UserRole.doctor, UserRole.front_desk, UserRole.admin)


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(user: User) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user.id), "role": user.role.value, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def authenticate_staff(db: Session, email: str, password: str) -> User | None:
    """Returns the User if email/password match an active staff account,
    else None. Deliberately doesn't distinguish "wrong password" from
    "no such user" in its return value — that distinction shouldn't leak
    to a login response either (see auth_web.py).
    """
    user = db.query(User).filter_by(email=email).one_or_none()
    if user is None or not user.is_active:
        return None
    if user.role not in STAFF_ROLES:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_staff_user(token: str | None = Depends(_oauth2_scheme), db: Session = Depends(get_db)) -> User:
    if token is None:
        raise _CREDENTIALS_EXCEPTION
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if user_id is None:
            raise _CREDENTIALS_EXCEPTION
    except JWTError:
        raise _CREDENTIALS_EXCEPTION

    user = db.get(User, int(user_id))
    if user is None or not user.is_active or user.role not in STAFF_ROLES:
        raise _CREDENTIALS_EXCEPTION
    return user


def require_roles(*roles: UserRole):
    """FastAPI dependency factory: require_roles(UserRole.admin) etc.
    Layered on top of get_current_staff_user (which already restricts to
    STAFF_ROLES) for endpoint-specific narrowing, e.g. the doctor
    dashboard only accepting UserRole.doctor.
    """

    def dependency(user: User = Depends(get_current_staff_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency
