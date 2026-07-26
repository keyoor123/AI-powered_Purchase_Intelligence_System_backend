import base64
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Union, List, Any, Dict
from pathlib import Path
from openai import AsyncOpenAI
from app.utils.config import settings
from app.prompts.prompt_manager import get_bill_extraction_system_prompt, get_bill_extraction_user_prompt

logger = logging.getLogger(__name__)

class BaseLLMExtractor(ABC):
    """Abstract base class for LLM extraction layer to support provider independence."""
    
    @abstractmethod
    async def extract_bill_data(self, ocr_text: str, image_path: Union[str, List[str]]) -> dict:
        """
        Extracts structured bill details using Vision/LLM.
        
        Args:
            ocr_text: Raw text extracted by the OCR layer
            image_path: Path to the preprocessed image file
            
        Returns:
            Dict containing structured bill fields
        """
        pass


class OpenRouterExtractor(BaseLLMExtractor):
    """OpenRouter-based implementation of structured bill extractor."""
    
    def __init__(self):
        # Initialize the OpenAI compatible client for OpenRouter
        # Base url is configured in settings
        self.api_key = settings.OPENROUTER_API_KEY
        self.model = settings.OPENROUTER_MODEL
        self.base_url = settings.OPENROUTER_BASE_URL
        
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY environment variable is empty. Vision LLM extraction will fail unless configured.")

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def _encode_image_to_base64(self, image_path: str) -> str:
        """Encodes local image to base64 format for Vision API."""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found for base64 encoding: {image_path}")
            
        # Determine mime type
        suffix = path.suffix.lower()
        mime_type = "image/png"
        if suffix in [".jpg", ".jpeg"]:
            mime_type = "image/jpeg"
        elif suffix == ".webp":
            mime_type = "image/webp"

        with open(path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
            
        return f"data:{mime_type};base64,{encoded_string}"

    def _clean_json_response(self, text: str) -> dict:
        """Strips markdown and parses the LLM output into a dictionary."""
        # Find JSON blocks: ```json ... ```
        pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
        match = re.search(pattern, text, re.DOTALL)
        
        if match:
            json_str = match.group(1)
        else:
            # Fallback: try to find any JSON-like boundaries
            json_str = text.strip()
            # Clean possible starting/ending markdown if regex missed
            if json_str.startswith("```"):
                json_str = json_str.lstrip("`").lstrip("json").rstrip("`").strip()

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode LLM response as JSON. Cleaned string: {json_str}. Error: {e}")
            raise ValueError(f"LLM output could not be parsed as JSON: {e}")

    def _clean_extracted_items(self, data: dict) -> dict:
        """Helper to sanitize and clean extracted LLM items from taxes and surcharges."""
        if "items" not in data or not isinstance(data["items"], list):
            return data

        cleaned_items = []
        price_adjustments_amount = 0.0

        # Keywords for tax or rounding/discount lines
        tax_rounding_keywords = ["cgst", "sgst", "igst", "vat", "tax", "round off", "rounding", "discount", "less :"]
        # Keywords for price increments / surcharges
        adjustment_keywords = ["price increment", "surcharge", "increment", "extra charge"]

        for item in data["items"]:
            prod_name = item.get("product", "").strip().lower()
            if not prod_name:
                continue

            # Check if it's a tax or rounding line
            is_tax_or_rounding = any(kw in prod_name for kw in tax_rounding_keywords)
            # Check if it's a price adjustment
            is_adjustment = any(kw in prod_name for kw in adjustment_keywords)

            if is_tax_or_rounding:
                # Skip tax and rounding lines in products
                continue
            elif is_adjustment:
                # Accumulate surcharge amounts to merge into actual products
                try:
                    price_adjustments_amount += float(item.get("amount") or 0.0)
                except (ValueError, TypeError):
                    pass
            else:
                # Keep actual products, cast numeric values safely
                try:
                    item["quantity"] = float(item.get("quantity") or 0.0)
                    item["price"] = float(item.get("price") or 0.0)
                    item["amount"] = float(item.get("amount") or 0.0)
                except (ValueError, TypeError):
                    pass
                cleaned_items.append(item)

        # Merge the accumulated price adjustments to the valid products
        if price_adjustments_amount > 0 and cleaned_items:
            target_item = cleaned_items[0]
            try:
                old_amount = target_item.get("amount", 0.0)
                new_amount = round(old_amount + price_adjustments_amount, 2)
                target_item["amount"] = new_amount
                
                qty = target_item.get("quantity", 1.0)
                if qty > 0:
                    target_item["price"] = round(new_amount / qty, 2)
            except Exception as e:
                logger.error(f"Failed to distribute price adjustment: {e}")

        # Enforce schemas constraints (positive values)
        for item in cleaned_items:
            if item.get("quantity", 0.0) <= 0:
                item["quantity"] = 1.0
            if item.get("price", 0.0) < 0:
                item["price"] = abs(item["price"])
            if item.get("amount", 0.0) < 0:
                item["amount"] = abs(item["amount"])

        data["items"] = cleaned_items

        # Recalculate subtotal as the sum of all cleaned item amounts to ensure
        # mathematical consistency with any merged price adjustments/surcharges.
        calculated_subtotal = round(sum(item.get("amount", 0.0) for item in cleaned_items), 2)
        data["subtotal"] = calculated_subtotal

        try:
            if "gst" in data:
                data["gst"] = float(data.get("gst") or 0.0)
            if "total" in data:
                data["total"] = float(data.get("total") or 0.0)
            else:
                # If total is missing, calculate it as subtotal + gst
                data["total"] = round(calculated_subtotal + float(data.get("gst") or 0.0), 2)
        except (ValueError, TypeError):
            pass

        return data

    async def extract_bill_data(self, ocr_text: str, image_path: Union[str, List[str]]) -> dict:
        """Passes image (base64) and OCR text to OpenRouter to parse invoice data."""
        logger.info(f"Initiating OpenRouter Vision LLM extraction using model: {self.model}")
        
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is not configured. Extraction aborted.")

        try:
            system_prompt = get_bill_extraction_system_prompt()
            user_prompt = get_bill_extraction_user_prompt(ocr_text)

            user_content = [
                {
                    "type": "text",
                    "text": user_prompt
                }
            ]

            # Append single or multiple images
            if isinstance(image_path, list):
                for p in image_path:
                    base64_image_url = self._encode_image_to_base64(p)
                    user_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": base64_image_url
                        }
                    })
            else:
                base64_image_url = self._encode_image_to_base64(image_path)
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": base64_image_url
                    }
                })

            # Build messages for Vision LLM
            messages = [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ]

            # Call OpenRouter API
            # extra_headers for OpenRouter listing/rankings
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                extra_headers={
                    "HTTP-Referer": "https://github.com/vudovn/ag-kit", 
                    "X-Title": "AI-powered Purchase Intelligence System"
                },
                temperature=0.0,
                max_tokens=1500
            )

            if not response or not hasattr(response, "choices") or not response.choices:
                logger.error(f"OpenRouter API returned an invalid response structure: {response}")
                raise RuntimeError("API returned empty choices or invalid response.")

            raw_response_text = response.choices[0].message.content
            if raw_response_text is None:
                logger.error("OpenRouter API returned None as choice content.")
                raise RuntimeError("API returned empty text content.")

            logger.info("LLM extraction API call finished. Cleaning response...")
            
            structured_data = self._clean_json_response(raw_response_text)
            
            # Run post-extraction Python cleaning to filter out non-product rows (taxes, rounding)
            try:
                structured_data = self._clean_extracted_items(structured_data)
                logger.info("Structured JSON cleaned of non-product lines successfully.")
            except Exception as e:
                logger.warning(f"Error during post-extraction cleaning: {e}")

            logger.info("Structured JSON extracted successfully.")
            return structured_data

        except Exception as e:
            logger.error(f"Error during OpenRouter LLM extraction: {e}")
            raise RuntimeError(f"Vision LLM extraction failed: {e}")

# Instantiate singleton extractor
llm_extractor = OpenRouterExtractor()
