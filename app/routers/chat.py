import json
from typing import List, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import (
    User,
    Role,
    Patient,
    Doctor,
    Appointment,
    Prescription,
    Bill,
    MedicalReport,
    ChatMessage,
)
from app.schemas.schemas import ChatIn, ChatOut
from app.services.ai import chat_complete

router = APIRouter(prefix="/api/chat", tags=["chat"])


SYSTEM_PROMPTS = {
    Role.admin: (
        "You are the hospital management assistant for an ADMINISTRATOR. "
        "Answer concisely about hospital operations, users, revenue, and analytics. "
        "Refer to the live CONTEXT_JSON system message for current numbers."
    ),
    Role.doctor: (
        "You are the hospital management assistant for a DOCTOR. "
        "Help with patient consultations, appointments, prescriptions, and clinical workflow. "
        "Be cautious — never provide definitive medical advice; suggest the doctor verify."
    ),
    Role.receptionist: (
        "You are the hospital management assistant for a RECEPTIONIST. "
        "Help with patient registration, appointment scheduling, and billing support."
    ),
    Role.patient: (
        "You are a friendly hospital assistant for a PATIENT. "
        "Help them navigate appointments, prescriptions, bills, and reports. "
        "Refer to the live CONTEXT_JSON system message for the patient's actual records. "
        "Never invent medical advice — point them to their doctor."
    ),
}


def _build_context(db: Session, user: User) -> Dict:
    ctx: Dict = {"user": {"name": user.full_name, "role": user.role.value}}

    if user.role == Role.patient:
        patient = db.query(Patient).filter(Patient.user_id == user.id).first()
        if patient:
            appts = (
                db.query(Appointment)
                .options(joinedload(Appointment.doctor).joinedload(Doctor.user))
                .filter(Appointment.patient_id == patient.id)
                .order_by(Appointment.scheduled_at.desc())
                .limit(10)
                .all()
            )
            ctx["appointments"] = [
                {
                    "id": a.id,
                    "scheduled_at": a.scheduled_at.isoformat(),
                    "status": a.status.value,
                    "doctor": a.doctor.user.full_name if a.doctor else None,
                    "reason": a.reason,
                }
                for a in appts
            ]
            pres = (
                db.query(Prescription)
                .filter(Prescription.patient_id == patient.id)
                .order_by(Prescription.id.desc())
                .limit(5)
                .all()
            )
            ctx["prescriptions"] = [
                {
                    "id": p.id,
                    "created_at": p.created_at.isoformat(),
                    "diagnosis": p.diagnosis,
                    "items": len(p.items),
                }
                for p in pres
            ]
            bills = db.query(Bill).filter(Bill.patient_id == patient.id).order_by(Bill.id.desc()).limit(10).all()
            ctx["bills"] = [
                {
                    "id": b.id,
                    "total": float(b.total),
                    "paid": float(b.paid),
                    "status": b.status.value,
                }
                for b in bills
            ]
            reports = (
                db.query(MedicalReport)
                .filter(MedicalReport.patient_id == patient.id)
                .order_by(MedicalReport.id.desc())
                .limit(10)
                .all()
            )
            ctx["reports"] = [
                {"id": r.id, "title": r.title, "created_at": r.created_at.isoformat()} for r in reports
            ]
    elif user.role == Role.doctor:
        doctor = db.query(Doctor).filter(Doctor.user_id == user.id).first()
        if doctor:
            appts = (
                db.query(Appointment)
                .options(joinedload(Appointment.patient).joinedload(Patient.user))
                .filter(Appointment.doctor_id == doctor.id)
                .order_by(Appointment.scheduled_at.desc())
                .limit(10)
                .all()
            )
            ctx["appointments"] = [
                {
                    "id": a.id,
                    "scheduled_at": a.scheduled_at.isoformat(),
                    "status": a.status.value,
                    "patient": a.patient.user.full_name if a.patient else None,
                    "reason": a.reason,
                }
                for a in appts
            ]
    elif user.role in {Role.admin, Role.receptionist}:
        ctx["totals"] = {
            "patients": db.query(Patient).count(),
            "doctors": db.query(Doctor).count(),
            "appointments": db.query(Appointment).count(),
            "bills": db.query(Bill).count(),
        }
    return ctx


@router.get("/history")
def history(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.id.asc())
        .limit(50)
        .all()
    )
    return [{"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()} for m in msgs]


@router.delete("/history", status_code=204)
def clear_history(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.query(ChatMessage).filter(ChatMessage.user_id == user.id).delete()
    db.commit()


@router.post("", response_model=ChatOut)
async def chat(
    payload: ChatIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    system_prompt = SYSTEM_PROMPTS.get(user.role, SYSTEM_PROMPTS[Role.patient])
    context = _build_context(db, user)
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": "CONTEXT_JSON:" + json.dumps(context, default=str)},
    ]

    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.id.desc())
        .limit(10)
        .all()
    )
    for m in reversed(history):
        messages.append({"role": m.role, "content": m.content})

    messages.append({"role": "user", "content": payload.message})

    reply = await chat_complete(messages)

    db.add(ChatMessage(user_id=user.id, role="user", content=payload.message))
    db.add(ChatMessage(user_id=user.id, role="assistant", content=reply))
    db.commit()

    return ChatOut(reply=reply)
