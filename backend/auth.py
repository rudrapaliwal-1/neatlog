"""Local individual accounts and expiring, server-managed browser sessions."""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import secrets
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from .database import utc_now
from .models import WorkflowError

COOKIE = "sentinel_session"
SESSION_HOURS = 12
hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
principal: ContextVar[str | None] = ContextVar("sentinel_principal", default=None)
identity_kind: ContextVar[str | None] = ContextVar("sentinel_identity_kind", default=None)
router = APIRouter(prefix="/api/auth", tags=["authentication"])


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def current_user() -> str:
    user_id = principal.get()
    if not user_id or identity_kind.get() != "USER_SESSION":
        raise WorkflowError("user session required", 401, "AUTH_REQUIRED")
    return user_id


def session_user(db, raw_token: str) -> str | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", raw_token):
        return None
    row = db.execute("SELECT user_id, expires_at FROM sessions WHERE token_hash = ?",
                     (digest(raw_token),)).fetchone()
    if row is None or row["expires_at"] <= utc_now():
        return None
    return row["user_id"]


def csrf_valid(db, raw_token: str, supplied: str | None) -> bool:
    if not supplied or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", supplied):
        return False
    row = db.execute("SELECT csrf_hash FROM sessions WHERE token_hash = ?",
                     (digest(raw_token),)).fetchone()
    return bool(row and hmac.compare_digest(row["csrf_hash"], digest(supplied)))


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=1024)


def _issue(request: Request, response: Response, user_id: str, email: str):
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).isoformat()
    with request.app.state.workflow.db.transaction() as db:
        db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                   (digest(token), user_id, digest(csrf), expires, utc_now()))
    response.set_cookie(COOKIE, token, httponly=True, secure=request.url.scheme == "https",
                        samesite="lax", max_age=SESSION_HOURS * 3600, path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"user": {"id": user_id, "email": email}, "csrf_token": csrf, "expires_at": expires}


@router.post("/register", status_code=201)
def register(payload: Credentials, request: Request, response: Response):
    email = payload.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise WorkflowError("enter a valid email address", 422, "INVALID_EMAIL")
    if len(payload.password.encode("utf-8")) > 1024:
        raise WorkflowError("password is too long", 422, "INVALID_PASSWORD")
    user_id = "user-" + uuid4().hex
    password_hash = hasher.hash(payload.password)
    with request.app.state.workflow.db.transaction() as db:
        if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise WorkflowError("email is already registered", 409, "EMAIL_EXISTS")
        db.execute("INSERT INTO users VALUES (?, ?, ?, ?)",
                   (user_id, email, password_hash, utc_now()))
    return _issue(request, response, user_id, email)


@router.post("/login")
def login(payload: Credentials, request: Request, response: Response):
    email = payload.email.strip().lower()
    with request.app.state.workflow.db.read() as db:
        row = db.execute("SELECT id, password_hash FROM users WHERE email = ?", (email,)).fetchone()
    try:
        if row is None or not hasher.verify(row["password_hash"], payload.password):
            raise WorkflowError("invalid email or password", 401, "INVALID_CREDENTIALS")
    except (VerifyMismatchError, VerificationError):
        raise WorkflowError("invalid email or password", 401, "INVALID_CREDENTIALS") from None
    return _issue(request, response, row["id"], email)


@router.get("/me")
def me(request: Request):
    user_id = current_user()
    token = request.cookies.get(COOKIE, "")
    csrf = secrets.token_urlsafe(32)
    with request.app.state.workflow.db.transaction() as db:
        db.execute("UPDATE sessions SET csrf_hash = ? WHERE token_hash = ? AND user_id = ?",
                   (digest(csrf), digest(token), user_id))
        row = db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
    return {"user": {"id": user_id, "email": row["email"]}, "csrf_token": csrf}


@router.post("/logout")
def logout(request: Request, response: Response):
    current_user()
    with request.app.state.workflow.db.transaction() as db:
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (digest(request.cookies.get(COOKIE, "")),))
    response.delete_cookie(COOKIE, path="/")
    return {"status": "logged_out"}
