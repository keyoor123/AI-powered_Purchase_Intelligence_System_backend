import sys
from pathlib import Path
from pydantic import ValidationError
from unittest.mock import MagicMock, patch

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

from app.schemas.bill import BillDataSchema
from fastapi.testclient import TestClient
from app.main import app
from app.utils.auth import get_current_user_id
from app.database.database import db_manager

# --- Unit Tests for Pydantic Schema ---

def test_pydantic_validation_success_without_category():
    """Verify that BillDataSchema allows missing or empty category."""
    data_missing = {
        "dealer_name": "Prakash Materials",
        "invoice_no": "INV-12345",
        "date": "2026-06-14",
        "items": [
            {
                "product": "Concrete Mix",
                "quantity": 10.0,
                "unit": "bag",
                "price": 350.0,
                "amount": 3500.0
            }
        ],
        "subtotal": 3500.0,
        "gst": 0.0,
        "total": 3500.0
    }
    
    # Validation should pass because category has a default value (None)
    schema = BillDataSchema(**data_missing)
    assert schema.category is None
    print("[PASS] Pydantic successfully validated schema with missing category")

    # Data with empty/whitespace category
    data_empty = data_missing.copy()
    data_empty["category"] = "   "
    schema_empty = BillDataSchema(**data_empty)
    # The validator strips it, resulting in ""
    assert schema_empty.category == ""
    print("[PASS] Pydantic successfully validated schema with empty whitespace category")

    # Data with valid category
    data_valid = data_missing.copy()
    data_valid["category"] = "Construction"
    schema_valid = BillDataSchema(**data_valid)
    assert schema_valid.category == "Construction"
    print("[PASS] Pydantic successfully validated schema with valid category")

def test_pydantic_validation_fails_on_other_required_fields():
    """Verify that other required fields still raise ValidationError if missing."""
    bad_data = {
        "dealer_name": "   ",  # dealer_name is empty
        "invoice_no": "INV-123",
        "date": "2026-06-14",
        "items": [],
        "subtotal": 0.0,
        "gst": 0.0,
        "total": 0.0
    }
    
    try:
        BillDataSchema(**bad_data)
        assert False, "Should have failed due to empty dealer_name and empty items"
    except ValidationError as e:
        print("[PASS] Validation correctly failed on empty dealer_name and empty items list:")
        print(f" -> {e}")


# --- Integration Tests for Endpoints using TestClient and Mock DB ---

# Mock database collection class for offline testing
class AsyncMockCollection:
    def __init__(self, name):
        self.name = name
    async def find_one(self, *args, **kwargs):
        return None
    async def insert_one(self, *args, **kwargs):
        mock_result = MagicMock()
        # Return a valid 24-character hex string for ObjectId representation
        mock_result.inserted_id = "507f1f77bcf86cd799439011"
        return mock_result
    async def update_one(self, *args, **kwargs):
        return MagicMock()

def test_save_endpoint_category_enforcement():
    """Verify that POST /save fails if category is missing/empty, and succeeds if present."""
    
    # 1. Override auth and database dependency to bypass validation/connection checks
    from app.database.database import get_database
    app.dependency_overrides[get_current_user_id] = lambda: "mock_user_123"
    app.dependency_overrides[get_database] = lambda: MagicMock()
    
    # 2. Mock database manager methods using patch
    mock_dealers = AsyncMockCollection("dealers")
    mock_products = AsyncMockCollection("products")
    mock_bills = AsyncMockCollection("bills")
    mock_logs = AsyncMockCollection("processing_logs")

    with patch.object(db_manager, "get_dealers_collection", return_value=mock_dealers), \
         patch.object(db_manager, "get_products_collection", return_value=mock_products), \
         patch.object(db_manager, "get_bills_collection", return_value=mock_bills), \
         patch.object(db_manager, "get_processing_logs_collection", return_value=mock_logs):
        
        client = TestClient(app)
        
        # Payload with missing category
        payload_missing_category = {
            "dealer_name": "Prakash Materials",
            "invoice_no": "INV-12345",
            "date": "2026-06-14",
            "items": [
                {
                    "product": "Concrete Mix",
                    "quantity": 10.0,
                    "unit": "bag",
                    "price": 350.0,
                    "amount": 3500.0
                }
            ],
            "subtotal": 3500.0,
            "gst": 0.0,
            "total": 3500.0
        }

        # Request with missing category should return 400 Bad Request
        res = client.post("/save", json=payload_missing_category)
        assert res.status_code == 400, f"Expected 400, got {res.status_code}"
        assert "Category is strictly required to save the bill" in res.json()["detail"]
        print("[PASS] POST /save correctly returned 400 Bad Request when category was missing")

        # Payload with empty/whitespace category
        payload_empty_category = payload_missing_category.copy()
        payload_empty_category["category"] = "    "
        res = client.post("/save", json=payload_empty_category)
        assert res.status_code == 400, f"Expected 400, got {res.status_code}"
        assert "Category is strictly required to save the bill" in res.json()["detail"]
        print("[PASS] POST /save correctly returned 400 Bad Request when category was whitespace-only")

        # Payload with valid category should succeed (201 Created)
        payload_valid_category = payload_missing_category.copy()
        payload_valid_category["category"] = "Construction Materials"
        res = client.post("/save", json=payload_valid_category)
        assert res.status_code == 201, f"Expected 201, got {res.status_code}"
        assert res.json()["success"] is True
        assert res.json()["id"] == "507f1f77bcf86cd799439011"
        print("[PASS] POST /save succeeded with 201 when valid category was provided")

    # Clean up overrides
    app.dependency_overrides.clear()

if __name__ == "__main__":
    print("=== Running Backend Category Validation Refactoring Tests ===")
    test_pydantic_validation_success_without_category()
    test_pydantic_validation_fails_on_other_required_fields()
    test_save_endpoint_category_enforcement()
    print("=== All Refactoring Tests Passed Successfully! ===")
