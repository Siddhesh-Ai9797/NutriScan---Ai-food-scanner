"""
Sign-in checks and per-user limits for the API.

Every paid endpoint (GPT-4o, S3, DynamoDB) requires a Firebase ID token sent
as `Authorization: Bearer <token>`. Tokens are verified locally against
Google's public signing certificates, so no Firebase service account is needed.
"""
import os
import time
from collections import defaultdict, deque

import httpx
from fastapi import Depends, HTTPException, Request
from google.auth import jwt as google_jwt

FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "nutriscan-ai-e6e8f")
CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
CLOCK_SKEW_SECONDS = 30

_certs: dict = {}
_certs_expire_at: float = 0.0


async def _fetch_certs() -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(CERTS_URL)
    response.raise_for_status()
    max_age = 3600
    for part in response.headers.get("cache-control", "").split(","):
        part = part.strip()
        if part.startswith("max-age="):
            try:
                max_age = int(part.split("=", 1)[1])
            except ValueError:
                pass
    return {"certs": response.json(), "max_age": max_age}


async def _get_certs(force: bool = False) -> dict:
    global _certs, _certs_expire_at
    if force or not _certs or time.time() >= _certs_expire_at:
        fetched = await _fetch_certs()
        _certs = fetched["certs"]
        _certs_expire_at = time.time() + fetched["max_age"]
    return _certs


def _decode(token: str, certs: dict) -> dict:
    claims = google_jwt.decode(
        token,
        certs=certs,
        audience=FIREBASE_PROJECT_ID,
        clock_skew_in_seconds=CLOCK_SKEW_SECONDS,
    )
    if claims.get("iss") != f"https://securetoken.google.com/{FIREBASE_PROJECT_ID}":
        raise ValueError("wrong issuer")
    if not claims.get("sub"):
        raise ValueError("missing subject")
    auth_time = claims.get("auth_time")
    if auth_time is not None and auth_time > time.time() + CLOCK_SKEW_SECONDS:
        raise ValueError("auth_time in the future")
    return claims


async def verify_token(token: str) -> dict:
    """Returns the token's claims or raises ValueError."""
    certs = await _get_certs()
    try:
        return _decode(token, certs)
    except Exception:
        # Google rotates keys; retry once with fresh certificates.
        certs = await _get_certs(force=True)
        return _decode(token, certs)


async def require_user(request: Request) -> str:
    """FastAPI dependency: returns the signed-in user's id or rejects with 401."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Please sign in to use NutriScan.")
    token = header.split(" ", 1)[1].strip()
    try:
        claims = await verify_token(token)
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Sign-in check is temporarily unavailable. Try again.")
    except Exception:
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
    request.state.uid = claims["sub"]
    request.state.claims = claims
    return claims["sub"]


async def require_admin(request: Request, uid: str = Depends(require_user)) -> str:
    """
    FastAPI dependency: only the email in the ADMIN_EMAIL server variable passes.
    The email never reaches the browser bundle.
    """
    admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    email = str(request.state.claims.get("email", "")).strip().lower()
    if not admin_email or email != admin_email:
        raise HTTPException(status_code=403, detail="Admins only.")
    return uid


# ── Per-user limits (single Railway replica, so memory is enough) ─────────
_calls: dict = defaultdict(deque)


def rate_limit(bucket: str, max_calls: int, per_seconds: int = 3600):
    """Dependency factory: at most `max_calls` per user per window for this bucket."""
    async def _check(uid: str = Depends(require_user)) -> str:
        now = time.time()
        calls = _calls[(bucket, uid)]
        while calls and calls[0] <= now - per_seconds:
            calls.popleft()
        if len(calls) >= max_calls:
            raise HTTPException(
                status_code=429,
                detail="You've reached the limit for now. Please try again a little later.",
            )
        calls.append(now)
        return uid
    return _check
