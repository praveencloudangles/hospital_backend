from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import User, Role, Patient, Bill, BillItem, BillStatus, Notification
from app.schemas.schemas import BillCreate, BillOut, BillPay

router = APIRouter(prefix="/api/bills", tags=["bills"])


def _base_query(db: Session):
    return (
        db.query(Bill)
        .options(
            joinedload(Bill.items),
            joinedload(Bill.patient).joinedload(Patient.user),
        )
    )


def _recalc(bill: Bill):
    bill.total = float(sum(i.quantity * float(i.unit_price) for i in bill.items))
    paid = float(bill.paid or 0)
    if paid <= 0:
        bill.status = BillStatus.unpaid
    elif paid >= bill.total:
        bill.status = BillStatus.paid
    else:
        bill.status = BillStatus.partial


@router.get("", response_model=List[BillOut])
def list_bills(
    status: Optional[BillStatus] = None,
    patient_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = _base_query(db)
    if user.role == Role.patient:
        patient = db.query(Patient).filter(Patient.user_id == user.id).first()
        if not patient:
            raise HTTPException(404, "Patient profile missing")
        q = q.filter(Bill.patient_id == patient.id)
    elif user.role == Role.doctor:
        # doctors don't need bills view by default
        raise HTTPException(403, "Forbidden")
    if status:
        q = q.filter(Bill.status == status)
    if patient_id and user.role in {Role.admin, Role.receptionist}:
        q = q.filter(Bill.patient_id == patient_id)
    return q.order_by(Bill.id.desc()).all()


@router.post("", response_model=BillOut, status_code=201)
def create_bill(
    payload: BillCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin, Role.receptionist)),
):
    patient = db.get(Patient, payload.patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")
    bill = Bill(
        patient_id=patient.id,
        appointment_id=payload.appointment_id,
        notes=payload.notes,
    )
    db.add(bill)
    db.flush()
    for it in payload.items:
        db.add(BillItem(bill_id=bill.id, **it.model_dump()))
    db.flush()
    db.refresh(bill)
    _recalc(bill)
    db.add(
        Notification(
            user_id=patient.user_id,
            title="New bill issued",
            body=f"A bill of {bill.total:.2f} has been generated.",
        )
    )
    db.commit()
    return _base_query(db).filter(Bill.id == bill.id).first()


@router.post("/{bill_id}/pay", response_model=BillOut)
def pay_bill(
    bill_id: int,
    payload: BillPay,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bill = _base_query(db).filter(Bill.id == bill_id).first()
    if not bill:
        raise HTTPException(404, "Bill not found")
    if user.role == Role.patient and bill.patient.user_id != user.id:
        raise HTTPException(403, "Forbidden")
    if user.role == Role.doctor:
        raise HTTPException(403, "Forbidden")
    if payload.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    new_paid = float(bill.paid or 0) + float(payload.amount)
    if new_paid > float(bill.total):
        new_paid = float(bill.total)
    bill.paid = new_paid
    _recalc(bill)
    db.commit()
    db.refresh(bill)
    return bill


@router.get("/{bill_id}", response_model=BillOut)
def get_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bill = _base_query(db).filter(Bill.id == bill_id).first()
    if not bill:
        raise HTTPException(404, "Not found")
    if user.role == Role.patient and bill.patient.user_id != user.id:
        raise HTTPException(403, "Forbidden")
    return bill
