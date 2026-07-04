import logging
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from app.analytics.repositories.analytics_repository import analytics_repository
from app.analytics.services.trend_service import trend_service
from app.analytics.schemas.responses import (
    SavingsResponse,
    SavingsOpportunityItem,
    ProductInsightsResponse,
    InsightItem
)

logger = logging.getLogger(__name__)

class SavingsService:
    async def get_savings_opportunities(self, user_id: str) -> SavingsResponse:
        """Finds purchases bought at higher rates than the cheapest available dealer."""
        logger.info(f"Computing savings opportunities across historical transactions for user: {user_id}")
        
        # 1. Fetch all product stats
        all_prods = await analytics_repository.get_all_products_stats(user_id)
        
        # Map product name -> cheapest price and cheapest dealer name
        cheapest_map = {}
        for prod in all_prods:
            prod_name = prod["_id"]
            # Find cheapest price by querying dealer prices
            dealer_prices = await analytics_repository.get_product_dealer_prices(prod_name, user_id)
            if dealer_prices:
                cheapest_item = min(dealer_prices, key=lambda x: x["average_price"])
                cheapest_map[prod_name] = {
                    "price": cheapest_item["average_price"],
                    "dealer": cheapest_item["_id"]
                }

        # 2. Retrieve history of recent prices and check for overpayments
        raw_history = await analytics_repository.get_recent_prices_history(user_id)
        
        opportunities = []
        total_potential_savings = 0.0
        
        for tx in raw_history:
            prod_name = tx["product"]
            actual_price = tx["price"]
            dealer = tx["dealer"]
            qty = tx.get("quantity", 1.0)
            
            cheapest = cheapest_map.get(prod_name)
            if cheapest and actual_price > cheapest["price"] and dealer != cheapest["dealer"]:
                diff = actual_price - cheapest["price"]
                savings = diff * qty
                
                opportunities.append(
                    SavingsOpportunityItem(
                        product_name=prod_name,
                        dealer_purchased=dealer,
                        actual_price=actual_price,
                        cheapest_dealer=cheapest["dealer"],
                        cheapest_price=cheapest["price"],
                        quantity_purchased=qty,
                        potential_savings=round(savings, 2)
                    )
                )
                total_potential_savings += savings

        # Sort opportunities by potential savings descending
        opportunities = sorted(opportunities, key=lambda x: x.potential_savings, reverse=True)

        return SavingsResponse(
            total_potential_savings=round(total_potential_savings, 2),
            opportunities=opportunities
        )

    async def get_insights(self, user_id: str) -> ProductInsightsResponse:
        """Extracts frequently purchased items, co-occurrence associations, growth rates, and rising/falling prices."""
        logger.info(f"Aggregates complex product insights for user: {user_id}")
        
        all_prods = await analytics_repository.get_all_products_stats(user_id)
        
        # 1. Frequently Purchased (by purchase events count)
        frequent = []
        for p in all_prods:
            dates_count = len(p.get("purchase_dates", []))
            frequent.append(InsightItem(
                product_name=p["_id"],
                value=dates_count,
                description=f"Purchased {dates_count} times across invoices"
            ))
        frequent = sorted(frequent, key=lambda x: x.value, reverse=True)[:5]

        # 2. Frequently Purchased Together (co-occurrence in same bill)
        bills_items = await analytics_repository.get_all_bill_items(user_id)
        pair_counts = defaultdict(int)
        for bill in bills_items:
            prods = sorted(list(bill.get("products", [])))
            for i in range(len(prods)):
                for j in range(i + 1, len(prods)):
                    pair_counts[(prods[i], prods[j])] += 1
                    
        sorted_pairs = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        purchased_together = [
            {"product_a": pair[0], "product_b": pair[1], "co_occurrences": count}
            for pair, count in sorted_pairs
        ]

        # 3. Growth trends, rising and falling prices
        rising = []
        falling = []
        fast_growing = []
        slow_moving = []
        
        for p in all_prods:
            prod_name = p["_id"]
            
            # Retrieve trend
            trend_data = await trend_service.get_product_price_trend(prod_name, user_id)
            if trend_data.overall_trend == "RISING":
                rising.append(InsightItem(
                    product_name=prod_name,
                    value=trend_data.percentage_increase,
                    description=f"Price increased by {trend_data.percentage_increase}% over trend period"
                ))
            elif trend_data.overall_trend == "FALLING":
                falling.append(InsightItem(
                    product_name=prod_name,
                    value=trend_data.percentage_decrease,
                    description=f"Price decreased by {trend_data.percentage_decrease}% over trend period"
                ))
                
            # Growth (MoM qty growth)
            total_qty = p["total_quantity_purchased"]
            dates_count = len(p.get("purchase_dates", []))
            avg_qty = total_qty / dates_count if dates_count > 0 else 0
            
            if avg_qty > 10:
                fast_growing.append(InsightItem(
                    product_name=prod_name,
                    value=total_qty,
                    description=f"High-volume fast moving product with {total_qty} units total"
                ))
            else:
                slow_moving.append(InsightItem(
                    product_name=prod_name,
                    value=total_qty,
                    description=f"Low-volume slow moving product with {total_qty} units total"
                ))

        # Sort lists
        rising = sorted(rising, key=lambda x: x.value, reverse=True)[:5]
        falling = sorted(falling, key=lambda x: x.value, reverse=True)[:5]
        fast_growing = sorted(fast_growing, key=lambda x: x.value, reverse=True)[:5]
        slow_moving = sorted(slow_moving, key=lambda x: x.value)[:5]

        return ProductInsightsResponse(
            frequently_purchased=frequent,
            frequently_purchased_together=purchased_together,
            fast_growing=fast_growing,
            slow_moving=slow_moving,
            rising_prices=rising,
            falling_prices=falling
        )

savings_service = SavingsService()
