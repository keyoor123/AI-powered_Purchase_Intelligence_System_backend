import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime

# Add backend directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.database import db_manager
from app.analytics.services.dashboard_service import dashboard_service
from app.analytics.services.dealer_service import dealer_service
from app.analytics.services.product_service import product_service
from app.analytics.services.trend_service import trend_service
from app.analytics.services.savings_service import savings_service
from app.analytics.services.forecast_service import forecast_service
from app.analytics.services.ai_context_service import ai_context_service

async def populate_mock_data():
    print("Populating mock invoice data in MongoDB...")
    db_manager.connect()
    db = db_manager.get_db()
    
    # Clean previous test entries to avoid duplicates skewing metrics
    await db["bills"].delete_many({"invoice_no": {"$in": ["TEST-INV-01", "TEST-INV-02", "TEST-INV-03"]}})
    await db["dealers"].delete_many({"name": {"$in": ["Dealer A", "Dealer B", "Dealer C"]}})
    await db["products"].delete_many({"name": {"$in": ["Cement", "Asian Paint 20L"]}})
    
    # 1. Populate products
    await db["products"].insert_many([
        {"name": "Cement", "category": "Building Materials", "default_unit": "bag", "user_id": "test_user_id_123"},
        {"name": "Asian Paint 20L", "category": "Paint", "default_unit": "bucket", "user_id": "test_user_id_123"}
    ])
    
    # 2. Populate dealers
    await db["dealers"].insert_many([
        {"name": "Dealer A", "phone": "123456", "address": "Ind Avenue", "created_at": datetime.utcnow(), "user_id": "test_user_id_123"},
        {"name": "Dealer B", "phone": "654321", "address": "Industrial Zone", "created_at": datetime.utcnow(), "user_id": "test_user_id_123"},
        {"name": "Dealer C", "phone": "789101", "address": "Market Sq", "created_at": datetime.utcnow(), "user_id": "test_user_id_123"}
    ])
    
    # 3. Populate bills
    await db["bills"].insert_many([
        {
            "dealer_name": "Dealer A",
            "invoice_no": "TEST-INV-01",
            "date": "2026-05-10",
            "bill_image": "test1.png",
            "subtotal": 42400.0,
            "gst": 2800.0,
            "total": 45200.0,
            "status": "verified",
            "user_id": "test_user_id_123",
            "items": [
                {"product": "Cement", "quantity": 100.0, "unit": "bag", "price": 320.0, "amount": 32000.0},
                {"product": "Asian Paint 20L", "quantity": 2.0, "unit": "bucket", "price": 5200.0, "amount": 10400.0}
            ],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "dealer_name": "Dealer B",
            "invoice_no": "TEST-INV-02",
            "date": "2026-06-12",
            "bill_image": "test2.png",
            "subtotal": 40750.0,
            "gst": 2500.0,
            "total": 43250.0,
            "status": "verified",
            "user_id": "test_user_id_123",
            "items": [
                {"product": "Cement", "quantity": 50.0, "unit": "bag", "price": 310.0, "amount": 15500.0},
                {"product": "Asian Paint 20L", "quantity": 5.0, "unit": "bucket", "price": 5050.0, "amount": 25250.0}
            ],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "dealer_name": "Dealer C",
            "invoice_no": "TEST-INV-03",
            "date": "2026-06-13",
            "bill_image": "test3.png",
            "subtotal": 53000.0,
            "gst": 3000.0,
            "total": 56000.0,
            "status": "verified",
            "user_id": "test_user_id_123",
            "items": [
                {"product": "Asian Paint 20L", "quantity": 10.0, "unit": "bucket", "price": 5300.0, "amount": 53000.0}
            ],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
    ])
    print("Mock data populated successfully.")

async def run_integration_tests():
    print("=== Starting Analytics Engine Integration Tests ===")
    
    # Populate mock DB data
    await populate_mock_data()
    user_id = "test_user_id_123"
    
    print("\n--- 1. Testing Dashboard Service ---")
    try:
        dash = await dashboard_service.get_dashboard_data(user_id)
        print(f"[OK] Dashboard Stats: Total Spent: Rs.{dash.total_purchase_amount}, Total Bills: {dash.total_bills}")
        print(f"     Monthly Summaries: {dash.monthly_purchase_summary}")
    except Exception as e:
        print(f"[FAIL] Dashboard Service: {e}")
        return

    print("\n--- 2. Testing Dealer Profile Service ---")
    try:
        profile = await dealer_service.get_dealer_profile("Dealer A", user_id)
        print(f"[OK] Dealer A Profile: Spend: Rs.{profile.total_purchase_amount}, Last Purchase: {profile.last_purchase_date}")
        print(f"     Most Purchased Product: {profile.most_purchased_product}")
    except Exception as e:
        print(f"[FAIL] Dealer Profile Service: {e}")
        return

    print("\n--- 3. Testing Dealer Comparison Service ---")
    try:
        comp = await dealer_service.compare_dealers("Dealer A", "Dealer B", user_id)
        print(f"[OK] Comparison: Dealer A vs Dealer B")
        print(f"     A Avg Price: Rs.{comp.metrics_a.average_price}, B Avg Price: Rs.{comp.metrics_b.average_price}")
        print(f"     Price Difference: Rs.{comp.price_difference}, Savings Opportunity: Rs.{comp.savings_opportunity}")
    except Exception as e:
        print(f"[FAIL] Dealer Comparison Service: {e}")
        return

    print("\n--- 4. Testing Same Product Supplier Comparison ---")
    try:
        prod_comp = await product_service.compare_product_dealers("Asian Paint 20L", user_id)
        print(f"[OK] Asian Paint 20L Supplier Comparison:")
        print(f"     Cheapest: {prod_comp.cheapest_dealer} (Rs.{prod_comp.cheapest_price})")
        print(f"     Costliest: {prod_comp.costliest_dealer} (Rs.{prod_comp.costliest_price})")
        print(f"     Market Average: Rs.{prod_comp.average_market_price}")
        print(f"     Potential Savings Opportunity: Rs.{prod_comp.potential_savings}")
    except Exception as e:
        print(f"[FAIL] Same Product Supplier Comparison: {e}")
        return

    print("\n--- 5. Testing Product Category Analytics ---")
    try:
        cat_data = await product_service.get_category_analytics(user_id)
        print(f"[OK] Categories Stats:")
        for c in cat_data.categories:
            print(f"     Category '{c.category_name}': Spend: Rs.{c.total_spending}, MoM Growth: {c.growth_percentage}%")
        print(f"     Top Category by Spend: {cat_data.top_category_by_spending}")
    except Exception as e:
        print(f"[FAIL] Product Category Analytics: {e}")
        return

    print("\n--- 6. Testing Price Trends Analytics ---")
    try:
        trend = await trend_service.get_product_price_trend("Cement", user_id)
        print(f"[OK] Cement Price Trend:")
        print(f"     Trend Direction: {trend.overall_trend}, Moving Avg: Rs.{trend.moving_average}")
        print(f"     Percentage Increase: {trend.percentage_increase}%, Percentage Decrease: {trend.percentage_decrease}%")
    except Exception as e:
        print(f"[FAIL] Price Trends: {e}")
        return

    print("\n--- 7. Testing Savings Opportunities ---")
    try:
        savings = await savings_service.get_savings_opportunities(user_id)
        print(f"[OK] Savings Analysis: Total Potential Savings: Rs.{savings.total_potential_savings}")
        print(f"     Top Opportunity: {savings.opportunities[0].model_dump() if savings.opportunities else 'None'}")
    except Exception as e:
        print(f"[FAIL] Savings Opportunities: {e}")
        return

    print("\n--- 8. Testing Product Insights (Market Basket & Prices) ---")
    try:
        insights = await savings_service.get_insights(user_id)
        print(f"[OK] Insights:")
        print(f"     Frequently Purchased: {[x.product_name for x in insights.frequently_purchased]}")
        print(f"     Frequently Purchased Together: {insights.frequently_purchased_together}")
        print(f"     Rising Prices: {[x.product_name for x in insights.rising_prices]}")
    except Exception as e:
        print(f"[FAIL] Product Insights: {e}")
        return

    print("\n--- 9. Testing Forecasting Service ---")
    try:
        forecast = await forecast_service.get_projections(user_id)
        print(f"[OK] Projections: Next Month Spend Estimate: Rs.{forecast.next_month_purchase_amount}")
        print(f"     Next Month Product Quantities: {[x.model_dump() for x in forecast.next_month_product_quantity]}")
    except Exception as e:
        print(f"[FAIL] Forecasting: {e}")
        return

    print("\n--- 10. Testing AI Context Service ---")
    try:
        ctx = await ai_context_service.get_query_context("cheapest_dealer", user_id, {"product_name": "Asian Paint 20L"})
        print(f"[OK] AI Context 'cheapest_dealer' generated: {ctx.context_type}")
        summary = ctx.context_data.get('insights_summary', '').replace('₹', 'Rs.')
        print(f"     Content Summary: {summary}")
        
        ctx_neg = await ai_context_service.get_query_context("negotiation_targets", user_id)
        print(f"[OK] AI Context 'negotiation_targets' generated: {ctx_neg.context_type}")
        summary_neg = ctx_neg.context_data.get('insights_summary', '').replace('₹', 'Rs.')
        print(f"     Content Summary: {summary_neg}")
    except Exception as e:
        print(f"[FAIL] AI Context Service: {e}")
        return

    print("\n--- 11. Testing Detailed Product Statistics Service ---")
    try:
        detailed_prods = await product_service.get_detailed_products(user_id)
        print(f"[OK] Detailed Products list fetched: {len(detailed_prods)} products found.")
        for item in detailed_prods:
            print(f"     Product: {item.product_name} | Category: {item.category} | Avg Price: Rs.{item.average_price} | Qty: {item.total_quantity_purchased} | Suppliers: {item.number_of_dealers} | Trend: {item.overall_trend} ({item.trend_percentage}%)")
    except Exception as e:
        print(f"[FAIL] Detailed Product Statistics Service: {e}")
        return

    print("\n--- 12. Testing AI Chat Assistant Service ---")
    try:
        from app.services.llm_chat_service import llm_chat_service
        
        # Test 1: Related procurement query
        resp_rel = await llm_chat_service.get_chat_response("Who is the cheapest dealer for Cement?", user_id)
        print(f"[OK] Procurement Query Response:")
        print(f"     Response: {resp_rel['response']}")
        print(f"     Query Type: {resp_rel['query_type']} | Extracted Product: {resp_rel['extracted_parameters']['product_name']}")
        
        # Test 2: Unrelated query
        resp_unrel = await llm_chat_service.get_chat_response("write python code for add two number", user_id)
        print(f"[OK] Unrelated Query Response:")
        print(f"     Response: {resp_unrel['response']}")
        print(f"     Query Type: {resp_unrel['query_type']}")
    except Exception as e:
        print(f"[FAIL] AI Chat Assistant Service: {e}")
        return

    print("\n=== All Integration Tests Completed Successfully! ===")
    db_manager.disconnect()



if __name__ == "__main__":
    asyncio.run(run_integration_tests())
