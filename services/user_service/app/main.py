import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import Session

from services.common.database import Base, engine, get_db, SessionLocal
from services.common.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    hash_token,
    verify_password,
    get_current_user,
    require_admin,
)
from services.common.consul import consul_client

from prometheus_fastapi_instrumentator import Instrumentator
from services.common.logging import setup_logger
from services.common.error_handler import setup_error_handlers

SERVICE_NAME = os.getenv("SERVICE_NAME", "user-service")
SERVICE_HOST = os.getenv("SERVICE_HOST", "localhost")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8000"))
INSTANCE_ID = f"{SERVICE_NAME}-{os.getenv('HOSTNAME', 'default')}"

logger = setup_logger(SERVICE_NAME)

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin123!")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")


# ── Models ────────────────────────────────────────────────────────────────────

class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="user")  # "user" | "admin"


class RefreshTokenModel(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)  # stored as naive UTC
    revoked = Column(Boolean, default=False, nullable=False)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up user-service...")
    Base.metadata.create_all(bind=engine)
    _seed_admin()
    consul_client.register_service(SERVICE_NAME, INSTANCE_ID, SERVICE_HOST, SERVICE_PORT)
    yield
    logger.info("Shutting down user-service...")
    consul_client.deregister_service(INSTANCE_ID)


def _seed_admin():
    """Tạo tài khoản admin mặc định nếu chưa tồn tại."""
    with SessionLocal() as db:
        existing = db.query(UserModel).filter(UserModel.email == ADMIN_EMAIL).first()
        if not existing:
            admin = UserModel(
                username=ADMIN_USERNAME,
                email=ADMIN_EMAIL,
                password=hash_password(ADMIN_PASSWORD),
                role="admin",
            )
            db.add(admin)
            db.commit()
            logger.info("Default admin user seeded: %s", ADMIN_EMAIL)


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="User Service", version="1.0.0", lifespan=lifespan)
Instrumentator().instrument(app).expose(app)
setup_error_handlers(app)

Base.metadata.create_all(bind=engine)


# ── Schemas ───────────────────────────────────────────────────────────────────

class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=100, description="Username must be between 2 and 100 characters")
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100, description="Password must be between 6 and 100 characters")


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, description="Password must be at least 6 characters")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class UserUpdateRequest(BaseModel):
    username: Optional[str] = Field(None, min_length=2, max_length=100)
    email: Optional[EmailStr] = None


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user: UserResponse


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "user-service", "message": "User service is running"}


@app.get("/health")
def health_check():
    return {"service": "user-service", "status": "ok"}


@app.post("/auth/register", status_code=201, response_model=UserResponse)
def register_user(payload: UserRegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(UserModel).filter(UserModel.email == str(payload.email)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = UserModel(
        username=payload.username,
        email=str(payload.email),
        password=hash_password(payload.password),
        role="user",  # public registration luôn là "user"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse(id=user.id, username=user.username, email=user.email, role=user.role)


@app.post("/auth/login", response_model=LoginResponse)
def login_user(payload: UserLoginRequest, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.email == str(payload.email)).first()
    if not user or not verify_password(payload.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token_payload = {"user_id": str(user.id), "email": user.email, "role": user.role}
    access_token = create_access_token(token_payload)
    refresh_token = create_refresh_token({"user_id": str(user.id)})

    # Lưu refresh token (hashed) vào DB — dùng naive UTC cho tương thích SQLite
    expires_at = datetime.utcnow() + timedelta(days=7)
    db.add(RefreshTokenModel(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        expires_at=expires_at,
        revoked=False,
    ))
    db.commit()

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=UserResponse(id=user.id, username=user.username, email=user.email, role=user.role),
    )


@app.post("/auth/refresh")
def refresh_access_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    """
    Nhận refresh_token hợp lệ → trả access_token mới + rotate refresh_token mới.
    Token cũ bị revoke ngay sau khi dùng.
    """
    try:
        claims = decode_refresh_token(payload.refresh_token)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    token_hash = hash_token(payload.refresh_token)
    stored = db.query(RefreshTokenModel).filter(
        RefreshTokenModel.token_hash == token_hash,
        RefreshTokenModel.revoked == False,  # noqa: E712
    ).first()

    if not stored:
        raise HTTPException(status_code=401, detail="Refresh token not found or already revoked")

    if stored.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Refresh token expired")

    # Lấy thông tin user để đưa role vào access token mới
    user = db.query(UserModel).filter(UserModel.id == stored.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Revoke token cũ
    stored.revoked = True
    db.commit()

    # Cấp token mới (rotation)
    new_access_token = create_access_token({
        "user_id": str(user.id),
        "email": user.email,
        "role": user.role,
    })
    new_refresh_token = create_refresh_token({"user_id": str(user.id)})

    expires_at = datetime.utcnow() + timedelta(days=7)
    db.add(RefreshTokenModel(
        user_id=user.id,
        token_hash=hash_token(new_refresh_token),
        expires_at=expires_at,
        revoked=False,
    ))
    db.commit()

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


@app.post("/auth/logout")
def logout(payload: RefreshRequest, db: Session = Depends(get_db)):
    """Revoke refresh token — vô hiệu hoá session hiện tại."""
    token_hash = hash_token(payload.refresh_token)
    stored = db.query(RefreshTokenModel).filter(
        RefreshTokenModel.token_hash == token_hash,
    ).first()

    if stored and not stored.revoked:
        stored.revoked = True
        db.commit()

    return {"message": "Logged out successfully"}


# ── User CRUD Routes ──────────────────────────────────────────────────────────

@app.get("/users", response_model=list[UserResponse], tags=["Users"])
def list_users(db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    """Lấy danh sách tất cả người dùng (Chỉ Admin)."""
    users = db.query(UserModel).all()
    return [UserResponse(id=u.id, username=u.username, email=u.email, role=u.role) for u in users]


@app.get("/users/{user_id}", response_model=UserResponse, tags=["Users"])
def get_user(user_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Lấy chi tiết thông tin người dùng (Admin hoặc chính chủ)."""
    if current_user["role"] != "admin" and int(current_user["user_id"]) != user_id:
        raise HTTPException(status_code=403, detail="Forbidden: You cannot access other users' data")
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(id=user.id, username=user.username, email=user.email, role=user.role)


@app.put("/users/{user_id}", response_model=UserResponse, tags=["Users"])
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Cập nhật thông tin người dùng (Admin hoặc chính chủ)."""
    if current_user["role"] != "admin" and int(current_user["user_id"]) != user_id:
        raise HTTPException(status_code=403, detail="Forbidden: You cannot modify other users' data")
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.username is not None:
        user.username = payload.username
    if payload.email is not None:
        # Check duplicate email
        existing = db.query(UserModel).filter(UserModel.email == str(payload.email), UserModel.id != user_id).first()
        if existing:
            raise HTTPException(status_code=409, detail="Email already in use")
        user.email = str(payload.email)

    db.commit()
    db.refresh(user)
    return UserResponse(id=user.id, username=user.username, email=user.email, role=user.role)


@app.delete("/users/{user_id}", tags=["Users"])
def delete_user(user_id: int, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    """Xóa người dùng (Chỉ Admin)."""
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully", "id": user_id}