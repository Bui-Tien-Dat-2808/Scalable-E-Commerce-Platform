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
    """Create short-lived JWT access token (default 60 minutes)."""
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
    """Create long-lived JWT refresh token (default 7 days).
    Contains a unique jti (JWT ID) to avoid hash collisions on rotation.
    """
    claims = {"user_id": payload["user_id"]}
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    claims.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
        "jti": secrets.token_hex(16),  # unique ID — guarantees uniqueness for each token
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
    """Hash refresh token before saving to database (prevents storing raw tokens)."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── FastAPI dependencies ──────────────────────────────────────────────────────

def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> str:
    """Dependency: returns user_id from access token. Maintains backward compatibility."""
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token missing user_id claim")
    return str(user_id)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    """Dependency: returns {"user_id": str, "role": str} from access token."""
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("user_id")
    role = payload.get("role", "user")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token missing user_id claim")
    return {"user_id": str(user_id), "role": role}


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency: restricts access to admin role. Returns 403 if unauthorized."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user