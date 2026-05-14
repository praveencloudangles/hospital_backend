from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles, get_current_user
from app.core.security import hash_password
from app.models import User, Role, Patient, Doctor
from app.schemas.schemas import RegisterIn, UserOut, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=List[UserOut])
def list_users(
    role: Optional[Role] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin)),
):
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    if q:
        like = f"%{q}%"
        query = query.filter((User.full_name.ilike(like)) | (User.email.ilike(like)))
    return query.order_by(User.id.desc()).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: RegisterIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin)),
):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        phone=payload.phone,
    )
    db.add(user)
    db.flush()

    if payload.role == Role.patient:
        db.add(
            Patient(
                user_id=user.id,
                dob=payload.dob,
                gender=payload.gender,
                blood_group=payload.blood_group,
                address=payload.address,
            )
        )
    elif payload.role == Role.doctor:
        db.add(
            Doctor(
                user_id=user.id,
                specialization=payload.specialization or "General",
                qualification=payload.qualification,
                consultation_fee=payload.consultation_fee or 0,
            )
        )

    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin)),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    me: User = Depends(require_roles(Role.admin)),
):
    if user_id == me.id:
        raise HTTPException(400, "Cannot delete yourself")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    db.delete(user)
    db.commit()
