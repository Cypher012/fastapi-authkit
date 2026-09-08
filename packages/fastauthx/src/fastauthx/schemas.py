from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class UserPublic(BaseModel):
    id: UUID
    email: str
    name: str
    avatar_url: str | None
    email_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AccessTokenResponse(BaseModel):
    """The refresh token is deliberately absent — it only ever travels as
    an HttpOnly cookie, never in a JSON body."""

    access_token: str
    token_type: str = "bearer"


class AuthResponse(AccessTokenResponse):
    user: UserPublic


class MessageResponse(BaseModel):
    message: str
