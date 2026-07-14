from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, String
from sqlalchemy.orm import Session

from services.common.database import Base, engine, get_db

app = FastAPI(title="Notification Service", version="1.0.0")


# ── Model ─────────────────────────────────────────────────────────────────────

class NotificationModel(Base):
    __tablename__ = "notifications"

    id = Column(String(30), primary_key=True, index=True)  # NTF-XXXX
    channel = Column(String(20), default="email")
    recipient = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=True)
    message = Column(String(2000), nullable=False)
    event_type = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False)  # queued | failed


Base.metadata.create_all(bind=engine)


# ── Schemas ───────────────────────────────────────────────────────────────────

class NotificationCreateRequest(BaseModel):
    channel: str = "email"
    recipient: str
    subject: str | None = None
    message: str
    event_type: str | None = None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "notification-service", "message": "Notification service is running"}


@app.get("/health")
def health_check():
    return {"service": "notification-service", "status": "ok"}


@app.post("/notifications")
def create_notification(payload: NotificationCreateRequest, db: Session = Depends(get_db)):
    notification_id = f"NTF-{uuid4().hex[:12].upper()}"
    status = "queued" if payload.recipient and payload.message else "failed"
    notification = NotificationModel(
        id=notification_id,
        channel=payload.channel,
        recipient=payload.recipient,
        subject=payload.subject,
        message=payload.message,
        event_type=payload.event_type,
        status=status,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return _to_dict(notification)


@app.get("/notifications/{notification_id}")
def get_notification(notification_id: str, db: Session = Depends(get_db)):
    notification = db.query(NotificationModel).filter(NotificationModel.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return _to_dict(notification)


def _to_dict(n: NotificationModel) -> dict:
    return {
        "notification_id": n.id,
        "channel": n.channel,
        "recipient": n.recipient,
        "subject": n.subject,
        "message": n.message,
        "event_type": n.event_type,
        "status": n.status,
    }