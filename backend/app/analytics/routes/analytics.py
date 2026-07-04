import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Optional
from app.analytics.schemas.responses import (
    DashboardResponse,
    DealerProfileResponse,
    DealerComparisonResponse,
    ProductAnalyticsResponse,
    ProductStatsItem,
    SameProductComparisonResponse,
    ProductPriceTrendResponse,
    DealerPriceHistoryResponse,
    PurchaseTrendResponse,
    CategoryAnalyticsResponse,
    SavingsResponse,
    ProductInsightsResponse,
    ForecastResponse,
    AIContextResponse,
    ProductDetailStatsItem,
    ChatRequest,
    ChatResponse
)

from app.analytics.services.dashboard_service import dashboard_service
from app.analytics.services.dealer_service import dealer_service
from app.analytics.services.product_service import product_service
from app.analytics.services.trend_service import trend_service
from app.analytics.services.savings_service import savings_service
from app.analytics.services.forecast_service import forecast_service
from app.analytics.services.ai_context_service import ai_context_service
from app.services.llm_chat_service import llm_chat_service

from app.analytics.repositories.analytics_repository import analytics_repository
from app.utils.auth import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics Engine"])

@router.get("/dashboard", response_model=DashboardResponse, status_code=status.HTTP_200_OK)
async def get_dashboard(user_id: str = Depends(get_current_user_id)):
    """Returns overall dashboard metrics and chronological purchase summaries."""
    try:
        return await dashboard_service.get_dashboard_data(user_id)
    except Exception as e:
        logger.error(f"Error fetching dashboard analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch dashboard data: {str(e)}"
        )

@router.get("/dealers", response_model=List[DealerProfileResponse], status_code=status.HTTP_200_OK)
async def get_all_dealers_profiles(user_id: str = Depends(get_current_user_id)):
    """Returns analytics profiles for all active dealers."""
    try:
        # Fetch all unique dealer profiles scoped by user_id
        cursor = analytics_repository._get_bills_col().distinct("dealer_name", {"user_id": user_id})
        dealer_names = await cursor
        
        profiles = []
        for name in dealer_names:
            if name:
                prof = await dealer_service.get_dealer_profile(name, user_id)
                profiles.append(prof)
        return profiles
    except Exception as e:
        logger.error(f"Error fetching dealers profiles list: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch dealers list: {str(e)}"
        )

@router.get("/dealers/compare", response_model=DealerComparisonResponse, status_code=status.HTTP_200_OK)
async def compare_dealers(
    dealer_a: str = Query(..., description="First dealer name to compare"),
    dealer_b: str = Query(..., description="Second dealer name to compare"),
    user_id: str = Depends(get_current_user_id)
):
    """Compares side-by-side transaction metrics and calculates savings opportunities between two dealers."""
    try:
        return await dealer_service.compare_dealers(dealer_a, dealer_b, user_id)
    except Exception as e:
        logger.error(f"Error comparing dealers '{dealer_a}' and '{dealer_b}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Dealers comparison failed: {str(e)}"
        )

@router.get("/dealers/{dealer_name}", response_model=DealerProfileResponse, status_code=status.HTTP_200_OK)
async def get_dealer_profile(dealer_name: str, user_id: str = Depends(get_current_user_id)):
    """Returns detailed analytics profile for a specific dealer."""
    try:
        return await dealer_service.get_dealer_profile(dealer_name, user_id)
    except Exception as e:
        logger.error(f"Error fetching dealer profile for '{dealer_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch dealer profile: {str(e)}"
        )

@router.get("/products", response_model=ProductAnalyticsResponse, status_code=status.HTTP_200_OK)
async def get_product_rankings(user_id: str = Depends(get_current_user_id)):
    """Returns lists of top most purchased, highest spending, and least purchased products."""
    try:
        return await product_service.get_product_rankings(user_id)
    except Exception as e:
        logger.error(f"Error fetching product rankings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch product rankings: {str(e)}"
        )

@router.get("/products/details", response_model=List[ProductDetailStatsItem], status_code=status.HTTP_200_OK)
async def get_detailed_products(user_id: str = Depends(get_current_user_id)):
    """Returns detailed purchase stats for all products, including category, average price, total quantity, supplier count, and price trend."""
    try:
        return await product_service.get_detailed_products(user_id)
    except Exception as e:
        logger.error(f"Error fetching detailed products: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch detailed products: {str(e)}"
        )


@router.get("/products/compare", response_model=SameProductComparisonResponse, status_code=status.HTTP_200_OK)
async def compare_product_dealers(
    product_name: str = Query(..., description="Name of the product to compare across suppliers"),
    user_id: str = Depends(get_current_user_id)
):
    """Analyzes prices for the same product across all supplying dealers to find the cheapest option."""
    try:
        return await product_service.compare_product_dealers(product_name, user_id)
    except Exception as e:
        logger.error(f"Error comparing product '{product_name}' across dealers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Product price comparison failed: {str(e)}"
        )

@router.get("/products/categories", response_model=CategoryAnalyticsResponse, status_code=status.HTTP_200_OK)
async def get_category_analytics(user_id: str = Depends(get_current_user_id)):
    """Returns spending, quantities, and MoM growth metrics grouped by product category."""
    try:
        return await product_service.get_category_analytics(user_id)
    except Exception as e:
        logger.error(f"Error fetching category analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Category analytics failed: {str(e)}"
        )

@router.get("/products/{product_name}", response_model=ProductStatsItem, status_code=status.HTTP_200_OK)
async def get_product_profile(product_name: str, user_id: str = Depends(get_current_user_id)):
    """Returns individual purchase stats, min/max price, last purchase, and frequency for a product."""
    try:
        prof = await product_service.get_single_product_stats(product_name, user_id)
        if not prof:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product '{product_name}' has no purchase history."
            )
        return prof
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching product stats for '{product_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch product profile: {str(e)}"
        )

@router.get("/price-trends", response_model=ProductPriceTrendResponse, status_code=status.HTTP_200_OK)
async def get_price_trends(
    product_name: str = Query(..., description="Product name to check price history"),
    dealer_name: Optional[str] = Query(None, description="Optional dealer name to filter trend history"),
    user_id: str = Depends(get_current_user_id)
):
    """Generates monthly average price trends and moving averages for a product."""
    try:
        return await trend_service.get_product_price_trend(product_name, user_id, dealer_name)
    except Exception as e:
        logger.error(f"Error calculating price trends for '{product_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Price trends generation failed: {str(e)}"
        )

@router.get("/price-trends/dealers", response_model=DealerPriceHistoryResponse, status_code=status.HTTP_200_OK)
async def get_dealer_price_history_trends(
    product_name: str = Query(..., description="Product name to check price history per dealer"),
    user_id: str = Depends(get_current_user_id)
):
    """Generates price history trends of a product mapped per individual dealer."""
    try:
        return await trend_service.get_dealers_price_history(product_name, user_id)
    except Exception as e:
        logger.error(f"Error fetching dealer trends for '{product_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch dealer price histories: {str(e)}"
        )

@router.get("/purchase-trends", response_model=PurchaseTrendResponse, status_code=status.HTTP_200_OK)
async def get_purchase_trends(user_id: str = Depends(get_current_user_id)):
    """Generates chronological transaction trends grouped daily, weekly, monthly, quarterly, and yearly."""
    try:
        return await trend_service.get_purchase_trends(user_id)
    except Exception as e:
        logger.error(f"Error calculating purchase trends: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch purchase trends: {str(e)}"
        )

@router.get("/savings", response_model=SavingsResponse, status_code=status.HTTP_200_OK)
async def get_savings_opportunities(user_id: str = Depends(get_current_user_id)):
    """Identifies overpayment margins and total potential savings if shifting to the cheapest supplier."""
    try:
        return await savings_service.get_savings_opportunities(user_id)
    except Exception as e:
        logger.error(f"Error retrieving savings analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Savings opportunities calculation failed: {str(e)}"
        )

@router.get("/insights", response_model=ProductInsightsResponse, status_code=status.HTTP_200_OK)
async def get_product_insights(user_id: str = Depends(get_current_user_id)):
    """Extracts business insights such as frequently purchased together items, fast growing items, and price alerts."""
    try:
        return await savings_service.get_insights(user_id)
    except Exception as e:
        logger.error(f"Error generating product insights: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Insights extraction failed: {str(e)}"
        )

@router.get("/forecast", response_model=ForecastResponse, status_code=status.HTTP_200_OK)
async def get_forecast(user_id: str = Depends(get_current_user_id)):
    """Generates future spend, quantity, and price trend estimates for next month using the active forecaster."""
    try:
        return await forecast_service.get_projections(user_id)
    except Exception as e:
        logger.error(f"Error calculating forecasts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Forecast generation failed: {str(e)}"
        )

@router.get("/ai-context", response_model=AIContextResponse, status_code=status.HTTP_200_OK)
async def get_ai_context(
    query_type: str = Query(..., description="Type of query context to build (e.g. cheapest_dealer, monthly_spend, dealer_comparison, price_increase, negotiation_targets)"),
    product_name: Optional[str] = Query(None, description="Product name (required for cheapest_dealer context)"),
    dealer_a: Optional[str] = Query(None, description="First dealer name (required for dealer_comparison context)"),
    dealer_b: Optional[str] = Query(None, description="Second dealer name (required for dealer_comparison context)"),
    user_id: str = Depends(get_current_user_id)
):
    """Exposes structured raw JSON context payloads for a downstream AI chat assistant to consume."""
    try:
        params = {
            "product_name": product_name,
            "dealer_a": dealer_a,
            "dealer_b": dealer_b
        }
        return await ai_context_service.get_query_context(query_type, user_id, params)
    except Exception as e:
        logger.error(f"Error generating AI context for query '{query_type}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI context generation failed: {str(e)}"
        )

@router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat_assistant(payload: ChatRequest, user_id: str = Depends(get_current_user_id)):
    """Receives natural language queries, classifies them using AI, extracts database context, and synthesizes data-grounded answers."""
    try:
        chat_data = await llm_chat_service.get_chat_response(payload.message, user_id)
        return ChatResponse(
            response=chat_data["response"],
            query_type=chat_data["query_type"],
            extracted_parameters=chat_data["extracted_parameters"]
        )
    except Exception as e:
        logger.error(f"Error in chat assistant execution: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat assistant failed: {str(e)}"
        )

