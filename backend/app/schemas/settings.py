from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional

class OrganizationSettingsSchema(BaseModel):
    org_name: str = Field(..., description="Organization name (min 2 characters)", min_length=2)
    currency: str = Field(..., description="Default currency (e.g. Indian Rupee (₹))")
    timezone: str = Field(..., description="Timezone (e.g. Asia/Kolkata)")
    date_format: str = Field(..., description="Display date format (e.g. 10 Apr 2026)")
    is_onboarded: Optional[bool] = Field(None, description="Whether onboarding is complete")

    @field_validator("org_name", "currency", "timezone", "date_format")
    @classmethod
    def strip_fields(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

class ProfileSettingsSchema(BaseModel):
    display_name: str = Field(..., description="User's display name", min_length=2)
    email: EmailStr = Field(..., description="User's display email")
    locale: str = Field(..., description="Language/Locale (e.g. English (India))")
    time_format: str = Field(..., description="Time display format (12-hour or 24-hour)")

    @field_validator("time_format")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        clean_val = v.strip().lower()
        if clean_val not in ["12-hour", "24-hour"]:
            raise ValueError("Time display format must be either '12-hour' or '24-hour'")
        return clean_val

    @field_validator("display_name", "locale")
    @classmethod
    def strip_fields(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()
