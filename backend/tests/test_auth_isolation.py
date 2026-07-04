import asyncio
import httpx
import sys
from pathlib import Path
from datetime import datetime

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

BASE_URL = "http://localhost:8000"

async def clean_database():
    print("Connecting to database for cleanup...")
    from app.database.database import db_manager
    db_manager.connect()
    db = db_manager.get_db()
    
    # Delete test users
    await db["users"].delete_many({"email": {"$in": ["usera@example.com", "userb@example.com"]}})
    
    # We will clean up bills, products, dealers, categories, and settings belonging to these users
    # We need to find the user IDs first or delete by email-derived patterns, but since we delete users,
    # we can also delete any document containing user_id in our tests during run_tests.
    db_manager.disconnect()
    print("Database cleanup pre-run completed.")

async def run_tests():
    await clean_database()
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        print("\n============================================================")
        print("=== RUNNING MULTI-TENANT ISOLATION INTEGRATION TESTS ===")
        print("============================================================\n")

        # 1. SIGNUP & LOGIN FOR USER A AND USER B
        print("[1] Signing up User A (usera@example.com)...")
        res_signup_a = await client.post("/auth/signup", json={
            "email": "usera@example.com",
            "password": "securepassword123",
            "display_name": "User A"
        })
        assert res_signup_a.status_code == 201, f"User A signup failed: {res_signup_a.text}"
        
        print("[2] Signing up User B (userb@example.com)...")
        res_signup_b = await client.post("/auth/signup", json={
            "email": "userb@example.com",
            "password": "securepassword456",
            "display_name": "User B"
        })
        assert res_signup_b.status_code == 201, f"User B signup failed: {res_signup_b.text}"

        print("[3] Logging in User A...")
        res_login_a = await client.post("/auth/login", data={
            "username": "usera@example.com",
            "password": "securepassword123"
        })
        assert res_login_a.status_code == 200, f"User A login failed: {res_login_a.text}"
        token_a = res_login_a.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        print("[4] Logging in User B...")
        res_login_b = await client.post("/auth/login", data={
            "username": "userb@example.com",
            "password": "securepassword456"
        })
        assert res_login_b.status_code == 200, f"User B login failed: {res_login_b.text}"
        token_b = res_login_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 2. CATEGORY ISOLATION TESTS
        print("\n[5] Testing Category Isolation...")
        # User A creates a custom category
        res = await client.post("/categories", json={"name": "UserA-Gold-Paint"}, headers=headers_a)
        assert res.status_code == 201
        cat_a = res.json()
        cat_a_id = cat_a["id"]
        print(f" -> User A created category: '{cat_a['name']}' (ID: {cat_a_id})")

        # User B gets categories -> verify User B does NOT see User A's custom category
        res = await client.get("/categories", headers=headers_b)
        assert res.status_code == 200
        categories_b = res.json()
        names_b = [c["name"] for c in categories_b]
        print(f" -> User B's categories: {names_b}")
        assert "UserA-Gold-Paint" not in names_b, "CRITICAL ERROR: User B can see User A's custom category!"

        # User B tries to update User A's category -> verify it fails with 404 (isolated)
        res = await client.put(f"/categories/{cat_a_id}", json={"name": "Hacked-Paint"}, headers=headers_b)
        assert res.status_code == 404, f"Expected 404, got {res.status_code}. User B was able to access User A's category!"
        print(" -> Properly isolated category update requests (User B got 404 on User A's category ID)")

        # 3. BILL INGESTION & READ ISOLATION
        print("\n[6] Testing Bill and Ingestion Isolation...")
        # User A saves a bill under their category
        bill_a_payload = {
            "dealer_name": "Dealer Gold",
            "invoice_no": "INV-GOLD-001",
            "date": "2026-06-14",
            "items": [
                {
                    "product": "UserA Exclusive Paint",
                    "quantity": 5.0,
                    "unit": "bucket",
                    "price": 1000.0,
                    "amount": 5000.0
                }
            ],
            "subtotal": 5000.0,
            "gst": 0.0,
            "total": 5000.0,
            "category": "UserA-Gold-Paint"
        }
        res = await client.post("/save", json=bill_a_payload, headers=headers_a)
        assert res.status_code == 201
        bill_a = res.json()
        bill_a_id = bill_a["id"]
        print(f" -> User A saved bill ID: {bill_a_id}")

        # User B saves a bill under default "Paint" category
        bill_b_payload = {
            "dealer_name": "Dealer Silver",
            "invoice_no": "INV-SILVER-002",
            "date": "2026-06-14",
            "items": [
                {
                    "product": "UserB Standard Paint",
                    "quantity": 10.0,
                    "unit": "bucket",
                    "price": 300.0,
                    "amount": 3000.0
                }
            ],
            "subtotal": 3000.0,
            "gst": 0.0,
            "total": 3000.0,
            "category": "Paint"
        }
        res = await client.post("/save", json=bill_b_payload, headers=headers_b)
        assert res.status_code == 201
        bill_b = res.json()
        bill_b_id = bill_b["id"]
        print(f" -> User B saved bill ID: {bill_b_id}")

        # User B tries to fetch User A's bill directly by ID -> verify 404
        res = await client.get(f"/bill/{bill_a_id}", headers=headers_b)
        assert res.status_code == 404, f"Expected 404, got {res.status_code}. User B could view User A's bill!"
        print(" -> Properly isolated single bill retrieval (User B got 404 on User A's bill ID)")

        # User B gets all bills -> verify they only see their own bill
        res = await client.get("/bills", headers=headers_b)
        assert res.status_code == 200
        bills_b = res.json()
        inv_numbers = [b["invoice_no"] for b in bills_b]
        print(f" -> User B's bills: {inv_numbers}")
        assert "INV-SILVER-002" in inv_numbers
        assert "INV-GOLD-001" not in inv_numbers, "CRITICAL ERROR: User B can see User A's bills in the list view!"
        print(" -> Properly isolated bills list view")

        # 4. ANALYTICS ENGINE ISOLATION
        print("\n[7] Testing Analytics Engine Isolation (JWT Protected)...")
        
        # User A dashboard
        res = await client.get("/analytics/dashboard", headers=headers_a)
        assert res.status_code == 200
        dash_a = res.json()
        print(f" -> User A Dashboard Spend: Rs.{dash_a['total_purchase_amount']} (Expected: Rs.5000.0)")
        assert dash_a["total_purchase_amount"] == 5000.0, f"Expected 5000.0, got {dash_a['total_purchase_amount']}"
        assert dash_a["total_bills"] == 1
        
        # User B dashboard
        res = await client.get("/analytics/dashboard", headers=headers_b)
        assert res.status_code == 200
        dash_b = res.json()
        print(f" -> User B Dashboard Spend: Rs.{dash_b['total_purchase_amount']} (Expected: Rs.3000.0)")
        assert dash_b["total_purchase_amount"] == 3000.0, f"Expected 3000.0, got {dash_b['total_purchase_amount']}"
        assert dash_b["total_bills"] == 1
        print(" -> Dashboard KPIs successfully isolated.")

        # Price Trends Isolation: User B tries to query User A's exclusive product
        res = await client.get("/analytics/price-trends", params={"product_name": "UserA Exclusive Paint"}, headers=headers_b)
        assert res.status_code == 200
        trend_b = res.json()
        print(f" -> User B Price Trend for User A's product month count: {len(trend_b['month_wise_trend'])}")
        assert len(trend_b["month_wise_trend"]) == 0, "CRITICAL ERROR: User B can access User A's product price trends!"

        # Dealer Profiles Isolation: User B tries to get Dealer Gold (owned by A)
        res = await client.get("/analytics/dealers/Dealer Gold", headers=headers_b)
        assert res.status_code == 200
        dealer_prof_b = res.json()
        print(f" -> User B Dealer Gold total purchase: Rs.{dealer_prof_b['total_purchase_amount']}")
        assert dealer_prof_b["total_purchase_amount"] == 0.0, "CRITICAL ERROR: User B leaked User A's dealer spending stats!"

        # 5. SETTINGS CRUD ISOLATION
        print("\n[8] Testing Settings CRUD Isolation...")
        # User A updates profile settings
        res = await client.put("/settings/profile", json={
            "display_name": "User A Updated",
            "email": "usera@example.com",
            "locale": "English (India)",
            "time_format": "24-hour"
        }, headers=headers_a)
        assert res.status_code == 200
        
        # User B fetches profile settings -> verify they are empty / default and do not leak A's profile
        res = await client.get("/settings/profile", headers=headers_b)
        assert res.status_code == 200
        settings_b = res.json()
        print(f" -> User B's profile setting object: {settings_b}")
        assert settings_b.get("display_name") != "User A Updated", "CRITICAL ERROR: User B's settings profile leaked User A's settings!"

        # Cleanup test data inside DB directly
        from app.database.database import db_manager
        db_manager.connect()
        db = db_manager.get_db()
        # Find and delete created documents
        user_a_doc = await db["users"].find_one({"email": "usera@example.com"})
        user_b_doc = await db["users"].find_one({"email": "userb@example.com"})
        
        if user_a_doc:
            user_a_id_str = str(user_a_doc["_id"])
            await db["bills"].delete_many({"user_id": user_a_id_str})
            await db["categories"].delete_many({"user_id": user_a_id_str})
            await db["products"].delete_many({"user_id": user_a_id_str})
            await db["dealers"].delete_many({"user_id": user_a_id_str})
            await db["settings"].delete_many({"user_id": user_a_id_str})
            await db["users"].delete_one({"_id": user_a_doc["_id"]})
            
        if user_b_doc:
            user_b_id_str = str(user_b_doc["_id"])
            await db["bills"].delete_many({"user_id": user_b_id_str})
            await db["categories"].delete_many({"user_id": user_b_id_str})
            await db["products"].delete_many({"user_id": user_b_id_str})
            await db["dealers"].delete_many({"user_id": user_b_id_str})
            await db["settings"].delete_many({"user_id": user_b_id_str})
            await db["users"].delete_one({"_id": user_b_doc["_id"]})
            
        db_manager.disconnect()
        print("\n============================================================")
        print("=== ALL MULTI-TENANT ISOLATION TESTS PASSED SUCCESSFULLY ===")
        print("============================================================\n")

if __name__ == "__main__":
    asyncio.run(run_tests())
