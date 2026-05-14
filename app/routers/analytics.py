from datetime import datetime, timedelta, date

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles, get_current_user
from app.models import (
    User,
    Role,
    Patient,
    Doctor,
    Appointment,
    AppointmentStatus,
    Bill,
    BillStatus,
)
from app.schemas.schemas import AdminAnalytics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/admin", response_model=AdminAnalytics)
def admin_analytics(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin)),
):
    now = datetime.utcnow()
    today_start = datetime.combine(now.date(), datetime.min.time())
    today_end = today_start + timedelta(days=1)

    users_total = db.query(func.count(User.id)).scalar() or 0
    patients_total = db.query(func.count(Patient.id)).scalar() or 0
    doctors_total = db.query(func.count(Doctor.id)).scalar() or 0
    appointments_total = db.query(func.count(Appointment.id)).scalar() or 0
    appointments_today = (
        db.query(func.count(Appointment.id))
        .filter(Appointment.scheduled_at >= today_start, Appointment.scheduled_at < today_end)
        .scalar()
        or 0
    )
    appointments_upcoming = (
        db.query(func.count(Appointment.id))
        .filter(
            Appointment.scheduled_at >= now,
            Appointment.status.in_(
                [AppointmentStatus.scheduled, AppointmentStatus.confirmed]
            ),
        )
        .scalar()
        or 0
    )

    revenue_total = float(db.query(func.coalesce(func.sum(Bill.paid), 0)).scalar() or 0)
    revenue_outstanding = float(
        db.query(func.coalesce(func.sum(Bill.total - Bill.paid), 0))
        .filter(Bill.status != BillStatus.paid)
        .scalar()
        or 0
    )

    by_status_rows = (
        db.query(Appointment.status, func.count(Appointment.id))
        .group_by(Appointment.status)
        .all()
    )
    by_status = {s.value: c for s, c in by_status_rows}

    # Revenue by day for last 14 days
    start = now.date() - timedelta(days=13)
    rev_rows = (
        db.query(func.date(Bill.created_at), func.coalesce(func.sum(Bill.paid), 0))
        .filter(Bill.created_at >= datetime.combine(start, datetime.min.time()))
        .group_by(func.date(Bill.created_at))
        .all()
    )
    rev_map = {str(d): float(v) for d, v in rev_rows}
    revenue_by_day = []
    for i in range(14):
        d = start + timedelta(days=i)
        revenue_by_day.append({"date": str(d), "amount": rev_map.get(str(d), 0.0)})

    return AdminAnalytics(
        users_total=users_total,
        patients_total=patients_total,
        doctors_total=doctors_total,
        appointments_total=appointments_total,
        appointments_today=appointments_today,
        appointments_upcoming=appointments_upcoming,
        revenue_total=revenue_total,
        revenue_outstanding=revenue_outstanding,
        appointments_by_status=by_status,
        revenue_by_day=revenue_by_day,
    )


@router.get("/summary")
def role_summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now = datetime.utcnow()
    today_start = datetime.combine(now.date(), datetime.min.time())
    today_end = today_start + timedelta(days=1)

    if user.role == Role.doctor:
        doctor = db.query(Doctor).filter(Doctor.user_id == user.id).first()
        if not doctor:
            return {}
        today_count = (
            db.query(func.count(Appointment.id))
            .filter(
                Appointment.doctor_id == doctor.id,
                Appointment.scheduled_at >= today_start,
                Appointment.scheduled_at < today_end,
            )
            .scalar()
            or 0
        )
        upcoming = (
            db.query(func.count(Appointment.id))
            .filter(
                Appointment.doctor_id == doctor.id,
                Appointment.scheduled_at >= now,
                Appointment.status.in_(
                    [AppointmentStatus.scheduled, AppointmentStatus.confirmed]
                ),
            )
            .scalar()
            or 0
        )
        completed = (
            db.query(func.count(Appointment.id))
            .filter(
                Appointment.doctor_id == doctor.id,
                Appointment.status == AppointmentStatus.completed,
            )
            .scalar()
            or 0
        )
        return {"today": today_count, "upcoming": upcoming, "completed": completed}

    if user.role == Role.patient:
        patient = db.query(Patient).filter(Patient.user_id == user.id).first()
        if not patient:
            return {}
        upcoming = (
            db.query(func.count(Appointment.id))
            .filter(
                Appointment.patient_id == patient.id,
                Appointment.scheduled_at >= now,
                Appointment.status.in_(
                    [AppointmentStatus.scheduled, AppointmentStatus.confirmed]
                ),
            )
            .scalar()
            or 0
        )
        unpaid = (
            db.query(func.coalesce(func.sum(Bill.total - Bill.paid), 0))
            .filter(Bill.patient_id == patient.id, Bill.status != BillStatus.paid)
            .scalar()
            or 0
        )
        return {"upcoming_appointments": upcoming, "outstanding_balance": float(unpaid)}

    if user.role == Role.receptionist:
        today_count = (
            db.query(func.count(Appointment.id))
            .filter(Appointment.scheduled_at >= today_start, Appointment.scheduled_at < today_end)
            .scalar()
            or 0
        )
        unpaid_total = (
            db.query(func.coalesce(func.sum(Bill.total - Bill.paid), 0))
            .filter(Bill.status != BillStatus.paid)
            .scalar()
            or 0
        )
        return {"appointments_today": today_count, "outstanding_total": float(unpaid_total)}

    return {}
