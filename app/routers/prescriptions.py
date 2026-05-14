from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import (
    User,
    Role,
    Patient,
    Doctor,
    Prescription,
    PrescriptionItem,
    Appointment,
    Notification,
)
from app.schemas.schemas import PrescriptionCreate, PrescriptionOut

router = APIRouter(prefix="/api/prescriptions", tags=["prescriptions"])


def _base_query(db: Session):
    return (
        db.query(Prescription)
        .options(
            joinedload(Prescription.items),
            joinedload(Prescription.patient).joinedload(Patient.user),
            joinedload(Prescription.doctor).joinedload(Doctor.user),
        )
    )


@router.get("", response_model=List[PrescriptionOut])
def list_prescriptions(
    patient_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = _base_query(db)
    if user.role == Role.patient:
        patient = db.query(Patient).filter(Patient.user_id == user.id).first()
        if not patient:
            raise HTTPException(404, "Patient profile missing")
        q = q.filter(Prescription.patient_id == patient.id)
    elif user.role == Role.doctor:
        doctor = db.query(Doctor).filter(Doctor.user_id == user.id).first()
        if not doctor:
            raise HTTPException(404, "Doctor profile missing")
        q = q.filter(Prescription.doctor_id == doctor.id)
    if patient_id and user.role in {Role.admin, Role.receptionist, Role.doctor}:
        q = q.filter(Prescription.patient_id == patient_id)
    return q.order_by(Prescription.id.desc()).all()


@router.post("", response_model=PrescriptionOut, status_code=201)
def create_prescription(
    payload: PrescriptionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.doctor)),
):
    doctor = db.query(Doctor).filter(Doctor.user_id == user.id).first()
    if not doctor:
        raise HTTPException(404, "Doctor profile missing")

    patient = db.get(Patient, payload.patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    if payload.appointment_id:
        appt = db.get(Appointment, payload.appointment_id)
        if not appt or appt.doctor_id != doctor.id:
            raise HTTPException(403, "Cannot attach to that appointment")

    pres = Prescription(
        appointment_id=payload.appointment_id,
        patient_id=patient.id,
        doctor_id=doctor.id,
        diagnosis=payload.diagnosis,
        notes=payload.notes,
    )
    db.add(pres)
    db.flush()
    for it in payload.items:
        db.add(PrescriptionItem(prescription_id=pres.id, **it.model_dump()))

    db.add(
        Notification(
            user_id=patient.user_id,
            title="New prescription",
            body=f"Dr. {doctor.user.full_name} added a new prescription",
        )
    )
    db.commit()
    db.refresh(pres)
    return _base_query(db).filter(Prescription.id == pres.id).first()


@router.get("/{prescription_id}", response_model=PrescriptionOut)
def get_prescription(
    prescription_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pres = _base_query(db).filter(Prescription.id == prescription_id).first()
    if not pres:
        raise HTTPException(404, "Not found")
    if user.role == Role.patient and pres.patient.user_id != user.id:
        raise HTTPException(403, "Forbidden")
    if user.role == Role.doctor and pres.doctor.user_id != user.id:
        raise HTTPException(403, "Forbidden")
    return pres
