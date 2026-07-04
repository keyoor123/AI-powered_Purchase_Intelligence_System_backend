import logging
from typing import Dict, Any, Optional
from app.analytics.services.dashboard_service import dashboard_service
from app.analytics.services.dealer_service import dealer_service
from app.analytics.services.product_service import product_service
from app.analytics.services.trend_service import trend_service
from app.analytics.services.savings_service import savings_service
from app.analytics.schemas.responses import AIContextResponse

logger = logging.getLogger(__name__)

class AIContextService:
    async def get_query_context(self, query_type: str, user_id: str, params: Optional[Dict[str, Any]] = None) -> AIContextResponse:
        """
        Gathers analytics data and formats it into structured context payloads for downstream AI consumption.
        Does NOT invoke any LLM API calls.
        """
        logger.info(f"Generating AI Context for query_type: '{query_type}' for user: {user_id}")
        params = params or {}
        context_data = {}

        if query_type == "cheapest_dealer":
            product_name = params.get("product_name")
            if not product_name:
                context_data = {"error": "Missing parameter 'product_name'"}
            else:
                comp = await product_service.compare_product_dealers(product_name, user_id)
                context_data = {
                    "product_name": product_name,
                    "cheapest_dealer": comp.cheapest_dealer,
                    "cheapest_price": comp.cheapest_price,
                    "costliest_dealer": comp.costliest_dealer,
                    "costliest_price": comp.costliest_price,
                    "average_market_price": comp.average_market_price,
                    "potential_savings_opportunity": comp.potential_savings,
                    "insights_summary": f"The cheapest supplier for '{product_name}' is {comp.cheapest_dealer} at ₹{comp.cheapest_price}. The costliest is {comp.costliest_dealer} at ₹{comp.costliest_price}."
                }

        elif query_type == "price_increase":
            rankings = await product_service.get_product_rankings(user_id)
            # Find the top spending products and check their trend
            highest_spend_prods = rankings.top_highest_spending
            
            top_increases = []
            for item in highest_spend_prods[:5]:
                trend = await trend_service.get_product_price_trend(item.product_name, user_id)
                if trend.percentage_increase > 0:
                    top_increases.append({
                        "product_name": item.product_name,
                        "percentage_increase": trend.percentage_increase,
                        "moving_average": trend.moving_average,
                        "overall_trend": trend.overall_trend
                    })
            
            # Sort by percentage increase descending
            top_increases = sorted(top_increases, key=lambda x: x["percentage_increase"], reverse=True)
            context_data = {
                "top_rising_price_products": top_increases,
                "insights_summary": f"Top products with rising prices identified: " + ", ".join([f"{x['product_name']} (+{x['percentage_increase']}% )" for x in top_increases]) if top_increases else "No significant price increases detected."
            }

        elif query_type == "monthly_spend":
            dash = await dashboard_service.get_dashboard_data(user_id)
            current_month = "N/A"
            current_spend = 0.0
            current_bills = 0
            
            if dash.monthly_purchase_summary:
                latest = dash.monthly_purchase_summary[-1]
                current_month = latest.label
                current_spend = latest.total_amount
                current_bills = latest.bill_count

            context_data = {
                "billing_month": current_month,
                "total_spending": current_spend,
                "bill_count": current_bills,
                "overall_dashboard_summary": {
                    "total_purchase_amount": dash.total_purchase_amount,
                    "total_bills": dash.total_bills,
                    "total_dealers": dash.total_dealers
                },
                "insights_summary": f"In the current billing month ({current_month}), the shop purchased goods worth ₹{current_spend} across {current_bills} bills."
            }

        elif query_type == "dealer_comparison":
            dealer_a = params.get("dealer_a")
            dealer_b = params.get("dealer_b")
            
            if not dealer_a or not dealer_b:
                context_data = {"error": "Missing parameters 'dealer_a' and 'dealer_b'"}
            else:
                comp = await dealer_service.compare_dealers(dealer_a, dealer_b, user_id)
                better_dealer = dealer_a if comp.metrics_a.average_price < comp.metrics_b.average_price else dealer_b
                context_data = {
                    "dealer_a": dealer_a,
                    "dealer_b": dealer_b,
                    "metrics_a": comp.metrics_a.model_dump(),
                    "metrics_b": comp.metrics_b.model_dump(),
                    "price_difference": comp.price_difference,
                    "savings_opportunity": comp.savings_opportunity,
                    "insights_summary": f"Comparing {dealer_a} vs {dealer_b}. On common items, {better_dealer} is generally cheaper. Shifting all common orders to them yields an estimated savings of ₹{comp.savings_opportunity}."
                }

        elif query_type == "negotiation_targets":
            savings = await savings_service.get_savings_opportunities(user_id)
            
            # Extract top 5 opportunities to target for negotiations
            targets = []
            for item in savings.opportunities[:5]:
                targets.append({
                    "product_name": item.product_name,
                    "current_supplier": item.dealer_purchased,
                    "current_price": item.actual_price,
                    "target_supplier": item.cheapest_dealer,
                    "target_price": item.cheapest_price,
                    "potential_savings": item.potential_savings
                })

            context_data = {
                "negotiation_candidates": targets,
                "total_potential_savings": savings.total_potential_savings,
                "insights_summary": f"Identified {len(targets)} high-potential product price discrepancies. Total potential savings through negotiations or supplier shifts: ₹{savings.total_potential_savings}."
            }
            
        else:
            context_data = {
                "error": f"Unknown query_type: '{query_type}'",
                "available_query_types": [
                    "cheapest_dealer",
                    "price_increase",
                    "monthly_spend",
                    "dealer_comparison",
                    "negotiation_targets"
                ]
            }

        return AIContextResponse(
            context_type=query_type,
            context_data=context_data
        )

ai_context_service = AIContextService()
