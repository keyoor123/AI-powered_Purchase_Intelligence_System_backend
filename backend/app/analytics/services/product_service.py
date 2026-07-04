import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.analytics.repositories.analytics_repository import analytics_repository
from app.analytics.schemas.responses import (
    ProductStatsItem,
    ProductAnalyticsResponse,
    SameProductComparisonResponse,
    ProductDealerPriceItem,
    CategoryAnalyticsResponse,
    CategoryStatsItem,
    ProductDetailStatsItem
)


logger = logging.getLogger(__name__)

class ProductService:
    def _parse_date(self, d: str) -> Optional[datetime]:
        """Parses a date string trying multiple common formats."""
        if not d:
            return None
        
        d_clean = d.strip()
        formats = [
            "%Y-%m-%d",  # 2026-04-17
            "%d-%b-%y",  # 17-Apr-26
            "%d-%b-%Y",  # 17-Apr-2026
            "%d/%m/%Y",  # 17/04/2026
            "%Y/%m/%d",  # 2026/04/17
            "%d-%m-%Y",  # 17-04-2026
            "%b %d, %Y", # Apr 17, 2026
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(d_clean, fmt)
            except ValueError:
                continue
                
        for fmt in formats:
            try:
                return datetime.strptime(d_clean[:10], fmt)
            except ValueError:
                try:
                    return datetime.strptime(d_clean[:9], fmt)
                except ValueError:
                    continue
                    
        logger.warning(f"Failed to parse date string: '{d}'")
        return None

    def _calculate_frequency(self, date_strings: List[str]) -> float:
        """Calculates average days between successive purchases."""
        if not date_strings or len(date_strings) <= 1:
            return 0.0
            
        # Parse and sort dates
        parsed_dates = []
        for d in date_strings:
            if d:
                dt = self._parse_date(d)
                if dt:
                    parsed_dates.append(dt)
                    
        if len(parsed_dates) <= 1:
            return 0.0
            
        dates = sorted(parsed_dates)
        deltas = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
        return round(sum(deltas) / len(deltas), 2)


    def _map_to_stats_item(self, row: Dict[str, Any]) -> ProductStatsItem:
        """Helper to format database result into ProductStatsItem Pydantic schema."""
        dates = row.get("purchase_dates", [])
        frequency = self._calculate_frequency(dates)
        
        return ProductStatsItem(
            product_name=row["_id"],
            total_quantity_purchased=row["total_quantity_purchased"],
            total_amount_spent=row["total_amount_spent"],
            average_price=row["average_price"],
            min_price=row["min_price"],
            max_price=row["max_price"],
            number_of_dealers=len(row["dealers"]),
            last_purchase_date=row["last_purchase_date"],
            purchase_frequency=frequency
        )

    async def get_single_product_stats(self, product_name: str, user_id: str) -> Optional[ProductStatsItem]:
        """Calculates profile stats for a specific product."""
        logger.info(f"Fetching stats for product: {product_name} for user: {user_id}")
        raw = await analytics_repository.get_product_stats(product_name, user_id)
        if not raw:
            return None
        return self._map_to_stats_item(raw)

    async def get_product_rankings(self, user_id: str) -> ProductAnalyticsResponse:
        """Aggregates all products and splits into top-10 list views for the user."""
        logger.info(f"Computing product ranking lists for user: {user_id}")
        all_prods = await analytics_repository.get_all_products_stats(user_id)
        
        # Map database rows to Pydantic stats items
        stats_items = [self._map_to_stats_item(row) for row in all_prods]
        
        # Sort for rankings
        top_purchased = sorted(stats_items, key=lambda x: x.total_quantity_purchased, reverse=True)[:10]
        top_spending = sorted(stats_items, key=lambda x: x.total_amount_spent, reverse=True)[:10]
        least_purchased = sorted(stats_items, key=lambda x: x.total_quantity_purchased)[:10]
        
        return ProductAnalyticsResponse(
            top_most_purchased=top_purchased,
            top_highest_spending=top_spending,
            least_purchased=least_purchased
        )

    async def compare_product_dealers(self, product_name: str, user_id: str) -> SameProductComparisonResponse:
        """Compares price differences for the same product across all dealers for the user."""
        logger.info(f"Comparing dealer prices for product: {product_name} for user: {user_id}")
        
        # Get pricing details for this product across all dealers
        dealer_prices = await analytics_repository.get_product_dealer_prices(product_name, user_id)
        
        # Get overall product stats to fetch total quantity purchased
        overall_stats = await analytics_repository.get_product_stats(product_name, user_id)
        total_qty = overall_stats["total_quantity_purchased"] if overall_stats else 0.0
        
        if not dealer_prices:
            return SameProductComparisonResponse(
                product_name=product_name,
                cheapest_dealer=None,
                cheapest_price=None,
                costliest_dealer=None,
                costliest_price=None,
                average_market_price=0.0,
                price_difference=0.0,
                potential_savings=0.0,
                historical_prices=[]
            )

        # Cheapest and costliest prices
        cheapest_row = min(dealer_prices, key=lambda x: x["average_price"])
        costliest_row = max(dealer_prices, key=lambda x: x["average_price"])
        
        avg_prices_sum = sum(item["average_price"] for item in dealer_prices)
        avg_market_price = avg_prices_sum / len(dealer_prices)
        
        price_diff = costliest_row["average_price"] - cheapest_row["average_price"]
        
        # Potential savings = (avg_price - cheapest_price) * total_qty
        # E.g. what could we have saved if we bought all of our volume at the cheapest price instead
        # of the actual price we paid?
        actual_total_spend = overall_stats["total_amount_spent"] if overall_stats else 0.0
        cheapest_potential_spend = total_qty * cheapest_row["average_price"]
        potential_savings = max(0.0, actual_total_spend - cheapest_potential_spend)
        
        historical_prices = [
            ProductDealerPriceItem(
                dealer_name=item["_id"],
                average_price=item["average_price"],
                min_price=item["min_price"],
                max_price=item["max_price"],
                last_purchase_date=item["last_purchase_date"]
            ) for item in dealer_prices
        ]

        return SameProductComparisonResponse(
            product_name=product_name,
            cheapest_dealer=cheapest_row["_id"],
            cheapest_price=cheapest_row["average_price"],
            costliest_dealer=costliest_row["_id"],
            costliest_price=costliest_row["average_price"],
            average_market_price=avg_market_price,
            price_difference=price_diff,
            potential_savings=round(potential_savings, 2),
            historical_prices=historical_prices
        )

    async def get_category_analytics(self, user_id: str) -> CategoryAnalyticsResponse:
        """Aggregates category spending, quantities, and top performing categories for the user."""
        logger.info(f"Retrieving category statistics for user: {user_id}")
        raw_cats = await analytics_repository.get_category_spending(user_id)
        
        categories_list = []
        for row in raw_cats:
            cat_name = row["_id"]
            total_spending = row["total_spending"]
            total_quantity = row["total_quantity"]
            
            # Growth calculation: compare current month spending vs previous month spending
            history = row.get("monthly_history", [])
            # Sort history chronologically
            history = sorted(history, key=lambda x: (x.get("year") or 0, x.get("month") or 0))
            
            growth_pct = 0.0
            if len(history) >= 2:
                prev_spend = history[-2]["spending"]
                curr_spend = history[-1]["spending"]
                if prev_spend > 0:
                    growth_pct = round(((curr_spend - prev_spend) / prev_spend) * 100, 2)
            
            categories_list.append(CategoryStatsItem(
                category_name=cat_name,
                total_spending=total_spending,
                total_quantity=total_quantity,
                growth_percentage=growth_pct
            ))

        top_by_spend = None
        top_by_qty = None
        if categories_list:
            top_by_spend = max(categories_list, key=lambda x: x.total_spending).category_name
            top_by_qty = max(categories_list, key=lambda x: x.total_quantity).category_name

        return CategoryAnalyticsResponse(
            categories=categories_list,
            top_category_by_spending=top_by_spend,
            top_category_by_quantity=top_by_qty
        )

    async def get_detailed_products(self, user_id: str) -> List[ProductDetailStatsItem]:
        """Returns detailed stats for all products including category, average price, total quantity, supplier count, and price trend."""
        logger.info(f"Computing detailed product stats list for user: {user_id}")
        
        # 1. Fetch raw product statistics from aggregation repository
        all_prods = await analytics_repository.get_all_products_stats(user_id)
        
        # 2. Fetch all product category mappings for this user from products collection
        products_col = analytics_repository._get_products_col()
        db_products = await products_col.find({"user_id": user_id}).to_list(length=2000)
        category_map = {p["name"]: p.get("category") or "Uncategorized" for p in db_products}
        
        # 3. For each product, calculate trend statistics and construct response items
        from app.analytics.services.trend_service import trend_service
        
        detailed_items = []
        for p in all_prods:
            prod_name = p["_id"]
            
            # Fetch category
            category = category_map.get(prod_name, "Uncategorized")
            
            # Calculate price trend
            trend_data = await trend_service.get_product_price_trend(prod_name, user_id)
            
            # Decide the trend percentage depending on RISING/FALLING direction
            if trend_data.overall_trend == "RISING":
                trend_pct = trend_data.percentage_increase
            elif trend_data.overall_trend == "FALLING":
                trend_pct = trend_data.percentage_decrease
            else:
                trend_pct = 0.0
                
            detailed_items.append(ProductDetailStatsItem(
                product_name=prod_name,
                category=category,
                average_price=p["average_price"],
                total_quantity_purchased=p["total_quantity_purchased"],
                number_of_dealers=len(p["dealers"]),
                overall_trend=trend_data.overall_trend,
                trend_percentage=trend_pct
            ))
            
        return detailed_items

product_service = ProductService()

