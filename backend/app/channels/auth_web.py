"""Staff login. Patient-facing channels never touch this — see
app/services/auth.py's module docstring for the scope boundary.

Uses the standard OAuth2-password-flow shape (form-encoded
username/password, not JSON) specifically so FastAPI's /docs "Authorize"
button works out of the box for manual testing — `username` holds the
staff member's email.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Doctor, User
from app.services.auth import authenticate_staff, create_access_token, get_current_staff_user

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class MeResponse(BaseModel):
    id: int
    email: str
    role: str
    full_name: str | None = None
    doctor_id: int | None = None


@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> TokenResponse:
    user = authenticate_staff(db, form_data.username, form_data.password)
    if user is None:
        # Deliberately identical error for "no such user" and "wrong
        # password" - don't help an attacker enumerate valid emails.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    token = create_access_token(user)
    return TokenResponse(access_token=token, role=user.role.value)


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_staff_user), db: Session = Depends(get_db)) -> MeResponse:
    doctor = db.query(Doctor).filter_by(user_id=user.id).one_or_none()
    return MeResponse(
        id=user.id,
        email=user.email,
        role=user.role.value,
        full_name=doctor.full_name if doctor else None,
        doctor_id=doctor.id if doctor else None,
    )
