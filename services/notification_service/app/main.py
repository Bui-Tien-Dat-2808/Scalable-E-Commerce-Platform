import os
from uuid import uuid4
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, String
from sqlalchemy.orm import Session

from services.common.database import Base, engine, get_db
from services.common.consul import consul_client

from prometheus_fastapi_instrumentator import Instrumentator
from services.common.logging import setup_logger
from services.common.error_handler import setup_error_handlers

SERVICE_NAME = os.getenv("SERVICE_NAME", "notification-service")
SERVICE_HOST = os.getenv("SERVICE_HOST", "localhost")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8005"))
INSTANCE_ID = f"{SERVICE_NAME}-{os.getenv('HOSTNAME', 'default')}"

logger = setup_logger(SERVICE_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up notification-service...")
    # Startup: Register with Consul
    consul_client.register_service(SERVICE_NAME, INSTANCE_ID, SERVICE_HOST, SERVICE_PORT)
    yield
    logger.info("Shutting down notification-service...")
    # Shutdown: Deregister from Consul
    consul_client.deregister_service(INSTANCE_ID)


app = FastAPI(title="Notification Service", version="1.0.0", lifespan=lifespan)
# Expose /metrics
Instrumentator().instrument(app).expose(app)
setup_error_handlers(app)


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
    channel: str = Field("email", min_length=1)
    recipient: str = Field(..., min_length=1, description="Recipient must not be empty")
    subject: str | None = None
    message: str = Field(..., min_length=1, description="Message body must not be empty")
    event_type: str | None = None


class NotificationResponse(BaseModel):
    notification_id: str
    channel: str
    recipient: str
    subject: str | None = None
    message: str
    event_type: str | None = None
    status: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "notification-service", "message": "Notification service is running"}


@app.get("/health")
def health_check():
    return {"service": "notification-service", "status": "ok"}


@app.post("/notifications", response_model=NotificationResponse, tags=["Notifications"])
def create_notification(payload: NotificationCreateRequest, db: Session = Depends(get_db)):
    """Send mock notification (Email / SMS)."""
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
    return _to_response(notification)


@app.get("/notifications/{notification_id}", response_model=NotificationResponse, tags=["Notifications"])
def get_notification(notification_id: str, db: Session = Depends(get_db)):
    """Retrieve a notification by its ID."""
    notification = db.query(NotificationModel).filter(NotificationModel.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return _to_response(notification)


def _to_response(n: NotificationModel) -> NotificationResponse:
    return NotificationResponse(
        notification_id=n.id,
        channel=n.channel,
        recipient=n.recipient,
        subject=n.subject,
        message=n.message,
        event_type=n.event_type,
        status=n.status,
    )