from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User, Role, Patient, Doctor
from app.schemas.schemas import LoginIn, RegisterIn, Token, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _issue_token(user: User) -> Token:
    token = create_access_token(user.id, user.role.value)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.post("/register", response_model=Token)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Public self-registration is restricted to patient role.
    # Staff/admin/doctor accounts are created by an admin via /api/users.
    if payload.role != Role.patient:
        raise HTTPException(status_code=403, detail="Only patient self-registration is allowed")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=Role.patient,
        phone=payload.phone,
    )
    db.add(user)
    db.flush()

    db.add(
        Patient(
            user_id=user.id,
            dob=payload.dob,
            gender=payload.gender,
            blood_group=payload.blood_group,
            address=payload.address,
        )
    )
    db.commit()
    db.refresh(user)
    return _issue_token(user)


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    return _issue_token(user)


@router.post("/login-json", response_model=Token)
def login_json(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    return _issue_token(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
