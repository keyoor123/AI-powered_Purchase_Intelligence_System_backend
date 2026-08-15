from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional

class UserSignupSchema(BaseModel):
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., description="User's password (min 6 characters)", min_length=6)
    display_name: str = Field(..., description="User's name (min 2 characters)", min_length=2)

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()

class UserLoginSchema(BaseModel):
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., description="User's password")

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()

class ForgotPasswordSchema(BaseModel):
    email: EmailStr = Field(..., description="User's registered email address")

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()

class ResetPasswordSchema(BaseModel):
    token: str = Field(..., description="Password reset JWT token")
    new_password: str = Field(..., description="New password (min 6 characters)", min_length=6)

class TokenResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict = Field(..., description="Basic details of the logged in user")

class VerifyEmailSchema(BaseModel):
    email: EmailStr = Field(..., description="User's email address")
    code: str = Field(..., description="6-digit verification OTP code", min_length=6, max_length=6)

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()

class ResendVerificationSchema(BaseModel):
    email: EmailStr = Field(..., description="User's email address")

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()
