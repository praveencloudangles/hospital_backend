import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User, Role, Patient, MedicalReport, Notification
from app.schemas.schemas import ReportOut

router = APIRouter(prefix="/api/reports", tags=["reports"])
settings = get_settings()


def _ensure_upload_dir():
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)


@router.get("", response_model=List[ReportOut])
def list_reports(
    patient_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(MedicalReport)
    if user.role == Role.patient:
        patient = db.query(Patient).filter(Patient.user_id == user.id).first()
        if not patient:
            raise HTTPException(404, "Patient profile missing")
        q = q.filter(MedicalReport.patient_id == patient.id)
    elif patient_id:
        q = q.filter(MedicalReport.patient_id == patient_id)
    return q.order_by(MedicalReport.id.desc()).all()


@router.post("", response_model=ReportOut, status_code=201)
async def upload_report(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    patient_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role == Role.patient:
        patient = db.query(Patient).filter(Patient.user_id == user.id).first()
        if not patient:
            raise HTTPException(404, "Patient profile missing")
        target_patient_id = patient.id
    else:
        if not patient_id:
            raise HTTPException(400, "patient_id required")
        p = db.get(Patient, patient_id)
        if not p:
            raise HTTPException(404, "Patient not found")
        target_patient_id = patient_id

    _ensure_upload_dir()
    safe_name = file.filename or "report"
    ext = os.path.splitext(safe_name)[1]
    stored = f"{uuid.uuid4().hex}{ext}"
    full_path = os.path.join(settings.UPLOAD_DIR, stored)
    with open(full_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    rec = MedicalReport(
        patient_id=target_patient_id,
        uploaded_by_user_id=user.id,
        title=title,
        description=description,
        file_path=full_path,
        file_name=safe_name,
        content_type=file.content_type,
    )
    db.add(rec)

    # notify patient if uploaded by staff
    if user.role != Role.patient:
        patient = db.get(Patient, target_patient_id)
        db.add(
            Notification(
                user_id=patient.user_id,
                title="New medical report",
                body=f"A new report '{title}' has been uploaded to your records.",
            )
        )
    db.commit()
    db.refresh(rec)
    return rec


@router.get("/{report_id}/download")
def download_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rec = db.get(MedicalReport, report_id)
    if not rec:
        raise HTTPException(404, "Not found")
    if user.role == Role.patient:
        patient = db.query(Patient).filter(Patient.user_id == user.id).first()
        if not patient or rec.patient_id != patient.id:
            raise HTTPException(403, "Forbidden")
    if not os.path.exists(rec.file_path):
        raise HTTPException(404, "File missing on disk")
    return FileResponse(rec.file_path, filename=rec.file_name, media_type=rec.content_type or "application/octet-stream")


@router.delete("/{report_id}", status_code=204)
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rec = db.get(MedicalReport, report_id)
    if not rec:
        raise HTTPException(404, "Not found")
    if user.role == Role.patient:
        patient = db.query(Patient).filter(Patient.user_id == user.id).first()
        if not patient or rec.patient_id != patient.id:
            raise HTTPException(403, "Forbidden")
    try:
        if os.path.exists(rec.file_path):
            os.remove(rec.file_path)
    except OSError:
        pass
    db.delete(rec)
    db.commit()
