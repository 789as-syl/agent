# ruff: noqa: B008
"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Body, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.exceptions import ValidationError
from app.models.engine import get_async_session
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.auth_service import AuthService
from app.services.token_service import TokenService

router = APIRouter(prefix="/auth", tags=["Authentication"])

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth/refresh"
LEGACY_REFRESH_COOKIE_PATH = "/api/auth/refresh"
ACCESS_COOKIE_NAME = "access_token"
ACCESS_COOKIE_PATH = "/api/v1"


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    auth_service = AuthService(session)
    user = await auth_service.register(phone=request.phone, password=request.password)
    tokens = TokenService.generate_tokens(user_id=user.id, phone=user.phone)
    _set_refresh_token_cookie(response, tokens["refresh_token"], tokens["refresh_expires_in"])
    _set_access_token_cookie(response, tokens["access_token"], tokens["access_expires_in"])

    return TokenResponse(
        access_token=tokens["access_token"],
        token_type=tokens["token_type"],
        access_expires_in=tokens["access_expires_in"],
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    auth_service = AuthService(session)
    user = await auth_service.authenticate(phone=request.phone, password=request.password)
    tokens = TokenService.generate_tokens(user_id=user.id, phone=user.phone)
    _set_refresh_token_cookie(response, tokens["refresh_token"], tokens["refresh_expires_in"])
    _set_access_token_cookie(response, tokens["access_token"], tokens["access_expires_in"])

    return TokenResponse(
        access_token=tokens["access_token"],
        token_type=tokens["token_type"],
        access_expires_in=tokens["access_expires_in"],
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    request: RefreshRequest = Body(default_factory=RefreshRequest),
    session: AsyncSession = Depends(get_async_session),
    refresh_token_cookie: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> TokenResponse:
    refresh_token = request.refresh_token or refresh_token_cookie
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is required")

    try:
        tokens = await TokenService.refresh_access_token(refresh_token, session=session)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.message) from exc
    if "refresh_token" in tokens:
        _set_refresh_token_cookie(response, tokens["refresh_token"], tokens["refresh_expires_in"])
    _set_access_token_cookie(response, tokens["access_token"], tokens["access_expires_in"])

    return TokenResponse(
        access_token=tokens["access_token"],
        token_type="bearer",
        access_expires_in=tokens["access_expires_in"],
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    request: RefreshRequest = Body(default_factory=RefreshRequest),
    refresh_token_cookie: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> None:
    refresh_token = request.refresh_token or refresh_token_cookie

    if refresh_token:
        try:
            payload = await TokenService.validate_refresh_token(refresh_token)
            jti = payload.get("jti")
            if jti:
                import time

                exp = payload.get("exp", 0)
                remaining = max(int(exp - time.time()), 0)
                if remaining > 0:
                    await TokenService.blacklist_token(jti, remaining)
        except Exception:
            pass

    _clear_refresh_cookie(response)
    _clear_access_cookie(response)


def _set_refresh_token_cookie(response: Response, token: str, max_age: int) -> None:
    for cookie_path in {REFRESH_COOKIE_PATH, LEGACY_REFRESH_COOKIE_PATH}:
        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=token,
            httponly=True,
            secure=settings.app_env == "production",
            samesite="strict",
            max_age=max_age,
            path=cookie_path,
        )


def _set_access_token_cookie(response: Response, token: str, max_age: int) -> None:
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="strict",
        max_age=max_age,
        path=ACCESS_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    for cookie_path in {REFRESH_COOKIE_PATH, LEGACY_REFRESH_COOKIE_PATH, "/api/v1/auth"}:
        response.delete_cookie(
            key=REFRESH_COOKIE_NAME,
            path=cookie_path,
            secure=settings.app_env == "production",
            httponly=True,
            samesite="strict",
        )


def _clear_access_cookie(response: Response) -> None:
    response.delete_cookie(
        key=ACCESS_COOKIE_NAME,
        path=ACCESS_COOKIE_PATH,
        secure=settings.app_env == "production",
        httponly=True,
        samesite="strict",
    )
