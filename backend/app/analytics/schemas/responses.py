from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import date, datetime

# --- Common Helper Schemas ---
class SpendTrendItem(BaseModel):
    label: str = Field(..., description="E.g. '2026-06', '2026', '2026-W24', '2026-06-13'")
    total_amount: float
    bill_count: int

class ProductPriceItem(BaseModel):
    product: str
    price: float
    quantity: float
    amount: float
    date: str

# --- Dashboard Schemas ---
class DashboardResponse(BaseModel):
    total_purchase_amount: float
    total_bills: int
    total_products: int
    total_dealers: int
    average_bill_amount: float
    highest_bill_amount: float
    lowest_bill_amount: float
    monthly_purchase_summary: List[SpendTrendItem]
    yearly_purchase_summary: List[SpendTrendItem]

# --- Dealer Schemas ---
class DealerProfileResponse(BaseModel):
    dealer_name: str
    total_purchase_amount: float
    number_of_bills: int
    number_of_products_purchased: int
    monthly_purchase: List[SpendTrendItem]
    yearly_purchase: List[SpendTrendItem]
    average_bill_value: float
    most_purchased_product: Optional[str] = None
    last_purchase_date: Optional[str] = None

class DealerComparisonMetric(BaseModel):
    total_purchase: float
    average_price: float
    total_quantity: float

class DealerComparisonResponse(BaseModel):
    dealer_a: str
    dealer_b: str
    metrics_a: DealerComparisonMetric
    metrics_b: DealerComparisonMetric
    price_difference: float = Field(..., description="Average unit price difference for commonly purchased products")
    savings_opportunity: float = Field(..., description="Potential savings if buying from the cheaper dealer")

# --- Product Comparison Schemas ---
class ProductDealerPriceItem(BaseModel):
    dealer_name: str
    average_price: float
    min_price: float
    max_price: float
    last_purchase_date: Optional[str] = None

class SameProductComparisonResponse(BaseModel):
    product_name: str
    cheapest_dealer: Optional[str] = None
    cheapest_price: Optional[float] = None
    costliest_dealer: Optional[str] = None
    costliest_price: Optional[float] = None
    average_market_price: float
    price_difference: float = Field(..., description="Max price minus min price")
    potential_savings: float = Field(..., description="Potential savings calculated based on total quantity purchased")
    historical_prices: List[ProductDealerPriceItem]

# --- Product Analytics Schemas ---
class ProductStatsItem(BaseModel):
    product_name: str
    total_quantity_purchased: float
    total_amount_spent: float
    average_price: float
    min_price: float
    max_price: float
    number_of_dealers: int
    last_purchase_date: Optional[str] = None
    purchase_frequency: float = Field(..., description="Average days between purchases")

class ProductAnalyticsResponse(BaseModel):
    top_most_purchased: List[ProductStatsItem] = Field(..., description="Top 10 products by quantity")
    top_highest_spending: List[ProductStatsItem] = Field(..., description="Top 10 products by amount spent")
    least_purchased: List[ProductStatsItem] = Field(..., description="Least purchased products")

class ProductDetailStatsItem(BaseModel):
    product_name: str
    category: str
    average_price: float
    total_quantity_purchased: float
    number_of_dealers: int
    overall_trend: str  # "RISING", "FALLING", "STABLE"
    trend_percentage: float


# --- Trend Schemas ---
class PriceTrendPoint(BaseModel):
    label: str = Field(..., description="E.g. 'Jan', 'Feb', '2026-06'")
    average_price: float
    min_price: float
    max_price: float

class ProductPriceTrendResponse(BaseModel):
    product_name: str
    month_wise_trend: List[PriceTrendPoint]
    percentage_increase: float = Field(..., description="Increase from start of period to end")
    percentage_decrease: float = Field(..., description="Decrease from start of period to end")
    moving_average: float = Field(..., description="Overall average price across the trend period")
    overall_trend: str = Field(..., description="Description of the trend, e.g., 'RISING', 'STABLE', 'FALLING'")

class DealerPriceTrendPoint(BaseModel):
    dealer_name: str
    trend: List[PriceTrendPoint]

class DealerPriceHistoryResponse(BaseModel):
    product_name: str
    dealers_trends: List[DealerPriceTrendPoint]

class PurchaseTrendResponse(BaseModel):
    daily_purchase: List[SpendTrendItem]
    weekly_purchase: List[SpendTrendItem]
    monthly_purchase: List[SpendTrendItem]
    quarterly_purchase: List[SpendTrendItem]
    yearly_purchase: List[SpendTrendItem]

# --- Category Schemas ---
class CategoryStatsItem(BaseModel):
    category_name: str
    total_spending: float
    total_quantity: float
    growth_percentage: float = Field(..., description="Month-over-month spending growth")

class CategoryAnalyticsResponse(BaseModel):
    categories: List[CategoryStatsItem]
    top_category_by_spending: Optional[str] = None
    top_category_by_quantity: Optional[str] = None

# --- Savings Schemas ---
class SavingsOpportunityItem(BaseModel):
    product_name: str
    dealer_purchased: str
    actual_price: float
    cheapest_dealer: str
    cheapest_price: float
    quantity_purchased: float
    potential_savings: float

class SavingsResponse(BaseModel):
    total_potential_savings: float
    opportunities: List[SavingsOpportunityItem]

# --- Insights Schemas ---
class InsightItem(BaseModel):
    product_name: str
    value: Any
    description: str

class ProductInsightsResponse(BaseModel):
    frequently_purchased: List[InsightItem]
    frequently_purchased_together: List[Dict[str, Any]] = Field(..., description="Association rules / items commonly bought on the same invoice")
    fast_growing: List[InsightItem]
    slow_moving: List[InsightItem]
    rising_prices: List[InsightItem]
    falling_prices: List[InsightItem]

# --- Forecast Schemas ---
class ForecastPoint(BaseModel):
    label: str = Field(..., description="Future month/period label, e.g. '2026-07'")
    forecast_value: float

class ForecastResponse(BaseModel):
    next_month_purchase_amount: float
    next_month_product_quantity: List[ForecastPoint]
    future_price_trend: Dict[str, List[ForecastPoint]] = Field(..., description="Future price projections key-indexed by product name")

# --- AI Context Schemas ---
class AIContextResponse(BaseModel):
    context_type: str = Field(..., description="Type of query context generated")
    context_data: Dict[str, Any] = Field(..., description="Structured JSON payload prepared for AI agent ingestion")

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    query_type: str
    extracted_parameters: Dict[str, Any]

