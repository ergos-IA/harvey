"""Named dashboard users: email + password, for a hosted (Railway) dashboard.

The dashboard's own token (harvey/dashboard_auth.py) stays the admin and
emergency key. Users are an extra way in that fits the same design: logging
in exchanges an email and password for a *session token* of the same shape
as the dashboard token, which the browser keeps in sessionStorage and sends
as ``Authorization: Bearer``, exactly like the dashboard token. Cookies are
still never read.

    data/dashboard-users.json   {"users": {"<email>": {"hash": "...", "created_at": "..."}}}

Passwords are stored only as scrypt hashes (stdlib hashlib, per-user random
salt). Sessions live in memory and expire after ``SESSION_HOURS``; a restart
logs everyone out, which is fine for a handful of people. Failed logins are
counted per email and per client: after ``MAX_FAILURES`` in
``LOCKOUT_MINUTES`` that email (or client) is refused until the window
passes, with the same answer whether or not the email exists.

Users are managed from a terminal (``harvey users add|list|remove|passwd``),
on Railway through ``railway ssh``. There is no sign-up from the dashboard.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from harvey.paths import PROJECT_ROOT

USERS_FILE = PROJECT_ROOT / "data" / "dashboard-users.json"

SESSION_HOURS = 12
MAX_FAILURES = 5
LOCKOUT_MINUTES = 15
MIN_PASSWORD_LENGTH = 12

# scrypt cost: ~16 MB and ~50 ms per check. Stored with the hash, so it can
# be raised later without invalidating existing passwords.
_N, _R, _P, _DKLEN = 2 ** 14, 8, 1, 32
_EMAIL_RE = re.compile(r"[^@\s]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}")


class UserError(ValueError):
    pass


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not _EMAIL_RE.fullmatch(email):
        raise UserError("Eso no parece una dirección de email.")
    return email


def check_password_policy(password: str):
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise UserError(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres.")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P,
                            dklen=_DKLEN, maxmem=64 * 1024 * 1024)
    b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return f"scrypt${_N}${_R}${_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        got = hashlib.scrypt((password or "").encode("utf-8"), salt=base64.b64decode(salt),
                             n=int(n), r=int(r), p=int(p), dklen=len(expected),
                             maxmem=64 * 1024 * 1024)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, expected)


# A real hash to check unknown emails against, so a wrong email takes as
# long as a wrong password and the timing doesn't reveal who has an account.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


class UserStore:
    """The users file. Every write replaces the whole file atomically."""

    def __init__(self, path: Path):
        self._lock = threading.Lock()
        self.path = Path(path)

    def configure(self, path: Path):
        with self._lock:
            self.path = Path(path)

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            raise UserError(f"No se puede leer {self.path}: {e}") from e
        users = data.get("users") if isinstance(data, dict) else None
        return users if isinstance(users, dict) else {}

    def _save(self, users: dict):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".users-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"users": users}, f, indent=2, sort_keys=True)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass  # Windows: ACLs, not mode bits
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def emails(self) -> list[str]:
        with self._lock:
            return sorted(self._load())

    def has_users(self) -> bool:
        with self._lock:
            return bool(self._load())

    def set_password(self, email: str, password: str, *, create: bool) -> str:
        email = normalize_email(email)
        check_password_policy(password)
        with self._lock:
            users = self._load()
            if create and email in users:
                raise UserError(f"{email} ya existe. Usa 'harvey users passwd' para cambiar su contraseña.")
            if not create and email not in users:
                raise UserError(f"{email} no existe.")
            entry = users.get(email, {"created_at": datetime.now(timezone.utc).isoformat()})
            entry["hash"] = hash_password(password)
            users[email] = entry
            self._save(users)
        sessions.revoke_user(email)
        return email

    def remove(self, email: str):
        email = normalize_email(email)
        with self._lock:
            users = self._load()
            if users.pop(email, None) is None:
                raise UserError(f"{email} no existe.")
            self._save(users)
        sessions.revoke_user(email)

    def authenticate(self, email: str, password: str) -> str | None:
        try:
            email = normalize_email(email)
        except UserError:
            verify_password(password, _DUMMY_HASH)
            return None
        with self._lock:
            entry = self._load().get(email)
        stored = entry.get("hash", "") if isinstance(entry, dict) else ""
        ok = verify_password(password, stored or _DUMMY_HASH)
        return email if ok and stored else None


class SessionStore:
    """Session token -> (email, expiry), in memory."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: dict[str, tuple[str, float]] = {}

    def create(self, email: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._prune()
            self._sessions[token] = (email, time.time() + SESSION_HOURS * 3600)
        return token

    def lookup(self, token: str) -> str | None:
        with self._lock:
            entry = self._sessions.get(token)
            if entry is None:
                return None
            if entry[1] <= time.time():
                del self._sessions[token]
                return None
            return entry[0]

    def revoke(self, token: str):
        with self._lock:
            self._sessions.pop(token, None)

    def revoke_user(self, email: str):
        with self._lock:
            for t in [t for t, (e, _) in self._sessions.items() if e == email]:
                del self._sessions[t]

    def clear(self):
        with self._lock:
            self._sessions.clear()

    def _prune(self):
        now = time.time()
        for t in [t for t, (_, exp) in self._sessions.items() if exp <= now]:
            del self._sessions[t]


class Throttle:
    """Failed logins per key, in a sliding window."""

    def __init__(self):
        self._lock = threading.Lock()
        self._fails: dict[str, list[float]] = {}

    def _recent(self, key: str, now: float) -> list[float]:
        window = LOCKOUT_MINUTES * 60
        kept = [t for t in self._fails.get(key, []) if now - t < window]
        if kept:
            self._fails[key] = kept
        else:
            self._fails.pop(key, None)
        return kept

    def blocked(self, *keys: str) -> bool:
        now = time.time()
        with self._lock:
            return any(len(self._recent(k, now)) >= MAX_FAILURES for k in keys)

    def fail(self, *keys: str):
        now = time.time()
        with self._lock:
            for k in keys:
                self._recent(k, now)
                self._fails.setdefault(k, []).append(now)

    def reset(self, *keys: str):
        with self._lock:
            for k in keys:
                self._fails.pop(k, None)


user_store = UserStore(USERS_FILE)
sessions = SessionStore()
throttle = Throttle()


def session_email(authorization: list[str]) -> str | None:
    """The user behind an ``Authorization: Bearer <session>`` header, if any."""
    if len(authorization) != 1:
        return None
    scheme, _, presented = authorization[0].partition(" ")
    if scheme.lower() != "bearer":
        return None
    token = presented.strip()
    email = sessions.lookup(token)
    # A user removed from the file (``harvey users remove``, often from
    # another process) loses any session still open here.
    if not email:
        return None
    try:
        known = email in user_store.emails()
    except UserError:
        known = False  # unreadable users file: fail closed
    if not known:
        sessions.revoke(token)
        return None
    return email


def _client_key(request: Request) -> str:
    # Behind Railway's proxy the socket peer is the proxy; the last
    # X-Forwarded-For hop is the one the proxy itself added.
    forwarded = request.headers.get("x-forwarded-for", "")
    hop = forwarded.split(",")[-1].strip() if forwarded else ""
    return "ip:" + (hop or (request.client.host if request.client else "?"))


# ── API ──

router = APIRouter()

LOGIN_PATH = "/api/login"


@router.post(LOGIN_PATH)
async def api_login(request: Request):
    """Public (no token): email + password -> a session token."""
    media = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media != "application/json":
        return JSONResponse({"error": "unsupported_media_type",
                             "message": "El cuerpo debe ser application/json."}, status_code=415)
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return JSONResponse({"error": "bad_request", "message": "Faltan email y contraseña."},
                            status_code=400)
    email = str(body.get("email") or "")[:320]
    password = str(body.get("password") or "")[:1024]
    keys = ("email:" + email.strip().lower(), _client_key(request))
    if throttle.blocked(*keys):
        return JSONResponse({"error": "too_many_attempts",
                             "message": f"Demasiados intentos. Espera {LOCKOUT_MINUTES} minutos."},
                            status_code=429)
    who = user_store.authenticate(email, password)
    if who is None:
        throttle.fail(*keys)
        return JSONResponse({"error": "bad_credentials",
                             "message": "Email o contraseña incorrectos."}, status_code=401)
    throttle.reset(keys[0])
    return {"token": sessions.create(who), "email": who, "expires_in": SESSION_HOURS * 3600}


@router.post("/api/logout")
async def api_logout(request: Request):
    auth = request.headers.get("authorization", "")
    scheme, _, presented = auth.partition(" ")
    if scheme.lower() == "bearer":
        sessions.revoke(presented.strip())
    return {"success": True}


@router.get("/api/me")
async def api_me(request: Request):
    email = session_email(request.headers.getlist("authorization"))
    return {"email": email, "admin": email is None}
