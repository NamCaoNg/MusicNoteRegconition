import os
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.deps import get_db
from app.auth import create_access_token
from app.error_utils import build_error_detail
from app.schemas import UserRegister, UserLogin, UserResponse, TokenResponse
from app.services.user_service import (
    get_user_by_username,
    create_user,
    authenticate_user,
)

router = APIRouter()

LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_WINDOW_SECONDS = int(os.getenv("LOGIN_WINDOW_SECONDS", "300"))
LOGIN_BLOCK_SECONDS = int(os.getenv("LOGIN_BLOCK_SECONDS", "300"))

_LOGIN_LOCK = threading.Lock()
_LOGIN_STATE: dict[str, dict[str, float | int]] = {}


def _client_key(username: str, client_ip: str | None) -> str:
    return f"{username.lower()}|{client_ip or 'unknown'}"


def _extract_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first_ip = forwarded_for.split(",")[0].strip()
        if first_ip:
            return first_ip

    if request.client is not None:
        return request.client.host

    return None


def _is_login_blocked(key: str) -> bool:
    now = time.time()
    with _LOGIN_LOCK:
        state = _LOGIN_STATE.get(key)
        if not state:
            return False

        blocked_until = float(state.get("blocked_until", 0.0))
        if blocked_until > now:
            return True

        if blocked_until > 0 and blocked_until <= now:
            _LOGIN_STATE.pop(key, None)
        return False


def _record_login_failure(key: str) -> None:
    now = time.time()
    with _LOGIN_LOCK:
        state = _LOGIN_STATE.get(key)
        if not state:
            state = {
                "first_failed_at": now,
                "fail_count": 0,
                "blocked_until": 0.0,
            }
            _LOGIN_STATE[key] = state

        first_failed_at = float(state["first_failed_at"])
        if now - first_failed_at > LOGIN_WINDOW_SECONDS:
            state["first_failed_at"] = now
            state["fail_count"] = 0
            state["blocked_until"] = 0.0

        state["fail_count"] = int(state["fail_count"]) + 1
        if int(state["fail_count"]) >= LOGIN_MAX_ATTEMPTS:
            state["blocked_until"] = now + LOGIN_BLOCK_SECONDS


def _clear_login_failures(key: str) -> None:
    with _LOGIN_LOCK:
        _LOGIN_STATE.pop(key, None)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    """Register a new user account."""
    existing = get_user_by_username(db, payload.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=build_error_detail("auth_username_exists", "Username already exists"),
        )

    user = create_user(db, username=payload.username, password=payload.password)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)):
    """Login and receive a JWT access token."""
    key = _client_key(payload.username, _extract_client_ip(request))
    if _is_login_blocked(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=build_error_detail(
                "auth_login_rate_limited",
                "Too many failed login attempts. Please try again later.",
            ),
        )

    user = authenticate_user(db, username=payload.username, password=payload.password)
    if user is None:
        _record_login_failure(key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=build_error_detail("auth_invalid_credentials", "Invalid username or password"),
        )

    _clear_login_failures(key)
    token = create_access_token(data={"sub": user.username})
    return TokenResponse(access_token=token)


@router.post("/token", response_model=TokenResponse)
def token_login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """OAuth2 password flow endpoint used by Swagger Authorize."""
    key = _client_key(form_data.username, _extract_client_ip(request))
    if _is_login_blocked(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=build_error_detail(
                "auth_login_rate_limited",
                "Too many failed login attempts. Please try again later.",
            ),
        )

    user = authenticate_user(db, username=form_data.username, password=form_data.password)
    if user is None:
        _record_login_failure(key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=build_error_detail("auth_invalid_credentials", "Invalid username or password"),
        )

    _clear_login_failures(key)
    token = create_access_token(data={"sub": user.username})
    return TokenResponse(access_token=token)
