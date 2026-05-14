from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import (
    auth,
    users,
    patients,
    doctors,
    appointments,
    prescriptions,
    bills,
    reports,
    notifications,
    analytics,
    chat,
)

settings = get_settings()

app = FastAPI(
    title="Hospital Management System API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(patients.router)
app.include_router(doctors.router)
app.include_router(appointments.router)
app.include_router(prescriptions.router)
app.include_router(bills.router)
app.include_router(reports.router)
app.include_router(notifications.router)
app.include_router(analytics.router)
app.include_router(chat.router)
