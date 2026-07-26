from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from datetime import datetime

class EmailRecipientSchema(BaseModel):
    email: EmailStr = Field(..., description="Recipient email address")
    is_enabled: bool = Field(True, description="Whether this email receives the report")

class MonthlyReportScheduleSchema(BaseModel):
    day_of_month: int = Field(2, ge=1, le=28, description="Fixed day of the month to send the report (1 to 28)")

class AgentSettingsResponseSchema(BaseModel):
    agent_type: str = Field("monthly_report", description="Identifier of the agent type")
    is_enabled: bool = Field(True, description="Is the agent active")
    schedule_config: MonthlyReportScheduleSchema = Field(default_factory=MonthlyReportScheduleSchema)
    delivery_emails: List[EmailRecipientSchema] = Field(default_factory=list, max_length=6) # 1 primary + max 5 added
    last_run: Optional[datetime] = Field(None, description="Timestamp of the last run")
    next_run: Optional[datetime] = Field(None, description="Timestamp of the next scheduled run")

class AgentSettingsUpdateSchema(BaseModel):
    is_enabled: Optional[bool] = Field(None, description="Enable or disable the agent")
    day_of_month: Optional[int] = Field(None, ge=1, le=28, description="Update fixed schedule day (1-28)")

class EmailRecipientUpdateSchema(BaseModel):
    email: EmailStr = Field(..., description="The email recipient address to update")
    is_enabled: bool = Field(..., description="Toggle status for this email")

class EmailRecipientAddSchema(BaseModel):
    email: EmailStr = Field(..., description="Email address to add to recipients list")


class YearlyReportScheduleSchema(BaseModel):
    month: int = Field(1, ge=1, le=12, description="Month of year (1 to 12)")
    day: int = Field(15, ge=1, le=28, description="Day of month (1 to 28)")


class YearlyAgentSettingsResponseSchema(BaseModel):
    agent_type: str = Field("yearly_report", description="Identifier of the agent type")
    is_enabled: bool = Field(True, description="Is the agent active")
    schedule_config: YearlyReportScheduleSchema = Field(default_factory=YearlyReportScheduleSchema)
    delivery_emails: List[EmailRecipientSchema] = Field(default_factory=list, max_length=6) # 1 primary + max 5 added
    last_run: Optional[datetime] = Field(None, description="Timestamp of the last run")
    next_run: Optional[datetime] = Field(None, description="Timestamp of the next scheduled run")


class YearlyAgentSettingsUpdateSchema(BaseModel):
    is_enabled: Optional[bool] = Field(None, description="Enable or disable the agent")
    month: Optional[int] = Field(None, ge=1, le=12, description="Month of year (1 to 12)")
    day: Optional[int] = Field(None, ge=1, le=28, description="Day of month (1 to 28)")

