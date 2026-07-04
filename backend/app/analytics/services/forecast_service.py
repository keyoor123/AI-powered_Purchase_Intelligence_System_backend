import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from app.analytics.repositories.analytics_repository import analytics_repository
from app.analytics.schemas.responses import ForecastResponse, ForecastPoint

logger = logging.getLogger(__name__)

# --- Abstract Base Forecaster ---
class BaseForecaster(ABC):
    """Abstract interface for forecasting logic, allowing future ML extensions."""
    @abstractmethod
    def forecast_next_values(self, history: List[float], steps: int = 1) -> List[float]:
        """Projections for the next 'steps' intervals based on chronological history values."""
        pass


# --- Default Python Implementation ---
class ExponentialSmoothingForecaster(BaseForecaster):
    """
    Simple Exponential Smoothing (SES) forecaster.
    Formula: S_t = alpha * Y_t + (1 - alpha) * S_t-1
    """
    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha

    def forecast_next_values(self, history: List[float], steps: int = 1) -> List[float]:
        if not history:
            return [0.0] * steps
        if len(history) == 1:
            return [history[0]] * steps
            
        # Run SES algorithm to find level at current state
        s = history[0]
        for val in history[1:]:
            s = self.alpha * val + (1 - self.alpha) * s
            
        # For SES, the flat forecast for all future steps is the last smoothed level
        return [round(s, 2)] * steps


class ForecastService:
    def __init__(self, forecaster: BaseForecaster = None):
        # Allow injecting other forecasters (e.g. ARIMA, Prophet) later
        self.forecaster = forecaster or ExponentialSmoothingForecaster()

    async def get_projections(self, user_id: str) -> ForecastResponse:
        """Generates future projections for spending, product quantities, and prices."""
        logger.info(f"Generating forecasts for user: {user_id} using the active forecaster module...")
        
        # 1. Forecast Next Month overall spend
        overall_stats = await analytics_repository.get_overall_stats(user_id)
        monthly_summary = overall_stats.get("monthly_purchase_summary", [])
        # Sort monthly summary chronologically
        monthly_summary = sorted(monthly_summary, key=lambda x: x["label"])
        monthly_spend_history = [item["total_amount"] for item in monthly_summary]
        
        next_month_spend = self.forecaster.forecast_next_values(monthly_spend_history, steps=1)[0]

        # 2. Forecast Next Month Product Quantities
        all_products = await analytics_repository.get_all_products_stats(user_id)
        quantity_forecasts = []
        price_forecasts = {}
        
        for prod in all_products:
            prod_name = prod["_id"]
            
            # Fetch chronological quantities and prices for each product
            # For simplicity, we can fetch monthly product prices from trend
            price_trend = await analytics_repository.get_price_trend(prod_name, user_id)
            # Sort chronologically
            price_trend = sorted(price_trend, key=lambda x: (x["_id"]["year"], x["_id"]["month"]))
            
            price_history = [item["average_price"] for item in price_trend]
            
            # Simple assumption: forecast quantities matching price monthly distributions
            # E.g. fetch product volume history (or default to fraction of total overall product quantity)
            # In a real environment, we'd group quantity per month.
            # Let's write a mock history or simple forecast
            total_qty = prod["total_quantity_purchased"]
            # Estimate monthly quantity history: divide overall qty evenly over purchase events
            qty_history = [total_qty / len(prod["purchase_dates"])] * len(prod["purchase_dates"])
            
            next_month_qty = self.forecaster.forecast_next_values(qty_history, steps=1)[0]
            next_month_price = self.forecaster.forecast_next_values(price_history, steps=1)[0]
            
            # Only include top/relevant product quantities to save response payload size
            if total_qty > 0:
                quantity_forecasts.append(ForecastPoint(
                    label="Next Month",
                    forecast_value=next_month_qty
                ))
                
                # Setup price projections
                price_forecasts[prod_name] = [ForecastPoint(
                    label="Next Month",
                    forecast_value=next_month_price
                )]

        # Sort product quantities and keep top 10
        quantity_forecasts = sorted(quantity_forecasts, key=lambda x: x.forecast_value, reverse=True)[:10]

        return ForecastResponse(
            next_month_purchase_amount=next_month_spend,
            next_month_product_quantity=quantity_forecasts,
            future_price_trend=price_forecasts
        )

forecast_service = ForecastService()
