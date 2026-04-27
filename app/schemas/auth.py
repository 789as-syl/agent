"""Schema模块：auth。"""

from __future__ import annotations

import re
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11)
    password: str = Field(..., min_length=8, max_length=64)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        if not re.match(r"^1[3-9]\d{9}$", value):
            raise ValueError("invalid phone format")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not any(ch.isupper() for ch in value):
            raise ValueError("password must include uppercase letter")
        if not any(ch.islower() for ch in value):
            raise ValueError("password must include lowercase letter")
        if not any(ch.isdigit() for ch in value):
            raise ValueError("password must include digit")
        return value


class LoginRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11)
    password: str = Field(..., min_length=8, max_length=64)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        if not re.match(r"^1[3-9]\d{9}$", value):
            raise ValueError("invalid phone format")
        return value


class RefreshRequest(BaseModel):
    refresh_token: str | None = Field(default=None, description="refresh token from body; optional if cookie exists")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    access_expires_in: int


class UserResponse(BaseModel):
    id: UUID
    phone: str
    role: str = "user"

    model_config = {"from_attributes": True}
