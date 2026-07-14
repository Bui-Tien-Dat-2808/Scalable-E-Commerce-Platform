from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from uuid import uuid4

app = FastAPI(title="Notification Service", version="1.0.0")


class NotificationCreateRequest(BaseModel):
    channel: str = "email"
    recipient: str
    subject: str | None = None
    message: str
    event_type: str | None = None  # e.g. "order_paid", "order_failed", "order_cancelled"


notifications_db: dict[str, dict] = {}


@app.get("/")
def root():
    return {"service": "notification-service", "message": "Notification service is running"}


@app.get("/health")
def health_check():
    return {"service": "notification-service", "status": "ok"}


@app.post("/notifications")
def create_notification(payload: NotificationCreateRequest):
    notification_id = f"NTF-{uuid4().hex[:12].upper()}"
    status = "queued" if payload.recipient and payload.message else "failed"
    notification = {
        "notification_id": notification_id,
        "channel": payload.channel,
        "recipient": payload.recipient,
        "subject": payload.subject,
        "message": payload.message,
        "event_type": payload.event_type,
        "status": status,
    }
    notifications_db[notification_id] = notification
    return notification


@app.get("/notifications/{notification_id}")
def get_notification(notification_id: str):
    notification = notifications_db.get(notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification