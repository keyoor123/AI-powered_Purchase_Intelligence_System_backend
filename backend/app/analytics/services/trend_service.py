import logging
from typing import List, Dict, Any, Optional
from app.analytics.repositories.analytics_repository import analytics_repository
from app.analytics.schemas.responses import (
    ProductPriceTrendResponse,
    PriceTrendPoint,
    DealerPriceHistoryResponse,
    DealerPriceTrendPoint,
    PurchaseTrendResponse
)

logger = logging.getLogger(__name__)

class TrendService:
    async def get_product_price_trend(self, product_name: str, user_id: str, dealer_name: str = None) -> ProductPriceTrendResponse:
        """Calculates price trend percentage changes and moving averages for a product."""
        logger.info(f"Computing price trend for: {product_name} (Dealer: {dealer_name}) for user: {user_id}")
        
        # 1. Fetch monthly price trends from DB
        raw_trend = await analytics_repository.get_price_trend(product_name, user_id, dealer_name)
        
        if not raw_trend:
            return ProductPriceTrendResponse(
                product_name=product_name,
                month_wise_trend=[],
                percentage_increase=0.0,
                percentage_decrease=0.0,
                moving_average=0.0,
                overall_trend="STABLE"
            )

        # 2. Form PriceTrendPoint structures
        month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        trend_points = []
        
        for item in raw_trend:
            year = item["_id"].get("year")
            month = item["_id"].get("month")
            
            if not year or not month:
                continue
                
            label = f"{month_names[month]} {year}"
            
            trend_points.append(PriceTrendPoint(
                label=label,
                average_price=item["average_price"],
                min_price=item["min_price"],
                max_price=item["max_price"]
            ))


        if not trend_points:
            return ProductPriceTrendResponse(
                product_name=product_name,
                month_wise_trend=[],
                percentage_increase=0.0,
                percentage_decrease=0.0,
                moving_average=0.0,
                overall_trend="STABLE"
            )

        # 3. Calculate percentage increase/decrease
        first_price = trend_points[0].average_price
        last_price = trend_points[-1].average_price
        
        pct_increase = 0.0
        pct_decrease = 0.0
        
        if last_price > first_price:
            pct_increase = round(((last_price - first_price) / first_price) * 100, 2)
        elif first_price > last_price:
            pct_decrease = round(((first_price - last_price) / first_price) * 100, 2)

        # 4. Calculate overall moving average
        avg_prices = [p.average_price for p in trend_points]
        moving_avg = sum(avg_prices) / len(avg_prices)


        # Determine overall trend classification
        diff_pct = ((last_price - first_price) / first_price) * 100 if first_price > 0 else 0.0
        if diff_pct > 3.0:
            overall_trend = "RISING"
        elif diff_pct < -3.0:
            overall_trend = "FALLING"
        else:
            overall_trend = "STABLE"

        return ProductPriceTrendResponse(
            product_name=product_name,
            month_wise_trend=trend_points,
            percentage_increase=pct_increase,
            percentage_decrease=pct_decrease,
            moving_average=round(moving_avg, 2),
            overall_trend=overall_trend
        )

    async def get_dealers_price_history(self, product_name: str, user_id: str) -> DealerPriceHistoryResponse:
        """Fetches pricing history trends for a product mapped across all supplying dealers."""
        logger.info(f"Retrieving dealer price history trends for product: {product_name} for user: {user_id}")
        
        raw_history = await analytics_repository.get_all_dealers_price_trends(product_name, user_id)
        month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
        dealers_trends_list = []
        for row in raw_history:
            dealer_name = row["_id"]
            db_trend = row["trend"]
            
            # Sort chronologically
            db_trend = sorted(db_trend, key=lambda x: (x.get("year") or 0, x.get("month") or 0))
            
            trend_points = [
                PriceTrendPoint(
                    label=f"{month_names[item['month']]} {item['year']}",
                    average_price=item["average_price"],
                    min_price=item["min_price"],
                    max_price=item["max_price"]
                ) for item in db_trend if item.get("month") and item.get("year")
            ]
            
            dealers_trends_list.append(
                DealerPriceTrendPoint(
                    dealer_name=dealer_name,
                    trend=trend_points
                )
            )

        return DealerPriceHistoryResponse(
            product_name=product_name,
            dealers_trends=dealers_trends_list
        )

    async def get_purchase_trends(self, user_id: str) -> PurchaseTrendResponse:
        """Retrieves and maps spending trends grouped daily, weekly, monthly, quarterly, and yearly."""
        logger.info(f"Computing daily/weekly/monthly purchase trends for user: {user_id}")
        raw_trends = await analytics_repository.get_purchase_trends(user_id)
        return PurchaseTrendResponse(**raw_trends)

trend_service = TrendService()
