import asyncio
import httpx
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

BASE_URL = "http://localhost:8000"

async def run_tests():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        print("=== Starting Category CRUD and Ingestion Integration Tests ===\n")

        # 1. Fetch all seeded categories
        print("[1] Testing GET /categories (Seeded list)")
        res = await client.get("/categories")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        categories = res.json()
        cat_names = [c["name"] for c in categories]
        print(f" -> Found seeded categories: {cat_names}")
        assert "Paint" in cat_names, "Paint not found in categories"
        assert "Building Materials" in cat_names, "Building Materials not found in categories"

        # 2. Add a new category
        print("\n[2] Testing POST /categories (Create new)")
        res = await client.post("/categories", json={"name": "Plumbing"})
        assert res.status_code == 201, f"Expected 201, got {res.status_code}"
        plumbing_cat = res.json()
        plumbing_id = plumbing_cat["id"]
        print(f" -> Created 'Plumbing' category with ID: {plumbing_id}")
        assert plumbing_cat["name"] == "Plumbing"

        # 3. Prevent duplicate creation
        print("\n[3] Testing POST /categories (Duplicate prevention)")
        res = await client.post("/categories", json={"name": "plumbing"})
        assert res.status_code == 400, f"Expected 400, got {res.status_code}"
        print(f" -> Properly prevented duplicate: {res.json()['detail']}")

        # 4. Save a bill with the new category
        print("\n[4] Testing POST /save (Category propagation to bill and products)")
        bill_payload = {
            "dealer_name": "Test Pipes Ltd",
            "invoice_no": "PIPE-998",
            "date": "2026-06-13",
            "items": [
                {
                    "product": "PVC Pipe 3 inch",
                    "quantity": 10.0,
                    "unit": "pcs",
                    "price": 120.0,
                    "amount": 1200.0
                }
            ],
            "subtotal": 1200.0,
            "gst": 0.0,
            "total": 1200.0,
            "category": "Plumbing"
        }
        res = await client.post("/save", json=bill_payload)
        assert res.status_code == 201, f"Expected 201, got {res.status_code}"
        save_result = res.json()
        bill_db_id = save_result["id"]
        print(f" -> Bill saved successfully. Bill ID: {bill_db_id}")

        # Check saved bill details
        res = await client.get(f"/bill/{bill_db_id}")
        assert res.status_code == 200
        bill_doc = res.json()
        print(f" -> Saved bill category is: '{bill_doc.get('category')}'")
        assert bill_doc.get("category") == "Plumbing"

        # Check products in MongoDB to see if category cascaded
        # We can fetch categories via product query using endpoints or direct DB check.
        # Since we are using endpoint integrations, let's check via get products analytics or helper.
        # Let's check using DB connection or verify through same product comparisons
        from app.database.database import db_manager
        db_manager.connect()
        db = db_manager.get_db()
        
        prod_doc = await db["products"].find_one({"name": "PVC Pipe 3 inch"})
        print(f" -> Database product record category: '{prod_doc.get('category')}'")
        assert prod_doc.get("category") == "Plumbing", "Product category not updated to Plumbing"

        # 5. Update the category name
        print("\n[5] Testing PUT /categories/{id} (Cascade rename)")
        res = await client.put(f"/categories/{plumbing_id}", json={"name": "Plumbing & Sanitation"})
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        updated_cat = res.json()
        print(f" -> Updated category name to: '{updated_cat['name']}'")
        assert updated_cat["name"] == "Plumbing & Sanitation"

        # Verify cascades in DB
        prod_doc = await db["products"].find_one({"name": "PVC Pipe 3 inch"})
        print(f" -> Cascaded product category: '{prod_doc.get('category')}'")
        assert prod_doc.get("category") == "Plumbing & Sanitation"

        res = await client.get(f"/bill/{bill_db_id}")
        bill_doc = res.json()
        print(f" -> Cascaded bill category: '{bill_doc.get('category')}'")
        assert bill_doc.get("category") == "Plumbing & Sanitation"

        # 6. Delete the category
        print("\n[6] Testing DELETE /categories/{id} (Cascade deletion reset)")
        res = await client.delete(f"/categories/{plumbing_id}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        print(f" -> Category deleted successfully: {res.json()['message']}")

        # Verify category references reset to "" in DB
        prod_doc = await db["products"].find_one({"name": "PVC Pipe 3 inch"})
        print(f" -> Product category reset: '{prod_doc.get('category')}'")
        assert prod_doc.get("category") == "", f"Expected empty product category, got '{prod_doc.get('category')}'"

        res = await client.get(f"/bill/{bill_db_id}")
        bill_doc = res.json()
        print(f" -> Bill category reset: '{bill_doc.get('category')}'")
        assert bill_doc.get("category") == "", f"Expected empty bill category, got '{bill_doc.get('category')}'"

        # Clean up test bill and product
        bill_doc = await db["bills"].find_one({"invoice_no": "PIPE-998"})
        if bill_doc:
            await db["bills"].delete_one({"_id": bill_doc["_id"]})
        await db["products"].delete_one({"name": "PVC Pipe 3 inch"})
        db_manager.disconnect()

        print("\n=== All Category CRUD & Cascade Tests Passed Successfully! ===")

if __name__ == "__main__":
    asyncio.run(run_tests())
