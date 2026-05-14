"""Seed default users + sample data for local dev."""
from datetime import datetime, timedelta, date

from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine, Base
from app.core.security import hash_password
from app.models import (
    User,
    Role,
    Patient,
    Doctor,
    Appointment,
    AppointmentStatus,
    Prescription,
    PrescriptionItem,
    Bill,
    BillItem,
    BillStatus,
)


def _ensure_user(db: Session, email: str, password: str, full_name: str, role: Role, **extra) -> User:
    u = db.query(User).filter(User.email == email).first()
    if u:
        return u
    u = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
        phone=extra.get("phone"),
    )
    db.add(u)
    db.flush()
    return u


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = _ensure_user(db, "admin@hms.local", "admin123", "Hospital Admin", Role.admin)
        recep = _ensure_user(db, "reception@hms.local", "reception123", "Front Desk", Role.receptionist)

        doc_user = _ensure_user(db, "doctor@hms.local", "doctor123", "Dr. Anika Rao", Role.doctor)
        if not db.query(Doctor).filter(Doctor.user_id == doc_user.id).first():
            db.add(
                Doctor(
                    user_id=doc_user.id,
                    specialization="General Medicine",
                    qualification="MBBS, MD",
                    years_experience=8,
                    consultation_fee=500,
                    bio="General physician with focus on preventive care.",
                )
            )

        doc2 = _ensure_user(db, "doctor2@hms.local", "doctor123", "Dr. Vikram Shah", Role.doctor)
        if not db.query(Doctor).filter(Doctor.user_id == doc2.id).first():
            db.add(
                Doctor(
                    user_id=doc2.id,
                    specialization="Cardiology",
                    qualification="MBBS, DM Cardiology",
                    years_experience=12,
                    consultation_fee=900,
                )
            )

        pat_user = _ensure_user(db, "patient@hms.local", "patient123", "John Patient", Role.patient)
        if not db.query(Patient).filter(Patient.user_id == pat_user.id).first():
            db.add(
                Patient(
                    user_id=pat_user.id,
                    dob=date(1992, 6, 14),
                    gender="male",
                    blood_group="O+",
                    address="221B Baker Street",
                    medical_history="None",
                    allergies="None",
                )
            )

        db.commit()

        # sample appointment + prescription + bill
        patient = db.query(Patient).filter(Patient.user_id == pat_user.id).first()
        doctor = db.query(Doctor).filter(Doctor.user_id == doc_user.id).first()

        if patient and doctor and not db.query(Appointment).filter(Appointment.patient_id == patient.id).first():
            appt = Appointment(
                patient_id=patient.id,
                doctor_id=doctor.id,
                scheduled_at=datetime.utcnow() + timedelta(days=1, hours=2),
                duration_min=30,
                reason="General check-up",
                status=AppointmentStatus.scheduled,
            )
            db.add(appt)
            db.flush()

            past = Appointment(
                patient_id=patient.id,
                doctor_id=doctor.id,
                scheduled_at=datetime.utcnow() - timedelta(days=7),
                duration_min=30,
                reason="Follow up",
                status=AppointmentStatus.completed,
            )
            db.add(past)
            db.flush()

            pres = Prescription(
                appointment_id=past.id,
                patient_id=patient.id,
                doctor_id=doctor.id,
                diagnosis="Mild hypertension",
                notes="Monitor BP daily.",
            )
            db.add(pres)
            db.flush()
            db.add_all(
                [
                    PrescriptionItem(
                        prescription_id=pres.id,
                        medicine="Amlodipine 5mg",
                        dosage="5mg",
                        frequency="Once daily",
                        duration="30 days",
                    ),
                    PrescriptionItem(
                        prescription_id=pres.id,
                        medicine="Aspirin 75mg",
                        dosage="75mg",
                        frequency="Once daily",
                        duration="30 days",
                    ),
                ]
            )

            bill = Bill(patient_id=patient.id, appointment_id=past.id, notes="Consultation + tests")
            db.add(bill)
            db.flush()
            items = [
                BillItem(bill_id=bill.id, description="Consultation", quantity=1, unit_price=500),
                BillItem(bill_id=bill.id, description="ECG", quantity=1, unit_price=300),
            ]
            db.add_all(items)
            db.flush()
            bill.total = 800
            bill.paid = 0
            bill.status = BillStatus.unpaid

            db.commit()

        print("Seed complete.")
        print("Logins (email / password):")
        print("  admin@hms.local       / admin123")
        print("  doctor@hms.local      / doctor123")
        print("  reception@hms.local   / reception123")
        print("  patient@hms.local     / patient123")
    finally:
        db.close()


if __name__ == "__main__":
    main()
