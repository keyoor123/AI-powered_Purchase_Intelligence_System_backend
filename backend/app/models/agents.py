from typing import List, Optional, Annotated
from pydantic import BaseModel, Field, BeforeValidator
from datetime import datetime

# Convert ObjectId to string for Pydantic serialization
PyObjectId = Annotated[str, BeforeValidator(str)]

class EmailRecipient(BaseModel):
    email: str
    is_enabled: bool = True

class MonthlyReportSchedule(BaseModel):
    day_of_month: int = Field(default=2, ge=1, le=28)

class AgentSettingsDocument(BaseModel):
    id: Optional[PyObjectId] = Field(None, alias="_id")
    user_id: str
    agent_type: str = "monthly_report"
    is_enabled: bool = True
    schedule_config: MonthlyReportSchedule = Field(default_factory=MonthlyReportSchedule)
    delivery_emails: List[EmailRecipient] = Field(default_factory=list)
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True
    }

class AgentExecutionLogDocument(BaseModel):
    id: Optional[PyObjectId] = Field(None, alias="_id")
    user_id: str
    agent_type: str = "monthly_report"
    status: str  # "success" | "failed"
    run_at: datetime = Field(default_factory=datetime.utcnow)
    emails_sent_to: List[str] = Field(default_factory=list)
    pdf_grid_file_id: Optional[str] = None  # GridFS file ID for PDF binary data
    error_message: Optional[str] = None

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True
    }
