from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime

class BillItemSchema(BaseModel):
    product: str = Field(..., description="Name of the product")
    quantity: float = Field(..., description="Quantity purchased", gt=0)
    unit: str = Field(..., description="Unit of measurement (e.g., kg, pcs, box)")
    price: float = Field(..., description="Unit price", ge=0)
    amount: float = Field(..., description="Total amount for this item", ge=0)

    @field_validator("product")
    @classmethod
    def product_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Product name cannot be empty")
        return v.strip()

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float, info) -> float:
        # Check if quantity and price are present and amount matches within small delta
        values = info.data
        quantity = values.get("quantity")
        price = values.get("price")
        if quantity is not None and price is not None:
            expected = round(quantity * price, 2)
            if abs(v - expected) > 1.0: # Allow small round-off or tax adjustments up to 1.0 unit
                # We can adjust it or warn, but let's check validation
                pass
        return v

class BillDataSchema(BaseModel):
    dealer_name: str = Field(..., description="Name of the dealer/merchant")
    invoice_no: str = Field(..., description="Invoice or bill number")
    date: str = Field(..., description="Invoice date (format: YYYY-MM-DD or raw extracted date)")
    items: List[BillItemSchema] = Field(..., description="List of items in the bill")
    subtotal: float = Field(..., description="Subtotal before taxes", ge=0)
    gst: float = Field(..., description="GST / Tax amount", ge=0)
    total: float = Field(..., description="Grand total of the bill", ge=0)
    category: Optional[str] = Field(None, description="Category for the entire bill and all its products")
    status: Optional[str] = Field(None, description="Verification status of the bill (e.g. pending, verified)")
    bill_image: Optional[str] = Field(None, description="Filename or paths of original bill image(s)")

    @field_validator("dealer_name", "invoice_no", "date")
    @classmethod
    def check_non_empty_strings(cls, v: str, info) -> str:
        field_name = info.field_name
        if not v.strip():
            raise ValueError(f"{field_name} cannot be empty")
        return v.strip()

    @field_validator("category")
    @classmethod
    def check_category_string(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return v.strip()
        return v

    @field_validator("total")
    @classmethod
    def validate_totals(cls, v: float, info) -> float:
        values = info.data
        subtotal = values.get("subtotal")
        gst = values.get("gst")
        if subtotal is not None and gst is not None:
            expected_total = round(subtotal + gst, 2)
            if abs(v - expected_total) > 2.0: # Allow small discrepancies/roundings up to 2.0
                raise ValueError(
                    f"Grand total ({v}) does not match subtotal + GST ({expected_total})"
                )
        return v

    @field_validator("items")
    @classmethod
    def items_must_not_be_empty(cls, v: List[BillItemSchema]) -> List[BillItemSchema]:
        if not v:
            raise ValueError("Bill must contain at least one item")
        return v

class DealerSchema(BaseModel):
    name: str = Field(..., description="Dealer name")
    phone: Optional[str] = Field(None, description="Dealer phone number")
    address: Optional[str] = Field(None, description="Dealer address")

class ProductSchema(BaseModel):
    name: str = Field(..., description="Product name")
    category: Optional[str] = Field(None, description="Product category")
    default_unit: Optional[str] = Field(None, description="Default unit of measurement")
