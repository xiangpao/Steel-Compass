from __future__ import annotations

from collections import deque
from threading import Lock
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..api_schemas import (
    ChangePasswordRequest,
    CreateUserRequest,
    LoginRequest,
    UserView,
)
from ..auth import (
    create_session,
    get_current_user,
    hash_password,
    require_admin,
    revoke_user_sessions,
    verify_password,
)
from ..config import get_settings
from ..database import get_db
from ..models import User


router = APIRouter(prefix="/auth", tags=["auth"])

# Hash compared against when the username does not exist, so unknown and
# known usernames take the same argon2 time.
_DUMMY_PASSWORD_HASH = hash_password("steel-compass-timing-guard")
_LOGIN_WINDOW_SECONDS = 300
_LOGIN_MAX_FAILURES = 10
_login_failures: dict[str, deque[float]] = {}
_login_lock = Lock()


def _login_key(request: Request, username: str) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{client}|{username.lower()}"


def _recent_failures(key: str, now: float) -> deque[float]:
    attempts = _login_failures.setdefault(key, deque())
    while attempts and now - attempts[0] > _LOGIN_WINDOW_SECONDS:
        attempts.popleft()
    return attempts


@router.post("/login", response_model=UserView)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> User:
    key = _login_key(request, payload.username)
    with _login_lock:
        if len(_recent_failures(key, monotonic())) >= _LOGIN_MAX_FAILURES:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="登录失败次数过多，请 5 分钟后再试",
            )
    user = db.scalar(select(User).where(User.username == payload.username))
    password_ok = verify_password(
        user.password_hash if user is not None else _DUMMY_PASSWORD_HASH,
        payload.password,
    )
    if user is None or not user.is_active or not password_ok:
        with _login_lock:
            _recent_failures(key, monotonic()).append(monotonic())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误"
        )
    with _login_lock:
        _login_failures.pop(key, None)
    raw_token = create_session(db, user)
    settings = get_settings()
    response.set_cookie(
        key=settings.cookie_name,
        value=raw_token,
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    revoke_user_sessions(db, user.id)
    response.delete_cookie(get_settings().cookie_name, path="/")


@router.get("/me", response_model=UserView)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    if not verify_password(user.password_hash, payload.current_password):
        raise HTTPException(status_code=400, detail="当前密码错误")
    try:
        user.password_hash = hash_password(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user.must_change_password = False
    db.commit()
    revoke_user_sessions(db, user.id)
    response.delete_cookie(get_settings().cookie_name, path="/")


@router.post("/users", response_model=UserView, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: CreateUserRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> User:
    try:
        password_hash = hash_password(payload.temporary_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        password_hash=password_hash,
        is_admin=payload.is_admin,
        must_change_password=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="用户名已存在") from exc
    db.refresh(user)
    return user
