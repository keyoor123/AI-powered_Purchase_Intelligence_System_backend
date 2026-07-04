from pydantic import BaseModel, Field, field_validator
from typing import Optional

class CategoryCreateSchema(BaseModel):
    name: str = Field(..., description="Name of the category")

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Category name cannot be empty")
        return v.strip()

class CategoryResponseSchema(BaseModel):
    id: str = Field(..., description="MongoDB ObjectId of the category", alias="id")
    name: str = Field(..., description="Name of the category")

    model_config = {
        "populate_by_name": True,
        "json_encoders": {
            # Standard string representations
        }
    }
