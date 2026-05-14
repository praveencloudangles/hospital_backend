from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import (
    User,
    Role,
    Patient,
    Doctor,
    Appointment,
    AppointmentStatus,
    Notification,
)
from app.schemas.schemas import AppointmentCreate, AppointmentOut, AppointmentUpdate

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


def _scope_query(db: Session, user: User):
    q = (
        db.query(Appointment)
        .options(
            joinedload(Appointment.patient).joinedload(Patient.user),
            joinedload(Appointment.doctor).joinedload(Doctor.user),
        )
    )
    if user.role == Role.patient:
        patient = db.query(Patient).filter(Patient.user_id == user.id).first()
        if not patient:
            raise HTTPException(404, "Patient profile missing")
        q = q.filter(Appointment.patient_id == patient.id)
    elif user.role == Role.doctor:
        doctor = db.query(Doctor).filter(Doctor.user_id == user.id).first()
        if not doctor:
            raise HTTPException(404, "Doctor profile missing")
        q = q.filter(Appointment.doctor_id == doctor.id)
    # admin & receptionist see all
    return q


@router.get("", response_model=List[AppointmentOut])
def list_appointments(
    status: Optional[AppointmentStatus] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    doctor_id: Optional[int] = None,
    patient_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = _scope_query(db, user)
    if status:
        q = q.filter(Appointment.status == status)
    if date_from:
        q = q.filter(Appointment.scheduled_at >= date_from)
    if date_to:
        q = q.filter(Appointment.scheduled_at <= date_to)
    if doctor_id and user.role in {Role.admin, Role.receptionist}:
        q = q.filter(Appointment.doctor_id == doctor_id)
    if patient_id and user.role in {Role.admin, Role.receptionist, Role.doctor}:
        q = q.filter(Appointment.patient_id == patient_id)
    return q.order_by(Appointment.scheduled_at.desc()).all()


@router.post("", response_model=AppointmentOut, status_code=201)
def create_appointment(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Determine patient
    if user.role == Role.patient:
        patient = db.query(Patient).filter(Patient.user_id == user.id).first()
        if not patient:
            raise HTTPException(404, "Patient profile missing")
        patient_id = patient.id
    else:
        if not payload.patient_id:
            raise HTTPException(400, "patient_id is required")
        if not db.get(Patient, payload.patient_id):
            raise HTTPException(404, "Patient not found")
        patient_id = payload.patient_id

    doctor = db.get(Doctor, payload.doctor_id)
    if not doctor:
        raise HTTPException(404, "Doctor not found")

    # Conflict check on doctor's calendar
    end = payload.scheduled_at + timedelta(minutes=payload.duration_min)
    conflicts = (
        db.query(Appointment)
        .filter(
            Appointment.doctor_id == payload.doctor_id,
            Appointment.status.in_(
                [AppointmentStatus.scheduled, AppointmentStatus.confirmed]
            ),
            Appointment.scheduled_at < end,
        )
        .all()
    )
    for c in conflicts:
        c_end = c.scheduled_at + timedelta(minutes=c.duration_min)
        if c_end > payload.scheduled_at:
            raise HTTPException(409, "Doctor has a conflicting appointment in this time slot")

    appt = Appointment(
        patient_id=patient_id,
        doctor_id=payload.doctor_id,
        scheduled_at=payload.scheduled_at,
        duration_min=payload.duration_min,
        reason=payload.reason,
    )
    db.add(appt)
    db.flush()

    # Notify doctor and patient
    db.add(
        Notification(
            user_id=doctor.user_id,
            title="New appointment scheduled",
            body=f"Appointment on {payload.scheduled_at:%Y-%m-%d %H:%M}",
        )
    )
    patient_user_id = db.get(Patient, patient_id).user_id
    db.add(
        Notification(
            user_id=patient_user_id,
            title="Appointment booked",
            body=f"Your appointment is on {payload.scheduled_at:%Y-%m-%d %H:%M}",
        )
    )
    db.commit()
    db.refresh(appt)
    return appt


@router.patch("/{appointment_id}", response_model=AppointmentOut)
def update_appointment(
    appointment_id: int,
    payload: AppointmentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    appt = db.get(Appointment, appointment_id)
    if not appt:
        raise HTTPException(404, "Appointment not found")

    # Permissions per field
    data = payload.model_dump(exclude_unset=True)

    if user.role == Role.patient:
        patient = db.query(Patient).filter(Patient.user_id == user.id).first()
        if not patient or appt.patient_id != patient.id:
            raise HTTPException(403, "Forbidden")
        # Patient can only cancel or reschedule
        allowed = {"scheduled_at", "duration_min", "reason", "status"}
        if not set(data.keys()).issubset(allowed):
            raise HTTPException(403, "Patients cannot edit those fields")
        if "status" in data and data["status"] not in {AppointmentStatus.cancelled}:
            raise HTTPException(403, "Patients can only cancel")
    elif user.role == Role.doctor:
        doctor = db.query(Doctor).filter(Doctor.user_id == user.id).first()
        if not doctor or appt.doctor_id != doctor.id:
            raise HTTPException(403, "Forbidden")

    for k, v in data.items():
        setattr(appt, k, v)
    db.commit()
    db.refresh(appt)
    return appt


@router.delete("/{appointment_id}", status_code=204)
def delete_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    appt = db.get(Appointment, appointment_id)
    if not appt:
        raise HTTPException(404, "Appointment not found")
    if user.role not in {Role.admin, Role.receptionist}:
        raise HTTPException(403, "Forbidden")
    db.delete(appt)
    db.commit()
