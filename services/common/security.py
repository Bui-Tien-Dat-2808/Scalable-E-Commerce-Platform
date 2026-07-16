import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

JWT_SECRET = os.getenv("JWT_SECRET", "change-this-secret-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

bearer_scheme = HTTPBearer(auto_error=True)


# ── Password hashing ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        100_000,
    ).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored_password: str) -> bool:
    try:
        salt, digest = stored_password.split("$", 1)
    except ValueError:
        return False

    computed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        100_000,
    ).hex()
    return hmac.compare_digest(computed, digest)


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(payload: dict, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    """Tạo access token JWT ngắn hạn (mặc định 60 phút)."""
    claims = payload.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    claims.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
        "jti": secrets.token_hex(8),  # unique per token
    })
    return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(payload: dict) -> str:
    """Tạo refresh token JWT dài hạn (mặc định 7 ngày).
    Chứa jti (JWT ID) duy nhất để tránh hash collision khi rotate.
    """
    claims = {"user_id": payload["user_id"]}
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    claims.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
        "jti": secrets.token_hex(16),  # unique ID — đảm bảo mỗi token khác nhau
    })
    return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from exc


def decode_refresh_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token") from exc


def hash_token(token: str) -> str:
    """Hash refresh token trước khi lưu vào DB (tránh lưu raw token)."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── FastAPI dependencies ──────────────────────────────────────────────────────

def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> str:
    """Dependency: trả về user_id từ access token. Tương thích ngược với code cũ."""
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token missing user_id claim")
    return str(user_id)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    """Dependency: trả về {"user_id": str, "role": str} từ access token."""
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("user_id")
    role = payload.get("role", "user")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token missing user_id claim")
    return {"user_id": str(user_id), "role": role}


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency: chỉ cho phép user có role='admin'. Trả 403 nếu không đủ quyền."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user