from __future__ import annotations

import os
import secrets
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

ADMIN_EMAIL = os.environ.get("NORTHOPS_EMAIL", "admin@northops.com").strip().lower()
ADMIN_PASSWORD = os.environ.get("NORTHOPS_PASSWORD", "northops")

PUBLIC_EXACT = {
    "/login",
    "/login.html",
    "/styles.css",
    "/login.js",
    "/api/login",
    "/favicon.ico",
}


def session_secret() -> str:
    env = os.environ.get("NORTHOPS_SECRET")
    if env:
        return env
    path = Path.home() / ".northops-prophet" / "session_secret"
    try:
        if path.exists():
            value = path.read_text().strip()
            if value:
                return value
        path.parent.mkdir(parents=True, exist_ok=True)
        value = secrets.token_hex(32)
        path.write_text(value)
        return value
    except OSError:
        return secrets.token_hex(32)


def credentials_ok(email: str, password: str) -> bool:
    got_email = (email or "").strip().lower()
    got_pass = password or ""
    return secrets.compare_digest(got_email, ADMIN_EMAIL) and secrets.compare_digest(got_pass, ADMIN_PASSWORD)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in PUBLIC_EXACT or request.method == "OPTIONS":
            return await call_next(request)
        if request.session.get("user"):
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Sign in required"}, status_code=401)
        return RedirectResponse("/login", status_code=302)
