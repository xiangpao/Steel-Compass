from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
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
from ..models import LoginSession, User


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserView)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> User:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not user.is_active or not verify_password(
        user.password_hash, payload.password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误"
        )
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
