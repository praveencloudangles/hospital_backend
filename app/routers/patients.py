from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles, require_any_staff
from app.models import User, Role, Patient
from app.schemas.schemas import PatientOut, PatientUpdate

router = APIRouter(prefix="/api/patients", tags=["patients"])


@router.get("", response_model=List[PatientOut])
def list_patients(
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_staff),
):
    query = db.query(Patient).join(Patient.user).options(joinedload(Patient.user))
    if q:
        like = f"%{q}%"
        query = query.filter((User.full_name.ilike(like)) | (User.email.ilike(like)))
    return query.order_by(Patient.id.desc()).all()


@router.get("/me", response_model=PatientOut)
def my_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != Role.patient:
        raise HTTPException(403, "Only patients have a patient profile")
    p = db.query(Patient).options(joinedload(Patient.user)).filter(Patient.user_id == user.id).first()
    if not p:
        raise HTTPException(404, "Patient profile not found")
    return p


@router.patch("/me", response_model=PatientOut)
def update_my_profile(
    payload: PatientUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != Role.patient:
        raise HTTPException(403, "Only patients have a patient profile")
    p = db.query(Patient).filter(Patient.user_id == user.id).first()
    if not p:
        raise HTTPException(404, "Patient profile not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(
    patient_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = db.query(Patient).options(joinedload(Patient.user)).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(404, "Patient not found")
    if user.role == Role.patient and p.user_id != user.id:
        raise HTTPException(403, "Forbidden")
    return p


@router.patch("/{patient_id}", response_model=PatientOut)
def update_patient(
    patient_id: int,
    payload: PatientUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin, Role.receptionist, Role.doctor)),
):
    p = db.get(Patient, patient_id)
    if not p:
        raise HTTPException(404, "Patient not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p
