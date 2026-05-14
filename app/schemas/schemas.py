from datetime import datetime, date
from typing import Optional, List

from pydantic import BaseModel, EmailStr, ConfigDict, Field

from app.models.models import Role, AppointmentStatus, BillStatus


# -------- Auth --------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class LoginIn(BaseModel):
    email: str
    password: str


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=6)
    full_name: str
    phone: Optional[str] = None
    role: Role = Role.patient
    # optional sub-profile fields
    specialization: Optional[str] = None
    qualification: Optional[str] = None
    consultation_fee: Optional[float] = None
    dob: Optional[date] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    address: Optional[str] = None


# -------- User --------
class UserBase(BaseModel):
    email: str
    full_name: str
    role: Role
    phone: Optional[str] = None
    is_active: bool = True


class UserOut(UserBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[Role] = None


# -------- Patient --------
class PatientBase(BaseModel):
    dob: Optional[date] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    address: Optional[str] = None
    medical_history: Optional[str] = None
    allergies: Optional[str] = None


class PatientUpdate(PatientBase):
    pass


class PatientOut(PatientBase):
    id: int
    user: UserOut
    model_config = ConfigDict(from_attributes=True)


# -------- Doctor --------
class DoctorBase(BaseModel):
    specialization: str = "General"
    qualification: Optional[str] = None
    years_experience: int = 0
    consultation_fee: float = 0
    bio: Optional[str] = None


class DoctorUpdate(BaseModel):
    specialization: Optional[str] = None
    qualification: Optional[str] = None
    years_experience: Optional[int] = None
    consultation_fee: Optional[float] = None
    bio: Optional[str] = None


class DoctorOut(DoctorBase):
    id: int
    user: UserOut
    model_config = ConfigDict(from_attributes=True)


# -------- Appointment --------
class AppointmentCreate(BaseModel):
    patient_id: Optional[int] = None  # required for staff, ignored for patient
    doctor_id: int
    scheduled_at: datetime
    duration_min: int = 30
    reason: Optional[str] = None


class AppointmentUpdate(BaseModel):
    scheduled_at: Optional[datetime] = None
    duration_min: Optional[int] = None
    reason: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[AppointmentStatus] = None


class AppointmentOut(BaseModel):
    id: int
    patient_id: int
    doctor_id: int
    scheduled_at: datetime
    duration_min: int
    reason: Optional[str]
    notes: Optional[str]
    status: AppointmentStatus
    created_at: datetime
    patient: Optional[PatientOut] = None
    doctor: Optional[DoctorOut] = None
    model_config = ConfigDict(from_attributes=True)


# -------- Prescription --------
class PrescriptionItemIn(BaseModel):
    medicine: str
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    instructions: Optional[str] = None


class PrescriptionItemOut(PrescriptionItemIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class PrescriptionCreate(BaseModel):
    appointment_id: Optional[int] = None
    patient_id: int
    diagnosis: Optional[str] = None
    notes: Optional[str] = None
    items: List[PrescriptionItemIn] = []


class PrescriptionOut(BaseModel):
    id: int
    appointment_id: Optional[int]
    patient_id: int
    doctor_id: int
    diagnosis: Optional[str]
    notes: Optional[str]
    created_at: datetime
    items: List[PrescriptionItemOut]
    patient: Optional[PatientOut] = None
    doctor: Optional[DoctorOut] = None
    model_config = ConfigDict(from_attributes=True)


# -------- Bills --------
class BillItemIn(BaseModel):
    description: str
    quantity: int = 1
    unit_price: float = 0


class BillItemOut(BillItemIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class BillCreate(BaseModel):
    patient_id: int
    appointment_id: Optional[int] = None
    notes: Optional[str] = None
    items: List[BillItemIn]


class BillPay(BaseModel):
    amount: float


class BillOut(BaseModel):
    id: int
    patient_id: int
    appointment_id: Optional[int]
    total: float
    paid: float
    status: BillStatus
    notes: Optional[str]
    created_at: datetime
    items: List[BillItemOut]
    patient: Optional[PatientOut] = None
    model_config = ConfigDict(from_attributes=True)


# -------- Reports --------
class ReportOut(BaseModel):
    id: int
    patient_id: int
    title: str
    description: Optional[str]
    file_name: str
    content_type: Optional[str]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# -------- Notification --------
class NotificationOut(BaseModel):
    id: int
    title: str
    body: Optional[str]
    is_read: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# -------- Chat --------
class ChatIn(BaseModel):
    message: str


class ChatOut(BaseModel):
    reply: str


# -------- Analytics --------
class AdminAnalytics(BaseModel):
    users_total: int
    patients_total: int
    doctors_total: int
    appointments_total: int
    appointments_today: int
    appointments_upcoming: int
    revenue_total: float
    revenue_outstanding: float
    appointments_by_status: dict
    revenue_by_day: list


Token.model_rebuild()
