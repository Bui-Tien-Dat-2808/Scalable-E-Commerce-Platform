from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import Session

from services.common.database import Base, engine, get_db
from services.common.security import create_access_token, hash_password, verify_password

app = FastAPI(title="User Service", version="1.0.0")


# ── Model ─────────────────────────────────────────────────────────────────────

class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)


Base.metadata.create_all(bind=engine)


# ── Schemas ───────────────────────────────────────────────────────────────────

class UserRegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str


class LoginResponse(BaseModel):
    access_token: str
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
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse(id=user.id, username=user.username, email=user.email)


@app.post("/auth/login", response_model=LoginResponse)
def login_user(payload: UserLoginRequest, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.email == str(payload.email)).first()
    if not user or not verify_password(payload.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"user_id": str(user.id), "email": user.email})
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(id=user.id, username=user.username, email=user.email),
    )