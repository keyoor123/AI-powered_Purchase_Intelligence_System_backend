from typing import List, Optional, Annotated, Any
from pydantic import BaseModel, Field, BeforeValidator
from datetime import datetime

# Convert ObjectId to string for Pydantic serialization
PyObjectId = Annotated[str, BeforeValidator(str)]

class BillItemDB(BaseModel):
    product: str
    quantity: float
    unit: str
    price: float
    amount: float

class UserDocument(BaseModel):
    id: Optional[PyObjectId] = Field(None, alias="_id")
    email: str
    hashed_password: str
    display_name: str
    is_verified: bool = False
    verification_code: Optional[str] = None
    verification_code_expires_at: Optional[datetime] = None
    failed_login_attempts: int = 0
    lockout_until: Optional[datetime] = None
    failed_otp_attempts: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True
    }

class SettingsDocument(BaseModel):
    id: Optional[PyObjectId] = Field(None, alias="_id")
    user_id: str
    type: str  # "organization" or "profile"
    value: dict
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True
    }

class BillDocument(BaseModel):
    id: Optional[PyObjectId] = Field(None, alias="_id")
    user_id: str
    dealer_name: str
    invoice_no: str
    date: str
    bill_image: str
    subtotal: float
    gst: float
    total: float
    status: str = "pending"  # pending, verified
    items: List[BillItemDB]
    category: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "json_encoders": {datetime: lambda v: v.isoformat()},
        "arbitrary_types_allowed": True
    }

class CategoryDocument(BaseModel):
    id: Optional[PyObjectId] = Field(None, alias="_id")
    user_id: str
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True
    }

class DealerDocument(BaseModel):
    id: Optional[PyObjectId] = Field(None, alias="_id")
    user_id: str
    name: str
    phone: Optional[str] = ""
    address: Optional[str] = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True
    }

class ProductDocument(BaseModel):
    id: Optional[PyObjectId] = Field(None, alias="_id")
    user_id: str
    name: str
    category: Optional[str] = ""
    default_unit: Optional[str] = ""

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True
    }

class ProcessingLogDocument(BaseModel):
    id: Optional[PyObjectId] = Field(None, alias="_id")
    bill_id: Optional[str] = None
    ocr_status: str
    llm_status: str
    validation_status: str
    message: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True
    }
