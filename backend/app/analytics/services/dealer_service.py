import logging
from typing import List, Dict, Any
from app.analytics.repositories.analytics_repository import analytics_repository
from app.analytics.schemas.responses import (
    DealerProfileResponse,
    DealerComparisonResponse,
    DealerComparisonMetric
)

logger = logging.getLogger(__name__)

class DealerService:
    async def get_dealer_profile(self, dealer_name: str, user_id: str) -> DealerProfileResponse:
        """Calculates specific stats and purchase frequency for a dealer belonging to the user."""
        logger.info(f"Retrieving stats for dealer: {dealer_name} for user: {user_id}")
        raw_data = await analytics_repository.get_dealer_stats(dealer_name, user_id)
        return DealerProfileResponse(**raw_data)

    async def compare_dealers(self, dealer_a: str, dealer_b: str, user_id: str) -> DealerComparisonResponse:
        """Compares Dealer A and Dealer B side-by-side across common products for the user."""
        logger.info(f"Comparing dealer '{dealer_a}' with '{dealer_b}' for user: {user_id}")
        
        # 1. Fetch profile summaries
        stats_a = await analytics_repository.get_dealer_stats(dealer_a, user_id)
        stats_b = await analytics_repository.get_dealer_stats(dealer_b, user_id)
        
        # 2. Fetch common product details to calculate price diff and savings opportunity
        common_prods = await analytics_repository.get_dealer_common_products(dealer_a, dealer_b, user_id)
        
        total_qty_common_a = 0.0
        total_qty_common_b = 0.0
        weighted_price_sum_a = 0.0
        weighted_price_sum_b = 0.0
        
        savings_opp = 0.0
        price_diff_sum = 0.0
        common_count = len(common_prods)
        
        for item in common_prods:
            dealers_list = item["dealers_data"]
            # Extract data for both dealers
            data_a = next(d for d in dealers_list if d["dealer"] == dealer_a)
            data_b = next(d for d in dealers_list if d["dealer"] == dealer_b)
            
            # Weighted averages calculations
            total_qty_common_a += data_a["total_qty"]
            total_qty_common_b += data_b["total_qty"]
            weighted_price_sum_a += data_a["avg_price"] * data_a["total_qty"]
            weighted_price_sum_b += data_b["avg_price"] * data_b["total_qty"]
            
            price_diff_sum += abs(data_a["avg_price"] - data_b["avg_price"])
            
            # Savings opportunity: if we purchased from the cheaper dealer instead
            if data_a["avg_price"] > data_b["avg_price"]:
                # Dealer B is cheaper. If we bought Dealer A's volume from B:
                savings_opp += (data_a["avg_price"] - data_b["avg_price"]) * data_a["total_qty"]
            elif data_b["avg_price"] > data_a["avg_price"]:
                # Dealer A is cheaper. If we bought Dealer B's volume from A:
                savings_opp += (data_b["avg_price"] - data_a["avg_price"]) * data_b["total_qty"]

        # Calculate average prices for common items
        avg_price_common_a = (weighted_price_sum_a / total_qty_common_a) if total_qty_common_a > 0 else 0.0
        avg_price_common_b = (weighted_price_sum_b / total_qty_common_b) if total_qty_common_b > 0 else 0.0
        
        avg_price_diff = (price_diff_sum / common_count) if common_count > 0 else 0.0

        return DealerComparisonResponse(
            dealer_a=dealer_a,
            dealer_b=dealer_b,
            metrics_a=DealerComparisonMetric(
                total_purchase=stats_a["total_purchase_amount"],
                average_price=avg_price_common_a,
                total_quantity=total_qty_common_a
            ),
            metrics_b=DealerComparisonMetric(
                total_purchase=stats_b["total_purchase_amount"],
                average_price=avg_price_common_b,
                total_quantity=total_qty_common_b
            ),
            price_difference=avg_price_diff,
            savings_opportunity=round(savings_opp, 2)
        )

dealer_service = DealerService()
