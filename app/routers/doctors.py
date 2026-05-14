from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import User, Role, Doctor
from app.schemas.schemas import DoctorOut, DoctorUpdate

router = APIRouter(prefix="/api/doctors", tags=["doctors"])


@router.get("", response_model=List[DoctorOut])
def list_doctors(
    specialization: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(Doctor).join(Doctor.user).options(joinedload(Doctor.user))
    if specialization:
        query = query.filter(Doctor.specialization.ilike(f"%{specialization}%"))
    if q:
        like = f"%{q}%"
        query = query.filter((User.full_name.ilike(like)) | (Doctor.specialization.ilike(like)))
    return query.order_by(Doctor.id.desc()).all()


@router.get("/me", response_model=DoctorOut)
def my_doctor_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != Role.doctor:
        raise HTTPException(403, "Only doctors")
    d = db.query(Doctor).options(joinedload(Doctor.user)).filter(Doctor.user_id == user.id).first()
    if not d:
        raise HTTPException(404, "Doctor profile not found")
    return d


@router.patch("/me", response_model=DoctorOut)
def update_my_doctor_profile(
    payload: DoctorUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != Role.doctor:
        raise HTTPException(403, "Only doctors")
    d = db.query(Doctor).filter(Doctor.user_id == user.id).first()
    if not d:
        raise HTTPException(404, "Doctor profile not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(d, k, v)
    db.commit()
    db.refresh(d)
    return d


@router.get("/{doctor_id}", response_model=DoctorOut)
def get_doctor(doctor_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    d = db.query(Doctor).options(joinedload(Doctor.user)).filter(Doctor.id == doctor_id).first()
    if not d:
        raise HTTPException(404, "Doctor not found")
    return d


@router.patch("/{doctor_id}", response_model=DoctorOut)
def update_doctor(
    doctor_id: int,
    payload: DoctorUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin)),
):
    d = db.get(Doctor, doctor_id)
    if not d:
        raise HTTPException(404, "Doctor not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(d, k, v)
    db.commit()
    db.refresh(d)
    return d
