import json
import logging
from typing import Dict, Any, Optional
from openai import AsyncOpenAI
from app.utils.config import settings
from app.analytics.repositories.analytics_repository import analytics_repository
from app.analytics.services.product_service import product_service
from app.analytics.services.dealer_service import dealer_service
from app.analytics.services.savings_service import savings_service
from app.analytics.services.trend_service import trend_service
from app.analytics.services.dashboard_service import dashboard_service

logger = logging.getLogger(__name__)

class OpenRouterChatService:
    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.model = settings.OPENROUTER_MODEL
        self.base_url = settings.OPENROUTER_BASE_URL
        
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    async def get_chat_response(self, user_query: str, user_id: str) -> Dict[str, Any]:
        """
        Runs the full AI chat assistant pipeline:
        1. Classify intent and extract variables using LLM.
        2. Resolve semantic variables to database products.
        3. Gather database procurement context using existing services.
        4. Synthesize final natural language answer using LLM.
        """
        logger.info(f"AI Assistant routing user query: '{user_query}'")
        
        if not self.api_key:
            return {
                "response": "AI Assistant is currently offline because OPENROUTER_API_KEY is not configured.",
                "query_type": "unrelated",
                "extracted_parameters": {}
            }

        # --- Phase 1: Intent & Entity Classification ---
        system_prompt = (
            "You are the AI Procurement Router. Your job is to classify the user's message into one of the following query types:\n"
            "1. 'cheapest_dealer': If they ask for the cheapest rate, cost comparison, or supplier for a specific product.\n"
            "2. 'negotiation_targets': If they ask about negotiation options, overpayments, or discount opportunities.\n"
            "3. 'price_increase': If they ask about rising prices, price increases, inflation, or alerts.\n"
            "4. 'monthly_spend': If they ask about monthly budget, spend summaries, or overall cost patterns.\n"
            "5. 'dealer_comparison': If they ask to compare two dealers side-by-side.\n"
            "6. 'unrelated': If they ask about general topics, coding, greetings, weather, or anything not related to procurement, products, or suppliers.\n\n"
            "Also extract any entities mentioned:\n"
            "- 'product_name': The semantic name of the product mentioned (e.g. 'cement', 'distemper', 'fasteners').\n"
            "- 'dealer_a': First dealer name (if comparing).\n"
            "- 'dealer_b': Second dealer name (if comparing).\n\n"
            "Return ONLY a raw JSON block in this format (no markdown, no extra text):\n"
            "{\n"
            "  \"query_type\": \"cheapest_dealer\" | \"negotiation_targets\" | \"price_increase\" | \"monthly_spend\" | \"dealer_comparison\" | \"unrelated\",\n"
            "  \"product_name\": string | null,\n"
            "  \"dealer_a\": string | null,\n"
            "  \"dealer_b\": string | null\n"
            "}"
        )

        try:
            classification_resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                extra_headers={
                    "HTTP-Referer": "https://github.com/vudovn/ag-kit", 
                    "X-Title": "AI-powered Purchase Intelligence System"
                },
                temperature=0.0,
                max_tokens=200
            )
            
            if not classification_resp or not getattr(classification_resp, "choices", None) or not classification_resp.choices:
                raise RuntimeError("Empty or invalid response from classification API")

            import re
            raw_text = classification_resp.choices[0].message.content.strip()
            # Clean markdown and extract JSON block
            pattern = r"(\{.*?\})"
            match = re.search(pattern, raw_text, re.DOTALL)
            if match:
                raw_text = match.group(1)
            else:
                if raw_text.startswith("```"):
                    raw_text = raw_text.lstrip("`").lstrip("json").rstrip("`").strip()
                
            classification_data = json.loads(raw_text)


        except Exception as e:
            logger.error(f"Failed to classify user query: {e}")
            classification_data = {
                "query_type": "unrelated",
                "product_name": None,
                "dealer_a": None,
                "dealer_b": None
            }

        query_type = classification_data.get("query_type", "unrelated")
        product_name = classification_data.get("product_name")
        dealer_a = classification_data.get("dealer_a")
        dealer_b = classification_data.get("dealer_b")

        # --- Phase 2: Product & Dealer Entity Matching ---
        # Fetch products from DB to align semantic names
        products_col = analytics_repository._get_products_col()
        db_products = await products_col.find({"user_id": user_id}).to_list(length=1000)
        
        matched_product = None
        if product_name:
            clean_name = product_name.strip().lower()
            for p in db_products:
                db_name = p["name"].strip()
                if clean_name in db_name.lower() or db_name.lower() in clean_name:
                    matched_product = db_name
                    break

        # Fetch dealer names to align
        dealers_col = analytics_repository._get_bills_col()
        db_dealers = await dealers_col.distinct("dealer_name", {"user_id": user_id})
        
        matched_dealer_a = None
        matched_dealer_b = None
        
        if dealer_a:
            clean_a = dealer_a.strip().lower()
            for d in db_dealers:
                if d and (clean_a in d.lower() or d.lower() in clean_a):
                    matched_dealer_a = d
                    break
        if dealer_b:
            clean_b = dealer_b.strip().lower()
            for d in db_dealers:
                if d and (clean_b in d.lower() or d.lower() in clean_b):
                    matched_dealer_b = d
                    break

        # --- Phase 3: Check Context/Missing State & Formulate Prompt ---
        is_missing_product = (query_type in ["cheapest_dealer", "price_increase"] and product_name and not matched_product)
        
        messages = []
        context_payload = {}

        if query_type == "unrelated":
            system_prompt = (
                "You are the AI Procurement Assistant. Refuse the user's query politely. "
                "Explain in one or two sentences that you cannot assist with this specific topic (mention specifically what they asked) "
                "and remind them that you are here to help them analyze their shop's purchasing bills, products, and supplier options. "
                "Do NOT write any code, do NOT answer general knowledge questions, and do NOT perform the requested task."
            )
            user_msg = f"Generate a polite rejection message specifically refusing the user's request: '{user_query}'."
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ]
        elif is_missing_product:
            system_prompt = (
                "You are the AI Procurement Assistant. Refuse the user's query politely. "
                "Explain that the product they asked about does not exist in their purchase history and suggest that they can upload new invoices using the dashboard."
            )
            user_msg = f"Generate a polite message explaining that you checked their historical bills but could not find any records for: '{product_name}'."
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ]
        else:
            # --- Phase 4: Gather Mathematical Context ---
            try:
                # If product name is needed but none was matched (and not classified as unrelated), fallback to first product if available
                target_product = matched_product
                if not target_product and db_products and query_type in ["cheapest_dealer", "price_increase"]:
                    target_product = db_products[0]["name"]

                if query_type == "cheapest_dealer" and target_product:
                    stats = await product_service.compare_product_dealers(target_product, user_id)
                    context_payload = stats.model_dump()
                elif query_type == "negotiation_targets":
                    stats = await savings_service.get_savings_opportunities(user_id)
                    context_payload = stats.model_dump()
                elif query_type == "price_increase":
                    stats = await savings_service.get_insights(user_id)
                    context_payload = {
                        "rising_prices": [item.model_dump() for item in stats.rising_prices]
                    }
                elif query_type == "monthly_spend":
                    stats = await dashboard_service.get_dashboard_data(user_id)
                    context_payload = {
                        "total_purchase_amount": stats.total_purchase_amount,
                        "total_bills": stats.total_bills,
                        "monthly_purchase_summary": [item.model_dump() for item in stats.monthly_purchase_summary]
                    }
                elif query_type == "dealer_comparison" and matched_dealer_a and matched_dealer_b:
                    stats = await dealer_service.compare_dealers(matched_dealer_a, matched_dealer_b, user_id)
                    context_payload = stats.model_dump()
                else:
                    context_payload = {"message": "No database statistics available for this query."}
            except Exception as e:
                logger.error(f"Error compiling database context for chat: {e}")
                context_payload = {"error": f"Failed to retrieve database context: {str(e)}"}

            synthesis_prompt = (
                "You are the AI Procurement Assistant. Here is the mathematical purchase history context fetched from our database:\n"
                f"{json.dumps(context_payload, indent=2)}\n\n"
                f"Answer the user's query: \"{user_query}\" using ONLY the context provided above.\n"
                "Rules:\n"
                "- Be conversational, direct, and concise.\n"
                "- Always use the names of products and dealers exactly as they appear in the context.\n"
                "- Never guess or hallucinate any prices, quantities, or savings not present in the context.\n"
                "- If the context has no data or is empty, tell the user politely that you don't have enough invoice records in the database to answer."
            )
            messages = [
                {"role": "system", "content": synthesis_prompt},
                {"role": "user", "content": user_query}
            ]

        # --- Phase 5: Synthesis & Natural Language Response ---
        try:
            synthesis_resp = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                extra_headers={
                    "HTTP-Referer": "https://github.com/vudovn/ag-kit", 
                    "X-Title": "AI-powered Purchase Intelligence System"
                },
                temperature=0.2,
                max_tokens=600
            )
            
            if not synthesis_resp or not getattr(synthesis_resp, "choices", None) or not synthesis_resp.choices:
                raise RuntimeError("Empty or invalid response from synthesis API")
                
            response_text = synthesis_resp.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Failed to synthesize conversational response: {e}")
            response_text = "I compiled the context but encountered an error generating the final chat response."



        return {
            "response": response_text,
            "query_type": query_type,
            "extracted_parameters": {
                "product_name": matched_product or product_name,
                "dealer_a": matched_dealer_a or dealer_a,
                "dealer_b": matched_dealer_b or dealer_b
            }
        }

llm_chat_service = OpenRouterChatService()
