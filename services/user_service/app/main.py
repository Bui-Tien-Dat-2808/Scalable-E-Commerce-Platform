from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr

from services.common.security import create_access_token, hash_password, verify_password

app = FastAPI(title="User Service", version="1.0.0")


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


users_db = {}


@app.get("/")
def root():
    return {"service": "user-service", "message": "User service is running"}


@app.get("/health")
def health_check():
    return {"service": "user-service", "status": "ok"}


@app.post("/auth/register", status_code=201, response_model=UserResponse)
def register_user(payload: UserRegisterRequest):
    if payload.email in users_db:
        raise HTTPException(status_code=400, detail="User already exists")

    user_id = len(users_db) + 1
    users_db[str(payload.email)] = {
        "id": user_id,
        "username": payload.username,
        "email": str(payload.email),
        "password": hash_password(payload.password),
    }
    return UserResponse(id=user_id, username=payload.username, email=str(payload.email))


@app.post("/auth/login", response_model=LoginResponse)
def login_user(payload: UserLoginRequest):
    user = users_db.get(str(payload.email))
    if not user or not verify_password(payload.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"user_id": str(user["id"]), "email": user["email"]})
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(id=user["id"], username=user["username"], email=user["email"]),
    )